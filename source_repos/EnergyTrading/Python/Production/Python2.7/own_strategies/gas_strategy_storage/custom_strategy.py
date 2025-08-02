#!/usr/bin/env python
# -*- coding: utf-8 -*-
import logging
from collections import defaultdict

import autotrader_core.strategy as STRATEGY
import autotrader_core.common as COMMON
import autotrader_core.gas_strategy_parameters as GSP
import autotrader_core.exchange_trading as APITR
import autotrader_core.strategy_utils as SU
import autotrader_lib.cet_util as CETUTIL

log = logging.getLogger('autotrader.gas_storage_strategy')

SLOT_SELL_STORAGE = "sell_storage"
SLOT_BUY_STORAGE = "buy_storage"

INDICATOR_MW_STEP = 5

# 5MW steps, minimum orderbook volume on counter side to use in immediate execution
MIN_VOL_FOR_IMMEDIATE_EXEC_INDEX = 0  # front

# 5MW steps, place in front of public order, if spread exists on this level.
MINIMUM_SPREAD_INDEX_INDICATOR = 15  # 75 MW level, or 1800 PEG_MWH_DAY level

TRAYPORT_BROKER_ID = COMMON.Broker.eexs

# rounding for machine precision
FINAL_QTY_DIGITS = 2

# DEFAULT values, if exchange value is missing
DEFAULT_MIN_MWH_QTY = 1
DEFAULT_STEP_MWH_QTY = 0.1

EXECUTION_RESTRICTION = COMMON.ExecutionRestriction.non


