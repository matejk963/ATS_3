#!/usr/bin/python3
# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import print_function

import collections
import copy
import datetime
import logging
import operator
import re
import time
import uuid

import six
from six.moves import range

import autotrader_lib.common as COMMON
import autotrader_core.persistence as PERSIST
import autotrader_core.utils
import autotrader_lib.util as ALU

log = logging.getLogger("autotrader.exchange_trading")

global_hash_generator = COMMON.UniqueIDGenerator()

# Set the start and end definition to unix timestamps for product debugging purposes
TRACE_PRODUCT_START = 1460929500
TRACE_PRODUCT_END = TRACE_PRODUCT_START + 900
TRACE_PRODUCT_START = None
INDICATOR_HISTORY_TIMESTEP = 10
# For brokers where public and own orders are combined into a single order per price,
# we need to store the original quantity in case a public order is wrongly deleted by an own order.
# This is the number of deleted public orders we store per product.
# The larger the number, the more memory is used. If the number is too small, we risk loosing public orders.
COMBINED_ORDER_BROKER_BUFFER_LENGTH = 20


def dbg_condition(product):
    return TRACE_PRODUCT_START is not None \
        and product.delivery_start == TRACE_PRODUCT_START \
        and product.delivery_end == TRACE_PRODUCT_END


class MetaDataDict(dict):
    """
    A dict subclass that provides the update_from_data_line method and a list of expected keys.

    WARNING: No checks are performed to enforce that all keys are inside valid keys.
    """
    valid_keys = []  # Set on subclass

    def update_from_data_line(self, line):
        """
        Iterate over self.valid_keys and fill them from corresponding items in the "line" dict.

        :param line: A single entry in a translated exchange message's data field.
        :type line: dict
        """
        changed = False
        for key in self.valid_keys:
            if key in line:
                if key not in self or self[key] != line[key]:
                    changed = True
                self[key] = line[key]
        return changed


class Capacity(object):
    """ Defines the available capacity between two areas during a specific delivery span

    :ivar int in_capacity: volume allowed to be imported between delivery_area_from and delivery_area_to
    :ivar int out_capacity: volume allowed to be exported between delivery_area_from and delivery_area_to
    :ivar str publication_time: date format when the capacity has been published
    :ivar int delivery_start: Unix timestamp of the delivery start
    :ivar int delivery_end: Unix timestamp of the delivery end
    :ivar str delivery_area_from: delivery area from where the volume will be transported
    :ivar str delivery_area_to: delivery area into where the volume will be transported
    :ivar bool internal: False if XBID, True otherwise
    :ivar int sequence_number: An event counter from the exchange, which is being incremented when the list of
                               capacities gets updated
    """
    def __init__(self, exchange, in_capacity, out_capacity, publication_time,
                 delivery_start, delivery_end, delivery_area_from, delivery_area_to, internal, sequence_number):
        self.exchange = exchange
        self.in_capacity = in_capacity
        self.out_capacity = out_capacity
        self.publication_time = publication_time
        self.delivery_start = delivery_start
        self.delivery_end = delivery_end
        self.delivery_area_from = delivery_area_from
        self.delivery_area_to = delivery_area_to
        self.internal = internal
        self.sequence_number = sequence_number

    def update(self, in_capacity, out_capacity, publication_time, delivery_start, delivery_end,
               delivery_area_from, delivery_area_to, internal, sequence_number=None, timestamp=None):
        self.in_capacity = in_capacity
        self.out_capacity = out_capacity
        self.publication_time = publication_time
        self.delivery_start = delivery_start
        self.delivery_end = delivery_end
        self.delivery_area_from = delivery_area_from
        self.delivery_area_to = delivery_area_to
        self.internal = internal
        if sequence_number:
            self.sequence_number = sequence_number

        self.update_db(timestamp)

    def update_db(self, timestamp):
        PERSIST.MongoDBConnector().update_db_capacities(self, timestamp)


class Capacities(object):

    def __init__(self, exchange):
        self._capacities = autotrader_core.utils.recursivedict()
        self.exchange = exchange

    def update_from_json(self, struct, current_timestamp):
        if struct["message_type"] == COMMON.Response.capacities:
            changed_capacities = []

            for line in struct["data"]:
                # cap_* helper variables to enhance readability
                cap_time_range = self._capacities[(line["delivery_start"], line["delivery_end"])]
                cap_delivery_range = cap_time_range[line["delivery_area_from"]][line["delivery_area_to"]]
                capacity = cap_delivery_range[line["internal"]] or None
                if capacity is not None:
                    capacity.update(
                        line["in_capacity"],
                        line["out_capacity"],
                        line["publication_time"],
                        line["delivery_start"],
                        line["delivery_end"],
                        line["delivery_area_from"],
                        line["delivery_area_to"],
                        line["internal"],
                        line["event_sequence_no"],
                        timestamp=current_timestamp
                    )
                else:
                    capacity = Capacity(
                        struct["exchange"],
                        line["in_capacity"],
                        line["out_capacity"],
                        line["publication_time"],
                        line["delivery_start"],
                        line["delivery_end"],
                        line["delivery_area_from"],
                        line["delivery_area_to"],
                        line["internal"],
                        line["event_sequence_no"]
                    )
                    # cap_* helper variables to enhance readability
                    cap_time_range = self._capacities[(capacity.delivery_start, capacity.delivery_end)]
                    cap_delivery_range = cap_time_range[capacity.delivery_area_from][capacity.delivery_area_to]
                    cap_delivery_range[capacity.internal] = capacity
                    capacity.update_db(current_timestamp)

                changed_capacities.append(capacity)

        return changed_capacities


class ProductsPriorityQueue(autotrader_core.utils.PriorityQueue):

    timespan = COMMON.TIMER_SLEEP_FAST

    def add_immediate_products(self, products, timestamp):
        for product in (p for p in products if p.immediate_action):
            product.next_action = timestamp - product.next_action_time_delta(timestamp)
            product.immediate_action = False
            self.poppush(product)

    def add_products(self, products, timestamp):
        self.add_immediate_products(products, timestamp)
        not_queued_products = set(products) - set(self.items)
        for product in not_queued_products:
            self.push(product)

    def change_next_timestamp(self, product, timestamp):
        if product.delivery_start - timestamp > COMMON.HOUR:
            product.next_action += COMMON.MINUTE
        else:
            product.next_action += COMMON.MINUTE / COMMON.NUM_REPETITIONS

    def get_products(self, products, timestamp):
        def pop_append(products_for_action):
            prod = self.pop()
            products_for_action.append(prod)
            self.change_next_timestamp(prod, timestamp)
        if not products:
            return []
        self.add_products(products, timestamp)
        products_for_action = []
        number_of_pops = len([prod for prod in self.items if prod.next_action < timestamp + self.timespan])
        if number_of_pops == 0:
            return []
        for unused_i in range(number_of_pops):
            pop_append(products_for_action)
        return products_for_action

    def __repr__(self):
        return "\n".join("ProductPriorityQueue {item.name} {item.next_action}".format(item=item)
                         for item in self.items)


class Product(object):
    """Defines a product (EPEX: Contract) on an exchange. The class holds both
    the lists of trades concluded and the order books.

    :ivar str product_id: The exchange's product id (EPEX: ContractID)
    :ivar str name: The name of the product
    :ivar int delivery_start: Unix timestamp of the product's delivery begin
    :ivar int delivery_end: Unix timestamp of the product's delivery end
    :ivar str product_type: The exchange's product type
    :ivar TradeList trades: Contains the product's trades
    :ivar OrderBook orders: Contains the product's order books
    :ivar bool immediate_action: If set to True, the immediate_action flag allows
                                     for adding the product to the top of the product
                                     priority queue, which will lead to an immediate
                                     activation of strategies for this product at the
                                     next "timer_fast" event.
    :ivar int next_action: Specifies next timestamp starting from which we expect
                               activation of strategies for this product at the next
                               "timer_fast" event.
    :ivar dict com_price_deltas: Dictionary with keys corresponding to
                                     delivery_areas and values holding a tuple with
                                     price deltas, i.e. `(buy_price_delta, sell_price_delta)`,
                                     which specify price tolerance for com trader orders.
    :ivar float locked_until: Specifies the timestamp until the product is locked
    :ivar autotrader_core.utils.InstanceLock order_lock: Contains product lock due to orders modification.
                                                          Also known as modification lock
    :ivar autotrader_core.utils.InstanceLock trade_lock: Contains product lock due to orders execution
                                                         Also known as execution lock
    """
    def __init__(self, exchange, product_id, name, delivery_start, delivery_end, product_type, delivery_area_states,
                 trading_phases, current_timestamp=None, market_meta_information=None,
                 lock_timeout=None, indicator_update=False, exchange_initialized=False):
        """
        :param exchange: The name of the exchange
        :type exchange: str
        :param product_id: The exchange's product id (EPEX: ContractID)
        :type product_id: str
        :param name: The name of the product
        :type name: str
        :param delivery_start: Unix timestamp of the product's delivery begin
        :type delivery_start: int or float
        :param delivery_end: Unix timestamp of the product's delivery end
        :type delivery_end: int or float
        :param product_type: The exchange's product type
        :type product_type: str
        :param delivery_area_states: delivery area as key and corresponding state from COMMON.DeliveryAreaState
        :type delivery_area_states: dict[str, str]
        :param trading_phases: delivery_area as key, with info about the trading phase start,
                               trading phase end and trading phase state in an inner dict.
        :type trading_phases: dict[str, dict[str, str|int]]
        :param current_timestamp: time in seconds
        :type current_timestamp: float
        :param market_meta_information: trayport market information containing first_item_id, first_sequence_id,
                                        sequence_span and second_item_id.
        :type market_meta_information: dict[str, dict[str, str]]
        :param lock_timeout: determines product lock timeout for execution and modification
                             in seconds, defaults to None. If set to None, the product
                             stays locked, unless an appropriate modification or execution
                             is received.
        :type lock_timeout: int|None
        :param indicator_update: if set indicators will get updated on all products
        :type indicator_update: bool
        """

        self.exchange = exchange
        self.is_exchange_initialized = exchange_initialized
        self.product_id = product_id
        self.name = name
        if delivery_start is not None:
            delivery_start = int(delivery_start)
        self.delivery_start = delivery_start
        if delivery_end is not None:
            delivery_end = int(delivery_end)
        self.delivery_end = delivery_end
        self._delivery_area_states = delivery_area_states
        self._trading_phases = trading_phases
        self.product_type = product_type
        self.own_order_to_tags = dict()
        self.trades = TradeList(self.exchange, self)
        self.orders = OrderBook(indicator_update, self.is_exchange_initialized)
        self.strategy_data = dict()
        self.last_strategy_infos = dict()
        self.immediate_action = False
        # first assignment for next_action timestamp
        self.time_delta = COMMON.MINUTE
        self.next_action = None
        self.init_next_action_timestamp(current_timestamp)
        if product_id is None:
            self.internal_id = "user_{}".format(uuid.uuid4())
        else:
            self.internal_id = product_id
        self.com_price_deltas = collections.defaultdict(lambda: (0.0, 0.0))
        self.locked_until = 0
        self.market_meta_information = market_meta_information if market_meta_information else {}
        self.order_lock = autotrader_core.utils.ModificationLock(timeout=lock_timeout, instance_name=name)
        self.trade_lock = autotrader_core.utils.ExecutionLock(timeout=lock_timeout, instance_name=name)
        self.tag_lock = autotrader_core.utils.TagLock(timeout=lock_timeout, instance_name=name)
        # List of tuples (public_order_id, delivery_area, broker_id) on combined order brokers, where we need to
        # re-evaluate the quantity on the next timer_fast:
        self._public_order_quantities_to_reevaluate = []

    @property
    def duration(self):
        """Return the product's delivery duration in seconds

        :rtype: int
        """
        return self.delivery_end - self.delivery_start

    @property
    def interval(self):
        """Return the product's delivery interval as start and end in integers

        :rtype: tuple[int, int]
        """
        return self.delivery_start, self.delivery_end

    @property
    def sequence_id(self):
        """
        For TRAYPORT products, return the corresponding (first) sequence id.

        :return: The sequence id on TRAYPORT, None on other exchanges.
        :rtype: str or None
        """
        if self.exchange == COMMON.Exchange.trayport:
            parts = self.product_id.split("_")
            if parts[0] == "dummy":
                return parts[1]
            return parts[0]
        return None

    @property
    def item_id(self):
        """
        For TRAYPORT products, return the corresponding (first) item id.

        :return: The item id on TRAYPORT, None on other exchanges.
        :rtype: str or None
        """
        if self.exchange == COMMON.Exchange.trayport:
            parts = self.product_id.split("_")
            return parts[2] if parts[0] == "dummy" else parts[1]
        return None

    def on_exchange_initialized(self):  # type: () -> None
        """
        Make the order book aware that the exchange is initialized, so we can stop tracking revision number
        """
        self.is_exchange_initialized = True
        self.orders.on_exchange_initialized()

    def init_next_action_timestamp(self, current_timestamp):
        if not current_timestamp:
            current_timestamp = time.time()
        self.next_action = current_timestamp + self.next_action_time_delta(current_timestamp)

    def next_action_time_delta(self, timestamp):
        return (self.time_delta if self.delivery_start - timestamp > COMMON.HOUR
                else int(self.time_delta / float(COMMON.NUM_REPETITIONS)))

    def update(self, name, product_type,
               delivery_start, delivery_end,
               delivery_area_states=None, trading_phases=None,
               current_timestamp=None, market_meta_information=None):
        self.name = name
        self.order_lock.instance_name = name
        self.trade_lock.instance_name = name
        self.product_type = product_type
        if delivery_start is not None:
            delivery_start = int(delivery_start)
        if delivery_end is not None:
            delivery_end = int(delivery_end)
        self.delivery_start = delivery_start
        self.delivery_end = delivery_end
        if delivery_area_states is not None:
            # Update delivery area states; if product area gets inactive, clean its order book and its order_lock
            for area, state in delivery_area_states.items():
                if self._delivery_area_states.get(area) != state:
                    self._delivery_area_states[area] = state
                    if state == COMMON.DeliveryAreaState.inactive:
                        self.cleanup(area)
        if trading_phases is not None:
            self._trading_phases.update(trading_phases)
        if market_meta_information is not None:
            self.market_meta_information = market_meta_information

        self.update_db(current_timestamp)
        # Reinitialize next action on product update
        self.init_next_action_timestamp(current_timestamp)

    def cleanup(self, delivery_area_id):
        """Removes unconfirmed orders from the order book and releases the order lock for these orders
        after the area becomes inactive.

        This internal function conceptually belongs to the product lock mechanism.
        It's purpose is NOT to reduce the memory footprint of the product. (See reset_orderbook)

        :param delivery_area_id: The area for which to perform the cleanup
        :type delivery_area_id: str
        :meta private:
        """
        cleanup = False
        own_orders = self.orders.get(delivery_area_id=delivery_area_id, order_filter=COMMON.OrderFilter.own)
        for order in own_orders:
            if getattr(order, "order_id", None) is None:
                cleanup = True
                log.debug("Removing an internal order with internal_id %s and releasing it from the order lock",
                          order.internal_id)
                self.orders.remove_own_order(order)
                self.order_lock.release_all_for_object_id(order.internal_id)
        if cleanup:
            log.debug("Cleanup for product product %s for area %s is completed: product order lock - %s",
                      self.name, delivery_area_id, self.order_lock.locking_objects)

    def reset_orderbook(self):
        """
        Remove all orderbook data from this product, to reduce memory usage.

        This function is called after the product's delivery_start, when trading is certainly no longer active.
        :meta private:
        """
        log.debug("Cleanup: Resetting OrderBook for product %s (%s), delivery from: %s (UTC)", self.product_id,
                  self.name, ALU.convert_utc_timestamp_to_dt(self.delivery_start))
        # strategies might have references to the OrderBook. By deleting this attribute, we make
        # sure at least this memory is always released. (As historic order ids are by orders of magnitude more
        # than current orders, this dictionary can take quite a lot of memory)
        del self.orders._deleted_public_orders
        # Set the OrderBook to a new object, to release all memory consumed by the OrderBook.
        self.orders = ExpiredOrderBook()

    def update_db(self, timestamp):
        PERSIST.MongoDBConnector().update_db_products(self, timestamp)

    def update_com_price_deltas(self, delivery_area, delta_buy=0.0, delta_sell=0.0):
        """ Updates com price deltas dictionary

        Updates `com_price_deltas` with specified `delivery_area` and
        a tuple `(delta_buy, delta_sell)` as a key and value pair.

        :param str delivery_area: delivery area code (see :class:`COMMON.Area`)
        :param float delta_buy: tolerance price delta for com trader buy orders
                                (should be nonnegative)
        :param float delta_sell: tolerance price delta for com trader sell orders
                                (should be nonnegative)
        """
        available_delivery_areas = COMMON.Area.get_all(exchange=self.exchange)
        if delivery_area in available_delivery_areas and isinstance(delta_buy,
                                                                    (int,
                                                                     float)) and isinstance(delta_sell, (int, float)):
            self.com_price_deltas[delivery_area] = (delta_buy, delta_sell)
            log.debug("Updating com_price_deltas for area %s: delta_buy %s, delta_sell %s",
                      delivery_area, delta_buy, delta_sell)
        else:
            log.warning("Error while updating com_price_deltas: price_deltas for products must be dictionary")

    @property
    def delivery_area_states(self):
        return self._delivery_area_states

    def update_indicators(self, timestamp, force=False):
        self.orders.update_indicators(timestamp, force=force)

    def match_delivery_areas(self, delivery_area_ids):
        for delivery_area in delivery_area_ids:
            if self._delivery_area_states and delivery_area in self._delivery_area_states:
                return True
        return False

    def state(self, delivery_area_id):
        """Returns the state of a product in an area.

        :param delivery_area_id: Return the state in that delivery area.
            Should be set to a member of :class:`common.Area`.
        :type delivery_area_id: str
        :return: :class:`common.DeliveryAreaState.none` if the internal state has
            not been set yet, otherwise a member of :class:`common.DeliveryAreaState`
        """
        if self._delivery_area_states:
            return self._delivery_area_states.get(delivery_area_id, COMMON.DeliveryAreaState.none)
        else:
            return COMMON.DeliveryAreaState.none

    def trading_phase(self, delivery_area_id):
        """Returns the state of a product in an area.

        :param delivery_area_id: Return phase in that delivery area.
            Should be set to a member of :class:`common.Area`.
        :type delivery_area_id: str
        :return: `(None, None, None)` if there are not phases yet, otherwise a tuple of
            (`<unix_timestamp_start>`, `<unix_timestamp_end>`, `<state>`)
        :rtype: (int,int,str)
        """
        if self._trading_phases and delivery_area_id in self._trading_phases:
            return self._trading_phases[delivery_area_id]
        else:
            return None, None, None

    def is_tradable(self, timestamp, delivery_area_id):
        """
        Check if the product is tradable or not

        :param timestamp: unix timestamp
        :type timestamp: float
        :param delivery_area_id: Return phase in that delivery area.
            Should be set to a member of :class:`common.Area`.
        :type delivery_area_id: common.Area
        :return: True if the Product is tradable, false otherwise
        :rtype: bool
        """
        try:
            start, stop, phase = self._trading_phases[delivery_area_id]
            return (
                self._delivery_area_states[delivery_area_id] == COMMON.DeliveryAreaState.active
                and phase in (COMMON.TradingPhase.continuous, None)
                and start <= timestamp <= stop
            )
        except KeyError:
            return False

    def zones_joined(self, area_sell, area_buy, timestamp, skip_de=False):
        """Checks if the conflicting orders are in two areas with open
        borders

        Borders are closed unless all of the areas are in Germany and the current
        timestamp is more than half an hour before the delivery start.

        :param area_sell: area of a sell order in the order conflict (:class:`COMMON.Area`)
        :type area_sell: str
        :param area_buy: area of a buy order in the order conflict (:class:`COMMON.Area`)
        :type area_buy: str
        :param timestamp: time at which areas are checked to be joined
        :type timestamp: float
        :param skip_de: if True, we consider that German zones are disconnected
        :type skip_de: bool
        :return: whether the zones are joined (True) or not (False)
        :rtype: bool
        """
        if area_sell == area_buy:
            return True

        # germany has 4 zones with leadtime for border cap
        if area_sell in COMMON.Area.de_zone and area_buy in COMMON.Area.de_zone and not skip_de:
            return self.delivery_start - timestamp > COMMON.DE_ZONES_JOINED_UNTIL_SEC_BEFORE_DELIVERY

        return False

    def remove_own_orders_from_book(self, orders_to_check, timestamp, reason):
        """ Removes all orders from the order book that have an order ID contained in the received ID list

        :param orders_to_check: list of internal order IDs that need to be removed from the product's order book
        :type orders_to_check: list[str]
        :param timestamp: current timestamp (to store when the deletion happened)
        :type timestamp: float
        """
        for order in self.orders.get(order_filter=COMMON.OrderFilter.own):
            if order.internal_id in orders_to_check:
                if getattr(order, "order_id", None) is None:
                    self.orders.remove_own_order(order, timestamp)
                    log.warning("Removing order '%s', because no order_id was received from the exchange and %s.",
                                order.shortstr, reason)
                elif order.execution_restriction in [COMMON.ExecutionRestriction.fok, COMMON.ExecutionRestriction.ioc]:
                    self.orders.remove_own_order(order, timestamp)
                    log.warning("Removing order '%s', because it has execution restriction %s and %s.",
                                order.shortstr, order.execution_restriction, reason)

    def time_out_product_locks(self, timestamp):
        """
        A helper method to expire old product locks if the timeout has expired.

        :meta private: Should not be used by custom strategies
        :param timestamp: Time out lock in relation to this timestamp
        :type timestamp: float
        :return: A triple containing the released lock objects from the order_lock, the tag_lock and the trade_lock
        :rtype: tuple
        """
        order_locks = self.time_out_order_locks(timestamp)
        tag_locks = self.tag_lock.release_on_timeout(timestamp)
        trade_locks = self.trade_lock.release_on_timeout(timestamp)

        return order_locks, tag_locks, trade_locks

    def time_out_order_locks(self, timestamp):
        """
        If order_lock releases an order object on timeout, we should remove the corresponding order from the order book,
        if the order lacks the order_id

        :meta private: Should not be used by custom strategies
        :param timestamp: Time out orders in relation to this timestamp
        :type timestamp: float
        :return: A list of orders that were released
        :rtype: list
        """
        released_orders = self.order_lock.release_on_timeout(timestamp)
        if released_orders:
            released_orders_internal_ids = [order_obj.object_id for order_obj in released_orders]
            self.remove_own_orders_from_book(released_orders_internal_ids, timestamp, "the order_lock was released "
                                                                                      "on timeout")
        return released_orders

    def is_product_locked(self, timestamp):
        """ Checks if the product is locked due to locking of orders in
        own order book. This function can be used for probing purposes
        in a strategy.

        :param timestamp: current timestamp
        :type timestamp: float
        :return: whether the product is locked (True) or not (False)
        :rtype: bool
        """
        if self.locked_until > timestamp:
            log.warning("product %s is locked until %s", self.name, self.locked_until)
            return True

        return (self.trade_lock.is_locked(timestamp)
                or self.order_lock.is_locked(timestamp)
                or self.tag_lock.is_locked(timestamp))

    def get_exposed_orders(self, area, side, modify_orders):
        """
        Get all own orders that are confirmed by the exchange for the area and direction.

        Orders are sorted based on the price and order site. In case there are modification requests,
        modified orders are used instead.
        :param area: area of trading
        :type area: str
        :param side: buy or sell for all orders. Needed for sorting.
        :type side: str
        :param modify_orders: order_id as key with corresponding orders from COMMON.ResolverState.modify_orders
        :type modify_orders: defaultdict(str, list)
        :return: a list of orders, sorted by price from best (in front of the order book) to worst
        :rtype: list(OwnOrder)
        """
        visible_own_orders = []
        for order in self.orders.get(area, COMMON.OrderFilter.own):
            if (
                    order.quantity > 0
                    and not isinstance(order, ComTraderOrder)
                    and order.direction == side
                    and order.state != COMMON.OrderState.hibe
            ):
                if order.order_id in modify_orders:
                    visible_own_orders.append(modify_orders[order.order_id][0])
                else:
                    visible_own_orders.append(order)
        visible_own_orders.sort(key=lambda order: order.price, reverse=side == COMMON.Direction.buy)
        return visible_own_orders

    def __repr__(self):
        return str(self.__dict__)

    def __hash__(self):
        return hash("{}_{}".format(self.product_id, self.exchange))

    def __eq__(self, other):
        return (self.product_id, self.exchange) == (other.product_id, other.exchange)

    def __ne__(self, other):
        # We need to implement __ne__ based on __eq__, because otherwise python would use __cmp__
        return not self == other

    def __gt__(self, other):
        return self.next_action > other.next_action

    def __cmp__(self, other):
        """
        This is needed for the ProductsPriorityQueue, which uses the heapq algorithm.
        """
        return self.next_action > other.next_action


