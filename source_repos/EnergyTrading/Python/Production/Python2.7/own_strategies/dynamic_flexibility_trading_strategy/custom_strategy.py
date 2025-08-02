#!/usr/bin/env python
# -*- coding: utf-8 -*-

import copy
import logging

import autotrader_core.api as API
import autotrader_core.common as COMMON
import autotrader_core.exchange_trading as APITR
import autotrader_core.exchanges as APIEXCH
import autotrader_core.strategy as strategy
import autotrader_lib.cet_util as ALCU
from autotrader_core.common import (DeliveryAreaState, Direction, InternalExecutionMode)
from autotrader_core.strategy import PositionSlot

log = logging.getLogger('autotrader.dynamic_flexibility_trading_strategy')

# MODIFIABLE
MAX_NUMBER_SCALES = 6
MAX_OTR_DEFAULT_VALUE = 90.
BRUTE_FORCE_LEVEL_OF_MAX_OTR = 0.8
FORCE_LEVEL_OF_MAX_OTR = 0.6
OTR_LIMIT_TO_PLACE_WITH_10SEC_LATENCY = 40
MAX_ORDER_BOOK_QUANTITY_RATE = 0.1

# NOT MODIFIABLE
ALLOW_HOUR_QUARTER = 0
ALLOW_HOUR = 1
ALLOW_QUARTER = 2


PRODUCTS_FILTER_DEFAULT = ALLOW_HOUR_QUARTER

SELL_SLOTNAME = "sell_flex"
BUY_SLOTNAME = "buy_flex"
SELL_TRADEBACK_SLOTNAME = "sell_tradeback"
BUY_TRADEBACK_SLOTNAME = "buy_tradeback"

TRADEBACK_PLACEMENT_MODE = ""

RAMP_DEFAULT = 10000.

HOUR_FILTERS = ("Intraday_Hour_Power",  # EPEX
                "XBID_Hour_Power",  # EPEX
                "NX_Intraday_Power_D")  # Nordpool
QUARTER_HOUR_FILTERS = ("Intraday_Quarter_Hour_Power",  # EPEX
                        "XBID_Quarter_Hour_Power",  # EPEX
                        "NX_Intraday_Power_D_QH")  # Nordpool

ACCEPTABLE_PRODUCT_TYPES = HOUR_FILTERS + QUARTER_HOUR_FILTERS


# TODO: Round price & Quantity in place_slots, so we don't need to do that in strategy
# TODO: Add tolerances for quantities as well, e.g. if price between a and b, quantity tolerance is between x and y?
# TODO: Ramp avoids hypertrading in quarters


class StrategyBehavior(object):
    """Depending on Strategy Behaviour and time to trading end, latency and placement mode are set"""
    balanced = "BALANCED"
    safe = "SAFE_CLOSURE"
    unsafe = "UNSAFE_CLOSURE"


class PlacementMode(object):
    """The placement mode defines price finding mechanism"""
    lazy = "LAZY"
    active = "ACTI"
    progressive = "PROG"
    aggressive = "AGGR"
    bruteforce = "BRUTE"


