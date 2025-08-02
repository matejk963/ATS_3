#!/usr/bin/python3
# -*- coding: utf-8 -*-

from __future__ import absolute_import
import collections
import functools
import logging
import math
import time
import uuid
import copy

import autotrader_lib.common as COMMON
import autotrader_core.exchange_trading as APITR
import autotrader_core.utils as AUTILS
import autotrader_lib.util

LOGGER = logging.getLogger("autotrader.conflict_resolver")


def create_log_entry(func):
    """This is a decorator function to create a log entry for each
    conflict resolver
    """

    @functools.wraps(func)
    def func_wrapper(*args, **kwargs):
        """Wraps function adding a log entry"""
        class_name = args[0].__class__.__name__
        LOGGER.debug(class_name)
        orders = func(*args, **kwargs)
        LOGGER.debug("PREPARE ORDERS TO SEND \n%s",
                     "\n".join(["%s: %s" % (key, "\n".join([str(value) for value in values]))
                                for key, values in orders.items()]))
        return orders

    return func_wrapper


class UnknownExecutionException(Exception):
    pass


class ConflictResolver(object):
    """Conflict Resolver base class
    """

    def __init__(self, internal_market):
        self.internal_market = internal_market
        self.orders_to_send = collections.defaultdict(list)
        self.route = None

    def set_route(self, route):
        """
        Sets active route to market to be persisted in mongo records for internal trades and orders

        :param route: route
        :type route: str
        """
        self.route = route
        LOGGER.info("Setting route to market for internal trades and orders to: %s", self.route)

    @create_log_entry
    def __call__(self, pub_orders=None):
        return self.resolve_conflict(pub_orders)

    def resolve_conflict(self, unused_pub_orders):
        return {}

    def orders_are_hidden(self):
        """The function determined if both of the conflicting orders are
        hidden from the market or not.

        :rtype: bool
        """
        sell_order_entry = self.internal_market.sell_order_entry
        buy_order_entry = self.internal_market.buy_order_entry
        return (
            sell_order_entry.status in COMMON.InternalOrderStatus.hidden_order_status
            and buy_order_entry.status in COMMON.InternalOrderStatus.hidden_order_status
        )

    def find_exchange_price(self, pub_orders, order_price, qty_target,
                            next_index=0, qty_accum=0, pri_accum=0):
        """Finds exchange price for an order

        The function evaluates exchange (weighted) price if only
        one of the conflicting orders would be placed at the exchange.
        It evaluates price base on prices of the orders in the public
        order book weighted with corresponding quantity. If the public
        order book is empty or the public orders do not create an opportunity
        for a trade with the own selected order, the price is taken
        from the order itself. The function acquires the price recursively.

        :param list pub_orders: list of public orders (:class:`APITR.PublicOrder`)
        :param float order_price: price of the selected order
        :param float qty_target: target quantity to trade on the exchange
        :param int next_index: index of the next order in the pub_orders
                               list, needed for recursion
        :param float qty_accum: accumulated quantity of the public orders
                                possibly leading to a trade during the recursion
        :param float pri_accum: accumulated price weighted with quantity
                                of the public orders during the recursion.

        :returns: weighted accumulated price divided by the target quantity.
        :rtype: float
        """

        if not pub_orders:
            return order_price

        if next_index >= len(pub_orders):
            if qty_accum:
                return (pri_accum + order_price * (qty_target - qty_accum)) / qty_target
            return order_price
        else:
            if qty_accum + pub_orders[next_index].quantity < qty_target:
                qty_accum += pub_orders[next_index].quantity
                pri_accum += pub_orders[next_index].quantity * pub_orders[next_index].price
            else:
                pri_accum += (qty_target - qty_accum) * pub_orders[next_index].price
                return pri_accum / qty_target

        next_index += 1
        return self.find_exchange_price(pub_orders, order_price, qty_target,
                                        next_index, qty_accum, pri_accum)

    def create_internal_trades(self, sell_order=None, buy_order=None, pub_orders=None):
        """Creates two internal trades on the Periotheus exchange

        The internal trades of :class:`APITR.InternalTrade` type are created
        for two conflicting orders, if their common execution mode is
        `exchange_base_price` or `average_price`. Trades of this type
        have internal number starting with `internal_`. The trades
        acquire minimal quantity of two conflicting orders.
        The trade price is evaluated as follows:

        (i) If execution mode is average_price, the price is an average
        of the orders prices;

        (ii) If execution mode is exchange_base_price, the public orders
        are taken into account. And the price is a average of prices,
        which would be acquired by the orders, if they would have been placed
        at the exchange separately. Exchange-weighted price for each order
        is evaluated in :func:`InternalMarket.find_exchange_price`.

        :param sell_order: sell order leading to the internal trade
        :param buy_order: buy order leading to the internal trade
        :type sell_order: :class:`APITR.OwnOrder`
        :type buy_order: :class:`APITR.OwnOrder`
        :param list pub_orders: list of public orders (:class:`APITR.PublicOrder`)

        :returns internal_quantity: Returns the quantity of the internal trade
        :rtype: int
        """
        if sell_order is None:
            sell_order = self.internal_market.sell_order_entry.order
            sell_order.route_id = self.route
        if buy_order is None:
            buy_order = self.internal_market.buy_order_entry.order
            buy_order.route_id = self.route

        internal_quantity = min([buy_order.quantity, sell_order.quantity])

        def get_exchange_based_internal_price():
            """Use public order book to find price for internal trade

            The trade price is evaluated using the public order
            We calculate the price for sell/buy order, as if we would place
            them to the exchange separately. The trade price is than
            average of the two.

            :rtype: float
            """

            # here we sort by price, not by internal_market_price, because these orders are public orders
            sell_pub_orders = sorted([order for order in pub_orders
                                      if order.direction == COMMON.Direction.sell],
                                     key=lambda val: val.price, reverse=False)
            buy_pub_orders = sorted([order for order in pub_orders
                                     if order.direction == COMMON.Direction.buy],
                                    key=lambda val: val.price, reverse=True)

            sell_exchange_price = self.find_exchange_price(sell_pub_orders, sell_order.price,
                                                           qty_target=internal_quantity)

            buy_exchange_price = self.find_exchange_price(buy_pub_orders, buy_order.price,
                                                          qty_target=internal_quantity)
            return (sell_exchange_price + buy_exchange_price) / 2.0

        def get_internal_price(sell_order, buy_order, execution):
            """Get internal price depending on internal market execution and tolerance of sell and buy order

            if both have delta=0, then make price depending on internal_market.execution (default case)
            if only one has delta=0, then make price depending on the price of the order with delta=0
            if both have delta!=0, then find average of both internal_market_prices

            :return: internal_price
            :rtype: float
            """

            sell_delta_is_zero = sell_order.price == sell_order.internal_market_price
            buy_delta_is_zero = buy_order.price == buy_order.internal_market_price
            if sell_delta_is_zero and buy_delta_is_zero:
                # this is the default case, exchange price or average
                if execution == COMMON.InternalExecutionMode.exchange_base_price:
                    internal_price = get_exchange_based_internal_price()
                elif execution == COMMON.InternalExecutionMode.average_price:
                    internal_price = (buy_order.price + sell_order.price) / 2.0
                else:
                    raise UnknownExecutionException()
            elif buy_delta_is_zero != sell_delta_is_zero:
                # this is XOR, if only one of the has delta 0, take the price which has no tolerance
                internal_price = sell_order.price if sell_delta_is_zero else buy_order.price
            else:
                # both deltas are >0
                internal_price = (buy_order.internal_market_price + sell_order.internal_market_price) / 2.0
            rounding = 3 if self.internal_market.exchange_id == COMMON.Exchange.trayport else 2
            return round(internal_price, rounding)

        internal_price = get_internal_price(sell_order, buy_order, self.internal_market.execution)
        # Create two trades for sell and buy
        try:
            sell_order_id = sell_order.order_id
        except AttributeError:
            sell_order_id = sell_order.internal_id
        try:
            buy_order_id = buy_order.order_id
        except AttributeError:
            buy_order_id = buy_order.internal_id

        trade_id = "internal_{}".format(uuid.uuid4())

        internal_trade_sell = dict(order_id=sell_order_id,
                                   user=COMMON.INTERNAL_USER,
                                   trade_id=trade_id,
                                   quantity=internal_quantity,
                                   price=internal_price,
                                   delivery_area=sell_order.delivery_area_id,
                                   direction=COMMON.Direction.sell,
                                   txt=autotrader_lib.util.serialize_order_tags(sell_order.tags),
                                   exchange=self.internal_market.exchange_id,
                                   execution_time=self.internal_market.timestamp,
                                   state=COMMON.TradeState.active,
                                   product_id=sell_order.product.product_id,
                                   revision=time.time())
        internal_trade_buy = dict(order_id=buy_order_id,
                                  user=COMMON.INTERNAL_USER,
                                  trade_id=trade_id,
                                  quantity=internal_quantity,
                                  price=internal_price,
                                  delivery_area=buy_order.delivery_area_id,
                                  direction=COMMON.Direction.buy,
                                  txt=autotrader_lib.util.serialize_order_tags(buy_order.tags),
                                  exchange=self.internal_market.exchange_id,
                                  execution_time=self.internal_market.timestamp,
                                  state=COMMON.TradeState.active,
                                  product_id=buy_order.product.product_id,
                                  revision=time.time())

        if self.route is not None:
            internal_trade_sell["route_id"] = self.route
            internal_trade_buy["route_id"] = self.route

        LOGGER.info("INTERNAL TRADE for product %s with qty %s and price %s.",
                    sell_order.product.name, internal_quantity, internal_price)

        order_executions = []
        if not isinstance(sell_order, APITR.ComTraderOrder):
            order_executions.append(sell_order)
        if not isinstance(buy_order, APITR.ComTraderOrder):
            order_executions.append(buy_order)
        if order_executions:
            self.orders_to_send[COMMON.ResolverState.internal_order_executions].extend(
                AUTILS.internal_order_execution(COMMON.OrderAction.full_execution, order_executions, self.route))
        self.orders_to_send[COMMON.ResolverState.internal_trades].extend([internal_trade_sell, internal_trade_buy])

        return internal_quantity

    def fulfill_order_quantity(self, fill_order_entry, counter_order_entry,
                               pub_orders=None, hard=True):
        """Searches for orders among "entry_orders" in `requested_order_dict`
        and orders with hidden state in `actual_orders`
        which might fulfill the quantity of the fill_order_entry.

        If we find hidden orders (i.e. orders not visible on the market),
        which might fulfill the quantity of the fill_order_entry,
        we create internal trades with these orders. In case the orders
        are com trader orders, they are modified according to the
        internal trade quantity and activated if possible.

        If `hard` flag set to True, the function collects all the counter
        orders, whose total quantity is enough to fulfill the quantity
        of the `fill_order_entry`. Otherwise, when `hard` is False,
        the complete realization of the quantity of the `fill_order_entry`
        is not required.

        If `hard` flag set to True and the quantity of counter orders does
        not suffice, we rerun the internal market while ignoring the
        `counter_order_entry` or while ignoring `fill_order_entry`, if its
        quantity is largest and both conflicting orders have the same
        execution restriction.

        :param fill_order_entry: order entry which is to be be filled
        :type fill_order_entry: :class:`COMMON.OrderEntry`
        :param counter_order_entry: counter order entry
        :type counter_order_entry: :class:`COMMON.OrderEntry`
        :param pub_orders: list of public orders
        :type pub_orders: list[:class:`APITR.PublicOrder`]
        :param bool hard: determines if the quantity of the fill_order_entry
                          should be filled completely or not
        """
        # Get all counter orders, which are not at the exchange
        entry_orders = [ordr for ordr in self.internal_market.requested_order_dict[COMMON.ResolverState.entry_orders]
                        if ordr.direction == counter_order_entry.order.direction]
        hidden_orders = [
            ordr for ordr in self.internal_market.actual_orders
            if ordr.state == COMMON.OrderState.hibe and ordr.direction == counter_order_entry.order.direction
        ]
        hidden_orders += entry_orders
        # adjust order by internal_market_price, because conflicts will be resolved according to those
        if fill_order_entry.order.direction == COMMON.Direction.sell:
            sell_order = fill_order_entry.order
            hidden_orders = sorted([ordr for ordr in hidden_orders
                                    if ordr.internal_market_price >= fill_order_entry.order.internal_market_price],
                                   key=lambda val: val.internal_market_price, reverse=True)
        else:
            buy_order = fill_order_entry.order
            hidden_orders = sorted([ordr for ordr in hidden_orders
                                    if ordr.internal_market_price <= fill_order_entry.order.internal_market_price],
                                   key=lambda val: val.internal_market_price)
        # Select orders, which can fulfill the fill_order_entry
        orders_to_trade = []
        quantity = 0.0
        fulfilled = False
        for order in hidden_orders:
            # Check the zones
            if order.direction == COMMON.Direction.sell:
                one_trading_zone = self.internal_market.product.zones_joined(
                    order.delivery_area_id, fill_order_entry.order.delivery_area_id,
                    self.internal_market.timestamp)
            else:
                one_trading_zone = self.internal_market.product.zones_joined(
                    fill_order_entry.order.delivery_area_id, order.delivery_area_id,
                    self.internal_market.timestamp)
            if not one_trading_zone:
                continue

            if (
                    quantity + order.quantity > fill_order_entry.order.quantity
                    and order.execution_restriction in [COMMON.ExecutionRestriction.fok,
                                                        COMMON.ExecutionRestriction.aon]
            ):
                # if order is FOK or AON and its quantity is too large,
                # we skip this order as we cannot fulfill it
                continue

            quantity += order.quantity
            orders_to_trade.append(order)

            if quantity >= fill_order_entry.order.quantity:
                fulfilled = True
                break
        # Create internal trades if fulfilled or is not hard
        if fulfilled or not hard:
            for order in orders_to_trade:
                if order.direction == COMMON.Direction.sell:
                    sell_order = order
                else:
                    buy_order = order
                internal_trade_quantity = self.create_internal_trades(sell_order, buy_order,
                                                                      pub_orders)
                if isinstance(order, APITR.ComTraderOrder):
                    order_entry = COMMON.OrderEntry(COMMON.InternalOrderStatus.hibernated, order)
                    self.modify_com_trader_orders(order_entry, internal_trade_quantity)
                fill_order_entry.order.quantity -= internal_trade_quantity
                if fill_order_entry.order.quantity <= 0:
                    break
            return self.orders_to_send
        # If the quantity is not enough to fulfill the order, we rerun the
        # internal market while ignoring the counter order or while
        # ignoring the fill order, if its quantity is largest.
        if (
                fill_order_entry.order.execution_restriction == counter_order_entry.order.execution_restriction
                and fill_order_entry.order.quantity > counter_order_entry.order.quantity
        ):
            self.orders_to_send = self.internal_market.rerun(
                ignore_hibernated=True, ignore_order_entries=[fill_order_entry])
        else:
            self.orders_to_send = self.internal_market.rerun(
                ignore_hibernated=True, ignore_order_entries=[counter_order_entry])

        return self.orders_to_send

    def modify_com_trader_orders(self, com_trader_order_entry, internal_trade_qty):
        """Generates dictionary with orders to send for com trader order entry

        :params com_trader_order_entry: the com trader order entry
        :type com_trader_order_entry: :class:`COMMON.OrderEntry`
        :param float internal_trade_qty: internal trade quantity
        :returns orders: a dictionary with orders to be sent to the exchange.
                        The dictionary keys correspond to the
                        requested actions: "delete_orders", "modify_orders"
        :rtype: dict
        """
        com_trader_order = copy.copy(com_trader_order_entry.order)
        com_trader_order.route_id = self.route
        new_quantity = com_trader_order_entry.order.quantity - internal_trade_qty
        if new_quantity <= 0:
            com_trader_order.quantity = 0.0
            self.orders_to_send[COMMON.ResolverState.delete_orders].append(com_trader_order)
        else:
            com_trader_order.quantity = round(new_quantity, 4)
            self.orders_to_send[COMMON.ResolverState.modify_orders].append(com_trader_order)
        return self.orders_to_send

    def prepare_orders_to_send(self, deactivate=True):
        """Helper function to send orders to be deleted or deactivated

        :param bool deactivate: determines if com trader order can be deactivated

        :returns orders: a dictionary with orders to be sent to the exchange.
                         The dictionary keys correspond to the
                         actions: "delete_orders", "deactivate_orders"
        :rtype: dict
        """

        def _append_order_entry(order_entry):
            if order_entry.status != COMMON.InternalOrderStatus.entered:
                if not isinstance(order_entry.order, APITR.ComTraderOrder):
                    self.orders_to_send[COMMON.ResolverState.delete_orders].append(order_entry.order)
                    order_entry.order.product.immediate_action = True
                else:
                    if deactivate and order_entry.status == COMMON.InternalOrderStatus.active:
                        order_entry.order.reactivate = True
                        self.orders_to_send[COMMON.ResolverState.deactivate_orders].append(order_entry.order)
                        order_entry.order.product.immediate_action = True

        _append_order_entry(self.internal_market.sell_order_entry)
        _append_order_entry(self.internal_market.buy_order_entry)
        return self.orders_to_send