class Products(object):
    """Holds a set of all products in an exchange, providing filter functions for products.
    """

    def __init__(self, exchange, create_dummy_products, lock_timeout=None, is_null_exchange=False,
                 indicator_update=False):
        """

        :param exchange: The name of the exchange
        :type exchange: str
        :param create_dummy_products: Defines if a dummy product creation is needed or not
        :type create_dummy_products: bool
        :param lock_timeout: determines product lock timeout for execution and modification
                             in seconds, defaults to None. If set to None, the product
                             stays locked, unless an appropriate modification or execution
                             is received.
        :type lock_timeout: int|None
        :param is_null_exchange: Defines if the current exchange is NullExchange or not
        :type is_null_exchange: bool
        :param indicator_update: if set indicators will get updated on all products
        :type indicator_update: bool
        """
        self._products = {}  # type: dict[str, Product]
        self._products_by_delivery = collections.defaultdict(
            set
        )  # {(delivery_start, delivery_end): {product1, product2...}}
        self.exchange = exchange  # type: str
        self.is_exchange_initialized = False
        self.create_dummy_products = create_dummy_products
        self.lock_timeout = lock_timeout
        self.is_null_exchange = is_null_exchange
        self.indicator_update = indicator_update

        # The action limit settings are loaded later during exchange initialization
        # actions_per_broker[broker_id] = deque()
        self.actions_per_broker = {}
        self.settings_per_broker = {}

        # We only fill up product list if DB is accessible and we're not initializing a NullExchange
        if PERSIST.MongoDBConnector().is_initialized and not self.is_null_exchange:
            self.load_from_db()

    def on_exchange_initialized(self):  # type: () -> None
        """
        Helper method to let the products know that the exchange is now initialized
        """
        self.is_exchange_initialized = True
        for product in self._products.values():
            # make them aware that exchange is initialized, and they have to let the order book know it too
            product.on_exchange_initialized()

    def actions_in_rolling_time(self, broker_id, current_timestamp):
        """
        Returns the amount of order actions confirmed by the exchange for a given broker for the last defined
        seconds. autoTRADER orders and ComTraderOrders are both counted (per company).
        If no setting can be found, returns -1.

        :param broker_id: broker_id as string
        :type broker_id: str
        :param current_timestamp: time in seconds
        :type current_timestamp: float
        :return: length of price actions per broker in given time_range. -1 if no limits are used.
        :rtype: int
        """
        if broker_id in self.actions_per_broker:
            try:
                current_time_frame = (
                    current_timestamp - self.settings_per_broker[broker_id][COMMON.ActionLimits.interval])
                while self.actions_per_broker[broker_id][0] < current_time_frame:
                    self.actions_per_broker[broker_id].popleft()
            except IndexError:
                return 0
            return len(self.actions_per_broker[broker_id])
        else:
            return -1

    def update_rolling_order_action_list(self, counted_order_actions_per_broker):
        """
        Adds the order timestamps to the deque list per broker, if broker settings are defined in common.

        :param counted_order_actions_per_broker: list of timestamps of order actions(price updates) per broker.
        :type counted_order_actions_per_broker: dict(list)
        :return: None
        :rtype: None
        """
        for broker_id in self.actions_per_broker:
            self.actions_per_broker[broker_id].extend(counted_order_actions_per_broker[broker_id])

    def load_from_db(self):
        # Here, we load all Products that are found in MongoDB. However, MongoDB has an expiry index, so products are
        # deleted 3 days after delivery end, and thus we do not accumulate products forever.
        # Products are loaded BEFORE we receive the new product data from the exchange, which then updates the
        # existing products and adds new products.
        # This is needed for the following reasons:
        #  * We need to load the executed orders, so we can correctly calculate the OTR
        #  * On exchanges other than trayport, we might not receive the product information for expired products.
        #  * On Trayport, we need to load the dummy products from the database, to ensure all relevant trades are
        #    loaded from MongoDB, even if we no longer receive them from the JD API (e.g. on BOM products)
        product_list = PERSIST.MongoDBConnector().load_db_products(self.exchange)
        for product_data in product_list:
            # we do not want to load this data from persistence because it may be not up to date anymore
            delivery_area_states = {}
            trading_phases = {}
            market_meta_information = {
                key: value
                for info in product_data.get("market_meta_information", {}) for key, value in info.items()
            }

            product = Product(
                self.exchange,
                product_data["product_id"],
                product_data["name"],
                ALU.convert_dt_to_timestamp(product_data["delivery_start"]),
                ALU.convert_dt_to_timestamp(product_data["delivery_end"]),
                product_data["type"],
                delivery_area_states,
                trading_phases,
                market_meta_information=market_meta_information,
                lock_timeout=self.lock_timeout,
                indicator_update=self.indicator_update,
                exchange_initialized=self.is_exchange_initialized
            )

            # no update_db here, the data comes from the db!
            self._products[product_data["product_id"]] = product

    def get_total_order_volume(self, products, delivery_area_id, order_filter, portfolio_key=None, internal_id=None):
        """Function returns total order volume exposed for products

        :param products: list or iterator of products to be used in the total order volume evaluation
        :param str delivery_area_id: delivery area, member of :class:`COMMON.Area`
        :param str order_filter: filter, member of :class:`COMMON.OrderFilter`
        :param str portfolio_key: determines trading portfolio (or strategy id)
        :param str internal_id: internal_id of an order. If specified, the order is removed from the volume evaluation

        :return: total order volume
        """
        total_volume = sum([product.orders.get_volume(delivery_area_id, order_filter, internal_id, portfolio_key)
                            for product in products])
        return total_volume

    def get_total_traded_volume(self, products, delivery_area_id, trade_filter, portfolio_key=None, balance=False):
        """Function returns total traded volume for products

        :param products: list or iterator of products to be used in the total traded volume evaluation
        :param str delivery_area_id: delivery area, member of :class:`COMMON.Area`
        :param str trade_filter: filter, member of :class:`COMMON.TradeFilter`
        :param str portfolio_key: determines trading portfolio (or strategy id)
        :param bool balance: determines if the traded balance volume should be returned
                            (i.e. traded buy - traded sell) or not
        :return: total traded volume
        """
        if balance:
            total_volume = sum([product.trades.get_balance(delivery_area_id, portfolio_key) for product in products])
        else:
            total_volume = sum([product.trades.get_volume(delivery_area_id, trade_filter, portfolio_key)
                                for product in products])
        return total_volume

    def update_from_json(self, struct, current_timestamp, autotrader_user=None, combined_brokers=None,
                         confirm_lock=None, multimatching_trade_lock_brokers=None):
        """Update Product based on new orderbook data in struct

        :type struct: dict
        :type current_timestamp: float
        :type autotrader_user: str
        :type combined_brokers: frozenset[str]
        :type confirm_lock: str
        :type multimatching_trade_lock_brokers: frozenset[str]
        """
        if combined_brokers is None:
            combined_brokers = frozenset()
        if multimatching_trade_lock_brokers is None:
            multimatching_trade_lock_brokers = frozenset()

        if struct["message_type"] == "product":
            changed_products = []
            for line in struct["data"]:
                delivery_area_states = {}
                if "delivery_area_states" in line:
                    delivery_area_states = dict((key, value["state"]) for key, value
                                                in line["delivery_area_states"].items())

                trading_phases = {}
                if "trading_phases" in line:
                    # TODO: many tests are broken because they do not consider the trading phase state in the test input
                    # TODO: once the test inputs are corrected, replace 'value.get("state")' with 'value["state"]'
                    trading_phases = dict((key, (value["start"], value["end"], value.get("state"))) for key, value
                                          in line["trading_phases"].items())
                product_type = line["product_type"]
                delivery_start = line["delivery_start"]
                delivery_end = line["delivery_end"]
                product = None
                if line["product_id"] in self._products:
                    product = self._products[line["product_id"]]
                elif product_type == "Intraday_Hour_Power" and (delivery_end - delivery_start) > COMMON.HOUR:
                    product = self.get_by_delivery_span(line["delivery_start"],
                                                        line["delivery_end"],
                                                        product_type=product_type)
                    if product:
                        if product.internal_id in self._products:
                            del self._products[product.internal_id]
                        product.product_id = line["product_id"]
                        self._products[line["product_id"]] = product

                if product:
                    product.update(
                        line["name"],
                        line["product_type"],
                        line["delivery_start"],
                        line["delivery_end"],
                        delivery_area_states,
                        trading_phases,
                        current_timestamp,
                        market_meta_information=line.get("market_meta_information", {}))
                    product.update_db(current_timestamp)
                else:
                    product = Product(
                        struct["exchange"],
                        line["product_id"],
                        line["name"],
                        line["delivery_start"],
                        line["delivery_end"],
                        line["product_type"],
                        delivery_area_states,
                        trading_phases,
                        current_timestamp,
                        market_meta_information=line.get("market_meta_information", {}),
                        lock_timeout=self.lock_timeout,
                        indicator_update=self.indicator_update,
                        exchange_initialized=self.is_exchange_initialized
                    )
                    self._products[line["product_id"]] = product
                    product.update_db(current_timestamp)

                self._products_by_delivery[(product.delivery_start, product.delivery_end)].add(product)

                changed_products.append(product)
            return changed_products

        byprod = self.group_msg_by_product(struct)

        changed_objects = []
        affected_delivery_areas = set()
        for product_id, product_struct in byprod.items():
            if product_id not in self._products:
                if not self.create_dummy_products:
                    continue

                product = Product(
                    struct["exchange"],
                    product_id,
                    "DUMMY",
                    0,
                    0,
                    "",
                    dict(),
                    dict(),
                    current_timestamp,
                    lock_timeout=self.lock_timeout,
                    indicator_update=self.indicator_update,
                    exchange_initialized=self.is_exchange_initialized
                )
                self._products[product_id] = product
                self._products[product_id].update_db(current_timestamp)

            if struct["message_type"] in ("order_book", "order_execution"):
                # we pass also the list of brokerids which need special handling (combined_brokers).
                # They are defined in the exchange class and forwarded to the orderbook
                changed, affected, counted_order_actions_per_broker = self._products[
                    product_id].orders.update_from_json(
                    product_struct, self._products[product_id], current_timestamp, autotrader_user, combined_brokers,
                    confirm_lock=confirm_lock, multimatching_trade_lock_brokers=multimatching_trade_lock_brokers)
                changed_objects.extend(changed)
                affected_delivery_areas.update(affected)
                self.update_rolling_order_action_list(counted_order_actions_per_broker)

            if (struct["message_type"] == "order_execution" and struct["exchange"] == COMMON.Exchange.nordpool) or \
                    struct["message_type"] in ("public_trade", "own_trade", "internal_trade"):
                changed, affected = self._products[product_id].trades.update_from_json(product_struct,
                                                                                       self._products[product_id],
                                                                                       current_timestamp,
                                                                                       autotrader_user)

                changed_objects.extend(changed)
                affected_delivery_areas.update(affected)

        return changed_objects, affected_delivery_areas

    def group_msg_by_product(self, struct):
        """
        Create a list of messages aggregated by product

        From a single message with a long list of data containing multiple products, create a list of messages, each of
        them  with all entries in data corresponding to the same product.

        :param struct: The input message of message_type order_book, order_execution, public_trade,
                       own_trade or internal_trade
        :type struct: dict
        :return: A dict of structs, with product_ids as keys and one message per key
        :rtype: dict[dict]
        """
        # group by product_id
        stripped_struct = dict(struct)  # copy struct
        del stripped_struct["data"]
        # reset data, every grouped struct will get only its data
        byprod = collections.defaultdict(lambda: dict(list(stripped_struct.items()) + [("data", [])]))
        for line in struct["data"]:
            if line["product_id"] is None:
                product = self.get_by_product_name(line["product_name"])
                if product:
                    line["product_id"] = product.product_id
                else:
                    raise COMMON.ProductNotFound(line["product_name"])
            byprod[line["product_id"]]["data"].append(line)
        return byprod

    def get_by_id(self, product_id):
        # type: (str) -> Product
        """Returns a product object if found for the product id given
        or raises ProductNotFound exception if not"""
        product = self._products.get(product_id, None)
        if not product:
            raise COMMON.ProductNotFound(product_id)
        return product

    def get_by_timerange(self, start, end=None, product_type=None):
        """Returns a list of all products found for the timerange and the product type given.

        :param start: A unix timestamp. Return products with `delivery_start` greater or equal to start
        :param end: A unix timestamp, defaults to None.
                    Return products with `delivery_end` smaller or equal to end.
                    If end is None, there is no restriction on when delivery ends, and the
                    products are filtered only by the start of the delivery.
        :param product_type: optional, defaults to None. Return products matching
                             the `product_type`, for example "Intraday_Hour_Power"
                             or "Intraday_Quarter_Hour_Power".
        :type start: int
        :type end: int
        :type product_type: str
        :rtype: list[APITR.Product]
        """
        found = [
            p for p in self._products.values()
            if (
                p.delivery_start >= start
                and (not end or p.delivery_end <= end)
                and (not product_type or p.product_type == product_type)
            )
        ]

        return found

    def get_overlapping_with_timerange(self, start, end):
        """Returns a list of products, whose delivery span overlaps with a timerange.

        :param start: A unix timestamp determining start of the timerange
        :type start: int or float
        :param end: A unix timestamp determining end of the timerange.
        :type end: int or float
        :rtype: list[APITR.Product]
        """
        products = [p for p in self._products.values() if (p.delivery_start < end and p.delivery_end > start)]
        return products

    def get_all_by_delivery_span(self, start, end):
        """

        :param int start: A unix timestamp determining product delivery start
        :param int end: A unix timestamp determining product delivery end
        :return: a list of products with the specified delivery interval
        :rtype: list[APITR.Product]
        """
        return self._products_by_delivery[(start, end)]

    def get_by_delivery_span(self, start, end, product_type=None):
        """Returns a product with defined delivery start, end, and product type

        :param int start: A unix timestamp determining product delivery start
        :param int end: A unix timestamp determining product delivery end
        :param str product_type: determines product_type
        :rtype: APITR.Product
        """
        for prod in self._products_by_delivery[(start, end)]:
            if not product_type or prod.product_type == product_type:
                return prod
        return None

    def get_by_product_name(self, name):
        """Returns a product if found, else returns None.

        :param name: Return products having this `name`
        :type name: str
        :rtype: APITR.Product
        """
        for product in self._products.values():
            if product.name == name:
                return product

    def get_by_market_metadata(self, metainfo_dict):
        """Returns a list of products that match the metainfo criteria passed on to the function.

        :param metainfo_dict: Filter dictionary for product.market_metadata
        :type metainfo_dict: dict
        :rtype: APITR.Product
        """
        result = []
        for product in self._products.values():
            for key, value in metainfo_dict.items():
                if product.market_meta_information.get(key, None) != value:
                    break
            else:
                result.append(product)
        return result

    def get_slot_product(self, slot_dict):
        """Returns the product specified in the slot. Will return None if it can't be found.

        :param slot: The slot dictionary
        :type slot: dict
        :return: The product of the slot or None
        :rtype: APITR.Product
        """
        if slot_dict.get("product_id"):
            return self.get_by_id(slot_dict["product_id"])
        elif slot_dict.get("product_name"):
            return self.get_by_product_name(slot_dict["product_name"])
        log.error("slot_request: No product specified")

    def get_active_products(self, delivery_area_id=None):
        """Returns a product if found, else returns None.

        :param delivery_area_id: Return products active in that delivery area.
            Should be set to a member of :class:`common.Area`.
        :type delivery_area_id: str
        :rtype: list[APITR.Product]
        """
        if delivery_area_id is None:
            return [p for p in self._products.values() if any((p.state(area) == COMMON.DeliveryAreaState.active
                                                               for area in p.delivery_area_states))]
        else:
            return [p for p in self._products.values() if p.state(delivery_area_id) == COMMON.DeliveryAreaState.active]

    def get_all(self):
        """
        Returns all products

        :rtype: list[Product]
        """
        return list(self._products.values())

    def iter_by_sequence_ids(self, sequence_ids, include_dummy_products=True):
        """
        Generator yielding all products which belong to any of the given sequence_ids.

        :param sequence_ids: A list of sequence ids.
        :type sequence_ids: list(str)
        :param include_dummy_products: True if dummy products should be included (e.g. when querying past trades),
                                       False otherwise. Only makes a difference for prompt and BOM products
        :type include_dummy_products: bool
        """
        for product in self.get_all():
            if ((include_dummy_products or not product.product_id.startswith("dummy"))
                    and product.sequence_id in sequence_ids):
                yield product

    def update_indicators(self, timestamp):
        for product in self.get_active_products():
            product.update_indicators(timestamp)

    def add_block_product(self, delivery_start, delivery_end):
        product_type = "Intraday_Hour_Power"
        product = self.get_by_delivery_span(delivery_start, delivery_end, product_type)
        if product:
            log.debug("An Hourly Block product with delivery {} - {} already exists"
                      "".format(delivery_start, delivery_end))
            return product
        if (delivery_end - delivery_start) % COMMON.HOUR != 0:
            log.debug("Invalid Block Product: Block product time span should be multiple of hour")
            return None
        elif (delivery_end - delivery_start) < 2 * COMMON.HOUR:
            log.debug("Invalid Block Product: Block product time span should be at least 2 hours")
            return None

        dt_delivery_start = datetime.datetime.utcfromtimestamp(delivery_start)
        if dt_delivery_start.minute != 0 or dt_delivery_start.second != 0:
            log.debug("Invalid Block Product: Block product start should be on a full hour")
            return None
        product = Product(
            exchange=self.exchange,
            product_id=None,
            name="USERProd",
            delivery_start=delivery_start,
            delivery_end=delivery_end,
            product_type=product_type,
            delivery_area_states={},
            trading_phases={},
            current_timestamp=None,
            lock_timeout=self.lock_timeout,
            indicator_update=self.indicator_update,
            exchange_initialized=self.is_exchange_initialized
        )
        self._products[product.internal_id] = product
        self._products_by_delivery[(delivery_start, delivery_end)].add(product)
        return product


