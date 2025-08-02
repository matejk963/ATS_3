#!/usr/bin/python3
# -*- coding: utf-8 -*-
from __future__ import absolute_import
import collections
import logging

import autotrader_lib.common as COMMON
import autotrader_core.conflict_resolver
import autotrader_core.exchange_trading as APITR
import autotrader_core.utils as AUTILS

LOGGER = logging.getLogger("autotrader.internal_market")


def remove_internal_only(func):
    """ This decorator function removes orders with internal_only execmode
    from the orders_to_send dict and converts it to a defaultdict
    """

    def func_wrapper(*args, **kwargs):
        orders_to_check = func(*args, **kwargs)
        orders_to_send = collections.defaultdict(list)
        for order_type, orders in orders_to_check.items():
            if order_type not in COMMON.ResolverState.internal_messages:
                orders = [order for order in orders
                          if order.execmode != COMMON.InternalExecutionMode.internal_only]
            orders_to_send[order_type] = orders
        return orders_to_send

    return func_wrapper


def sort_helper(order_entries, consider_tolerance=True):
    """Helper function to sort the order entries by price and direction.

    Sorting of the order entries is performed by price and in addition,
    if the prices of two orders are the same, buy orders follow sell orders.

    :param consider_tolerance: bool flag,
                if True, internal_market_price will be considered,
                if False, price will be considered
    :param order_entries: list of order entries of :class:`COMMON.OrderEntry` type
    :type order_entries: list

    :returns: list -- Sorted list of order entries
    """
    if consider_tolerance:
        return sorted(order_entries,
                      key=lambda val: (round(-val.order.internal_market_price, 3), val.order.direction),
                      reverse=True)
    return sorted(order_entries,
                  key=lambda val: (round(-val.order.price, 3), val.order.direction),
                  reverse=True)


class OrderConflict(object):
    """Defines an order conflict object.

    The order conflict arises when the left most sell order has lower
    price than right most buy order. If such two orders would appear at the
    exchange, they would create a so-called cross-trade, i.e. a trade with itself.

    :param list order_entries: list of order entries
    """

    def __init__(self, order_entries, consider_tolerance=True):
        """

        :param order_entries: list of planned order entries
        :param consider_tolerance: bool flag,
                if True, internal_market_price will be considered,
                if False, price will be considered
        """
        self.consider_tolerance = consider_tolerance
        self.order_entries = order_entries

    def _order_index(self, order_direction):
        order_entries = reversed(self.order_entries) if order_direction == COMMON.Direction.buy else self.order_entries
        for i, order_entry in enumerate(order_entries):
            if order_entry.order.direction == order_direction:
                return i
        return None

    def find(self):
        """Finds two indexes of orders in the order conflict: for the left most sell order and for the right most buy
        order according to price

        :return: tuple with sell and buy order indexes of conflicting orders
        :rtype: Tuple[int, int] or Tuple[None, None]
        """
        ind_sell = self._order_index(COMMON.Direction.sell)
        ind_buy = self._order_index(COMMON.Direction.buy)

        if ind_sell is None or ind_buy is None:
            return None, None

        ind_buy = len(self.order_entries) - ind_buy - 1

        if self.consider_tolerance:
            if (
                    ind_sell < ind_buy
                    or self.order_entries[ind_sell].order.internal_market_price
                    == self.order_entries[ind_buy].order.internal_market_price
            ):
                return ind_sell, ind_buy
            else:
                return None, None
        elif ind_sell < ind_buy or self.order_entries[ind_sell].order.price == self.order_entries[ind_buy].order.price:
            return ind_sell, ind_buy
        return None, None


