#!/usr/bin/python3
# -*- coding: utf-8 -*-

from __future__ import absolute_import

import abc
import collections
import copy
import datetime
import json
import math
import operator
import random
import time
import uuid

import dateutil.relativedelta as RD
import six
from six.moves import filter
from six.moves import range

import autotrader_lib.common as COMMON
import autotrader_lib.compliance_log_templates as LOGTEMP
import autotrader_core.exchange_config as EXCFG
import autotrader_core.exchange_rate_limiting as ERL
import autotrader_core.exchange_trading as APITR
import autotrader_core.internal_market
import autotrader_core.persistence as PERSIST
import autotrader_core.simulation_data
import autotrader_core.statistics as STATS
import autotrader_core.trayport_records as TR
import autotrader_core.utils as UTILS
import autotrader_lib.cet_util as ALCU
import autotrader_lib.config_helper as ATCONF
import autotrader_lib.util as ALU

if six.PY2:
    import autotrader_lib.fast_logging_py2 as FLOG
else:
    import autotrader_lib.fast_logging_py3 as FLOG

log = FLOG.getLogger("autotrader.exchanges")

dbg_condition = APITR.dbg_condition


@autotrader_core.utils.memorize
def modify_orders(orders, execmode, market_state):
    """
    Adding utils.memorize decorator to this function,
    makes the function name to a dictionary containing
    cached orders of the following form:
    {"entry_orders": entry_orders,
     "modify_orders": modify_orders,
     "delete_orders": delete_orders}
    """
    modify_orders_list = []
    delete_orders_list = []
    entry_orders_list = []

    if market_state == COMMON.MarketState.hibernated:
        log.debug("No orders modified because of market halt")
    else:
        for order in orders:
            if getattr(order, "order_id", None) is not None:
                # an order_id is given by the epex
                # which means that it is not an entry but a modification
                if order.quantity < COMMON.MIN_ORDER_QTY:
                    delete_orders_list.append(order)
                else:
                    modify_orders_list.append(order)
            else:
                if order.quantity < COMMON.MIN_ORDER_QTY:
                    continue
                entry_orders_list.append(order)
            order.execmode = execmode
            order.tags["execmode"] = str(execmode)
    all_orders = {}
    if entry_orders_list:
        all_orders[COMMON.ResolverState.entry_orders] = entry_orders_list
    if modify_orders_list:
        all_orders[COMMON.ResolverState.modify_orders] = modify_orders_list
    if delete_orders_list:
        all_orders[COMMON.ResolverState.delete_orders] = delete_orders_list
    return all_orders


class ExchangeInterface(six.with_metaclass(abc.ABCMeta, object)):
    """Abstract BaseClass for Exchanges to define all necessary methods which are called in api.py"""

    @abc.abstractmethod
    def remove_old_ioc_orders(self, timestamp):
        pass

    @abc.abstractmethod
    def initialize(self):
        """Initialize the exchange; including sending initialization messages to the exchange
        """
        pass

    def bookkeeping_on_timer_fast(self, current_timestamp):
        """
        Run some internal bookkeeping tasks that have to run frequently on timer fast.

        :type current_timestamp: float or int
        :return: The strategy callbacks that should be run after this. A dict callback_name -> modified objects
        :rtype: dict
        :meta private:
        """
        return {}

    @abc.abstractmethod
    def init_files_ready(self):
        """Returns True if the exchange has successfully handled its init messages

        :rtype: bool
        """
        pass

    @abc.abstractmethod
    def update_db(self, timestamp, history_fields=None):
        pass

    @abc.abstractmethod
    def update_indicators(self, timestamp):
        pass

    @abc.abstractmethod
    def update_connection_status(self, status):
        pass

    @abc.abstractmethod
    def request_private_order_book_info(self, start=None, end=None):
        pass

    @abc.abstractmethod
    def request_trade_captures(self, start, end):
        pass

    @abc.abstractmethod
    def serialize_trades(self):
        pass

    @abc.abstractmethod
    def serialize_order_book(self, message):
        pass

    @abc.abstractmethod
    def serialize_products(self, timestamp):
        pass

    @abc.abstractmethod
    def serialize_market_state(self):
        pass

    @abc.abstractmethod
    def resolve_order_conflicts(self, current_timestamp, products_to_intmarket=None, is_parent=True):
        pass

    @abc.abstractmethod
    def order_modify_chunking(self, orders, message_type):
        pass

    @abc.abstractmethod
    def remove_old_products(self):
        pass

    @abc.abstractmethod
    def remove_old_orderbook(self, timestamp):
        pass

    @abc.abstractmethod
    def update_from_json(self, struct, current_timestamp):
        pass

    @abc.abstractmethod
    def update_from_json_on_trade(self, struct, current_timestamp):
        pass

    @abc.abstractmethod
    def update_from_json_on_order(self, struct, current_timestamp, confirm_lock=None):
        pass

    @staticmethod
    def modify_orders(orders, execmode, market_state):
        pass

    @staticmethod
    def send_func(*args):
        pass

    @abc.abstractmethod
    def send(self, struct, properties=None):
        pass

    @abc.abstractmethod
    def update_market_halt(self, market_halt):
        pass


class StoppableExchangeBase(ExchangeInterface):
    """
    Common functionality for NullExchange and ExchangeBase with the ability to stop the exchange.

    :ivar str internal_id: exchange internal id
    :ivar bool allowed: if the exchange is allowed in the system.cfg
    :ivar str market_state: state of the market (i.e. public exchange)
    :ivar bool connected: determines if the exchange is connected
    :ivar bool halted: if the exchange is halted due to an error
    :ivar str halt_reason: reason of exchange being halted
    :ivar list areas: list of available areas
    :ivar str caption: exchange name
    :ivar set market_halt_set: holds market halt timestamps
    """
    __metaclass__ = abc.ABCMeta

    def __init__(self, allowed, internal_id, is_parent):
        self.internal_id = internal_id
        self.allowed = allowed
        self.market_state = None
        self.connected = False
        self.halted = False
        self.critical_exchange_halt = False
        self.halt_reason = ""
        self.areas = [
            (area_id, COMMON.Area.get_caption(area_id, self.internal_id))
            for area_id in COMMON.Area.get_all(self.internal_id)
        ]
        self.caption = internal_id
        self.is_parent = is_parent
        self.market_halt_set = set()  # 15Minutes Blocks with halt
        self.remove_orders = True
        self.simulation_mode = False
        self.last_incoming_message_timestamp = 0
        self.capacities = APITR.Capacities(internal_id)
        self.routes = None
        self.init_files_correlation_ids = {}
        self.initialized_dt = None

        # this field is updated everytime we call self.update_db
        # Warning ! Do not rely on this field to know if the autotrader is initialized or not, instead use the
        # init_files_ready function! This attribute is used in the persistence to reflect the state of the exchange.
        self.initialized = None

    def stop_exchange(self, reason, timestamp=None, remove_orders=True, critical=False,
                      username=COMMON.PeriotheusSystemUsers.system):
        """Stops exchange for trading with keeping the reason for stopping at the DB

        :param str reason: stop reason
        :param bool remove_orders: should the orders be removed on halt
        :param float or None timestamp: current timestamp
        :param bool critical: True if that halt was caused by an error, false if the halt was requested by a user.
        :param str username: username for compliance log
        """
        if not (self.halted or self.critical_exchange_halt == critical and self.halt_reason == reason):
            history_fields = ["halted", "halt_reason", "remove_orders", "critical_exchange_halt"]
        else:
            history_fields = []

        self.halted = True
        self.halt_reason = reason
        self.remove_orders = remove_orders
        self.critical_exchange_halt = critical

        if timestamp is None:
            timestamp = time.time()

        # when halted, we write status to mongo directly avoiding queue
        PERSIST.MongoDBConnector().update_db_exchanges(
            self, timestamp, history_fields=history_fields
        )

        log.warning("Stop %s exchange. Reason: '%s'", self.caption, reason)
        log.compliance_log(log_entry=LOGTEMP.AutoTraderBasic.exchange_halted,
                           exchange_name=self.internal_id,
                           reason=reason, critical=critical,
                           remove_orders=remove_orders,
                           username=username)

    def _load_state_from_db(self):
        """Loads exchange state from DB on class initialization"""
        exchange = PERSIST.MongoDBConnector().load_db_exchange(self.internal_id, self.caption)
        if exchange:
            self.halted = exchange.get("halted", False)
            self.halt_reason = exchange.get("halt_reason", "")
            self.remove_orders = exchange.get("remove_orders", True)
            self.critical_exchange_halt = exchange.get("critical_exchange_halt", False)


class NullExchange(StoppableExchangeBase):
    """Empty Exchange placeholder for not initialized exchanges"""

    def __init__(self, allowed, internal_id, indicator_update=True, is_parent=True):
        # type: (bool, str, bool, bool) -> None
        super(NullExchange, self).__init__(allowed, internal_id, is_parent)

        self.products = APITR.Products(internal_id, True, None, is_null_exchange=True,
                                       indicator_update=indicator_update)
        # use a real Product PriorityQueue, but mock the get_products function
        self.products_queue = APITR.ProductsPriorityQueue()
        self.products_queue.get_products = self._get_products_dummy
        self._load_state_from_db()

    @staticmethod
    def _get_products_dummy(_active_products, _current_timestamp):
        return []

    def remove_old_ioc_orders(self, timestamp):
        pass

    def initialize(self):
        pass

    def init_files_ready(self):
        return False

    def update_db(self, timestamp, history_fields=None):
        pass

    def update_indicators(self, timestamp):
        pass

    def update_connection_status(self, status):
        pass

    def request_private_order_book_info(self, start=None, end=None):
        pass

    def request_trade_captures(self, start, end):
        pass

    def serialize_market_state(self):
        # type: () -> dict
        return {"exchange": COMMON.Exchange.autotrader,
                "timestamp": int(time.time()),
                "message_type": COMMON.Response.market_state,
                "data": {"state": self.market_state}}

    def serialize_trades(self):
        pass

    def serialize_order_book(self, message):
        pass

    def serialize_products(self, timestamp):
        pass

    def resolve_order_conflicts(self, current_timestamp, products_to_intmarket=None, is_parent=True):
        pass

    def order_modify_chunking(self, orders, message_type):
        pass

    def remove_old_products(self):
        pass

    def remove_old_orderbook(self, timestamp):
        pass

    def update_from_json(self, struct, current_timestamp):
        pass

    def update_from_json_on_trade(self, struct, current_timestamp):
        pass

    def update_from_json_on_order(self, struct, current_timestamp, confirm_lock=None):
        pass

    @staticmethod
    def modify_orders(orders, execmode, market_state):
        pass

    def start_exchange(self, timestamp=None, username=COMMON.PeriotheusSystemUsers.system):
        pass

    def update_on_timer(self, current_timestamp):
        pass

    def remove_own_orders_on_init(self):
        pass

    def delete_all_orders(self):
        pass

    def send_func(self, *args):
        log.warning("Trying to send message to %s NullExchange: %s", self.internal_id, str(args))
        return None

    def send(self, struct, properties=None):
        return self.send_func(struct, properties)

    def update_market_halt(self, market_halt):
        pass

    def __str__(self):
        return "{} (class name: {})".format(self.internal_id, self.__class__.__name__)