class Order(object):
    """Defines an order and is the base class for OwnOrder and PublicOrder.

    Attributes:

        **direction** (str): Buy (bid) or sell (ask) order, member of :class:`COMMON.Direction`

        **exchange** (str): Exchange where the order is placed, member of :class:`COMMON.Exchange`

        **state** (str): denotes the state or status of the order at the Exchange, for example,
        active or hibernated (deactivated).

        **tags** (dict): dict containing custom information from the strategies

        **product** (Product): :class:`Product` object for the order

        **quantity** (float): The order's volume in MW

        **price** (float): The order's price in Euro per MWh

        **delivery_area_id** (str): Area, member of :class:`common.Area`

        **execmode** (str): member of :class:`COMMON.InternalExecutionMode`, defines
            the behaviour for internal executions.

        **order_type** (str): determines order type, for example regular ("O")
            or iceberg ("I"), member of :class:`COMMON.OrderType`

        **visible_quantity** (float): order quantity visible to other participants
            on the market (applicable only to iceberg ("I") orders)

        **clip_quantity** (float): order quantity defining maximal visible
            quantity to other participants on the market (applicable only to
            iceberg ("I") orders)

        **internal_market_price** (float): order price used on the internal market

        **broker_id** (str): ID of the broker brokering the order. None if no broker is used.


    Mapping to internal and external systems:

    Internal classification:

    - internal_id: uuid
    - internal_state: InternalOrderState

    External classification:

    - tags with keys without underscore at the beginning.
      They will be saved in the txt field on the epex spot and
      in the FreeText field on the Nordpool.
    - clOrdrId for the epex exchange will not be used because
      there is no nordpool equivalent for this field.
    """

    def __init__(self,
                 direction,
                 product,
                 delivery_area_id,
                 quantity,
                 price,
                 exchange,
                 order_type=COMMON.OrderType.order,
                 visible_quantity=None,
                 clip_quantity=None,
                 state=None,
                 last_update_user=None,
                 original_user=None,
                 internal_market_price=None,
                 tags=None,
                 engine_id=None,
                 client_order_id=None,
                 clip_price_change=None,
                 execmode=None,
                 system_rank=None,
                 is_tradable=True,
                 counter_party_ok=True,
                 implied=False,
                 broker_id=None,
                 **kwargs
                 ):
        """

        :param direction: Buy (bid) or sell (ask) order, member of :class:`COMMON.Direction`
        :type direction: str
        :param product: Product object for the order
        :type product: Product
        :param delivery_area_id: Area, member of :class:`common.Area`
        :type delivery_area_id: str
        :param quantity: The order's volume in MW
        :type quantity: float
        :param price: The order's price in Euro per MWh
        :type price: float
        :param exchange: Exchange where the order is placed, member of :class:`COMMON.Exchange`
        :type exchange: str
        :param order_type: e.g. regular ("O") or iceberg ("I"), member of :class:`COMMON.OrderType`
        :type order_type: str
        :param visible_quantity: quantity visible to other participants on the market (only for iceberg ("I") orders)
        :type visible_quantity: float
        :param clip_quantity: maximal visible quantity to other participants (only for iceberg ("I") orders)
        :type clip_quantity: float
        :param state: denotes the state or status of the order at the Exchange, e.g. active or hibernated (deactivated).
        :type state: str
        :param last_update_user: last user to updated this order
        :type last_update_user: str
        :param original_user: user who created this order
        :type original_user: str
        :param internal_market_price: order price used on the internal market
        :type internal_market_price: float
        :param tags: dict containing custom information from the strategies
        :type tags: dict
        :param client_order_id: client order id, constant over order lifetime, originally uuid
        :type client_order_id: str
        :param clip_price_change: For iceberg ("I") orders only; the price change after each clip is consumed
        :type clip_price_change: str
        :param execmode: member of class InternalExecutionMode, defines the behaviour for internal executions.
        :type execmode: str
        :param str system_rank: determines the rank of the order in the exchange system (Trayport specific).
                                The system rank is used internally by Joule Direct when sorting orders in
                                the Joule front-end.
        :param is_tradable: This attribute indicates whether the order is tradable. [TRAYPORT specific]
        :type is_tradable: bool
        :param counter_party_ok: The currently logged in user's counter party status in relation to this order. This
                                attribute is set to true if the currently logged in user is allowed to hit the order.
                                [TRAYPORT specific]
        :type counter_party_ok: bool
        :param implied: Indicates whether this order is a calculated order [TRAYPORT specific]
        :type implied: bool
        :param broker_id: ID of the broker brokering the trade [TRAYPORT specific]
        :type broker_id: str
        """
        self.direction = direction
        self.product = product  # type: Product
        self.delivery_area_id = delivery_area_id
        self.quantity = round(quantity, 2)
        self.visible_quantity = round(visible_quantity, 2) if visible_quantity else visible_quantity
        self.clip_quantity = round(clip_quantity, 2) if clip_quantity else clip_quantity
        self.price = round(price, 3)
        self._internal_market_price = internal_market_price
        self.exchange = exchange
        self.order_type = order_type
        self.tags = tags or {}
        self._fexe = False
        self.execmode = execmode or COMMON.InternalExecutionMode.default
        self.system_rank = system_rank
        self.is_tradable = is_tradable
        self.counter_party_ok = counter_party_ok
        self.implied = implied
        self.state = state
        self.last_update_user = last_update_user
        self.original_user = original_user
        self.engine_id = engine_id
        self.client_order_id = client_order_id or str(uuid.uuid4())  # uuid needed for np
        self.clip_price_change = clip_price_change
        self._internal_id = None  # type: str|None
        self.creation_timestamp = int(time.time())
        self.last_delete_attempt = None
        self.broker_id = broker_id
        self.route_id = kwargs.get("route_id")

    @classmethod
    def from_data_line(cls, line, product, exchange_id):
        """
        Factory function to translate a line of a message's data field to an Order
        Must be implemented in subclass

        :param line: The dict in the message that describes the Order
        :type line: dict
        :param product: The Product the order is valid for
        :type product: Product
        :param exchange_id: The exchange where the Order is placed
        :type exchange_id: str
        :return: The newly created Order
        :rtype: Order
        """
        raise NotImplementedError

    @property
    def internal_id(self):
        return self._internal_id

    @property
    def internal_market_price(self):
        return self.price

    def validate(self):
        """Validates an order

        Applicable for ICB (iceberg) orders. Here we check, if the
        visible quantity and total quantity of the order are greater than
        or equal the clip quantity, otherwise, the order becomes a regular order
        type.
        """
        if self.order_type == COMMON.OrderType.iceberg:
            if self.clip_quantity and self.visible_quantity and self.quantity >= self.clip_quantity:
                return True
            else:
                log.debug("Order validation: changing ICB order to regular order")
                update_order = {"order_type": COMMON.OrderType.order,
                                "visible_quantity": None,
                                "clip_quantity": None}
                self.update(**update_order)
                return False
        return True

    def match_delivery_areas(self, delivery_area_ids):
        return self.delivery_area_id in delivery_area_ids

    def update(self, **kwargs):
        self.__dict__.update(kwargs)
        return self

    def update_inplace(self, **kwargs):
        """
        Updates the Order in-place and returns whether something (except revision) has changed.

        Note: This is a low-level function that directly modifies self.__dict__,
        without any checking of the keywords.

        :param kwargs: key-value pairs used to update this order
        :type kwargs: dict
        :return: True if any attribute was added or changed
        :rtype: bool
        """
        changed = self.check_order_change(**kwargs)
        self.__dict__.update(kwargs)
        return changed

    def check_order_change(self, **kwargs):
        """
        Returns whether something (except revision) has changed.

        :param kwargs: key-value pairs used to check if something changed for this order
        :type kwargs: dict
        :return: True if any attribute was added or changed
        :rtype: bool
        """
        changed = False
        for key in kwargs:
            if key == "revision":
                continue
            if key not in self.__dict__ or kwargs[key] != self.__dict__[key]:
                changed = True
        return changed

    def update_db(self, timestamp):
        pass

    def can_attempt_delete(self, timestamp):  # (float) -> bool
        """Checks whether enough time has passed to allow another delete order request to be sent for this order."""
        return self.last_delete_attempt is None or self.last_delete_attempt + 5 < timestamp

    def __repr__(self):
        cls_name = self.__class__.__name__
        representation = str(sorted([(k, v) for k, v in self.__dict__.items()
                                     if k not in ("self", "product")])) \
            + ", product:" + self.product.name
        state = self.state
        return "{}({}, {})".format(cls_name, state, representation)

    def __str__(self):
        order_type = self.__class__.__name__
        product = self.product.name
        price = getattr(self, "price", None)
        internal_market_price = self.internal_market_price
        quantity = getattr(self, "quantity", None)
        direction = getattr(self, "direction", None)
        order_id = getattr(self, "order_id", None)
        delivery_area = getattr(self, "delivery_area_id", None)
        execmode = getattr(self, "execmode", None)
        execution_restriction = getattr(self, "execution_restriction", None)
        return ("\n<{} {} for product {}: price {}; internal_market_price {}; "
                "qty {}; {}; order_id {}; restr: {}; execmode: {}>"
                ).format(order_type, direction, product, price, internal_market_price, quantity,
                         delivery_area, order_id, execution_restriction, execmode)


class OrderRegulatoryData(MetaDataDict):
    read_write_keys = ["trading_capacity", "decision_maker", "execution_maker", "derivative_indicator", "dea",
                       "dea_client_id", "liquidity_provision"]
    read_only_keys = ["foreign_order_id", "datetime_nanoseconds_part", "product_classification"]
    valid_keys = read_write_keys + read_only_keys


class OwnOrder(Order):
    """Defines an own order, inherits from Order and adds some fields to it.

    Attributes:

        **execution_restriction** (str): Pass through field for the order execution type (e.g. 'IOC')

        **validity_restriction** (str): Pass through field for the order validity setting

        **validity_date** (int): unix timestamp for the validity if validity_restriction is set

        **portfolio_key** (str): Portfolio of trade. This parameter corresponds to the strategy id

        **order_id** (str): The exchange's order id
    """

    def __init__(self,
                 portfolio_key,
                 execution_restriction,
                 validity_restriction,
                 validity_date,
                 initial_order_id,
                 *args, **kwargs):
        # We have to pop the MiFID fields derivative_indicator, decision_maker, execution_maker, liquidity_provision
        # before the super call, otherwise we would get an argument error, because the base class's __init__ does
        # not support this keyword argument
        derivative_indicator = kwargs.pop("derivative_indicator", None)
        decision_maker = kwargs.pop("decision_maker", None)
        execution_maker = kwargs.pop("execution_maker", None)
        liquidity_provision = kwargs.pop("liquidity_provision", None)

        dea = kwargs.pop("dea", None)
        dea_client_id = kwargs.pop("dea_client_id", None)
        trading_capacity = kwargs.pop("trading_capacity", None)

        self.trading_account = kwargs.pop("trading_account", "")

        self.terms = kwargs.pop("terms", None)

        super(OwnOrder, self).__init__(*args, **kwargs)
        # Update execmode from tags if available
        if self.tags:
            self._set_execmode()
        self.tags["execmode"] = six.text_type(self.execmode)
        self.execution_restriction = execution_restriction
        self.validity_restriction = validity_restriction
        self.validity_date = validity_date
        self.portfolio_key = portfolio_key
        self.tags["portfolio_key"] = self.portfolio_key
        self.revision = None
        self.start_timestamp = None
        self.end_timestamp = None
        self.initial_order_id = initial_order_id
        # Note: order.reactivate is used by autoTRADER to handle hibernation of orders in the internal market.
        #       This flag should not be modified by custom strategies directly.
        self.reactivate = None

        # regulatory_data relevant for markets underlying the MifidII regulation
        self.regulatory_data = OrderRegulatoryData()
        if derivative_indicator is not None:
            self.derivative_indicator = derivative_indicator
        if decision_maker is not None:
            self.decision_maker = decision_maker
        if execution_maker is not None:
            self.execution_maker = execution_maker
        if liquidity_provision is not None:
            self.liquidity_provision = liquidity_provision
        if dea is not None:
            self.dea = dea
        if dea_client_id is not None:
            self.dea_client_id = dea_client_id
        if trading_capacity is not None:
            self.trading_capacity = trading_capacity

        # set portfolio ID if it was given in the internal number of the strategy
        exchange_portfolio_id = re.findall(
            r"@([\w-]+)\Z",
            six.text_type(self.portfolio_key) or ""
        ) if self.portfolio_key else None
        if not exchange_portfolio_id:
            if self.exchange == COMMON.Exchange.nordpool:
                log.debug("Could not read Exchange portfolio id from portfolio key: {}".format(self.portfolio_key))
            self.exchange_portfolio_id = None
        else:
            self.exchange_portfolio_id = exchange_portfolio_id[0]

        if "internal_id" not in self.tags:
            self._internal_id = global_hash_generator.get_uid()
            self.tags["internal_id"] = self._internal_id
        else:
            self._internal_id = self.tags["internal_id"]

    @classmethod
    def from_data_line(cls, line, product, exchange_id,  # pylint: disable=arguments-differ
                       portfolio_key=None,
                       order_user=None,
                       tags=None):
        """
        Factory function to translate a line of a message's data field to an OwnOrder

        :param line: The dict in the message that describes the Order
        :type line: dict
        :param product: The Product the order is valid for
        :type product: Product
        :param exchange_id: The exchange where the Order is placed
        :type exchange_id: str
        :param portfolio_key: The strategy that placed this order. Can be given for speed-up.
                              If this is not given, it will be taken from the line's "txt" field
        :type portfolio_key: Optional[str]
        :param order_user: The user who created the Order. Optional; if not given, use line["user"]
        :type order_user: Optional[str]
        :param tags: Order tags. Typically a dict with at least the keys "internal_id" (Order-id),
                     "portfolio_key" (The strategy that placed the Order).
                     Optional. If missing, it will be created from the message's text.
        :type tags: Optional[str]
        :return: The newly created OwnOrder
        :rtype: OwnOrder
        """
        if tags is None:
            tags = ALU.parse_order_tags(line["txt"])

        if portfolio_key is None:
            portfolio_key = tags.get("portfolio_key", None)

        if order_user is None:
            order_user = line["user"]

        new_order = cls(portfolio_key,
                        line["execution_restriction"],
                        line["validity_restriction"],
                        line["validity_date"],
                        line["initial_order_id"],
                        line["direction"],
                        product,
                        line["delivery_area_id"],
                        line["quantity"],
                        line["price"],
                        exchange_id,
                        line["type"],
                        line.get("visible_quantity", None),
                        line.get("clip_quantity", None),
                        line["state"],
                        line["last_update_user"],
                        order_user,
                        terms=line.get("terms"),
                        tags=tags,
                        client_order_id=line.get("client_order_id"),
                        broker_id=line.get("broker_id"),
                        engine_id=line.get("engine_id"),
                        system_rank=line.get("system_rank"),
                        is_tradable=line.get("is_tradable", True),
                        implied=line.get("implied", False),
                        counter_party_ok=line.get("counter_party_ok", True),
                        trading_account=line.get("trading_account", ""),
                        route_id=line.get("route_id"),
                        )
        new_order.update(revision=line["revision"], order_id=line["order_id"])
        new_order.regulatory_data.update_from_data_line(line)
        return new_order

    @property
    def derivative_indicator(self):
        return self.regulatory_data.get("derivative_indicator")

    @derivative_indicator.setter
    def derivative_indicator(self, value):
        self.regulatory_data["derivative_indicator"] = value

    @property
    def decision_maker(self):
        return self.regulatory_data.get("decision_maker")

    @decision_maker.setter
    def decision_maker(self, value):
        self.regulatory_data["decision_maker"] = value

    @property
    def execution_maker(self):
        return self.regulatory_data.get("execution_maker")

    @execution_maker.setter
    def execution_maker(self, value):
        self.regulatory_data["execution_maker"] = value

    @property
    def liquidity_provision(self):
        return self.regulatory_data.get("liquidity_provision")

    @liquidity_provision.setter
    def liquidity_provision(self, value):
        self.regulatory_data["liquidity_provision"] = value

    @property
    def dea(self):
        return self.regulatory_data.get("dea")

    @dea.setter
    def dea(self, value):
        self.regulatory_data["dea"] = value

    @property
    def dea_client_id(self):
        return self.regulatory_data.get("dea_client_id")

    @dea_client_id.setter
    def dea_client_id(self, value):
        self.regulatory_data["dea_client_id"] = value

    @property
    def trading_capacity(self):
        return self.regulatory_data.get("trading_capacity")

    @trading_capacity.setter
    def trading_capacity(self, value):
        self.regulatory_data["trading_capacity"] = value

    @property
    def internal_market_price(self):
        if self._internal_market_price is None:
            self._internal_market_price = self.price
        return self._internal_market_price

    @internal_market_price.setter
    def internal_market_price(self, value):
        self._internal_market_price = round(value, 3) if value else value

    def update_db(self, timestamp):
        PERSIST.MongoDBConnector().update_db_own_orders(self, timestamp)

    def modify(self, quantity=None, price=None, internal_market_price=None, trading_account=""):
        modified = copy.copy(self)

        if quantity is not None:
            modified.quantity = quantity
        if price is not None:
            modified.price = price
        if trading_account is not None:
            # we ignore the parameter if the call to the function explicitly states that the value is None
            modified.trading_account = trading_account
        if internal_market_price is None:
            internal_market_price = modified.price
        try:
            modified.internal_market_price = internal_market_price
        except AttributeError:
            log.error("Internal market price of an order cannot be set. This happens if an OwnOrder has been"
                      " modified by the ComTrader. Deleting the order %s", modified.order_id)
            modified.quantity = 0

        modified.original_order = copy.copy(self)
        return modified

    def _set_execmode(self):
        try:
            execmode = int(float(self.tags.get("execmode")))
        except (ValueError, TypeError):
            return
        if execmode in COMMON.InternalExecutionMode.available_execmodes:
            self.execmode = execmode

    def _get_order_entry_params(self):
        if self.exchange == COMMON.Exchange.epex:
            mandatory = dict(pre_arranged="false",
                             type=self.order_type,
                             delivery_area_id=self.delivery_area_id,
                             quantity=self.quantity,
                             price=self.price,
                             side=self.direction,
                             clearing_account_type="P")
            if self.order_type == COMMON.OrderType.iceberg:
                mandatory.update(dict(clip_quantity=self.clip_quantity))
            optional = dict(state=COMMON.OrderState.acti,
                            txt=ALU.serialize_order_tags(self.tags),
                            validity_date=self.validity_date,
                            execution_restriction=self.execution_restriction,
                            exchange_portfolio_id=self.exchange_portfolio_id,
                            validity_restriction=self.validity_restriction)
            if self.product.product_id:
                optional.update(dict(product_id=self.product.product_id))
            else:
                optional.update(dict(product_type=self.product.product_type,
                                     delivery_start=self.product.delivery_start,
                                     delivery_end=self.product.delivery_end))
            return autotrader_core.utils.make_element_params(mandatory, optional)
        elif self.exchange == COMMON.Exchange.nordpool:
            tags = copy.deepcopy(self.tags)
            mandatory = dict(pre_arranged="false",
                             type=COMMON.OrderType.order,
                             delivery_area_id=self.delivery_area_id,
                             quantity=self.quantity,
                             price=self.price,
                             side=self.direction,
                             state=self.state or COMMON.OrderState.acti,
                             txt=ALU.serialize_order_tags(tags),
                             product_id=self.product.product_id,
                             execution_restriction=self.execution_restriction,
                             exchange_portfolio_id=self.exchange_portfolio_id,
                             client_order_id=self.client_order_id,
                             validity_restriction=self.validity_restriction,
                             clearing_account_type="P")
            if self.order_type == COMMON.OrderType.iceberg:
                mandatory.update(dict(clip_quantity=self.clip_quantity,
                                      clip_price_change=self.clip_price_change))
            if mandatory["validity_restriction"] == "GTD":
                mandatory.update(validity_date=self.validity_date)
                optional = {}
            else:
                optional = dict(validity_date=self.validity_date)

            # mandatory field state, is COMMON.OrderState.acti by default for entry orders (compare EPEX)
            # but it can also be hibernated if it is explicitly defined
            mandatory.update(state=self.state or COMMON.OrderState.acti)
            return autotrader_core.utils.make_element_params(mandatory, optional)
        elif self.exchange == COMMON.Exchange.trayport:
            inst_specifier = self.product.market_meta_information.copy()
            inst_specifier["instrument_id"] = self.delivery_area_id
            mandatory = dict(execution_restriction=self.execution_restriction,
                             validity_restriction=self.validity_restriction,
                             quantity=self.quantity,
                             price=self.price,
                             state=self.state or COMMON.OrderState.acti,
                             direction=self.direction,
                             broker_id=self.broker_id,
                             txt=ALU.serialize_order_tags(self.tags),
                             inst_specifier=[inst_specifier])
            optional = dict(visible_quantity=self.visible_quantity,
                            derivative_indicator=self.derivative_indicator,
                            decision_maker=self.decision_maker,
                            execution_maker=self.execution_maker,
                            liquidity_provision=self.liquidity_provision,
                            dea=self.dea,
                            trading_account=self.trading_account,
                            dea_client_id=self.dea_client_id,
                            trading_capacity=self.trading_capacity,
                            terms=self.terms)
            return autotrader_core.utils.make_element_params(mandatory, optional)

    def _get_order_modify_params(self):
        if self.exchange == COMMON.Exchange.epex:
            mandatory = dict(revision=self.revision,
                             type=self.order_type,
                             quantity=self.quantity,
                             price=self.price,
                             product_id=self.product.product_id,
                             side=self.direction,
                             delivery_area_id=self.delivery_area_id,
                             order_id=self.order_id)
            if self.order_type == COMMON.OrderType.iceberg:
                mandatory.update(dict(clip_quantity=self.clip_quantity))
            optional = dict(txt=ALU.serialize_order_tags(self.tags),
                            execution_restriction=self.execution_restriction,
                            validity_restriction=self.validity_restriction)
            return autotrader_core.utils.make_element_params(mandatory, optional)
        elif self.exchange == COMMON.Exchange.nordpool:
            tags = copy.deepcopy(self.tags)
            mandatory = dict(client_order_id=self.client_order_id,
                             exchange_portfolio_id=self.exchange_portfolio_id,
                             revision=self.revision,
                             type=self.order_type,
                             product_id=self.product.product_id,
                             quantity=self.quantity,
                             price=self.price,
                             txt=ALU.serialize_order_tags(tags),
                             validity_restriction=self.validity_restriction,
                             execution_restriction=self.execution_restriction,
                             order_id=self.order_id)
            if mandatory["validity_restriction"] == "GTD":
                mandatory.update(validity_date=self.validity_date)
                optional = {}
            else:
                optional = dict(validity_date=self.validity_date)
            if self.order_type == COMMON.OrderType.iceberg:
                mandatory.update(dict(clip_quantity=self.clip_quantity,
                                      clip_price_change=self.clip_price_change))
            return autotrader_core.utils.make_element_params(mandatory, optional)
        elif self.exchange == COMMON.Exchange.trayport:
            inst_specifier = self.product.market_meta_information.copy()
            inst_specifier["instrument_id"] = self.delivery_area_id
            mandatory = dict(execution_restriction=self.execution_restriction,
                             validity_restriction=self.validity_restriction,
                             quantity=self.quantity,
                             price=self.price,
                             state=self.state or COMMON.OrderState.acti,
                             engine_id=self.engine_id,
                             order_id=self.order_id,
                             broker_id=self.broker_id,
                             direction=self.direction,
                             txt=ALU.serialize_order_tags(self.tags),
                             inst_specifier=[inst_specifier])
            optional = dict(visible_quantity=self.visible_quantity,
                            derivative_indicator=self.derivative_indicator,
                            decision_maker=self.decision_maker,
                            execution_maker=self.execution_maker,
                            liquidity_provision=self.liquidity_provision,
                            dea=self.dea,
                            dea_client_id=self.dea_client_id,
                            trading_account=self.trading_account,
                            trading_capacity=self.trading_capacity,
                            terms=self.terms,
                            )
            return autotrader_core.utils.make_element_params(mandatory, optional)

    def update_inplace(self, **kwargs):
        has_changed = super(OwnOrder, self).update_inplace(**kwargs)
        # When an exchange replies with UDEL/UADD, the internal market price is reset to the price.
        # We need the same behavior in case of MOD.
        if "price" in kwargs:
            self._internal_market_price = self.price
        if "portfolio_key" in self.tags:
            self.portfolio_key = self.tags["portfolio_key"]
        if "internal_id" in self.tags:
            self._internal_id = self.tags["internal_id"]

        return has_changed

    def serialize(self):
        result = dict(self.__dict__)
        result["product_id"] = self.product.product_id
        result.pop("product", None)
        result.pop("original_order", None)
        return result

    @classmethod
    def deserialize(cls, exchange, source_dict):
        order = super(OwnOrder, cls).__new__(cls)
        order.__dict__.update(source_dict)
        order.product = exchange.products.get_by_id(getattr(order, "product_id"))
        order.regulatory_data = OrderRegulatoryData(order.regulatory_data)
        delattr(order, "product_id")
        return order

    @property
    def shortstr(self):
        return "OwnOrder {} ({} {}@{}, {} strategy: {})".format(self.internal_id, self.direction, self.quantity,
                                                                self.price, getattr(self, "order_id", None),
                                                                self.portfolio_key)


class ComTraderOrder(OwnOrder):
    """Defines ComTrader order, i.e. an order created at the exchange by user

    The execution mode for these orders can be specified by user at the text field
    in the ComTrader as `{"execmode": 1}`.

    If the internal market hibernates and then activates the order,
    the "execmode" and the originating "user" will be visible in the text field.
    """

    def __init__(self, *args, **kwargs):
        super(ComTraderOrder, self).__init__(*args, **kwargs)
        self.tags["user"] = self.original_user
        self._price_ind = 0 if self.direction == COMMON.Direction.buy else 1

    @property
    def internal_market_price(self):
        # Do not update price, if order was hibernated by autotrader
        if self.reactivate and self._internal_market_price:
            return self._internal_market_price
        price_delta = self.product.com_price_deltas[self.delivery_area_id][self._price_ind]
        # Here we imply a positive price shift for buy orders and
        # negative one for sell orders.
        sign = 1 - 2 * self._price_ind
        rounding = 3 if self.exchange == COMMON.Exchange.trayport else 2
        self._internal_market_price = round(self.price + sign * abs(price_delta), rounding)
        return self._internal_market_price

    def update(self, **kwargs):
        super(ComTraderOrder, self).update(**kwargs)
        if self.tags:
            self._set_execmode()
        if "original_user" in list(kwargs.keys()):
            self.tags["user"] = self.original_user
        return self

    def update_inplace(self, **kwargs):
        has_changed = super(ComTraderOrder, self).update_inplace(**kwargs)
        if self.tags:
            self._set_execmode()
        if "original_user" in list(kwargs.keys()):
            self.tags["user"] = self.original_user
        return has_changed

    @property
    def shortstr(self):
        return "ManualOrder {} ({} {}@{}, {})".format(self.internal_id, self.direction, self.quantity, self.price,
                                                      getattr(self, "order_id", None))