class OrderConflictFinder(object):
    """Finds order conflicts

    On initialization of the object a combined orders list is created,
    which holds the orders as of "should" state, i.e. it holds the updated
    orders from the actual orders list combined with the orders in
    the requested_order_dict.
    Knowing the combined_orders, the algorithm is able to determine the
    orders potentially leading to the cross trade, once sent to the exchange.
    One is able to find conflicts by calling the object directly or
    by calling the object function :func:`find_conflicting_orders`.

    The object
    than returns sell order, buy order and common execution mode of the
    found conflict

    :cvar global_mode: :class:`COMMON.GlobalInternalMarketMode`
    :cvar list combined_orders: list with merge actual and requests orders

    .. seealso:: :func:`OrderConflictFinder.find_conflicting_orders`
    """

    def __init__(self, global_mode=COMMON.GlobalInternalMarketMode.default, aggress_other_brokers=True):
        self.aggress_other_brokers = aggress_other_brokers
        self.global_mode = global_mode
        self.combined_orders = []  # list with merge actual and requests orders

    def __call__(self, product, actual_orders, requested_order_dict, timestamp,
                 combined_orders=None, brokers_without_hibernation=None, consider_tolerance=True):
        """

        :param product: member of :class:`APITR.Product`
        :param list actual_orders: list of all actual own orders being accepted by the exchange
        :param dict requested_order_dict: order requested by the strategies to be added/modified/deleted.
        :param float timestamp: current timestamp
        :param combined_orders: list with merge actual and requests orders. If None, the list will be created from
                                the actual and requested orders
        :param frozenset brokers_without_hibernation: Set of broker ids where autotrader cannot hibernate manual orders
        :param bool consider_tolerance: specifies if the conflict resolvement should be done by taking into account
                                        the internal market prices
        :return:
        """
        if brokers_without_hibernation is None:
            brokers_without_hibernation = frozenset()
        if combined_orders is None:
            combined_orders = self.combine_into_planned_order_entries(actual_orders, requested_order_dict)
        return self.find_conflicting_orders(product, combined_orders, timestamp,
                                            brokers_without_hibernation=brokers_without_hibernation,
                                            consider_tolerance=consider_tolerance)

    @staticmethod
    def combine_into_planned_order_entries(actual_orders, requested_order_dict):
        """Creates a list of aggregated order entries between
        actual and requested orders

        This function goes through a list of actual orders and a dictionary
        of requested orders to combine them together and form a list
        of planned order entries.
        This list consist of Order entries (:class:`COMMON.OrderEntry`) containing
        information about the orders and their status with respect to the exchange.
        The order status can be any of the status described
        in :class:`COMMON.InternalOrderStatus`:

        * entered - "E";
        * modified - "M";
        * unchanged - "U";
        * old - "O";         # The order before a modification or deletion is applied.
        * hibernated - "H";
        * active - "A".

        The last two apply only for the com trader orders.

        The status "E" is applicable only for the entry orders in the
        requested order dictionary. An order acquires status "U", if
        it is present in the actual orders list or in addition
        in the requested orders dictionary under the delete_orders key.
        An order acquires status "M", if it is present in both actual
        orders list and requested orders dictionary under the
        modify_orders key. The status of the com trader orders is defined
        by their internal state: active or hibernated.

        :param list actual_orders: list of all own orders as of the "Is"-state
        :param dict requested_order_dict: dictionary of orders to be added/modified/deleted:
                            a wish-list of all strategies. The dictionary keys
                            correspond to the requested by the strategies action:
                            "delete_orders", "modify_orders", "entry_orders"
        :returns combined_orders: sorted list of planned order entries, i.e. a list
                                       of actual orders and
                                       requested orders combined together
                                       with the corresponding "Should"-state
                                       at the exchange.
        :rtype: list
        """
        if not actual_orders and not requested_order_dict:
            return []
        # append all entry orders (status="E")
        combined_orders = [COMMON.OrderEntry(COMMON.InternalOrderStatus.entered, order)
                           for order in requested_order_dict.get(COMMON.ResolverState.entry_orders, [])
                           if order.execmode != COMMON.InternalExecutionMode.skip]
        for order in actual_orders:
            if order.execmode == COMMON.InternalExecutionMode.skip:
                continue
            unchanged = True
            for new_ord in requested_order_dict.get(COMMON.ResolverState.modify_orders, []):
                if order.internal_id == new_ord.internal_id:
                    # add the new modified order to the list (status = "O" for old state, status="M" for new state)
                    combined_orders.append(
                        COMMON.OrderEntry(COMMON.InternalOrderStatus.old, order))
                    combined_orders.append(
                        COMMON.OrderEntry(COMMON.InternalOrderStatus.modified, new_ord))
                    unchanged = False
                    break
            if not unchanged:
                continue
            if unchanged:
                # If the order is neither modified nor deleted, add the
                # original unchanged order to the list (status="U")
                if isinstance(order, APITR.ComTraderOrder):
                    if order.state == COMMON.OrderState.hibe:
                        combined_orders.append(
                            COMMON.OrderEntry(COMMON.InternalOrderStatus.hibernated, order))
                    elif order.state == COMMON.OrderState.acti:
                        combined_orders.append(
                            COMMON.OrderEntry(COMMON.InternalOrderStatus.active, order))
                else:
                    combined_orders.append(
                        COMMON.OrderEntry(COMMON.InternalOrderStatus.unchanged, order))
        # Return combined orders sorted by price and by direction, so if
        # sell and buy order have the same price, the sell order goes before
        # the buy order:
        # sort by internal market price, because these orders will go into the internal market, not the exchange
        return combined_orders

    @staticmethod
    def get_execution_mode(sell_ord_execmode, buy_ord_execmode):
        """Get the combined execution mode of the two orders in the conflict

        If two orders have different internal execution modes, the common
        execution mode is determined by the execution mode with the highest priority.
        The priority is set as follows (from highest to lowest):

        * :class:`COMMON.InternalExecutionMode.internal_only`
        * :class:`COMMON.InternalExecutionMode.no`
        * :class:`COMMON.InternalExecutionMode.exchange_base_price`
        * :class:`COMMON.InternalExecutionMode.average_base_price`

        :param sell_ord_execmode: internal execution mode of the sell orders
        :type sell_ord_execmode: :class:`COMMON.InternalExecutionMode`
        :param buy_ord_execmode: internal execution mode of the buy orders
        :type buy_ord_execmode: :class:`COMMON.InternalExecutionMode`

        :returns execmode: common execution mode
        :rtype: :class:`COMMON.InternalExecutionMode`

        .. seealso:: available status in :class:`COMMON.InternalExecutionMode`
        """
        execmodes = [sell_ord_execmode, buy_ord_execmode]
        if any(execmode == COMMON.InternalExecutionMode.no for execmode in execmodes):
            emode = COMMON.InternalExecutionMode.no
        elif any(execmode == COMMON.InternalExecutionMode.exchange_base_price for execmode in execmodes):
            # If one of the execmode is exchange_base_price, use combined
            # exchange_base_price execution
            emode = COMMON.InternalExecutionMode.exchange_base_price
        elif all(execmode == COMMON.InternalExecutionMode.average_price for execmode in execmodes):
            emode = COMMON.InternalExecutionMode.average_price
        else:
            emode = COMMON.InternalExecutionMode.default
        return emode

    def find_conflicting_orders(self, product, planned_order_entries, timestamp, brokers_without_hibernation,
                                consider_tolerance=True):
        """The function finds two conflicting orders in the list of planned orders.

        :params list planned_order_entries: list of planned order entries
                                            sorted by price and order direction.

        :returns (sell_order_entry, buy_order_entry, execution): returns found
                            sell and buy order entries forming an order conflict
                            as well as their common execution mode. If no conflict is found
                            `(None, None, None)` is returned

        .. seealso:: :func:`APITR.Product.zones_joined`
        """

        # because planned_order_entries are sorted by price and not internal price,
        # we have to sort them again to make sure to find conflicts based on the internal prices
        planned_order_entries = sort_helper(planned_order_entries, consider_tolerance=consider_tolerance)
        area_order_entries = collections.defaultdict(list)

        for orderentry in planned_order_entries:
            order_area = orderentry.order.delivery_area_id
            area_order_entries[orderentry.order.delivery_area_id].append(orderentry)

            if order_area in COMMON.Area.de_zone:
                area_order_entries["germany"].append(orderentry)

        # special handling for germany:
        # to avoid unneeded lookups, we remove the combined zone of germany if skip_de is deactivated, or
        # the product cannot be transferred between the german areas (if less than 30 min left until delivery_start)
        # or if we do not have a timestamp yet.
        if (timestamp is None
                or product.delivery_start - timestamp <= COMMON.DE_ZONES_JOINED_UNTIL_SEC_BEFORE_DELIVERY
                or self.global_mode == COMMON.GlobalInternalMarketMode.skip_de):
            area_order_entries.pop("germany", None)
        else:
            # if it is still possible to trade between german areas, we remove all single areas and just use the
            # area "germany" where all german orders are present.
            for area in COMMON.Area.de_zone:
                area_order_entries.pop(area, None)

        area_order_entries = sorted(area_order_entries.items())
        # loop over all orders in their respective area and find the first order conflict
        for key, sorted_orders in area_order_entries:
            if len(sorted_orders) > 1:
                conflict = self._find_next_conflict(product, sorted_orders, timestamp, brokers_without_hibernation,
                                                    consider_tolerance)
                if conflict != (None, None, None):
                    return conflict

        return None, None, None

    def _find_next_conflict(self, product, sorted_orders, timestamp, brokers_without_hibernation, consider_tolerance):
        """
        helper function to search for the first conflict in the sorted_orders, if there is any.
        The function uses :class:`OrderConflict` as conflict iterator
        for finding left most sell and right most buy orders in the list of sorted orders. However,
        if both orders have common execution mode
        :class:`COMMON.InternalExecutionMode.no` and status
        :class:`COMMON.InternalOrderStatus.hibernated`, the next order
        conflict is considered. On special occasions (see unresolvable_exposed_conflict and block_cross_broker)
        the algorithm runs the function recursively to find the next possible conflict.

        :param product: The product of the orders
        :type product: APITR.Product
        :param sorted_orders: list of orders sorted by internal market price/or price, depending on consider_tolerance
        :type sorted_orders:  list
        :param timestamp: current timestamp
        :type timestamp: float
        :param brokers_without_hibernation: Set of broker ids where autotrader cannot hibernate manual orders.
        :type brokers_without_hibernation: frozenset
        :param consider_tolerance: flag,
                if True, internal_market_price will be considered for sorting orders,
                if False, price will be considered
        :type consider_tolerance: bool
        :return: sell_order_entry, buy_order_entry, execmode
        :rtype: tuple
        """

        order_conflict = OrderConflict(sorted_orders, consider_tolerance=consider_tolerance)
        found_ind_sell, found_ind_buy = order_conflict.find()
        if found_ind_buy is not None and found_ind_sell is not None:
            sell_order_entry = sorted_orders[found_ind_sell]
            buy_order_entry = sorted_orders[found_ind_buy]

            execution = self.get_execution_mode(sell_order_entry.order.execmode,
                                                buy_order_entry.order.execmode)
        else:
            return None, None, None

        # Conflicts between a hibernated and an old order can be ignored,
        # but either of the two orders can be in a different conflict.
        # The same applies for old vs Unchanged/Active on OTC markets
        unresolvable_exposed_conflict = self._is_conflict_on_exchange_and_unresolvable(brokers_without_hibernation,
                                                                                       buy_order_entry,
                                                                                       sell_order_entry)

        # self.aggress_other_brokers:
        #     - True -> do never block internal market based on broker ids
        #     - False -> only block internal market, if the broker id of both orders is different
        block_cross_broker = (
            not self.aggress_other_brokers
            and sell_order_entry.order.broker_id != buy_order_entry.order.broker_id
        )

        if block_cross_broker:
            LOGGER.debug(("conflicting orders are played via different brokers, "
                          "but aggress_other_brokers parameter is False\n"
                          "SELL %s: %s (broker: %s);\n BUY %s: %s (broker: %s)\n"
                          "trying to find another conflict"),
                         sell_order_entry.order.delivery_area_id, sell_order_entry, sell_order_entry.order.broker_id,
                         buy_order_entry.order.delivery_area_id, buy_order_entry, buy_order_entry.order.broker_id)
        if unresolvable_exposed_conflict:
            LOGGER.debug(("ignoring conflict already on the exchange\n"
                          "SELL %s: %s;\n BUY %s: %s\n"
                          "trying to find another conflict"),
                         sell_order_entry.order.delivery_area_id, sell_order_entry,
                         buy_order_entry.order.delivery_area_id, buy_order_entry)
        if unresolvable_exposed_conflict or block_cross_broker:
            # If sell index is higher than buy index, then
            if found_ind_sell >= found_ind_buy:
                return None, None, None
            # Find conflicting orders without the buy_order_entry
            new_orders = sorted_orders[found_ind_sell:found_ind_buy]
            found_buy_index_increment_orders = self._find_next_conflict(
                product, new_orders, timestamp, brokers_without_hibernation, consider_tolerance=consider_tolerance)
            # Find conflicting orders without the sell_order_entry
            new_orders = sorted_orders[found_ind_sell + 1:found_ind_buy + 1]
            found_sell_index_increment_orders = self._find_next_conflict(
                product, new_orders, timestamp, brokers_without_hibernation, consider_tolerance=consider_tolerance)
            if found_buy_index_increment_orders[0] and found_sell_index_increment_orders[0]:
                price_buy_from_buy = found_buy_index_increment_orders[1].order.internal_market_price
                price_buy_from_sell = found_sell_index_increment_orders[1].order.internal_market_price
                if price_buy_from_buy >= price_buy_from_sell:
                    return found_buy_index_increment_orders
                return found_sell_index_increment_orders
            elif found_buy_index_increment_orders[0]:
                return found_buy_index_increment_orders
            elif found_sell_index_increment_orders[0]:
                return found_sell_index_increment_orders
            return None, None, None
        elif execution == COMMON.InternalExecutionMode.no:
            sell_stat = sell_order_entry.status
            buy_stat = buy_order_entry.status
            if (COMMON.InternalOrderStatus.entered not in (buy_stat, sell_stat)
                    and COMMON.InternalOrderStatus.hibernated in (sell_stat, buy_stat)):
                i_sell = found_ind_sell + 1 if sell_stat == COMMON.InternalOrderStatus.hibernated else found_ind_sell
                i_buy = found_ind_buy if buy_stat == COMMON.InternalOrderStatus.hibernated else found_ind_buy + 1
                new_orders = sorted_orders[i_sell:i_buy]
                return self._find_next_conflict(product, new_orders, timestamp, brokers_without_hibernation,
                                                consider_tolerance=consider_tolerance)
        return sell_order_entry, buy_order_entry, execution

    def _is_conflict_on_exchange_and_unresolvable(self, brokers_without_hibernation, buy_order_entry, sell_order_entry):
        """
        In certain situations we ignore a conflict that is already exposed on the exchange.

        Conflicts between "old" orders (status "O") and orders already on the exchange can be ignored, because they
        will anyway disappear, as soon as the old order is modified (remember that the old order represents the old
        price of a modification request, while status "modified" represents the new price.)
        Old order prices are only relevent when they conflict with "new" prices (such as other modification or order
        entry requests). Then they are relevant, because most exchanges, such as EPEX, do not support transactions
        and process lists of modification requests in arbitrary order

        Additionally, conflicts between two manual orders on the exchange (no matter if hibernated or active) should
        be ignored in situation where we cannot resolve the conflict via an internal trade (i.e. on brokers where
        we cannot hibernate orders), because moving the price of a manual order would be a too big interference of
        autotrader with manual orders.

        :param brokers_without_hibernation: The set of broker_ids where hibernation is not possible.
        :type brokers_without_hibernation: frozenset
        :type buy_order_entry: COMMON.OrderEntry
        :type sell_order_entry: COMMON.OrderEntry
        :return: True, if we should find a different conflict, False otherwise
        :rtype: bool
        """
        if (sell_order_entry.status == COMMON.InternalOrderStatus.old
                and buy_order_entry.status not in [COMMON.InternalOrderStatus.entered,
                                                   COMMON.InternalOrderStatus.modified]):
            return True
        if (buy_order_entry.status == COMMON.InternalOrderStatus.old
                and sell_order_entry.status not in [COMMON.InternalOrderStatus.entered,
                                                    COMMON.InternalOrderStatus.modified]):
            return True
        # Additionally, on brokers where withholding is not possible,
        # conflicts between two manual orders can be ignored, but each of them can be involved in a different conflict
        for order_pair in [(buy_order_entry, sell_order_entry), (sell_order_entry, buy_order_entry)]:
            if (order_pair[0].status == COMMON.InternalOrderStatus.active
                    and order_pair[0].order.broker_id in brokers_without_hibernation
                    and order_pair[1].status in (COMMON.InternalOrderStatus.active,
                                                 COMMON.InternalOrderStatus.hibernated)):
                return True
        return False