class ExchangeBase(StoppableExchangeBase):
    """ExchangeBase class holding common functionality among the exchanges

    :ivar Products products: exchange products
    :ivar bool create_dummy_products: if dummy products are to be created
    :ivar func modify_orders: deep copy of the :func:`modify_orders`
    :ivar ProductsPriorityQueue products_queue: holds products queue for the exchange
    :ivar int global_internal_execmode: global execution mode for resolving order conflicts on the internal market
    :ivar str autotrader_user: autotrader user used on the exchange
    :ivar float last_incoming_message_timestamp: timestamp of the last received message
    :ivar int error_queue_max_size:
    :ivar collections.deque error_queue:
    :ivar float tick_size:  minimal price step for an order (exchange dependent)
    :ivar int force_lock: determines the forced product lock in seconds.
                          If set to None, no force product lock is applied
    """
    __metaclass__ = abc.ABCMeta

    def __init__(self, internal_id, send_func, create_dummy_products,
                 allowed, exchange_config, lock_timeout=None,
                 indicator_update=True, current_time=None, is_parent=True):
        """Exchange Base class

        The class contains basic functionality

        :param internal_id: exchange internal id as defined in :class:`COMMON.Exchange`
        :type internal_id: str
        :param send_func: callable that sends a message to the exchange
        :type send_func: callable
        :param create_dummy_products:
        :type create_dummy_products: types.FunctionType
        :param allowed:
        :type allowed: bool
        :param exchange_config: exchange config parameters
        :type exchange_config: ATCONF.ExchangeConfig
        :param lock_timeout: determines product lock timeout for execution and modification
                             in seconds, defaults to None. If set to None, the product
                             stays locked, unless an appropriate modification or execution
                             is received.
        :type lock_timeout: int|None
        :param indicator_update: if set indicators will get updated on all products
        :type indicator_update: bool
        :type current_time: float or None
        """
        super(ExchangeBase, self).__init__(allowed, internal_id, is_parent)

        self.send_func = send_func
        self.products = APITR.Products(self.internal_id, create_dummy_products, lock_timeout,
                                       indicator_update=indicator_update)
        self.lock_timeout = lock_timeout
        self.create_dummy_products = create_dummy_products
        self._market_state_revision = None
        self.modify_orders = copy.deepcopy(modify_orders)
        self.products_queue = APITR.ProductsPriorityQueue()

        self.global_internal_execmode = exchange_config.internal_market_mode
        self.autotrader_user = exchange_config.autotrader_user
        self.read_only = exchange_config.read_only

        if exchange_config.autotrader_user is None:
            err = "Please provide an autotrader_user setting in the config file for {}".format(self.internal_id)
            log.critical(err)
            raise ALU.ConfigError(err)
        self.error_queue_max_size = 1000
        # error queue [ ( <timestamp>, <text> ) ] for up to 1000 error messages
        self.error_queue = collections.deque(maxlen=self.error_queue_max_size)

        self.tick_size = 0.01
        self._load_from_db(current_time or time.time())

        # set global internal market settings, such as execmode and aggress other brokers
        # aggress_other_brokers has to be communicated to the internal market, but only the TrayportConfig has that
        # field, so we need to read it, and just set it to True by default for all other exchanges
        self.aggress_other_brokers = getattr(exchange_config, "aggress_other_brokers", True)
        self.internal_market = autotrader_core.internal_market.InternalMarket(
            self.internal_id, self.global_internal_execmode, self.aggress_other_brokers
        )

        # Internal market vault holding the pending entry orders on the parent autotrader (unused on children)
        self._vault = autotrader_core.utils.InternalMarketVault()

        self._configuration = EXCFG.ExchangeConfiguration.from_db(self.internal_id)

        # set of broker ids on TRAYPORT which need special orderbook handling
        # these broker mix all orders on the same price level, including own orders
        # so they are marked for special handling, which means, when we look for public orderbook,
        # we manually remove the own orders by removing their quantity from the price level to get only the quantity
        # of public orders
        self.combined_order_brokers = frozenset()  # type: frozenset[str]

        # The set of brokers where we do not want to use order matching and conversion of orders to trade orders
        self.brokers_without_tradeorders = frozenset()  # type: frozenset[str]

        # The set of brokers which should handle trade lock release for multimatching orders. Used especially for EEX
        # and ICE
        self.brokers_with_multimatching_lock_release = frozenset()  # type: frozenset[str]

        # store (order_id, timestamp) tuples here by product for orders that we want to be cleaned up after timeout
        self.orders_with_timeout = collections.defaultdict(list)

    def _load_from_db(self, _=None):
        """
        Load the exchange state from Mongo and clear init files when the exchange instance is initialized.
        Can be overwritten by a specific exchange.

        :param _: unused current time argument to keep method signature
        :type _: float or None
        """
        self._load_state_from_db()
        self.init_files_correlation_ids = {}

    def bookkeeping_on_timer_fast(self, current_timestamp):
        """
        Run some internal bookkeeping tasks that have to run frequently on timer fast.

        :type current_timestamp: float or int
        :return: The strategy callbacks that should be run after this. A dict callback_name -> modified objects
        :rtype: dict
        :meta private:
        """
        return {}

    def init_files_ready(self):
        if not self.init_files_correlation_ids or not all(self.init_files_correlation_ids.values()):
            return False
        # We make a datetime entry (UTC) in the object when it was first initialized
        if self.initialized_dt is None:
            self.initialized_dt = datetime.datetime.utcnow()
            self.products.on_exchange_initialized()
        return True

    def _send_init_file(self, message_body, prefix, topic=None):
        """
        Send a message to the exchange as part of initialization

        :param message_body: body of the message to send
        :type message_body: dict
        :param prefix: "init", "trayport-init" or "nordpool-init"
        :type prefix: str
        :param topic: For trayport, we need to distinguish the topics (shortcuts for message_types)
                      of the init-messages, so we can send the next query,
                      once all messages of one type have been answered.
        :type topic: str or None
        """
        if self.is_parent:
            file_id = str(uuid.uuid1())[:8]
            if topic:
                file_id = "{}_{}".format(topic, file_id)

            self.send(message_body, {"correlation_id": "{}-{}".format(prefix, file_id)})
            log.debug("Send init message: %s, %s-%s", message_body.get("message_type"), prefix, file_id)
            self.init_files_correlation_ids[file_id] = False

    def update_db(self, timestamp, history_fields=None):
        if history_fields is None:
            history_fields = []

        was_initialized = self.initialized
        self.initialized = self.init_files_ready()
        if was_initialized != self.initialized:
            history_fields.append("initialized")

        PERSIST.MongoDBConnector().update_db_exchanges(
            self, timestamp, history_fields=history_fields
        )

    def update_indicators(self, timestamp):
        self.products.update_indicators(timestamp)

    def update_connection_status(self, status):
        current_status = self.connected
        self.connected = status
        if status != current_status:
            log.warning("Switching exchange status to connected=%s", status)
            self.update_db(time.time(), history_fields=["connected"])
            log.compliance_log(log_entry=LOGTEMP.AutoTraderBasic.exchange_connection_state_change,
                               exchange_name=self.internal_id,
                               old_state=current_status,
                               new_state=status)

    def request_private_order_book_info(self, start=None, end=None):
        data = None
        if start and end:
            data = dict(start=start, end=end)
        return {"exchange": self.internal_id,
                "timestamp": int(time.time()),
                "message_type": COMMON.Request.own_orders,
                "data": data}

    def request_trade_captures(self, start, end):
        return {"exchange": self.internal_id,
                "timestamp": int(time.time()),
                "message_type": COMMON.Request.own_trade,
                "data": {"start": start,
                         "end": end}}

    def delete_all_orders(self):
        """
        Get the message to delete all orders, in the format used between autotrader and the connection managers

        :meta private:
        """
        return {"exchange": self.internal_id,
                "timestamp": int(time.time()),
                "message_type": COMMON.Request.order_delete_all,
                "data": []}

    def serialize_trades(self):
        data = []
        for product in self.products.get_all():
            delivery_period = (product.delivery_start, product.delivery_end)
            for trade in product.trades.get(trade_filter=COMMON.TradeFilter.own):
                if trade.direction == COMMON.Direction.buy:
                    delivery_area = trade.buy_delivery_area
                elif trade.direction == COMMON.Direction.sell:
                    delivery_area = trade.sell_delivery_area
                else:
                    raise ValueError("Unknown trade direction: %s" % (trade.direction,))
                data.append({"txt": ALU.serialize_order_tags(trade.tags),
                             "user": trade.user,
                             "execution_time": trade.execution_time,
                             "trade_id": trade.trade_id,
                             "delivery_area": delivery_area,
                             "revision": trade.revision,
                             "state": trade.state,
                             "price": trade.price,
                             "order_id": trade.order_id,
                             "quantity": trade.quantity,
                             "product_id": trade.product.product_id,
                             "direction": trade.direction,
                             "delivery_period": delivery_period,
                             "exchange": trade.exchange,
                             "product_type": trade.product.product_type
                             })
        return data

    def serialize_order_book(self, message):
        product_id = message["data"]["product_id"]
        data = []
        try:
            product = self.products.get_by_id(product_id)
            orders = product.orders.get(delivery_area_id=message["data"]["area"],
                                        order_filter=COMMON.OrderFilter.public)
        except COMMON.ProductNotFound:
            orders = []
        for order in orders:
            data.append({"order_id": order.order_id,
                         "quantity": order.quantity,
                         "price": order.price,
                         "side": order.direction,
                         "type": "public"})
        try:
            product = self.products.get_by_id(product_id)
            orders = product.orders.get(delivery_area_id=message["data"]["area"],
                                        order_filter=COMMON.OrderFilter.own)
        except COMMON.ProductNotFound:
            orders = []
        for order in orders:
            data.append({"order_id": order.order_id,
                         "quantity": order.quantity,
                         "price": order.price,
                         "side": order.direction,
                         "type": "own"})
        message = {"exchange": COMMON.Exchange.autotrader,
                   "timestamp": int(time.time()),
                   "message_type": COMMON.Response.order_book,
                   "data": {"order_book": data}}
        return message

    def serialize_products(self, timestamp):
        amount_indexes_to_serialize = [0, 1, 3, 7, 15]

        data = []

        products_by_span = {}

        for product in self.products.get_by_timerange(start=int(time.time() - 12 * COMMON.HOUR),
                                                      end=int(time.time() + 48 * COMMON.HOUR)):
            key = (product.delivery_start, product.delivery_end, product.product_type)
            products_by_span[key] = product

        unified_products_by_span = UTILS.unify_xbid_and_local_product_type(products_by_span)

        for products in unified_products_by_span.values():
            all_areas = COMMON.Area.get_all(exchange=self.internal_id)
            price_indicators = STATS.calculate_price_indicators(products, all_areas, timestamp)
            indicators_data = STATS.calculate_indicators_data(products, all_areas, amount_indexes_to_serialize,
                                                              timestamp)
            trades = []
            own_trade_ids = set()
            for product in products:
                trades.extend(product.trades.get())
                own_trade_ids.update((t.trade_id, t.aggressor_broker_id)
                                     for t in product.trades.get(trade_filter=COMMON.TradeFilter.own_exchange))
            trade_statistics = STATS.calculate_statistics_for_trades(trades, exchange_id=self.internal_id)
            prices = STATS.calculate_volume_weighted_average_price(trades, exchange_id=self.internal_id)

            # "products" always has local product, and it's always the first product in the list
            product = products[0]

            product_info = {"product_id": product.product_id,
                            "product_type": product.product_type,
                            "name": product.name,
                            "delivery_start": product.delivery_start,
                            "delivery_end": product.delivery_end,
                            "own_trade_ids": list(own_trade_ids),
                            "trade_count": len(own_trade_ids),
                            "exchange": self.internal_id}
            product_info.update(prices)
            product_info.update(trade_statistics)
            product_info.update(indicators_data)
            product_info.update(price_indicators)
            data.append(product_info)
        return data

    def get_vault_products(self):
        """
        Get a set of products for which we have orders in the vault.
        :return: A set of products
        :rtype: set[APITR.Product]
        """
        return self._vault.get_products()

    def resolve_order_conflicts(self, current_timestamp, products_to_intmarket=None, is_parent=True):
        """The function detects and resolves the conflict between the two own orders

        The function returns an orders_to_send dictionary in the following keys:

        * "entry_orders";
        * "modify_orders";
        * "delete_orders";
        * "delete_all_orders";
        * "deactivate_orders";
        * "activate_orders";
        * "trade_orders";
        * "internal_trades";
        * "internal_order_executions";
        * "internal_order_reject";
        * "internal_trade_lock"

        The orders from the dictionary are than sent to the exchange or are propagated back from parent
        to the children

        :param float current_timestamp:
        :param list products_to_intmarket: products to be checked on the internal market even if the strategy
               does not request any actions
        :param bool is_parent: if the autotrader is operated in the parent of child mode
        :return orders_to_send: dict with orders to be sent to the master while executing on a child autotrader or
                                to the exchange and children while executing on parent autotrader
        :rtype: dict[str, list]
        """

        orders_to_check = self._get_orders_to_check()
        modified_products = self._get_modified_products(products_to_intmarket, orders_to_check)

        orders_to_send = collections.defaultdict(list)

        if is_parent:
            self._vault.add_entry_orders(orders_to_check, current_timestamp)
            log.debug("VAULT %s", self._vault)

        # Sometimes we want to include the reason for rejecting a modification request in the reject message.
        # As the reject_reason dictionary is not product specific, we have to reset it once
        # before we loop over the products
        self.internal_market.reject_reasons = {}

        for product in modified_products:
            # Get new orders allowed by the internal market
            new_orders = self._get_new_orders(orders_to_check, product, is_parent, current_timestamp)
            # Lock products with orders, which are send to the exchange for master, or to the parent for children
            orders_to_send = self._lock_orders(new_orders, orders_to_send, product, current_timestamp, is_parent)

        if self.halted:
            # Dangling entry orders in the internal market vault are deleted as well
            self.internal_market.append_released_orders(orders_to_send, self._vault.release_all())

        # Update last_delete_attempt timestamps for all orders that are going to be deleted
        # We assume that delete orders won't get rejected/discarded past this point
        self._update_delete_throttling_timestamp(orders_to_send.get(COMMON.ResolverState.delete_orders, []),
                                                 current_timestamp)
        self._update_delete_throttling_timestamp(
            orders_to_send.get(COMMON.ResolverState.delete_orders_for_locked_product, []),
            current_timestamp
        )

        if orders_to_send:
            log.info("ORDERS TO EXCHANGE \n%s",
                     "\n".join(["%s: %s" % (key, "\n".join([str(value) for value in values]))
                                for key, values in orders_to_send.items()
                                if values]))
        self.modify_orders.clear_cache()
        return orders_to_send

    def _get_orders_to_check(self):
        """Helper function to create orders_to_check dictionary based on the cached orders

        If the exchange is halted, orders_to_check will be reduced only to the incoming delete orders.
        """
        orders_to_check = self.modify_orders.cache()
        log.debug("Orders to check: %s",
                  "; ".join("{}: {}".format(key, ", ".join([order.internal_id for order in orders]))
                            for key, orders in orders_to_check.items() if orders))
        if self.halted:
            # If the exchange is halted, we allow to send only delete order requests
            log.debug("%s is halted (reason: %s). Only order delete requests are sent",
                      self.caption, self.halt_reason)
            del_orders = orders_to_check[COMMON.ResolverState.delete_orders]
            orders_to_check = {COMMON.ResolverState.delete_orders: del_orders}

        return orders_to_check

    @staticmethod
    def _get_modified_products(products_to_intmarket, orders_to_check):
        """Helper function to get a list of all modified products"""
        modified_products = set([order.product for orders in six.itervalues(orders_to_check) for order in orders])
        if products_to_intmarket:
            modified_products = modified_products | set([product for product in products_to_intmarket])
        return modified_products

    @staticmethod
    def _update_delete_throttling_timestamp(del_orders, current_timestamp):
        # for all orders that are going to be deleted update the last_deleted timestamp in the orderbook
        for order in del_orders:
            original_order = order.product.orders.get_own_order_by_order_id(order.order_id, broker_id=order.broker_id)
            if original_order is None:
                log.warning("Trying to delete order that can't be found in the orderbook: {}"
                            "".format(order.order_id))
            else:
                original_order.last_delete_attempt = current_timestamp

    def _get_new_orders(self, orders_to_check, product, is_parent, current_timestamp):
        # type: (dict[str, list[APITR.OwnOrder]], APITR.Product, bool, float) -> None
        """Helper function to obtain a dict with new order wishes.

        If the product is locked, only delete orders are propagated to the internal market

        On the parent, this also converts orders to trade orders on Trayport.

        :param orders_to_check: The new order wishes from the strategies (a dict with COMMON.ResolverState's as keys
                                and lists of orders as values.
        :type orders_to_check: dict
        :param product: The product for which this function is run
        :type product: APITR.Product
        :param is_parent: Whether or not we are on autoTRADER parent.
        :type is_parent: bool
        :type current_timestamp: float
        """
        new_orders = {}

        timed_out_order_locks = product.time_out_product_locks(current_timestamp)[0]  # NOTE: The method returns a tuple
        if timed_out_order_locks and any(
            [self.last_incoming_message_timestamp <= lock.timestamp for lock in timed_out_order_locks]
        ):
            log.error(
                "Scheduling a restart of an unresponsive exchange: {}. Last message received at {}".format(
                    product.exchange, ALU.convert_from_timestamp(
                        self.last_incoming_message_timestamp,
                        "%Y-%m-%dT%H:%M:%S.%fZ"
                    )
                )
            )
            raise COMMON.UnresponsiveExchangeException(self.internal_id)
        # Check, if the product is locked.
        product_locked = product.is_product_locked(current_timestamp)

        if product_locked:
            log.warning("Product %s is locked: allow only for order deletions", product.name)
            del_orders = [order for order in orders_to_check.get(COMMON.ResolverState.delete_orders, [])
                          if order.product == product and order.internal_id not in product.order_lock]
            del_orders_locked_product = [order for order in orders_to_check.get(COMMON.ResolverState.delete_orders, [])
                                         if order.product == product and order.internal_id in product.order_lock]

            # Add preexisting delete_for_locked_product
            del_orders_ids = set(order.internal_id for order in del_orders_locked_product)
            existing_del_orders_locked_product = orders_to_check.get(
                COMMON.ResolverState.delete_orders_for_locked_product, [])
            del_orders_locked_product += [order for order in existing_del_orders_locked_product
                                          if order.product == product and order.internal_id not in del_orders_ids]

            # Throttle delete_orders_for_locked_products and filter orders where the product area became untradeable:
            del_orders_locked_product = [order for order in del_orders_locked_product
                                         if order.can_attempt_delete(current_timestamp)
                                         and product.is_tradable(current_timestamp, order.delivery_area_id)]

            if del_orders:
                new_orders[COMMON.ResolverState.delete_orders] = del_orders
            if del_orders_locked_product:
                new_orders[COMMON.ResolverState.delete_orders_for_locked_product] = del_orders_locked_product
            if not any([del_orders, del_orders_locked_product]):
                new_orders = {}
        else:
            for order_type, orders in orders_to_check.items():
                order_list = []
                for order in orders:
                    if order.product != product:
                        continue
                    if order.state == COMMON.OrderState.unknown:
                        # This should happen rarely, one case where this is known to happen is when the M7 XBID
                        # disconnects (e.g.: during SIDC maintenence)
                        log.info("Removing order {} from {} because its state is unknown"
                                 "".format(order.internal_id, order_type))
                    elif order.state == COMMON.OrderState.hibe and not order.reactivate:
                        # This should happen rarely, as we check for hibernation on the placing of slots,
                        # but could happen on the parent if there is a race between a modification and a hibernation.
                        log.info("Removing order %s from %s because it is hibernated", order.internal_id,
                                 order_type)
                    else:
                        order_list.append(order)
                if order_list:
                    new_orders[order_type] = order_list
            # Get all orders from the orderbook (except for manually hibernated orders).
            actual_orders = self._get_actual_orders(product, current_timestamp)

            if is_parent and not self.halted:
                # Release expired orders from the vault.
                released_objects = self._vault.release_on_timeout(current_timestamp)

                # The remaining orders are added to the requested orders from the vault.
                if COMMON.ResolverState.entry_orders in new_orders:
                    for pending_order in self._vault.get_orders(product.product_id):
                        if pending_order not in new_orders[COMMON.ResolverState.entry_orders]:
                            new_orders[COMMON.ResolverState.entry_orders].append(pending_order)
                else:
                    new_orders[COMMON.ResolverState.entry_orders] = self._vault.get_orders(
                        product.product_id)

                # Now run the internal market.
                if self.global_internal_execmode != COMMON.GlobalInternalMarketMode.skip:
                    # new_orders is converted to a defaultdict after!
                    new_orders = self.internal_market.run(product, actual_orders, new_orders, current_timestamp)
                else:
                    new_orders = collections.defaultdict(list, new_orders)
                    log.info("Global internal market execution mode is set to %s", self.global_internal_execmode)
                # new_orders is now a defaultdict instead of a dict.
                # Match entry and modify orders with public orders
                new_orders = self.match_orders(new_orders, product, current_timestamp)

                # Limit the number of orders visible at the exchange
                new_orders = self._handle_exposed_order_limit(new_orders, product)

                # apply monthly action limits for trayport
                new_orders = self._handle_order_action_violations(new_orders, product.product_id)

                # Internal rejects always have to be sent, no matter what.
                self.internal_market.append_released_orders(new_orders, released_objects)

        if is_parent:
            new_orders = self._reject_orders(orders_to_check, new_orders, product)

        return new_orders

    def _handle_order_action_violations(self, new_orders, product_id):
        """On Nordpool, no order actions are enforced. Trayport and EPEX overwrite this method."""
        return new_orders

    def _handle_exposed_order_limit(self, orders_in, product):
        """
        Ensure that at most as many orders are exposed per product, market area and side, as configured.

        If a single user (autotrader) has too many orders on a single product/ market area combination, then
        this can be seen as market manipulation, as the market looks to other companies more liquid as it is (e.g.
        it looks as if a lot of companies would trade this product while in fact only one company places all the
        orders).

        For this reason, a max order limit can be configured. If this limit is set, then it is enforced in this
        function. On each combination of product, area and side, only the N best orders are allowed to go to the
        exchange, where "best" means closest to the front of the orderbook (highest buy, lowest sell). The limit only
        affects autoTRADER orders and does not include manual orders.

        Algorithm: If the limit is currently not reached, the best entry orders are allowed to go to the exchange
        until the limit is reached. The best of the remaining entry orders is then compared to the worst exposed order
        (exposed order = order currently on the exchange), the second best entry order to the second worst exposed
        order etc. If an entry order is better than an existing order, then the existing order is deleted, but the
        entry order is still discarded (it stays in the vault anyway), until the deletion is confirmed.

        :param orders_in: A dictionary where keys are from COMMON.ResolverState and values are lists of order objects
        :type orders_in: defaultdict(str, list)
        :param product: The product we are currently looking at.
        :type product: APITR.Product
        :return: A copy of orders_in with only the allowed messages and some messages converted to delete requests.
        :rtype: defaultdict(str, list)
        """
        order_limit = self._configuration.max_exposed_orders_per_side
        if not order_limit:
            return orders_in
        areas = set()
        orders_out = collections.defaultdict(list)

        # entry_orders[(side, area)] = [order,...]
        entry_orders = collections.defaultdict(list)
        # modify_orders[order.order_id] = [order, ...]
        modify_orders = collections.defaultdict(list)
        # deleted_orders = {order_id1, order_id2,...}
        delete_orders = set()
        for order in orders_in.get(COMMON.ResolverState.modify_orders, []):
            modify_orders[order.order_id].append(order)
        for order in orders_in.get(COMMON.ResolverState.entry_orders, []):
            entry_orders[(order.direction, order.delivery_area_id)].append(order)
        for order in orders_in.get(COMMON.ResolverState.delete_orders, []):
            delete_orders.add(order.order_id)

        for key in orders_in:
            if key not in (COMMON.ResolverState.modify_orders, COMMON.ResolverState.entry_orders):
                orders_out[key] = orders_in[key]
                continue
            for order in orders_in[key]:
                if UTILS.add_elem_to_set_and_confirm(order.delivery_area_id, areas):
                    for area, side in ((order.delivery_area_id, COMMON.Direction.sell),
                                       (order.delivery_area_id, COMMON.Direction.buy)):
                        self._complement_out_orders(product, area, side, entry_orders, modify_orders, delete_orders,
                                                    orders_out, order_limit)

        # Do not send modifications and delete requests of the same order.

        for order in orders_in.get(COMMON.ResolverState.modify_orders, []):
            if order.order_id not in delete_orders:
                orders_out[COMMON.ResolverState.modify_orders].append(order)
        return orders_out

    @staticmethod
    def _complement_out_orders(product, area, side, entry_orders, modify_orders, delete_orders, orders_out,
                               order_limit):
        """
        complement orders which are allowed to be sent to the exchange. Orders which are allowed at the exchange
        will be added to the orders_out dict.

        :param product: The product we are currently looking at.
        :type product: APITR.Product
        :param area: area of trading
        :type area: str
        :param side: buy or sell for the orders. Needed for sorting.
        :type side: str
        :param entry_orders: (side, area) as key with corresponding orders from COMMON.ResolverState.entry_orders
        :type entry_orders: defaultdict((str, str), list)
        :param modify_orders: order_id as key with corresponding orders from COMMON.ResolverState.modify_orders
        :type modify_orders: defaultdict(str, list)
        :param delete_orders: order_id which are marked for deletion are saved in the set
        :type delete_orders: set(str)
        :param orders_out: The dictionary with keys from COMMON.ResolverState and lists of orders as values which do
                           not violate the order_limit
        :type orders_out: defaultdict(str, list)
        :param order_limit: amount of orders allowed for each side of the orderbook
        :type order_limit: int
        """

        visible_own_orders = product.get_exposed_orders(area, side, modify_orders)
        curr_entry_orders = entry_orders[(side, area)] if (side, area) in entry_orders else []
        if curr_entry_orders:
            curr_entry_orders.sort(key=lambda o: o.price, reverse=side == COMMON.Direction.buy)
            free_slot_count = order_limit - len(visible_own_orders)
            # 1: If we still have "space" at the exchange, we allow the best entry orders to go to the exchange directly
            if free_slot_count > 0:
                orders_out[COMMON.ResolverState.entry_orders].extend(curr_entry_orders[:free_slot_count])
            if len(curr_entry_orders) > free_slot_count:
                log.debug("Limit number of exposed orders for product %s (%s), area %s, side %s:"
                          " Letting %s out of %s entry orders in to fill the limit of %s.", product.product_id,
                          product.name, area, side, min(free_slot_count, len(curr_entry_orders)),
                          len(curr_entry_orders), order_limit)
            curr_entry_orders = curr_entry_orders[free_slot_count:]

        # 2: If the remaining entry orders are better than the exposed orders, we also need to delete exposed orders.
        is_better = operator.gt if side == COMMON.Direction.buy else operator.lt
        for i, entry_order in enumerate(curr_entry_orders, start=1):
            worst_unhandled_exposed_order = None
            if i <= len(visible_own_orders):
                worst_unhandled_exposed_order = visible_own_orders[-i]
            if (worst_unhandled_exposed_order is not None
                    and is_better(entry_order.price, worst_unhandled_exposed_order.price)):
                if worst_unhandled_exposed_order.order_id in delete_orders:
                    log.debug("Limit number of exposed orders (%s) for product %s (%s), area %s, side %s:"
                              " Would delete order %s, but its deletion is already"
                              " requested.", order_limit, product.product_id, product.name, area, side,
                              worst_unhandled_exposed_order.order_id)
                else:
                    orders_out[COMMON.ResolverState.delete_orders].append(worst_unhandled_exposed_order)
                    delete_orders.add(worst_unhandled_exposed_order.order_id)
                    log.debug("Limit number of exposed orders (%s) for product %s (%s), area %s, side %s:"
                              "Request deleting of exposed order %s to make space for order %s",
                              order_limit, product.product_id, product.name, area, side,
                              worst_unhandled_exposed_order.shortstr,
                              entry_order.shortstr)
                    log.compliance_log(LOGTEMP.AutoTraderLimiter.max_exposed_order_deleted,
                                       deleted_order=LOGTEMP.get_own_order_keys(worst_unhandled_exposed_order),
                                       better_order=LOGTEMP.get_own_order_keys(entry_order),
                                       product_id=product.product_id,
                                       instrument_id=area, side=side,
                                       better_price=entry_order.price,
                                       max_exposed_order_limit=order_limit)
            else:
                log.compliance_log(LOGTEMP.AutoTraderLimiter.max_exposed_entry_denied,
                                   strategy_id=entry_order.portfolio_key,
                                   product_id=product.product_id,
                                   instrument_id=area, side=side,
                                   max_exposed_order_limit=order_limit)
        return orders_out

    @staticmethod
    def _reject_orders(orders_to_check, new_orders, product):
        """
        Reject all order modify and delete request currently not allowed by the internal market.

        If there are conflicting orders, the internal market will resolve a single conflict at a time
        and not forward any other orders to the exchange.
        Other entry orders are stored in the vault, but we have to send reject messages for all other
        orders to the children, so they can unlock the product and re-send their order-wish.

        Note: If an order_modify is converted to an order_delete, then we still reject the order modify as usual,
              which will unlock the child product. This is in line with the fact that the child's product does not get
              locked on order_delete_requests issued by the parent and requests by one child do not lock the product
              on other children.

        :param orders_to_check: The original order wishes. A dict COMMON.ResolverState-> list of orders
        :type orders_to_check: dict
        :param new_orders: The order wishes allowed by the internal market.
        :type new_orders: dict
        :param product: The product. (Internal market is run per-product)
        :return: new_orders. This is modified in-place and then returned.
        """
        order_modifies = [order for order in orders_to_check.get(COMMON.ResolverState.modify_orders, [])
                          if order.product == product]
        for order in new_orders.get(COMMON.ResolverState.internal_order_executions, []):
            if order in order_modifies:
                order_modifies.remove(order)
        for order in new_orders.get(COMMON.ResolverState.modify_orders, []):
            if order in order_modifies:
                order_modifies.remove(order)

        order_deletes = [order for order in orders_to_check.get(COMMON.ResolverState.delete_orders, [])
                         if order.product == product]
        for order in new_orders.get(COMMON.ResolverState.delete_orders, []):
            if order in order_deletes:
                order_deletes.remove(order)

        order_delete_locked_product = [order for order in
                                       orders_to_check.get(COMMON.ResolverState.delete_orders_for_locked_product, [])
                                       if order.product == product]
        for order in new_orders.get(COMMON.ResolverState.delete_orders_for_locked_product, []):
            if order in order_delete_locked_product:
                order_delete_locked_product.remove(order)
            # as the orders in "delete_orders_for_locked_product" are derived from the ones in "delete_orders",
            # we need to remove them from order_deletes list as well;
            # otherwise, the order got rejected by internal market
            if order in order_deletes:
                order_deletes.remove(order)

        reject_key = COMMON.ResolverState.internal_order_reject
        orders_to_reject = order_modifies + order_deletes + order_delete_locked_product
        orders_to_reject += orders_to_check.get(reject_key, [])

        if orders_to_reject:
            new_orders[reject_key] = orders_to_reject

        return new_orders

    @staticmethod
    def _get_actual_orders(product, current_timestamp):
        """
        Get all own orders from the order book for this product,
        which have to be taken into account for the internal market.

        :param product: The product for which we want the orders
        :type product: APITR.Product
        :type current_timestamp: float
        """
        own_orders = product.orders.get(order_filter=COMMON.OrderFilter.own)
        actual_orders = []
        for order in own_orders:
            # If order state is HIBE (i.e. hibernated) and autotrader did not hibernate it
            # (by setting "reac" flag in order tags), we ignore the order by removing it from
            # the old_orders list we send to the internal market.
            # This also removes own hibernated orders
            if order.state == COMMON.OrderState.hibe and not getattr(order, "reactivate", None):
                continue
            actual_orders.append(order)

        return actual_orders

    def _lock_orders(self, new_orders, orders_to_send, product, current_timestamp, is_parent):
        """
        Add orders from new_orders to orders_to_send and update locks and vault accordingly.

        This function locks the product based on the orders that get sent to the exchange. We lock the order-lock
        with the internal_id of the order once for each execution message that we expect
        (except for entry orders on the child process)

        Orders that go to the exchange are removed from the vault.

        :param new_orders: The orders that should now be added to orders_to_send. We lock based on these orders.
        :type new_orders: dict
        :param orders_to_send: The orders that will be sent to the exchange. We add the orders to this dictionary
                               (it is modified in-place), and return a reference to it.
        :type orders_to_send: defaultdict(list)
        :param product: The product which the new_orders correspond to.
        :type product: autotrader_core.exchange_trading.Product
        :type current_timestamp: float or int
        :type is_parent: bool
        :return: A reference to orders_to_send
        :rtype: defaultdict(list)
        """
        locks_updated = False
        for order_type, orders in new_orders.items():
            orders_to_send[order_type].extend(orders)
            if order_type == COMMON.ResolverState.internal_order_executions:
                # Orders that have been traded internally, are removed from the vault.
                for order in orders:
                    self._vault.modify(order["internal_id"], COMMON.InstanceLockState.confirm_all,
                                       current_timestamp)
            if (order_type == COMMON.ResolverState.delete_orders_for_locked_product
                    or order_type in COMMON.ResolverState.internal_messages):
                # We lock the product for all messages sent to the exchange/ the parent, where we expect an execution.
                # As internal messages are not sent to the exchange, we do not expect an execution.
                # For the delete_orders_for_locked_product, we do not lock the product, as we might send this message
                # multiple times but expect only one execution message
                continue
            # Lock orders to be modified
            # for entry orders add them to the product
            for order in orders:
                locks_updated = True
                if order_type == COMMON.ResolverState.entry_orders:
                    # If the order is sent to the exchange, remove it from the vault.
                    self._vault.modify(order.internal_id, COMMON.InstanceLockState.confirm_all,
                                       current_timestamp)
                    product.orders.add_own_order(order)

                if order_type == COMMON.ResolverState.trade_orders:
                    # we don't lock the product if the order is a comtrader order
                    # for a trade order it most likely is not a comtrader order but we check just in case.
                    if not product.orders.is_com_trader_order(order.order_id, order.broker_id):
                        internal_id = order.tags.get("internal_id")
                        if internal_id:
                            if order.broker_id in self.brokers_with_multimatching_lock_release:
                                # This is in a separate decision since we don't want the else branch to trigger for this
                                if product.trade_lock.handle_multimatching_add_lock(internal_id,
                                                                                    order.quantity):
                                    product.trade_lock.add(internal_id, current_timestamp,
                                                           quantity=order.quantity)
                            else:
                                product.trade_lock.add(internal_id, current_timestamp)
                        else:
                            log.warning("Can't find internal_id in tags for the order: {}".format(order))

                    break
                else:
                    # Validate order type
                    order.validate()
                    # On the child process, we don't lock the product on entry orders.
                    # We have "Unconfirmed Order Blocks..." That is enough.
                    # Otherwise we would lock the product while an order is in the vault, which we do not want,
                    # as it would break the internal market and the max exposed orders limit.
                    # On the parent, we still lock on entry orders,
                    # but only AFTER they go out from the vault and to the exchange.
                    if is_parent or order_type != COMMON.ResolverState.entry_orders:
                        product.order_lock.add(order.internal_id, current_timestamp)
                    else:
                        # for entry orders in the child we can't rely on the lock if we want the order to be
                        # cleaned up from the product's order book, so we register it as an order with timeout
                        self.orders_with_timeout[order.product].append((order.internal_id, current_timestamp))
                    if order.execution_restriction in [COMMON.ExecutionRestriction.ioc,
                                                       COMMON.ExecutionRestriction.fok]:
                        # FOK and IOC orders are deleted immediately after creation on the exchange.
                        # If something goes wrong and we do not receive the "delete" execution restriction,
                        # Then we clean-up these orders after a timeout.
                        self.orders_with_timeout[order.product].append((order.internal_id, current_timestamp))

                    if order_type in (COMMON.ResolverState.modify_orders, COMMON.ResolverState.activate_orders):
                        # If the order is to be modified, we add one more order lock as we expect UDEL and UADD
                        # order execution messages
                        order.product.order_lock.add(order.internal_id, current_timestamp)
        if locks_updated:
            product.update_db(current_timestamp)
        return orders_to_send

    def match_orders(self, orders_to_send, unused_product, unused_current_timestamp=None):
        return orders_to_send

    def order_modify_chunking(self, orders, message_type):
        """Get the right parameters for the orders and prepare dict structures to sendnull them

        :type orders: list[APITR.Order]
        :type message_type: str
        :rtype: list[dict]
        """
        raise NotImplementedError

    def trade_order_chunking(self, orders):
        return []

    def remove_old_products(self):
        trading_start_dt = datetime.datetime.combine((datetime.datetime.today() - datetime.timedelta(days=1)),
                                                     datetime.time(10))
        trading_start = ALU.convert_dt_to_timestamp(trading_start_dt)
        for product_id in list(self.products._products.keys()):
            # dummy products will be removed because of their trading_phase
            # that starts and ends at timestamp 0
            if self.products._products[product_id].delivery_end < trading_start:
                del self.products._products[product_id]
        # Remove products from the products_by_delivery dict
        for del_span in list(self.products._products_by_delivery.keys()):
            if del_span[1] < trading_start:
                del self.products._products_by_delivery[del_span]

        log.debug("remove old products for '%s' completed", self.internal_id)

    def _iter_expired_products(self, timestamp):
        """
        Iter over all products for which trading is no longer possible.

        For these products, we can clear-out the orderbook.

        :param timestamp: The current timestamp of autotrader (real time or simulation time)
        :type timestamp: float
        """

        # This is implemented on the exchange class, not the product list, because it has exchange-specific subclasses
        # Get all products which expired recently, so we can delete the orderbook.
        # By using COMMON.ORDERBOOK_CLEANUP_INTERVAL * 2, we ensure that this is run at least once per product.
        # As an extra security, we keep the orderbook data at least 15 minutes after delivery start.
        # This way, aftermarket products have time to become active before we start the clean-up.
        for product in self.products.get_overlapping_with_timerange(
                timestamp - COMMON.ORDERBOOK_CLEANUP_INTERVAL * 2 - COMMON.QUARTER,
                timestamp - COMMON.QUARTER):
            assert timestamp >= product.delivery_start  # For explicity, implied by get_overlapping_with_timerange
            # If the product type contains after market, we do not clean the product.
            # This is the case for After_Market_Quarter_Hour_Power_BE, After_Market_Quarter_Hour_Power_NL,
            # After_Market_Quarter_Hour_Power_BE and After_Market_Quarter_Hour_Power_NL on EPEX
            if "After_Market" in product.product_type:
                log.debug("Not cleaning orderbook of product %s (%s), because its type is %s",
                          product.product_id, product.name, product.product_type)
                continue
            # In case the check for the product type failed (because an exchange introduces new product types which we
            # we were not aware of) then we may also detect after market products based on the delivery phase.
            if any(state == COMMON.DeliveryAreaState.active for state in product.delivery_area_states.values()):
                log.debug("Not cleaning orderbook of product %s (%s), because it is still active after delivery start",
                          product.product_id, product.name)
                continue
            yield product

    def remove_old_orderbook(self, timestamp):
        """
        Internal method used to delete orderbook information from products that have already started delivery.

        The OrderBook contains quite a lot of data (indicators, orders and bookkeeping data) that is no longer
        needed when the product has started delivery.

        :param timestamp: The current timestamp
        :type timestamp: float
        :rtype: None
        :meta private:
        """
        for product in self._iter_expired_products(timestamp):
            product.reset_orderbook()

    def update_market_halt(self, market_halt):
        """
        Extract and store the market halt information from a timeseries.

        This overwrites any market halt information stored previously

        :param market_halt: A list of dicts with the keys 'begin', 'end' and 'value', where 0 and everything below
                            indicates a market halt.
        :type market_halt: list
        :return: None
        """
        self.market_halt_set = []
        for halt in sorted(market_halt, key=lambda halt: halt["begin"]):
            if halt["value"] is not None and halt["value"] <= 0.:
                if not self.market_halt_set or halt["begin"] > self.market_halt_set[-1][1]:
                    # new item
                    self.market_halt_set.append((halt["begin"], halt["end"]))
                else:
                    self.market_halt_set[-1] = (self.market_halt_set[-1][0], halt["end"])

    def update_from_json(self, struct, current_timestamp):
        """Main Callback to update exchange state based on messages

        :type struct: dict
        :type current_timestamp: float
        :rtype: dict
        """
        self.last_incoming_message_timestamp = current_timestamp

        if not self.allowed:
            return {}

        if struct["message_type"] == COMMON.Response.market_state:
            data = struct["data"]
            if (self._market_state_revision is None) or (data["revision"] > self._market_state_revision):
                self._market_state_revision = data["revision"]
                if self.market_state == COMMON.MarketState.hibernated and data["state"] == COMMON.MarketState.active:
                    # Restart AutoTrader completely after market start
                    log.warning("restarting autotrader due to market activation")
                    raise COMMON.RestartExchangeException(self.internal_id)
                self.market_state = data["state"]
        elif struct["message_type"] == COMMON.Response.error_response:
            if not self.handle_error_response(struct, current_timestamp):
                new_entry = (struct.get("timestamp", -1.0),
                             [error.get("error_message", "") for error in struct.get("data", [])])
                self.error_queue.append(new_entry)
                for error in struct["data"]:
                    text = error["error_message"]
                    error_msg = error.get("error_msg", "")
                    if error_msg:
                        text += " | {}".format(error_msg)
                    PERSIST.MongoDBConnector().update_db_global_log(
                        is_error=True,
                        domain="exchange",
                        domain_key=self.internal_id.lower(),
                        domain_caption=self.internal_id,
                        text=text,
                        data_object=[],
                        timestamp=struct["timestamp"])

                log.warning("Received Error Response from exchange (check persistence for details): "
                            "ts:{} error_message:({!r})".format(struct["timestamp"], struct["data"]))
            return {"on_error": struct["data"]}

        elif struct["message_type"] == COMMON.Response.internal_order_reject:
            for entry in struct["data"]:
                product = self.products.get_by_id(entry["product_id"])
                product.order_lock.modify(entry["internal_id"], COMMON.InstanceLockState.confirm_all, current_timestamp)
                if entry["reason"]:
                    log.debug("Modification of order %s (of strategy %s) was rejected with reason %s",
                              entry["internal_id"], entry["portfolio_key"], entry["reason"])
            return {"on_internal_order_reject": struct["data"]}

        elif struct["message_type"] == COMMON.Response.internal_trade_lock:
            for entry in struct["data"]:
                product = self.products.get_by_id(entry["product_id"])
                # here we keep order_id as the name comes from api.send_to_exchange
                if entry.get("order_id"):
                    if entry.get("broker_id") in self.brokers_with_multimatching_lock_release:
                        if product.trade_lock.handle_multimatching_add_lock(entry["order_id"], entry.get("quantity")):
                            product.trade_lock.add(entry["order_id"], entry["timestamp"],
                                                   quantity=entry.get("quantity"))
                    else:
                        product.trade_lock.add(entry["order_id"], entry["timestamp"])
                else:
                    log.warning("Tried to add None as lock id : {}".format(entry))
            return {}

        elif "trade" in struct["message_type"]:
            return self.update_from_json_on_trade(struct, current_timestamp)

        elif "order" in struct["message_type"]:
            return self.update_from_json_on_order(struct, current_timestamp)

        elif struct["message_type"] == COMMON.Response.product:
            modified_products = self.products.update_from_json(struct, current_timestamp)
            return {"on_products_update": modified_products}

        elif struct["message_type"] == COMMON.Response.capacities:
            modified_capacities = self.capacities.update_from_json(struct, current_timestamp)
            return {"on_products_update": modified_capacities}

        elif struct["message_type"] == COMMON.TrayportResponse.routes:
            route = struct.get("default_route")
            if route is not None:
                self.internal_market.set_route(route)
            if struct["data"]:
                self.routes = struct["data"]

        return {}

    def update_from_json_on_trade(self, struct, current_timestamp):
        modified_trades, unused_del_areas = self.products.update_from_json(
            struct, current_timestamp, autotrader_user=self.autotrader_user)
        modified_products = set()
        callback_name = "on_public_trade_update"

        if struct["message_type"] in (COMMON.Response.own_trade, COMMON.Response.internal_trade):
            for trade in modified_trades:
                modified_products.add(trade.product)
                if self._validate_trade(trade, current_timestamp):
                    lock_field = "order_id" if struct["exchange"] != COMMON.Exchange.trayport else "order_internal_id"
                    lock_id = getattr(trade, lock_field)
                    if not lock_id:
                        log.info("We would unlock the trade lock with None on trade %s and product %s (%s). "
                                 "Not unlocking it.", trade.trade_id, trade.product.name, trade.product.product_id)
                    else:
                        if (trade.aggressor_broker_id not in self.brokers_with_multimatching_lock_release
                                or trade.product.trade_lock.handle_multimatching_modify_lock(lock_id, trade.quantity)):
                            trade.product.trade_lock.modify(lock_id, COMMON.InstanceLockState.confirm_one,
                                                            current_timestamp, quantity=trade.quantity)

            callback_name = "on_trade_update"
            for product in modified_products:
                product.update_db(current_timestamp)
        return {callback_name: modified_trades}

    def _validate_trade(self, trade, unused_current_timestamp):
        """Validate trade received from the exchange

        Implement exchange-specific trade validation in the corresponding exchange class.

        Returns True if the trade should modify the execution lock.

        :param trade: trade object to be validated
        :type trade: :class:`APITR.OwnTrade`
        :param unused_current_timestamp: timestamp
        :type unused_current_timestamp: float
        :returns: returns True to indicate that trade is valid
        :rtype: bool
        """
        # for internal trades, ignore modification of the trade lock, if trades were made with ComTraderOder.
        # This will avoid 10s lock on trade with COMMON.InstanceLockState.added_negative and
        # allow the internal market to react immediately right after the ComTraderOrder execution is received
        # and order_lock is freed.
        com_trader_order = trade.product.orders.is_com_trader_order(trade.order_id)
        return not (trade.trade_id.startswith("internal") and com_trader_order)

    def update_from_json_on_order(self, struct, current_timestamp, confirm_lock=None):
        """
        To handle orderbook update json messages
        :type struct: dict
        :type current_timestamp: float
        :type confirm_lock: str
        :return: list of modified orders under the key of on_order_book_update key in a dictionary
        :rtype: dict
        """
        modified_orders, unused_del_areas = self.products.update_from_json(
            struct, current_timestamp, autotrader_user=self.autotrader_user,
            combined_brokers=self.combined_order_brokers, confirm_lock=confirm_lock,
            multimatching_trade_lock_brokers=self.brokers_with_multimatching_lock_release)
        return {"on_order_book_update": modified_orders}

    def remove_old_ioc_orders(self, timestamp):
        pass

    def handle_error_response(self, struct, current_timestamp):
        """
        Handle an error response from the exchange, or return False if it cannot be handled.

        :param struct: The message with struct["message_type"] == COMMON.Response.error_response
        :type struct: dict
        :param current_timestamp: The current autoTRADER timestamp
        :type current_timestamp: float or int
        :return: True, if the error has been fully handled (=> No warning log message needed,
                 no need to store it in persistence), False, otherwise
        :rtype: bool
        """
        return False

    def serialize_market_state(self):
        # type: () -> dict
        message = {"exchange": COMMON.Exchange.autotrader,
                   "timestamp": int(time.time()),
                   "message_type": COMMON.Response.market_state,
                   "data": {"state": self.market_state}}
        return message

    def start_exchange(self, timestamp=None, username=COMMON.PeriotheusSystemUsers.system):
        """
        Unhalt the exchange

        :param timestamp: The current timestamp (used for updating the database)
        :type timestamp: int
        :param username: The user who unhalts the exchange. Used for compliance logging
        :type username: str
        """
        history_fields = []
        if self.halted:
            history_fields.extend(["halted", "critical_exchange_halt"])

        self.halted = False
        self.halt_reason = ""
        self.remove_orders = True
        if timestamp is None:
            timestamp = time.time()
        self.critical_exchange_halt = False
        self.update_db(timestamp, history_fields=history_fields)
        log.warning(U"Start %s exchange", self.caption)
        log.compliance_log(log_entry=LOGTEMP.AutoTraderBasic.exchange_started,
                           exchange_name=self.internal_id, username=username)

    def _pre_send(self, struct, properties):
        """ Overwrite this function if there should be some processing before send_func."""
        pass

    def _post_send(self, struct, properties):
        """ Overwrite this function if there should be some processing after send_func."""
        pass

    def send(self, struct, properties=None):
        """Sends a message to the exchange using exchange.send_func.

        Will call exchange._pre_send before sending to the exchange.
        Will call exchange._post_send after sending to the exchange.
        """
        if properties is None:
            properties = dict()
        self._pre_send(struct, properties)
        self.send_func(struct, properties)
        self._post_send(struct, properties)

    def __str__(self):
        return "{} (class name: {})".format(self.internal_id, self.__class__.__name__)