class PublicOrder(Order):
    """Defines a public order, inherits from Order and adds some fields to it.

    Attributes:

        **order_id** (str): The exchange's order id

        **execution_restriction** (str): execution restriction of the public order (AON or NON)
    """

    def __init__(self, order_id, execution_restriction, *args, **kwargs):
        super(PublicOrder, self).__init__(*args, **kwargs)
        self.order_id = order_id
        self.execution_restriction = execution_restriction
        self._last_exchange_confirmed_quantity = 0  # Used for combined brokers like EEX and ICE

    @classmethod
    def from_data_line(cls, line, product, exchange_id):
        """
        Factory function to create PublicOrder from a line in an "order_book"-message's data entry

        :param line: An item from the message's "data" field.
        :type line: dict
        :param product: The product the Order was made for
        :type product: Product
        :param exchange_id: The exchange where the order was placed.
        :type exchange_id: str
        :return: The newly created order
        :rtype: PublicOrder
        """
        new_order = cls(line["order_id"],
                        line.get("execution_restriction", COMMON.ExecutionRestriction.non),
                        line["direction"],
                        product,
                        line["delivery_area_id"],
                        line["quantity"],
                        line["price"],
                        exchange_id,
                        engine_id=line.get("engine_id"),
                        system_rank=line.get("system_rank"),
                        is_tradable=line.get("is_tradable", True),
                        implied=line.get("implied", False),
                        counter_party_ok=line.get("counter_party_ok", True),
                        broker_id=line.get("broker_id"),
                        route_id=line.get("route_id"),
                        )
        new_order.update(revision=line["revision"])
        return new_order

    def update_db(self, timestamp):
        if hasattr(self, "order_id"):
            PERSIST.MongoDBConnector().update_db_public_orders(self, timestamp)


class OrderBookIndicators(list):
    """Container for the indicators of the last 5 minutes

    The first element contains the most current :class:`OrderBookIndicator` object,
    that means the newest statistic from the last exchange event. The second element
    contains the indicator built in the last 0-10 seconds, the next one build in the last
    10-20 seconds and so on. The distance between the build timestamps of every element
    with an index > 0 is always 10 seconds. The list has a maximum length of 30 elements.
    """

    def __init__(self):
        self.tainted = {COMMON.Direction.sell: True, COMMON.Direction.buy: True}
        self.indicator_history_timestep = INDICATOR_HISTORY_TIMESTEP
        self.front_buffer_len = 5

        self.last_front_buy_orders = collections.deque(
            [set() for _ in range(self.front_buffer_len)],
            maxlen=self.front_buffer_len)  # type: collections.deque[set[PublicOrder]]
        self.last_front_sell_orders = collections.deque(
            [set() for _ in range(self.front_buffer_len)],
            maxlen=self.front_buffer_len)  # type: collections.deque[set[PublicOrder]]
        self.last_front_buy_orders_by_broker_id = collections.defaultdict(
            lambda: collections.deque([set() for _ in range(self.front_buffer_len)], maxlen=self.front_buffer_len))
        self.last_front_sell_orders_by_broker_id = collections.defaultdict(
            lambda: collections.deque([set() for _ in range(self.front_buffer_len)], maxlen=self.front_buffer_len))

    def taint(self, direction):
        self.tainted[direction] = True

    @staticmethod
    def _populate_last_front_deque(deque_buffer, orders):
        """Add new order set to deque buffer, if the price of the order set has changed to the last known front price.

        :type deque_buffer: collections.deque
        :type orders: set
        """
        # if there are no entries in the buffer, it means there is no current best order
        if not deque_buffer[-1]:
            # if the the latest order set is not empty and the buffer is currently empty, just push the latest order set
            if orders:
                deque_buffer.append(orders)
        else:
            if not orders:
                # if there is no order currently in the market, but the buffer has a history,
                # then set an empty set as current best front orders
                deque_buffer.append(set())
            else:
                best_current_front_price = tuple(orders)[0].price
                last_history_front_price = tuple(deque_buffer[-1])[0].price
                if last_history_front_price == best_current_front_price:
                    # if the price of the current orders is the same as the latest front prices in the buffer,
                    # then add the best current orders to the buffer
                    deque_buffer[-1] = deque_buffer[-1].union(orders)
                else:
                    # if the current order is different, then create a new current entry
                    deque_buffer.append(orders)

    def update(self, orders, timestamp):
        if self:
            ancestor = self[0]
        else:
            ancestor = None

        # prepare containers for current known orders on sell and buy side
        buy_orders = []
        sell_orders = []
        buy_orders_by_broker_id = collections.defaultdict(list)
        sell_orders_by_broker_id = collections.defaultdict(list)

        # loop through the tradable orders to separate the buys/sells, and group additionally by Broker ID
        for order in orders:
            # skip all orders which are not public, not active or not tradable
            if not(isinstance(order, PublicOrder) and order.quantity > 0 and order.is_tradable):
                continue
            if order.direction == COMMON.Direction.buy:
                buy_orders.append(order)
                if order.broker_id:
                    buy_orders_by_broker_id[order.broker_id].append(order)
            elif order.direction == COMMON.Direction.sell:
                sell_orders.append(order)
                if order.broker_id:
                    sell_orders_by_broker_id[order.broker_id].append(order)

        # calculate best buys to add to tracking
        if buy_orders:
            buy_front = max(buy_orders, key=lambda o: o.price)
            best_front_orders = set([o for o in buy_orders if o.price == buy_front.price])
            self._populate_last_front_deque(self.last_front_buy_orders, best_front_orders)
            # check all brokers which are available now or were available in the past
            for broker_id in set(
                list(self.last_front_buy_orders_by_broker_id.keys())
                + list(buy_orders_by_broker_id.keys())
            ):
                if broker_id in buy_orders_by_broker_id:
                    broker_front_order = max(buy_orders_by_broker_id[broker_id], key=lambda o: o.price)
                    broker_front_orders = set(
                        [o for o in buy_orders_by_broker_id[broker_id] if o.price == broker_front_order.price])
                    self._populate_last_front_deque(self.last_front_buy_orders_by_broker_id[broker_id],
                                                    broker_front_orders)
                else:
                    self._populate_last_front_deque(self.last_front_buy_orders_by_broker_id[broker_id], set())
        else:
            # if no orders available, check if last value should be updated to None
            self._populate_last_front_deque(self.last_front_buy_orders, set())
            for broker_id in self.last_front_buy_orders_by_broker_id.keys():
                self._populate_last_front_deque(self.last_front_buy_orders_by_broker_id[broker_id], set())

        # calculate best sells to add to tracking
        if sell_orders:
            sell_front = min(sell_orders, key=lambda o: o.price)
            best_front_orders = set([o for o in sell_orders if o.price == sell_front.price])
            self._populate_last_front_deque(self.last_front_sell_orders, best_front_orders)
            # check all brokers which are available now or were available in the past
            for broker_id in set(
                list(self.last_front_sell_orders_by_broker_id.keys())
                + list(sell_orders_by_broker_id.keys())
            ):
                if broker_id in sell_orders_by_broker_id:
                    broker_front_order = min(sell_orders_by_broker_id[broker_id], key=lambda o: o.price)
                    broker_front_orders = set(
                        [o for o in sell_orders_by_broker_id[broker_id] if o.price == broker_front_order.price])
                    self._populate_last_front_deque(self.last_front_sell_orders_by_broker_id[broker_id],
                                                    broker_front_orders)
                else:
                    self._populate_last_front_deque(self.last_front_sell_orders_by_broker_id[broker_id], set())
        else:
            # if no orders available, check if last value should be updated to None
            self._populate_last_front_deque(self.last_front_sell_orders, set())
            for broker_id in self.last_front_sell_orders_by_broker_id.keys():
                self._populate_last_front_deque(self.last_front_sell_orders_by_broker_id[broker_id], set())

        new = OrderBookIndicator(orders, timestamp, ancestor, self.tainted)

        # If the new message is not newer than the ancestor,
        # then do not create a new entry, but replace the previous one.
        if ancestor and ancestor.timestamp >= new.timestamp:
            # Reduce the risk of putting (transient) incorrect states into the indicator

            # Context: On Epex and Nordpool, own orders are included in the public order messages as well, and
            # in the update_from_json we remove the corresponding (wrong) entry from the public order book,
            # as soon as an own order with the same id arrives.

            # Situation:
            # own order is first returned as a public order, before order execution.
            # this order will be inserted into the indicators as well.
            #
            # The indicators get corrected when we receive the order execution,
            # which removes the own order from the public orderbook and the indicator
            #
            # The issue is with the history of the indicators
            #
            # indicators have a self correcting mechanism, because values are coninuously discarded for 10 seconds.
            # only if 10 seconds passed, a snapshot will be kept, and then again for 10 seconds the next one will be
            # discarded
            #
            # However there is a risk, that the wrong indicator will be used as history snapshot and then will
            # be "remembered".
            #
            # The issue is that an indicator does not remember what order ids were responsible for its creation.
            # so it cannot invalidate the snapshot if it turns out that it has been built based on an order ids
            # which actually was not belonging to a public order, but an own order.
            # By checking the timestamp, we further reduce the (already small) risk of persisting wrong historic data.
            self[0] = new
        else:
            self.insert(0, new)
        if len(self) > 2 and (self[1].timestamp - self[2].timestamp) < (self.indicator_history_timestep - 0.1):
            self.pop(1)
        if len(self) > 30:
            self.pop()
        self.tainted = {COMMON.Direction.sell: False, COMMON.Direction.buy: False}

    @staticmethod
    def _clean_front_buffer(front_buffer, order):
        for index in range(len(front_buffer)):
            if order in front_buffer[index]:
                if index < len(front_buffer) - 1:
                    front_buffer[index].remove(order)
                else:
                    front_buffer.pop()
                    front_buffer.appendleft(set())  # append to keep the length of the history buffer
                break

    @staticmethod
    def _clean_front_buffer_by_broker_id(front_buffer_by_broker_id, broker_id, order):
        if broker_id in front_buffer_by_broker_id:
            front_buffer = front_buffer_by_broker_id[broker_id]
            OrderBookIndicators._clean_front_buffer(front_buffer, order)

    def clean_invalid_public_order(self, order):
        """Remove the last order which was own and not public from the public history and replace it with None

        Need to keep all best orders with same price. If we only kept 1 order, we could get the wrong history value
        in case the memorized order turns out to be an own order. If we don't memorize the other best order, the front
        price can be None, which is wrong.

        Example Situation:

        Public Orders:
        ID: 1, Price 10
        ID: 2, Price 10

        => Buffer: [None, None, None, None, 10]

        Own Order:
        ID: 2, Price 10

        => Buffer: [None, None, None, None, None]
        Reality:
        => Buffer: [None, None, None, None, 10]

        This is why we need sets for each history entry

        :type order: PublicOrder
        :rtype: None
        """

        OrderBookIndicators._clean_front_buffer(self.last_front_buy_orders, order)
        OrderBookIndicators._clean_front_buffer(self.last_front_sell_orders, order)

        broker_id = order.broker_id
        OrderBookIndicators._clean_front_buffer_by_broker_id(self.last_front_buy_orders_by_broker_id, broker_id, order)
        OrderBookIndicators._clean_front_buffer_by_broker_id(self.last_front_sell_orders_by_broker_id, broker_id, order)


class OrderBookIndicatorsParent(list):
    """class to avoid any orderbook update on autotrader parent, since these values are only used in children
    processes."""
    def __init__(self):
        pass

    def taint(self, direction):
        pass

    def update(self, orders, timestamp):
        pass

    def clean_invalid_public_order(self, order):
        pass