class CommonConflictResolver(ConflictResolver):
    """The class represents the common conflict resolving among different
    execution modes.

    In general the conflict is resolved by deleting existing conflicting orders
    from the exchange or by creating an internal trade, if
    both conflicting orders are "entry_orders". No orders are sent
    to the exchange in the later case.

    If the common execution mode is "no", no internal trade is created.
    In this case, the entry orders participating in the order conflict
    are removed from the requested_orders_dict. The com trader orders
    are never removed. However, the hibernated com trader order
    can be activated again.
    """

    def resolve_conflict(self, pub_orders=None):
        """The common conflict resolver represents the common behavior
        among different execution modes.

        :param list pub_orders: list of public orders (:class:`APITR.PublicOrder`)
                                default is None

        :returns orders: a dictionary with orders to be sent to the exchange.
                        The dictionary keys correspond to the
                        actions: "delete_orders", "modify_orders",
                        "deactivate_orders", "activate_orders"
        :rtype: dict
        """

        com_trader_order_entries = []
        sell_order_entry = self.internal_market.sell_order_entry
        buy_order_entry = self.internal_market.buy_order_entry
        if sell_order_entry.status in COMMON.InternalOrderStatus.com_trader_status:
            com_trader_order_entries.append(sell_order_entry)
        if buy_order_entry.status in COMMON.InternalOrderStatus.com_trader_status:
            com_trader_order_entries.append(buy_order_entry)

        if self.orders_are_hidden():
            if self.internal_market.execution == COMMON.InternalExecutionMode.no:
                for com_order_entry in com_trader_order_entries:
                    if self.internal_market.request_to_activate_order(com_order_entry):
                        com_order_entry.order.reactivate = False
                        self.orders_to_send[COMMON.ResolverState.activate_orders].append(com_order_entry.order)
                        return self.orders_to_send
                self.orders_to_send = self.internal_market.rerun()
                return self.orders_to_send
            else:
                # The internal trade can be created only between orders with
                # status "E"-"E" (entered-entered), "H"-"E" (hibernated-entered),
                # "E"-"H" (entered-hibernated), or "H"-"H" (hibernated-hibernated).
                # After the internal trade is created, the quantity is subtracted
                # from the quantity of the "H" (hibernated) order (if exist).
                # The "H" (hibernated) order is deleted, if the new_quantity
                # is less than or equal to 0.
                internal_trade_quantity = self.create_internal_trades(pub_orders=pub_orders)
                for order_entry in com_trader_order_entries:
                    self.modify_com_trader_orders(
                        order_entry, internal_trade_quantity)
                return self.orders_to_send
        else:
            if self.internal_market.execution == COMMON.InternalExecutionMode.no:
                if COMMON.InternalOrderStatus.entered in (sell_order_entry.status, buy_order_entry.status):
                    self.orders_to_send = self.internal_market.rerun()
                    return self.orders_to_send

            # The ComTraderOrder should not be hibernated if it conflicts with the modified order, because
            # we want to first delete the autoTRADER order. When the strategy replaces the order as entry request,
            # we will hibernate the manual order and store the entry order in the vault.
            if (COMMON.InternalOrderStatus.modified == sell_order_entry.status
                    and isinstance(buy_order_entry.order, APITR.ComTraderOrder)):
                deactivate = False
            elif (COMMON.InternalOrderStatus.modified == buy_order_entry.status
                  and isinstance(sell_order_entry.order, APITR.ComTraderOrder)):
                deactivate = False
            else:
                deactivate = self.internal_market.execution != COMMON.InternalExecutionMode.no
            return self.prepare_orders_to_send(deactivate=deactivate)