class Epex(ExchangeBase):
    OMT_REFRESH_RATE = 4
    OMT_RELEVANT_MESSAGES = [COMMON.Request.order_delete_all, COMMON.Request.order_activate_all,
                             COMMON.Request.order_deactivate_all, COMMON.Request.order_modify,
                             COMMON.Request.order_activate, COMMON.Request.order_delete,
                             COMMON.Request.order_deactivate, COMMON.Request.order_entry]

    def __init__(self, send_func, create_dummy_products, allowed, exchange_config, indicator_update=True,
                 is_parent=True):
        # type: (callable, bool, bool, ATCONF.EpexConfig, bool, bool) -> None
        handler_dict = {
            COMMON.ThrottlingState.BLOCKING: self.omt_internal_blocking_handler,
            COMMON.EpexOMTState.RESTRICTED: self.omt_restricted_handler,
            COMMON.EpexOMTState.NO_RESTRICTION: self.omt_no_restriction_handler,
        }
        self.next_omt_request = None

        self.throttling_enabled = exchange_config.enable_throttling
        self._short_omt = ERL.ShortOMTManager(exchange_config.short_throttling_limit, handler_dict)
        self._long_omt = ERL.LongOMTManager(exchange_config.long_throttling_limit, handler_dict)
        super(Epex, self).__init__(COMMON.Exchange.epex, send_func, create_dummy_products,
                                   allowed, exchange_config, COMMON.ORDER_LOCK_TIMEOUT,
                                   indicator_update=indicator_update, is_parent=is_parent)
        self.market_halt_set = set()  # 15Minutes Blocks with halt

        self.max_orders = 1
        self.allowed_products = {"local": exchange_config.local_products,
                                 "xbid": exchange_config.xbid_products,
                                 "uk": exchange_config.uk_products,
                                 "half_hour_products": exchange_config.half_hour_products,
                                 "quarter_hour_products": exchange_config.quarter_hour_products}

        self._message_report_handler = {
            COMMON.EpexMessageCodes.throttling: self._handle_omt_throttling_status_changed,
            COMMON.EpexMessageCodes.no_throttling: self._handle_omt_throttling_status_changed,
        }

    def omt_internal_blocking_handler(self, omt, **_):  # type: (ERL.OMTManager, dict[str, any]) -> None
        """Called when the internal OMT state changes to BLOCKING"""
        if self.throttling_enabled:
            log.warning("Reached {} state for {} OMT, sending delete all orders request."
                        "".format(COMMON.ThrottlingState.BLOCKING, omt.parameters.limit_type))
            self.send(self.delete_all_orders())

    def omt_no_restriction_handler(self, omt, **_):  # type: (ERL.OMTManager, dict[str, any]) -> None
        """Called when the OMT state changes to NO_RESTRICTION"""
        if omt.epex_state.previous == COMMON.EpexOMTState.RESTRICTED:
            log.info("Recovered from {} state for {} OMT, deleting all orders before proceeding."
                     "".format(COMMON.EpexOMTState.RESTRICTED, omt.parameters.limit_type))
            self.send(self.delete_all_orders())

    def omt_restricted_handler(self, omt, **_):  # type: (ERL.OMTManager, dict[str, any]) -> None
        """Called when the OMT state changes to RESTRICTED"""
        log.warning("Reached {} state for {} OMT, all orders should be hibernated by EPEX."
                    "".format(COMMON.EpexOMTState.RESTRICTED, omt.parameters.limit_type))

    @property
    def short_omt(self):
        """ Get the OMT parameters of the short observation period

        :return: OMT parameters
        :rtype: ALU.OMTParameters
        """
        return self._short_omt.parameters

    @property
    def long_omt(self):
        """ Get the OMT parameters of the long observation period

        :return: OMT parameters
        :rtype: ALU.OMTParameters
        """
        return self._long_omt.parameters

    def get_relevant_omt(self):
        """Gets OMT manager for the omt which is currently closest to its threshold.

        :rtype: ALU.OMTParameters
        """
        if self.short_omt.l1_percent > self.long_omt.l1_percent:
            return self.short_omt
        else:
            return self.long_omt

    def _load_omt(self, short_dict, long_dict, persist, current_time):
        """Updates the short and long OMT objects with the given dicts.

        If persist is true, saves the updated objects to mongo.
        """
        if isinstance(short_dict, dict):
            self._short_omt.from_dict(short_dict, current_time)
        if isinstance(long_dict, dict):
            self._long_omt.from_dict(long_dict, current_time)
        if persist:
            PERSIST.MongoDBConnector().update_db_rate_limit(self._short_omt.to_dict(True), COMMON.Exchange.epex)
            PERSIST.MongoDBConnector().update_db_rate_limit(self._long_omt.to_dict(True), COMMON.Exchange.epex)
        log.debug("OMT loaded: short %s; long %s", self._short_omt.to_json(True), self._long_omt.to_json(True))

    def _increment_omt(self, message_type, current_time, n=1):
        """Increments the short and long OMTs.
        :type current_time: float
        """
        if n == 0:
            log.debug("OMT wanted to increment due to {}, but received value 0.".format(message_type))
            return
        self._short_omt.increment(current_time, n)
        self._long_omt.increment(current_time, n)
        PERSIST.MongoDBConnector().update_db_rate_limit(self._short_omt.to_dict(True), COMMON.Exchange.epex)
        PERSIST.MongoDBConnector().update_db_rate_limit(self._long_omt.to_dict(True), COMMON.Exchange.epex)
        log.debug("OMT incremented triggered by %s: short %s; long %s", message_type, self._short_omt.to_json(),
                  self._long_omt.to_json())

    def update_current_omt(self, current_time):  # type: (float) -> None
        """Decays buckets and updates both long and short OMT levels and states."""
        self._short_omt.update_current_omt(current_time)
        self._long_omt.update_current_omt(current_time)

    def _pre_send(self, struct, properties):
        """Add data to correlation-id before sending the message."""
        if (struct.get("message_type") in self.OMT_RELEVANT_MESSAGES):
            omt_prop = Epex.add_omt_message_property(struct)
            properties["correlation_id"] = ALU.append_correlation_id_data(properties.get("correlation_id"), omt_prop)
        # add an uuid to the correlation-id, helpful for tracing messages in logs
        properties["correlation_id"] = ALU.append_correlation_id_data(properties.get("correlation_id"),
                                                                      str(uuid.uuid1())[:8])

    @staticmethod
    def add_omt_message_property(struct):
        """Generates the omt correlation-id string, so OMT can be incremented with ack-messages."""
        # Explicitly check for modify all orders requests (in case data changes for those)
        message_type = struct.get("message_type")
        if message_type in [COMMON.Request.order_activate_all, COMMON.Request.order_deactivate_all,
                            COMMON.Request.order_delete_all] or not isinstance(struct.get("data"), list):
            msg_count = 1
        else:
            msg_count = len(struct["data"])
        return "omt.{}.{}".format(message_type, msg_count)

    def _handle_order_action_violations(self, new_orders, _):
        # type: (collections.defaultdict[str, list[APITR.OwnOrder]], any) -> collections.defaultdict
        """Prevent order modifying requests when short or long OMT is in WARNING or RESTRICTED mode."""
        if (not self.throttling_enabled
                or (self._short_omt.autotrader_state.current == COMMON.ThrottlingState.NON_BLOCKING
                    and self._long_omt.autotrader_state.current == COMMON.ThrottlingState.NON_BLOCKING)):
            return new_orders

        # OMT breached:
        placing_strategies = set()
        for order_type, order_type_list in new_orders.items():
            if order_type in COMMON.ResolverState.internal_messages:
                continue
            for order in order_type_list:
                if order.portfolio_key not in placing_strategies:
                    log.warning("Strategy {} tried to send {} ({}) although OMT is breached (Short: {}, Long: {})."
                                "".format(order.portfolio_key, order_type, order.shortstr, self._short_omt.to_json(),
                                          self._long_omt.to_json()))
                    log.compliance_log(LOGTEMP.AutoTraderLimiter.omt_state_warning, strategy=order.portfolio_key,
                                       short_state=self.short_omt.status, long_state=self.long_omt.status)
                    placing_strategies.add(order.portfolio_key)
        return collections.defaultdict(list)

    def _handle_omt_throttling_status_changed(self, message_dict, current_time):
        # type: (dict[str, any], float) -> None
        """Handles throttling status changed messages from the message report message-type"""
        log.debug("Received throttling state changed message: %s", message_dict["txt"])
        msg_var = message_dict["vars"]  # type: dict[str, str]

        new_state = msg_var[COMMON.EpexVars.omt_status_general]
        short_state, short_ts = ERL.OMTManager.parse_status_update(
            msg_var.get(COMMON.EpexVars.omt_short_info), new_state)
        long_state, long_ts = ERL.OMTManager.parse_status_update(
            msg_var.get(COMMON.EpexVars.omt_long_info), new_state)

        self._short_omt._evaluate_epex_state(current_time, short_state, omt_timestamp=short_ts)
        self._long_omt._evaluate_epex_state(current_time, long_state, omt_timestamp=long_ts)

    def _handle_omt_from_correlation_id(self, struct):
        """Evaluates an ack message to increment OMTs accordingly

        :param struct: message struct
        :type struct: dict
        """
        omt_corr_id = ALU.extract_data_from_correlation_id(struct, "omt")
        if omt_corr_id:
            log.debug('Extracting OMT Info from message: %s', struct.get("correlation_id"))
            _, message_type, amount = omt_corr_id.split('.')
            self._increment_omt(message_type, struct["timestamp"], int(amount))
        else:
            # even without omt relevant messages from exchange, continue with decaying the values
            self.update_current_omt(struct["timestamp"])

    def _handle_message_report(self, struct):  # type: (dict[str, any]) -> None
        """Handles message report messages and forwards the messages to the correct handlers"""
        current_time = struct.get("timestamp", time.time())
        for msg in struct.get("data", []):
            message_code = msg.get("code", "")
            handler = self._message_report_handler.get(message_code)
            if handler is None:
                log.info("Can't handle message from message report: %s", struct)
            else:
                handler(msg, current_time)

    def remove_old_ioc_orders(self, timestamp):
        for delivery_area_id in COMMON.Area.get_all():
            for product in self.products.get_active_products(delivery_area_id):
                product.orders.remove_ioc_orders_created_before(timestamp)

    def order_modify_chunking(self, orders, message_type):
        structures = []
        if message_type == COMMON.TrayportRequest.trade_order:
            return []
        elif message_type == COMMON.Request.order_entry:
            get_data_func = "_get_order_entry_params"
        elif message_type == COMMON.Request.order_delete_all:
            return [self.delete_all_orders()]
        else:
            get_data_func = "_get_order_modify_params"

        for ind in range(0, len(orders), self.max_orders):
            structure = {
                "exchange": COMMON.Exchange.epex,
                "message_type": message_type,
                "timestamp": int(time.time()),
                "data": []
            }
            for order in orders[ind:ind + self.max_orders]:
                order_data = getattr(order, get_data_func)()
                structure["data"].append(order_data)
            structures.append(structure)
        return structures

    def serialize_market_state(self):
        # type: () -> dict
        message = {"exchange": COMMON.Exchange.autotrader,
                   "timestamp": int(time.time()),
                   "message_type": COMMON.Response.market_state,
                   "data": {"state": self.market_state}}
        return message

    def delete_orders(self, orders):
        return self.order_modify_chunking(orders, COMMON.Request.order_delete)

    def deactivate_orders(self, orders):
        return self.order_modify_chunking(orders, COMMON.Request.order_deactivate)

    def activate_orders(self, orders):
        return self.order_modify_chunking(orders, COMMON.Request.order_activate)

    def recall_trade(self, trade):
        return {
            "exchange": COMMON.Exchange.epex,
            "message_type": COMMON.Request.trade_recall,
            "timestamp": int(time.time()),
            "data": {"trade_id": trade.trade_id,
                     "revision": trade.revision}
        }

    def deactivate_all_orders(self):
        return {"exchange": COMMON.Exchange.epex,
                "timestamp": int(time.time()),
                "message_type": COMMON.Request.order_deactivate_all,
                "data": None}

    def activate_all_orders(self):
        return {"exchange": COMMON.Exchange.epex,
                "timestamp": int(time.time()),
                "message_type": COMMON.Request.order_activate_all,
                "data": None}

    def request_market_state_info(self):
        return {"exchange": COMMON.Exchange.epex,
                "timestamp": int(time.time()),
                "message_type": COMMON.Request.market_state,
                "data": None}

    def request_product_infos(self, start, end):
        return {"exchange": COMMON.Exchange.epex,
                "timestamp": int(time.time()),
                "message_type": COMMON.Request.product,
                "data": {"start": start,
                         "end": end}}

    def request_public_order_book_info(self):
        return {"exchange": COMMON.Exchange.epex,
                "timestamp": int(time.time()),
                "message_type": COMMON.Request.order_book,
                "data": {"local": self.allowed_products["local"],
                         "xbid": self.allowed_products["xbid"],
                         "uk": self.allowed_products["uk"],
                         "half_hour_products": self.allowed_products["half_hour_products"],
                         "quarter_hour_products": self.allowed_products["quarter_hour_products"]}}

    def request_public_trade_confirmations(self, start, end):
        return {"exchange": COMMON.Exchange.epex,
                "timestamp": int(time.time()),
                "message_type": COMMON.Request.public_trade,
                "data": {"start": start,
                         "end": end}}

    def request_system_info(self):
        return {"exchange": "EPEX",
                "timestamp": int(time.time()),
                "message_type": COMMON.EpexRequest.system_info}

    def request_omt_status(self):
        """Returns the message_struct for a omt status request."""
        return {"exchange": COMMON.Exchange.epex,
                "timestamp": int(time.time()),
                "message_type": COMMON.EpexRequest.omt_status}

    def send_omt_status_request(self, current_time):
        """Sends an omt status request to the exchange, if enough time has passed."""
        if self.next_omt_request is not None and current_time >= self.next_omt_request:
            self.send(self.request_omt_status())
            self.next_omt_request = current_time + Epex.OMT_REFRESH_RATE
            log.debug("Next OMT request: %s", ERL.ts_to_isoformat(self.next_omt_request))

    def _load_from_db(self, current_time):
        """Read the OMT parameters and state from mongo."""
        super(Epex, self)._load_from_db()
        omt_short = PERSIST.MongoDBConnector().load_db_rate_limit(COMMON.RateLimitType.Epex.short, COMMON.Exchange.epex)
        omt_long = PERSIST.MongoDBConnector().load_db_rate_limit(COMMON.RateLimitType.Epex.long, COMMON.Exchange.epex)
        log.debug("Read OMT status from mongo: short: %s; long: %s", omt_short, omt_long)
        self._load_omt(omt_short, omt_long, persist=False, current_time=current_time)

    def initialize(self):
        if not self.allowed:
            return

        PERSIST.MongoDBConnector().close_all_orders(self.internal_id)

        # Let's go 10 minutes into the future to have buffer for the time we need to send the message
        now = datetime.datetime.now() + datetime.timedelta(minutes=10)
        today_start = datetime.datetime.combine(now, datetime.time.min)
        yesterday_start = today_start - datetime.timedelta(days=1)
        tomorrow_start = today_start + datetime.timedelta(days=1)
        day_after_tomorrow_start = tomorrow_start + datetime.timedelta(days=1)

        initialization_messages = [

            # Send a delete_all_request here in addition to the one we send before restarting the exchange
            # to be on the safe side.
            # If we start up autoTRADER after a crash/ downtime, the earlier delete_all request does not go through
            # because it would still belong to a NullExchange.
            self.delete_all_orders(),

            self.request_omt_status(),
            self.request_market_state_info(),
            self.request_private_order_book_info(),
            self.request_product_infos(yesterday_start, today_start),
            self.request_product_infos(tomorrow_start, day_after_tomorrow_start),
            self.request_product_infos(today_start, tomorrow_start),
            self.request_public_order_book_info(),
            self.request_system_info()
        ]

        date_end = now
        date_start = date_end - datetime.timedelta(hours=6)
        while date_end > yesterday_start:
            initialization_messages.append(self.request_trade_captures(date_start, date_end))
            initialization_messages.append(self.request_public_trade_confirmations(date_start, date_end))
            date_end = date_start
            # So the max time span (7) will not be breached in fall time change
            date_start = date_start - datetime.timedelta(hours=6)
        self.next_omt_request = time.time() + Epex.OMT_REFRESH_RATE
        log.debug("Next OMT request: %s", ERL.ts_to_isoformat(self.next_omt_request))
        for message_body in initialization_messages:
            self._send_init_file(message_body, COMMON.InitCorrelationIds.epex_init)

    def update_from_json(self, struct, current_timestamp):
        """Handle special case specific for epex such as system_info. For others refer to base class

        :type struct: dict
        :type current_timestamp: float
        :rtype: dict
        """
        if struct["message_type"] == COMMON.EpexResponse.message_report:
            self._handle_message_report(struct)
        elif struct["message_type"] == COMMON.EpexResponse.omt_status:
            self._load_omt(struct["data"].get("short"), struct["data"].get("long"), True, current_timestamp)
        elif struct["message_type"] == COMMON.Response.ack_response:
            if "timestamp" not in struct:
                struct["timestamp"] = current_timestamp
            self._handle_omt_from_correlation_id(struct)
        elif struct["message_type"] == COMMON.EpexResponse.system_info:
            self.max_orders = int(struct["data"]["max_orders"])
        else:
            return super(Epex, self).update_from_json(struct, current_timestamp)
        return {}

    def handle_error_response(self, struct, current_timestamp):
        """ Handle error responses, sent by EPEX. There are three types of error messages we differentiate between.
        1)  for OMT messages, there is special handling - the corresponding function is called and the error is then
        considered handled.
        2) for concurrent order update and order not found errors, we do not remove the OwnOrder from the product's
        orderbook, but we DO remove the order_lock, to allow a (possibly running) SO to remove the resting order
        from the market. Also, as EPEX provides a bit more information in these error messages, it is possible to handle
        them, even if the internal_id and product_id fields are missing in the error response.
        3) for all other errors, we remove the order_lock and remove the OwnOrder from the product's orderbook, if
        the order is being inserted, i.e. it does not have an order_id yet, to avoid filling the orderbook with
        OwnOrders on faulty slot entry.

        We do not need to specifically check whether the error message is in response to an order
        entry/modification/deletion request, as we obtain the necessary information to perform the handling,
        by checking for the internal_id and product_id fields, which autoTRADER provides to EPEX in the
        client_order_id field of the order entry/modification/deletion request. I.e. any other error type would not
        have these fields, and we would not be able to handle it (which is desired, as the current handling only
        concerns itself with orders).

        :param struct: The message with struct["message_type"] == COMMON.Response.error_response
        :type struct: dict
        :param current_timestamp: The current autoTRADER timestamp
        :type current_timestamp: float or int
        :return: True, if all errors have been fully handled (=> No warning log message needed,
                 no need to store it in persistence),
                 False, otherwise (esp. also in case the exchange is not initialized yet).
        :rtype: bool
        """
        if not self.init_files_ready():
            log.info("Received error response, but no special handling is needed, because EPEX is not initialized")
            return False
        handled = 0
        for line in struct["data"]:
            error_code = line.get("error_code", "")
            error_message = line.get("error_message", "")

            # OMT error
            if "exceeded throttling limit" in line.get("error_message", ""):
                log.debug("Received IgnoredRestrictedOMT error message: %s", struct)
                # This error message contains the correlation-id of the request that triggered it
                self._handle_omt_from_correlation_id(struct)
                handled += 1
                continue

            try:
                product, internal_id = self._get_internal_id_and_product(line, error_code)
            except (COMMON.OrderNotFound, COMMON.ProductNotFound) as exception:
                log.warning("Cannot handle error response, due to: {reason}. Error response: {resp}"
                            .format(reason=exception, resp=line))
                continue
            # we need the product_id in the SO error handling, so we add it here,
            # if it was missing in the error response message
            if not line.get("product_id"):
                line["product_id"] = product.product_id

            if product and internal_id and (internal_id in product.order_lock):
                log.debug("Removing %s from order lock of product %s on error response with code %s and message '%s'",
                          internal_id, product.product_id, error_code, error_message)

                # we need to extract the portfolio_key and the so_instance_name (if applicable), as there is no way
                # to obtain that information in the synthetic order strategy error handling
                internal_order = None
                own_orders = product.orders.get(order_filter=COMMON.OrderFilter.own)
                for own_order in own_orders:
                    if own_order.internal_id == internal_id:
                        internal_order = own_order
                        break
                order_tags = internal_order.tags if internal_order else None
                if order_tags:
                    strategy_slot = order_tags.get("strategy_slot")
                    if strategy_slot:
                        line["strategy_slot"] = strategy_slot
                    portfolio_key = order_tags.get("portfolio_key")
                    if portfolio_key:
                        line["portfolio_key"] = portfolio_key

                # Remove all order (=modification) locks, as we know that the modification failed
                product.order_lock.modify(internal_id, COMMON.InstanceLockState.confirm_all, current_timestamp)
                handled += 1

                if error_code in [COMMON.EpexErrorCodes.concurrent_update, COMMON.EpexErrorCodes.order_not_found]:
                    # NOTE: For concurrent_update and order_not_found, we do NOT remove this order from our
                    #       orderbook, because the most likely explanation is that the order has been traded, in
                    #       which case we can only delete the order, when we set the execution lock
                    #       (to avoid overtrading)
                    continue

                # find the order in the orderbook and remove it, if it is being inserted, but not updated
                # i.e. when the error is in response to an initial faulty order insertion
                internal_order_id = "OWN_{}".format(internal_id)
                internal_order = product.orders.get_own_order_by_order_id(internal_order_id)
                if internal_order:
                    product.orders.remove_own_order(internal_order, current_timestamp)
            else:
                log.debug("Insufficient information in EPEX error response, cannot handle error with code %s",
                          error_code)
        # Only return True, if we have fully handled all errors.
        return handled == len(struct["data"])

    def _get_internal_id_and_product(self, line, error_code):
        """
        Attempts to retrieve the internal_id and the corresponding product of the order, which caused an error
        response (line).

        :param line: an error from the error response, received form an exchange
        :type line: dict
        :param error_code: the error code of the error received
        :type error_code: string
        :return: internal_id, product
        :rtype: (string, Product)
        """
        internal_id = line.get("internal_id")
        product_id = line.get("product_id")
        product = None
        if product_id and internal_id:
            # We expect to be able to find the product_id and internal_id for
            # every order entry/modification error response.
            # We check both, since if ONE of them is missing, we CANNOT handle the error. However, there are
            # some special types of error responses handled in the else case, for which we do not need
            # the product_id and internal_id. So, we would like to default to that statement,
            # in case one of the two is missing.
            try:
                product = self.products.get_by_id(product_id)
            except COMMON.ProductNotFound:
                raise COMMON.ProductNotFound("Product with product_id {product_id} not found"
                                             .format(product_id=product_id))

        else:
            # if we cannot find the product_id and internal_id, we might have been able to send the order_id
            # in the client_order_id within the order modification request to EPEX
            order_id = line.get("order_id")
            if not order_id:
                try:
                    # if the error response is for a concurrent_update/order_not_found,
                    # the order_id is present in the original message by EPEX
                    order_id = line["var_list"][0][COMMON.EpexErrorCodes.order_id_variable[error_code]][0]
                except (KeyError, IndexError):
                    raise COMMON.OrderNotFound("Cannot extract order_id from message {msg}".format(msg=line))

            # For own orders, this code assumes that order_ids are unique between products.
            for active_product in self.products.get_active_products():
                order = active_product.orders.get_own_order_by_order_id(order_id)
                if order is not None:
                    product = active_product
                    internal_id = order.internal_id
                    break
                else:
                    raise COMMON.OrderNotFound("Order with id {id} not found".format(id=order_id))
        return product, internal_id