class CustomStrategy(STRATEGY.GasStrategy):
    """ This is the Gas Storage Strategy which makes a profit by buying and selling at better prices.

    The two relevant variables are:
        inject capacity -> how much gas can be put into storage (limits how much we can buy)

        withdraw capacity -> how much gas can be taken from storage (limits how much we can sell)

    NOTE:
        The withdraw and inject capacities are correlated, since when gas is put in storage the inject capacity
        is reduced while the withdraw capacity increases


    The relevant settings for the strategy are, which are filled/computed by the customer:

        maximum_order_book_size
            regulates the size of the orders being placed

        strategy_price_purchase_immediate_vesting
            the strategy will actively aggress orders (buying) for prices lower than this price

        strategy_price_sales_immediate_vesting
            the strategy will actively aggress orders (selling) for prices higher than this price

        strategy_price_purchase
            the strategy will place (buy/bid) orders on the market at this price,
            if the order book is empty or almost empty, and wait for them to be aggressed

        strategy_price_sales
            the strategy will place (sell/ask) orders on the market at this price,
            if the order book is empty or almost empty, and wait for them to be aggressed

        strategy_storage_cutoff_purchase (user timeserie)
            the strategy will be prevented from placing any (buy/bid) order higher than this price

        strategy_storage_cutoff_sell (user timeserie)
            the strategy will be prevented from placing any (sell/ask) order lower than this price

        NOTE 1: The cutoff prices are filled manually and act as limits. However the usual strategy limits
        are also observed, just as an extra safety mechanism against errors in the cutoffs.


    """

    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        self.log = log
        self.parameters = GSP.Parameters()
        # maximum tradeable amount per order, initialized with 0, to make sure, no trades before first strategy update
        self.maximum_order_book = 0

        self.delivery_area = None

        self.exchange_1 = COMMON.Exchange.trayport

        self.broker_id = TRAYPORT_BROKER_ID
        self.execution_restriction = EXECUTION_RESTRICTION

    def get_traded_amount_timeseries_by_slot_type(self, products):
        # type: (list[APITR.Product]) -> dict[str,dict[str, dict[int, float]]]
        """

        :type products: list[APITR.Product]
        :return: quantities area/strategy_slot/timestamp
        :rtype: dict[str,dict[str, dict[int, float]]]
        """
        result = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))  # area -> slot -> ts -> value
        for product in products:
            trades = product.trades.get(trade_filter=COMMON.TradeFilter.own, portfolio_key=self.strategy_id)
            for t in trades:
                area = t.sell_delivery_area or t.buy_delivery_area
                for ts in range(product.delivery_start, product.delivery_end, COMMON.HOUR):
                    result[area][t.tags.get("strategy_slot", "")][ts] += t.quantity
        return result

    @staticmethod
    def _get_closest_to_zero(values):
        """
        Returns the value closest to 0, depending on sign of first value.
        If first value is positive, the smallest value of all positive values including 0 is returned.
        If first value is negative, the highest value of all negative values including 0 is returned.
        :type values: list[float]
        :return: value closest to 0
        :rtype: float
        """
        first = values[0]
        if first >= 0:
            closest = max(min(values), 0.)
        else:
            closest = min(max(values), 0.)

        return closest

    @staticmethod
    def calculate_and_block(formula, ts_from, ts_until, *parameters):
        """
        Calls `formula` for every hour in [ts_from, ts_to) with the vales for every hour from the timeseries provided
        in `parameters` and returns the value closest to 0 depending on the sing of the first result value.

        :param formula: a function
        :type formula: callable
        :type ts_from: int
        :type ts_until: int
        :param parameters: timeseries with the input values for `formula`, must cover [ts_from, ts_to) in hour res.
        :type parameters: tuple[dict[int, float]]
        :rtype: float
        """
        result = dict()  # type: dict[int, float]
        try:
            for ts in range(ts_from, ts_until, COMMON.HOUR):
                result[ts] = formula(*[param[ts] for param in parameters])
        except KeyError:
            log.debug("cannot build block, for ts: %s", ts)
            return 0.

        # now build a block
        values = result.values()

        return CustomStrategy._get_closest_to_zero(values)

    def get_indicators(self, area, product, depth):
        """ Get the best buy price and best sell price for the best (5 * depth) MWH

        :param area: area of the public orders
        :type area: COMMON.Area
        :param product: product of the public orders
        :type product: exchange_trading.Product
        :param depth: the first depth * 5 Mwh to get from the indicators
        :type depth: int
        :return: best buy and sell prices of the first 5 * DEEPNESS MWH in the orderbook
        :type (float, float) or (None, None)
        """
        try:
            indicators = product.orders.indicators(area)[0].mw_prices
            return indicators[0][depth], indicators[1][depth]
        except IndexError:
            return None, None

    def mk_slot(self, name, direction, quantity, price):
        """ Helper function for creating a slot and defaulting some of the values """
        return STRATEGY.PositionSlot(
            name, direction, quantity, price,
            quantity_range_lo=quantity, quantity_range_hi=quantity,
            price_range_hi=price, price_range_lo=price,
            execution_restriction=self.execution_restriction,
            tick_size=self.exchange.tick_size, broker_id=self.broker_id)

    def place_slot_with_log(self, product, timestamp, delivery_area_index, slots, mode):
        """Helper function to place the created slots and emit useful log messages

        :type product: APITR.Product
        :type timestamp: float
        :param delivery_area_index: hardcoded 0 ?
        :type delivery_area_index: int
        :param slots: list containing buy_slot and sell_slot
        :type slots: list[STRATEGY.PositionSlot]
        :type mode: str
        :rtype: None
        """
        product_interval = (product.delivery_start, product.delivery_end)
        max_buy_price_ts = self.strategy_limit_maximum_purchase_price.get(product_interval)
        max_buy_price_product = self.per_product_limits.get_limit("maximum_purchase_price", product)
        min_sales_price_ts = self.strategy_limit_minimum_sales_price.get(product_interval)
        min_sales_price_product = self.per_product_limits.get_limit("minimum_sales_price", product)
        buy_price_limit = None
        if max_buy_price_product is not None or max_buy_price_ts is not None:
            # max(10, None) => 10, it is enough if 1 is not None
            buy_price_limit = max(max_buy_price_product, max_buy_price_ts)

        sell_price_limit = None
        if min_sales_price_ts is not None:
            # min(10, None) => None, for minimum both must be not None
            sell_price_limit = min_sales_price_ts
            if min_sales_price_product is not None:
                sell_price_limit = min(sell_price_limit, min_sales_price_product)
        elif min_sales_price_product is not None:
            sell_price_limit = min_sales_price_product

        for slot in slots:
            self.debug_log("Placing slot, slot_type: {}, {}-{}@{}, mode:{}".format(
                slot.slot_type, slot.direction, slot.quantity, slot.price, mode
            ), product)

        for o in product.orders.get(self.delivery_areas[delivery_area_index], order_filter=COMMON.OrderFilter.own,
                                    portfolio_key=self.strategy_id):
            self.debug_log("Current placed own order in product: {}-{}@{}, tags:{}".format(
                o.direction, o.quantity, o.price, o.tags
            ), product)

        self.place_slots({}, product, timestamp, self.delivery_areas[delivery_area_index],
                         slots, [mode],
                         limit_minimum_sales_price=sell_price_limit,
                         limit_maximum_purchase_price=buy_price_limit,
                         execmode=COMMON.InternalExecutionMode.exchange_base_price)

    @staticmethod
    def immediate_vesting_peg(product, public_order_direction, immediate_execution_price,
                              min_orderbook_volume_for_pricing, cap_quantity, property, delivery_area_id=None):
        """Check in the order book if an immediate vesting is possible

        If direction is sell, we would be placing a buy order therefore the immediate_execution_price parameter
        is the price on the buy side and vice versa

        if no order can be placed with immediate execution, return 0,0

        :type product:  autotrader_core.exchange_trading.Product
        :param public_order_direction: Direction of public order.
                                       This is the counter direction.
                                       e.g. "buy": public order is buy, and our own order will be sell.
                                       We check here, if there is a good enough public order for immediate execution
        :type public_order_direction: str
        :param immediate_execution_price: own order immediate execution price.
                                          if public order direction is "buy",
                                          then this is our own sell immediate execution price
        :type immediate_execution_price: float
        :param min_orderbook_volume_for_pricing: [MWH_D] or [MW], depending on property,
                                    this is the required volume for immediate execution,
                                    but not the volume at which the price is taken
        :type min_orderbook_volume_for_pricing: float
        :type cap_quantity: float
        :type property: Property
        :type delivery_area_id: str
        :rtype: float, float
        """
        quantity, price = 0, 0

        # if there is not enough volume
        if public_order_direction == "buy":
            # check if the minimum volume needed for pricing is available
            price_at_required_vol, _ = product.orders.get_price_at_min_volume(
                min_orderbook_volume_for_pricing,
                COMMON.OrderFilter.public_buy,
                min_order_size=property.min_quantity,
                delivery_area_id=delivery_area_id)
        else:
            price_at_required_vol, _ = product.orders.get_price_at_min_volume(
                min_orderbook_volume_for_pricing,
                COMMON.OrderFilter.public_sell,
                min_order_size=property.min_quantity,
                delivery_area_id=delivery_area_id)
        if price_at_required_vol is None:
            return 0, 0

        # if minimum volume is reached, then find the price at the minimum placement quantity -> front order price
        if public_order_direction == "buy":
            # min_price := price for the min_quantity, which is actually Property.min_quantity
            front_order_price, front_order_quantity = product.orders.get_price_at_min_volume(
                property.min_quantity, COMMON.OrderFilter.public_buy,
                delivery_area_id=delivery_area_id
            )
        else:
            front_order_price, front_order_quantity = product.orders.get_price_at_min_volume(
                property.min_quantity, COMMON.OrderFilter.public_sell, delivery_area_id=delivery_area_id
            )

        # defensive code, this should make sure, that the minimum quantity is also fulfilled
        if front_order_price is None:
            return 0, 0

        # if the front price exists, then now round the quantity according to the public front order price
        if public_order_direction == "buy":
            if front_order_price >= immediate_execution_price:
                price = front_order_price
                quantity = SU.load_rounder(front_order_quantity, property.min_quantity, property.qty_tick,
                                           max_amount=cap_quantity)
        else:  # direction == sell
            if front_order_price <= immediate_execution_price:
                price = front_order_price
                quantity = SU.load_rounder(front_order_quantity, property.min_quantity, property.qty_tick,
                                           max_amount=cap_quantity)

        return quantity, price

    def place_storage(self, timestamp, active_product, remaining_storage_inject_capacity,
                      remaining_storage_withdraw_capacity, storage_price_purchase_immediate_vesting,
                      storage_price_sell_immediate_vesting, storage_default_price_purchase, storage_default_price_sell,
                      storage_cutoff_price_purchase, storage_cutoff_price_sell):
        """
        passed in values already have to correct unit, no conversion needed.
        :type timestamp: float
        :type active_product: autotrader_core.exchange_trading.Product
        :param remaining_storage_inject_capacity: [MW] or [MWH_D] in PEG MODE
        :type remaining_storage_inject_capacity: float
        :param remaining_storage_withdraw_capacity: [MW] or [MWH_D] in PEG MODE
        :type remaining_storage_withdraw_capacity: float
        :type storage_price_purchase_immediate_vesting: float
        :type storage_price_sell_immediate_vesting: float
        :type storage_default_price_purchase: float
        :type storage_default_price_sell: float
        :type storage_cutoff_price_purchase: float
        :type storage_cutoff_price_sell: float
        :rtype: tuple[float, float]
        """

        if None in (remaining_storage_inject_capacity, remaining_storage_withdraw_capacity,
                    storage_price_purchase_immediate_vesting, storage_price_sell_immediate_vesting,
                    storage_default_price_purchase, storage_default_price_sell,
                    storage_cutoff_price_purchase, storage_cutoff_price_sell):

            # in case there are some configurations missing we should not act on that product

            self.warn_log(
                "Configuration was incomplete, current parameters are: {}".format(SU.log_locals(locals())),
                active_product
            )

            # data missing, no activity
            sell_slot = self.mk_slot(SLOT_SELL_STORAGE, COMMON.Direction.sell, 0., 0.)
            buy_slot = self.mk_slot(SLOT_BUY_STORAGE, COMMON.Direction.buy, 0., 0.)
            self.place_slot_with_log(active_product, timestamp, 0, [buy_slot, sell_slot], "no_config")
            # return capacities unchanged
            return remaining_storage_inject_capacity, remaining_storage_withdraw_capacity

        properties = self.get_trayport_properties(product_id=active_product.product_id)
        tick_size = properties.price_tick

        # set unit conversion factor depending on contract unit
        if properties.unit in (COMMON.Units.MW, COMMON.Units.MWH):
            unit_conversion_factor = 1
        else:
            # if units are PEG_MWH_DAY, also use aon execution restriction
            unit_conversion_factor = 24

        # maximum orderbook is always transferred as MW from periotheus
        converted_maximum_order_book = self.maximum_order_book * unit_conversion_factor

        if converted_maximum_order_book < properties.min_quantity:
            self.warn_log("Maximum order limit ({}) < minimum quantity ({}) - cannot trade!, "
                          "conversion factor: {}, unit: {}"
                          .format(converted_maximum_order_book, properties.min_quantity, unit_conversion_factor,
                                  properties.unit), active_product)
            return remaining_storage_inject_capacity, remaining_storage_withdraw_capacity

        # get prices for immediate execution
        min_orderbook_volume_to_place_imm_execution = (
            MIN_VOL_FOR_IMMEDIATE_EXEC_INDEX * INDICATOR_MW_STEP * unit_conversion_factor
        )
        # MW steps are 10 -> MWH/DAY steps: 240
        # indicator MW steps are 5 -> MWH/DAY steps: 240
        # for MW, check 75MW level -> MWH/DAY -> check 1800MWH/DAY level
        # Problem: indicators always think they use MW, and always have 5 (whatever unit) steps.
        # -> solution, manually add up all the orders, until the given level is reached.

        # 0 -> 0 MW / 0MWH/DAY
        # 1 -> 5 MW / 120MWH/DAY
        # 2 -> 10 MW / 240MWH/DAY

        # get prices for at minimum spread level
        # volume_to_check := 15 * 5 * fac == 75 * 24 == 1800 MWH_D
        volume_to_check = MINIMUM_SPREAD_INDEX_INDICATOR * 5 * unit_conversion_factor
        best_buy_price_for_minimum_spread, _ = active_product.orders.get_price_at_min_volume(
            volume=volume_to_check,
            order_filter=COMMON.OrderFilter.public_buy,
            delivery_area_id=self.delivery_area_id
        )
        best_sell_price_for_minimum_spread, _ = active_product.orders.get_price_at_min_volume(
            volume=volume_to_check,
            order_filter=COMMON.OrderFilter.public_sell,
            delivery_area_id=self.delivery_area_id
        )

        # front order
        best_buy_price, _ = active_product.orders.get_price_at_min_volume(
            volume=properties.min_quantity,
            order_filter=COMMON.OrderFilter.public_buy,
            delivery_area_id=self.delivery_area_id
        )
        best_sell_price, _ = active_product.orders.get_price_at_min_volume(
            volume=properties.min_quantity,
            order_filter=COMMON.OrderFilter.public_sell,
            delivery_area_id=self.delivery_area_id
        )

        # quantity is the rest of the position capped
        sell_qty = max(0, remaining_storage_withdraw_capacity)
        sell_qty = SU.load_rounder(sell_qty, properties.min_quantity, properties.qty_tick,
                                   max_amount=converted_maximum_order_book)

        buy_qty = max(0, remaining_storage_inject_capacity)
        buy_qty = SU.load_rounder(buy_qty, properties.min_quantity, properties.qty_tick,
                                  max_amount=converted_maximum_order_book)

        # SELL SIDE CHECKS
        public_buy_orderbook_volume = active_product.orders.get_volume(self.delivery_area_id,
                                                                       order_filter=COMMON.OrderFilter.public_buy)

        # check if enough volume is in the orderbook to use immediate execution
        immediate_volume_sell, price_sell = 0, 0
        if public_buy_orderbook_volume > min_orderbook_volume_to_place_imm_execution:
            # check public buy side for sell side placement
            immediate_volume_sell, price_sell = self.immediate_vesting_peg(active_product, COMMON.Direction.buy,
                                                                           storage_price_sell_immediate_vesting,
                                                                           min_orderbook_volume_to_place_imm_execution,
                                                                           sell_qty, properties, self.delivery_area_id)

        if immediate_volume_sell > 0:
            mode = "immediate"
            sell_slot = self.mk_slot(SLOT_SELL_STORAGE, COMMON.Direction.sell, immediate_volume_sell, price_sell)
        elif best_sell_price_for_minimum_spread is not None:
            sell_slot = self.mk_slot(SLOT_SELL_STORAGE, COMMON.Direction.sell, sell_qty,
                                     best_sell_price - self.exchange.tick_size)
            mode = "minimum_spread"
        else:
            sell_slot = self.mk_slot(SLOT_SELL_STORAGE, COMMON.Direction.sell, sell_qty, storage_default_price_sell)
            mode = "default"
        mode += "|Unit:" + properties.unit + "|convFact[MW]:" + str(round(unit_conversion_factor))
        sell_slot.price = max(sell_slot.price, storage_cutoff_price_sell)
        self.place_slot_with_log(active_product, timestamp, 0, [sell_slot], mode)

        # BUY SIDE CHECKS
        public_sell_orderbook_volume = active_product.orders.get_volume(self.delivery_area_id,
                                                                        order_filter=COMMON.OrderFilter.public_sell)

        # check if enough volume is in the orderbook to use immediate execution
        immediate_volume_buy, price_buy = 0, 0
        if public_sell_orderbook_volume > min_orderbook_volume_to_place_imm_execution:
            # check public sell side for buy side placement
            immediate_volume_buy, price_buy = self.immediate_vesting_peg(active_product, COMMON.Direction.sell,
                                                                         storage_price_purchase_immediate_vesting,
                                                                         min_orderbook_volume_to_place_imm_execution,
                                                                         buy_qty, properties, self.delivery_area_id)

        if immediate_volume_buy > 0:
            mode = "immediate"
            buy_slot = self.mk_slot(SLOT_BUY_STORAGE, COMMON.Direction.buy, immediate_volume_buy, price_buy)

        elif best_buy_price_for_minimum_spread is not None:
            buy_slot = self.mk_slot(SLOT_BUY_STORAGE, COMMON.Direction.buy, buy_qty,
                                    best_buy_price + self.exchange.tick_size)
            mode = "minimum_spread"
        else:
            buy_slot = self.mk_slot(SLOT_BUY_STORAGE, COMMON.Direction.buy, buy_qty, storage_default_price_purchase)
            mode = "default"

        mode += "|Unit:" + properties.unit + "|convFact[MW]:" + str(round(unit_conversion_factor))
        buy_slot.price = min(buy_slot.price, storage_cutoff_price_purchase)
        self.place_slot_with_log(active_product, timestamp, 0, [buy_slot], mode)

        return (max(0, remaining_storage_inject_capacity - buy_slot.quantity),
                max(0, remaining_storage_withdraw_capacity - sell_slot.quantity))

    def act_for_interval(self, ts_from, ts_until, timestamp):
        """

        :type ts_from: int
        :type ts_until: int
        :type timestamp: float
        """
        # get all relevant products for this time interval

        # Day-Ahead Saturday
        # Weekend (Saturday/Sunday)
        # need to consider both, to not sell more than we have
        # e.g. sell 240 MWh/Day on Saturday
        # e.g. sell 240 MWh/Day over weekend
        # -> need to have 480 MWh/Day capacity on Saturday, 240 MWh/Day on Sunday

        range_products = [
            p for p in self.exchange.products.get_all()
            if p.delivery_start < ts_until and p.delivery_end > ts_from
        ]

        # use the filtering function to only take the products which we are using (DA, WD, W/END)
        range_products = self.filter_products(range_products)

        if not range_products:
            self.debug_log("No range products found after filter for block [{}-{}, {}-{}] in {}, returning".format(
                CETUTIL.utc_ts2cet_str(ts_from), CETUTIL.utc_ts2cet_str(ts_until), ts_from, ts_until,
                self.delivery_area
            ))
            return

        # calculate what has already been traded
        traded_timeseries = self.get_traded_amount_timeseries_by_slot_type(range_products)

        # now that we have the traded timeseries, restrict the range products to only the current ones
        range_products = [product for product in range_products if "dummy" not in product.product_id]

        # now calculate active products for the delivery areas (ones we can still trade on)
        active_products = [
            product for product in range_products
            if (product.state(self.delivery_areas[0]) == COMMON.DeliveryAreaState.active)
        ]

        def f_remaining_storage_inject_capacity(max_inject, max_withdraw, sell_storage, buy_storage):
            """ Helper function which computes the remaining capacity from the user filled max capacities
            and information on what was already traded

            It is important to compare hour by hour, since the hour value gives the upper bound what can be moved
            This is different to the position closer,
            where a daily amount might need to be closed, and also passed hours have to be considered
            """
            return min(max(0, SU.get_value_or_zero(max_inject) - buy_storage + sell_storage),
                       SU.get_value_or_zero(max_inject) + SU.get_value_or_zero(max_withdraw)
                       )

        # example
        # storage has 720 MWH/DAY can be stored (can be loaded into storage)
        # currently 480 MWH/DAY is already getting stored by other trades
        # left over capacity for buy: 240 MWH/DAY
        remaining_storage_inject_capacity = self.calculate_and_block(
            f_remaining_storage_inject_capacity,
            ts_from, ts_until,
            self.parameters.strategy_position_tradable_position_short,
            self.parameters.strategy_position_tradable_position_long,
            traded_timeseries[self.delivery_areas[0]][SLOT_SELL_STORAGE],
            traded_timeseries[self.delivery_areas[0]][SLOT_BUY_STORAGE]
        )

        def f_remaining_storage_withdraw_capacity(max_inject, max_withdraw, sell_storage,
                                                  buy_storage):
            """ Helper function which computes the remaining capacity from the user filled max capacities
            and information on what was already traded"""
            return min(max(0, SU.get_value_or_zero(max_withdraw) + buy_storage - sell_storage),
                       SU.get_value_or_zero(max_inject) + SU.get_value_or_zero(max_withdraw))

        remaining_storage_withdraw_capacity = self.calculate_and_block(
            f_remaining_storage_withdraw_capacity,
            ts_from, ts_until,
            self.parameters.strategy_position_tradable_position_short,
            self.parameters.strategy_position_tradable_position_long,
            traded_timeseries[self.delivery_areas[0]][SLOT_SELL_STORAGE],
            traded_timeseries[self.delivery_areas[0]][SLOT_BUY_STORAGE]
        )

        storage_price_purchase_immediate_vesting = \
            self.parameters.strategy_price_purchase_immediate_vesting.min_of_range(ts_from, ts_until)
        storage_price_sell_immediate_vesting = \
            self.parameters.strategy_price_sales_immediate_vesting.max_of_range(ts_from, ts_until)
        storage_default_price_purchase = \
            self.parameters.strategy_price_purchase.min_of_range(ts_from, ts_until)
        storage_default_price_sell = \
            self.parameters.strategy_price_sales.max_of_range(ts_from, ts_until)
        storage_cutoff_price_purchase = \
            self.parameters.strategy_storage_cutoff_purchase.min_of_range(ts_from, ts_until)
        storage_cutoff_price_sell = \
            self.parameters.strategy_storage_cutoff_sell.max_of_range(ts_from, ts_until)

        self.debug_log(
            "Remaining Capacities for block [{}-{}, {}-{}] in {}:"
            " Inject/Withdraw:{}/{},"
            " traded: [[{}//{}]],"
            " open: [[{}//{}]],"
            " prices: [[immex:{}//{}, default:{}//{}, cutoff:{}//{}]]"
            " active products:{}".format(
                CETUTIL.utc_ts2cet_str(ts_from), CETUTIL.utc_ts2cet_str(ts_until), ts_from, ts_until,
                self.delivery_area,
                # remaining capacities:
                remaining_storage_inject_capacity, remaining_storage_withdraw_capacity,
                # info about traded and open hourly:
                [traded_timeseries[self.delivery_areas[0]][SLOT_BUY_STORAGE][ts] for ts in
                 range(ts_from, ts_until, COMMON.HOUR)],
                [traded_timeseries[self.delivery_areas[0]][SLOT_SELL_STORAGE][ts] for ts in
                 range(ts_from, ts_until, COMMON.HOUR)],
                [self.parameters.strategy_position_tradable_position_short[ts] for ts in
                 range(ts_from, ts_until, COMMON.HOUR)],
                [self.parameters.strategy_position_tradable_position_long[ts] for ts in
                 range(ts_from, ts_until, COMMON.HOUR)],
                # price information
                storage_price_purchase_immediate_vesting, storage_price_sell_immediate_vesting,
                storage_default_price_purchase, storage_default_price_sell,
                storage_cutoff_price_purchase, storage_cutoff_price_sell,
                # active products for this block
                ",".join([p.name for p in active_products])
            ))

        for active_product in active_products:
            # update memory of remaining quantities, and reuse them each iteration
            remaining_storage_inject_capacity, remaining_storage_withdraw_capacity = \
                self.place_storage(timestamp, active_product, remaining_storage_inject_capacity,
                                   remaining_storage_withdraw_capacity, storage_price_purchase_immediate_vesting,
                                   storage_price_sell_immediate_vesting, storage_default_price_purchase,
                                   storage_default_price_sell, storage_cutoff_price_purchase, storage_cutoff_price_sell)

    def custom_act(self, log_data, timestamp, products=None):
        """

        :type log_data: list
        :type timestamp: int
        :type products: list[autotrader_core.exchange_trading.Product]
        """
        if not products:
            return

        # get daily ranges to run on
        ranges = set()  # type: set[tuple(int, int)]
        for product in products:
            if product.delivery_start > timestamp and not product.product_id.startswith("dummy"):
                ranges.add((product.delivery_start, product.delivery_end))

        for start, end in ranges:
            self.act_for_interval(start, end, timestamp=timestamp)

    def on_strategy_update(self, strategy_json):
        super(CustomStrategy, self).on_strategy_update(strategy_json)
        self.maximum_order_book = abs(self.strategy_settings["maximum_order_book"] or 1)
        self.parameters.update(strategy_json)

        self.delivery_area = self.delivery_areas[0]
        self.exchange_1 = COMMON.Exchange.trayport

    def custom_on_order_book_update(self, orders, timestamp):
        # we want to ensure whenever the order book changes
        products = set(order.product for order in orders)
        products = self.filter_products(products_list=products)
        self.act(timestamp, products)

    def custom_on_trade_update(self, trades, timestamp):
        # we want to ensure we act whenever we make a trade
        products = set(trade.product for trade in trades)
        products = self.filter_products(products_list=products)
        self.act(timestamp, products)

    def custom_on_public_trade_update(self, trades, timestamp):
        # we do not need to act on public trade updates because those will also cause order book update
        pass

    def custom_on_products_update(self, products, timestamp):
        self.act(timestamp, products)

    def custom_on_products_queue(self, products, timestamp):
        pass

    def custom_on_timer(self, timestamp):
        products = self.autotrader.trayport.products.get_all()
        products = self.filter_products(products_list=products)

        self.act(timestamp, products)