class MoveOrderConflictResolver(ConflictResolver):
    """The class is responsible for resolving an order conflict by modifying
    one of the conflicting orders

    The Conflict Resolver aims to modify the price of the one of the conflicting
    orders allowing for creating a trade with the existing public counter order,
    which possesses a better price than the own counter order.

    This Conflict Resolver is expected to be triggered only if the common
    execution mode of the two conflicting orders is "exchange base price".
    """

    def resolve_conflict(self, pub_orders):
        """The function modifies orders in the exchange base price
        execution mode in order to create a trade at the exchange with
        better price.

        In the exchange_base_price execution mode this function modifies
        the price of the moving_order_entry according to the price of the
        neighbor public_order.
        In this case, the order conflict is resolved by artificially
        moving the Buy(Sell) order before(after) the Sell(Buy) order

        :param pub_orders: list containing only one public order, which we utilize for moving of own order

        :returns orders: a dictionary with orders to be sent to the exchange.
                        The dictionary keys correspond to the
                        actions: "modify_orders", "entry_orders"
        :rtype: dict
        """
        pub_order = pub_orders[0]
        moving_direction = COMMON.Direction.sell if pub_order.direction == COMMON.Direction.buy else \
            COMMON.Direction.buy
        public_order_price = pub_order.price

        LOGGER.debug("PREPARE TO MOVE ORDERS %s-direction and public_price %s",
                     moving_direction, public_order_price)

        if moving_direction == COMMON.Direction.sell:
            moving_order_entry = self.internal_market.sell_order_entry
            resting_order_entry = self.internal_market.buy_order_entry
        elif moving_direction == COMMON.Direction.buy:
            moving_order_entry = self.internal_market.buy_order_entry
            resting_order_entry = self.internal_market.sell_order_entry
        else:
            return self.orders_to_send
        # We move the order to match the existing public order by price
        # to avoid rounding issues with the exchange
        moving_order_entry.order.price = public_order_price

        if moving_order_entry.status == COMMON.InternalOrderStatus.entered:
            self.orders_to_send[COMMON.ResolverState.entry_orders].append(moving_order_entry.order)
        else:
            self.orders_to_send[COMMON.ResolverState.modify_orders].append(moving_order_entry.order)

        if resting_order_entry.status == COMMON.InternalOrderStatus.modified:
            self.orders_to_send[COMMON.ResolverState.modify_orders].append(resting_order_entry.order)

        return self.orders_to_send