class NordPool(ExchangeBase):

    def __init__(self, send_func, create_dummy_products, allowed, exchange_config, indicator_update=True,
                 is_parent=True):
        # type: (callable, bool, bool, ATCONF.NordpoolConfig, bool, bool) -> None

        super(NordPool, self).__init__(COMMON.Exchange.nordpool, send_func, create_dummy_products, allowed,
                                       exchange_config, COMMON.ORDER_LOCK_TIMEOUT,
                                       indicator_update=indicator_update, is_parent=is_parent)

    def initialize(self):
        if not self.allowed:
            return

        PERSIST.MongoDBConnector().close_all_orders(self.internal_id)

        request = {"exchange": self.internal_id,
                   "timestamp": int(time.time()),
                   "message_type": COMMON.Request.init}
        self._send_init_file(request, COMMON.InitCorrelationIds.nordpool_init)

    def delete_all_orders(self):
        raise NotImplementedError("order_delete_all requests are not implemented for Nordpool")

    def order_modify_chunking(self, orders, message_type):
        structures = []
        if message_type == COMMON.Request.order_entry:
            get_data_func = "_get_order_entry_params"
        else:
            get_data_func = "_get_order_modify_params"

        for order in orders:
            order_data = getattr(order, get_data_func)()
            structure = {
                "exchange": COMMON.Exchange.nordpool,
                "message_type": message_type,
                "timestamp": int(time.time()),
                "data": order_data
            }
            structures.append(structure)
        return structures

    def update_from_json_on_trade(self, struct, current_timestamp):
        trade_message_struct = dict(exchange=struct["exchange"],
                                    message_type=struct["message_type"],
                                    timestamp=current_timestamp,
                                    data=[])
        # we filter the trades that are older than 2 day
        for element in struct["data"]:
            if element["execution_time"] >= (current_timestamp - 48 * COMMON.HOUR):
                trade_message_struct["data"].append(element)
        return super(NordPool, self).update_from_json_on_trade(trade_message_struct, current_timestamp)

    def handle_error_response(self, struct, current_timestamp):
        """ Handle error responses, sent by NordPool. We do not differentiate between the different
        types of errors, as they all imply that we need to remove the order lock (all are related to order
        entry/modification). If an OwnOrder exists in the product's orderbook, it is removed, in case it is being
        inserted, i.e. it does not have an order_id yet, to avoid filling the orderbook with OwnOrders on faulty slot
        entry.

        :param struct: The message with struct["message_type"] == COMMON.Response.error_response
        :type struct: dict
        :param current_timestamp: The current autoTRADER timestamp
        :type current_timestamp: float or int
        :return: True, if all errors have been fully handled (=> No warning log message needed,
                 no need to store it in persistence),
                 False, otherwise (esp. also in case the exchange is not initialized yet).
        :rtype: bool
        """
        if not self.init_files_ready():
            log.info("Received error response, but no special handling is needed, because NordPool is not initialized")
            return False
        handled = 0
        to_handle = 0
        for error in struct["data"]:
            order_list = error.get("var_list", {})
            if not isinstance(order_list, list):
                order_list = [order_list]

            to_handle += len(order_list)
            for error_var_list in order_list:
                order_tags = ALU.parse_order_tags(error_var_list.get("txt"))
                internal_id = order_tags.get("internal_id")
                if not internal_id:
                    log.debug("Cannot handle error response: Order internal id not found in txt field of the response")
                    continue
                # Unfortunately, NordPool does not give us the product in the error response.
                # For own orders, this code assumes that only one product locks based on one order
                for product in self.products.get_active_products():
                    if internal_id in product.order_lock:
                        log.debug("Removing %s from order lock of product %s on error response with code %s",
                                  internal_id, product.product_id, error.get("error_code", ""))
                        # Remove all order (=modification) locks, as we know that the modification failed
                        product.order_lock.modify(internal_id, COMMON.InstanceLockState.confirm_all, current_timestamp)
                        handled += 1

                        # we need the product_id in the SO error handling, so we add it here
                        error_var_list["product_id"] = product.product_id

                        # find the order in the orderbook and remove it, if it has no initial_order_id
                        # i.e. when the error is in response to an initial faulty order insertion
                        internal_order_id = "OWN_{}".format(internal_id)
                        internal_order = product.orders.get_own_order_by_order_id(internal_order_id)
                        if internal_order:
                            product.orders.remove_own_order(internal_order, current_timestamp)
                        break
                else:
                    log.debug("Cannot handle error response: Order with internal_id %s not found", internal_id)

        return handled == to_handle


