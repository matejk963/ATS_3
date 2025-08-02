# -*- coding: utf-8 -*-

import collections
import copy
import logging
import operator

import autotrader_core.gas_strategy_parameters as PARAMS
import autotrader_core.strategy as STRATEGY
import autotrader_core.common as COMMON
import autotrader_core.strategy_utils as SU
import autotrader_core.exchange_trading as APITR


log = logging.getLogger('autotrader.gas_arbitrage')

TRAYPORT_BROKER_ID = "20"  # Broker 20 is PEGAS


# slot names
SLOT_SELL_ARBITRAGE = "sell_arbitrage"  # PASSIVE
SLOT_BUY_ARBITRAGE = "buy_arbitrage"  # PASSIVE
SLOT_SELL_ARBITRAGE_LIFT = "sell_arbitrage_lift"  # ACTIVE
SLOT_BUY_ARBITRAGE_LIFT = "buy_arbitrage_lift"  # ACTIVE

# price tolerance: if the strategy order is somewhere at the back of the order book, don't update the price every time
# it changes, just if the total change is larger than the PRICE_TOLERANCE
PRICE_TOLERANCE = 0.2
# the minimum quantity of a single order where we assume it wasn't a bot who placed it
# if the front order's quantity reaches this limit, we always place one tick in front, regardless the price change
BIG_ORDER_LIMIT = 100
# if the placed order is executed partially, it's only replaced if its new quantity is less than this value.
# The virtual iceberg is disabled when set to 0.
MIN_QTY_PLACEMENT = 0
# the minimum cumulative quantity on the source market for which a slot is placed on the destination market. The base
# price used for calculation is also taken from the order at this depth. It doesn't impact immediate execution.
DEEP_BOOK_QTY = 80
DEEP_BOOK_QTY_PEG = 600  # The deep quantity should always be larger than the maximum order book (typically 240 on PEG)

# Map the area of the product to one of area_a or area_b
AREA_MAPPING = {
    COMMON.Area.cegh_wd: COMMON.Area.cegh
}

# Constants that denote where the energy flows between market A and market B (useful for calculations with capacities)
MOVEMENT_A_B = "A->B"
MOVEMENT_B_A = "B->A"


def apply_tolerance(price_to_place, is_sell, step_size):
    """
    Return a tuple (range_lo, target_price, range_hi), where the range is equally step_size big in both directions.
    It takes into account the direction of the market and defines only that limit that matters.
    The other limit can't be None, because mk_slot() then lets any target price through.
    """
    if is_sell:
        return price_to_place, price_to_place, price_to_place + step_size
    else:
        return price_to_place - step_size, price_to_place, price_to_place


def tick(direction_on_target_market, front_price, front_order_quantity, previous_front_price, spread_price,
         previous_target_price, step_size, tick_size):
    """ Determines the price where the strategy should place the order.

    :param direction_on_target_market: type of order (buy or sell)
    :type direction_on_target_market: COMMON.Direction.buy | COMMON.Direction.sell
    :param front_price: front order price of the side to place the order on
    :type front_price: float or None
    :param front_order_quantity: the quantity of the front order for the same side to place the order on
    :type front_order_quantity: float
    :param previous_front_price: previous front price of the side to place the order on
    :type previous_front_price: float
    :param spread_price: minimum price to place at (calculated spread price or aon price)
    :type spread_price: float
    :param previous_target_price: previous price the strategy placed the order at
    :type previous_target_price: float
    :param step_size: the tolerance in both directions from the price
    :type step_size: float
    :param tick_size: exchange minimum tick size
    :type tick_size: float
    :return: target price
    :rtype: float
    """
    is_sell = direction_on_target_market == COMMON.Direction.sell
    # checks if arg1 is further away from other side of the orderbook than arg2
    further = operator.gt if is_sell else operator.lt
    # checks if arg1 is closer to the other side of the orderbook than arg2
    closer = operator.lt if is_sell else operator.gt
    if front_price is None or further(spread_price, front_price):  # empty or close market: we place at the spread price
        return apply_tolerance(spread_price, is_sell, step_size)

    # if the front quantity is big enough (probably not a bot placement), or the front price gets better for us
    # (because we would like to place higher sell orders on target market), we always place one tick in front,
    # to encourage our placed order to be traded with higher probability
    if front_order_quantity >= BIG_ORDER_LIMIT or (
        previous_front_price is not None and further(front_price, previous_front_price)
    ):
        target_price = front_price - tick_size if is_sell else front_price + tick_size   # place one tick in front
    # the following elif covers the case when the quantity gets < BIG_ORDER_LIMIT and the front price doesn't change
    # and the previous_target_price was a result of an open market calculation, not a minimum spread
    elif (previous_target_price is not None
          and front_price == previous_front_price
          and closer(previous_target_price, previous_front_price)):                      # place the same as before
        target_price = previous_target_price
    else:                                                                                # follow the front price
        target_price = front_price

    # price tolerance check, now on the calculated target price (if the front price just didn't breach the spread)
    # in case the target price equals the spread price no tolerances should be considered
    if further(target_price, spread_price) or target_price == spread_price:
        return None, target_price, None      # open market, price tolerance doesn't need to be checked
    else:                                    # spread price is placed, or no change if its value is within step size
        return apply_tolerance(spread_price, is_sell, step_size)


def aon_protection(direction_on_target_market, spread_price, aon_front_price, tick_size):
    """ Makes sure the price is legally placeable and doesn't violate an AON front order of the other buy/sell side.

    :param direction_on_target_market: type of order (buy or sell)
    :type direction_on_target_market: str
    :param spread_price: best price
    :type spread_price: float
    :param aon_front_price: price of the AON front order of the other side (buy or sell) if there is one
    :type aon_front_price: float | None
    :param tick_size: the minimum acceptable price change
    :type tick_size: float
    :return: AON protected price
    :rtype: float
    """
    if aon_front_price is None:
        return spread_price

    if direction_on_target_market == COMMON.Direction.sell:
        if spread_price <= aon_front_price:
            return aon_front_price + tick_size
    else:
        if spread_price >= aon_front_price:
            return aon_front_price - tick_size

    return spread_price