class MatrixBuilder(object):
    def build_scale_steering_matrix(self, ts_from, ts_until):
        """Build scales for 1-Hour time ranges, defining price and quantity levels for each quarter hour

        :param ts_from: start timestamp
        :param ts_until: end timestamp (after 3600seconds duration)
        :type ts_from: int
        :type ts_until: int
        :return: list

        Steps:

        Read values from Periotheus time series. First for standard price and quantity from:
        - position_tradable_position_long
        - position_tradable_position_short
        - price_purchase
        - price_sales

        Furthermore get the price levels from user defined scale time series:
        - position_long_scale_<number>
        - position_short_scale_<number>
        - tradeable_price_purchase_scale_<number>
        - tradeable_price_sales_scale_<number>

        Build list for quantities and prices on each price level for each quarter. Example with 2 scale steps.
        The values will be represented by the time series name, which should provide the value for that timestamp.

        initialization:
        ---------------

        scale =                 [
               0 sec entry          [[], []],
             900 sec entry          [[], []],
            1800 sec entry          [[], []],
            2700 sec entry          [[], []]
                                ]

        added standard values:
        ----------------------

        scale =                 [
               [0]   = 0 sec entry     [
               [0][0]= bid                    [(scale_pos_short_name, tradeable_price_purchase_name)],
               [0][1]= ask                    [(scale_pos_long_name, tradeable_price_sales_name)],
                                       ],
               [1]   = 900 sec entry   [
               [1][0]= bid                    [(scale_pos_short_name, tradeable_price_purchase_name)],
               [1][1]= ask                    [(scale_pos_long_name, tradeable_price_sales_name)],
                                       ],
               [2]   = 1800 sec entry  [
               [2][0]= bid                    [(scale_pos_short_name, tradeable_price_purchase_name)],
               [2][1]= ask                    [(scale_pos_long_name, tradeable_price_sales_name)],
                                       ],
               [3]   = 2700 sec entry  [
               [3][0]= bid                    [(scale_pos_short_name, tradeable_price_purchase_name)],
               [3][1]= ask                    [(scale_pos_long_name, tradeable_price_sales_name)],
                                       ]
                                  ]

        added 2 scales values:
        ----------------------

        scale =                     [
               [0]=0 sec entry          [
               [0][0]=bid                    [
               [0][0][0]                             (scale_pos_short, tradeable_price_purchase),
               [0][0][1]                             (position_short_scale_1, tradeable_price_purchase_scale_1),
               [0][0][2]                             (position_short_scale_2, tradeable_price_purchase_scale_2)
                                             ],
               [0][1]=ask                    [
               [0][1][0]                             (scale_pos_long, tradeable_price_sales),
               [0][1][1]                             (position_long_scale_1, tradeable_price_sales_scale_1),
               [0][1][2]                             (position_long_scale_2, tradeable_price_sales_scale_2)
                                            ],
                                        ],
               [1]=900 sec entry        [
               [1][0]=bid                    [
               [1][0][0]                             (scale_pos_short, tradeable_price_purchase),
               [1][0][1]                             (position_short_scale_1, tradeable_price_purchase_scale_1),
               [1][0][2]                             (position_short_scale_2, tradeable_price_purchase_scale_2)
                                             ],
               [1][1]=ask                    [
               [1][1][0]                             (scale_pos_long, tradeable_price_sales),
               [1][1][1]                             (position_long_scale_1, tradeable_price_sales_scale_1),
               [1][1][2]                             (position_long_scale_2, tradeable_price_sales_scale_2)
                                            ],
                                        ],
               [2]=1800 sec entry       [
               [2][0]=bid                    [
               [2][0][0]                             (scale_pos_short, tradeable_price_purchase),
               [2][0][1]                             (position_short_scale_1, tradeable_price_purchase_scale_1),
               [2][0][2]                             (position_short_scale_2, tradeable_price_purchase_scale_2)
                                             ],
               [2][1]=ask                    [
               [2][1][0]                             (scale_pos_long, tradeable_price_sales),
               [2][1][1]                             (position_long_scale_1, tradeable_price_sales_scale_1),
               [2][1][2]                             (position_long_scale_2, tradeable_price_sales_scale_2)
                                            ],
                                        ],
               [3]=2700 sec entry       [
               [3][0]=bid                    [
               [3][0][1]                             (scale_pos_short, tradeable_price_purchase),
               [3][0][2]                             (position_short_scale_1, tradeable_price_purchase_scale_1),
               [3][0][3]                             (position_short_scale_2, tradeable_price_purchase_scale_2)
                                             ],
               [3][1]=ask                    [
               [3][1][0]                             (scale_pos_long, tradeable_price_sales),
               [3][1][1]                             (position_long_scale_1, tradeable_price_sales_scale_1),
               [3][1][2]                             (position_long_scale_2, tradeable_price_sales_scale_2)
                                             ],
                                        ]
                                    ]

        these scales are then sorted by price.
        """
        # scale is [interval_index][<buy/sell>][scale_number, 0...][quantity=0,price=1]
        # the quantity in the scale is not accumulative, thus a scale of
        # [3, 40], [5, 43] means that a total quantity of 8 is available for 2 different prices
        scale = [[[], []] for unused_interval in range(ts_from, ts_until, COMMON.QUARTER)]

        def from_timeseries(name, ts, default):
            try:
                series = getattr(self, name)
            except AttributeError:
                return default
            return series.get((ts, ts + COMMON.QUARTER), default)

        # first add the standard timeseries to the scale (as scale 0)
        scale_pos_long_name = COMMON.StrategyJsonKey.TS.pos_sell
        scale_pos_short_name = COMMON.StrategyJsonKey.TS.pos_buy
        tradeable_price_purchase_name = COMMON.StrategyJsonKey.TS.price_buy
        tradeable_price_sales_name = COMMON.StrategyJsonKey.TS.price_sell
        for idx, ts in enumerate(range(ts_from, ts_until, COMMON.QUARTER)):
            scale[idx][0].append((from_timeseries(scale_pos_short_name, ts, 0.) or 0.,
                                  from_timeseries(tradeable_price_purchase_name, ts, None)))
            scale[idx][1].append((from_timeseries(scale_pos_long_name, ts, 0.) or 0.,
                                  from_timeseries(tradeable_price_sales_name, ts, None)))

        # then extend the scales by the information from the user timeseries for scales, if they exist
        for scale_idx in range(1, MAX_NUMBER_SCALES + 2):
            scale_pos_long_name = "strategy_position_long_scale_{}".format(scale_idx)
            scale_pos_short_name = "strategy_position_short_scale_{}".format(scale_idx)
            tradeable_price_purchase_name = "strategy_tradeable_price_purchase_scale_{}".format(scale_idx)
            tradeable_price_sales_name = "strategy_tradeable_price_sales_scale_{}".format(scale_idx)

            for idx, ts in enumerate(range(ts_from, ts_until, COMMON.QUARTER)):
                scale[idx][0].append((from_timeseries(scale_pos_short_name, ts, 0.) or 0.,
                                      from_timeseries(tradeable_price_purchase_name, ts, None)))
                scale[idx][1].append((from_timeseries(scale_pos_long_name, ts, 0.) or 0.,
                                      from_timeseries(tradeable_price_sales_name, ts, None)))

        for scale_interval in scale:
            # side:0 - buy, side: 1 sell
            scale_interval[0] = [[qty, prc] for qty, prc in scale_interval[0] if prc is not None]
            # the buy side has to be sorted from higher to lower prices
            scale_interval[0].sort(key=lambda scale: -scale[1])
            scale_interval[1] = [[qty, prc] for qty, prc in scale_interval[1] if prc is not None]
            # the sell side has to be sorted from lower to higher prices
            scale_interval[1].sort(key=lambda scale: scale[1])

        return scale

    def build_scale_remaining_matrix(self, all_range_products, raw_scale, ts_from, ts_until):
        """Split the raw scales into traded quantities and remaining scales.

        The scales have information about what quantities can be traded on which price levels.
        If quantities have been traded already, the raw scales have to be reduced to get the remaining scales.
        The traded scales can be used to set up the buy back quantities.

        [interval_index][<buy/sell>][scale_number, 0...][quantity=0,price=1]

        ts_until-ts_from should always be 3600 (complete hour)

        :param all_range_products: list of all the products delivering in ts_from-ts_until
        :type all_range_products: list
        :param raw_scale: distribution of price and quantity levels for each side for each quarter hour
        :type raw_scale: list
        :param ts_from: start timestamp of hour
        :type ts_from: int
        :param ts_until: end timestamp of hour
        :type ts_until: int
        :return:
            - remaining_scale: [interval_index][<buy/sell>][scale_number, 0...][quantity=0,price=1]
            - traded_quantities: (net quantities) [interval_index][<buy/sell>]
        :rtype: tuple
        """
        remaining_scale = copy.deepcopy(raw_scale)

        # traded quantities in each quarter hour for the duration
        traded_quantities = [[0., 0.] for unused_interval in range(ts_from, ts_until, COMMON.QUARTER)]

        # go through all products and add up the quantities to get net traded amounts for each side for each 15min
        for product in all_range_products:
            # ... for every quarter
            for idx, ts in enumerate(range(ts_from, ts_until, COMMON.QUARTER)):
                # if the product is relevant for the interval
                if product.delivery_start <= ts < product.delivery_end:
                    # ... iterate all trades of the product
                    for trade in product.trades.get(portfolio_key=self.strategy_id):
                        slot = trade.tags.get("strategy_slot", "")
                        tradeback = slot.endswith("_tradeback")

                        def work_on_scale(index):
                            if tradeback:
                                traded_quantities[idx][abs(index - 1)] -= trade.quantity
                            else:
                                traded_quantities[idx][index] += trade.quantity

                        if trade.sell_delivery_area:  # area is string or empty string
                            work_on_scale(1)
                        if trade.buy_delivery_area:
                            work_on_scale(0)

        for idx, ts in enumerate(range(ts_from, ts_until, COMMON.QUARTER)):
            # Remove traded quantity from the scale, starting with the lowest scale
            for index in [0, 1]:
                distribute_trade_quantity = traded_quantities[idx][index]
                for scale_item in remaining_scale[idx][index]:
                    distribute_on_item = min(scale_item[0], distribute_trade_quantity)
                    distribute_trade_quantity -= distribute_on_item
                    scale_item[0] -= distribute_on_item

        return remaining_scale, traded_quantities

    def compress_scale_remaining_matrix(self, raw_scale):
        """Compress by taking the minimum of quantities and simple average of frontmost prices in each passed segment

        :param raw_scale: distribution of price and quantity levels for each side for each quarter hour
        :type raw_scale: list
        :return: compressed scales, depending on number of 15min entries to 30min, 1h, or more
        :rtype: list
        """
        scale = copy.deepcopy(raw_scale)

        def compress_side(index):
            scale_len = float(len(scale))
            result = []
            min_qty = 0.
            for unused_iteration in range(200):
                for scale_part in scale:
                    if not scale_part[index]:
                        return [r for r in result if r[0] > 0.]
                    scale_part[index][0][0] -= min_qty
                    if scale_part[index][0][0] <= 0.:
                        # pop that item
                        del scale_part[index][0]
                        if not scale_part[index]:
                            return [r for r in result if r[0] > 0.]
                min_qty = min(scale_part[index][0][0] for scale_part in scale)
                avg_price = sum(scale_part[index][0][1] for scale_part in scale) / scale_len
                result.append([min_qty, avg_price])
            raise Exception("Should never be here")

        return [[compress_side(0), compress_side(1)]]

    def get_single_traded_quantity(self, all_range_products, ts):
        """Get combined traded volumes for each quarter hour in the hour starting with ts for the given products

        The volumes are added up to:
            [
                buy  - tradeback_sell,
                sell - tradeback_buy
            ]

        :param all_range_products: all products in the hour range
        :param ts: hour starting with ts
        :type all_range_products: list
        :type ts: int
        :rtype: list
        """
        traded_quantity = [0., 0.]
        # all_range_products should be a list of all the products delivering in the called hour
        for product in all_range_products:
            # if the product is relevant for the interval
            if product.delivery_start <= ts < product.delivery_end:
                # ... iterate all trades of the product
                for trade in product.trades.get(portfolio_key=self.strategy_id):
                    slot = trade.tags.get("strategy_slot", "")
                    tradeback = slot.endswith("_tradeback")

                    def work_on_scale(index):
                        if tradeback:
                            traded_quantity[abs(index - 1)] -= trade.quantity
                        else:
                            traded_quantity[index] += trade.quantity

                    if trade.sell_delivery_area:  # area is string or empty string
                        work_on_scale(1)
                    if trade.buy_delivery_area:
                        work_on_scale(0)
        return traded_quantity

    def determine_dynamic_placement_position(self,
                                             exchange,  # type: APIEXCH.ExchangeBase
                                             product,  # type: APITR.Product
                                             behaviour,  # type: str
                                             area,  # type: str
                                             seconds_left,  # type: float
                                             max_otr  # type: int
                                             ):  # type: (...) -> tuple
        """Place buy and sell price based on placement mode and orderbook.

        The more aggressive the mode, the more a ask price goes into the bid side of the orderbook.

        :param exchange: current exchange object (Epex, Nordpool, Trayport, ...)
        :type exchange: APIEXCH.ExchangeBase
        :param product: current product
        :type product: APITR.Product
        :param behaviour: Strategy Behaviour, can be aggressive (unsafe), balanced or passive (safe)
        :type behaviour: str
        :param area: delivery area id
        :type area: str
        :param seconds_left: seconds left until trading stop on this product
        :type seconds_left: float
        :param max_otr: maximum otr limit
        :type max_otr: int
        :return: mode, sell_price, sell_price_upper, sell_price_lower, buy_price, buy_price_upper, buy_price_lower
        :rtype: tuple
        """

        otr = exchange.products.get_total_order_to_trade_ratio(product.delivery_start, product.delivery_end, area)
        mode = self.get_placement_mode(behaviour, max_otr, otr, seconds_left)

        sell_price, sell_price_upper, sell_price_lower = None, None, None
        buy_price, buy_price_upper, buy_price_lower = None, None, None
        try:
            indicators = product.orders.indicators(area)[0].mw_prices
        except IndexError:
            return mode, sell_price, sell_price_upper, sell_price_lower, buy_price, buy_price_upper, buy_price_lower

        return self.get_sell_buy_price_levels(mode, indicators)

    @staticmethod
    def get_placement_mode(behaviour, max_otr, otr, seconds_left):
        """Get placement mode depending on behaviour, otr limits and seconds.

        The mode will define the price finding mechanism

        :param behaviour: Strategy Behaviour, can be aggressive (unsafe), balanced or passive (safe)
        :type behaviour: str
        :param max_otr: maximum otr limit
        :type max_otr: int
        :param otr: order to trade ratio
        :type otr: int
        :param seconds_left: seconds left until trading stop on this product
        :type seconds_left: float
        :return: Placement mode
        :rtype: str
        """
        brute_force_otr = max_otr * BRUTE_FORCE_LEVEL_OF_MAX_OTR
        force_otr = max_otr * FORCE_LEVEL_OF_MAX_OTR

        if behaviour == StrategyBehavior.safe:
            if seconds_left > COMMON.MINUTE * 5:
                mode = PlacementMode.aggressive
            else:
                mode = PlacementMode.bruteforce
        elif behaviour == StrategyBehavior.balanced:
            if seconds_left > COMMON.MINUTE * 5:
                mode = PlacementMode.progressive
            elif seconds_left > COMMON.MINUTE * 2:
                mode = PlacementMode.aggressive
            else:
                mode = PlacementMode.bruteforce
        else:
            if seconds_left > COMMON.MINUTE * 10:
                mode = PlacementMode.lazy
            elif seconds_left > COMMON.MINUTE * 5:
                mode = PlacementMode.active
            else:
                mode = PlacementMode.progressive

        if otr >= brute_force_otr:
            mode = PlacementMode.bruteforce
        elif otr >= force_otr and mode != PlacementMode.bruteforce:
            mode = PlacementMode.aggressive
        return mode

    @staticmethod
    def get_sell_buy_price_levels(mode, indicators):
        """Calculate buy and sell prices based on placement mode and orderbook distributions.

        The more aggressive the mode, the more a ask price goes into the bid side of the orderbook.

        :param mode: PlacementMode
        :type mode: str
        :param indicators: order book information
        :type indicators: list
        :return: mode, sell_price, sell_price_upper, sell_price_lower, buy_price, buy_price_upper, buy_price_lower
        :rtype: tuple
        """

        def notnone(*elements):
            return not any(e is None for e in elements)

        sell_price, sell_price_upper, sell_price_lower = None, None, None
        buy_price, buy_price_upper, buy_price_lower = None, None, None

        if mode == PlacementMode.lazy:
            if notnone(indicators[0][1], indicators[0][2], indicators[1][1], indicators[1][2]):
                mid = (indicators[0][2] + indicators[1][2]) * 0.5
                sell_price = (indicators[1][1] + indicators[1][2]) / 2  # between 5MW and 10 MW
                sell_price_lower = mid  # mid
                sell_price_upper = indicators[1][2]  # 10 MW
                buy_price = (indicators[0][1] + indicators[0][2]) / 2  # between 5MW and 10 MW
                buy_price_lower = indicators[0][2]  # 10 MW
                buy_price_upper = mid  # mid
        elif mode == PlacementMode.active:
            if notnone(indicators[0][1], indicators[0][1], indicators[1][1], indicators[1][1]):
                mid = (indicators[0][1] + indicators[1][1]) * 0.5
                sell_price = indicators[1][1]  # 5 MW
                sell_price_lower = mid  # 5 MW
                sell_price_upper = indicators[1][1]  # 5 MW
                buy_price = indicators[0][1]  # 5 MW
                buy_price_lower = indicators[0][1]  # 5 MW
                buy_price_upper = mid  # 5 MW
        elif mode == PlacementMode.progressive:
            if notnone(indicators[0][1], indicators[0][1], indicators[1][1], indicators[1][1]):
                sell_price = indicators[1][1] * 0.7 + indicators[0][1] * 0.3  # in spread, more on the sell side
                sell_price_lower = indicators[0][1] * 0.7 + indicators[1][1] * 0.3  # 5 MW
                sell_price_upper = indicators[1][1]  # 5 MW
                buy_price = indicators[0][1] * 0.7 + indicators[1][1] * 0.3  # in spread, more on the buy side
                buy_price_lower = indicators[0][1]  # 5 MW
                buy_price_upper = indicators[1][1] * 0.7 + indicators[0][1] * 0.3  # 5 MW
        elif mode == PlacementMode.aggressive:
            if notnone(indicators[0][1], indicators[0][1], indicators[1][1], indicators[1][1]):
                # in spread, more on the buy side minus 10 cent
                sell_price = indicators[1][1] * 0.3 + indicators[0][1] * 0.7 - 0.1
                sell_price_lower = indicators[0][1]  # 5 MW
                sell_price_upper = indicators[1][1]  # 5 MW
                # in spread, more on the sell side plus 10 cent
                buy_price = indicators[0][1] * 0.3 + indicators[1][1] * 0.7 + 0.1
                buy_price_lower = indicators[0][1]  # 5 MW
                buy_price_upper = indicators[1][1]  # 5 MW
        elif mode == PlacementMode.bruteforce:  # just trade it
            if notnone(indicators[0][1], indicators[0][2], indicators[1][1], indicators[1][2]):
                # hit order
                sell_price = indicators[0][2]
                sell_price_lower = indicators[0][2]
                sell_price_upper = indicators[0][2]
                # hit order
                buy_price = indicators[1][2]
                buy_price_lower = indicators[1][2]
                buy_price_upper = indicators[1][2]
        return mode, sell_price, sell_price_lower, sell_price_upper, buy_price, buy_price_lower, buy_price_upper

    def truncate_quantity_by_behaviour(self, maximum_order_book, behaviour, quantity):
        """Restrict trade quantity by strategy behaviour and maximum order book parameter passed by user

        :param maximum_order_book: highest amount allowed in order book
        :param maximum_order_book: float
        :param behaviour: Strategy Behaviour, can be aggressive (unsafe), balanced or passive (safe)
        :type behaviour: str
        :param quantity: raw target quantity
        :type quantity: float
        :return: truncated quantity
        :rtype: float
        """

        if quantity <= maximum_order_book:
            return quantity
        if behaviour == StrategyBehavior.safe:
            return max(quantity * 0.2, maximum_order_book)
        elif behaviour == StrategyBehavior.balanced:
            return max(quantity * 0.1, maximum_order_book)
        else:
            return max(quantity * 0.05, maximum_order_book)

    def build_placement_for_products(self, all_available_products, remaining_matrix, maximum_order_book,
                                     behaviour, area, ts_from, ts_until, timestamp, trading_end_before_market_closure,
                                     max_otr):
        """Build packets for placement of the quantities in remaining_matrix using the available products.

        The quantities are filled from the longer term (hour) products to the shorter term (quarter) products
        filling the longer term products only with consistent packets over every quarter.
        The maximum order size depends on the base quantity of the scale and the mode set for the strategy
        (StrategyBehavior) and on the maximum_order_book setting.
        The quantity itself is dependent on the position of the order in the order book, depending on the
        product's indicators
        """
        placement = dict()
        remaining_matrix = copy.deepcopy(remaining_matrix)
        # all_range_products should be a list of all the products delivering in ts_from-ts_until and suitable for
        # trading of this product.
        # ts_until-ts_from should always be 3600 (complete hour)
        # now sort the all_available_products list by the delivery interval
        all_available_products.sort(key=lambda prod: prod.delivery_end - prod.delivery_start, reverse=True)

        for product in all_available_products:
            # is this product currently being traded?
            if product.state(area) != DeliveryAreaState.active:
                continue
            trading_end = product.delivery_start - trading_end_before_market_closure
            seconds_left = trading_end - timestamp
            if seconds_left < 0:
                # still active, but trading is over now
                placement[product.product_id] = (0., 0., 0., 0., 0., 0., 0., 0., 0., 0., "X", 0.)
                continue
            # determine dynamic placement position for buy and sell
            (
                placement_mode, sell_price, sell_price_lower, sell_price_upper, buy_price, buy_price_lower,
                buy_price_upper
            ) = self.determine_dynamic_placement_position(
                self.exchange, product, behaviour, area, seconds_left, max_otr
            )
            # lookup the price positions in the matrix
            # ... for every quarter of the product delivery
            scale_interval_index = 0
            if product.delivery_end - product.delivery_start == COMMON.HOUR:
                use_matrix = self.compress_scale_remaining_matrix(remaining_matrix)
            elif product.delivery_end - product.delivery_start == COMMON.QUARTER * 2:
                if product.delivery_start - ts_from >= COMMON.QUARTER * 2:
                    use_matrix = self.compress_scale_remaining_matrix(remaining_matrix[2:])
                else:
                    use_matrix = self.compress_scale_remaining_matrix(remaining_matrix[:2])
            else:
                use_matrix = remaining_matrix
                scale_interval_index = (product.delivery_start - ts_from) / COMMON.QUARTER

            # look up the quantity for the product's placement prices in the remaining matrix.
            # if there is a quantity for that price, use it. If not (price too high or low),
            # place the fixed order at the lowest scale, if there's still quantity
            sell_amounts_interval = []
            buy_amounts_interval = []

            # accumulate buy
            buy_scale_start = -100000.
            for idx, scale in enumerate(use_matrix[scale_interval_index][0]):
                # with each iteration, the price at scale[1] will be falling, since we go deeper.
                # this means the first iteration sets the buy_scale_start, the upper limit at which the bid can be set.
                buy_scale_start = max(buy_scale_start, scale[1])

                if (buy_price is None or scale[1] < buy_price) and idx == 0:
                    # only for the first scale, accept a price inside the price tolerance
                    buy_amounts_interval.append((scale[0], scale[1]))
                    break

                # if scale exceeds the buy_price set by the placement mechanism, then use the buy_price
                if scale[1] >= buy_price:
                    buy_amounts_interval.append((scale[0], buy_price))
                else:
                    break

            # accumulate sell
            sell_scale_start = 100000.
            for idx, scale in enumerate(use_matrix[scale_interval_index][1]):
                sell_scale_start = min(sell_scale_start, scale[1])
                if (sell_price is None or scale[1] > sell_price) and idx == 0:
                    # only for the first scale, accept a price inside the price tolerance
                    sell_amounts_interval.append((scale[0], scale[1]))
                    break
                if scale[1] <= sell_price:
                    sell_amounts_interval.append((scale[0], sell_price))
                else:
                    break

            # now sum up the quantities and take the min price for buy and the max price for sell
            if buy_amounts_interval:
                raw_buy_quantity = sum(elem[0] for elem in buy_amounts_interval)
                buy_amount = self.truncate_quantity_by_behaviour(maximum_order_book, behaviour, raw_buy_quantity)
                buy_price = min(elem[1] for elem in buy_amounts_interval)
            else:
                raw_buy_quantity = 0.
                buy_amount = self.truncate_quantity_by_behaviour(maximum_order_book, behaviour, raw_buy_quantity)
                buy_price = 0
            if sell_amounts_interval:
                raw_sell_quantity = sum(elem[0] for elem in sell_amounts_interval)
                sell_amount = self.truncate_quantity_by_behaviour(maximum_order_book, behaviour, raw_sell_quantity)
                sell_price = max(elem[1] for elem in sell_amounts_interval)
            else:
                raw_sell_quantity = 0.
                sell_amount = self.truncate_quantity_by_behaviour(maximum_order_book, behaviour, raw_sell_quantity)
                sell_price = 0

            # now remove the quantity from the overall scale, so the other products don't get it
            for ts in range(product.delivery_start, product.delivery_end, COMMON.QUARTER):
                scale_interval_index = (ts - ts_from) / COMMON.QUARTER
                # buy
                amount_to_deduct = buy_amount
                for idx, scale in enumerate(remaining_matrix[scale_interval_index][0]):
                    deduct = min(scale[0], amount_to_deduct)
                    scale[0] -= deduct
                    amount_to_deduct -= deduct
                # sell
                amount_to_deduct = sell_amount
                for idx, scale in enumerate(remaining_matrix[scale_interval_index][1]):
                    deduct = min(scale[0], amount_to_deduct)
                    scale[0] -= deduct
                    amount_to_deduct -= deduct

            # memorize the data for this product
            buy_price_lower = min(min(buy_price_lower, buy_price), buy_scale_start)
            buy_price_upper = min(max(buy_price_upper, buy_price), buy_scale_start)
            sell_price_lower = max(min(sell_price_lower, sell_price), sell_scale_start)
            sell_price_upper = max(max(sell_price_upper, sell_price), sell_scale_start)
            placement[product.product_id] = (raw_buy_quantity, buy_amount, buy_price, buy_price_lower, buy_price_upper,
                                             raw_sell_quantity, sell_amount, sell_price, sell_price_lower,
                                             sell_price_upper, placement_mode, seconds_left)
        return placement

    def build_tradeback_placement_for_products(self, all_available_products, traded_quantities, maximum_order_book,
                                               behaviour, sell_limit_prices, buy_limit_prices, area,
                                               ts_from, ts_until, timestamp, trading_end_before_market_closure):
        """build packets for placement of the quantities in traded_quantities using the available products.

        The quantities are filled from the longer term (hour) products to the shorter term (quarter) products
        filling the longer term products only with consistent packets over every quarter.

        Quantity:
        when having a product over a longer term, than the amount is the minimum quantity of all quarter hours
        within the products duration.
        Additionally, the quantity is truncated by behaviour.

        Quantity Aggregation:
        - minimum value of quarter hours is taken, if product has longer duration

        Price:
        The tradeback price is always set to the limit price.
        Currently the passed limit prices are taken from the time series:
        - strategy_limit_maximum_purchase_price
        - strategy_limit_maximum_sales_price

        Price Aggregation:
        - bid: minimum value of quarter hours is taken, if product has longer duration
        - ask: maximum value of quarter hours is taken, if product has longer duration
        """
        placement = dict()
        traded_quantities = copy.deepcopy(traded_quantities)
        # all_range_products should be a list of all the products delivering in ts_from-ts_until and suitable for
        # trading of this product.
        # ts_until-ts_from should always be 3600 (complete hour)
        # now sort the all_available_products list by the delivery interval
        all_available_products.sort(key=lambda prod: prod.delivery_end - prod.delivery_start, reverse=True)

        for product in all_available_products:
            # is this product currently being traded?
            if product.state(area) != DeliveryAreaState.active:
                continue
            trading_end = product.delivery_start - trading_end_before_market_closure
            seconds_left = trading_end - timestamp
            if seconds_left < 0:
                # still active, but trading is over now
                placement[product.product_id] = (0., 0., 0., 0.)
                continue
            sell_amounts_product = []
            buy_amounts_product = []
            # ... for every quarter of the product delivery
            for ts in range(product.delivery_start, product.delivery_end, COMMON.QUARTER):
                # collect traded quantities
                scale_interval_index = (ts - ts_from) / COMMON.QUARTER
                # accumulate buy from the current sold quantities
                buy_amounts_product.append((traded_quantities[scale_interval_index][1],
                                            buy_limit_prices[scale_interval_index]))
                # accumulate sell from the current bought quantities
                sell_amounts_product.append((traded_quantities[scale_interval_index][0],
                                             sell_limit_prices[scale_interval_index]))

            # now evaluate the quantities over all intervals
            buy_amount = buy_price = 0.
            sell_amount = sell_price = 0.
            if buy_amounts_product:
                buy_amount = min(elem[0] for elem in buy_amounts_product)
                buy_amount = self.truncate_quantity_by_behaviour(maximum_order_book, behaviour, buy_amount)
                buy_price = min(elem[1] for elem in buy_amounts_product)
            if sell_amounts_product:
                sell_amount = min(elem[0] for elem in sell_amounts_product)
                sell_amount = self.truncate_quantity_by_behaviour(maximum_order_book, behaviour, sell_amount)
                sell_price = max(elem[1] for elem in sell_amounts_product)

            # now remove the quantity from the traded_quantities, so the other products don't get it
            for ts in range(product.delivery_start, product.delivery_end, COMMON.QUARTER):
                scale_interval_index = (ts - ts_from) / COMMON.QUARTER
                # buy
                traded_quantities[scale_interval_index][1] -= buy_amount
                # sell
                traded_quantities[scale_interval_index][0] -= sell_amount

            # memorize the data for this product
            placement[product.product_id] = (
                max(0., buy_amount - sell_amount), buy_price,
                max(0., sell_amount - buy_amount), sell_price
            )
        return placement