class Trayport(ExchangeBase):
    """Exchange class handling everything related to Trayport (EEXS, OTC, ...)"""
    _TradeOrder = collections.namedtuple("_TradeOrder",
                                         ["order_id", "engine_id", "quantity", "product_id", "tags",
                                          "broker_id", "trading_capacity", "decision_maker", "execution_maker",
                                          "derivative_indicator", "dea", "dea_client_id", "liquidity_provision",
                                          "trading_account"])
    Property = collections.namedtuple("property", ["min_quantity", "price_tick", "qty_tick", "unit", "name"])

    def __init__(self, send_func, create_dummy_products, allowed, exchange_config, indicator_update=True,
                 is_parent=True):
        # type: (callable, bool, bool, ATCONF.TrayportConfig, bool, bool) -> None

        # actions_count_mth[year-month][broker_id]
        # actions_count_per_pdt_mth[year-month][broker_id][product_id]
        self.actions_count_mth = collections.defaultdict(collections.Counter)
        self.actions_count_per_pdt_mth = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))

        super(Trayport, self).__init__(COMMON.Exchange.trayport, send_func,
                                       create_dummy_products, allowed, exchange_config,
                                       COMMON.ORDER_LOCK_TIMEOUT,
                                       indicator_update=indicator_update, is_parent=is_parent)

        self.company_id = None
        self.synthetic_products_created = False
        self.local_random = random.Random()
        self.orders_to_remove = []
        """float: For Trayport the smallest possible price step is 0.025"""
        self.tick_size = 0.025

        self.commodities = exchange_config.commodities
        self.venues = exchange_config.venues

        self.product_subscription_max_years = exchange_config.product_subscription_max_years
        self.product_subscription_shortterm_days = exchange_config.product_subscription_shortterm_days
        self.product_subscription_midterm_count = exchange_config.product_subscription_midterm_count
        self.product_subscription_longterm_count = exchange_config.product_subscription_longterm_count

        self.aggress_other_brokers = exchange_config.aggress_other_brokers

        self.trayport_areas = TR.TrayportAreas(self.commodities, self.venues)
        self.trayport_sequences = TR.TrayportSequences()
        self.trayport_terms = TR.TrayportTermFormats()
        self.trayport_properties = TR.TrayportProperties()
        self._connected_brokers = set()

        self._deleted_order_ids = set()
        # Store product ids for products which are already expired long in the past and no longer
        self._expired_product_ids = set()

        # action limits average over a month per broker and, per broker and product
        # action_limits_mth[broker_id][COMMON.ActionLimits.HFT_limit_keys]
        self.action_limits_mth = collections.defaultdict(collections.Counter)

    def is_broker_connected(self, broker_id):
        """
        Returns whether a particular broker is connected, according to the VenueConnections Subscription

        :param broker_id: The id of the broker, a number as string, like "20"
        :type broker_id: str
        :return: Returns True only if both Upstream and Downstream are Connected / Active, otherwise False
        :rtype: bool
        """
        return str(broker_id) in self._connected_brokers

    def _load_from_db(self, _=None):
        super(Trayport, self)._load_from_db()
        limits = PERSIST.MongoDBConnector().load_db_action_limits(self.internal_id)
        if limits:
            self._load_action_limits(limits)

    def _load_action_limits(self, limits):
        """
        loads the action limits for the current year month from the given limits dict
        :param limits: dict with actions_per_product_count and actions_count as keys.
            limits["actions_count"]["year-month"]["broker_id"] = 10
            limits["actions_per_product_count"]["year-month"]["broker_id"]["product_id"] = 10
            the result uses a collections.Counter object
        :type limits: dict
        :return: returns False if no data is loaded and True if data from limits is used.
        :rtype: bool
        """
        # load limits only for the current month
        per_broker = limits.get("actions_count", {})
        per_product = limits.get("actions_per_product_count", {})
        current_year_month = datetime.datetime.utcnow().strftime("%Y-%m")
        if per_broker.get(current_year_month) and per_product.get(current_year_month):
            self.actions_count_mth[current_year_month] = collections.Counter(per_broker[current_year_month])
            convert_prod_count = collections.defaultdict(collections.Counter)
            for brokers, products in per_product[current_year_month].items():
                convert_prod_count[brokers] = collections.Counter(products)
            self.actions_count_per_pdt_mth[current_year_month] = convert_prod_count
            return True
        return False

    def bookkeeping_on_timer_fast(self, current_timestamp):
        """
        Run some internal bookkeeping tasks that have to run frequently on timer fast.

        :type current_timestamp: float or int
        :return: The strategy callbacks that should be run after this. A dict callback_name -> modified objects
        :rtype: dict
        :meta private:
        """
        changed = []
        for product in self.products.get_all():
            changed.extend(product.orders.reevaluate_public_orders_on_timer_fast(current_timestamp))
        return {"on_order_book_update": changed}

    def is_product_id_long_expired(self, product_id):
        """
        Returns True for product ids which have stopped delivery more than 7 days in the past.

        Note: If this returns False, there is no guarantee that the product is active/ not long expired,
              but if it returns True, the product is certainly expired.

        :param product_id: The product_id to check
        :type product_id: string
        :rtype: bool
        """
        return product_id in self._expired_product_ids

    def fetch_inst_definitions(self):
        request = {"exchange": self.internal_id,
                   "timestamp": time.time(),
                   "message_type": COMMON.TrayportRequest.inst_definition}
        self._send_init_file(request,
                             COMMON.InitCorrelationIds.trayport_init,
                             COMMON.InitCorrelationIds.Topic.inst_definitions)

    def fetch_sequence_items(self, sequence_ids):
        request = {"exchange": self.internal_id,
                   "timestamp": time.time(),
                   "message_type": COMMON.TrayportRequest.sequence_items,
                   "data": []}
        for sequence_id in sequence_ids:
            request["data"].append({"sequence_id": sequence_id})
        self._send_init_file(request,
                             COMMON.InitCorrelationIds.trayport_init,
                             COMMON.InitCorrelationIds.Topic.sequence_items)

    def fetch_term_info(self, term_format_ids):
        request = {"exchange": self.internal_id,
                   "timestamp": time.time(),
                   "message_type": COMMON.TrayportRequest.term_format,
                   "data": []}
        for term_format_id in term_format_ids:
            request["data"].append({"term_format_id": term_format_id})
        self._send_init_file(request,
                             COMMON.InitCorrelationIds.trayport_init,
                             COMMON.InitCorrelationIds.Topic.term_formats)

    def fetch_inst_properties(self, inst_prop_ids):
        request = {"exchange": self.internal_id,
                   "timestamp": time.time(),
                   "message_type": COMMON.TrayportRequest.inst_properties,
                   "data": []}
        for broker_id, instrument_id, first_sequence_id, first_item_id in inst_prop_ids:
            request["data"].append({"broker_id": broker_id,
                                    "instrument_id": instrument_id,
                                    "first_sequence_id": first_sequence_id,
                                    "first_item_id": first_item_id})
        self._send_init_file(request,
                             COMMON.InitCorrelationIds.trayport_init,
                             COMMON.InitCorrelationIds.Topic.inst_properties)

    def fetch_trading_data(self):
        request = {"exchange": self.internal_id,
                   "timestamp": time.time(),
                   "message_type": COMMON.TrayportRequest.init_request}
        self._send_init_file(request,
                             COMMON.InitCorrelationIds.trayport_init,
                             COMMON.InitCorrelationIds.Topic.trading_data)

    def get_properties(self, broker_id, delivery_area_id, product_id):
        """find the trayport properties for the specified product

        :param broker_id: ID of broker for the product
        :type broker_id: str
        :param delivery_area_id: ID of delivery area for the product
        :type delivery_area_id: str
        :param product_id: ID of specified product
        :type product_id: str
        :rtype: Property
        """

        key = "{}_{}_{}".format(broker_id, delivery_area_id, product_id)
        area_property = self.trayport_areas[delivery_area_id]
        try:
            properties = self.trayport_properties[key]
            min_quantity = properties.min_quantity
            price_tick = properties.price_tick
            qty_tick = properties.qty_tick
        except KeyError:
            self.error_log("Could not find trayport properties for key: {}".format(key))
            raise
        return self.Property(min_quantity=min_quantity, price_tick=price_tick, qty_tick=qty_tick,
                             unit=getattr(area_property, 'unit', None), name=getattr(area_property, 'inst_name', None))

    def initialize(self):
        if not self.allowed:
            return
        PERSIST.MongoDBConnector().close_all_orders(self.internal_id)
        if not self.read_only:
            # Send delete-all request, but don't require a successful response
            corr_id = "{}_{}".format(COMMON.InitCorrelationIds.Topic.delete_all, str(uuid.uuid1())[:8])
            self.send(self.delete_all_orders(), {"correlation_id": corr_id})
        self.fetch_inst_definitions()

    def _apply_term_formats_on_outgoing_terms(self, term_format_id, terms):
        """
        Apply the rules defined in the specified term format on a list of term dictionaries

        :param term_format_id: ID of term definitions which should be fulfilled
        :type term_format_id: str
        :param terms: terms of the order in JSON format that are going to be sent
        :type terms: list(dict)
        """

        if term_format_id not in list(self.trayport_terms.keys()):
            log.warning("Term format ID %s not found in received term format object collection", term_format_id)
            term_format_defaults = {}
        else:
            term_format_defaults = self.trayport_terms[term_format_id]  # instance of trayport_records.TermDefinitions
        # First, get rid of terms we do not want to send:
        # [:] makes a copy of terms, which is necessary because of terms.remove
        for term in terms[:]:
            if term.get("term_format_id"):
                terms.remove(term)
                continue
            if term["label"] in term_format_defaults:
                definition = term_format_defaults[term["label"]]  # instance of trayport_records.TermDefinition

                read_only_extg_and_true = hasattr(definition, "flags") and definition.flags.get("read_only", False)
                if read_only_extg_and_true or definition.phase != "price" or term["label"] is None:
                    terms.remove(term)
            else:
                log.warning("Term %s was supplied, which is not defined in the term format", term["label"])

        for label, definition in term_format_defaults.items():
            for term in terms:
                if term["label"] == label:
                    # When we send a term with min-digits (e.g. "0.00"), it can happen that the response
                    # just contains "0" without the needed digits. So on modifications, we have to re-add the digits.
                    # We do the formatting only on string values, so we need str() conversion here.
                    term["value"] = definition.format_value(str(term["value"]))
                    break
            else:
                # Read-only terms are filtered, term formats are not applied on them.
                # JD only supports price terms, so we filter out terms with other phases.
                read_only_extg_and_true = hasattr(definition, "flags") and definition.flags.get("read_only", False)
                if read_only_extg_and_true or definition.phase != "price":
                    if definition.choices and definition.default_value not in definition.choices:
                        log.warning("The default value for the term %s is %s, "
                                    "which is not part of the allowed choices: %s",
                                    label, definition.default_value, definition.choices)
                    continue
                terms.append({"label": label, "value": definition.format_value(definition.default_value)})

    @staticmethod
    def _update_products_delivery_area_states(product, new_state, current_timestamp):
        """Helper function updating delivery area states of a product and storing the new state in the db"""
        product._delivery_area_states = {area_id: new_state for area_id in product.delivery_area_states}
        product.update_db(current_timestamp)

    @staticmethod
    def _get_product_states(product, current_timestamp):
        """Helper function to obtain product state and expected state.
        Since all areas have the same delivery states, we do not differentiate them"""
        if product.delivery_area_states:
            area, state = list(product.delivery_area_states.items())[0]
            trading_from, trading_until, unused_state = product.trading_phase(area)
            new_state = trading_from <= current_timestamp < trading_until
            new_state = COMMON.DeliveryAreaState.active if new_state else COMMON.DeliveryAreaState.inactive
            return state, new_state
        else:
            return None, None

    @staticmethod
    def _seq_product_filter(product):
        # This condition excludes `dummy_*` products
        return product.product_id.startswith((TR.SequenceItemRecord.GAS_PROMPT_SEQ_ID,
                                              TR.SequenceItemRecord.BOM_SEQ_ID))

    def _update_synthetic_prompt_product(self, product, current_timestamp):
        """Updates states of a given prompt product"""
        if product.delivery_area_states:
            area, state = list(product.delivery_area_states.items())[0]
            trading_from, trading_until, unused_state = product.trading_phase(area)
            if current_timestamp >= trading_until:
                # If the current ts is greater than the trading phase, then we have to rotate the product
                # Move trades (if any) to the corresponding dummy product
                self._move_trades(current_timestamp, product)
                # Update the delivery intervals to the new intervals.
                self._update_synthetic_product(current_timestamp, product)
                # Remove own active orders (if any) for the product
                self._remove_own_orders(product)
            elif state == COMMON.DeliveryAreaState.inactive and trading_from <= current_timestamp < trading_until:
                # Switch product to active
                self._update_products_delivery_area_states(product, COMMON.DeliveryAreaState.active, current_timestamp)
                log.debug("Synthetic prompt product: %s with product_id: %s became active again",
                          product.name, product.product_id)

    def update_synthetic_prompt_products(self, current_timestamp):
        """Updated all synthetic prompt products on timer to ensure the correct rotation of these products"""
        seq_products = filter(self._seq_product_filter, self.products.get_all())
        for product in seq_products:
            self._update_synthetic_prompt_product(product, current_timestamp)

    def update_synthetic_products(self, current_timestamp):
        """Updates all synthetic products. This function should be called only once per day"""
        log.info("Updating all synthetic products.")
        for product in list(self.products.get_all()):
            if Trayport._seq_product_filter(product):
                self._update_synthetic_prompt_product(product, current_timestamp)
            elif not product.product_id.startswith("dummy"):
                state, new_state = self._get_product_states(product, current_timestamp)
                if state != new_state:
                    self._update_products_delivery_area_states(product, new_state, current_timestamp)
                    log.debug("CHANGE PRODUCT STATE from %s to %s for product_id %s",
                              state, new_state, product.product_id)

    def _move_trades(self, current_timestamp, product):
        """Move trades stored in the current product to a new dummy product on product update"""
        trades = product.trades.get()
        log.debug("MOVING %s TRADES TO DUMMY PRODUCT ON PRODUCT UPDATE", len(trades))
        for trade in trades:
            for area_id in [trade.buy_delivery_area, trade.sell_delivery_area]:
                if area_id:
                    dummy_product = self._get_dummy_product(trade.execution_time, product, area_id)
            trade.product = dummy_product
            product.trades.remove_trade(trade)
            dummy_product.trades.add_trade(trade)
            trade.update_db(current_timestamp)

    def _remove_own_orders(self, product):
        """Remove own orders on product update"""
        log.debug("REMOVE ORDERS ON PRODUCT UPDATE")
        own_orders = product.orders.get(order_filter=COMMON.OrderFilter.own)
        inactive_orders = [order.modify(quantity=0., price=order.price)
                           for order in own_orders
                           if not isinstance(order, APITR.ComTraderOrder)]
        execmode = COMMON.InternalExecutionMode.default
        if inactive_orders:
            self.modify_orders(inactive_orders, execmode, self.market_state)
        # release product lock for orders and trades during inactive trading phase
        product.order_lock.release_all()
        product.trade_lock.release_all()
        product.immediate_action = True

    def _update_synthetic_product(self, current_timestamp, product, area_ids=None):
        """Update delivery and trading intervals of the product"""
        sequence_id = product.market_meta_information["first_sequence_id"]
        item_id = product.market_meta_information["first_item_id"]

        product_message_struct = dict(exchange=COMMON.Exchange.trayport,
                                      message_type=COMMON.Response.product,
                                      timestamp=current_timestamp,
                                      data=[])
        if area_ids is None:
            area_ids = list(product.delivery_area_states)
        if area_ids:
            # Get the trading and delivery interval valid at the current timestamp
            prod_interval = self._get_prod_item_interval(current_timestamp,
                                                         product.market_meta_information)
            product_data = self._synthetic_product_struct(
                prod_interval, product.product_id, product.product_type, area_ids, sequence_id, item_id)
            product_message_struct["data"] = [product_data]
            self.products.update_from_json(product_message_struct, current_timestamp)
        log.debug("Performed product rotation for product: %s with product_id: %s,"
                  " now delivering from: %s until: %s",
                  product.name, product.product_id, product.delivery_start, product.delivery_end)

    @staticmethod
    def _convert_to_orders_by_broker(new_orders, action_types):
        """
        extract all given orders from new_orders with the given action_types to a dict representation by broker and type

        :param new_orders: orders sorted by the ResolverState in a dict
        :type new_orders: dict
        :param action_types: list of COMMON.ResolverState which create an order action
        :type action_types: list
        :return: new_orders with empty lists for the given action_types and an unchanged list for others,
        orders_by_broker[broker_id][action_types]=[order, order,...]
        :rtype: dict[str,list], dict[str, dict[str, list]]
        """

        orders_by_broker = collections.defaultdict(lambda: collections.defaultdict(list))
        for order_type, orders in new_orders.items():
            if order_type in action_types:
                for order in orders:
                    orders_by_broker[order.broker_id][order_type].append(order)
                del orders[:]
        return new_orders, orders_by_broker

    def _handle_order_action_violations(self, new_orders, product_id):
        """
        restrict orders to be sent to the exchange based on a monthly limit per broker and, per broker and product.

        The limit is enforced on a per day basis, adding the unused limits from the last day/s of the current month.
        All new_orders MUST have the same product.
        :param new_orders: defaultdict with COMMON.ResolverState as keys and list of orders as value
        :type new_orders: defaultdict[str, list]
        :param product_id: the id of the product as string
        :type product_id: str
        :return: orders to be sent to the exchange with form: new_orders[ResolverState] = [order1,order2,...]
        :rtype: dict[str, list]
        """
        action_types = [COMMON.ResolverState.modify_orders, COMMON.ResolverState.entry_orders,
                        COMMON.ResolverState.trade_orders, COMMON.ResolverState.activate_orders]

        current_date = datetime.datetime.utcnow()
        curr_day = current_date.day
        current_year_month = current_date.strftime("%Y-%m")

        # orders_by_broker[broker_id][action_types] = [order1, order2, ...]
        new_orders, orders_by_broker = self._convert_to_orders_by_broker(new_orders, action_types)

        restricted_orders = {order_type: [] for order_type in action_types}
        for broker_id, order_types in orders_by_broker.items():
            if broker_id in self.action_limits_mth:
                avl_broker_actions, avl_product_actions = self._calculate_available_actions(broker_id,
                                                                                            curr_day,
                                                                                            current_year_month,
                                                                                            product_id)

                self._calculate_violations(broker_id, product_id, avl_broker_actions, avl_product_actions,
                                           current_year_month, order_types, new_orders, restricted_orders)
            else:
                for order_type, orders in order_types.items():
                    new_orders[order_type].extend(orders)

        # special handling for trade_orders, we need to throw away the lock which would be sent to the child
        self._remove_restricted_trade_locks(new_orders, restricted_orders)

        PERSIST.MongoDBConnector().update_db_action_limits(
            self.actions_count_mth, self.actions_count_per_pdt_mth, self.internal_id
        )

        return new_orders

    def _remove_restricted_trade_locks(self, new_orders, restricted_orders):
        """
        Checks if a restricted_order is of type trade_order and deletes the corresponding trade_lock from new_orders

        :param new_orders: dict with COMMON.ResolverState as keys and list of orders as value
        :type new_orders: dict[str, list]
        :param restricted_orders: dict with COMMON.ResolverState as keys and list of orders as value
        :type restricted_orders: dict[str, list]
        """

        trade_locks = {(order.order_id, order.broker_id) for order in
                       restricted_orders[COMMON.ResolverState.trade_orders]}
        if trade_locks:
            new_orders[COMMON.ResolverState.internal_trade_lock] = [
                order for order in new_orders[COMMON.ResolverState.internal_trade_lock] if
                (order.order_id, order.broker_id) not in trade_locks]

    def _calculate_violations(self, broker_id, product_id, avl_broker_actions, avl_product_actions, current_year_month,
                              order_types, new_orders, restricted_orders):
        """
        calculate the current actions for the broker and restrict orders if needed.

        :param broker_id: broker_id as string
        :type broker_id: str
        :param product_id: product_id as string
        :type product_id: str
        :param avl_broker_actions: currently available order actions per the broker defined in broker_id
        :type avl_broker_actions: int
        :param avl_product_actions: currently available product actions for the given broker_id and product_id
        :type avl_product_actions: int
        :param current_year_month: string in the format "2020-04"
        :type current_year_month: str
        :param order_types: key is the COMMON.ResolverState with a list of orders as values
        :type order_types: dict[str, list]
        :param new_orders: key is the COMMON.ResolverState with a list of orders as values
        :type new_orders: dict[str, list]
        :param restricted_orders: same format as order_types, will be updated with the found restricted orders
        :type restricted_orders: dict[str, list]
        """
        max_poss_actions = max(min(avl_broker_actions, avl_product_actions), 0)
        for order_type, orders in order_types.items():
            allowed_actions = max(min(len(orders), max_poss_actions), 0)
            new_orders[order_type].extend(orders[:allowed_actions])
            restricted_orders[order_type].extend(orders[allowed_actions:])
            max_poss_actions -= allowed_actions
            self.actions_count_mth[current_year_month][broker_id] += allowed_actions
            self.actions_count_per_pdt_mth[current_year_month][broker_id][product_id] += allowed_actions

    def _calculate_available_actions(self, broker_id, curr_day, current_year_month, product_id):
        """
        calculates the available actions for the given broker and product

        :param broker_id: id of a broker as string
        :type broker_id: str
        :param curr_day: current day as integer
        :type curr_day: int
        :param current_year_month: string with format "2020-04"
        :type current_year_month: str
        :param product_id: the product_id of the current used product
        :type product_id: str
        :return: currently available actions for broker and products.
        :rtype: int, int
        """

        broker_limit = curr_day * COMMON.DAY * self.action_limits_mth[broker_id][COMMON.ActionLimits.broker]
        product_limit = curr_day * COMMON.DAY * self.action_limits_mth[broker_id][COMMON.ActionLimits.product]
        broker_action_count = self.actions_count_mth[current_year_month][broker_id]
        product_action_count = self.actions_count_per_pdt_mth[current_year_month][broker_id][product_id]
        available_broker_actions = broker_limit - broker_action_count
        available_product_actions = product_limit - product_action_count
        # after 80% of actions are used, a limit message will be written to compliance log
        if 0 < available_broker_actions < broker_limit * 0.2:
            log.compliance_log(LOGTEMP.AutoTraderLimiter.broker_limit_info,
                               broker_id=broker_id,
                               percent=int(math.floor(broker_action_count / float(broker_limit) * 100)))
        elif available_broker_actions <= 0:
            log.compliance_log(LOGTEMP.AutoTraderLimiter.broker_limit_error,
                               broker_id=broker_id)

        if 0 < available_product_actions < product_limit * 0.2:
            log.compliance_log(LOGTEMP.AutoTraderLimiter.product_limit_info,
                               broker_id=broker_id,
                               product_id=product_id,
                               percent=int(math.floor(product_action_count / float(product_limit) * 100)))
        elif available_product_actions <= 0:
            log.compliance_log(LOGTEMP.AutoTraderLimiter.product_limit_error,
                               broker_id=broker_id,
                               product_id=product_id)

        return available_broker_actions, available_product_actions

    def _validate_action_limits_json(self, data):
        """
        Checks if the dict converted from the json data for the action_limits file contains all needed keys.

        It is not allowed to have no action_limits defined. There must be at least one broker
        :param data: action limits loaded from a json file into a dict
        :type data: dict
        :return True if the file is validated correctly, False if not.
        """

        action_limit_keys = COMMON.ActionLimits.action_limit_keys
        HFT_limit_keys = COMMON.ActionLimits.HFT_limit_keys

        return (COMMON.ActionLimits.version in data and data.get(self.internal_id)
                and all(self._validate_limit_keys(data[self.internal_id][broker_id], action_limit_keys, HFT_limit_keys)
                        for broker_id in data[self.internal_id]))

    def _validate_broker_spec_json(self, data):
        """"
        Validate the content of the broker spec file (jd_manager_config.json)

        Example of the json data:

        .. code-block:: json

            {
              "VERSION": "2021-02-01T08:00:00Z",
              "TRAYPORT": {
                "30": {
                   "combined_orders": true
                },
                "1441": {
                    "combined_orders": true
                }
              }
            }

        :param data: Parsed json data
        :type data: dict
        :returns: False if the data contains errors, True otherwise.
        :rtyoe: bool
        """
        if self.internal_id not in data:
            log.error("Validation of broker spec file %s failed: %s not found in %r",
                      COMMON.BrokerSpecs.filename, self.internal_id, data)
            return False
        try:
            for broker_id, broker_data in data[self.internal_id].items():
                if not isinstance(broker_data, dict):
                    log.error("Validation of broker spec file %s failed: Broker %r does not map to a dict,"
                              " found %r instead", COMMON.BrokerSpecs.filename, broker_id, broker_data)

                    return False
                if not isinstance(broker_id, six.string_types):
                    log.error("Validation of broker spec file %s failed: Broker ID %r must be a unicode!",
                              COMMON.BrokerSpecs.filename, broker_id)
                    return False
                for key in broker_data:
                    if key not in COMMON.BrokerSpecs.valid_keys:
                        log.error("Ignoring %r: %r in broker spec file for broker %s, because the "
                                  "key '%s' is not valid. Valid keys are: %s. This warning can either indicate that "
                                  "a new key was introduced in a higher version of autoTRADER or that there is a typo "
                                  "in the configuration file 'jd_manager_config.json'.", key, broker_data[key],
                                  broker_id, key, COMMON.BrokerSpecs.valid_keys)
        except AttributeError as err:
            log.error("Validation of broker spec file %s failed: data[%s] is not a dict, found %r instead. Error: %s",
                      COMMON.BrokerSpecs.filename, self.internal_id, data[self.internal_id], err)
            # If data[internal_id] is not a dict
            return False
        # Note: We do not validate the keys inside the broker config, to be forward compatible with new keys
        # that we might add to this file in the future.
        return True

    def _update_action_limit_settings_from_dict(self, settings):
        """
        Update the action limit settings from the given dict.

        :param settings: limit settings defined per broker settings[broker_id][action_rate_limit] = 20
        :type settings: dict[dict[str, int]
        """

        # settings[broker_id][action_rate_limit] = 20
        self.products.settings_per_broker = settings
        for broker_id, limit_values in self.products.settings_per_broker.items():
            if set(COMMON.ActionLimits.action_limit_keys).issubset(set(limit_values)):
                self.products.actions_per_broker[broker_id] = collections.deque(
                    maxlen=limit_values[COMMON.ActionLimits.limit])
            if set(COMMON.ActionLimits.HFT_limit_keys).issubset(set(limit_values)):
                for limit in COMMON.ActionLimits.HFT_limit_keys:
                    self.action_limits_mth[broker_id][limit] = limit_values[limit]

    @staticmethod
    def _validate_limit_keys(data, limit_keys, HFT_keys):
        """
        check if limit_keys OR HFT_keys OR (limit_keys + HFT_keys) are keys of data dict. Values have to be integer.

        :param data: dict with integer as values
        :type data: dict
        :param limit_keys: list of needed limit_keys
        :type limit_keys: tuple
        :param HFT_keys: list of needed HFT_keys
        :type HFT_keys: tuple
        :return: True if valid, False if not
        :rtype: bool
        """
        # limit_keys OR HFT_keys
        limits_or_HFT = set(data) in (set(limit_keys), set(HFT_keys))
        # limit_keys OR HFT_keys OR limit_keys + HFT_keys
        if limits_or_HFT or set(data) == set(limit_keys + HFT_keys):
            return all(isinstance(value, int) for value in data.values())
        return False

    def fetch_action_limits(self):
        """
        load the action limits and intervals from the action_limit_config file
        """
        try:
            data = self._read_action_limit_file()
            if self._validate_action_limits_json(data):
                self._update_action_limit_settings_from_dict(data[COMMON.Exchange.trayport])
            else:
                raise COMMON.ActionLimitFormatError
        except IOError as err:
            reason = "Stop Exchange {} due to missing file: {}, err: {}".format(self.internal_id,
                                                                                ATCONF.ACTION_LIMIT_CONFIG,
                                                                                err)
            log.exception(reason)
            raise COMMON.HaltExchangeException(self.internal_id, reason)
        except ValueError as err:
            reason = "No json format found, check {} file for validity! err: {}".format(ATCONF.ACTION_LIMIT_CONFIG, err)
            log.exception(reason)
            raise COMMON.HaltExchangeException(self.internal_id, reason)
        except COMMON.ActionLimitFormatError as err:
            reason = "Wrong settings for action limits, check {} file for validity!".format(ATCONF.ACTION_LIMIT_CONFIG)
            log.exception(reason)
            raise COMMON.HaltExchangeException(self.internal_id, reason)

    def _fetch_broker_specs(self):
        """
        Open the broker_spec file, validate it and store the read configuration

        This file contains information about the behavior of the broker, which we cannot read via any API,
        such as whether or not the broker combines multiple public orders with the same price into a single order.
        """
        try:
            data = self._read_broker_spec_file()
        except IOError as err:
            reason = "Stop Exchange {} due to missing file: {}, err: {}".format(self.internal_id,
                                                                                ATCONF.BROKER_SPEC_CONFIG,
                                                                                err)
            raise COMMON.HaltExchangeException(self.internal_id, reason)
        except ValueError as err:
            reason = "No json format found, check {} file for validity! err: {}".format(ATCONF.BROKER_SPEC_CONFIG, err)
            log.exception(reason)
            raise COMMON.HaltExchangeException(self.internal_id, reason)
        try:
            log.info("Loaded broker-spec file (%s) file with version %s", COMMON.BrokerSpecs.filename,
                     data[COMMON.BrokerSpecs.version])
        except KeyError as err:
            log.error("Broker spec file %s does not contain a version!", COMMON.BrokerSpecs.filename)
        if not self._validate_broker_spec_json(data):
            reason = "Wrong settings for broker spec, check {} file for validity!".format(ATCONF.BROKER_SPEC_CONFIG)
            raise COMMON.HaltExchangeException(self.internal_id, reason)
        self.combined_order_brokers = self._get_brokers_from_brokerdata_which(
            COMMON.BrokerSpecs.does_combine_public_orders,
            data, self.internal_id)
        log.info("Set combined_order_brokers to %s", self.combined_order_brokers)
        self.brokers_without_tradeorders = self._get_brokers_from_brokerdata_which(
            COMMON.BrokerSpecs.does_not_support_tradeorders,
            data, self.internal_id)
        log.info("Set brokers_without_tradeorders to %s", self.brokers_without_tradeorders)
        self.brokers_with_multimatching_lock_release = self._get_brokers_from_brokerdata_which(
            COMMON.BrokerSpecs.does_match_quantity_for_execution_lock_release,
            data, self.internal_id)
        log.info("Set brokers_with_multimatching_lock_release to %s", self.brokers_with_multimatching_lock_release)
        # now we can fill the "brokers_without_hibernation" frozenset in the internal market object
        self.internal_market.brokers_without_hibernation = self._get_brokers_from_brokerdata_which(
            COMMON.BrokerSpecs.cannot_hibernate_orders,
            data, self.internal_id)
        log.info("Set brokers_without_hibernation to %s", self.internal_market.brokers_without_hibernation)

    @staticmethod
    def _get_brokers_from_brokerdata_which(condition, broker_data, exchange_id):
        """Get all broker ids for which combined orders handling applies from the broker data

        :param condition: Return brokers, where the value mapped to this key is True.
                          Use a key from COMMON.BrokerSpecs
        :type condition: str
        :type broker_data: dict
        :type exchange_id: str
        :rtype: frozenset[str]
        """
        return frozenset(
            broker_id for (broker_id, broker_config) in broker_data[exchange_id].items()
            if broker_config.get(condition)
        )

    @staticmethod
    def _read_broker_spec_file():
        """
        Read the combined orders file and return the content as dictionary.

        :return: The action limits
        :rtype: dict
        """
        with open(ATCONF.BROKER_SPEC_CONFIG, "r") as combined_orders_file:
            return json.load(combined_orders_file)

    @staticmethod
    def _read_action_limit_file():
        """
        Read the action_limit file and return the content as dictionary.

        :return: The action limits
        :rtype: dict
        """
        with open(ATCONF.ACTION_LIMIT_CONFIG, "r") as action_limit_file:
            return json.load(action_limit_file)

    def generate_synthetic_products(self, sequence, current_timestamp):
        log.debug("Generate synthetic products for sequence %s with %s items", sequence.seq_id, len(sequence))

        sequence_id = sequence.seq_id
        for item_id, trayport_item in sequence.items():
            product_id = "{}_{}".format(sequence_id, item_id)
            area_ids = [area_id for area_id, area_record in self.trayport_areas.items()
                        if sequence_id in area_record.sequences]
            try:
                # Product loaded from MongoDB.
                product = self.products.get_by_id(product_id)
            except COMMON.ProductNotFound:
                self._create_synthetic_prompt_product(sequence_id, item_id, trayport_item, area_ids, current_timestamp)
            else:
                prod_interval = self._get_prod_item_interval(current_timestamp, {"first_sequence_id": sequence_id,
                                                                                 "first_item_id": item_id})
                if (prod_interval.delivery_start != product.delivery_start
                        or prod_interval.delivery_end != product.delivery_end):
                    # While autoTRADER was offline, product rotation would have happened. Rotate now.
                    log.info("Performing product rotation on start-up for product %s (%s)",
                             product.product_id, product.name)
                    self._move_trades(current_timestamp, product)
                # Here we set the delivery area states and trading phases (which were not loaded from MongoDB).
                # This may or may not change the product interval from what we loaded from MongoDB.
                # After this, the product is inactive, but will be set to active on the next timer event.
                self._update_synthetic_product(current_timestamp, product, area_ids=area_ids)

            # Send request for instrument properties
            inst_prop_ids = [(broker_id, area_id, sequence_id, item_id)
                             for area_id in area_ids
                             for broker_id in self.trayport_areas[area_id].brokers]
            for i in range(0, len(inst_prop_ids), 200):
                self.fetch_inst_properties(inst_prop_ids[i:i + 200])

    def _create_synthetic_prompt_product(self, sequence_id, item_id, trayport_item, area_ids, current_timestamp):
        product_id = "{}_{}".format(sequence_id, item_id)
        product_message_struct = dict(exchange="TRAYPORT",
                                      message_type="product",
                                      timestamp=current_timestamp)
        product_type = trayport_item.item_name
        prod_interval = trayport_item.item_interval.get_interval(current_timestamp)
        product_data = self._synthetic_product_struct(
            prod_interval, product_id, product_type, area_ids, sequence_id, item_id)
        product_message_struct["data"] = [product_data]

        self.products.update_from_json(product_message_struct, current_timestamp)

    def _synthetic_product_struct(self, prod_interval, product_id, product_type,
                                  instrument_ids, sequence_id, item_id,
                                  state=COMMON.DeliveryAreaState.inactive):
        """

        :param prod_interval: product interval holding a collection of delivery and trading phases evaluated
                              for that product (i.e. sequence and item)
        :type prod_interval: :class:`autotrader_core.trayport_items._ItemInterval`
        :param str product_id: id of the product
        :param str product_type: type of the product
        :param list instrument_ids: list with instrument ids associated with the products areas
        :param str sequence_id: id of the corresponding sequence
        :param str item_id: id of the corresponding sequence item
        :param state: state of the product
        :type state: :class:`COMMON.DeliveryAreaState`
        :return: dict with product information to propagate further into the products class
        :rtype: dict
        """
        sequence = self.trayport_sequences[sequence_id]
        item = sequence[item_id]
        name = u"{}_{}_{}".format(sequence.seq_name, item.item_name, prod_interval.name)
        return dict(name=name,
                    delivery_start=prod_interval.delivery_start,
                    delivery_end=prod_interval.delivery_end,
                    product_id=product_id,
                    predefined="true",
                    delivery_area_states={
                        # State has to be true, because orders are not automatically removed from
                        # Trayport if such a synthetic product ends its trading
                        instrument_id: {"state": state} for instrument_id in instrument_ids},
                    trading_phases={
                        instrument_id: {
                            "start": prod_interval.trading_start,
                            # trayport does not have trading phase but we set it here to be compatible
                            # with the exchange_trading.is_tradable function
                            "state": COMMON.TradingPhase.continuous,
                            "end": prod_interval.trading_end} for instrument_id in instrument_ids},
                    product_type=product_type,
                    market_meta_information={
                        "first_sequence_id": sequence_id,
                        "first_item_id": item_id,
                        "second_item_id": "0",
                        "sequence_span": "Single"}
                    )

    def _get_prod_item_interval(self, timestamp, metadata_dict):
        item_id = metadata_dict["first_item_id"]
        sequence_id = metadata_dict["first_sequence_id"]
        sequence = self.trayport_sequences[sequence_id]
        seq_item = sequence[item_id]
        prod_interval = seq_item.item_interval.get_interval(timestamp)
        return prod_interval

    def _get_dummy_product(self, timestamp, product, instrument_id):
        # instrument_id ~= trayport equivalent to area id
        # round timestamp down to a full hour and add half an hour to avoid ambiguity in product interval due to
        # TRADING_END_DELTA
        timestamp = (timestamp // COMMON.HOUR + 0.5) * COMMON.HOUR
        product_id = product.product_id
        metadata_dict = product.market_meta_information
        prod_interval = self._get_prod_item_interval(timestamp, metadata_dict)
        try:
            dummy_product = self.products.get_by_id("dummy_{}_{}".format(product_id, prod_interval.name))
        except COMMON.ProductNotFound:
            dummy_product = self.generate_dummy_synthetic_product(
                timestamp, metadata_dict, instrument_id)
        return dummy_product

    def generate_dummy_synthetic_product(self, timestamp, metadata_dict, instrument_id):
        sequence_id = metadata_dict["first_sequence_id"]
        item_id = metadata_dict["first_item_id"]
        sequence = self.trayport_sequences[sequence_id]
        trayport_item = sequence[item_id]

        prod_interval = self._get_prod_item_interval(timestamp, metadata_dict)

        product_id = u"dummy_{}_{}_{}".format(sequence_id, item_id, prod_interval.name)

        product_type = trayport_item.item_name
        product_message_struct = dict(exchange="TRAYPORT",
                                      message_type="product",
                                      timestamp=timestamp)
        product_data = self._synthetic_product_struct(
            prod_interval, product_id, product_type, [instrument_id], sequence_id, item_id)
        product_message_struct["data"] = [product_data]
        product = self.products.update_from_json(product_message_struct, timestamp)[0]
        log.debug("DUMMY product is created %s", product.product_id)
        return product

    def order_modify_chunking(self, orders, message_type):
        structures = []
        if message_type == COMMON.Request.order_entry:
            get_data_func = "_get_order_entry_params"
        else:
            get_data_func = "_get_order_modify_params"

        for order in orders:
            order_data = getattr(order, get_data_func)()
            # Get term format id
            area = self.trayport_areas[order.delivery_area_id]
            term_format_id = area.brokers[order.broker_id]
            order_data["inst_specifier"][0]["term_format_id"] = term_format_id

            if order_data.get("terms") is None:
                order_data["terms"] = []
            self._apply_term_formats_on_outgoing_terms(term_format_id, order_data["terms"])

            structure = {
                "exchange": COMMON.Exchange.trayport,
                "message_type": message_type,
                "timestamp": int(time.time()),
                "data": [order_data]
            }
            structures.append(structure)
        return structures

    def trade_order_chunking(self, trade_orders):
        structures = []

        for trade_order in trade_orders:
            order_data = {"order_id": trade_order.order_id,
                          "engine_id": trade_order.engine_id,
                          "quantity": int(trade_order.quantity),
                          "broker_id": trade_order.broker_id,
                          "txt": ALU.serialize_order_tags(trade_order.tags)}
            for field in APITR.OrderRegulatoryData.read_write_keys:
                if getattr(trade_order, field) is not None:
                    order_data[field] = getattr(trade_order, field)
            if trade_order.trading_account is not None:
                order_data["trading_account"] = trade_order.trading_account
            structure = {
                "exchange": COMMON.Exchange.trayport,
                "message_type": COMMON.TrayportRequest.trade_order,
                "timestamp": int(time.time()),
                "data": [order_data]
            }
            structures.append(structure)
        return structures

    def update_from_json(self, struct, current_timestamp):
        callbacks = {
            COMMON.TrayportResponse.user_info: self.update_from_json_on_user_info,
            COMMON.TrayportResponse.inst_definitions: self.update_from_json_on_inst_definition,
            COMMON.TrayportResponse.inst_properties: self.update_from_json_on_inst_properties,
            COMMON.TrayportResponse.sequence_items: self.update_from_json_on_sequence_items,
            COMMON.TrayportResponse.term_format: self.update_from_json_on_term_info,
            COMMON.TrayportResponse.venue_connection: self.update_from_venue_connection_message,
        }
        if struct["message_type"] not in callbacks:
            return super(Trayport, self).update_from_json(struct, current_timestamp)
        else:
            return callbacks[struct["message_type"]](struct, current_timestamp)

    def update_from_json_on_user_info(self, struct, unused_current_timestamp):
        self.autotrader_user = struct["data"][0]["user_id"]
        self.company_id = struct["data"][0]["company_id"]
        return {}

    def _get_error_type(self, error):
        # type: (dict) -> str
        """Get error type based info in the error.

        If no additional info about order/trade/tradeorder is present, the error type is general
        """
        for error_type in (COMMON.TrayportReplyATErrorType.trade,
                           COMMON.TrayportReplyATErrorType.tradeorder,
                           COMMON.TrayportReplyATErrorType.order):
            if error.get(error_type):
                return error_type
        return COMMON.TrayportReplyATErrorType.general

    def handle_error_response(self, struct, current_timestamp):
        timestamp = struct["timestamp"]
        if not self.init_files_ready():
            log.info("Received error response, but no special handling is needed, because TRAYPORT is not initialized")
            return False
        for error in struct["data"]:
            error_type = self._get_error_type(error)
            error_message = error.get("error_message", "")

            if COMMON.ErrorMsgs.request_timeout in error_message or COMMON.ErrorMsgs.request_expired in error_message:
                log.error("Received a request timeout error message from Trayport, requesting a restart!")
                raise COMMON.RestartExchangeException(self.internal_id)
            elif error_type in ["trade", "tradeorder"]:
                trade_error = error[error_type][0]
                tags = ALU.parse_order_tags(trade_error["txt"])
                memo = ALU.parse_order_tags(trade_error.get("memo", ""))
                product_id = tags.get("product_id") or memo.get("product_id")
                internal_id = tags.get("internal_id") or memo.get("internal_id")

                if product_id and internal_id:
                    product = self.products.get_by_id(product_id)
                    product.trade_lock.modify(internal_id, COMMON.InstanceLockState.confirm_all, timestamp)
                else:
                    log.error("Received Error message: {}. No Product ID or Internal ID found, "
                              "so no product could be unlocked.".format(error))
            elif error_type == "order":
                order_error = error["order"][0]
                inst_specifier = order_error["inst_specifier"][0]
                delivery_area_id = inst_specifier["instrument_id"]
                if delivery_area_id not in self.trayport_areas:
                    if self.is_parent:
                        log.debug("Delivery area %s is not configured for autoTRADER: skipping error", delivery_area_id)
                    continue
                metadata_dict = {
                    "first_sequence_id": inst_specifier["first_sequence_id"],
                    "first_item_id": inst_specifier["first_item_id"],
                    "second_item_id": "0",
                    "term_format_id": inst_specifier["term_format_id"]
                }
                product_id = u"{}_{}".format(metadata_dict["first_sequence_id"], metadata_dict["first_item_id"])
                try:
                    product = self.products.get_by_id(product_id)
                except COMMON.ProductNotFound:
                    log.exception("Product not found: %s", product_id)
                    continue

                internal_id = ALU.parse_order_tags(order_error["txt"]).get("internal_id")
                broker_id = order_error.get("broker_id", None)
                if internal_id:
                    product.order_lock.modify(internal_id, COMMON.InstanceLockState.confirm_all, timestamp)
                    order_id = order_error["order_id"] if order_error["order_id"] else order_error["initial_order_id"]
                    if not order_id:
                        # If order does not have an order_id yet, remove it from the
                        # own_order_book
                        internal_order_id = "OWN_{}".format(internal_id)
                        internal_order = product.orders.get_own_order_by_order_id(order_id=internal_order_id,
                                                                                  broker_id=broker_id)
                        if internal_order:
                            product.orders.remove_own_order(internal_order, current_timestamp)
            else:
                log.error("Unspecified error: Error: {}, {}".format(
                    error_message, error.get("error_msg")
                ))
        # NOTE(bet): Currently we return False for backwards compatibility (i.e. to store the
        #            error response in the database). Could probably be True as well
        return False

    def update_from_venue_connection_message(self, struct, _):
        """
        Update the set of connected brokers based on a venue connection message from JD.

        This gets triggered if the state of the connection between JD and a venue (broker) changes.

        :meta private:

        :param struct: The message received from the jd connection manager
        :type struct: dict
        """
        log.debug("Received venue connections response:")
        for venue_info in struct.get("data", []):
            if (venue_info["upstream_state"] in ("Connected", COMMON.SIMULATION_VENUE_UPSTREAM_STATE)
                    and venue_info["downstream_state"] == "Active"):
                self._connected_brokers.add(venue_info["broker_id"])
                level = FLOG.INFO
                state = "ok"
            else:
                self._connected_brokers.discard(venue_info["broker_id"])
                level = FLOG.WARNING
                state = "inactive"
            log.log(level,
                    "Venue with broker_id %s is %s (Upstream state: %s, downstream state: %s, last changed at %s)",
                    venue_info["broker_id"], state, venue_info["upstream_state"],
                    venue_info["downstream_state"],
                    ALU.convert_from_timestamp(venue_info["last_update_timestamp"], COMMON.DATEFORMAT))
        return {}

    def update_from_json_on_inst_definition(self, struct, unused_current_timestamp):

        term_format_ids = set([])

        for inst_def in struct["data"]:
            inst_id = inst_def["inst_id"]
            self.trayport_areas[inst_id] = inst_def
            if inst_id in self.trayport_areas:
                area = self.trayport_areas[inst_id]
                for seq_id, sequence in area.sequences.items():
                    if seq_id not in self.trayport_sequences:
                        self.trayport_sequences[seq_id] = sequence
                for _, term_format_id in area.brokers.items():
                    if term_format_id not in term_format_ids:
                        term_format_ids.add(term_format_id)

        self.fetch_sequence_items(list(self.trayport_sequences.collection.keys()))
        self.fetch_term_info(term_format_ids)

        return {}

    def update_from_json_on_inst_properties(self, struct, current_timestamp):
        for prop in struct["data"]:
            self.trayport_properties.add_property(prop)

        # If we have received all instrument properties, we continue initialization by fetching trading data.
        # We do not care whether the delete_all request has been confirmed or not
        if (self.init_files_correlation_ids
                and all(value
                        for corr_id, value in self.init_files_correlation_ids.items()
                        if corr_id.startswith(COMMON.InitCorrelationIds.Topic.inst_properties))):
            self.trayport_terms.update_db()
            self.fetch_trading_data()
            self.update_synthetic_products(current_timestamp)
            # setting trayport properties inside internal market now, because they were not yet available upon __init__
            self.internal_market.trayport_properties = self.trayport_properties
        return {}

    def _is_sequence_item_relevant(self, sequence_item, current_timestamp, filter_start_ts, filter_end_ts):
        """
        Returns whether we should subscribe to a sequence item, based on its delivery span.

        This function classifies sequence_items (~products) based on the configuration values
        product_subscription_shortterm_days, product_subscription_midterm_count and
        product_subscription_longterm_count

        :param sequence_item: The sequence item json
        :type sequence_item: dict
        :param current_timestamp: AT's current timestamp
        :type current_timestamp: float
        :param filter_start_ts: Start timestamp. For products finishing delivery earlier than this timestamp
                                this function will always return False, independent of other settings.
        :type filter_start_ts: float
        :param filter_end_ts: End timestamp. For products delivering later than this timestamp
                              this function will always return False, independent of other settings.
        :type filter_end_ts: float

        """
        delivery_delta = sequence_item["delivery_end"] - sequence_item["delivery_start"]
        if delivery_delta >= COMMON.DAY * 80:
            time_ahead_to_collect = self.product_subscription_longterm_count * delivery_delta
        elif delivery_delta >= COMMON.HOUR * 24:
            # default: for daily products accumulate for 10 days ahead
            time_ahead_to_collect = self.product_subscription_midterm_count * delivery_delta
        else:
            # default: for <daily (hourly) products accumulate 3 days ahead
            time_ahead_to_collect = self.product_subscription_shortterm_days * COMMON.DAY
        seq_id = sequence_item["seq_id"]

        delivery_filter = (sequence_item["delivery_start"] < current_timestamp + time_ahead_to_collect
                           and filter_start_ts < sequence_item["delivery_end"] < filter_end_ts)

        if seq_id == TR.SequenceItemRecord.GAS_PROMPT_SEQ_ID or delivery_filter and seq_id in self.trayport_sequences:
            return True
        else:
            log.debug("Not subscribing to product %s_%s, delivering from %s until %s. Time ahead to collect: %s",
                      seq_id, sequence_item["item_id"], sequence_item["delivery_start"], sequence_item["delivery_end"],
                      time_ahead_to_collect)
            # Store sequence_items which are long in the past, so we forget limits set for them.
            if sequence_item["delivery_end"] < current_timestamp - COMMON.WEEK:
                self._expired_product_ids.add("{}_{}".format(seq_id, sequence_item["item_id"]))
            return False

    def update_from_json_on_sequence_items(self, struct, current_timestamp):
        """Method that updates the exchange on receiving a sequence items information from Trayport

        We filter the sequence items according to their delivery period:
        1) The delivery period should lie within the two days before until 2 years ahead;
        2) There are no more than 9-10 products with the same delivery span liying within the interval in 1).
        """
        # fetch the action limits, if the file does not exist, critical halt exchange
        self.fetch_action_limits()
        self._fetch_broker_specs()

        updated_sequences = set()
        now = current_timestamp
        datetime_now = ALU.convert_utc_timestamp_to_dt(now).replace(hour=0, minute=0, second=0)
        delivery_start_dt = datetime_now - datetime.timedelta(days=2)
        delivery_start_dt = ALU.convert_dt_to_float_timestamp(delivery_start_dt)
        delivery_end_dt = datetime_now + RD.relativedelta(years=self.product_subscription_max_years)
        delivery_end_dt = ALU.convert_dt_to_float_timestamp(delivery_end_dt)

        for sequence_item in struct["data"]:
            seq_id = sequence_item["seq_id"]
            item_id = sequence_item["item_id"]
            if self._is_sequence_item_relevant(sequence_item, current_timestamp, delivery_start_dt, delivery_end_dt):
                sequence = self.trayport_sequences[seq_id]
                updated_sequences.add(sequence)
                sequence[item_id] = sequence_item

        # Update db with the added sequence items as well as create synthetic products
        for sequence in updated_sequences:
            self.generate_synthetic_products(sequence, current_timestamp)
            sequence.update_db()
        return {}

    def update_from_json_on_term_info(self, struct, unused_current_timestamp):
        """Updates trayport_terms on new term_format message

        :param struct: translated Trayport response on Term Format query, with message type "term_format"
        :type struct: typing.Dict[str, str]
        :returns: empty dictionary (because strategy callback is not needed)
        :rtype: dict
        """

        for term_format in struct["data"]:
            term_format_id = term_format["term_format_id"]
            self.trayport_terms[term_format_id] = term_format["term"]
            self.trayport_terms[term_format_id].update_db()

        return {}

    def update_on_timer(self, current_timestamp):
        self.update_synthetic_prompt_products(current_timestamp)

    @staticmethod
    def _product_filter(product, timestamp):
        trading_start, trading_end, unused_state = list(product._trading_phases.values())[0]
        return trading_start <= timestamp < trading_end

    @staticmethod
    def _product_filter_gt(product, timestamp):
        unused_trading_start, trading_end, unused_state = list(product._trading_phases.values())[0]
        return timestamp < trading_end

    def update_from_json_on_trade(self, struct, current_timestamp):
        own_trade_message_struct = dict(exchange=COMMON.Exchange.trayport,
                                        message_type=COMMON.Response.own_trade,
                                        timestamp=current_timestamp,
                                        data=[])
        internal_trade_message_struct = dict(exchange=COMMON.Exchange.trayport,
                                             message_type=COMMON.Response.internal_trade,
                                             timestamp=current_timestamp,
                                             data=[])
        public_trade_message_struct = dict(exchange=COMMON.Exchange.trayport,
                                           message_type=COMMON.Response.public_trade,
                                           timestamp=current_timestamp,
                                           data=[])

        if struct["message_type"] == COMMON.TrayportResponse.trade_list:
            for trade_data in struct["data"]:
                product = self._get_product_or_dummy_product(trade_data)
                if not product:
                    continue
                delivery_area_id = trade_data["inst_specifier"][0]["instrument_id"]

                # user determines if that is an own trade or not
                trade_dict = dict(trade_id=trade_data["trade_id"],
                                  order_id=trade_data.get("order_id"),
                                  state=trade_data["state"],
                                  txt=trade_data["txt"],
                                  revision=current_timestamp,
                                  execution_time=trade_data["execution_time"],
                                  product_id=product.product_id,
                                  price=trade_data["price"],
                                  quantity=trade_data["quantity"],
                                  aggressor_broker_id=trade_data["aggressor_broker_id"],
                                  initiator_broker_id=trade_data["initiator_broker_id"],
                                  aggressor_trading_account=trade_data.get("aggressor_trading_account", ""),
                                  initiator_trading_account=trade_data.get("initiator_trading_account", ""),
                                  route_id=trade_data.get("route_id"),
                                  from_broken_spread=trade_data.get("from_broken_spread", ""),
                                  init_sleeve=trade_data.get("init_sleeve", ""),
                                  agg_sleeve=trade_data.get("agg_sleeve", ""),
                                  voice_deal=trade_data.get("voice_deal", "")
                                  )

                if self.company_id in (trade_data.get("initiator_company_id", ""),
                                       trade_data.get("aggressor_company_id", "")):
                    # this is an own trade
                    trade_dict.update(dict(delivery_area=delivery_area_id,
                                           annotations=trade_data.get("annotations")))
                    for key in APITR.TradeRegulatoryData.valid_keys:
                        trade_dict[key] = trade_data.get(key)
                    trade_dict["terms"] = trade_data.get("terms")

                    if self.company_id == trade_data.get("aggressor_company_id", ""):
                        trade_dict.update({"direction": trade_data["aggressor_action"],
                                           "user": trade_data["aggressor_user_id"],
                                           "aggressor": COMMON.ActorType.true,
                                           "initiator": COMMON.ActorType.false,
                                           "counterparty": trade_data["initiator_company"],
                                           "trader_id": trade_data["aggressor_trader_id"],
                                           "trader_name": trade_data["aggressor_trader_name"]})
                        if self.company_id == trade_data.get("initiator_company_id", ""):
                            trade_dict.update({"initiator": COMMON.ActorType.true})
                        own_trade_message_struct["data"].append(trade_dict.copy())
                    elif self.company_id == trade_data.get("initiator_company_id", ""):
                        trade_dict.update({"direction": trade_data["initiator_action"],
                                           "user": trade_data["initiator_user_id"],
                                           "aggressor": COMMON.ActorType.false,
                                           "initiator": COMMON.ActorType.true,
                                           "counterparty": trade_data["aggressor_company"],
                                           "trader_id": trade_data["initiator_trader_id"],
                                           "trader_name": trade_data["initiator_trader_name"]})
                        own_trade_message_struct["data"].append(trade_dict)
                else:
                    # public
                    trade_dict["sell_delivery_area"] = delivery_area_id
                    trade_dict["buy_delivery_area"] = delivery_area_id
                    public_trade_message_struct["data"].append(trade_dict)
        elif struct["message_type"] == COMMON.Response.internal_trade:
            internal_trade_message_struct = struct

        strategy_callback = {"on_trade_update": []}
        if public_trade_message_struct["data"]:
            strategy_callback["on_public_trade_update"] = super(Trayport, self).update_from_json_on_trade(
                public_trade_message_struct, current_timestamp).get("on_public_trade_update", [])
        if own_trade_message_struct["data"]:
            log.debug("own_trades %s", own_trade_message_struct)
            strategy_callback["on_trade_update"] += super(Trayport, self).update_from_json_on_trade(
                own_trade_message_struct, current_timestamp).get("on_trade_update", [])
        if internal_trade_message_struct["data"]:
            log.debug("internal_trades %s", internal_trade_message_struct)
            strategy_callback["on_trade_update"] += super(Trayport, self).update_from_json_on_trade(
                internal_trade_message_struct, current_timestamp).get("on_trade_update", [])
        log.debug("Strategy callbacks %s", list(strategy_callback.keys()))
        return strategy_callback

    def _get_product_or_dummy_product(self, trade_data):
        """
        Given a trade data dictionary, as received from the connection manager,
        retrieve the corresponding product object.

        The current product is only returned, when the delivery period we would expect from the execution time
        corresponds to the product's delivery period. Otherwise, a dummy product is returned (and if needed generated)

        :param trade_data: Ths dictionary received from the connection manager.
        :type trade_data: dict
        :return: The product (if found)
        :rtype: APITR.Product or None
        """
        # find product using the instrument metadata
        product = self._get_product_by_data(trade_data, "trade")
        if product is None or product.sequence_id not in (COMMON.SequenceId.gas_prompt, COMMON.SequenceId.bom):
            return product
        trade_exec_time = (trade_data["execution_time"] // COMMON.HOUR + 0.5) * COMMON.HOUR
        try:
            prod_interval = self._get_prod_item_interval(trade_exec_time, trade_data["inst_specifier"][0])
        except KeyError:
            # Should never happen, except if we backload an old BOM product from MongoDB and don't have the
            # corresponding sequence item left in our memory. In which case skipping the trade because the product
            # was not found (due to it being too long in the past) is fine.
            return None
        if (prod_interval.delivery_start != product.delivery_start
                or prod_interval.delivery_end != product.delivery_end):
            if prod_interval.delivery_start > product.delivery_start:
                # Should never happen, unless clocks are out of sync
                # or we have a bug in trayport_items.py where we calculate the period
                log.error("Trade %s will be assigned to a dummy product in the future:"
                          " delivering from %s until %s, while the current product delivers from %s until %s."
                          " This should normally not happen and could indicate that the exchange's and the"
                          " server's clock are out of sync.",
                          trade_data["trade_id"],
                          ALCU.utc_ts2cet_str(prod_interval.delivery_start, True, True),
                          ALCU.utc_ts2cet_str(prod_interval.delivery_end, True, True),
                          ALCU.utc_ts2cet_str(product.delivery_start, True, True),
                          ALCU.utc_ts2cet_str(product.delivery_end, True, True))
            product = self._get_dummy_product(trade_exec_time, product,
                                              trade_data["inst_specifier"][0]["instrument_id"])
        return product

    def _validate_trade(self, trade, current_timestamp):
        """Validate trade received from the Trayport exchange

        Sometimes Trayport sends trades without a text field. As a result, such trades cannot be assigned to
        any strategy and the strategies may potentially fail to close the correct positions. In this case,
        the trade should not modify the product's trade lock and additionally add a tag-lock.

        If the received trade is internal trade, the product's trade_lock should be unlocked.

        :param trade: trade object to be validated
        :type trade: :class:`APITR.OwnTrade`
        :returns: True if the trade should unlock the trade_lock, False otherwise
        :rtype: bool
        """
        # special handling for internal trades, because internal trades have no broker_id and is_com_trader_order()
        # fails on internal trades
        if trade.aggressor_broker_id is None and trade.trade_id.startswith("internal"):
            return bool(trade.portfolio_key)
        # aggressor_broker_id and initiator_broker_id should always be the same, this is checked in
        # the trade object itself
        elif (
                not trade.portfolio_key
                and trade.user == self.autotrader_user
                and not trade.product.orders.is_com_trader_order(trade.order_id, broker_id=trade.aggressor_broker_id)
        ):
            # this is our trade, it must have some info on the portfolio, otherwise we lose track of our trading
            log.warning("Receiving trade without assigned strategy: %s", trade.trade_id)
            trade.product.tag_lock.add(trade.order_id, current_timestamp)
            return False
        else:
            trade.product.tag_lock.modify(trade.order_id, COMMON.InstanceLockState.confirm_one, current_timestamp)
            return not trade.product.orders.is_com_trader_order(trade.order_id, broker_id=trade.aggressor_broker_id)

    def _get_product_by_data(self, data, data_type):
        """
        retuns a Product depending on the instrument metadata. If nothing is found returns None
        :param data: data which is contained in the struct["data"] obtained by update_from_json
        :type data: dict
        :param data_type: string to represent order or trade for logs
        :type data_type: String
        :return: returns a Product if found, else None
        :rtype: None or Product
        """
        # find product using the instrument metadata
        inst_specifier = data["inst_specifier"][0]
        # VT-67030 fix to ignore sequence_span of 'Spread'. Currently only Single supported.
        sequence_span = inst_specifier["sequence_span"]
        if inst_specifier["sequence_span"] != 'Single':
            if self.is_parent:
                log.debug("Ignore %s for sequence_span '%s' : %s ", data_type, sequence_span, data)
            return None
        delivery_area_id = inst_specifier["instrument_id"]
        if delivery_area_id not in self.trayport_areas:
            if self.is_parent:
                log.debug("Delivery area %s is not configured for autoTRADER: skipping %s", delivery_area_id, data_type)
            return None
        metadata_dict = {
            "first_sequence_id": inst_specifier["first_sequence_id"],
            "first_item_id": inst_specifier["first_item_id"],
            "second_item_id": "0",
            "term_format_id": inst_specifier["term_format_id"]
        }
        product_id = u"{}_{}".format(metadata_dict["first_sequence_id"],
                                     metadata_dict["first_item_id"])
        try:
            product = self.products.get_by_id(product_id)
            if delivery_area_id not in list(product.delivery_area_states.keys()):
                raise COMMON.ProductNotFound
        except COMMON.ProductNotFound:
            log.warning("No product found for %s in area %s with market metadata %s",
                        data_type, delivery_area_id, metadata_dict)
            return None
        return product

    def update_from_json_on_order(self, struct, current_timestamp, confirm_lock=None):
        own_order_message_struct = dict(exchange=COMMON.Exchange.trayport,
                                        message_type="order_execution",
                                        timestamp=current_timestamp,
                                        data=[])
        public_order_message_struct = dict(exchange=COMMON.Exchange.trayport,
                                           message_type="order_book",
                                           timestamp=current_timestamp,
                                           data=[])
        if struct["message_type"] == "order_book":
            for order_data in struct["data"]:
                if order_data["implied"]:
                    order_data["is_tradable"] = False

                product = self._get_product_by_data(order_data, "order")
                if not product:
                    continue

                initial_order_id = order_data["initial_order_id"]
                order_id = order_data["order_id"]
                broker_id = order_data.get("broker_id", None)
                if order_data["order_id"] != initial_order_id:
                    self._deleted_order_ids.add((initial_order_id, broker_id))

                if (order_id, broker_id) in self._deleted_order_ids:
                    log.warning("Order with order_id: %s and broker_id: %s was ignored since it was previously deleted",
                                order_id, broker_id)
                    continue

                # user determines if that is an own order or not
                order_dict = dict(order_id=order_data["order_id"],
                                  delivery_area_id=order_data["inst_specifier"][0]["instrument_id"],
                                  direction=order_data["direction"],
                                  revision=order_data["timestamp"],  # revision nr is not in the API, we use exchange ts
                                  price=order_data["price"],
                                  quantity=order_data["quantity"],
                                  timestamp=order_data["timestamp"],
                                  engine_id=order_data["engine_id"],
                                  system_rank=order_data["system_rank"],
                                  is_tradable=order_data["is_tradable"],
                                  implied=order_data["implied"],
                                  counter_party_ok=order_data["counter_party_ok"],
                                  execution_restriction=order_data["execution_restriction"],
                                  broker_id=order_data["broker_id"],
                                  terms=order_data.get("terms", []),
                                  route_id=order_data.get("route_id"),
                                  )
                if not order_data.get("account") or self.company_id == order_data["account"]:
                    # this is an own order
                    if (
                            order_data["action"] == COMMON.OrderAction.queried
                            and order_data["user_id"] == self.autotrader_user
                    ):
                        inst_specifier = product.market_meta_information
                        inst_specifier["instrument_id"] = order_data["inst_specifier"][0]["instrument_id"]
                        order_to_remove = dict(order_id=order_data["order_id"],
                                               engine_id=order_data["engine_id"],
                                               broker_id=order_data["broker_id"],
                                               inst_specifier=[product.market_meta_information],
                                               txt=order_data["txt"])
                        self.orders_to_remove.append(order_to_remove)
                    action = order_data["action"]
                    if action == COMMON.OrderAction.modified and order_data["traded"]:
                        # partial execution
                        action = COMMON.OrderAction.partial_execution
                        order_dict["traded_order_id"] = order_data["initial_order_id"]
                    elif action == COMMON.OrderAction.deleted and order_data["traded"]:
                        action = COMMON.OrderAction.full_execution
                        order_dict["traded_order_id"] = order_data["order_id"]
                    order_dict.update(
                        dict(initial_order_id=order_data["initial_order_id"],
                             product_id=product.product_id,
                             action=action,
                             state=order_data["state"],
                             type=order_data["type"],
                             txt=order_data["txt"],
                             initial_quantity=0.,
                             visible_quantity=order_data.get("visible_quantity"),
                             account=order_data["account"],
                             user=order_data["user_id"],
                             last_update_user="",
                             validity_restriction=order_data["validity_restriction"],
                             validity_date=order_data["validity_date"],
                             trading_account=order_data.get("trading_account"))
                    )
                    for key in APITR.OrderRegulatoryData.valid_keys:
                        order_dict[key] = order_data.get(key)
                    own_order_message_struct["data"].append(order_dict)
                else:
                    # public
                    order_dict["product_id"] = product.product_id
                    if order_data["action"] == COMMON.OrderAction.modified:
                        # If the modification has changed the order id (initial_order_id is OldOrderId
                        # in Trayport terminology), then we have to delete the old order.
                        # NOTE: for own orders, this is handled by OrderBook._find_and_delete_orders
                        if order_data["initial_order_id"] != order_data["order_id"]:
                            order_dict_del = order_dict.copy()
                            order_dict_del["action"] = COMMON.OrderAction.deleted
                            order_dict_del["order_id"] = order_data["initial_order_id"]
                            order_dict_del["quantity"] = 0
                            public_order_message_struct["data"].append(order_dict_del)
                    elif order_data["action"] == COMMON.OrderAction.deleted:
                        order_dict["quantity"] = 0
                    public_order_message_struct["data"].append(order_dict.copy())
        elif struct["message_type"] == COMMON.Response.order_execution:
            own_order_message_struct["data"] = struct["data"]

        confirm_lock = COMMON.InstanceLockState.confirm_all
        own_callback = super(Trayport, self).update_from_json_on_order(
            own_order_message_struct, current_timestamp, confirm_lock)
        pub_callback = super(Trayport, self).update_from_json_on_order(
            public_order_message_struct, current_timestamp, confirm_lock)
        modified_objects = own_callback.get("on_order_book_update", []) + pub_callback.get("on_order_book_update", [])
        return {"on_order_book_update": modified_objects}

    @staticmethod
    def _public_orders_by_price_and_rank(own_order, orders):
        """ Return a generator with the sorted orders according to own_order.direction and remove the
            ones that will not be matched

        :param own_order: the order we want to find a match for
        :type own_order: `APITR.OwnOrder`
        :param orders: the list of orders that we want to look through (like the public orders)
        :type orders: list of `APITR.Order`
        :return:
        """

        need_reverse = own_order.direction != COMMON.Direction.buy

        sorted_orders = sorted(
            orders,
            key=lambda val: (val.price, (-1 if need_reverse else 1) * int(val.system_rank if val.system_rank else "0")),
            reverse=need_reverse
        )
        for order in sorted_orders:
            if (
                not order.is_tradable
                or (own_order.execution_restriction == COMMON.ExecutionRestriction.fok
                    and own_order.quantity > order.quantity)
            ):
                continue

            if (
                    own_order.direction == COMMON.Direction.buy
                    and round(own_order.price, 3) < round(order.price, 3)
                    or own_order.direction == COMMON.Direction.sell
                    and round(own_order.price, 3) > round(order.price, 3)
            ):
                return
            else:
                yield order

    def _match_helper(self, orders_to_match, order, product, current_timestamp):
        """ Returns a copy of the orders_to_match parameter with the orders matching the orders_to_match param

        :param orders_to_match: dict with "entry_orders", "modify_orders" etc. where we want to find our match
        :type orders_to_match: dict
        :param order: the order we want to match
        :type order: `APITR.OwnOrder`
        :param product: the corresponding product
        :type product: `APITR.Product`
        :return: dict with "entry_orders", "modify_orders", etc. or None if no match was found
        :rtype dict or None
        """
        found_orders_to_match = orders_to_match.copy()
        public_orders = self._get_available_public_orders_for_order(order, product)
        return self._match_order_with_best_public_order(public_orders, found_orders_to_match, order, current_timestamp)

    def _get_available_public_orders_for_order(self, order, product):
        """for the given order, returns a generator with possible matching public orders

        :param order: the order we want to match
        :type order: `APITR.OwnOrder`
        :param product: the corresponding product
        :type product: `APITR.Product`
        :return: Return a generator with possible matching orders
        """
        broker_id = None
        if not self.aggress_other_brokers:
            broker_id = order.broker_id
        if order.direction == COMMON.Direction.sell:
            buy_orders = product.orders.get(delivery_area_id=order.delivery_area_id,
                                            order_filter=COMMON.OrderFilter.public_buy, broker_id=broker_id)
            public_orders = self._public_orders_by_price_and_rank(order, buy_orders)
        else:
            sell_orders = product.orders.get(delivery_area_id=order.delivery_area_id,
                                             order_filter=COMMON.OrderFilter.public_sell, broker_id=broker_id)
            public_orders = self._public_orders_by_price_and_rank(order, sell_orders)
        return public_orders

    def _match_order_with_best_public_order(self, public_orders, found_orders_to_match, own_order, current_timestamp):
        """ Returns a copy of the orders_to_match parameter with the orders matching the orders_to_match param.
        IOC and FOK orders are deleted, if no order can be matched.

        :param public_orders: generator with the sorted orders according to own_order.direction
        :type public_orders: Generator[APITR.Order, None, None]
        :param own_order: the order we want to match
        :type own_order: `APITR.OwnOrder`
        :param found_orders_to_match: dict with "entry_orders", "modify_orders" etc. where we want to find our match
        :type found_orders_to_match: dict
        :return: dict with "entry_orders", "modify_orders", etc. or None if no match was found
        :rtype dict or None
        """
        for public_order in public_orders:
            if (
                (public_order.execution_restriction == COMMON.ExecutionRestriction.aon
                    and public_order.quantity > own_order.quantity)
                or not self.is_broker_connected(public_order.broker_id)
            ):
                log.debug("Cannot aggress public order %s (qty=%s, %s) from own order %s (qty=%s, %s) "
                          "on broker %s (connected=%s)", public_order.order_id,
                          public_order.quantity, public_order.execution_restriction, own_order.internal_id,
                          own_order.quantity, own_order.execution_restriction,
                          public_order.broker_id, self.is_broker_connected(public_order.broker_id))
                continue

            # Round the quantity to the tick size
            key = "{}_{}_{}".format(public_order.broker_id,
                                    public_order.delivery_area_id,
                                    public_order.product.product_id)
            try:
                property = self.trayport_properties[key]
            except KeyError:
                # Should usually not happen in production, as we should query for all
                # relevant instrument properties on init. But there is no hard guarantee that JD won't send us
                # public orders for new brokers (e.g. if the venue connection state changed),
                # so we have to handle this case.
                log.warning("Cannot aggress public order %s on broker %s, as we lack the instrument properties "
                            "for key %s", public_order.order_id, public_order.broker_id, key)
                # Continue means: ignore this public order, look for the next.
                continue

            tradable_quantity = ALU.round_qty_to_ticksize(min(own_order.quantity,
                                                              public_order.quantity), property.qty_tick)
            if tradable_quantity < property.min_quantity:
                log.debug("Cannot match public order %s on broker %s from own order %s, because the "
                          "quantity %s is below the minimum quantity of %s", public_order.order_id,
                          public_order.broker_id, own_order.internal_id, tradable_quantity,
                          property.min_quantity)
                continue
            if (own_order.execution_restriction in (COMMON.ExecutionRestriction.aon,
                                                    COMMON.ExecutionRestriction.fok)
                    and own_order.quantity > tradable_quantity):
                log.debug("Cannot match public order %s on broker %s from own order %s, because the "
                          "tradable quantity %s is below the own order qty %s and the execution restriction is %s",
                          public_order.order_id, public_order.broker_id, own_order.internal_id, tradable_quantity,
                          own_order.quantity, own_order.execution_restriction)
                continue

            if public_order.broker_id in self.brokers_without_tradeorders:
                if own_order.broker_id == public_order.broker_id:
                    self._aggress_via_automatching(found_orders_to_match, own_order, public_order)
                else:
                    self.aggress_via_ioc(found_orders_to_match, own_order, public_order, tradable_quantity)
            else:
                self._aggress_via_tradeorder(found_orders_to_match, own_order, public_order,
                                             tradable_quantity, current_timestamp)
            log.debug("MATCH ORDERS PUBLIC\n%s", public_order)
            # found_orders_to_match were modified in-place by one of the _aggress_via_* functions.
            return found_orders_to_match

        # filter out IOC orders that do not get matched and delete them
        if own_order.execution_restriction in COMMON.ExecutionRestriction.trayport_trade_orders:
            # release the vault of this order, since it is cancelled
            self._vault.modify(own_order.internal_id, COMMON.InstanceLockState.confirm_all,
                               current_timestamp)
            found_orders_to_match[COMMON.ResolverState.internal_order_executions].extend(
                autotrader_core.utils.internal_order_execution(COMMON.OrderAction.deleted, [own_order]))
            del found_orders_to_match[COMMON.ResolverState.entry_orders]
            del found_orders_to_match[COMMON.ResolverState.modify_orders]
            log.debug("Order {} on product {} with execution restriction {} rejected: no matching public order"
                      "".format(own_order.internal_id, own_order.product.product_id, own_order.execution_restriction))
            return found_orders_to_match

        return None

    def _aggress_via_tradeorder(self, found_orders_to_match, own_order, public_order,
                                tradable_quantity, current_timestamp):
        """
        Modify found_orders_to_match in-place, so that we aggress the given public order with a TradeOrder

        :param found_orders_to_match: The defaultdict with the currently planned orders.
        :type found_orders_to_match: dict[list]
        :param own_order: The own order which matches the public order
        :type own_order: APITR.OwnOrder
        :param public_order: The public order we want to aggress
        :type public_order: APITR.PublicOrder
        :param tradable_quantity: The quantity which we want to aggress.
                                  The calling function has to make sure it fits with the public and own order quantity
                                  and the relevant instrument properties
        :type tradable_quantity: float or int
        :param current_timestamp: autoTRADER's current unix timestamp
        :type current_timestamp: float or int

        :return: None. found_orders_to_match is modified in-place
        :rtype: None
        """
        if own_order in found_orders_to_match[COMMON.ResolverState.modify_orders]:
            found_orders_to_match[COMMON.ResolverState.delete_orders].append(own_order)
        else:
            own_order.tags[COMMON.OrderTagKeys.product_id] = own_order.product.product_id
            found_orders_to_match[COMMON.ResolverState.trade_orders] = [
                self._TradeOrder(public_order.order_id, public_order.engine_id, tradable_quantity,
                                 public_order.product.product_id, own_order.tags, public_order.broker_id,
                                 own_order.trading_capacity, own_order.decision_maker, own_order.execution_maker,
                                 own_order.derivative_indicator, own_order.dea, own_order.dea_client_id,
                                 own_order.liquidity_provision, own_order.trading_account)
            ]
            # The matched entry order should be processed accordingly:
            # (i) send an order execution for the matched entry order;
            # (ii) send trade lock for the matched public_order;
            # (iii) release the vault for the matched entry order.
            found_orders_to_match[COMMON.ResolverState.internal_order_executions].extend(
                autotrader_core.utils.internal_order_execution(COMMON.OrderAction.deleted, [own_order]))
            found_orders_to_match[COMMON.ResolverState.internal_trade_lock].append(own_order)
            self._vault.modify(own_order.internal_id, COMMON.InstanceLockState.confirm_all,
                               current_timestamp)
        del found_orders_to_match[COMMON.ResolverState.entry_orders]
        del found_orders_to_match[COMMON.ResolverState.modify_orders]

    def aggress_via_ioc(self, found_orders_to_match, own_order, public_order, tradable_quantity):
        """
        Modify found_orders_to_match in-place, so that we aggress the given public order by sending an IOC order

        Note that the IOC execution restriction is implemented in our Joule Direct connection manager
        as virtual IOC order.

        :param found_orders_to_match: The defaultdict with the currently planned orders.
        :type found_orders_to_match: dict[list]
        :param own_order: The own order which matches the public order
        :type own_order: APITR.OwnOrder
        :param public_order: The public order we want to aggress
        :type public_order: APITR.PublicOrder
        :param tradable_quantity: The quantity which we want to aggress.
                                  The calling function has to make sure it fits with the public and own order quantity
                                  and the relevant instrument properties
        :type tradable_quantity: float or int

        :return: None. found_orders_to_match is modified in-place
        :rtype: None
        """
        if own_order in found_orders_to_match[COMMON.ResolverState.modify_orders]:
            found_orders_to_match[COMMON.ResolverState.delete_orders].append(own_order)
            del found_orders_to_match[COMMON.ResolverState.entry_orders]
        else:
            log.debug("aggress_other_brokers: Setting IOC restriction on own order request %s to match "
                      "public order (%s) on broker (%s). Setting qty to %s", own_order.internal_id,
                      public_order.order_id, public_order.broker_id, tradable_quantity)

            # Modify price and quantity, to make sure they are both valid
            # according to the target broker's instrument properties.
            aggressing_order = own_order.modify(quantity=tradable_quantity,
                                                price=public_order.price,
                                                trading_account=None)
            aggressing_order.broker_id = public_order.broker_id
            aggressing_order.execution_restriction = COMMON.ExecutionRestriction.ioc

            # When an order execution message comes that gives this order an order_id,
            # we need to know the original broker so OrderBook.update_from_json can
            # remove the unconfirmed order from the correct broker.
            aggressing_order.tags[COMMON.OrderTagKeys.internal_orders_broker_id] = own_order.broker_id
            found_orders_to_match[COMMON.ResolverState.entry_orders] = [aggressing_order]
        del found_orders_to_match[COMMON.ResolverState.modify_orders]

    def _aggress_via_automatching(self, found_orders_to_match, own_order, public_order):
        """
        Modify found_orders_to_match in-place, so that only the own_order is sent to the exchange to auto-match

        All other entry and modify orders are not sent in this iteration, as they should be sent after the
        trade has arrived.

        :param found_orders_to_match: The defaultdict with the currently planned orders.
        :type found_orders_to_match: dict[list]
        :param own_order: The own order which matches the public order
        :type own_order: APITR.OwnOrder
        :param public_order: The public order we want to aggress
        :type public_order: APITR.PublicOrder

        :return: None. found_orders_to_match is modified in-place
        :rtype: None
        """
        log.debug("Own order request %s matches public order (%s) on the same broker (%s) for which "
                  "trade orders are disabled. Sending as normal order request", own_order.internal_id,
                  public_order.order_id, public_order.broker_id)
        # Send this order as a regular order, don't send any other order (they might match
        # in the next iteration)
        # own_order must be either in the entry order or modify orders list.
        if own_order in found_orders_to_match[COMMON.ResolverState.modify_orders]:
            found_orders_to_match[COMMON.ResolverState.modify_orders] = [own_order]
            del found_orders_to_match[COMMON.ResolverState.entry_orders]
        else:
            found_orders_to_match[COMMON.ResolverState.entry_orders] = [own_order]
            del found_orders_to_match[COMMON.ResolverState.modify_orders]

    def match_orders(self, orders_to_match, product, current_timestamp=None):
        """Finds a possible match between one of the (own) entry or modify orders and
        front public order for creating a trade.

        This is necessary for OTC venues which don't support automatching, but is also done for some automatching venues

        :param orders_to_match: defaultdict with "entry_orders", "modify_orders" etc.
                                to be checked for potential trades.
        :type orders_to_match: defaultdict[str, list]
        :param product: the corresponding product
        :type product: `APITR.Product`
        :param current_timestamp: current timestamp
        :type current_timestamp: float
        :returns: dict with additional "trade_orders" key, if match was found
        :rtype: dict
        """
        matching_orders = (
            orders_to_match[COMMON.ResolverState.entry_orders] + orders_to_match[COMMON.ResolverState.modify_orders]
        )
        self.local_random.seed(sum(order.quantity + order.price for order in matching_orders))
        self.local_random.shuffle(matching_orders)
        for order in matching_orders:
            new_orders = self._match_helper(orders_to_match, order, product, current_timestamp)
            if new_orders:
                orders_to_match = new_orders
                break

        return orders_to_match

    def remove_old_products(self):
        """Restarts the Trayport exchange to remove old and create new synthetic products

        Creation of new(next) synthetic products on Trayport is not provided by the exchange as well as expiry of
        the old ones. We, therefore, should be sure, that the old products are removed and new synthetic products
        are added and activated (see criteria in update_from_json_on_sequence_items). This is assured by enforcing
        the restart of the exchange.
        """
        raise COMMON.RestartExchangeException(COMMON.Exchange.trayport, "restart exchange for removing old products")

    def _iter_expired_products(self, timestamp):
        """
        Iter over all products for which trading is no longer possible.

        For these products, we can clear-out the orderbook.

        :param timestamp: The current timestamp of autotrader (real time or simulation time)
        :type timestamp: float
        """
        for product in super(Trayport, self)._iter_expired_products(timestamp):
            # Do not expire the orderbook for prompt products
            if product.sequence_id in (COMMON.SequenceId.bom, COMMON.SequenceId.gas_prompt):
                continue
            yield product