class PriceStatistics(object):
    """
    An object that will be filled with prices and quantities from indicators of a given direction
    and thrown away after use.
    """
    __slots__ = ['direction', 'best_price_deep', 'best_price', 'best_quantity', 'front_aon_price']

    def __init__(self, direction):
        """Create PriceStatistics for a direction

        :type direction: str
        """
        self.direction = None  # type: str
        self.best_price_deep = None  # type: float
        self.best_price = None  # type: float
        self.best_quantity = None  # type: float
        self.front_aon_price = None  # type: float
        self.direction = direction

    def __str__(self):
        out = []
        for attr in self.__slots__:
            if attr != 'direction':
                out.append("{}_{}:{}".format(attr, getattr(self, "direction"), getattr(self, attr)))
        return ", ".join(out)

    @classmethod
    def determine(
            cls,
            direction,  # type: str
            public_orders,  # type: list[APITR.PublicOrder | APITR.OwnOrder]
            deep_book_quantity,  # type: int
    ):  # type: (...) -> PriceStatistics
        """ Creates and fills price statistics for a given direction.

        :param direction: type of orders to evaluate (buy or sell)
        :type direction: str
        :param public_orders: public orders to consider
        :type public_orders: list[APITR.PublicOrder | APITR.OwnOrder]
        :param deep_book_quantity: quantity which counts as deep
        :type deep_book_quantity: int
        :return: price statistics
        :rtype: PriceStatistics
        """
        is_sell = direction == COMMON.Direction.sell
        stat = cls(direction)  # type: PriceStatistics

        filtered_public_orders = [[o.price, o.quantity, o.execution_restriction]
                                  for o in public_orders if o.direction == direction]
        public_limit_orders = [o for o in filtered_public_orders if o[2] == COMMON.ExecutionRestriction.non]
        public_aon_orders = [o for o in filtered_public_orders if o[2] == COMMON.ExecutionRestriction.aon]
        public_limit_orders.sort(reverse=not is_sell)

        if public_aon_orders:
            public_aon_orders.sort(reverse=not is_sell)
            stat.front_aon_price = public_aon_orders[0][0]
        public_limit_orders.append([-10E10, 0.])  # added in case it is empty
        # cumulating - the for loop below cumulates by modifying the list in place while iterating
        for first, second in zip(public_limit_orders, public_limit_orders[1:]):
            second[1] += first[1]
            if stat.best_price is None:
                stat.best_price = first[0]
                stat.best_quantity = first[1]
            if first[1] >= deep_book_quantity and stat.best_price_deep is None:
                stat.best_price_deep = first[0]
        return stat