class OrderBookIndicator(object):
    """Holds an order book statistic for a certain point in time.

    Attributes:
        **mw_prices** (list): Two element list of a list for the buy [0] and the sell [1] side
            listing the prices for the first x*5 MW in the orders. Every list has 20 elements,
            so this attribute covers the prices for the first 100 MW.

        **eur_quantities** (list): Two element list of a list for the buy [0] and the sell [1] side
            listing the volumes for the first x Euros in the orders. Every list has 20 elements,
            so this sttribute covers the quantities in the first 20 Euros, starting from best offer.

    .. code-block:: python

        # Maximum price to be paid, if we'd buy 10 MW
        mw_prices[0][2]
        # Maximum price to be paid, if we'd buy 15 MW
        mw_prices[0][3]
        # Maximum price to be paid, if we'd sell 0 MW, this is the current best sell offer price
        mw_prices[1][0]
        # Quantity, we could buy, if we do not accept a price worse that best offer + 2 Euro
        eur_quantities[0][1]
        # Quantity, we could sell, if we do not accept a price worse that best offer + 4 Euro
        eur_quantities[1][3]
    """
    quantity_steps = 5
    price_steps = 1.

    def __init__(self, orders, timestamp, ancestor, direction_flags):
        assert timestamp is not None
        # 0/5/10/20/50 MW price for sell and buy
        # 0/5/10/20/50 bid/ask spread, can be calculated from above
        # 0/1/2/3/4/5 EUR quantity for sell and buy
        self.timestamp = timestamp
        if ancestor:
            self.mw_prices = [ancestor.mw_prices[0], ancestor.mw_prices[1]]
            self.eur_quantities = [ancestor.eur_quantities[0], ancestor.eur_quantities[1]]
        else:
            self.mw_prices = [[None] * 20, [None] * 20]  # 5 MW steps
            self.eur_quantities = [[0.] * 20, [0.] * 20]  # 1 EUR steps

        def calculate(orders, price_list, quantity_list):
            if not orders:
                return
            start_price = None
            aggregated_quantity = 0.
            for order in orders:
                if start_price is None:
                    start_price = order.price
                    price_list[0] = order.price
                price_slot = int(abs(order.price - start_price) // self.price_steps)
                if price_slot < 20:
                    quantity_list[price_slot] += order.quantity
                slot_before = int(aggregated_quantity // self.quantity_steps)
                aggregated_quantity += order.quantity
                slot_after = int(aggregated_quantity // self.quantity_steps)
                for cnt in range((slot_after - slot_before)):
                    idx = slot_before + cnt + 1
                    if idx < 20:
                        price_list[idx] = order.price
        if direction_flags[COMMON.Direction.sell] or not ancestor:
            sell_orders = [o for o in orders
                           if o.direction == COMMON.Direction.sell and isinstance(o, PublicOrder) and o.is_tradable]
            sell_orders.sort(key=lambda o: o.price)
            self.eur_quantities[1] = [0.] * 20
            self.mw_prices[1] = [None] * 20
            calculate(sell_orders, self.mw_prices[1], self.eur_quantities[1])
        if direction_flags[COMMON.Direction.buy] or not ancestor:
            buy_orders = [o for o in orders
                          if o.direction == COMMON.Direction.buy and isinstance(o, PublicOrder) and o.is_tradable]
            buy_orders.sort(key=lambda o: -o.price)
            self.eur_quantities[0] = [0.] * 20
            self.mw_prices[0] = [None] * 20
            calculate(buy_orders, self.mw_prices[0], self.eur_quantities[0])

    def __repr__(self):
        result = ["#" * 146]
        result.append(
            "    " + "".join("   {:2d}  ".format(x) for x in range(0, self.quantity_steps * 20, self.quantity_steps))
        )
        result.append("sell" + "".join(["    -  " if x is None else "{:>7.2f}".format(x) for x in self.mw_prices[1]]))
        result.append("buy " + "".join(["    -  " if x is None else "{:>7.2f}".format(x) for x in self.mw_prices[0]]))
        return "\n".join(result)


class _CombinedOrderBrokerBookkeeper(object):
    """
    Class for handling edge cases for combined order brokers (EEX, ICE)

    On EEX and ICE, all orders at the same price are combined into a single public order. Own orders are included
    in these combined public orders, but also sent separately (like how epex sends own orders twice, as own
    and as public order with the same id). The OrderBook's update from json removes the own order's quantity from
    the public orders, so we have a consistent orderbook that works the same on all exchanges.
    However, because the messages can come in random order (i.e. the order execution or the order_book can arrive
    first), and because at least for manual own orders we cannot always know if a public order book message was
    triggered by an own order update or not, we need to store additional information to ensure we always have the
    correct state:

    * The _exchange_confirmed_quantity of public orders is stored directly on the PublicOrder object, and it stores
    the quantity the order had before we removed the own orders. This is important, so we can re-evaluate the
    order's quantity at any time just from the current state in the OrderBook. It is stored directly on the
    PublicOrder and not inside this bookkeeper class.
    * self._public_orders_removed_by_combined_own: Storing the original quantity on the PublicOrder only works if
    the public order exists, i.e. is not deleted. However, when all public quantity seems to come from the own
    orders, then the public order is removed and we have to store the original quantity somewhere else. For this
    purpose we store the whole dictionary, i.e. the translated message from the exchange, in a buffer inside
    this class. We store one line per delivery_area, broker_id and price level. As we only deal with
    auto-matching exchanges, the direction is not used to identify the order.

    In addition to storing the public orders that were removed buy own orders, this bookkeeping class has a second
    purpose: To store the order_ids, for which we should re-evaluate the public order quantity.
    As stated previously, we can at any time re-calculate the actual public quantity from the order book data we have
    (own orders and the public order's exchange confirmed quantity. To avoid flickering (i.e. situation where a public
    order's quantity increases and immediately afterwards decreases again), we sometimes want to delay an update of
    a public order. We use the timer_fast event for this and delay the update to the next timer fast.
    This class stores the order_ids for which we have delayed the quantity update, such that we can re-evaluate the
    quantity
    """
    def __init__(self):
        # Needed by combined order brokers (EEX, ICE). In rare scenarios, we wrongly discard a public order message
        # because we think it is an own order. These messages are buffered here in case we need to restore the order.
        # A maxlen here is important for performance (we iterate over the deque) and memory usage (there is no better
        # way to remove objects from this deque and prevent indefinite growth)
        self._public_orders_removed_by_combined_own = collections.deque(maxlen=COMBINED_ORDER_BROKER_BUFFER_LENGTH)

        # Quantities to reevaluate:
        # The purpose of this is to avoid too aggressive placement by autoTRADER. Between the (own) order execution
        # message and the corresponding public order message, we cannot always show the correct state. The logic
        # implemented here is based on the assumption that in edge cases it is better to see a public order's
        # increased quantity too late than to see a wrong increase in quantity which does not actually happen on
        # the exchange.
        self.quantities_to_reevaluate = []

    def remove_from_public_order_buffer(self, order_id, delivery_area_id, broker_id):
        """
        Remove a public order from the deleted order buffer.

        This is triggered, whenever a public order update is received, so outdated buffered data is removed..
        :param order_id: The order_id of the order for which the buffered entry should be removed
        :type order_id: str
        :param delivery_area_id: The delivery area. See :class:`COMMON.Area`
        :type delivery_area_id: str
        :type broker_id: str
        """
        for buffered_line in self._public_orders_removed_by_combined_own:
            if (buffered_line["order_id"] == order_id
                    and buffered_line["delivery_area_id"] == delivery_area_id
                    and buffered_line["broker_id"] == broker_id):
                log.debug("Removing public order %s from buffer (area %s, broker %s), as the message became outdated",
                          order_id, delivery_area_id, broker_id)
                self._public_orders_removed_by_combined_own.remove(buffered_line)
                break

    def buffer_public_order_msg(self, record):
        """
        Buffer a public order message, which is not stored in the orderbook (because its qty is covered by own orders)

        :param record: A translated dictionary, one entry of a message's "data" list
        :type record: dict
        """
        log.debug("Public order %s (area %s, broker %s) is probably entirely an own order. "
                  "Buffering it in case it is not.", record["order_id"], record["delivery_area_id"],
                  record["broker_id"])
        self._public_orders_removed_by_combined_own.append(copy.copy(record))

    def get_order_to_resurrect(self, price, delivery_area_id, broker_id, direction):
        """
        Check if an order in the buffer has to be added into the orderbook and return it
        :param price: The price at which we have to look for a public order
        :type price: float
        :param delivery_area_id: :class:`COMMON.Area`
        :type delivery_area_id: str
        :type broker_id: str
        :param direction: :class:`COMMON.Direction`
        :type direction: str
        :return: The message that can be used to restore the order
        :rtype: dict or None
        """
        for buffered_line in self._public_orders_removed_by_combined_own:
            if (ALU.is_close(buffered_line["price"], price)
                    and buffered_line["delivery_area_id"] == delivery_area_id
                    and buffered_line["broker_id"] == broker_id):
                self._public_orders_removed_by_combined_own.remove(buffered_line)
                if buffered_line["direction"] == direction:
                    log.debug("Found buffered deleted public order matching price %s: %s area=%s broker=%s. "
                              "Preparing replay of the message into the orderbook.", price, buffered_line["order_id"],
                              buffered_line["delivery_area_id"], buffered_line["broker_id"])
                    return buffered_line
                else:
                    # Should not happen as we only support combined order brokers if they have automatching!
                    log.warning("Found buffered deleted public order matching price %s: %s area=%s broker=%s, but the "
                                "direction is different. Deleting it from the buffer!", price,
                                buffered_line["order_id"], buffered_line["delivery_area_id"],
                                buffered_line["broker_id"])
                    return None
        return None

    def schedule_qty_reevaluation(self, order_id, delivery_area_id, broker_id):
        """
        If we want to delay the update of a public order's quantity, we store the order_id here
        :param order_id: The id of the order
        :type order_id: str
        :param delivery_area_id: :class:`COMMON.Area`
        :type delivery_area_id: str
        :type broker_id: str
        """
        log.debug("Due to own order execution, the quantity of the public order %s (broker=%s, area=%s) "
                  "is scheduled for re-evaluation.", order_id, broker_id, delivery_area_id)
        self.quantities_to_reevaluate.append((order_id, delivery_area_id, broker_id))


class OrderBook(object):
    """Holds all private and public orders for a product.
    """

    def __init__(self, indicator_update=False, exchange_initialized=False):
        # the internal key is [delivery_area][order_id, broker_id] where broker_id is None except for Trayport
        # Own/com_trader/public order books collect all own/com_trade/public orders
        self._own_order_book = collections.defaultdict(dict)
        self._public_order_book = collections.defaultdict(dict)
        # set contains tuples of (order_id, broker_id)
        self._com_trader_order_ids = set()
        # the internal key is [product][delivery_area] -> OrderBookIndicators
        if indicator_update:
            self._indicators = collections.defaultdict(OrderBookIndicators)
        else:
            self._indicators = collections.defaultdict(OrderBookIndicatorsParent)
        # needed to keep track of orders which were deleted
        # [area_id: str][order_id: str, broker_id: str] -> [revision: int]
        # Note: Public and Private orders use a different revision format: For OwnOrders, it is the revision of the
        #       order, for public ones, it is the revision of the order book.
        self._deleted_own_orders = collections.defaultdict(dict)
        self._deleted_public_orders = collections.defaultdict(dict)
        self._last_area_revision = collections.defaultdict(int)  # area_id -> int
        # Bookkeeping for combined order brokers, such as eex and ice
        self._eex_bookkeeper = _CombinedOrderBrokerBookkeeper()
        self.is_exchange_initialized = exchange_initialized

    def on_exchange_initialized(self):
        """
        Helper method to set the exchange status to True end delete the order revision number tracking dicts
        """
        self.is_exchange_initialized = True
        self._deleted_public_orders = collections.defaultdict(dict)

    def update_indicators(self, timestamp, force=False):
        for area_id, indicators_object in self._indicators.items():
            if force:
                indicators_object.taint(COMMON.Direction.sell)
                indicators_object.taint(COMMON.Direction.buy)
            indicators_object.update(list(self._public_order_book[area_id].values()), timestamp)

    def _sum_own_qty_at_price(self, price, direction, delivery_area, broker_id):
        """
        Sum the quantity of all own orders at the given price and area.

        This is used for combined order brokers like EEX.
        :type price: float
        :type direction: str
        :type delivery_area: str
        :type broker_id: str
        :rtype: float
        """
        own_orders = self._own_order_book[delivery_area]
        same_price_own_orders = [
            order for order in own_orders.values()
            if (order.broker_id == broker_id
                and order.direction == direction
                and ALU.is_close(order.price, price)
                and order.state == COMMON.OrderState.acti
                and hasattr(order, "order_id"))
        ]
        return sum(o.quantity for o in same_price_own_orders)

    def reevaluate_public_orders_on_timer_fast(self, current_timestamp):
        """
        Re-evaluate the quantity for some combined public orders

        This goes over the public orders marked for re-evaluation by the _eex_bookkeeper
        and re-evaluates their quantity

        :type current_timestamp: float or int
        :return: The changed public orders
        :rtype: list[PublicOrder]
        :meta private:
        """
        changed = []
        to_update = collections.defaultdict(list)
        for order_id, area, broker_id in self._eex_bookkeeper.quantities_to_reevaluate:
            public_order = self.get_public_order_by_order_id(order_id, area, broker_id)
            if public_order:
                new_qty = public_order._last_exchange_confirmed_quantity - self._sum_own_qty_at_price(
                    public_order.price,
                    public_order.direction,
                    area, broker_id)
                if new_qty != public_order.quantity:
                    log.debug("Restoring public order quantity on timer fast: %s, new qty: %s", public_order, new_qty)
                    if new_qty < 0:
                        # Should never happen
                        raise RuntimeError("Could not determine public order quantity properly"
                                           " for combined order broker.")
                    public_order.quantity = new_qty
                    public_order.update_db(current_timestamp)
                    changed.append(public_order)
                    to_update[area].append(public_order.direction)
        self._eex_bookkeeper.quantities_to_reevaluate = []
        for delivery_area_id, directions in to_update.items():
            for direction in directions:
                self._indicators[delivery_area_id].taint(direction)
            self._indicators[delivery_area_id].update(
                list(self._public_order_book[delivery_area_id].values()),
                current_timestamp)
        return changed

    def update_from_json(self, struct, product, current_timestamp, autotrader_user, combined_brokers=None,
                         confirm_lock=None, multimatching_trade_lock_brokers=None):
        """Update Orderbook of product based on new orderbook data in struct

        :type struct: dict
        :type product: :class:`autotrader_core.exchange_trading.Product`
        :type current_timestamp: float
        :type autotrader_user: str
        :type combined_brokers: frozenset[str]
        :type confirm_lock: str
        :type multimatching_trade_lock_brokers: frozenset[str]
        """
        if combined_brokers is None:
            combined_brokers = frozenset()
        if multimatching_trade_lock_brokers is None:
            multimatching_trade_lock_brokers = frozenset()

        if struct["message_type"] == "order_book":
            try:
                return self._update_from_public_order_message(struct, product, current_timestamp, combined_brokers)
            except COMMON.UnexpectedAreaRevisionException as e:
                log.error("Scheduling a restart of exchange: {}".format(e.exchange_id))
                raise COMMON.RestartExchangeException(e.exchange_id, str(e))
        elif struct["message_type"] == "order_execution":
            return self._update_from_own_execution_message(struct, product, current_timestamp, autotrader_user,
                                                           combined_brokers, confirm_lock,
                                                           multimatching_trade_lock_brokers)

    def _update_from_public_order_message(self, struct, product, current_timestamp, combined_brokers):
        """
        Update Orderbook of product based on new (public) orderbook data in struct

        :type struct: dict
        :type product: :class:`autotrader_core.exchange_trading.Product`
        :type current_timestamp: float
        :type combined_brokers: frozenset[str]
        """
        # keep track of order updates, to update all indicators on the latest public orderbook state,
        # and not line by line on the orderbook
        to_update = set()
        changed_orders = []
        affected_delivery_areas = set()

        for line in struct["data"]:
            # flag to handle public orders , who already have an own order corresponding on epex/trayport,
            # and also include EEX and ICE in handling
            removed_public_by_own = False

            # keep track of indicators to update
            indicator_update_key = (line["delivery_area_id"], line["direction"])
            to_update.add(indicator_update_key)

            affected_delivery_areas.add(line["delivery_area_id"])

            current_order = self.get_public_order_by_order_id(line["order_id"],
                                                              line["delivery_area_id"],
                                                              line.get("broker_id"))
            original_quantity = line["quantity"]

            if struct["exchange"] != COMMON.Exchange.trayport and line["revision"] is not None:
                if ((line["revision"] < self._last_area_revision[line["delivery_area_id"]])
                        and self.is_exchange_initialized):
                    raise COMMON.UnexpectedAreaRevisionException(
                        exchange_id=struct["exchange"],
                        delivery_area=line["delivery_area_id"],
                        expected_revision_number=self._last_area_revision[line["delivery_area_id"]],
                        actual_revision_number=line["revision"]
                    )
                self._last_area_revision[line["delivery_area_id"]] = line["revision"]

            if line.get("broker_id") in combined_brokers:
                # if own order already exists, remove the quantity from this update based on the own order quantity
                qty_to_remove = self._sum_own_qty_at_price(line["price"], line["direction"],
                                                           line["delivery_area_id"], line["broker_id"])
                new_qty = line["quantity"] - qty_to_remove

                # If this is buffered, remove the old entry from the buffer, as we have just received a new entry
                self._eex_bookkeeper.remove_from_public_order_buffer(line["order_id"],
                                                                     line["delivery_area_id"],
                                                                     line["broker_id"])
                if (new_qty < 0 or ALU.is_close(new_qty, 0)
                        and qty_to_remove > 0 and not ALU.is_close(qty_to_remove, 0)):
                    # treat the public order now, as if an own order for this public is present
                    # Buffer the line, in case we have to restore the order
                    self._eex_bookkeeper.buffer_public_order_msg(line)
                    line["quantity"] = 0
                    # We have to decrease the revision a tiny bit, such that replaying the buffered message will
                    # not fail due in the "is_order_revision_valid" check.
                    line["revision"] = line["revision"] - 0.000001
                    removed_public_by_own = True
                else:
                    line["quantity"] = new_qty

                # set own_order to None, because we do not want to skip this update,
                # and own order is already taken into account now
                own_order = None
            else:
                # Here we avoid adding own_orders to the public order book.
                own_order = self.get_own_order_by_order_id(line["order_id"],
                                                           delivery_area_id=line["delivery_area_id"],
                                                           broker_id=line.get("broker_id"))

            if own_order and not current_order:
                continue
            elif own_order and current_order:
                self.remove_public_order(current_order, public_is_own_order=True,
                                         current_timestamp=current_timestamp)
                continue
            if line["quantity"] == 0 and current_order:
                # if order is removed completely, then clean it. public_is_own_order is true only,
                # if own order quantities can be added up to the public order quantity on EEX and ICE
                self.remove_public_order(current_order, public_is_own_order=removed_public_by_own,
                                         current_timestamp=current_timestamp)

                # we add the deleted order to changed_orders because
                # we need strategies to react on this information
                changed_orders.append(current_order)

                # store the revision id at which the order was deleted
                if not self.is_exchange_initialized:
                    self._deleted_public_orders[line.get("delivery_area_id")][
                        (line["order_id"], line.get("broker_id"))] = line["revision"]

            elif line["quantity"] == 0:
                to_update.add(indicator_update_key)  # recheck the indicators
                # store the revision id at which the order was deleted
                if not self.is_exchange_initialized:
                    self._deleted_public_orders[line.get("delivery_area_id")][
                        (line["order_id"], line.get("broker_id"))] = line["revision"]
                continue  # except that do nothing for an empty order
            elif current_order:
                updated_order = self._update_public_order(current_order, current_timestamp,
                                                          price=line["price"],
                                                          quantity=line["quantity"],
                                                          system_rank=line.get("system_rank"),
                                                          is_tradable=line.get("is_tradable", True),
                                                          implied=line.get("implied", False),
                                                          counter_party_ok=line.get("counter_party_ok", True),
                                                          broker_id=line.get("broker_id"))
                updated_order._last_exchange_confirmed_quantity = original_quantity
                changed_orders.append(updated_order)
            elif not current_order and self._is_order_revision_valid(line["order_id"],
                                                                     order_revision=line["revision"],
                                                                     is_own_order=False,
                                                                     area_id=line["delivery_area_id"],
                                                                     exchange_id=struct["exchange"]):
                new_order = PublicOrder.from_data_line(line, product, struct["exchange"])
                new_order._last_exchange_confirmed_quantity = original_quantity
                self.add_public_order(new_order, current_timestamp)
                changed_orders.append(new_order)

        for delivery_area_id, direction in to_update:
            self._indicators[delivery_area_id].taint(direction)
            self._indicators[delivery_area_id].update(
                list(self._public_order_book[delivery_area_id].values()),
                struct["timestamp"]
            )

        return changed_orders, affected_delivery_areas, collections.defaultdict(list)

    def _update_from_own_execution_message(self, struct, product, current_timestamp, autotrader_user, combined_brokers,
                                           confirm_lock, multimatching_trade_lock_brokers):
        """
        Update Orderbook of product based on own order execution data in struct

        :type struct: dict
        :type product: :class:`autotrader_core.exchange_trading.Product`
        :type current_timestamp: float
        :type autotrader_user: str
        :type combined_brokers: frozenset[str]
        :type confirm_lock: str
        :type multimatching_trade_lock_brokers: frozenset[str]
        """
        log.debug("EXECUTION %s", struct)
        (changed_orders, affected_delivery_areas, counted_order_actions_per_broker, resurrection_struct,
         to_update) = self._process_order_execution_struct(struct, product, current_timestamp, autotrader_user,
                                                           combined_brokers, confirm_lock,
                                                           multimatching_trade_lock_brokers)

        for delivery_area_id, direction in to_update:
            self._indicators[delivery_area_id].taint(direction)
            self._indicators[delivery_area_id].update(
                list(self._public_order_book[delivery_area_id].values()),
                struct["timestamp"]
            )

        self._update_db(changed_orders, current_timestamp)
        log.debug("changed %r", changed_orders)

        if resurrection_struct["data"]:
            log.debug("Resurrecting buffered public orders: %s", resurrection_struct)
            changed_orders.extend(self.update_from_json(resurrection_struct, product, current_timestamp,
                                                        autotrader_user, combined_brokers)[0])
        return changed_orders, affected_delivery_areas, counted_order_actions_per_broker

    def _process_order_execution_struct(self, struct, product, current_timestamp, autotrader_user, combined_brokers,
                                        confirm_lock, multimatching_trade_lock_brokers):
        """
        Function to process the received order execution struct elements
        :param struct: received order_execution struct
        :type struct: dict
        :type product: autotrader_core.exchange_trading.Product
        :type current_timestamp: float
        :type autotrader_user: str
        :type combined_brokers: frozenset[str]
        :type confirm_lock: str
        :type multimatching_trade_lock_brokers: frozenset[str]
        :rtype: tuple(list(), set(), collections.defaultdict(list), dict, set())
        """
        # On EEX and ICE (combined order brokers), we might have to resurrect a buffered public order book message
        # into the order_book based on this execution message. Prepare an empty struct for this here:
        resurrection_struct = {"message_type": "order_book", "data": [],
                               "timestamp": struct["timestamp"], "exchange": struct["exchange"]}
        affected_delivery_areas = set()
        changed_orders = []
        counted_order_actions_per_broker = collections.defaultdict(list)
        old_price = None
        old_quantity = None
        old_state = None
        old_portfolio_key = None
        to_update = set()
        for line in struct["data"]:
            area = line["delivery_area_id"]
            if line.get("state") == "PENDING":
                log.debug("Received Order Pending Info (No further handling): %s", line)
                continue

            tags = ALU.parse_order_tags(line["txt"])

            affected_delivery_areas.add(area)
            product.own_order_to_tags[(line["order_id"], line.get("broker_id"))] = tags

            # Check if the order belongs to a com trader user or autotrader
            com_trader = False
            order_user = line["user"]
            if (order_user not in [autotrader_user, COMMON.INTERNAL_USER]
                    or (line["initial_order_id"], line.get("broker_id")) in self._com_trader_order_ids):
                com_trader = True

            if com_trader and order_user == autotrader_user:
                order_user = tags.get("user", order_user)

            internal_id = tags.get("internal_id", global_hash_generator.get_uid())
            portfolio_key = tags.get("portfolio_key", None)
            action = line["action"]

            init_order_id = line.get("initial_order_id") if action.endswith(("MOD", "EXE")) else None
            order = self._find_and_delete_orders(line["delivery_area_id"],
                                                 line["order_id"],
                                                 internal_id,
                                                 init_order_id,
                                                 line.get("broker_id"),
                                                 tags.get(COMMON.OrderTagKeys.internal_orders_broker_id))
            debug_order_id = line["order_id"]
            if order:
                old_price = order.price
                old_quantity = order.quantity
                old_state = order.state
                old_portfolio_key = order.portfolio_key
                if isinstance(order, ComTraderOrder):
                    com_trader = True
                changed_order, count_order_action = self._handle_order_execution_with_existing_order(
                    order, action, line, current_timestamp, tags, struct["exchange"], com_trader, order_user,
                    multimatching_trade_lock_brokers)
            else:
                changed_order, count_order_action = self._handle_order_execution_without_existing_order(
                    action, line, current_timestamp, tags, struct["exchange"], com_trader, order_user, product,
                    portfolio_key, multimatching_trade_lock_brokers)
            if changed_order:
                if count_order_action:
                    counted_order_actions_per_broker[changed_order.broker_id].append(current_timestamp)
                original_ts = self._remove_modification_lock(changed_order, action, confirm_lock, current_timestamp,
                                                             internal_id, old_price, old_quantity, old_state,
                                                             old_portfolio_key)
                if original_ts is not None and line["user"] != COMMON.INTERNAL_USER:
                    # Note: This number is only valid, if the strategy was reacting to a message from the exchange
                    #       (e.g. orderbook update). It is invalid (wrongly too high), if the strategy reacted to a
                    #       steering call or an emergency halt message, and also wrong if the strategy reacted to
                    #       a timer or products_queue event (in which case it does not cover a full roundtrip, and
                    #       deviations between the exchange clock and autotrader clock can mess up the result)
                    log.debug("Roundtrip time estimated as %s for order %s (%s), action %s.",
                              current_timestamp - original_ts, getattr(changed_order, "order_id", None),
                              internal_id, action)
                changed_orders.append(changed_order)
            log.debug("Com Trader Order {!r}; order_id {!r}; internal_id {!r}; broker_id {!r}; request {!r}"
                      .format(com_trader, debug_order_id, ALU.parse_order_tags(line["txt"]).get("internal_id"),
                              line.get("broker_id"), action))
            if line.get("broker_id") in combined_brokers:
                prices_to_check = [line["price"]]
                if old_price is not None and not ALU.is_close(old_price, line["price"]):
                    prices_to_check.append(old_price)
                for price in prices_to_check:
                    order_to_resurrect = self._reevaluate_combined_public_orders_on_execution(price, area,
                                                                                              line["broker_id"],
                                                                                              line["direction"],
                                                                                              current_timestamp,
                                                                                              to_update)
                    if order_to_resurrect:
                        resurrection_struct["data"].append(order_to_resurrect)
            else:
                # handling for other exchanges, when public order can be mapped to own by order id
                public_order = self.get_public_order_by_order_id(line["order_id"], area,
                                                                 line.get("broker_id"))
                if public_order is not None:
                    self.remove_public_order(public_order,
                                             public_is_own_order=True,
                                             current_timestamp=current_timestamp)
        return (changed_orders, affected_delivery_areas, counted_order_actions_per_broker, resurrection_struct,
                to_update)

    def _handle_order_execution_with_existing_order(self, order, action, order_record, current_timestamp, tags,
                                                    exchange, com_trader, order_user,
                                                    multimatching_trade_lock_brokers):
        """
        Function to handle one order from the order execution message that has an existing order
        :type order: autotrader_core.exchange_trading.OwnOrder
        :type action: str
        :param action: one action from the order_execution struct
        :type order_record: dict
        :type current_timestamp: float
        :type tags: dict
        :type exchange: str
        :type com_trader: bool
        :type order_user: str
        :type multimatching_trade_lock_brokers: frozenset[str]
        :rtype: tuple(autotrader_core.exchange_trading.OwnOrder, bool, dict)
        """
        count_order_action = False
        changed_order = None
        if action.endswith("DEL"):
            order.quantity = 0.0

            # store the revision id at which the order was deleted
            self._deleted_own_orders[order_record["delivery_area_id"]][
                (order_record["order_id"], order_record.get("broker_id"))] = order_record["revision"]

            self.remove_own_order(order, current_timestamp)
            changed_order = order
        elif ((action.endswith(("ADD", "MOD", "EXE", "HIB"))
               or action == COMMON.OrderAction.state_unknown
               or action == COMMON.OrderAction.order_validation_failed)
              and self._is_order_revision_valid(order_id=order_record["order_id"],
                                                order_revision=order_record["revision"], is_own_order=True,
                                                area_id=order_record["delivery_area_id"],
                                                exchange_id=exchange)):
            # We do not want to lose the existing tags information
            if not tags:
                tags = order.tags
            if action.endswith("ADD") and isinstance(order, ComTraderOrder):
                order.reactivate = None
            does_state_change = order.check_order_change(state=order_record["state"])
            remaining_quantity = (None if action != COMMON.OrderAction.partial_execution
                                  else order.quantity - order_record["quantity"])
            has_order_changed = self._update_own_order_inplace(order, order_record, order_user,
                                                               current_timestamp, tags=tags)
            if action.endswith("EXE"):
                _ = self.handle_execution_action(
                    exchange, order_record, order, com_trader, current_timestamp, action,
                    multimatching_trade_lock_brokers, remaining_quantity=remaining_quantity)
                changed_order = order

            if has_order_changed:
                if (does_state_change and order.state == COMMON.OrderState.hibe
                        # on exchange EPEX, UHIB message
                        # on exchange trayport, MOD message instead of UHIB.
                        or action.endswith("EXE")):
                    # for exchange EPEX, we ignore FEXE and PEXE messages here
                    # for exchange trayport, we ignore the PEXE message. FEXE has no order object.
                    pass
                else:
                    count_order_action = True
                changed_order = order
            order.start_timestamp = current_timestamp
        return changed_order, count_order_action

    def _handle_order_execution_without_existing_order(self, action, order_record, current_timestamp, tags, exchange,
                                                       com_trader, order_user, product, portfolio_key,
                                                       multimatching_trade_lock_brokers):
        """
        Function to handle one order from the order execution message that does not have and existing order
        :type action: str
        :param order_record: one action from the order_execution struct
        :type order_record: dict
        :type current_timestamp: float
        :type tags: dict
        :type exchange: str
        :type com_trader: bool
        :type order_user: str
        :type product: autotrader_core.exchange_trading.Product
        :type portfolio_key: str
        :type multimatching_trade_lock_brokers: frozenset[str]
        :rtype: tuple(autotrader_core.exchange_trading.OwnOrder, bool, dict())
        """
        count_order_action = False
        updated_order = None
        if action.endswith("DEL"):  # We only track it on uninitialized exchanges
            self._deleted_own_orders[order_record["delivery_area_id"]][
                (order_record["order_id"], order_record.get("broker_id"))] = order_record["revision"]
        elif action.endswith(("ADD", "MOD", "EXE", "HIB")):
            revision_valid = self._is_order_revision_valid(
                order_id=order_record["order_id"],
                order_revision=order_record["revision"],
                is_own_order=True,
                area_id=order_record["delivery_area_id"],
                exchange_id=exchange
            )
            if revision_valid:
                order_instance = ComTraderOrder if com_trader else OwnOrder
                updated_order = order_instance.from_data_line(order_record, product, exchange, portfolio_key,
                                                              order_user, tags)
                if com_trader is True and "exchange_portfolio_id" in order_record:
                    # we need this information to be able to hibernate orders done by manual trading
                    updated_order.update(exchange_portfolio_id=order_record["exchange_portfolio_id"])
                if action in (COMMON.OrderAction.added, COMMON.OrderAction.user_added):
                    # on exchange EPEX, we count UADD messages as actions
                    # on exchange trayport, we only count ADD messages as actions,
                    # furthermore we ignore the QRADD messages
                    count_order_action = True
                self.add_own_order(updated_order)
                if action.endswith("EXE"):
                    # This function would return with the order but here we don't need to use it
                    self.handle_execution_action(
                        exchange, order_record, updated_order, False, current_timestamp, action,
                        multimatching_trade_lock_brokers)
                updated_order.start_timestamp = current_timestamp

        return updated_order, count_order_action

    def handle_execution_action(self, exchange, order_record, order, com_trader, current_timestamp, action,
                                multimatching_trade_lock_brokers, remaining_quantity=None):
        """
        For execution actions adds trade lock and modifies orders accordingly if it is a Fully Executed action

        :type action: str
        :param order_record: one action from the order_execution struct
        :type order_record: dict
        :type order: autotrader_core.exchange_trading.OwnOrder
        :type current_timestamp: float
        :type exchange: str
        :type com_trader: bool
        :type multimatching_trade_lock_brokers: frozenset[str]
        :param remaining_quantity: In case of PEXE to store the remaining quantity after the partial execution
        :type remaining_quantity: float
        :rtype: autotrader_core.exchange_trading.OwnOrder
        """
        if order.broker_id in multimatching_trade_lock_brokers:
            self._add_trade_lock(exchange, order_record, order, com_trader, current_timestamp, multimatching=True,
                                 quantity=remaining_quantity if remaining_quantity else order.quantity)
        else:
            self._add_trade_lock(exchange, order_record, order, com_trader, current_timestamp)
        if action == COMMON.OrderAction.full_execution:
            order._fexe = True
            order.end_timestamp = current_timestamp
            order.quantity = 0
            self.remove_own_order(order, current_timestamp)
        if com_trader:
            self._com_trader_order_ids.add((order_record.get("traded_order_id", order.order_id),
                                            order.broker_id))
        return order

    @staticmethod
    def _update_db(changed_orders, current_timestamp):
        """
        Updates the changed orders in MongoDB
        :type changed_orders: list[autotrader_core.exchange_trading.OwnOrder]
        :type current_timestamp: float
        :rtype: None
        """
        modified_products = set()
        for order in changed_orders:
            modified_products.add(order.product)
            order.update_db(current_timestamp)
        for modified_product in modified_products:
            modified_product.update_db(current_timestamp)

    def _remove_modification_lock(self, order, action, confirm_lock, current_timestamp, internal_id_from_txt,
                                  old_price=None, old_quantity=None, old_state=None,
                                  old_portfolio_key=None):
        """
        Removes the modification lock (AKA order lock) from the given order if the confirm_lock can be defined
        :type order: autotrader_core.exchange_trading.OwnOrder
        :type action: str
        :param action: one action from the order_execution struct
        :type confirm_lock: str
        :type current_timestamp: float
        :param internal_id_from_txt: The internal id of the order taken from the text field (not from the data
               stored inside autoTRADER)
        :type internal_id_from_txt: str
        :returns: The timestamp when the lock that we removed was added, or None
        :rtype: float or None
        :"""
        if (isinstance(order, ComTraderOrder) and action.endswith("DEL")
                and order.state == COMMON.OrderState.hibe and order.internal_id != internal_id_from_txt):
            # Special case:
            # If Autotrader hibernates a manual order, EPEX does NOT set the text field (even if autoTRADER sends it).
            # So if the order is firmed by autoTRADER (without being modified beforehand), EPEX sends a UDEL and UADD
            # without text field. This means we have to completely unlock the product on the UDEL (based on the
            # internal_id of the order object), because we cannot find out the internal_id on the UADD from the message.
            confirm_type = confirm_lock or COMMON.InstanceLockState.confirm_all
            log.debug("Received UDEL for manual order without proper autotrader txt field, probably corresponding to "
                      "order reactivation. Confirm_type for removing modification locks for internal_id %s is"
                      " set to %s", order.internal_id, confirm_type)
        # On Trayport, it can happen that a request triggers two responses:
        # 1) On order entry requests, it can be that we first receive an order without text field,
        # which is then updated to get a text field.
        # 2) On order modification requests which also update the textfield, it can be that the text field is updated
        # first and later the price / quantity is updated,
        # 2) or the other way round.
        # In the first scenario, we can't unlock on the first message (as we don't have the internal id).
        # On the second message, the portfolio_key changes, so we unlock there.
        # In the second scenario, the first message does not change price/quantity or state AND does not change
        # the portfolio_key (as this never changes once set).
        # The second message changes price/ qty or state, so we unlock.
        # In the third scenario, it is fine to unlock on the first message, as we do not allow a strategy to change
        # any important info in the text field (i.e. slot_name and portfolio_key are constant)
        elif (order.price == old_price and order.quantity == old_quantity and order.state == old_state
              and order.portfolio_key == old_portfolio_key and action.endswith("MOD")):
            confirm_type = None
        else:
            confirm_type = confirm_lock or self._define_lock_state(action)
        if confirm_type:
            return order.product.order_lock.modify(order.internal_id, confirm_type, current_timestamp)

    @staticmethod
    def _define_lock_state(action):
        """
        Helper function to define the instance lock state for order lock modification
        :type action: str
        :return: None if PEXE or IADD action, "CONF_ALL" if UMOD, UHIB or FEXE else "CONF_ONE"
        :rtype: str
        """
        if action in [COMMON.OrderAction.user_modified, COMMON.OrderAction.user_hibernated,
                      COMMON.OrderAction.full_execution]:
            # remove all locks if we get only a UMOD or UHIB instead of UDEL and UADD
            # Additionally, we have to delete all locks for FEXE, because on EPEX we cannot unlock the product
            # based on error responses, if the order no longer exists in the order book.
            return COMMON.InstanceLockState.confirm_all
        elif action.endswith("EXE") or action == COMMON.OrderAction.iceberg_slice_added:
            return None
        else:
            return COMMON.InstanceLockState.confirm_one

    def _reevaluate_combined_public_orders_on_execution(self, price, delivery_area, broker_id, direction,
                                                        current_timestamp, to_update):
        """
        Special logic for combined order brokers: Re-evaluate public orders after own order executions.

        On combined_order_brokers, the own orders cannot be easily mapped to public due to different order ids
        and combining public orders on the same price. This function checks the public order at the given price
        and re-evaluates its quantity

        :param price: The price at which the own order book has changed
        :type price: float
        :param delivery_area: The area at which the own order book has changed
        :type delivery_area: str
        :param broker_id: The broker for which the own order book has changed
        :type broker_id: str
        :param direction: The direction, at which the own orderbook has changed
        :type direction: str
        :type current_timestamp: float
        :param to_update: A set of indicator keys which must be updated. This collection is modified in-place
        :type to_update: set
        :return: If applicable, a dict describing a public order which must be put into the public order book,
                 otherwise None.
        :rtype: dict or None
        """
        public_orders = self._public_order_book[delivery_area]
        same_price_public_orders = [
            order for order in public_orders.values()
            if (order.broker_id == broker_id
                and order.direction == direction
                and ALU.is_close(order.price, price))
        ]
        if same_price_public_orders:
            # keep track of modifications, to eventually update the orderbook indicators,
            # since a public order might get removed on this own order update
            indicator_update_key = (delivery_area, direction)
            to_update.add(indicator_update_key)

            # we remove the public order.
            # we can take same_price_public_orders[0], because there can only be 1 public order at
            # the same price at the same time
            public_order = same_price_public_orders[0]

            new_pub_quantity = public_order._last_exchange_confirmed_quantity - self._sum_own_qty_at_price(
                public_order.price, public_order.direction, public_order.delivery_area_id, public_order.broker_id,
            )
            if new_pub_quantity > public_order.quantity:
                # If the public order quantity would increase, we delay this update to the next timer fast
                # or the next orderbook update to avoid flickering behavior in case the own update
                # arrives at autoTRADER before the public update.
                self._eex_bookkeeper.schedule_qty_reevaluation(public_order.order_id,
                                                               public_order.delivery_area_id,
                                                               public_order.broker_id)
            else:
                public_order.quantity = new_pub_quantity
                if public_order.quantity > 0 and not ALU.is_close(public_order.quantity, 0):
                    public_order.update_db(current_timestamp)
                else:
                    self.remove_public_order(public_order, True, current_timestamp)
                    # Note: We do not have to add the public order here to
                    #       self._public_orders_removed_by_combined_own for the following reason:
                    #       If the own execution comes after the public order message, then we already
                    #       have the correct state, and if the public message comes after, then it will
                    #       anyway trigger an update
        else:
            # Check if there is a deleted public order in the buffer that we might have to
            # resurrect into the order_book
            order_to_resurrect = self._eex_bookkeeper.get_order_to_resurrect(price,
                                                                             delivery_area,
                                                                             broker_id,
                                                                             direction)
            if order_to_resurrect:
                return order_to_resurrect
        return None

    def is_com_trader_order(self, order_id, broker_id=None):
        return (order_id, broker_id) in self._com_trader_order_ids

    @staticmethod
    def _filter_by_order_filter(orders, order_filter):
        # type: (list[Order], COMMON.OrderFilter) -> list[Order]
        result = []
        if order_filter is None:
            return orders
        properties = COMMON.OrderFilter.properties(order_filter)
        for order in orders:
            if isinstance(order, OwnOrder) and properties["own"]:
                if properties[order.direction]:
                    result.append(order)
            elif isinstance(order, ComTraderOrder) and properties["com"]:
                if properties[order.direction]:
                    result.append(order)
            elif isinstance(order, PublicOrder) and properties["public"]:
                if properties[order.direction]:
                    result.append(order)
        return result

    @staticmethod
    def _get_price_at_min_volume(orders, volume, min_order_size):
        """
        internal helper - gets price of order where cumulative volume greater equal `volume`
        :param orders: a SORTED list of orders
        :type orders: list[Order]
        :param volume: target volume, at which we are looking for the price
        :type volume: float
        :param min_order_size: only consider orders greater than this size
        :type min_order_size: float
        :return: price, cumulated volume
        :rtype: float, float
        """
        cumulative_volume = 0
        for o in orders:
            if o.quantity < min_order_size:
                continue
            cumulative_volume += o.quantity
            if cumulative_volume >= volume:
                return o.price, cumulative_volume
        return None, None

    def get_price_at_min_volume(self, volume, order_filter, min_order_size=0, delivery_area_id=None, broker_id=None,
                                only_tradable=True):
        """Gets the price of the buy order where cumulated volume greater equal `volume`

        :param volume: target volume, at which we are looking for the price
        :type volume: float
        :param order_filter: Specify, which orders should be taken into account for the calculation.
                             member of :class:`COMMON.OrderFilter`
        :type order_filter: string
        :param min_order_size: only consider orders greater than this size
        :type min_order_size: float
        :param delivery_area_id: optional COMMON.Area
        :type delivery_area_id: str or list[str] or tuple[str] or None
        :param broker_id: optional broker id filter value
        :type broker_id: str
        :param only_tradable: if True, we filter out orders where is_tradable == False
        :type only_tradable: bool
        :return: return price and quantity if volume can be reached in the orderbook, otherwise return None,None
        :rtype: float, float
        """
        if COMMON.Direction.buy in order_filter and COMMON.Direction.sell in order_filter:
            raise ValueError("order_filter must not contain 'buy' and 'sell'")
        elif COMMON.Direction.sell in order_filter:
            reverse = False
        elif COMMON.Direction.buy in order_filter:
            reverse = True
        else:
            raise ValueError("Wrong order filter. Order filter must contain either 'buy' or 'sell'")

        if isinstance(delivery_area_id, (list, tuple)):
            delivery_area_ids = delivery_area_id
        else:
            delivery_area_ids = [delivery_area_id]
        orders = []
        for delivery_area in delivery_area_ids:
            orders.extend(self.get(order_filter=order_filter, delivery_area_id=delivery_area,
                                   broker_id=broker_id, only_tradable=only_tradable, only_active=True))
        orders.sort(key=lambda o: o.price, reverse=reverse)
        return self._get_price_at_min_volume(orders, volume, min_order_size)

    def get_public_buy_price_at_min_volume(self, volume, min_order_size=0, delivery_area_id=None, broker_id=None,
                                           only_tradable=True):
        """
        .. deprecated :: V1.100.57

            The function name get_public_buy_price_at_min_volume() is deprecated. Please use
            get_price_at_min_volume() instead with order_filter=COMMON.OrderFilter.public_buyl!
        """
        return self.get_price_at_min_volume(volume, COMMON.OrderFilter.public_buy, min_order_size, delivery_area_id,
                                            broker_id, only_tradable)

    def get_public_sell_price_at_min_volume(self, volume, min_order_size=0, delivery_area_id=None, broker_id=None,
                                            only_tradable=False):
        """
        .. deprecated :: V1.100.57

            The function name get_public_sell_price_at_min_volume() is deprecated. Please use
            get_price_at_min_volume() instead with order_filter=COMMON.OrderFilter.public_sell!
        """
        return self.get_price_at_min_volume(volume, COMMON.OrderFilter.public_sell, min_order_size, delivery_area_id,
                                            broker_id, only_tradable)

    def can_create_trade(self, direction, delivery_area_id, price, quantity, min_quantity=None):
        # type: (str, float, float, str, float|None) -> bool
        """Checks whether a trade can be created by an imaginary order with the specified price, quantity and direction.

        :param direction: direction of the imaginary order, orders of the opposite side will be checked/aggressed;
                          one of COMMON.Direction
        :param delivery_area_id: Delivery area of the order
        :param price: at what price point we are trying to trade (price of the imaginary aggressing order)
        :param quantity: target volume, how much we can trade
        :param min_quantity: minimum volume we have to trade, set to 0 to allow any trades;
                             default None (the entire quantity needs to be traded)
        :return: Whether the imaginary order would create a trade
        """
        min_quantity = quantity if min_quantity is None else min_quantity

        if direction == COMMON.Direction.sell:
            order_filter = COMMON.OrderFilter.buy
            reverse = True
            further = operator.lt
        elif direction == COMMON.Direction.buy:
            order_filter = COMMON.OrderFilter.sell
            reverse = False
            further = operator.gt
        else:
            raise ValueError("Invalid direction '{}': direction must equal either 'buy' or 'sell'".format(direction))

        orders = self.get(delivery_area_id, order_filter, only_tradable=True, only_active=True)
        orders.sort(key=lambda o: o.price, reverse=reverse)
        cumulative_volume = 0
        for o in orders:
            if further(o.price, price):
                break  # the price is too far from the spread
            execution_restriction = getattr(o, "execution_restriction", None)
            if execution_restriction == COMMON.ExecutionRestriction.aon and quantity < cumulative_volume + o.quantity:
                continue  # unable to trade this entire AON order, skip it
            cumulative_volume += o.quantity
            if cumulative_volume >= min_quantity:
                return True  # found enough orders to be able to trade the min_quantity
        return False

    def get(self, delivery_area_id=None, order_filter=None, portfolio_key=None, broker_id=None, only_tradable=False,
            only_active=False):
        """Returns a list of orders based on the filter criteria passed.

        :param delivery_area_id: optional. Delivery area of the order
        :param order_filter: optional. Filter definition
        :param portfolio_key: optional. Portfolio of order.
            This parameter corresponds to the strategy id
        :param broker_id: optional. Broker id of order.
        :param only_tradable: optional. If True, orders are filtered on is_tradable == True.
        :param only_active: if True, orders are filtered on state == "ACTI", otherwise the orders
                            are not filtered by this state. Only affects own and manual orders.
        :type delivery_area_id: str, member of :class:`COMMON.Area`
        :type order_filter: member of :class:`COMMON.OrderFilter`
        :type portfolio_key: str
        :type broker_id: str
        :type only_tradable: bool
        :type only_active: bool
        :return: list of :class:`PublicOrder` or :class:`OwnOrder`
        :rtype: list[Order]

        .. code-block:: python

            # get all public sell trades concluded in german Amprion area
            api.orders.get(delivery_area_id=common.Area.rwe, order_filter=OrderFilter.public_sell)
        """
        def _check_portfolio_key(orders, portfolio_key):
            if portfolio_key is not None:
                orders = [order for order in orders if getattr(order, "portfolio_key", None) == portfolio_key]
            return orders

        def _get_by_delivery_area_id(order_collection, delivery_area_id, portfolio_key):
            if delivery_area_id:
                orders = _check_portfolio_key(list(order_collection[delivery_area_id].values()),
                                              portfolio_key)
            else:
                orders = []
                for delivery_area_id in order_collection:
                    orders.extend(_check_portfolio_key(list(order_collection[delivery_area_id].values()),
                                                       portfolio_key))
            return orders

        def _filter_by_broker_id(orders, broker_id):
            orders = [order for order in orders if getattr(order, "broker_id", None) == broker_id]
            return orders

        def _filter_by_is_tradable(orders):
            return [order for order in orders if getattr(order, "is_tradable", None)]

        def _filter_by_active(orders):
            if only_active:
                return [order for order in orders if order.state == COMMON.OrderState.acti]
            else:
                return orders

        orders = []

        if order_filter is not None:
            properties = COMMON.OrderFilter.properties(order_filter)
            if properties["own"] or properties["com"]:
                orders.extend(_filter_by_active(_get_by_delivery_area_id(self._own_order_book,
                                                                         delivery_area_id, portfolio_key)))
            if properties["public"]:
                orders.extend(_get_by_delivery_area_id(self._public_order_book,
                                                       delivery_area_id, portfolio_key))
        else:
            orders = (
                _filter_by_active(_get_by_delivery_area_id(self._own_order_book, delivery_area_id, portfolio_key))
                + _get_by_delivery_area_id(self._public_order_book, delivery_area_id, portfolio_key)
            )
        if broker_id:
            orders = _filter_by_broker_id(orders, broker_id)
        if only_tradable:
            orders = _filter_by_is_tradable(orders)

        return OrderBook._filter_by_order_filter(orders, order_filter)

    def indicators(self, delivery_area_id):
        """Returns the indicators list for the area given.

        :param delivery_area_id: Delivery area of the indicators collection
        :type delivery_area_id: str, member of :class:`common.Area`

        :return: :class:`OrderBookIndicators`
        :rtype: autotrader_core.exchange_trading.OrderBookIndicators
        """
        return self._indicators[delivery_area_id]

    @staticmethod
    def _get_orders_by_order_id(order_book, order_id, delivery_area_id, broker_id):
        if not order_id:
            return None
        if delivery_area_id:
            if (order_id, broker_id) in order_book[delivery_area_id]:
                return order_book[delivery_area_id][order_id, broker_id]
        else:
            for order_book_per_delivery_area in order_book.values():
                if (order_id, broker_id) in order_book_per_delivery_area:
                    return order_book_per_delivery_area[order_id, broker_id]
        return None

    def get_own_order_by_order_id(self, order_id, delivery_area_id=None, broker_id=None):
        return self._get_orders_by_order_id(self._own_order_book, order_id, delivery_area_id, broker_id)

    def get_public_order_by_order_id(self, order_id, delivery_area_id=None, broker_id=None):
        return self._get_orders_by_order_id(self._public_order_book, order_id, delivery_area_id, broker_id)

    def get_by_order_id(self, order_id, delivery_area_id=None, broker_id=None):
        """
        returns the corresponding order for the searched order_id. For trayport, the broker_id is needed, to
        uniquely identify an order. On other exchanges, broker_id defaults to None, as the order_id is a unique
        identifier on them. The delivery area can be used as an optional parameter to reduce the search time.

        :param order_id: id of an order as string. Unique for orders, except for trayport.
        :type order_id: string
        :param delivery_area_id: delivery area of the order which is searched (used to increase search speed)
        :type delivery_area_id: string
        :param broker_id: needed to uniquely identify an order on trayport, None for other exchanges.
        :type broker_id: string
        :return: returns an OwnOrder or PublicOrder if found, else None
        :rtype: class:`OwnOrder` or class:`PublicOrder`
        """
        order = self.get_own_order_by_order_id(order_id, delivery_area_id, broker_id)
        if order:
            return order
        order = self.get_public_order_by_order_id(order_id, delivery_area_id, broker_id)
        return order

    @staticmethod
    def _get_order_ids(order_book, delivery_area_id, direction):
        def directed_orders(orders_in_del_area, direction):
            return [order_id for order_id, order in orders_in_del_area.items()
                    if order.direction == direction]

        if delivery_area_id:
            if not direction:
                return list(order_book[delivery_area_id].keys())
            else:
                return directed_orders(order_book[delivery_area_id], direction)
        else:
            ids = []
            for order_book_per_delivery_area in order_book.values():
                if not direction:
                    ids.extend(list(order_book_per_delivery_area.keys()))
                else:
                    ids.extend(directed_orders(order_book_per_delivery_area, direction))
            return ids

    def get_own_order_ids(self, delivery_area_id=None, direction=None):
        return self._get_order_ids(self._own_order_book, delivery_area_id, direction)

    def get_public_order_ids(self, delivery_area_id=None, direction=None):
        return self._get_order_ids(self._public_order_book, delivery_area_id, direction)

    def _find_and_delete_orders(self, delivery_area_id, order_id, internal_id, initial_order_id=None, broker_id=None,
                                child_broker_id_of_unconfirmed_order=None):

        # if call was initiated by modification, remove the initial order because a new order will follow
        if initial_order_id != order_id:
            initial_order = self.get_own_order_by_order_id(initial_order_id, delivery_area_id, broker_id)
            if initial_order:
                self.remove_own_order(initial_order, current_timestamp=time.time())
                return initial_order

        # if both were found, current and unsynchronised (internal) order, we will remove the internal
        # because there should never be two orders with the same internal id
        order = self.get_own_order_by_order_id(order_id, delivery_area_id, broker_id)
        internal_order_id = "OWN_{}".format(internal_id)

        # On the parent process, the unconfirmed order is always on the broker with broker_id...
        internal_order = self.get_own_order_by_order_id(internal_order_id, delivery_area_id,
                                                        broker_id)
        if internal_order is None and child_broker_id_of_unconfirmed_order is not None:
            # ...on the child process, it can be on a different broker_id,
            # if we tried to aggress via an IOC order across brokers
            internal_order = self.get_own_order_by_order_id(internal_order_id, delivery_area_id,
                                                            child_broker_id_of_unconfirmed_order)

        if order and internal_order:
            order.execmode = internal_order.execmode
            self.remove_own_order(internal_order, current_timestamp=time.time())
            return order
        elif order and not internal_order:
            return order
        else:
            return internal_order

    def _is_order_revision_valid(self, order_id, order_revision, is_own_order, area_id, exchange_id):
        """ checks if ("ADD", "MOD", "EXE", "HIB") action can be done, or the order already got deleted meanwhile """
        if self.is_exchange_initialized is True and not is_own_order:
            # Only make this check when exchange is not yet initialized
            # That's why we immediately return True here
            return True

        if exchange_id == COMMON.Exchange.trayport:
            # Disable order-revision check on TRAYPORT. The JD API sends the orders in the correct sequence,
            # while the date (which we use as revision) is not guaranteed to be in the correct sequence.
            # Thus, we rely on the JD-API to handle the ordering of messages and consider all revisions as valid.
            return True

        deleted_orders_dict = self._deleted_own_orders if is_own_order else self._deleted_public_orders
        deleted_order_revision = deleted_orders_dict.get(area_id, {}).get((order_id, None))

        if deleted_order_revision is None:
            return True
        elif deleted_order_revision >= order_revision:
            log.warning("Attempted to add order with order_id: %s and revision %s "
                        "while the order was already deleted at revision %s, the order was not added!",
                        order_id, order_revision, deleted_order_revision)
            return False
        else:
            del deleted_orders_dict[area_id][(order_id, None)]
            return True

    def add_own_order(self, order):
        if getattr(order, "order_id", None) is None:
            order_id = "OWN_{}".format(order._internal_id)
        else:
            order_id = order.order_id

        broker_id = order.broker_id
        self._own_order_book[order.delivery_area_id][order_id, broker_id] = order

        if isinstance(order, ComTraderOrder):
            self._com_trader_order_ids.add((order.order_id, broker_id))
            if (order.initial_order_id, broker_id) not in self._com_trader_order_ids:
                # If the order has an initial order-id different from its order_id, it should already be
                # inside the com_trader_order_ids, so this warning should only be triggered in rare cases that warrant
                # an investigation.
                log.warning("Received ComTrader order (order_id=%s) with initial_order_id %s and broker_id %s "
                            "not known to be a ComTrader order.", order.order_id, order.initial_order_id,
                            broker_id)
                self._com_trader_order_ids.add((order.initial_order_id, broker_id))

    def add_public_order(self, order, timestamp):
        self._public_order_book[order.delivery_area_id][order.order_id, order.broker_id] = order
        order.update_db(timestamp)

    def remove_own_order(self, order, current_timestamp=None):
        """ Removed own orders from the `_own_order_book` dictionary

        :param order: own or com trader order to be removed from the
                      `_own_order_book` dictionary
        :type order: class:`OwnOrder`
        :param current_timestamp: current timestamp
        :type current_timestamp: float

        """
        if getattr(order, "order_id", None) is None:
            order_id = "OWN_{}".format(order._internal_id)
        else:
            order_id = order.order_id
            order.end_timestamp = current_timestamp
            # Important: modify makes a copy.
            # We do not want to modify the quantity for anyone still holding a reference to this order.
            order.modify(quantity=0.).update_db(current_timestamp)
        if (order_id, order.broker_id) in self._own_order_book[order.delivery_area_id]:
            del self._own_order_book[order.delivery_area_id][order_id, order.broker_id]

    def remove_public_order(self, order, public_is_own_order=False, current_timestamp=None):
        order.end_timestamp = current_timestamp
        order.quantity = 0.
        order.update_db(current_timestamp)
        del self._public_order_book[order.delivery_area_id][order.order_id, order.broker_id]
        # refresh the indicators on that area for this product, otherwise public order is gone,
        # but indicators still show as if it was part of the public orderbook until the next proper orderbook update
        if public_is_own_order:
            self._indicators[order.delivery_area_id].clean_invalid_public_order(order)
            self._indicators[order.delivery_area_id].taint(order.direction)
            self._indicators[order.delivery_area_id].update(
                list(self._public_order_book[order.delivery_area_id].values()), current_timestamp or time.time()
            )

    def update_public_order(self, order, timestamp, **kwargs):
        return self._update_public_order(order, timestamp, **kwargs)

    def _update_public_order(self, order, timestamp, **kwargs):
        """
        :rtype: PublicOrder
        """
        o = order.update(**kwargs)
        order.update_db(timestamp)
        return o

    def _update_own_order_inplace(self, order, line, order_user, current_timestamp, tags=None):
        kwargs = dict(quantity=line["quantity"],
                      price=line["price"],
                      revision=line["revision"],
                      state=line["state"],
                      execution_restriction=line["execution_restriction"],
                      last_update_user=line["last_update_user"],
                      original_user=order_user,
                      engine_id=line.get("engine_id"),
                      initial_order_id=line.get("initial_order_id"),
                      system_rank=line.get("system_rank"),
                      is_tradable=line.get("is_tradable", True),
                      implied=line.get("implied", False),
                      counter_party_ok=line.get("counter_party_ok", True),
                      broker_id=line.get("broker_id"),
                      order_id=line["order_id"],
                      trading_account=line.get("trading_account", ""),
                      terms=line.get("terms"),
                      route_id=line.get("route_id"),
                      )
        if tags is not None:
            kwargs["tags"] = tags

        if getattr(order, "order_id", None) is None:
            self.remove_own_order(order, current_timestamp)

        has_changed = order.update_inplace(**kwargs)
        # In the data line received from Trayport, regulatory data entries are at the top level,
        # but we like to nest them inside regulatory_data, which is not done in `update_own_order`
        has_changed |= order.regulatory_data.update_from_data_line(line)

        self.add_own_order(order)

        return has_changed

    def remove_ioc_orders_created_before(self, timestamp):
        for delivery_area_id in self._own_order_book:
            for (order_id, broker_id), order in self._own_order_book[delivery_area_id].items():
                if (
                        order.creation_timestamp < timestamp
                        and order.execution_restriction == COMMON.ExecutionRestriction.ioc
                ):
                    log.debug("Removed too old ioc order_id: %s broker_id: %s", order_id, broker_id)
                    del self._own_order_book[delivery_area_id][order_id, broker_id]

    def get_volume(self, delivery_area_id, order_filter, internal_id_filter=None, portfolio_key=None, broker_id=None,
                   only_tradable=False, only_active=False):
        """Returns the overall volume of the orders defined by the filters.

        :param delivery_area_id: Buy or sell delivery area of the trade
        :param order_filter: Filter definition
        :param internal_id_filter: optional, filter for a defined internal order number (only for api internal use)
        :param portfolio_key: optional. Portfolio of order.
            This parameter corresponds to the strategy id
        :param broker_id: optional broker id filter value
        :param only_tradable: if True, we filter out orders where is_tradable == False
        :param only_active: if True, orders are filtered on state == "ACTI", otherwise the orders
                            are not filtered by this state. Only affects own and manual orders.
        :type delivery_area_id: str, member of :class:`common.Area`
        :type order_filter: member of :class:`TradeFilter`
        :type internal_id_filter: str
        :type portfolio_key: str
        :type broker_id: str
        :type only_tradable: bool
        :type only_active: bool

        :return: overall volume as float
        """
        volume = 0
        for order in self.get(delivery_area_id=delivery_area_id, order_filter=order_filter, portfolio_key=portfolio_key,
                              broker_id=broker_id, only_tradable=only_tradable, only_active=only_active):
            if internal_id_filter and order._internal_id == internal_id_filter:
                continue
            volume += order.quantity
        return volume

    def get_public_order_depth(self, direction, delivery_area_id, broker_id=None, only_tradable=False):
        """
        Works similar as get_volume: Returns the aggregated volume of the filtered public orders, and it applies an
        additional mandatory direction filter, by default untradable orders are not filtered.

        .. deprecated :: V1.100.57

            Use get_volume directly instead

        :param direction: Specifies if the result refers to buy or sell public orders
        :param delivery_area_id: Buy or sell delivery area of the public order
        :param broker_id: optional broker id filter value
        :param only_tradable: optional count only volumes of tradable orders
        :type direction: str, member of :class:`COMMON.Direction`
        :type delivery_area_id: str, member of :class:`common.Area`
        :type broker_id: str
        :type only_tradable: bool

        :return: buy/sell volume
        :rtype: float
        """
        if direction == COMMON.Direction.buy:
            return self.get_volume(order_filter=COMMON.OrderFilter.public_buy,
                                   delivery_area_id=delivery_area_id,
                                   broker_id=broker_id,
                                   only_tradable=only_tradable)
        else:
            return self.get_volume(order_filter=COMMON.OrderFilter.public_sell,
                                   delivery_area_id=delivery_area_id,
                                   broker_id=broker_id,
                                   only_tradable=only_tradable)

    def _add_trade_lock(self, exchange, message_data_line, order, is_com_trader, current_ts, quantity=None,
                        multimatching=False):
        """ Adds a trade lock on the specific order's product

        :param exchange: The exchange that sent the order message
        :type exchange: str
        :param message_data_line: The order message line which is processed
        :type message_data_line: dict
        :param order: The specific order object that is included in the order message
        :type order: :class:`OwnOrder`
        :param is_com_trader: A flag showing if the order is manual
        :type is_com_trader: bool
        :param current_ts: the timestamp of the order message
        :type current_ts: float
        :param quantity: Only for EEX. To track the quantity of FEXE/PEXE message and match with own trade quantities
        :type quantity: float
        :param multimatching: A flag to show if the trade lock should be added with multimatching logic or not
        :type multimatching: bool
        """
        if exchange == COMMON.Exchange.trayport:
            lock_id = ALU.parse_order_tags(message_data_line["txt"]).get("internal_id")
        else:
            lock_id = message_data_line.get("traded_order_id", order.order_id)

        # We add a trade_lock on trayport only if the order is not a manual order,
        # always if the exchange is not trayport.
        if exchange != COMMON.Exchange.trayport or not is_com_trader:
            if not lock_id:
                log.warning("Lock id is None: %s", message_data_line)
            if not multimatching or order.product.trade_lock.handle_multimatching_add_lock(lock_id, quantity):
                order.product.trade_lock.add(lock_id, current_ts, quantity=quantity)
        else:
            log.debug("We do not add a trade lock for the manual order: %s (%s)", order, exchange)

    def __repr__(self):
        return str(self.__dict__)


class ExpiredOrderBook(OrderBook):
    """
    After the product's delivery start, we discard the order book (as it is no longer needed) and replace it with this.

    This is a subclass of the OrderBook to ensure that it has the same attributes as the OrderBook, such that
    accidental access to them will not cause a traceback/ crash.
    Instead, it writes a warning to the log on attribute access.

    :meta private:
    """

    def update_indicators(self, timestamp, force=False):
        pass

    def update_from_json(self, struct, product, current_timestamp, autotrader_user, combined_brokers=None,
                         confirm_lock=None, multimatching_trade_lock_brokers=None):
        """
        Handles orderbook update for expired orders
        :type struct: dict
        :type product: Product
        :type current_timestamp: float
        :type autotrader_user: str
        :type combined_brokers: frozenset[str]
        :type confirm_lock: str
        :type multimatching_trade_lock_brokers: frozenset[str]
        :rtype: tuple
        """
        counted_order_actions_per_broker = collections.defaultdict(list)
        log.debug("Ignoring message %s, because the product %s (%s) is already expired!", struct["message_type"],
                  product.product_id, product.name)
        for line in struct.get("data", {}):
            if line.get("quantity", 0) > 0:
                log.warning("Ignoring order %s, because the product is already expired!", line.get("order_id"))
            if (struct["message_type"] == COMMON.Response.order_execution
                    and line["action"] in (COMMON.OrderAction.added, COMMON.OrderAction.user_added)):
                counted_order_actions_per_broker[line.get("broker_id")].append(current_timestamp)
        return [], set(), counted_order_actions_per_broker

    def is_com_trader_order(self, order_id, broker_id=None):
        # We use warning here, because this is mostly autoTRADER internal
        # and this function should usually not be called on an expired order book.
        log.warning("`is_com_trader_order (order_id=%s, broker_id=%s)` was called on an expired orderbook "
                    "(product is already expired). Returning False", order_id, broker_id)
        return False

    def get_price_at_min_volume(self, volume, order_filter, min_order_size=0, delivery_area_id=None, broker_id=None,
                                only_tradable=True):
        # No log here. None, None would also be returned on a normal orderbook if no orders exist
        return None, None

    def get(self, delivery_area_id=None, order_filter=None, portfolio_key=None, broker_id=None, only_tradable=False,
            only_active=False):
        # No log here. [] would also be returned on a normal orderbook if no orders exist
        return []

    def indicators(self, delivery_area_id):
        log.debug("`indicators` was called on an expired orderbook (product is already expired). "
                  " Returning Empty Indicators.")
        return OrderBookIndicators()

    def get_own_order_by_order_id(self, order_id, delivery_area_id=None, broker_id=None):
        # We add a log message here, because whoever called this function probably
        # believed that the order with the given id still exists.
        log.info("`get_own_order_by_order_id(order_id=%s, delivery_area_id=%s, broker_id=%s)` was called on "
                 "an expired orderbook (product is already expired). Returning None.", order_id, delivery_area_id,
                 broker_id)
        return None

    def get_public_order_by_order_id(self, order_id, delivery_area_id=None, broker_id=None):
        # We add a log message here, because whoever called this function probably
        # believed that the order with the given id still exists.
        log.info("`get_public_order_by_order_id(order_id=%s, delivery_area_id=%s, broker_id=%s)` was called on "
                 "an expired orderbook (product is already expired). Returning None.", order_id, delivery_area_id,
                 broker_id)
        return None

    def get_by_order_id(self, order_id, delivery_area_id=None, broker_id=None):
        # We add a log message here, because whoever called this function probably
        # believed that the order with the given id still exists.
        log.info("`get_by_order_id(order_id=%s, delivery_area_id=%s, broker_id=%s)` was called on "
                 "an expired orderbook (product is already expired). Returning None.", order_id, delivery_area_id,
                 broker_id)
        return None

    def get_own_order_ids(self, delivery_area_id=None, direction=None):
        return []

    def get_public_order_ids(self, delivery_area_id=None, direction=None):
        return []

    def add_own_order(self, order):
        # add_own_order is only used within the orderBook and in tests, so raising here is fine.
        assert False, "`add_own_order` should never be called on an expired orderbook"

    def add_public_order(self, order, timestamp):
        # add_public_order is only used within the orderBook and in tests, so raising here is fine.
        assert False, "`add_public_order` should never be called on an expired orderbook"

    def remove_own_order(self, order, current_timestamp=None):
        log.error("Ignoring call `remove_own_order` on an expired orderbook (product is already expired)!")

    def remove_public_order(self, order, public_is_own_order=False, current_timestamp=None):
        log.error("Ignoring call `remove_public_order` on an expired orderbook (product is already expired)!")

    def update_public_order(self, order, timestamp, **kwargs):
        log.error("Ignoring call `update_public_order` on an expired orderbook (product is already expired)!")

    def remove_ioc_orders_created_before(self, timestamp):
        # As this is just a clean-up task, we do not have to log any warning here
        pass

    def get_volume(self, delivery_area_id, order_filter, internal_id_filter=None, portfolio_key=None, broker_id=None,
                   only_tradable=False, only_active=False):
        # The order_guard calls this during normal operation, e.g. call this in the expired orderbook of the hourly
        # product when checking the limits of the (not yet expired) last quarter of the same hour.
        # As this is part of normal operation and returning 0 is the correct behavior, we do not log anything here.
        return 0

    def get_public_order_depth(self, direction, delivery_area_id, broker_id=None, only_tradable=False):
        return 0

    def __repr__(self):
        return "<ExpiredOrderBook {}>".format(super(ExpiredOrderBook, self).__repr__())


class Trade(object):
    """Defines a concluded trade and is the base class for PublicTrade and OwnTrade.

    Attributes:
        **exchange** (str): Exchange where the trade has been concluded, member of :class:`common.Exchange`

        **trade_id** (str): Id of the trade

        **tags** (dict): dict containing custom information from the strategies

        **product** (Product): :class:`Product` object for the trade

        **quantity** (float): The trade's volume in MW

        **price** (float): The trade's price in Euro per MWh

        **execution_time** (int): The trade execution timestamp as unix timestamp

        **sell_delivery_area** (str): Sell area, member of :class:`common.Area`

        **buy_delivery_area** (str): Buy area, member of :class:`common.Area`

        **portfolio_key** (str): Portfolio of trade. This parameter corresponds to the strategy id

        **aggressor_broker_id** (str): ID of the broker of the aggressor. None of no broker was used

        **initiator_broker_id** (str): ID of the broker of the initiator. None of no broker was used

        **annotations** (dict): Optional Trayport annotations for the trade
    """

    def __init__(self, trade_id, revision, state, product, quantity, price, execution_time,
                 sell_delivery_area, buy_delivery_area, exchange, tags=None, aggressor_broker_id=None,
                 initiator_broker_id=None, annotations=None, **kwargs):
        self.exchange = exchange
        self.trade_id = trade_id
        self.revision = revision
        self.state = state
        self.tags = tags or {}
        self.order_internal_id = self.tags.get("internal_id")
        self.product = product
        self.quantity = quantity
        self.price = price
        self.execution_time = execution_time
        self.sell_delivery_area = sell_delivery_area
        self.buy_delivery_area = buy_delivery_area
        self._internal_id = str(uuid.uuid4())
        self.tags["internal_id"] = self._internal_id
        self.aggressor_broker_id = aggressor_broker_id
        self.initiator_broker_id = initiator_broker_id
        if aggressor_broker_id != initiator_broker_id:
            # The reason why these two fields exist in the Joulde direct API is legacy
            # (although it might be used again on different markets in the future)
            log.warning("Found different broker ids for initiator and aggressor."
                        "This should not happen anymore nowadays. "
                        "Trade_id: %s, initiator_broker_id: %s != aggressor_broker_id: %s",
                        trade_id, initiator_broker_id, aggressor_broker_id)
        self.aggressor_trading_account = kwargs.get("aggressor_trading_account", "")
        self.initiator_trading_account = kwargs.get("initiator_trading_account", "")
        self.annotations = annotations
        self.route_id = kwargs.get("route_id")
        self.from_broken_spread = kwargs.get("from_broken_spread", "")
        self.init_sleeve = kwargs.get("init_sleeve", "")
        self.agg_sleeve = kwargs.get("agg_sleeve", "")
        self.voice_deal = kwargs.get("voice_deal", "")

    @property
    def portfolio_key(self):
        return self.tags.get("portfolio_key")

    @classmethod
    def from_data_line(cls, line, product, exchange_id):
        """
        Factory function to create a Trade from a line in a message's data entry.
        Must be implemented in the sub class.

        :param line: An item from the message's "data" field.
        :type line: dict
        :param product: The product that was traded
        :type product: Product
        :param exchange_id: The exchange where the order was placed.
        :type exchange_id: str
        :return: The newly created Trade
        :rtype: Trade
        """
        raise NotImplementedError

    def match_delivery_areas(self, delivery_area_ids):
        combined_zone_ids = set(delivery_area_ids)
        if (combined_zone_ids & set(COMMON.Area.de_zone)
                and self.product.delivery_start - self.execution_time > COMMON.HALF):
            # if the strategy operates in germany and the product is more than 30 minutes
            # away from delivery (zones still joined), match all german trades
            # caution! no append! That would modify delivery_area_ids
            combined_zone_ids.update(COMMON.Area.de_zone)
        return self.sell_delivery_area in combined_zone_ids or self.buy_delivery_area in combined_zone_ids

    def update_inplace(self, **kwargs):
        """
        Updates the Trade in-place and returns whether something (except revision) has changed.

        Note: This is a low-level function that directly modifies self.__dict__,
        without any checking of the keywords.

        :param kwargs: key-value pairs used to update this trade
        :type kwargs: dict
        :return: True if any attribute was added or changed
        :rtype: bool
        """
        changed = False
        tags_changed = False
        if "tags" in kwargs:
            # We do not want to overwrite the internal id, which was set in the __init__ method to a uuid.
            kwargs["tags"]["internal_id"] = self._internal_id
        for key in kwargs:
            if key == "revision":
                continue
            if key not in self.__dict__ or kwargs[key] != self.__dict__[key]:
                if key == "tags" and self.__dict__.get(key, None):
                    tags_changed = True
                else:
                    changed = True
        if not changed and tags_changed and (len(self.tags) >= len(kwargs["tags"])):
            # If the only change is changing the tags, do not update, unless we received additional tags

            log.warning(
                "Only tags (Memo Field) changed in trade (trade_id: {}). "
                "Old tags: {}, New tags: {}. Will not update trade!".format(
                    self.__dict__["trade_id"], self.__dict__["tags"], kwargs["tags"])
            )
        else:
            self.__dict__.update(kwargs)
        return changed or tags_changed

    def __repr__(self):
        template = "<{class_name} {trade_id} {quantity}@{price} sell_delivery_area: {sell_area!r}, " \
                   "buy_delivery_area: {buy_area!r}, broker {broker_id} for Product {product_id}, {product_name}, " \
                   "delivering from {delivery_from}Z until {delivery_until}Z>"
        return template.format(class_name=self.__class__.__name__, trade_id=self.trade_id,
                               quantity=self.quantity, price=self.price, sell_area=self.sell_delivery_area,
                               buy_area=self.buy_delivery_area,
                               broker_id=self.aggressor_broker_id, product_id=self.product.product_id,
                               product_name=self.product.name,
                               delivery_from=ALU.convert_utc_timestamp_to_dt(
                                   self.product.delivery_start).isoformat(),
                               delivery_until=ALU.convert_utc_timestamp_to_dt(
                                   self.product.delivery_end).isoformat())

    def to_dict(self):
        data = copy.deepcopy(self.__dict__)
        data["product_id"] = self.product.product_id
        data["delivery_start"] = self.product.delivery_start
        data["delivery_end"] = self.product.delivery_end
        data["product_type"] = self.product.product_type
        data["trading_portfolio"] = self.portfolio_key
        data["slot_type"] = self.tags.get("strategy_slot")
        data["stats"] = self.tags.get("stats")
        data["internal"] = "internal" in self.trade_id
        return data


class PublicTrade(Trade):
    """Inherits from Trade without changes.
    """

    def __init__(self, *args, **kwargs):
        # we need to remove these from the kwargs because super does not expect them
        if "buy_order_id" in kwargs:
            self.buy_order_id = kwargs["buy_order_id"]
            del kwargs["buy_order_id"]
        if "sell_order_id" in kwargs:
            self.sell_order_id = kwargs["sell_order_id"]
            del kwargs["sell_order_id"]
        super(PublicTrade, self).__init__(*args, **kwargs)

    def update_db(self, timestamp):
        # a recalled trade is essentially cancelled, separate state is kept for root cause transparency
        if self.state == COMMON.TradeState.cancelled or self.state == COMMON.TradeState.recall_granted:
            PERSIST.MongoDBConnector().update_db_trade_on_cancellation(self, timestamp, "PublicTrade")
        else:
            PERSIST.MongoDBConnector().update_db_public_trades(self, timestamp)

    @classmethod
    def from_data_line(cls, line, product, exchange_id):
        """
        Factory function to create PublicTrade from a line in a "public_trade"-message's data entry

        :param line: An item from the message's "data" field.
        :type line: dict
        :param product: The product that was traded
        :type product: Product
        :param exchange_id: The exchange where the order was placed.
        :type exchange_id: str
        :return: The newly created Trade
        :rtype: PublicTrade
        """
        new_trade = cls(line["trade_id"],
                        line["revision"],
                        line["state"],
                        product,
                        line["quantity"],
                        line["price"],
                        line["execution_time"],
                        line["sell_delivery_area"],
                        line["buy_delivery_area"],
                        exchange_id,
                        aggressor_broker_id=line.get("aggressor_broker_id"),
                        initiator_broker_id=line.get("initiator_broker_id"),
                        aggressor_trading_account=line.get("aggressor_trading_account", ""),
                        initiator_trading_account=line.get("initiator_trading_account", ""),
                        route_id=line.get("route_id"),
                        )
        return new_trade


class TradeRegulatoryData(MetaDataDict):
    valid_keys = ["aggressor_foreign_order_id", "initiator_foreign_order_id", "datetime_nanoseconds_part",
                  "last_update_nanoseconds_part", "foreign_trade_id", "aggressor_trading_capacity",
                  "aggressor_decision_maker", "aggressor_execution_maker", "aggressor_derivative_indicator",
                  "aggressor_dea", "aggressor_dea_client_id", "aggressor_liquidity_provision",
                  "initiator_trading_capacity", "initiator_decision_maker", "initiator_execution_maker",
                  "initiator_derivative_indicator", "initiator_dea", "initiator_dea_client_id",
                  "initiator_liquidity_provision", "product_classification"]


class OwnTrade(Trade):
    """Defines an own concluded trade.

    Attributes added to base class:
        **order_id** (str): Links to the order id that the trades bases on

        **user** (str): User that added the order that caused the trade
    """

    def __init__(self,
                 order_id,
                 user,
                 trader_id,
                 trader_name,
                 aggressor,
                 initiator,
                 counterparty,
                 *args, **kwargs):
        super(OwnTrade, self).__init__(*args, **kwargs)

        self.order_id = order_id
        self.user = user
        self.trader_id = trader_id
        self.trader_name = trader_name
        self.aggressor = aggressor
        self.initiator = initiator
        self.counterparty = counterparty
        self.regulatory_data = TradeRegulatoryData()
        self.terms = []
        self._generate_internal_id()

    def _generate_internal_id(self):
        """
        Generates a unique internal id from exchange id, trade id, direction [and broker id on Trayport]
        """
        # the internal ID should be of following format (with [] only for Trayport):
        # <EXCHANGE_ID>-<TRADE_ID>-<DIRECTION>[-<BROKER_ID>]
        # This ensures trades get assigned the same ID no matter if loaded from DB or elsewhere.

        direction_short = "B" if self.direction == COMMON.Direction.buy else "S"

        self._internal_id = "{}-{}-{}".format(self.exchange, self.trade_id, direction_short)
        if self.aggressor_broker_id:
            self._internal_id += "-{}".format(self.aggressor_broker_id)

        self.tags["internal_id"] = self._internal_id

    @classmethod
    def from_data_line(cls, line, product, exchange_id,  # pylint: disable=arguments-differ
                       tags=None):
        """
        Factory function to create an OwnTrade from a line in an "own_trade"-message's data entry

        :param line: An item from the message's "data" field.
        :type line: dict
        :param product: The product that was traded
        :type product: Product
        :param exchange_id: The exchange where the trade took place.
        :type exchange_id: str
        :param tags: Optionally pass the order tags. Otherwise they will be parsed from the line's "txt" field
        :type tags: dict or None
        :return: The newly created Trade
        :rtype: OwnTrade
        """
        if tags is None:
            tags = ALU.parse_order_tags(line["txt"])

        new_trade = cls(line["order_id"],
                        line["user"],
                        line.get("trader_id"),
                        line.get("trader_name"),
                        line.get("aggressor", COMMON.ActorType.unknown),
                        line.get("initiator", COMMON.ActorType.unknown),
                        line.get("counterparty"),
                        line["trade_id"],
                        line["revision"],
                        line["state"],
                        product,
                        line["quantity"],
                        line["price"],
                        line["execution_time"],
                        line["delivery_area"] if line["direction"] == COMMON.Direction.sell else "",
                        line["delivery_area"] if line["direction"] == COMMON.Direction.buy else "",
                        exchange_id,
                        tags=tags,
                        aggressor_broker_id=line.get("aggressor_broker_id"),
                        initiator_broker_id=line.get("initiator_broker_id"),
                        annotations=line.get("annotations"),
                        aggressor_trading_account=line.get("aggressor_trading_account", ""),
                        initiator_trading_account=line.get("initiator_trading_account", ""),
                        route_id=line.get("route_id"),
                        from_broken_spread=line.get("from_broken_spread", ""),
                        init_sleeve=line.get("init_sleeve", ""),
                        agg_sleeve=line.get("agg_sleeve", ""),
                        voice_deal=line.get("voice_deal", "")
                        )
        new_trade.regulatory_data.update_from_data_line(line)
        new_trade.terms = line.get("terms", [])  # terms are trayport specific
        return new_trade

    def update_db(self, timestamp):
        # a recalled trade is essentially cancelled, separate state is kept for root cause transparency
        if self.state == COMMON.TradeState.cancelled or self.state == COMMON.TradeState.recall_granted:
            PERSIST.MongoDBConnector().update_db_trade_on_cancellation(self, timestamp, "OwnTrade")
        else:
            PERSIST.MongoDBConnector().update_db_own_trades(self, timestamp)

    @property
    def direction(self):
        if self.buy_delivery_area != "":
            return COMMON.Direction.buy
        elif self.sell_delivery_area != "":
            return COMMON.Direction.sell


class InternalTrade(OwnTrade):
    def __init__(self, order_id, user, trade_id, *args, **kwargs):
        kwargs.update({"revision": 0, "state": COMMON.TradeState.active})
        trader_name = "autoTRADER"
        trader_id = "INTERNAL"
        aggressor = COMMON.ActorType.true
        initiator = COMMON.ActorType.true
        counterparty = "internal_counterparty"
        super(InternalTrade, self).__init__(order_id, user, trader_id, trader_name,
                                            aggressor, initiator, counterparty, trade_id, *args, **kwargs)
        if not trade_id:
            self.trade_id = "internal_{}".format(self._internal_id)

    @classmethod
    def from_data_line(cls, line, product, exchange_id, tags=None):
        """
        Factory function to create an InternalTrade from a line in an "own_trade"-message's data entry

        :param line: An item from the message's "data" field.
        :type line: dict
        :param product: The product that was traded
        :type product: Product
        :param exchange_id: The exchange where the trade took place.
        :type exchange_id: str
        :param tags: Optionally pass the order tags. Otherwise they will be parsed from the line's "txt" field
        :type tags: dict or None
        :return: The newly created Trade
        :rtype: InternalTrade

        """
        if tags is None:
            tags = ALU.parse_order_tags(line["txt"])
        new_trade = cls(order_id=line["order_id"],
                        user=line["user"],
                        trade_id=line["trade_id"],
                        revision=line["revision"],
                        state=line["state"],
                        product=product,
                        quantity=line["quantity"],
                        price=line["price"],
                        execution_time=line["execution_time"],
                        sell_delivery_area=line["delivery_area"]
                        if line["direction"] == COMMON.Direction.sell else "",
                        buy_delivery_area=line["delivery_area"]
                        if line["direction"] == COMMON.Direction.buy else "",
                        exchange=exchange_id,
                        tags=tags,
                        aggressor_trading_account=line.get("aggressor_trading_account", ""),
                        initiator_trading_account=line.get("initiator_trading_account", ""),
                        route_id=line.get("route_id"),
                        )
        return new_trade


class TradeList(object):
    """Holds all private and public trades for a product.
    """

    def __init__(self, exchange, product):
        """

        :param exchange: The exchange_id this product belongs to.
        :type exchange: str
        :param product: Backreference to the Product
        :type product: Product
        """
        # The key is [trade_id, direction, broker_id] where broker_id is None except for Trayport
        self._own_trades = dict()
        self._internal_trades = dict()
        self._public_trades = dict()
        # Special case NordPool: there exist trades without trade ids for a short
        # period of time until they get updated by NordPool's public_trade
        self._trades_by_order_id = dict()
        self.exchange = exchange
        self.product = product
        if PERSIST.MongoDBConnector().is_initialized:
            self.load_from_db()

        # timestamp of last change of public trades registered for specific product id and areas
        self.last_trade_update_ts = collections.defaultdict(float)  # type: dict[(str, str), float]

    def load_from_db(self):
        trade_list = PERSIST.MongoDBConnector().load_db_own_trades(self.exchange, self.product.product_id)
        for trade_data in trade_list:
            if trade_data["internal"]:
                new_trade = InternalTrade(
                    order_id=trade_data["order_id"],
                    user=trade_data["user"],
                    trade_id=trade_data["trade_id"],
                    revision=trade_data["revision"],
                    state=trade_data["state"],
                    product=self.product,
                    quantity=trade_data["quantity"],
                    price=trade_data["price"],
                    execution_time=ALU.convert_dt_to_timestamp(trade_data["execution_time"]),
                    sell_delivery_area=trade_data["sell_delivery_area"],
                    buy_delivery_area=trade_data["buy_delivery_area"],
                    exchange=self.exchange,
                    tags=trade_data["tags"],
                    route_id=trade_data.get("route_id"),
                )
                # `.get` instead of `[]` is needed only for migration of old databases
                new_trade.regulatory_data = TradeRegulatoryData(trade_data.get("regulatory_data", {}))
                new_trade.terms = trade_data.get("terms", [])
                self.add_internal_trade(new_trade)
            else:
                new_trade = OwnTrade(
                    order_id=trade_data["order_id"],
                    user=trade_data["user"],
                    trader_id=trade_data.get("trader_id"),
                    trader_name=trade_data.get("trader_name"),
                    aggressor=trade_data.get("aggressor", COMMON.ActorType.unknown),
                    initiator=trade_data.get("initiator", COMMON.ActorType.unknown),
                    counterparty=trade_data.get("counterparty"),
                    trade_id=trade_data["trade_id"],
                    revision=trade_data["revision"],
                    state=trade_data["state"],
                    product=self.product,
                    quantity=trade_data["quantity"],
                    price=trade_data["price"],
                    execution_time=ALU.convert_dt_to_timestamp(trade_data["execution_time"]),
                    sell_delivery_area=trade_data["sell_delivery_area"],
                    buy_delivery_area=trade_data["buy_delivery_area"],
                    exchange=self.exchange,
                    tags=trade_data["tags"],
                    aggressor_broker_id=trade_data.get("aggressor_broker_id"),
                    initiator_broker_id=trade_data.get("initiator_broker_id"),
                    aggressor_trading_account=trade_data.get("aggressor_trading_account", ""),
                    initiator_trading_account=trade_data.get("initiator_trading_account", ""),
                    annotations=trade_data.get("annotations"),
                    route_id=trade_data.get("route_id"),
                )
                # `.get` instead of `[]` is needed only for migration of old databases
                new_trade.regulatory_data = TradeRegulatoryData(trade_data.get("regulatory_data", {}))
                new_trade.terms = trade_data.get("terms", [])
                self.add_own_trade(new_trade)

    def update_from_json(self, struct, product, current_timestamp, autotrader_user=None):
        changed_trades = []
        affected_delivery_areas = set()
        if struct["exchange"] not in [COMMON.Exchange.epex, COMMON.Exchange.nordpool, COMMON.Exchange.trayport]:
            return changed_trades, affected_delivery_areas
        if struct["message_type"] in ("own_trade", "internal_trade"):
            log.debug("%s %s", struct["message_type"], struct)
            for line in struct["data"]:
                affected_delivery_areas.add(line["delivery_area"])
                current_trade = self.get_own_by_trade_id(line["trade_id"], line["direction"],
                                                         line.get("initiator_broker_id"))
                tags = ALU.parse_order_tags(line["txt"])
                if not tags and line["user"] == autotrader_user:
                    # The tags (from the text field / JdMemo) are important to assign our own trades to strategies.
                    # It can happen (at least on JD) that we receive a trade without these tags.
                    # We have several fallbacks in place to handle such situations:
                    # 1) If we have an older version of the trade in memory, keep the tags from that trade
                    # 2) If we have the referenced order in memory, take the tags from there
                    # 3) Otherwise, wait for an update message that adds the tags (It is common on JD to first receive
                    #    the trade without tags and later receiuve an update with the tags.)
                    # 1 and 2 are implemented here, while 3 is implemented in the exchange class by setting a tag-lock.
                    if current_trade and current_trade.tags:
                        tags = current_trade.tags
                        log.warning("Not removing tags from trade %s on update", line["trade_id"])
                    else:
                        referenced_order_tags = product.own_order_to_tags.get(
                            (line["order_id"], line.get('initiator_broker_id')))
                        if referenced_order_tags is None and not self.product.is_exchange_initialized:
                            # product.own_order_to_tags is not persisted over exchange restarts, so right after an
                            # exchange restart we have to do lazy loading of this information
                            log.info("Trade with id %s has no tags (text field), but belongs to autotrader's user %s. "
                                     "Trying to load tags from the database for referenced order %s", line["trade_id"],
                                     line["user"], line["order_id"])
                            referenced_order_tags = PERSIST.MongoDBConnector().load_tags_for_order_id(
                                self.exchange, line["order_id"], line.get("initiator_broker_id"))
                            if referenced_order_tags:
                                log.info("Found referenced order tags for trade id %s "
                                         "using order_id %s in the database: %s", line["trade_id"],
                                         line["order_id"], referenced_order_tags)
                        if referenced_order_tags:
                            tags = referenced_order_tags
                            log.warning("Updating trade with missing tags: Adding tags %s from referenced order", tags)

                if current_trade:
                    current_trade.order_internal_id = tags.get("internal_id")
                    if current_trade.revision < line["revision"]:
                        regulatory_data = TradeRegulatoryData()
                        regulatory_data.update_from_data_line(line)
                        quantity = 0 if (line["state"] == COMMON.TradeState.cancelled
                                         or line["state"] == COMMON.TradeState.recall_granted) else line["quantity"]
                        update_trade_dict = dict(quantity=quantity,
                                                 price=line["price"],
                                                 revision=line["revision"],
                                                 state=line["state"],
                                                 aggressor_broker_id=line.get("aggressor_broker_id"),
                                                 initiator_broker_id=line.get("initiator_broker_id"),
                                                 annotations=line.get("annotations"),
                                                 tags=tags,
                                                 regulatory_data=regulatory_data,
                                                 terms=line.get("terms", []),
                                                 aggressor_trading_account=line.get("aggressor_trading_account", ""),
                                                 initiator_trading_account=line.get("initiator_trading_account", ""))
                        counterparty = line.get("counterparty", None)
                        if counterparty:
                            update_trade_dict["counterparty"] = counterparty
                        changed = current_trade.update_inplace(**update_trade_dict)
                        if changed:
                            changed_trades.append(current_trade)
                    elif current_trade.revision == line["revision"]:
                        if not all([current_trade.quantity == line["quantity"],
                                    current_trade.price == line["price"]]):
                            log.critical("Wrong trade revision: Trade id: {}, q: {}/{}, p: {}/{}".format(
                                current_trade.trade_id,
                                current_trade.quantity, line["quantity"],
                                current_trade.price, line["price"]))
                            raise COMMON.HaltExchangeException(self.exchange)
                    else:
                        log.critical("Wrong trade revision: Trade id: {}".format(current_trade.trade_id))
                        raise COMMON.HaltExchangeException(self.exchange)
                elif not current_trade:
                    seconds_since_execution = (datetime.datetime.utcnow() - datetime.datetime.utcfromtimestamp(
                        line["execution_time"])).total_seconds()
                    if (line["state"] == COMMON.TradeState.cancelled
                            or line["state"] == COMMON.TradeState.recall_granted):
                        continue
                    if seconds_since_execution > COMMON.MINUTE * 10:
                        log.warning("Received trade with execution %d minutes in the past (trade_id: %s)",
                                    int(seconds_since_execution / 60), line["trade_id"])
                    if struct["message_type"] == "own_trade":
                        new_trade = OwnTrade.from_data_line(line, product, struct["exchange"], tags=tags)
                        self.add_own_trade(new_trade)
                        changed_trades.append(new_trade)
                    elif struct["message_type"] == "internal_trade":
                        new_trade = InternalTrade.from_data_line(line, product, struct["exchange"], tags=tags)
                        self.add_internal_trade(new_trade)
                        changed_trades.append(new_trade)
                if dbg_condition(product):
                    print(("trade capture", new_trade.quantity, new_trade.price, new_trade.tags))
            for trade in changed_trades:
                trade.update_db(current_timestamp)

        if struct["message_type"] == "public_trade":
            for line in struct["data"]:
                affected_delivery_areas.add(line["sell_delivery_area"])
                affected_delivery_areas.add(line["buy_delivery_area"])
                current_trade = self.get_public_by_trade_id(line["trade_id"], broker_id=line.get("initiator_broker_id"))
                if current_trade:
                    if current_trade.revision < line["revision"]:
                        quantity = 0 if (line["state"] == COMMON.TradeState.cancelled
                                         or line["state"] == COMMON.TradeState.recall_granted) else line["quantity"]
                        current_trade.update_inplace(
                            quantity=quantity,
                            price=line["price"],
                            revision=line["revision"],
                            state=line["state"],
                            aggressor_trading_account=line.get("aggressor_trading_account", ""),
                            initiator_trading_account=line.get("initiator_trading_account", ""))
                        changed_trades.append(current_trade)
                else:
                    if (line["state"] == COMMON.TradeState.cancelled
                            or line["state"] == COMMON.TradeState.recall_granted):
                        continue
                    new_trade = PublicTrade.from_data_line(line, product, struct["exchange"])
                    self.add_public_trade(new_trade)
                    changed_trades.append(new_trade)

            self.update_last_changed_public_trades_timestamp(changed_trades)

            for trade in changed_trades:
                trade.update_db(current_timestamp)

        return changed_trades, affected_delivery_areas

    def update_last_changed_public_trades_timestamp(self, changed_trades):
        """
        Update last update timestamp of any public trade update in the given list,
        grouped by product id and area, ignoring route id and broker id.

        :param changed_trades: we update the timestamp in TradeList object based on the status of these public trades
        :type changed_trades: list[PublicTrade]
        """
        for t in changed_trades:
            for area in (t.buy_delivery_area, t.sell_delivery_area):
                self.last_trade_update_ts[(t.product.product_id, area)] = \
                    max(t.execution_time, self.last_trade_update_ts[(t.product.product_id, area)])

    def remove_trade_by_order_id_if_found(self, order_id):
        trade = self._trades_by_order_id.get(order_id)
        if trade:
            del self._trades_by_order_id[order_id]
            return True
        return False

    def add_trade_to_order_trades(self, trade):
        """Applies only to partially initialized trades without trade ids.
        """
        assert isinstance(trade, OwnTrade)
        self._trades_by_order_id[trade.order_id] = trade

    @staticmethod
    def _exec_call(inst_calls, trade):
        next(callfunc(trade) for inst, callfunc in inst_calls if isinstance(trade, inst))

    @classmethod
    def get_trade_key(cls, trade):
        if isinstance(trade, PublicTrade):
            return cls.build_trade_key(trade.trade_id, None, trade.initiator_broker_id)
        # Note: Initiator and aggressor broker id should always be the same
        return cls.build_trade_key(trade.trade_id, trade.direction, trade.initiator_broker_id)

    @staticmethod
    def build_trade_key(trade_id, direction, broker_id=None):
        if direction is None:  # Public trade
            return "{}_{}".format(trade_id, broker_id)
        return "{}_{}_{}".format(trade_id, direction, broker_id)

    def add_trade(self, trade):
        inst_calls = ((InternalTrade, self.add_internal_trade),
                      (OwnTrade, self.add_own_trade),
                      (PublicTrade, self.add_public_trade))
        self._exec_call(inst_calls, trade)

    def add_own_trade(self, trade):
        trade_key = self.get_trade_key(trade)
        self._own_trades[trade_key] = trade

    def add_internal_trade(self, trade):
        trade_key = self.get_trade_key(trade)
        self._internal_trades[trade_key] = trade

    def add_public_trade(self, trade):
        trade_key = self.get_trade_key(trade)
        self._public_trades[trade_key] = trade

    def remove_trade(self, trade):
        inst_calls = ((InternalTrade, self.remove_internal_trade),
                      (OwnTrade, self.remove_own_trade),
                      (PublicTrade, self.remove_public_trade))
        self._exec_call(inst_calls, trade)

    def remove_public_trade(self, trade):
        trade_key = self.get_trade_key(trade)
        del self._public_trades[trade_key]

    def remove_own_trade(self, trade):
        trade_key = self.get_trade_key(trade)
        del self._own_trades[trade_key]

    def remove_internal_trade(self, trade):
        trade_key = self.get_trade_key(trade)
        del self._internal_trades[trade_key]

    def _update_own_trade(self, trade, trade_id, **kwargs):
        """Update trade id of the trade and other fields with kwargs arguments.
        Will change the key of the trade to the public trade id adif needed."""
        if trade.trade_id.startswith("ORDERID_"):
            self.remove_own_trade(trade)

        trade.trade_id = trade_id
        trade.update(**kwargs)
        self.add_own_trade(trade)
        return trade

    @staticmethod
    def _filter_by_trade_filter(trades, trade_filter):
        # type(list, COMMON.TradeFilter) -> list[Trade]
        result = []
        if trade_filter is None:
            return trades
        properties = COMMON.TradeFilter.properties(trade_filter)
        if properties["public"]:
            result.extend(trade for trade in trades if isinstance(trade, PublicTrade))

        elif properties["own"] or properties["internal"]:
            result.extend(
                trade for trade in trades
                if isinstance(trade, OwnTrade)
                and (properties["buy"] and trade.sell_delivery_area == "")
                or (properties["sell"] and trade.buy_delivery_area == "")
            )

        return result

    def get_by_trade_id(self, trade_id, direction=None, broker_id=None):
        """Returns a trade or many trades based on the passed trade id.

        :param trade_id: Id of the trade
        :param direction: optional. Buy or sell trade
        :param broker_id: The initiator_broker_id of the trade to search for.
                          Has to be given on Trayport, None otherwise.
        :type trade_id: str
        :type direction: str, member of :class:`common.Direction`
        :type: broker_id: str
        :return: :class:`PublicTrade` or :class:`OwnTrade` if one found
            else list of :class:`PublicTrade` or :class:`OwnTrade`

        .. code-block:: python

            # get trade "1444233442"
            api.trades.get_by_trade_id("1444233442")
        """
        found = []

        def check_trade(search_func, trade_id, direction):
            trade = search_func(trade_id, direction, broker_id)
            if trade:
                found.append(trade)

        if direction is None:
            for i_direction in [COMMON.Direction.buy, COMMON.Direction.sell]:
                check_trade(self.get_own_by_trade_id, trade_id, i_direction)
                check_trade(self.get_internal_by_trade_id, trade_id, i_direction)
        else:
            check_trade(self.get_own_by_trade_id, trade_id, direction)
            check_trade(self.get_internal_by_trade_id, trade_id, direction)

        check_trade(self.get_public_by_trade_id, trade_id, direction)

        if len(found) == 1:
            return found[0]
        else:
            return found

    def get_own_by_trade_id(self, trade_id, direction, broker_id=None):
        """Returns an own trade based on the passed trade id.

        :param trade_id: Id of the trade
        :param direction: Buy or sell trade
        :param broker_id: The initiator_broker_id of the trade to search for.
                  Has to be given on Trayport, None otherwise.
        :type trade_id: str
        :type direction: str, member of :class:`common.Direction`
        :type: broker_id: str
        :return: :class:`OwnTrade` if one found
            else None
        """
        try:
            return self._own_trades[self.build_trade_key(trade_id, direction, broker_id)]
        except KeyError:
            return

    def get_internal_by_trade_id(self, trade_id, direction, broker_id=None):
        """Returns an internal trade based on the passed trade id.

        :param trade_id: Id of the trade
        :param direction: Buy or sell trade
        :param broker_id: The initiator_broker_id of the trade to search for.
                  Has to be given on Trayport, None otherwise.
        :type trade_id: str
        :type direction: str, member of :class:`common.Direction`
        :type: broker_id: str
        :return: :class:`OwnTrade` if one found else None
        """
        try:
            return self._internal_trades[self.build_trade_key(trade_id, direction, broker_id)]
        except KeyError:
            return

    def get_public_by_trade_id(self, trade_id, direction=None, broker_id=None):
        """Returns a public trade based on the passed trade id.

        :param trade_id: Id of the trade
        :type trade_id: str
        :param direction: optional. Buy or sell trade
        :type direction: str, member of :class:`common.Direction`
        :param broker_id: The initiator_broker_id of the trade to search for.
                          Has to be given on Trayport, None otherwise.
        :type broker_id: str
        :rtype: APITR.PublicTrade
        :return: :class:`PublicTrade` if one found
            else else None
        """
        try:
            return self._public_trades[self.build_trade_key(trade_id, None, broker_id)]
        except KeyError:
            return

    def get_by_order_id(self, order_id):
        """Takes only partially initialized trades into account, which don't have
           trade ids.
        """
        return self._trades_by_order_id.get(order_id)

    def get_public_by_order_id(self, order_id):
        for trade in self.get(trade_filter=COMMON.TradeFilter.public):
            if trade.buy_order_id == order_id or trade.sell_order_id == order_id:
                return trade

    def get_own_by_order_id(self, order_id):
        for trade in self.get(trade_filter=COMMON.TradeFilter.own):
            if trade.order_id == order_id:
                return trade

    def get(self, buy_delivery_area=None, sell_delivery_area=None,
            delivery_area=None,
            portfolio_key=None,
            trade_filter=None,
            timerange=None):
        # type: (str, str, str, str, COMMON.TradeFilter, tuple[int]) -> list[Trade]
        """Returns a list of trades based on the filter criteria passed.

        :param buy_delivery_area: optional. Buy area of the trade
        :param sell_delivery_area: optional. Sell area of the trade
        :param delivery_area: optional. Buy or sell delivery area of the trade
        :param portfolio_key: optional. Portfolio of trade.
            This parameter corresponds to the strategy id
        :param trade_filter: optional. Filter definition
        :param timerange: optional, tuple containing 2 timestamps, filtering by trade execution
        :type buy_delivery_area: str, member of :class:`common.Area`
        :type sell_delivery_area: str, member of :class:`common.Area`
        :type delivery_area: str, member of :class:`common.Area`
        :type portfolio_key: str
        :type trade_filter: member of :class:`TradeFilter`
        :type timerange: tuple with 2 int elements

        :return: list of :class:`PublicTrade` or :class:`OwnTrade`
        :rtype: list[Trade]
        .. code-block:: python

            # get all our buy trades concluded in german Amprion area
            api.trades.get(delivery_area=common.Area.rwe, trade_filter=TradeFilter.own_buy)
        """
        result = []
        trades = []

        if trade_filter is not None:
            properties = COMMON.TradeFilter.properties(trade_filter)
            if properties["own"]:
                trades.extend(list(self._own_trades.values()))
            if properties["internal"]:
                trades.extend(list(self._internal_trades.values()))
            if properties["public"]:
                trades.extend(list(self._public_trades.values()))
        else:
            trades = list(self._own_trades.values()) + \
                list(self._internal_trades.values()) + \
                list(self._public_trades.values())
        if timerange is not None and len(timerange) == 2:
            trades = [t for t in trades if timerange[0] <= t.execution_time <= timerange[1]]
        for trade in trades:
            if delivery_area is not None \
                    and delivery_area not in (trade.buy_delivery_area, trade.sell_delivery_area):
                continue
            if buy_delivery_area is not None \
               and buy_delivery_area != trade.buy_delivery_area:
                continue
            if sell_delivery_area is not None \
               and sell_delivery_area != trade.sell_delivery_area:
                continue
            result.append(trade)
        if portfolio_key is not None:
            result = [trade for trade in result if trade.portfolio_key == portfolio_key]
        return TradeList._filter_by_trade_filter(result, trade_filter)

    def get_volume(self, delivery_area_id, trade_filter, portfolio_key=None):
        """Returns the overall volume of the trades defined by the filters.

        :param delivery_area_id: optional. Buy or sell delivery area of the trade
        :param trade_filter: Filter definition
        :param portfolio_key: optional. Portfolio of trade.
            This parameter corresponds to the strategy id
        :type delivery_area_id: str, member of :class:`common.Area`
        :type trade_filter: member of :class:`TradeFilter`
        :type portfolio_key: str

        :return: overall volume as float
        :rtype: float
        """
        volume = 0
        for trade in self.get(delivery_area=delivery_area_id, portfolio_key=portfolio_key, trade_filter=trade_filter):
            volume += trade.quantity
        return volume

    def get_balance(self, delivery_area_id, portfolio_key=None):
        """Returns the balance volume (i.e. buy - sell) of own trades

        :param str delivery_area_id: optional. Buy or sell delivery area of the trade, member of :class:`common.Area`
        :param str portfolio_key: optional. Portfolio of trade.
            This parameter corresponds to the strategy id

        :return: overall volume as float
        """
        volume = 0
        trade_filter = COMMON.TradeFilter.own
        for trade in self.get(delivery_area=delivery_area_id, portfolio_key=portfolio_key, trade_filter=trade_filter):
            sign = -1 if (isinstance(trade, OwnTrade) and trade.direction == COMMON.Direction.sell) else 1
            volume += trade.quantity * sign
        return volume

    def __repr__(self):
        return str(self.__dict__)