class MoveOrderConflictResolverNoTrade(ConflictResolver):
    """
    Conflict resolver to be used when we cannot create internal trades with manual orders.

    Some venues like EEX, ICE,... do not support withheld (deactivated) orders. Thus, autoTRADER cannot create
    internal trades on these brokers. This conflict resolver resolves such conflicts by moving the autoTRADER order to a
    price 1 tick in front of the manual order.
    """

    def resolve_conflict(self, pub_orders=None):
        """
        Resolve the conflict by changing the price of the autoTRADER order.

        Special case: If the autoTRADER order already has the desired price, the internal market is rerun.

        :param pub_orders: unused
        """
        base_order_is_sell = self.internal_market.sell_order_entry.status == COMMON.InternalOrderStatus.active
        if base_order_is_sell:
            base_order_entry = self.internal_market.sell_order_entry
            moving_order_entry = self.internal_market.buy_order_entry
        else:
            base_order_entry = self.internal_market.buy_order_entry
            moving_order_entry = self.internal_market.sell_order_entry

        key = "{}_{}_{}".format(moving_order_entry.order.broker_id, moving_order_entry.order.delivery_area_id,
                                self.internal_market.product.product_id)
        ticksize = self.internal_market.trayport_properties[key].price_tick
        target_price = math.floor(base_order_entry.order.price / ticksize) * ticksize
        target_price = round(target_price, COMMON.FLOAT_ROUNDING_PRECISION)
        if base_order_is_sell and target_price >= base_order_entry.order.price:
            target_price = round(target_price - ticksize, COMMON.FLOAT_ROUNDING_PRECISION)
        elif not base_order_is_sell and target_price <= base_order_entry.order.price:
            target_price = round(target_price + ticksize, COMMON.FLOAT_ROUNDING_PRECISION)
        original_price = moving_order_entry.order.price
        # We move the order to avoid a cross-trade
        if moving_order_entry.status == COMMON.InternalOrderStatus.unchanged:
            # In case of unchanged orders, the order is a reference to the order in the orderbook.
            # Make a copy of the order here, so we don't change the price in the orderbook
            moving_order = moving_order_entry.order.modify(price=target_price)
        else:
            moving_order = moving_order_entry.order
            moving_order.price = target_price

        if moving_order_entry.status == COMMON.InternalOrderStatus.entered:
            self.orders_to_send[COMMON.ResolverState.entry_orders].append(moving_order)
            LOGGER.debug("CROSS TRADE PROTECTION: Placing order %s at price %s instead of %s to avoid a cross trade.",
                         moving_order.internal_id, target_price, original_price)
        elif moving_order_entry.status in [COMMON.InternalOrderStatus.modified, COMMON.InternalOrderStatus.unchanged]:
            # Quite often the order will already be at the target price.
            # In this case re-run the internal market without this order.
            for actual_order in self.internal_market.actual_orders:
                if (actual_order.order_id == moving_order.order_id
                        and abs(actual_order.price - moving_order.price) < 10 ** -COMMON.FLOAT_ROUNDING_PRECISION
                        and abs(
                            actual_order.quantity - moving_order.quantity) < 10 ** -COMMON.FLOAT_ROUNDING_PRECISION):
                    LOGGER.debug("cross trade protection: Order %s (%s) is already at the correct target price %s. "
                                 "Trying to find another conflict.", moving_order.internal_id, moving_order.order_id,
                                 target_price)

                    # We rerun the internal market without the modification request of the moving order
                    # We drop the modifiction request for the moving order here, which means that later it will be
                    # rejected. By storing the reject reason here, the rejection request will propagate this info to
                    # the child process, allowing the synthetic order strategy to update the SO status.
                    reason = COMMON.RejectReason.price_moved_by_internal_market + " ({} -> {})".format(original_price,
                                                                                                       target_price)
                    self.internal_market.reject_reasons[moving_order.internal_id] = reason

                    self.orders_to_send = self.internal_market.rerun(ignore_order_entries=[moving_order_entry])
                    break
            else:
                LOGGER.debug("CROSS TRADE PROTECTION: Changing modify request for order %s (%s) to "
                             "target price %s from price %s to avoid a cross trade.",
                             moving_order.internal_id, moving_order.order_id, target_price, original_price)

                self.orders_to_send[COMMON.ResolverState.modify_orders].append(moving_order)
        else:
            # This code is unreachable, due to the way conflicts are found in the conflict finder
            # (See _is_conflict_on_exchange_and_unresolvable)
            # One order is always a manual order with status "A" so _is_conflict_on_exchange_and_unresolvable
            # would return True if the moving order had status "A", "H", or "O",
            # This means the moving order's status can only be "E", "M" and "U", and these cases are handled above
            LOGGER.error("MoveOrderConflictResolverNoTrade called with moving order %s with state %s. "
                         "This should not happen and can lead to unexpected behavior (e.g. autoTRADER orders not "
                         "being placed on this product). Please contact support if you come across this error.",
                         moving_order.internal_id, moving_order_entry.status)
        return self.orders_to_send