class CustomStrategy(strategy.Strategy, MatrixBuilder):
    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        self.log = log
        self.position = strategy.Position()
        self.behavior = StrategyBehavior.balanced
        self.delivery_area_id = None

        self.strategy_position_tradable_position_long = None  # timeseries
        self.strategy_position_tradable_position_short = None  # timeseries
        self.strategy_price_purchase_immediate_vesting = None  # timeseries
        self.strategy_price_sales_immediate_vesting = None  # timeseries
        self.strategy_limit_maximum_sales_volume = None  # timeseries
        self.strategy_limit_maximum_purchase_volume = None  # timeseries
        self.strategy_limit_maximum_purchase_price = None  # timeseries
        self.strategy_limit_minimum_sales_price = None  # timeseries
        self.strategy_price_minimum_spread_buyback = None  # timeseties
        self.strategy_price_purchase = None  # timeseties
        self.strategy_price_sales = None  # timeseties

    def trade_action_locks_strategy(self, product, behaviour, timestamp, seconds_left):
        """Get latency and trades for the specified product within he time range including the latency

        latency means lookback time to include previous trades

        :param product: current product to check the own trades for
        :type product: APITR.Product
        :param behaviour: Strategy Behaviour, can be aggressive (unsafe), balanced or passive (safe)
        :type behaviour: str
        :param timestamp: current timestamp
        :type timestamp: int
        :param seconds_left: seconds left to trade the current product
        :type seconds_left: float
        :return: return true, if any trades have been done for the product within the latency.
        :rtype: bool
        """
        if behaviour == StrategyBehavior.safe:
            if seconds_left > COMMON.MINUTE * 5:
                latency = 2
            else:
                latency = 0
        elif behaviour == StrategyBehavior.balanced:
            if seconds_left > COMMON.MINUTE * 5:
                latency = 10
            elif seconds_left > COMMON.MINUTE * 2:
                latency = 2
            else:
                latency = 0
        else:
            if seconds_left > COMMON.MINUTE * 10:
                latency = 90
            elif seconds_left > COMMON.MINUTE * 5:
                latency = 20
            else:
                latency = 10
        if self.exchange.products.get_total_order_to_trade_ratio(product.delivery_start, product.delivery_end,
                                                                 self.delivery_area_id) >\
                OTR_LIMIT_TO_PLACE_WITH_10SEC_LATENCY:
            latency = 10
        return bool(product.trades.get(buy_delivery_area=None, sell_delivery_area=None,
                                       delivery_area=self.delivery_areas[0],
                                       portfolio_key=self.strategy_id,
                                       trade_filter=API.TradeFilter.own,
                                       timerange=(timestamp - latency, timestamp + 10)))

    def act_for_interval(self, ts_from, ts_until, timestamp):
        assert ts_until - ts_from == COMMON.HOUR
        # calculate the volume and price matrix from the scale data
        scale = self.build_scale_steering_matrix(ts_from, ts_until)
        if self.exchange.internal_id == COMMON.Exchange.epex:
            all_range_products = \
                self.autotrader.epex.products.get_by_timerange(ts_from - COMMON.HOUR, ts_until + COMMON.HOUR)
        elif self.exchange.internal_id == COMMON.Exchange.nordpool:
            all_range_products = \
                self.autotrader.nordpool.products.get_by_timerange(ts_from - COMMON.HOUR, ts_until + COMMON.HOUR)
        else:
            raise NotImplementedError("This strategy does not support Exchange: {}".format(self.exchange.internal_id))

        all_range_products = [p for p in all_range_products
                              if p.delivery_end - p.delivery_start <= COMMON.HOUR
                              and p.product_type in ACCEPTABLE_PRODUCT_TYPES]
        before_products = [p for p in all_range_products if p.delivery_end <= ts_from]
        after_products = [p for p in all_range_products if p.delivery_start >= ts_until]
        all_range_products = [p for p in all_range_products if ts_from <= p.delivery_start < ts_until]

        # now take the traded amounts into account, and reduce the quantities in the scale by the traded amounts
        # the traded amounts will then be considered for the tradeback positions
        remaining_quantities_scale, traded_quantities = self.build_scale_remaining_matrix(all_range_products,
                                                                                          scale, ts_from,
                                                                                          ts_until)
        self.debug_log("Status summary for {cet_timestamp}: remaining: {remaining}, traded: {traded}"
                       .format(cet_timestamp=ALCU.utc_ts2cet_str(ts_from, False, True),
                               remaining=remaining_quantities_scale, traded=traded_quantities))
        # 0.1 has to be the default, because it's not only used with min, but also with max above
        maximum_order_book = abs(self.strategy_settings["maximum_order_book"] or MAX_ORDER_BOOK_QUANTITY_RATE)
        trading_end_before_market_closure = \
            (self.strategy_settings["trading_end_before_market_closure"] or 0) * COMMON.MINUTE

        # filter by product filter timeseries if available
        if hasattr(self, "strategy_ramp"):
            ramps = [
                self.strategy_ramp.get((ts, ts + COMMON.QUARTER), RAMP_DEFAULT) or RAMP_DEFAULT
                for ts in range(ts_from - COMMON.QUARTER * 2, ts_until, COMMON.QUARTER)
            ]
            assert len(ramps) == 6
        else:
            ramps = [RAMP_DEFAULT] * 6
        if hasattr(self, "strategy_otr"):
            max_otr = self.strategy_otr.get((ts_from, ts_until), MAX_OTR_DEFAULT_VALUE) or MAX_OTR_DEFAULT_VALUE
            self.debug_log("setting otr limit to {max_otr}".format(max_otr=max_otr))
        else:
            max_otr = MAX_OTR_DEFAULT_VALUE

        # Set product filter, for hour, half and quarter products
        if hasattr(self, "strategy_products_filter"):
            product_filter = (
                self.strategy_products_filter.get((ts_from, ts_until), PRODUCTS_FILTER_DEFAULT)
                or PRODUCTS_FILTER_DEFAULT
            )
        else:
            product_filter = PRODUCTS_FILTER_DEFAULT

        available_products_filter = []
        if product_filter in (ALLOW_HOUR_QUARTER, ALLOW_HOUR):
            available_products_filter.extend(HOUR_FILTERS)
        if product_filter in (ALLOW_HOUR_QUARTER, ALLOW_QUARTER):
            available_products_filter.extend(QUARTER_HOUR_FILTERS)

        # apply product filters, only get allowed durations and active products
        all_available_products = [
            product
            for product in all_range_products
            if (
                product.product_type in available_products_filter
                and product.state(self.delivery_areas[0]) == DeliveryAreaState.active
            )
        ]

        product_placement_dict = self.build_placement_for_products(all_available_products,
                                                                   remaining_quantities_scale,
                                                                   maximum_order_book, self.behavior,
                                                                   self.delivery_area_id, ts_from, ts_until,
                                                                   timestamp, trading_end_before_market_closure,
                                                                   max_otr)
        # now place the orders for buyback, don't forget to sort the items, they are unsorted!!
        sell_limit_prices = [value for (i_ts_from, i_ts_until), value in
                             sorted(self.strategy_limit_minimum_sales_price.items()) if
                             ts_from <= i_ts_from < ts_until and i_ts_until - i_ts_from == COMMON.QUARTER]
        buy_limit_prices = [value for (i_ts_from, i_ts_until), value in
                            sorted(self.strategy_limit_maximum_purchase_price.items()) if
                            ts_from <= i_ts_from < ts_until and i_ts_until - i_ts_from == COMMON.QUARTER]
        if not sell_limit_prices or not buy_limit_prices:
            return

        self.debug_log("limits-traded-quantities {cet_str_from} - {cet_str_until} [{ts_from} - {ts_until}]: "
                       "sell-limit: {sell_limits}, "
                       "buy-limit: {buy_limits},"
                       "traded-quantities: {traded}"
                       .format(cet_str_from=ALCU.utc_ts2cet_str(ts_from, False, True),
                               cet_str_until=ALCU.utc_ts2cet_str(ts_until, False, True),
                               ts_from=ts_from,
                               ts_until=ts_until,
                               sell_limits=sell_limit_prices, buy_limits=buy_limit_prices,
                               traded=traded_quantities)
                       )

        assert len(sell_limit_prices) == len(buy_limit_prices) == len(traded_quantities)
        product_placement_dict_tradeback = self.build_tradeback_placement_for_products(
            all_available_products, traded_quantities, maximum_order_book, self.behavior, sell_limit_prices,
            buy_limit_prices, self.delivery_area_id, ts_from, ts_until, timestamp, trading_end_before_market_closure
        )
        assert len(product_placement_dict) == len(product_placement_dict_tradeback)

        quantity_before = self.get_single_traded_quantity(before_products, ts_from - COMMON.QUARTER)
        quantity_after = self.get_single_traded_quantity(after_products, ts_until)

        target_positions = [quantity_before[0] - quantity_before[1]] + \
                           [q[0] - q[1] for q in traded_quantities] + \
                           [quantity_after[0] - quantity_after[1]]

        def evaluate_ramp_minmaxes(pos_before, pos, pos_after, ramp_before_before, ramp_before, ramp):
            min_before = pos_before + 0.1 * ramp_before_before - ramp_before
            max_before = pos_before - 0.1 * ramp_before_before + ramp_before
            min_after = pos_after - 0.9 * ramp
            max_after = pos_after + 0.9 * ramp
            max_joined = min(max_before, max_after)
            min_joined = max(min_before, min_after)
            return min(max(max_joined - pos, 0), 0.1 * ramp_before), min(max(pos - min_joined, 0.), 0.1 * ramp_before)

        ramp_minmaxes = dict((x * COMMON.QUARTER + ts_from,
                              evaluate_ramp_minmaxes(target_positions[x], target_positions[x + 1],
                                                     target_positions[x + 2],
                                                     ramps[x], ramps[x + 1], ramps[x + 2])) for x in range(4))

        # long range products come first
        all_range_products.sort(key=lambda prod: prod.delivery_end - prod.delivery_start, reverse=True)
        for product in all_range_products:

            product_interval = (product.delivery_start, product.delivery_end)
            limit_maximum_purchase_price, limit_minimum_sales_price = self.get_strategy_timerow_settings([
                (COMMON.StrategyJsonKey.TS.limit_buy_price, None),
                (COMMON.StrategyJsonKey.TS.limit_sell_price, None)], product_interval)

            # for hours, take the minimum of first and last buy size
            product_ramp_max_buy_size = min(ramp_minmaxes[product.delivery_start][0],
                                            ramp_minmaxes[product.delivery_end - COMMON.QUARTER][0])

            # for hours, take the minimum of first and last sell size
            product_ramp_max_sell_size = min(ramp_minmaxes[product.delivery_start][1],
                                             ramp_minmaxes[product.delivery_end - COMMON.QUARTER][1])

            def mk_stat(mode, raw_qty, placed_qty):
                """Create statistics which will be added to the slot entry
                   to give additional info on the placement behaviour and positions"""
                return "{}/r{:0.1f}/p{:0.1f}".format(mode, raw_qty, placed_qty)

            def rd(x):
                return round(x, 2) if x is not None else x

            try:
                (
                    raw_buy_quantity, buy_amount, buy_price, buy_price_lower, buy_price_upper,
                    raw_sell_quantity, sell_amount, sell_price, sell_price_lower, sell_price_upper,
                    placement_mode, seconds_left
                ) = product_placement_dict[product.product_id]
            except KeyError:
                # cancel all orders which are out on the market
                slots = [PositionSlot(BUY_SLOTNAME, Direction.buy, 0., 0),
                         PositionSlot(SELL_SLOTNAME, Direction.sell, 0., 0),
                         PositionSlot(BUY_TRADEBACK_SLOTNAME, Direction.buy, 0., 0),
                         PositionSlot(SELL_TRADEBACK_SLOTNAME, Direction.sell, 0., 0)]
                self.place_slots({}, product, timestamp, self.delivery_area_id, slots, [],
                                 limit_minimum_sales_price, limit_maximum_purchase_price,
                                 InternalExecutionMode.exchange_base_price)
                continue

            # reduce amounts by ramp limits
            buy_amount = min(buy_amount, product_ramp_max_buy_size)
            sell_amount = min(sell_amount, product_ramp_max_sell_size)

            # take a break for that product because of a trade?
            if self.trade_action_locks_strategy(product, self.behavior, timestamp, seconds_left):
                continue  # do nothing

            def place_slot_with_stat(slot, stat):
                self.debug_log(
                    "{timestamp} {product_name}, {slot_type} {direction} {quantity}@{price}"
                    .format(timestamp=timestamp, product_name=product.name, slot_type=slot.slot_type,
                            direction=slot.direction, quantity=slot.quantity, price=slot.price)
                )

                if product.state(self.delivery_areas[0]) == DeliveryAreaState.active:
                    self.place_slots({}, product, timestamp, self.delivery_area_id, [slot], [stat],
                                     limit_minimum_sales_price, limit_maximum_purchase_price,
                                     InternalExecutionMode.exchange_base_price)

            place_slot_with_stat(PositionSlot(BUY_SLOTNAME, Direction.buy, rd(buy_amount), rd(buy_price),
                                              rd(buy_price_lower), rd(buy_price_upper)),
                                 mk_stat(placement_mode, raw_buy_quantity, buy_amount))

            place_slot_with_stat(PositionSlot(SELL_SLOTNAME, Direction.sell, rd(sell_amount), rd(sell_price),
                                              rd(sell_price_lower), rd(sell_price_upper)),
                                 mk_stat(placement_mode, raw_sell_quantity, sell_amount))

            buy_amount, buy_price, sell_amount, sell_price = \
                product_placement_dict_tradeback[product.product_id]

            buy_amount = min(buy_amount, product_ramp_max_buy_size)
            sell_amount = min(sell_amount, product_ramp_max_sell_size)

            place_slot_with_stat(PositionSlot(BUY_TRADEBACK_SLOTNAME, Direction.buy, rd(buy_amount), rd(buy_price)),
                                 mk_stat("", buy_amount, buy_amount))

            place_slot_with_stat(PositionSlot(SELL_TRADEBACK_SLOTNAME, Direction.sell, rd(sell_amount), rd(sell_price)),
                                 mk_stat("", sell_amount, sell_amount))

    def custom_act(self, log_data, timestamp, products=None):
        """Find intervals to act on, and place orders where necessary according to calculations

        :type log_data: list
        :type timestamp: float
        :type products: list[autotrader_core.exchange_trading.Product]
        """
        if not products:
            return

        # get hourly intervals to run on, since we always look at 1h the same time
        intervals = set()
        for product in products:
            if product.delivery_start > timestamp:
                intervals.add((product.delivery_start // COMMON.HOUR * COMMON.HOUR,
                               (product.delivery_start // COMMON.HOUR + 1) * COMMON.HOUR))

        for interval in intervals:
            self.act_for_interval(*interval, timestamp=timestamp)

    def on_strategy_update(self, strategy_json):
        super(CustomStrategy, self).on_strategy_update(strategy_json)
        assert len(self.delivery_areas) == 1
        self.delivery_area_id = self.delivery_areas[0]
        # steering timeseries for products to be used
        if "user_defined_timeseries" in strategy_json:
            udf = strategy_json["user_defined_timeseries"]
            if "strategy_products_filter" in udf:
                self.strategy_products_filter = strategy.mk_strategy_tr_dict(
                    udf["strategy_products_filter"], "min")
            if "strategy_ramp" in udf:
                self.strategy_ramp = strategy.mk_strategy_tr_dict(
                    udf["strategy_ramp"], "max")
            if "strategy_otr" in udf:
                self.strategy_otr = strategy.mk_strategy_tr_dict(
                    udf["strategy_otr"], "min")
            # TODO: @PFO AUT-1218 this should be MAX_NUMBER_SCALES+1, make these non-functional changes in next ticket.
            for scale in range(1, MAX_NUMBER_SCALES):
                scale_pos_long_name = "strategy_position_long_scale_{}".format(scale)
                scale_pos_short_name = "strategy_position_short_scale_{}".format(scale)
                tradeable_price_purchase_name = "strategy_tradeable_price_purchase_scale_{}".format(scale)
                tradeable_price_sales_name = "strategy_tradeable_price_sales_scale_{}".format(scale)
                if scale_pos_long_name in udf and scale_pos_short_name in udf and \
                        tradeable_price_purchase_name in udf and tradeable_price_sales_name in udf:
                    setattr(self, scale_pos_long_name,
                            strategy.mk_strategy_tr_dict(udf[scale_pos_long_name], "min"))
                    setattr(self, scale_pos_short_name,
                            strategy.mk_strategy_tr_dict(udf[scale_pos_short_name], "min"))
                    setattr(self, tradeable_price_purchase_name,
                            strategy.mk_strategy_tr_dict(udf[tradeable_price_purchase_name], "min"))
                    setattr(self, tradeable_price_sales_name,
                            strategy.mk_strategy_tr_dict(udf[tradeable_price_sales_name], "max"))
        self.strategy_position_tradable_position_long = strategy.mk_strategy_tr_dict(
            strategy_json[COMMON.StrategyJsonKey.TS.pos_sell], "min")
        self.strategy_position_tradable_position_short = strategy.mk_strategy_tr_dict(
            strategy_json[COMMON.StrategyJsonKey.TS.pos_buy], "min")
        self.strategy_price_purchase_immediate_vesting = strategy.mk_strategy_tr_dict(
            strategy_json[COMMON.StrategyJsonKey.TS.price_imm_buy], "min")
        self.strategy_price_sales_immediate_vesting = strategy.mk_strategy_tr_dict(
            strategy_json[COMMON.StrategyJsonKey.TS.price_imm_sell], "max")
        self.strategy_price_purchase = strategy.mk_strategy_tr_dict(strategy_json[COMMON.StrategyJsonKey.TS.price_buy], "min")
        self.strategy_price_sales = strategy.mk_strategy_tr_dict(strategy_json[COMMON.StrategyJsonKey.TS.price_sell], "max")
        self.strategy_price_minimum_spread_buyback = \
            strategy.mk_strategy_tr_dict(strategy_json[COMMON.StrategyJsonKey.TS.price_min_spread_buyback], "min_nonone")
        self.behavior = strategy_json["behavior"] or StrategyBehavior.balanced

        def mk_ts_exp(ts):
            return dict((ts_from, value) for (ts_from, ts_to), value in ts.items() if ts_to - ts_from == COMMON.QUARTER)

        self.api_export_timeseries(
            {
                "pos_long": (
                    "Position Long", "MW", "MW", COMMON.QUARTER,
                    mk_ts_exp(self.strategy_position_tradable_position_long)
                ),
                "pos_short": (
                    "Position Short", "MW", "MW", COMMON.QUARTER,
                    mk_ts_exp(self.strategy_position_tradable_position_short)
                )
            }
        )

    def custom_on_order_book_update(self, orders, timestamp):
        products = set(o.product for o in orders)
        self.act(timestamp, products)

    def custom_on_trade_update(self, trades, timestamp):
        products = set(o.product for o in trades)
        self.act(timestamp, products)

    def custom_on_public_trade_update(self, trades, timestamp):
        pass

    def custom_on_products_update(self, products, timestamp):
        # no action here, because of the XBID product switches
        # EPEX sends the product updates in separate documents, so
        # reacting on those documents directly causes premature order
        # placement for products that may already be closed at the exchange
        # but we can't see that yet.
        pass

    def custom_on_products_queue(self, products, timestamp):
        self.act(timestamp, products)

    def custom_on_timer(self, timestamp):
        pass