class InternalMarket(object):
    """Class performing internal market algorithm

    This class creates an OrderConflictFinder object, which finds two orders potentially
    leading to a cross-trade at the exchange using the information about the actual orders
    and requested orders. If two orders creating a potential conflict or
    cross-trade are detected, they are resolved by the appropriate ConflictResolver
    according to their common internal execution mode:

    1) 0 or "no" for no internal trade;

    2) 1 or "exchange_base_price" allowing for an internal trade with price determined by the
        public order book;

    3) 2 or "average_price" allowing for an internal trade with price evaluated as
        average price of two orders;

    The conflict detection and its consequent treatment are performed by calling
    the object itself. The call returns than a dictionary with
    orders to be sent to the exchange.

    :cvar exchange_id: defines relevant exchange id, member of :class:`COMMON.Exchanges`
    :cvar global_mode: :class:`COMMON.GlobalInternalMarketMode`
    :cvar product: product for which the internal market should run, member of
                   :class:`APITR.Product`
    :cvar str product_name: name of the product
    :cvar list actual_orders: list of all actual own orders being accepted
                              by the exchange
    :cvar dict requested_order_dict: dictionary with orders requested by
                                     the strategies to be added/modified/deleted.
    :cvar float timestamp: current timestamp
    :cvar conflict_finder: conflict finder object, :class:`OrderConflictFinder`
    :cvar sell_order_entry: sell order entry in an order conflict
    :type sell_order_entry: :class:`COMMON.OrderEntry`
    :cvar buy_order_entry: buy order entry in an order conflict
    :type buy_order_entry: :class:`COMMON.OrderEntry`
    :cvar execution: common execution mode in an order conflict
    :type execution: :class:`COMMON.InternalExecutionMode`
    """

    def __init__(self, exchange_id, global_mode=COMMON.GlobalInternalMarketMode.default, aggress_other_brokers=True):
        self.exchange_id = exchange_id
        self.global_mode = global_mode
        self.product = None
        self.product_name = None
        self.actual_orders = []
        self.orig_actual_orders = []
        self.requested_order_dict = {}
        self.reject_reasons = {}
        self.timestamp = None
        self.conflict_finder = OrderConflictFinder(self.global_mode, aggress_other_brokers)
        self.sell_order_entry = None
        self.buy_order_entry = None
        self.execution = None
        self.route = None
        self.trayport_properties = None  # Will only be set by the Trayport exchange
        self.brokers_without_hibernation = frozenset()

    def set_route(self, route):
        """
        Sets active route to market to be persisted in mongo records for internal trades and orders

        :param route: route
        :type route: str
        """
        self.route = route
        LOGGER.info("Setting route to market for internal trades and orders to: %s", self.route)

    def create_log_entry(self, conflict):
        if conflict:
            header = "ORDER CONFLICT with execution {} for product {}.".format(
                self.execution, self.product_name)
            msg = "{} {}".format(self.sell_order_entry, self.buy_order_entry)
        else:
            header = "NO CONFLICT DETECTED for product {}.".format(self.product_name)
            msg = ""
        LOGGER.info(header + msg)
        LOGGER.info("COMBINED ORDERS %s", self.conflict_finder.combined_orders)

    @remove_internal_only
    def run(self, product, actual_orders, requested_order_dict, timestamp):
        self.product = product
        self.product_name = getattr(product, "name", None)
        self.actual_orders = actual_orders
        self.orig_actual_orders = tuple(actual_orders)
        self.requested_order_dict = requested_order_dict

        self.timestamp = timestamp
        orders_to_send = self._run(actual_orders, requested_order_dict)
        return orders_to_send

    @staticmethod
    def append_released_orders(orders_to_send, released_objects):
        if released_objects:
            if COMMON.ResolverState.internal_order_executions not in orders_to_send:
                orders_to_send[COMMON.ResolverState.internal_order_executions] = []
            orders_to_send[COMMON.ResolverState.internal_order_executions].extend(
                AUTILS.internal_order_execution(
                    COMMON.OrderAction.deleted, [rel_obj.instance for rel_obj in released_objects]))

    def _run(self, actual_orders, requested_order_dict):
        # Here all the magic happens
        self.sell_order_entry, self.buy_order_entry, self.execution = self.conflict_finder(
            self.product, actual_orders, requested_order_dict, self.timestamp,
            brokers_without_hibernation=self.brokers_without_hibernation)
        if not self.sell_order_entry:
            self.create_log_entry(conflict=False)
            return self.activate_com_trader_order()
        else:
            self.create_log_entry(conflict=True)

        # Conflicts between an old order (O) and an entry- or modify order,
        # mean we remove the E/M order and rerun the internal market
        if self.sell_order_entry.status == COMMON.InternalOrderStatus.old:
            return self.rerun(ignore_order_entries=[self.buy_order_entry])
        elif self.buy_order_entry.status == COMMON.InternalOrderStatus.old:
            return self.rerun(ignore_order_entries=[self.sell_order_entry])

        # Otherwise, use the appropriate conflict resolver.
        if self.execution == COMMON.InternalExecutionMode.no:
            return self.execution_no()
        elif self.execution == COMMON.InternalExecutionMode.exchange_base_price:
            return self.execution_exchange_base_price()
        elif self.execution == COMMON.InternalExecutionMode.average_price:
            return self.execution_average_price()
        return {}

    def rerun(self, ignore_hibernated=False, ignore_order_entries=None):
        """Removes entry orders from the requested order dictionary,
        reinitializes the InternalMarket and starts searching for a
        conflict again

        By default the function removes new entry orders engaged in the
        conflict from the `requested_order_dict`. It reinitializes and
        reruns the internal market.

        If `ignore_hibernated` flag is set to True, the function
        reinitializes and reruns the internal market while ignoring
        hibernated orders participating in the order conflict,
        by removing them from the `actual_orders` list.

        Adding `ignore_order_entries` list with selected orders allows
        for deliberate withdrawal of these orders.

        :param bool ignore_hibernated: if set to True, the function will
                                       remove the hibernated orders
                                       participating in the conflict from
                                       the `actual_orders` list.
        :param ignore_order_entries: one may explicitly specify
                                          the order entries to be ignored.
        :type ignore_order_entries: list[:class:`COMMON.OrderEntry`]

        """
        if ignore_order_entries:
            if not isinstance(ignore_order_entries, collections.Iterable):
                ignore_order_entries = list(ignore_order_entries)
        else:
            ignore_order_entries = []
            if (
                    self.sell_order_entry.status == COMMON.InternalOrderStatus.entered
                    or self.sell_order_entry.status == COMMON.InternalOrderStatus.hibernated
                    and ignore_hibernated
            ):
                ignore_order_entries.append(self.sell_order_entry)
            if (
                    self.buy_order_entry.status == COMMON.InternalOrderStatus.entered
                    or self.buy_order_entry.status == COMMON.InternalOrderStatus.hibernated
                    and ignore_hibernated
            ):
                ignore_order_entries.append(self.buy_order_entry)
            if not ignore_order_entries:
                LOGGER.error(("internal market rerun error: conflicting orders "
                              "cannot be ignored %s %s"),
                             self.sell_order_entry, self.buy_order_entry)
                return {}

        # check if we have internal_only orders in the ignore_order_entries list
        # if yes, we have to delete the internal_only orders first
        # we should always first remove the OnlyInternal order and rerun
        only_internal = any(order_entry.order.execmode == COMMON.InternalExecutionMode.internal_only
                            for order_entry in ignore_order_entries)
        if only_internal:
            ignore_order_entries = [order_entry for order_entry in ignore_order_entries
                                    if order_entry.order.execmode == COMMON.InternalExecutionMode.internal_only]

        for order_entry in ignore_order_entries:
            if order_entry.status == COMMON.InternalOrderStatus.hibernated and order_entry.order in self.actual_orders:
                if ignore_hibernated:
                    try:
                        self.actual_orders.remove(order_entry.order)
                    except ValueError:
                        LOGGER.error(("internal market rerun error: conflicting hibernated order "
                                      "cannot be ignored. No such order in the order book: %s"),
                                     order_entry)
                        return {}
            elif order_entry.order in self.requested_order_dict.get(COMMON.ResolverState.entry_orders, []):
                self.requested_order_dict[COMMON.ResolverState.entry_orders].remove(order_entry.order)
            elif order_entry.order in self.requested_order_dict.get(COMMON.ResolverState.modify_orders, []):
                self.requested_order_dict[COMMON.ResolverState.modify_orders].remove(order_entry.order)
            else:
                LOGGER.error("internal market rerun error: conflicting order cannot be ignored %s", order_entry)
                return {}
        LOGGER.debug("rerun the internal market while ignoring the following order(s) %s",
                     ignore_order_entries)
        return self._run(self.actual_orders, self.requested_order_dict)

    def _get_resolver(self):
        restrictions = (
            self.sell_order_entry.order.execution_restriction, self.buy_order_entry.order.execution_restriction
        )

        if any(oe.status == COMMON.InternalOrderStatus.active and oe.order.broker_id in self.brokers_without_hibernation
               for oe in [self.sell_order_entry, self.buy_order_entry]):
            resolver = autotrader_core.conflict_resolver.MoveOrderConflictResolverNoTrade(self)
        elif COMMON.ExecutionRestriction.aon in restrictions:
            resolver = autotrader_core.conflict_resolver.AONConflictResolver(self)
        elif COMMON.ExecutionRestriction.fok in restrictions:
            resolver = autotrader_core.conflict_resolver.FOKConflictResolver(self)
        elif COMMON.ExecutionRestriction.ioc in restrictions:
            resolver = autotrader_core.conflict_resolver.IOCConflictResolver(self)
        else:
            resolver = autotrader_core.conflict_resolver.CommonConflictResolver(self)
        resolver.set_route(self.route)
        return resolver

    def execution_no(self):
        """Resolved conflict for the common execution mode :class:`COMMON.InternalExecutionMode.no`

        The conflict is resolved by following the common return behavior
        as implemented in :class:`autotrader_core.conflict_resolver.CommonConflictResolver`
        or, in case the orders have fok execution restriction, in
        :class:`autotrader_core.conflict_resolver.FOKConflictResolver`

        :returns orders: a dictionary with orders to be sent to the exchange.
        :rtype: dict

        .. seealso:: :class:`autotrader_core.conflict_resolver.CommonConflictResolver`
                     :class:`autotrader_core.conflict_resolver.FOKConflictResolver`
        """
        resolver = self._get_resolver()
        return resolver()

    def execution_average_price(self):
        return self.execution_no()

    def execution_exchange_base_price(self):
        """Resolved conflict for the common execution mode :class:`COMMON.InternalExecutionMode.exchange_base_price`

        The function takes into account the neighboring public orders.
        If there is a public buy (sell) order with higher (lower) price
        as the sell (buy) order in the conflict, the order is moved as
        implemented in :class:`autotrader_core.conflict_resolver.MoveOrderConflictResolver`.
        Otherwise the conflict is resolved by calling
        :class:`autotrader_core.conflict_resolver.CommonConflictResolver` or
        :class:`autotrader_core.conflict_resolver.FOKConflictResolver` (if FOK orders
        participate in the conflict)
        with public orders taken into account.

        :returns orders: a dictionary with orders to be sent to the exchange.
        :rtype: dict

        .. seealso:: :class:`autotrader_core.conflict_resolver.CommonConflictResolver`
                     :class:`autotrader_core.conflict_resolver.FOKConflictResolver`
                     :class:`autotrader_core.conflict_resolver.MoveOrderConflictResolver`
        """
        sell_area = self.sell_order_entry.order.delivery_area_id
        public_ord = self.product.orders.get(delivery_area_id=sell_area, order_filter=COMMON.OrderFilter.public)

        # public orders do not have seperate internal market price, getter always takes price
        public_ord = sorted(public_ord, key=lambda val: val.price)

        # entry orders can have a tolerance delta -> use internal market price
        sell_price = self.sell_order_entry.order.internal_market_price
        buy_price = self.buy_order_entry.order.internal_market_price

        right_price = max(self.buy_order_entry.order.price, self.sell_order_entry.order.price)
        left_price = min(self.buy_order_entry.order.price, self.sell_order_entry.order.price)
        # Cross Trade can only happen if buy price is higher or sell price is lower.
        # for the buy price, only iterate through public buy orders whose price is higher
        # for the sell price, only iterate through public sell orders whose price is lower
        try:
            right_public_order = next(ord for ord in public_ord if ord.price > right_price and ord.direction == "buy")
            right_order_direction = right_public_order.direction
        except StopIteration:
            right_public_order = None
            right_order_direction = COMMON.Direction.sell
        try:
            left_public_order = next(
                ord for ord in public_ord[::-1] if ord.price < left_price and ord.direction == "sell"
            )
            left_order_direction = left_public_order.direction
        except StopIteration:
            left_public_order = None
            left_order_direction = COMMON.Direction.buy

        if self.buy_order_entry.order.execmode != COMMON.InternalExecutionMode.internal_only \
                and left_order_direction == right_order_direction == COMMON.Direction.sell:
            # If the neighboring public orders are both sell, we move the buy order in the conflict
            pub_orders = [left_public_order]
            resolver = autotrader_core.conflict_resolver.MoveOrderConflictResolver(self)
        elif self.sell_order_entry.order.execmode != COMMON.InternalExecutionMode.internal_only \
                and left_order_direction == right_order_direction == COMMON.Direction.buy:
            # If the neighboring public orders are both buy, we move the sell order in the conflict
            pub_orders = [right_public_order]
            resolver = autotrader_core.conflict_resolver.MoveOrderConflictResolver(self)
        else:
            # generator for public orders in between moved sell and buy
            pub_orders = [ordr for ordr in public_ord if sell_price <= ordr.price <= buy_price]
            resolver = self._get_resolver()
        return resolver(pub_orders)

    def activate_com_trader_order(self):
        """Function checks for possible com trader orders to be activated

        The function checks one hibernated order at a time, if it can be activated on the market
        without producing a cross trade (or order conflict). If there is no such order, all
        requested orders from strategies are sent to the market

        :returns orders: a dictionary with orders to be sent to the exchange.
                        The dictionary keys correspond to the
                        actions: "delete_orders", "modify_orders",
                        "deactivate_orders", "activate_orders"
        :rtype: dict
        """
        own_orders = [o for o in self.orig_actual_orders if isinstance(o, APITR.ComTraderOrder)]
        for order in sorted(own_orders, key=lambda val: val.price):
            if order.state == COMMON.OrderState.hibe and order.reactivate and self.request_to_activate_order([order]):
                order.reactivate = False
                return {COMMON.ResolverState.activate_orders: [order]}
        return self.requested_order_dict

    def request_to_activate_order(self, orders_to_activate):
        """This function checks if an order once sent to the exchange would
        create a cross trade or an order conflict.

        The function checks if any order from the specified orders_to_activate list
        may potentially create another conflict with the existing own orders
        at the exchange. If it does, the order is not sent to the exchange,
        otherwise it is.

        For the hibernated com trader order there are a few situations, where
        the internal market would wish to activate it. In this case the
        function checks if the order can potentially lead to another order
        conflict, or likewise a cross trade, once activated.
        The function can take into consideration several com trader orders,
        which should be activated at the same time.

        :param orders_to_activate: the com trader orders, which should be activated
        :type orders_to_activate: list[:class:`COMMON.OrderEntry`]

        :returns: returns True if the order creates another conflict with
                  the existing own orders (actual orders) and False otherwise.
        :rtype: bool
        """
        all_order_entries = []
        # We build a list of all_order_entries with orders present at the exchange
        # and artificially activate currently hibernated orders from the
        # orders_to_activate list to check, if these orders can be safely
        # activated, without creating another conflict
        for order in self.orig_actual_orders:
            if order.state == COMMON.OrderState.hibe and order in orders_to_activate:
                # We activate only those orders specified in the list of
                # orders to activate
                all_order_entries.append(COMMON.OrderEntry(COMMON.InternalOrderStatus.active, order))
            elif order.state == COMMON.OrderState.hibe:
                # If there is a hibernated order, which is not in the
                # orders_to_activate list, we ignore it
                continue
            else:
                # All other existing orders are added with the unchanged
                # status
                all_order_entries.append(COMMON.OrderEntry(
                    COMMON.InternalOrderStatus.unchanged, order))

        sell_entry, buy_entry, _ = self.conflict_finder(self.product, None, None, self.timestamp,
                                                        combined_orders=all_order_entries,
                                                        brokers_without_hibernation=self.brokers_without_hibernation,
                                                        consider_tolerance=False)

        if sell_entry is None:
            return True
        LOGGER.debug(("DO NOT ACTIVATE COM TRADER ORDER for product %s as another conflict is detected: "
                      "Sell order %s; Buy order %s."),
                     self.product_name, sell_entry, buy_entry)
        return False