class RestrictedConflictResolver(CommonConflictResolver):
    """ The base class for resolving conflicts between orders with
    execution restriction: IOC, FOK or AON

    This class takes care of basic functionality for resolving conflicts
    between orders with different execution restrictions.

    The orders with execution restrictions also have different priorities:
    if two conflicting orders have different execution restriction the
    internal market will invoke a conflict resolver according to
    leading execution restriction. The highest priority is given to AON,
    following by FOK and IOC afterwards.

    For further details see :func:`RestrictedConflictResolver.resolve_conflict`

    .. data:: execution_restriction

        Determines the execution restriction of the resolver class: IOC, FOK, or AON
    """
    execution_restriction = COMMON.ExecutionRestriction.ioc

    def resolve_conflict(self, pub_orders=None):
        """Resolves the order conflict between orders with execution restriction

        The conflict is resolved using the following rules:

        1) If both orders are hidden from the market, i.e. they are
           either entry or hibernated orders, the resolver decides upon the
           execution of these orders internally by invoking
           :func:`RestrictedConflictResolver.resolve_orders`.
           For further details see :func:`RestrictedConflictResolver.resolve_orders`.

        2) If one of the conflicting orders is not hidden, we rerun the
           internal market (see :func:`internal_market.InternalMarket.rerun`)
           while ignoring the hidden entry or hibernated order.
           Here we assume that one order is always hidden, as orders with IOC and FOK
           execution restrictions should always be entry orders.

           In case of AON orders, however, we use a specific implementation of
           the function (see :func:`AONConflictResolver.resolve_orders`)
           as both conflicting orders can be visible at the exchange at the
           same time

        :param list pub_orders: list of public orders (:class:`APITR.PublicOrder`)
                                default is None

        :returns orders: a dictionary with orders to be sent to the exchange.
                        The dictionary keys correspond to the
                        actions: "delete_orders", "modify_orders",
                        "deactivate_orders", "activate_orders"
        :rtype: dict

        .. seealso:: :func:`RestrictedConflictResolver.resolve_orders`
        """
        if self.orders_are_hidden():
            return self.resolve_orders(pub_orders)
        self.orders_to_send = self.internal_market.rerun(ignore_hibernated=True)
        return self.orders_to_send

    def resolve_orders(self, pub_orders):
        """ The function implementing specific resolving algorithms
        for each execution restriction

        If the orders are not visible to the participants of the market,
        we can manipulate them without any problem. This means,
        that we can create internal trades, if the quantity and execution mode
        allows.

        1) If the internal execution mode is set to no, :func:`_no_execution`
           is invoked, we rerun the internal market while ignoring the
           conflicting hidden orders.

        2) For average_price and exchange_base_price execution modes,
           if both orders have the same execution restriction or the
           execution restriction of the resolver class is IOC,
           :func:`_equal_restriction` is invoked:

            * The order with the largest quantity among the conflicting order pair
              is chosen to be fulfilled in
              :func:`ConflictResolver.fulfill_order_quantity`. The
              function checks if the quantity of that order can be realized by the
              hidden counter orders and creates internal trades if possible.
              For FOK and AON leading execution restrictions the quantity
              have to be realized completely (`hard` flag is `True`),
              whereas for IOC leading restriction it is not required
              (`hard` flag is `False`).

        3) For average_price and exchange_base_price execution modes,
           if orders have different execution restrictions,
           :func:`_diff_restriction` is invoked:

            * The leading order, i.e. the order with the highest prioritized
              execution restriction, is chosen to be fulfilled in
              :func:`ConflictResolver.fulfill_order_quantity`.

        :params list pub_orders: list of public orders (:class:`APITR.PublicOrder`)
                                 default is None

        :return orders: a dictionary with orders to be sent to the exchange.
                        The dictionary keys correspond to the actions: “delete_orders”,
                        “modify_orders”, “deactivate_orders”, “activate_orders”
        :rtype: dict
        """
        if self.execution_restriction == COMMON.ExecutionRestriction.ioc:
            ioc_resolver = True
            hard = False
        else:
            ioc_resolver = False
            hard = True

        sell_execution = self.internal_market.sell_order_entry.order.execution_restriction
        buy_execution = self.internal_market.buy_order_entry.order.execution_restriction
        product = self.internal_market.product
        if self.internal_market.execution == COMMON.InternalExecutionMode.no or product.product_id is None:
            # rerun removes hidden orders from the requested orders dict
            # or actual order list and runs the internal market again
            if product.product_id is None:
                LOGGER.debug(
                    "product_id is None for product with delivery %s - %s: ignore conflicting orders",
                    product.delivery_start, product.delivery_end
                )
            self.orders_to_send = self.internal_market.rerun(ignore_hibernated=True)
        else:
            if sell_execution == buy_execution or ioc_resolver:
                self._equal_restriction(pub_orders, hard=hard)
            else:
                self._diff_restriction(pub_orders, hard=hard)
        return self.orders_to_send

    def _equal_restriction(self, pub_orders, hard=False):
        sell_order_entry = self.internal_market.sell_order_entry
        buy_order_entry = self.internal_market.buy_order_entry
        if sell_order_entry.order.quantity >= buy_order_entry.order.quantity:
            self.fulfill_order_quantity(sell_order_entry, buy_order_entry,
                                        pub_orders, hard=hard)
        else:
            self.fulfill_order_quantity(buy_order_entry, sell_order_entry,
                                        pub_orders, hard=hard)

    def _diff_restriction(self, pub_orders, hard=False):
        sell_order_entry = self.internal_market.sell_order_entry
        buy_order_entry = self.internal_market.buy_order_entry
        sell_restricted = sell_order_entry.order.execution_restriction == self.execution_restriction
        fill_order_entry = sell_order_entry if sell_restricted else buy_order_entry
        counter_order_entry = buy_order_entry if sell_restricted else sell_order_entry
        self.fulfill_order_quantity(fill_order_entry, counter_order_entry, pub_orders, hard=hard)