class CustomStrategy(STRATEGY.GasStrategy):
    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        self.broker_id = TRAYPORT_BROKER_ID
        self.parameters = PARAMS.Parameters()
        self.maximum_order_book = 0
        self.minimum_order_book = 0
        self.price_tolerance = 0
        self.log = log

        self.previous_best_sell_price_a = dict()
        self.previous_best_sell_price_b = dict()
        self.previous_best_buy_price_a = dict()
        self.previous_best_buy_price_b = dict()

    @property
    def area_a(self):
        return self.delivery_areas[0]

    @property
    def area_b(self):
        return self.delivery_areas[1]

    # area mapping is not implemented yet
    def get_traded_amount_timeseries_by_slot_type(self, products):
        """
        This function gets everything that we trades so far, and aggregates it by areas, slots and time intervals

        As the weekend product overlaps with other products that are tradeable at the same time,
        we also have to get this timeseries only for the weekend product.

        :param products: The products to look at. For a given delivery period,
                         ALL overlapping products have to be included here.
        :type products: list
        :return: A nested dictionary with the keys area -> slot -> delivery_hour (timestamp)
        :rtype: dict[dict[dict]]
        """

        # area -> slot -> ts -> value
        result = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.defaultdict(float)))
        result_weekend = collections.defaultdict(lambda: collections.defaultdict(
            lambda: collections.defaultdict(float)))
        for product in products:
            trades = product.trades.get(trade_filter=COMMON.TradeFilter.own, portfolio_key=self.strategy_id)
            for t in trades:
                area = t.sell_delivery_area or t.buy_delivery_area
                area = AREA_MAPPING.get(area, area)  # e.g we convert cegh_wd --> cegh

                # get values to fill timeseries with traded data
                # make conversion from area unit, w.g. MWH/DAY
                quantity_mw = self.area_qty_to_mw(t.quantity, area, product.duration)

                for ts in range(product.delivery_start, product.delivery_end, COMMON.HOUR):
                    # slot is needed to distinguish between strategy behavior and order type (Passive or Active)
                    result[area][t.tags.get("strategy_slot", "")][ts] += quantity_mw
                    if product.product_type == "W/END":
                        result_weekend[area][t.tags.get("strategy_slot", "")][ts] += quantity_mw
        return result, result_weekend

    def calculate_and_block(self, formula, timestamp_from, timestamp_until, *parameters):
        """
        For every hour between timestamp_from and timestamp_until, we apply the formula to the
        corresponding values from all parameter timeseries. Then we take the minimum if the results are all positive,
        the maximum if they are all negative and 0 otherwise.

        :param formula: A function to be called with elements from the time-series
        :type formula: function
        :param timestamp_from: Start timestamp, referring to a full hour
        :type timestamp_from: float
        :param timestamp_until: End timestamp, referring to a full hour
        :type timestamp_until: float
        :param parameters: A list of time-series whose elements will be passed to the formula.
                           The list should have as many timeseries as the formula takes arguments.
        :type parameters: list
        :return: A scalar number that represents the minimum of value of all resulting hourly values.
        :rtype: float
        """
        result = dict()
        try:
            for ts in range(timestamp_from, timestamp_until, COMMON.HOUR):
                result[ts] = formula(*[param[ts] for param in parameters])
        except (KeyError, TypeError):
            self.debug_log("cannot build block")
            return 0.
        # now build a block
        values = result.values()
        block = values[0]
        for value in values[1:]:
            if block >= 0:
                block = max(min(block, value), 0.)
            else:
                block = min(max(block, value), 0.)
        return block

    def calculate_remaining_capacity(
        self, area_a, area_b, product, a_b_capacity_series, b_a_capacity_series, traded_timeseries
    ):
        """
        Calculate the remaining capacities from A to B and from B to A.

        :param area_a: first area of the strategy (passed on here, because this function is static)
        :type area_a: str
        :param area_b: second area
        :type area_b: str
        :param product: The product is used to find the delivery period for which we calculate the capacity
        :type product: autotrader_core.exchange_trading.Product
        :param a_b_capacity_series: The base capacity timeseries for transport A->B
        :type a_b_capacity_series: PARAMS.ParameterTimeseries
        :param b_a_capacity_series: The base capacity timeseries for transport B->A
        :type b_a_capacity_series: PARAMS.ParameterTimeseries
        :param traded_timeseries: The trades amounts in a dict generated by get_traded_amount_timeseries_by_slot_type
        :type traded_timeseries: dict
        :return: two capacity values (A->B and B->A)
        :rtype: tuple[float, float]
        """

        def f_remaining_a_b_capacity(max_a_b, max_b_a, sell_on_b, buy_on_a, buy_on_b, sell_on_a):
            # Min refers to the fact we cannot trade above the whole capacity between both A and B
            return min(max(0, max_a_b - sell_on_b - buy_on_a + buy_on_b + sell_on_a),
                       max_a_b + max_b_a)

        # buy_on_B - buy_on_A + sell_on_A - sell_on_B + max_A_B

        remaining_a_b_capacity = self.calculate_and_block(f_remaining_a_b_capacity,
                                                          product.delivery_start, product.delivery_end,
                                                          a_b_capacity_series, b_a_capacity_series,
                                                          traded_timeseries[area_b][SLOT_SELL_ARBITRAGE],
                                                          traded_timeseries[area_a][SLOT_BUY_ARBITRAGE],
                                                          traded_timeseries[area_b][SLOT_BUY_ARBITRAGE],
                                                          traded_timeseries[area_a][SLOT_SELL_ARBITRAGE])

        def f_remaining_b_a_capacity(max_a_b, max_b_a, sell_on_b, buy_on_a, buy_on_b, sell_on_a):
            return min(max(0, max_b_a - buy_on_b - sell_on_a + sell_on_b + buy_on_a),
                       max_a_b + max_b_a)

        # (buy_on_B - buy_on_A + sell_on_A - sell_on_B) - max_B_A

        remaining_b_a_capacity = self.calculate_and_block(f_remaining_b_a_capacity,
                                                          product.delivery_start, product.delivery_end,
                                                          a_b_capacity_series, b_a_capacity_series,
                                                          traded_timeseries[area_b][SLOT_SELL_ARBITRAGE],
                                                          traded_timeseries[area_a][SLOT_BUY_ARBITRAGE],
                                                          traded_timeseries[area_b][SLOT_BUY_ARBITRAGE],
                                                          traded_timeseries[area_a][SLOT_SELL_ARBITRAGE])

        return remaining_a_b_capacity, remaining_b_a_capacity

    @staticmethod
    def _prune_inactive_products_from_dict(active_products, state_dict):
        """ Static helper function for prune_inactive_products_from_state. """
        for prod_id in list(state_dict):
            if prod_id not in active_products:
                state_dict.pop(prod_id)

    def prune_inactive_products_from_state(self, active_products):
        """Removes products that aren't active anymore from some persistent variables to make sure the arbitrage doesn't
        increase in memory over time

        :param active_products: a list of active products
        :type active_products: list[autotrader_core.exchange_trading.Product]
        """
        active_product_ids = {p.product_id for p in active_products}
        self._prune_inactive_products_from_dict(active_product_ids, self.previous_best_buy_price_a)
        self._prune_inactive_products_from_dict(active_product_ids, self.previous_best_buy_price_b)
        self._prune_inactive_products_from_dict(active_product_ids, self.previous_best_sell_price_a)
        self._prune_inactive_products_from_dict(active_product_ids, self.previous_best_sell_price_b)

    def validate_price_tolerance(self, price_tolerance):
        """ Make sure price_tolerance has an acceptable value. """
        if not isinstance(price_tolerance, (int, float)) or price_tolerance < 0:
            self.error_log("PRICE_TOLERANCE Validation Error: Only positive numbers can be used for PRICE_TOLERANCE."
                           "Current: {}".format(price_tolerance))
            raise TypeError("Only positive numbers can be used for PRICE_TOLERANCE")
        if price_tolerance >= 10000:
            self.error_log("PRICE_TOLERANCE Validation Error: PRICE_TOLERANCE must be within the range [0; 9999.99]."
                           "Current: {}".format(price_tolerance))
            raise TypeError("PRICE_TOLERANCE must be within the range [0; 9999.99]")
        return price_tolerance

    def get_last_price_for_slot(self, product, area, slot_name):
        strategy_orders = product.orders.get(area, COMMON.OrderFilter.own, portfolio_key=self.strategy_id)
        slot_orders = [o for o in strategy_orders if o.tags.get("strategy_slot", "") == slot_name]
        if len(slot_orders) == 1:
            return slot_orders[0].price
        elif len(slot_orders) > 1:
            self.warn_log("Multiple orders are not supported for the same slot type '{}': {}".format(
                slot_name, slot_orders), product)
        return None

    def indicators(self, area, product):
        """
        Get the PriceStatistics for the buy and sell of the current order_book state
        :param area: area to get the price statistics for
        :type area: str
        :param product: product to get the price statistics for
        :type product: autotrader_core.exchange_trading.Product
        :return: tuple of (sell-statistics, buy-statistics)
        :rtype: (PriceStatistics, PriceStatistics)
        """
        deep_book_quantity = DEEP_BOOK_QTY_PEG if self.is_mwh_per_day_area(area) else DEEP_BOOK_QTY

        area_property = self.get_trayport_properties(product.product_id, instrument_id=area, broker_id=self.broker_id)
        # Be sure that we filter out smaller amounts than min_quantity (although it's already filtered by deep quantity)
        public_orders = [p for p in product.orders.get(order_filter=COMMON.OrderFilter.public, delivery_area_id=area,
                                                       only_tradable=True) if p.quantity >= area_property.min_quantity]
        stat_sell = PriceStatistics.determine(COMMON.Direction.sell, public_orders, deep_book_quantity)
        stat_buy = PriceStatistics.determine(COMMON.Direction.buy, public_orders, deep_book_quantity)
        stat_sell.best_quantity = self.area_qty_to_mw(stat_sell.best_quantity, area, product.duration)
        stat_buy.best_quantity = self.area_qty_to_mw(stat_buy.best_quantity, area, product.duration)

        return stat_sell, stat_buy

    def calculate_quantity(self, movement_direction, placeable_quantity_mw, available_capacities_mw, product):
        """
        If necessary, decreases ("caps") the given quantity so that it doesn't exceed the maximum_order_book,
        the remaining capacity of the given transfer direction and the PEG unit restrictions.
        The return value is the capped quantity.

        :param movement_direction: the direction of the movement of energy, hence it specifies which capacity
                                   value to use. Use one of the constants MOVEMENT_A_B or MOVEMENT_B_A
        :type movement_direction: str
        :param placeable_quantity_mw: the target quantity we would like to place at most.
                                      It may be capped by constraints
        :type placeable_quantity_mw: float
        :param available_capacities_mw: A list of two floats, the available capacities for the two movement directions.
                                        The first value is for A->B, the second for B->A
        :type available_capacities_mw: list[float]
        :param product: the product for which the order is intended.
                        This is needed because some areas (looking at you, PEG) have units that
                        depend on the product duration
        :type product: APITR.Product
        :return: the decreased quantity that fits the constraints.
        :rtype: float
        """
        index = 0 if movement_direction == MOVEMENT_A_B else 1
        cap = self.maximum_order_book  # in MW!
        capped_quantity = min(cap, available_capacities_mw[index], placeable_quantity_mw)
        if self.is_mwh_per_day_area(self.area_a) or self.is_mwh_per_day_area(self.area_b):
            capped_quantity = self.adjust_quantity_for_peg(capped_quantity, product)
        return capped_quantity

    @staticmethod
    def reserve_capacities(capacities_mw, used_quantity_mw, movement_direction):
        """
        Modify the capacities_mw list in-place by removing the used_quantity_mw

        :param capacities_mw: The list of available capacities. This is modified in-place!
        :type capacities_mw: list[float]
        :type used_quantity_mw: float
        :param movement_direction: Use one of the constants MOVEMENT_A_B or MOVEMENT_B_A.
        :type movement_direction: str
        """
        index = 0 if movement_direction == MOVEMENT_A_B else 1
        capacities_mw[index] = max(0, capacities_mw[index] - used_quantity_mw)

    def adjust_quantity_for_peg(self, target_quantity_mw, product):
        """
        Calculates the quantity and the execution_restriction parameter for the slot if PEG area is involved.

        (If PEG is the target area, the validate function of the slot applies the PEG constraints, and reduces quantity,
         if needed. However, it's easier to check them here as well, together with the orders with PEG source area.)
        """

        # First constraint: only integer values are allowed (if MW is fine, the other unit is also fine)
        original_target_qty_mw = target_quantity_mw = int(target_quantity_mw)

        original_peg_qty = peg_quantity = self.mw_to_area_qty(target_quantity_mw, COMMON.Area.peg, product.duration)

        # Second constraint: quantity on PEG area must be dividable by 10.
        # If harmed, quantity is replaced with the highest value that fulfills this condition.
        while peg_quantity > 0 and peg_quantity % 10 != 0:
            target_quantity_mw -= 1
            peg_quantity = self.mw_to_area_qty(target_quantity_mw, COMMON.Area.peg, product.duration)

        # Third constraint: quantity on PEG area must be at least 240. If harmed, slot is not created.
        if peg_quantity < 240:
            target_quantity_mw = 0
            peg_quantity = 0

        if target_quantity_mw != original_target_qty_mw:
            self.debug_log("PEG constraints: Changed target quantity from {} MW ({} PEG)  to {} MW ({} PEG)".format(
                original_target_qty_mw, original_peg_qty, target_quantity_mw, peg_quantity), product)

        return target_quantity_mw

    def mk_slot(self, name, direction, product, area, quantity_mw, price, price_range_low=None, price_range_high=None,
                info=None):
        """
        Helper-function to create a slot object.
        Quantity should be passed as MW or MWH/H, and will be translated according to the area properties here.
        Area specific filtering (e.g. PEG constraints) is also included here.

        :rtype: STRATEGY.PositionSlot
        """
        execution_restriction = COMMON.ExecutionRestriction.non

        # checking if we have a PEG area where conversion and filtering is needed
        if self.is_mwh_per_day_area(self.area_a) or self.is_mwh_per_day_area(self.area_b):
            quantity_mw = self.adjust_quantity_for_peg(quantity_mw, product)
            execution_restriction = COMMON.ExecutionRestriction.aon
        target_quantity = self.mw_to_area_qty(quantity_mw, area, product.duration)

        return STRATEGY.PositionSlot(
            name, direction, target_quantity, price,
            execution_restriction=execution_restriction,
            tick_size=self.exchange.tick_size, broker_id=TRAYPORT_BROKER_ID,
            quantity_range_lo=self.minimum_order_book if self.minimum_order_book != 0 else None,
            price_range_hi=price_range_high, price_range_lo=price_range_low, info=info)

    def place_slot_with_log(self, product, timestamp, delivery_area, slots):
        """
        Helper-function to place slots and log some info about them.
        """
        for slot in slots:
            self.debug_log("  slot: {} {} {}@{} mode: {}".format(slot.slot_type, slot.direction,
                                                                 slot.quantity, slot.price, slot.info), product)
        self.place_slots({}, product, timestamp, delivery_area, slots,
                         [], None, None, COMMON.InternalExecutionMode.exchange_base_price)

    def lift_order(self, product, current_timestamp, area_from, area_to, slotname, quantity):
        """
        Place lifting slots to remove imbalances if needed (everything we buy on one area
        must be sold on the other area and vice versa).

        Arbitrage works by placing orders on two delivery areas. If one of them is clicked,
        then the strategy has to create a trade on the other area to actually enable transport. This function finds the
        relevant price and places or removes the lifting slot.

        We always place the lift order at the same price as the last trade made on the other area,
        although we hope that autoTRADER will be able to match it with a spread, so we can earn money on the transport.

        :param product: The active product we are looking at
        :type product: autotrader_core.exchange_trading.Product
        :param current_timestamp: The current timestamp, used for placing the slot.
        :type current_timestamp: int
        :param area_from: Get last price from this area.
        :type area_from: str
        :param area_to: Lift in this area
        :type area_to: str
        :param slotname: Arbitrage sell or buy slot. This is the original slot that we want to balance out,
                         not the slot we place for lifting.
        :type slotname: str
        :param quantity: Lifting quantity
        :type quantity: float
        :raises SU.LastPriceNotFoundError: If no trades were found for this product. This should never happen.
        :rtype: None
        """

        lift_slot_map = {
            SLOT_SELL_ARBITRAGE: SLOT_BUY_ARBITRAGE_LIFT,
            SLOT_BUY_ARBITRAGE: SLOT_SELL_ARBITRAGE_LIFT,
        }
        # The direction at which we have to lift.
        direction_map = {
            SLOT_SELL_ARBITRAGE: COMMON.Direction.buy,
            SLOT_BUY_ARBITRAGE: COMMON.Direction.sell,
        }

        if quantity:
            last_price = SU.get_last_price_by_slot(self.exchange, product, area_from, slotname, self.strategy_id)
            if last_price is None:
                self.error_log("No trade found for this product", product)
                raise SU.LastPriceNotFoundError

            sell_slot = self.mk_slot(lift_slot_map[slotname], direction_map[slotname], product, area_to,
                                     quantity, last_price, info="lift")
            self.place_slot_with_log(product, current_timestamp, area_to, [sell_slot])
        else:
            sell_slot = self.mk_slot(lift_slot_map[slotname], direction_map[slotname], product, area_to, 0., 0.,
                                     "no-lift")
            self.place_slot_with_log(product, current_timestamp, area_to, [sell_slot])

    def _place_arbitrage_slot(self, current_timestamp, product, area, direction, previous_front_price,
                              immediate_vesting_spread, min_spread, capacities,
                              target_market_stats, source_market_stats, is_a):
        """
        :param current_timestamp: current timestamp passed to place_slot_with_log
        :param product: current product passed to place_slot_with_log
        :type product: autotrader_core.exchange_trading.Product
        :param area: area to place the slot on
        :type area: str
        :param direction: type of order (buy or sell)
        :type direction: str
        :param previous_front_price: previous price of the front order
        :type previous_front_price: float
        :param immediate_vesting_spread: the spread when the strategy initiates immediate execution
        :type immediate_vesting spread: float
        :param min_spread: the minimum spread to place at
        :type min_spread: float
        :param capacities: the available capacities. NOTE: This is modified in-place!
        :type capacities: list
        :param target_market_stats: statistics for the market to place the slot on (sell-statistics, buy-statistics)
        :type target_market_stats: (PriceStatistics, PriceStatistics)
        :param source_market_stats: statistics for the market to compare spread to. (sell-statistics, buy-statistics)
        :type source_market_stats: (PriceStatistics, PriceStatistics)
        :param is_a: True if target_market_stats is for area A
        :type is_a: bool
        """
        target_stat_sell, target_stat_buy = target_market_stats
        source_stat_sell, source_stat_buy = source_market_stats
        # destination market area and direction -> wants to place the slot here
        target_stat = target_stat_buy if direction == COMMON.Direction.buy else target_stat_sell
        # same destination area, but opposite direction -> no intent to place here
        target_other_dir_stat = target_stat_sell if direction == COMMON.Direction.buy else target_stat_buy
        # source market area, but same direction as the strategy intends to place the slot -> no intent to place here
        # here exists the counterpart to the order the strategy wants to place
        source_stat = source_stat_buy if direction == COMMON.Direction.buy else source_stat_sell

        slot_name = SLOT_BUY_ARBITRAGE if direction == COMMON.Direction.buy else SLOT_SELL_ARBITRAGE
        # energy flows from B to A when 1.) target is A and we sell on target, or 2.) target is B and we buy on target
        movement = MOVEMENT_B_A if is_a == (direction == COMMON.Direction.sell) else MOVEMENT_A_B

        target_quantity = 0

        # spread parameter calculations presume "A" as target market by default. If we switch the market roles between
        # A and B, the spread parameter changes sign. E.g. on sell markets, if the target is A, we buy on B, and the
        # minimal spread price on target A is deep_price_B + minimum_spread_B_A. When we change the roles (buy markets,
        # target is B), the maximal spread price on target B is deep_price_A + (-minimum_spread_B_A).
        if not is_a:
            immediate_vesting_spread *= -1
            min_spread *= -1

        better = operator.le if direction == COMMON.Direction.sell else operator.ge
        execute_immediately = (
            source_stat.best_price is not None
            and target_other_dir_stat.best_price is not None
            and better(source_stat.best_price + immediate_vesting_spread, target_other_dir_stat.best_price)
        )
        self.debug_log(
            "Decide Immediate Execution: Area: %s, source_stat.best_price: %s, target_other_dir_stat.best_price: %s, "
            "immediate = %s" % (area, source_stat.best_price, target_other_dir_stat.best_price, execute_immediately),
            product)

        if execute_immediately:
            if is_a:
                # Immediate Execution
                target_quantity = self.calculate_quantity(
                    movement, min(target_other_dir_stat.best_quantity, source_stat.best_quantity), capacities, product)
                self.debug_log(
                    "Immediate Execution parameters: Movement:%s, Quantities: %s // %s, CapQ: %s" % (
                        movement, target_other_dir_stat.best_quantity, source_stat.best_quantity, target_quantity),
                    product
                )
                slot_price = source_stat.best_price + immediate_vesting_spread
                slot = self.mk_slot(
                    slot_name, direction, product, area, target_quantity, slot_price,
                    info="initiate_immediately"
                )
            else:
                # When we initiate immediately, we only place orders on area a and balance them out with lifts on area b
                # So we have to remove the normal arbitrage order from B to ensure we do not over trade capacities..
                slot = self.mk_slot(slot_name, direction, product, area, 0.0, None, info="imm_ex_remove_b_area_order")
        elif source_stat.best_price_deep is not None:
            # Place slot
            previous_strategy_price = self.get_last_price_for_slot(product, area, slot_name)
            # if the target market is empty we want to place at immediate execution spread to prevent accidental trades
            # and to place the order at a better price
            spread_price = source_stat.best_price_deep + immediate_vesting_spread if target_stat.best_price is None \
                else source_stat.best_price_deep + min_spread
            min_price = aon_protection(direction, spread_price, target_other_dir_stat.front_aon_price,
                                       self.exchange.tick_size)
            range_lo, target_price, range_hi = tick(
                direction, target_stat.best_price, target_stat.best_quantity, previous_front_price, min_price,
                previous_strategy_price, self.price_tolerance, self.exchange.tick_size)
            target_quantity = self.calculate_quantity(movement, self.maximum_order_book, capacities, product)

            slot = self.mk_slot(slot_name, direction, product, area, target_quantity, target_price, range_lo,
                                range_hi, info="initiate")
        else:
            # Delete slot
            slot = self.mk_slot(slot_name, direction, product, area, 0, None, info="no_arbitrage_0_delete")

        self.place_slot_with_log(product, current_timestamp, area, [slot])
        self.reserve_capacities(capacities, target_quantity, movement)

    def gas_arbitrage(self, current_timestamp, product, remaining_a_b_capacity_mw,
                      remaining_b_a_capacity_mw, a_b_min_spread_purchase, a_b_min_spread_sell,
                      a_b_immediate_vesting_spread_purchase, a_b_immediate_vesting_spread_sell,
                      lift_sell_a_mw, lift_sell_b_mw, lift_buy_a_mw, lift_buy_b_mw, only_lift):
        """
        Main function that is called per product to place the corresponding slots.

        :param current_timestamp: The current timestamp, which will be recorded when we place the slots.
        :type current_timestamp: int
        :param product: The active Product we are looking at
        :type product autotrader_core.exchange_trading.Product
        :param remaining_a_b_capacity_mw: Remaining transmission capacity from A to B
        :type remaining_a_b_capacity_mw: float
        :param remaining_b_a_capacity_mw: Remaining transmission capacity from B to A
        :type remaining_b_a_capacity_mw: float
        :param a_b_min_spread_purchase: The minimal price difference between the two areas
                                        if we place orders for buy on area A and sell on area b
        :type a_b_min_spread_purchase: float
        :param a_b_min_spread_sell:  The minimal price difference between the two areas
                                        if we place orders for sell on area A and buy on area b
        :type a_b_min_spread_sell: float
        :param a_b_immediate_vesting_spread_purchase: The minimal price difference between the two areas
                                                      for immediately executing buy trades on area A
                                                      and sell trades on area b
        :type a_b_immediate_vesting_spread_purchase: float
        :param a_b_immediate_vesting_spread_sell: The minimal price difference between the two areas
                                                  for immediately executing sell trades on area A
                                                  and buy trades on area b
        :type a_b_immediate_vesting_spread_sell: float
        :param lift_sell_a_mw: quantity that we need to sell on area A to balance out the areas
        :type lift_sell_a_mw: float
        :param lift_sell_b_mw: quantity that we need to sell on area B to balance out the areas
        :type lift_sell_b_mw: float
        :param lift_buy_a_mw: quantity that we need to buy on area A to balance out the areas
        :type lift_buy_a_mw: float
        :param lift_buy_b_mw: quantity that we need to buy on area B to balance out the areas
        :type lift_buy_b_mw: float
        :param only_lift: If True, do not update any initiating orders
        :type only_lift: bool
        :return: remaining capacities for area A and B
        :rtype: tuple
        """

        capacities_mw = [remaining_a_b_capacity_mw, remaining_b_a_capacity_mw]

        def used_capacities():
            """Capacities is modified in place"""
            return remaining_a_b_capacity_mw - capacities_mw[0], remaining_b_a_capacity_mw - capacities_mw[1]

        # One hour a day the within day product and the day-ahead product overlap. In this case, do not trade on the
        # within day product, as overlapping products cause all kinds of troubles, as seen on the weekend product
        # In this case, we do not have to reserve any capacities or cancel any slots,
        # as this condition becomes true directly after product rotation.

        if product.product_type == "WD":
            da_product = self.exchange.products.get_by_id("10000302_2")
            if product.delivery_start == da_product.delivery_start:
                self.debug_log("Skipping WD product because of overlap with DA product.", product)
                return used_capacities()

        area_a = self.area_a
        area_b = self.area_b

        if None in (remaining_a_b_capacity_mw, remaining_b_a_capacity_mw, a_b_min_spread_purchase,
                    a_b_min_spread_sell, a_b_immediate_vesting_spread_purchase,
                    a_b_immediate_vesting_spread_sell):

            self.warn_log("Configuration was incomplete for this product, current parameters are: {}".format(
                          SU.log_locals(locals())), product)

            # If we do not have complete data, we cancel open orders, but not lift.
            # TODO: should we also cancel lift orders?
            sell_slot = self.mk_slot(SLOT_SELL_ARBITRAGE, COMMON.Direction.sell, product, area_b, 0., 0., "no_config")
            buy_slot = self.mk_slot(SLOT_BUY_ARBITRAGE, COMMON.Direction.buy, product, area_b, 0., 0., "no_config")
            self.place_slot_with_log(product, current_timestamp, area_b, [buy_slot, sell_slot])
            sell_slot = self.mk_slot(SLOT_SELL_ARBITRAGE, COMMON.Direction.sell, product, area_a, 0., 0., "no_config")
            buy_slot = self.mk_slot(SLOT_BUY_ARBITRAGE, COMMON.Direction.buy, product, area_a, 0., 0., "no_config")
            self.place_slot_with_log(product, current_timestamp, area_a, [buy_slot, sell_slot])
            return used_capacities()

        # Lifting required? If yes, decrease capacities (in both direction) with maximum_order_book (reservation)
        # ------------------------------------------------------------

        # We lift at worst with 0 spread, so this is the slot we place.
        # If there are better counter-orders out there (which usually is the case,
        # because we had a spread when we created the imbalance), then autoTRADER or the exchange will take care of that
        # If the counter-order has disappeared, we try to close the imbalance, even at the cost of having 0 spread.
        self.lift_order(product, current_timestamp, area_b, area_a, SLOT_BUY_ARBITRAGE, lift_sell_a_mw)
        self.lift_order(product, current_timestamp, area_a, area_b, SLOT_BUY_ARBITRAGE, lift_sell_b_mw)
        self.lift_order(product, current_timestamp, area_b, area_a, SLOT_SELL_ARBITRAGE, lift_buy_a_mw)
        self.lift_order(product, current_timestamp, area_a, area_b, SLOT_SELL_ARBITRAGE, lift_buy_b_mw)

        if lift_sell_a_mw > 0 or lift_sell_b_mw > 0 or lift_buy_a_mw > 0 or lift_buy_b_mw > 0:
            # In case of overlapping products, we have to reserve capacity here for the initiating orders:
            # As the products are ordered by duration, this function is always first called for the weekend product
            # and then for the saturday and sunday products.
            # While lifting is in progress, we leave our initiate orders unchanged at the exchange, but we do not run
            # the code that places the slots below (early return).
            # Still we have to reserve (at least) their capacities before we move
            # to the next products, otherwise we could overtrade. As we could have orders on two areas, we reserve
            # the maximum orderbook two times.
            # But there is an additional scenario to consider: As soon as the lifting is done (i.e. we have received
            # the trade), this function is first called for the Weekend product before being called for the other
            # products, and we want the strategy to be able to place the weekend orders irrespective of the orders that
            # might be exposed at the saturday product. So it is not enough to reserve the quantity of the current
            # orders, we have to reserve the quantity of the orders that could be placed here after lifting is complete.
            # And this quantity is again capped by 2 times the max orderbook.
            # So by reserving here, we ensure that only the shorter products have to take orders on the longer products
            # into account (via the capacities) and not the other way round.
            self.reserve_capacities(capacities_mw, 2 * self.maximum_order_book, MOVEMENT_B_A)
            self.reserve_capacities(capacities_mw, 2 * self.maximum_order_book, MOVEMENT_A_B)

            self.debug_log("used capacities after reserving: {}".format(used_capacities()), product)
            return used_capacities()  # no other action while lifting
        if only_lift:
            self.debug_log("Not performing initiate action on the current callback.", product)
            return used_capacities()

        # Place initiating orders for arbitrage, if lifting wasn't needed
        # ---------------------------------------------------------------

        stat_a_sell, stat_a_buy = self.indicators(area_a, product)
        stat_b_sell, stat_b_buy = self.indicators(area_b, product)

        self.debug_log(
            "gas_arbitrage parameters for this product are: %s, max_orderbook: %s,"
            " stat_A_buy: %s stat_A_sell: %s stat_B_buy: %s stat_B_sell: %s" % (
                SU.log_locals(locals()), self.maximum_order_book, stat_a_buy, stat_a_sell, stat_b_buy, stat_b_sell),
            product)

        # how much we sell on A, depending on B public orders
        self._place_arbitrage_slot(current_timestamp, product, area_a, COMMON.Direction.sell,
                                   self.previous_best_sell_price_a.get(product.product_id),
                                   a_b_immediate_vesting_spread_sell, a_b_min_spread_sell,
                                   capacities_mw,
                                   (stat_a_sell, stat_a_buy), (stat_b_sell, stat_b_buy), True)

        # how much we sell on B, depending on A public orders
        self._place_arbitrage_slot(current_timestamp, product, area_b, COMMON.Direction.sell,
                                   self.previous_best_sell_price_b.get(product.product_id),
                                   a_b_immediate_vesting_spread_purchase, a_b_min_spread_purchase,
                                   capacities_mw,
                                   (stat_b_sell, stat_b_buy), (stat_a_sell, stat_a_buy), False)

        # how much we buy on A, depending on B public orders
        self._place_arbitrage_slot(current_timestamp, product, area_a, COMMON.Direction.buy,
                                   self.previous_best_buy_price_a.get(product.product_id),
                                   a_b_immediate_vesting_spread_purchase, a_b_min_spread_purchase,
                                   capacities_mw,
                                   (stat_a_sell, stat_a_buy), (stat_b_sell, stat_b_buy), True)

        # how much we buy on B, depending on A public orders
        self._place_arbitrage_slot(current_timestamp, product, area_b, COMMON.Direction.buy,
                                   self.previous_best_buy_price_b.get(product.product_id),
                                   a_b_immediate_vesting_spread_sell, a_b_min_spread_sell,
                                   capacities_mw,
                                   (stat_b_sell, stat_b_buy), (stat_a_sell, stat_a_buy), False)

        # memorize current front order prices to be able to use them in the next act iteration
        self.previous_best_sell_price_a[product.product_id] = stat_a_sell.best_price
        self.previous_best_sell_price_b[product.product_id] = stat_b_sell.best_price
        self.previous_best_buy_price_a[product.product_id] = stat_a_buy.best_price
        self.previous_best_buy_price_b[product.product_id] = stat_b_buy.best_price

        return used_capacities()

    def custom_act(self, log_data, timestamp, products=None, only_lift=False):
        """
        Loop over all products and place arbitrage orders.

        :param log_data: Unused
        :param timestamp: The current timestamp, which will be recorded when we place the slots
        :type timestamp: int or float
        :param unused_products: Unused
        :param only_lift: If this is set to True, the arbitrage strategy does not place any "initiate" slots.
                          This is currently True on on_trade_update callbacks.
                          Per definition, own trades do not change the price indicators, so existing exposed orders
                          do not have to be updated. What we want to prevent is new trade orders going to the exchange,
                          because we might have incomplete information (if the public  orderbook update corresponding
                          to the trade has not yet arrived)
        :type only_lift: bool
        """
        # Warning: We always have to loop over all products that might overlap.
        # (E.g. if we want saturday, we have to include the weekend and thus also the sunday product)
        # So we must not use the products passed into this function, but instead always loop over all products.
        # Performance wise, this should be ok, as there currently are at most 5 products.

        range_products = self.exchange.products.get_all()
        # only WD, DA, WE, Saturday, Sunday product
        range_products = [product for product in range_products if product.product_type in
                          ["DA", "WD", "W/END", "Saturday", "Sunday"]]

        if not range_products:
            return

        if products and not any(p in range_products for p in products):
            # If no update happened on any of the relevant products, we can skip this callback.
            return

        # range products can now be more than one. For example Day ahead from yesterday and Within day for today
        # delivering for the same period. They only differ in their trading state.

        # first calculate the remaining capacities

        traded_timeseries_mw, traded_timeseries_weekend_mw = self.get_traded_amount_timeseries_by_slot_type(
            range_products
        )

        a_b_capacity_series = copy.deepcopy(self.parameters.strategy_A_B_capacity)
        b_a_capacity_series = copy.deepcopy(self.parameters.strategy_B_A_capacity)

        # now that we have the traded timeseries, restrict the range products to only the active ones
        range_products = [product for product in range_products if "dummy" not in product.product_id]

        # only run for products currently active in both areas
        active_products = [
            product for product in range_products
            if (
                product.state(self.area_a) == COMMON.DeliveryAreaState.active
                and product.state(self.area_b) == COMMON.DeliveryAreaState.active
            )
        ]

        # sort products by interval length (we prefer longer products due to higer liqudity
        # (example, weekend has more liquidity as compared to Sunday Saturday)
        # we start with the bigger one because they would have a smaller or equal block then the rest
        active_products.sort(key=lambda p: p.delivery_end - p.delivery_start, reverse=True)

        self.prune_inactive_products_from_state(active_products)

        for product in active_products:

            remaining_a_b_capacity_mw, remaining_b_a_capacity_mw = self.calculate_remaining_capacity(
                self.area_a, self.area_b, product, a_b_capacity_series, b_a_capacity_series, traded_timeseries_mw
            )

            a_b_min_spread_purchase = self.parameters.strategy_A_B_min_spread_purchase.max_of_range(
                product.delivery_start, product.delivery_end
            )

            if a_b_min_spread_purchase is not None and a_b_min_spread_purchase > 0.:
                a_b_min_spread_purchase = 0.

            a_b_min_spread_sell = \
                self.parameters.strategy_A_B_min_spread_sell.max_of_range(product.delivery_start, product.delivery_end)

            if a_b_min_spread_sell is not None and a_b_min_spread_sell < 0.:
                a_b_min_spread_sell = 0.

            a_b_immediate_vesting_spread_purchase = (
                self.parameters.strategy_A_B_immediate_vesting_spread_purchase.min_of_range(
                    product.delivery_start, product.delivery_end
                )
            )
            a_b_immediate_vesting_spread_sell = (
                self.parameters.strategy_A_B_immediate_vesting_spread_sell.max_of_range(
                    product.delivery_start, product.delivery_end
                )
            )

            lift_sell_a_mw = self.calculate_lift_quantity(product, traded_timeseries_mw, traded_timeseries_weekend_mw,
                                                          original_area=self.area_b,
                                                          lift_area=self.area_a,
                                                          original_direction=COMMON.Direction.buy)

            lift_sell_b_mw = self.calculate_lift_quantity(product, traded_timeseries_mw, traded_timeseries_weekend_mw,
                                                          original_area=self.area_a,
                                                          lift_area=self.area_b,
                                                          original_direction=COMMON.Direction.buy)

            lift_buy_a_mw = self.calculate_lift_quantity(product, traded_timeseries_mw, traded_timeseries_weekend_mw,
                                                         original_area=self.area_b,
                                                         lift_area=self.area_a,
                                                         original_direction=COMMON.Direction.sell)

            lift_buy_b_mw = self.calculate_lift_quantity(product, traded_timeseries_mw, traded_timeseries_weekend_mw,
                                                         original_area=self.area_a,
                                                         lift_area=self.area_b,
                                                         original_direction=COMMON.Direction.sell)

            used_a_b_capacity, used_b_a_capacity = self.gas_arbitrage(
                timestamp, product, remaining_a_b_capacity_mw,
                remaining_b_a_capacity_mw, a_b_min_spread_purchase,
                a_b_min_spread_sell,
                a_b_immediate_vesting_spread_purchase,
                a_b_immediate_vesting_spread_sell,
                lift_sell_a_mw, lift_sell_b_mw, lift_buy_a_mw, lift_buy_b_mw,
                only_lift=only_lift
            )

            self.debug_log("Performed arbitrage for this product, and the used capacities are, "
                           "AB capacity: {}, BA capacity; {}".format(used_a_b_capacity, used_b_a_capacity), product)

            for ts_from in range(product.delivery_start, product.delivery_end, COMMON.HOUR):
                try:
                    a_b_capacity_series[ts_from] = (a_b_capacity_series[ts_from] or 0.) - used_a_b_capacity
                except KeyError:
                    a_b_capacity_series[ts_from] = -used_a_b_capacity
                try:
                    b_a_capacity_series[ts_from] = (b_a_capacity_series[ts_from] or 0.) - used_b_a_capacity
                except KeyError:
                    b_a_capacity_series[ts_from] = -used_b_a_capacity

    def calculate_lift_quantity(self, product, traded_timeseries, traded_timeseries_weekend,
                                original_area, lift_area, original_direction):
        """
        Calculate the quantity that we need to lift on a product, in a direction and on an area.

        There is special logic for the weekend product, because it is currently the only case
        where 2 products for overlapping delivery times can be traded at the same time.

        :param product: The product to investigate. Note that we can perform lifts after product rotation
                        (i.e. If we had an imbalance when the day-ahead product for wednesday closed,
                        we can balance out on the wednesday within day product)
        :type product: autotrader_core.exchange_trading.Product
        :param traded_timeseries: As returned from get_traded_amount_timeseries_by_slot_type
        :type traded_timeseries: dict
        :param traded_timeseries_weekend: As returned from get_traded_amount_timeseries_by_slot_type
        :type traded_timeseries_weekend: dict
        :param original_area: Check for imbalances where the initial trade was made on this area...
        :type original_area: string
        :param lift_area: ... and we have to lift on this area
        :type lift_area: string
        :param original_direction: Check for imbalances where the original trade was in this direction.
                                   If this is "sell", we need to buy when lifting.
        :type original_direction: string
        :return: The quantity that we need to lift.
        :rtype: float
        """
        def max_lift(a, b):
            """
            Return the difference between area A and B if positive,
            or zero if negative
            :param a: area 1
            :type a: float
            :param b: area 2
            :type b: float
            :rtype: float
            """
            return max(0, a - b)

        if original_direction == COMMON.Direction.buy:
            original_slot = SLOT_BUY_ARBITRAGE
            lift_slot = SLOT_SELL_ARBITRAGE_LIFT
        else:
            original_slot = SLOT_SELL_ARBITRAGE
            lift_slot = SLOT_BUY_ARBITRAGE_LIFT

        lift_weekend = self.calculate_and_block(max_lift,
                                                product.delivery_start, product.delivery_end,
                                                traded_timeseries_weekend[original_area][original_slot],
                                                traded_timeseries_weekend[lift_area][lift_slot])
        if product.product_type == "W/END":
            return lift_weekend
        else:
            lift = self.calculate_and_block(max_lift,
                                            product.delivery_start, product.delivery_end,
                                            traded_timeseries[original_area][original_slot],
                                            traded_timeseries[lift_area][lift_slot])
            if lift and lift_weekend:
                self.debug_log("total lift: {} will be reduced by weekend lift {}".format(lift, lift_weekend), product)
            return lift - lift_weekend

    def on_strategy_update(self, strategy_json):
        super(CustomStrategy, self).on_strategy_update(strategy_json)
        self.price_tolerance = self.validate_price_tolerance(PRICE_TOLERANCE)
        self.minimum_order_book = MIN_QTY_PLACEMENT
        self.maximum_order_book = abs(self.strategy_settings["maximum_order_book"] or 1)
        self.parameters.update(strategy_json)

    def custom_on_order_book_update(self, orders, timestamp):
        products = set(order.product for order in orders)
        self.act(timestamp, products)

    def custom_on_trade_update(self, trades, timestamp):
        products = set(trade.product for trade in trades)
        self.act(timestamp, products, only_lift=True)

    def custom_on_public_trade_update(self, trades, timestamp):
        pass

    def custom_on_products_update(self, products, timestamp):
        self.act(timestamp, products)

    def custom_on_timer(self, timestamp):
        products = self.exchange.products.get_all()
        self.act(timestamp, products)