class IOCConflictResolver(RestrictedConflictResolver):
    """ The class is responsible for resolving an order conflict between
    the orders, if at least one of them has Immediate-Or-Cancel (IOC)
    execution restriction.

    IOC restriction means that the order is executed immediately to its
    maximum extend. In case of a partial execution, the remaining volume
    is removed from the order book. Orders with IOC execution restriction
    can be created for products with execution restrictions NON or AON.
    """
    execution_restriction = COMMON.ExecutionRestriction.ioc


class FOKConflictResolver(RestrictedConflictResolver):
    """The class is responsible for resolving an order conflict between
    the orders, if at least one of them has Fill-Or-Kill execution restriction.

    FOK restriction means that the order is immediately fully executed
    or deleted. Orders with FOK execution restriction can be created
    for products with execution restrictions NON or AON.
    """
    execution_restriction = COMMON.ExecutionRestriction.fok


class AONConflictResolver(RestrictedConflictResolver):
    """The class is responsible for resolving an order conflict between
    the orders, if at least one of them has All-Or-None execution restriction.

    AON restriction means that the order must be filled completely or not at all.
    The order stays in the order book until it is executed or removed by the
    system or user. AON orders can be created only for product with AON execution
    restriction. For those products only orders with AON and FOK
    restrictions are allowed.
    """
    execution_restriction = COMMON.ExecutionRestriction.aon

    def resolve_conflict(self, pub_orders=None):
        """Resolves the order conflict between orders with AON execution restriction

        This AON specific conflict resolver overwrites the base
        :func:`resolve_conflict` function.

        Although the resolver follows the generic behavior for hidden
        conflicting orders, for visible conflicting orders it is different:

            * If both AON orders visible on the market (only AON-AON
              is possible), the resolver returns an empty dictionary
              for orders to be send, i.e. it ignores the requested orders
              altogether, and shows an error message emphasizing that
              two AON orders may potentially lead to a cross trades;

            * If the quantity of the two orders is the same, the visible AON
              order is removed from the market (to allow for an internal
              trade on the next run of the strategies);

            * If the quantity of the two orders is not the same,
              we rerun the internal market while removing an entry
              order from the `requested_order_dict`.

        :param list pub_orders: list of public orders (:class:`APITR.PublicOrder`)
                                default is None

        :returns orders: a dictionary with orders to be sent to the exchange.
                        The dictionary keys correspond to the
                        actions: "delete_orders", "modify_orders",
                        "deactivate_orders", "activate_orders"
        :rtype: dict

        .. seealso:: :func:`RestrictedConflictResolver.resolve_orders`
        """
        sell_order_entry = self.internal_market.sell_order_entry
        buy_order_entry = self.internal_market.buy_order_entry

        if self.orders_are_hidden():
            return self.resolve_orders(pub_orders)

        if (
                sell_order_entry.status not in COMMON.InternalOrderStatus.hidden_order_status
                and buy_order_entry.status not in COMMON.InternalOrderStatus.hidden_order_status
        ):
            # if both orders are present on the market (meaning they are both AON)
            # the autotrader removes all the orders prepared to be send
            # to the epex and leave an error message
            LOGGER.warning("Two conflicting AON orders are detected at "
                           "the exchange for product %s possibly leading to "
                           "cross trades", self.internal_market.product_name)
            return {}
        elif sell_order_entry.order.quantity != buy_order_entry.order.quantity:
            self.orders_to_send = self.internal_market.rerun(ignore_hibernated=True)
            return self.orders_to_send
        return self.prepare_orders_to_send()
