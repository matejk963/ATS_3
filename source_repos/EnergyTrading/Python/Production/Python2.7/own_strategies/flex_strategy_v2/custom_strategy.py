#!/usr/bin/env python
# -*- coding: utf-8 -*-
import collections
import copy
import itertools
import logging
import operator
import types as T
import datetime

import autotrader_core.api as API
import autotrader_core.common as COMMON
import autotrader_core.exchanges as APIEXCH
import autotrader_core.exchange_trading as APITR
import autotrader_core.strategy as strategy
import autotrader_lib.cet_util as CETUTIL
import autotrader_lib.cet_util as ALCU
import autotrader_lib.functools_lru_cache

log = logging.getLogger("autotrader.flex_strategy_v2_2022_08_29")

# MODIFIABLE
MAX_NUMBER_SCALES = 25

OMT_L1_PERCENT_LIMIT = 95.
BRUTE_FORCE_PERCENT_OF_MAX_OMT = 0.9 * OMT_L1_PERCENT_LIMIT
FORCE_PERCENT_OF_MAX_OMT = 0.8 * OMT_L1_PERCENT_LIMIT
OMT_PERCENT_LIMIT_TO_PLACE_WITH_10SEC_LATENCY = 70.

DEFAULT_LIMIT_MAXIMUM_PURCHASE_PRICE = 0
DEFAULT_LIMIT_MINIMUM_SALES_PRICE = 100
DEFAULT_LIMIT_MAXIMUM_PURCHASE_VOLUME = 1000
DEFAULT_LIMIT_MAXIMUM_SALES_VOLUME = 1000

# QUANTITY PLACEMENT MULTIPLIERS
# the raw quantities multiplier, which then are compared to the MIN_ORDER_BOOK_QUANTITY
# order sizes should neither be too big, and small quantities should still be placed with minimum placement size.
SAFE_QTY_STEP = 0.2
BALANCED_QTY_STEP = 0.1
UNSAFE_QTY_STEP = 0.05

# maximum absolute order size of a slot in the order book. absolute value in MW
DEFAULT_MAX_ORDER_BOOK_QUANTITY = 10
MIN_ORDER_BOOK_QUANTITY = 0.1

# ALLOWED RAMP STEP SIZES
RAMP_SAFETY = 1.0  # 100%,  use at most this fraction of the possible ramp
RAMP_MAX_ORDER_SIZE_FRACTION = 0.1  # upper order size limit as fraction of the ramp

# digits to round mw quantities and prices, usually 2 to cut unused digits which might follow float operations
ROUND_DIGITS = 2

# digits to round after subtraction to avoid e-16 error
DIGITS_TO_AVOID_MACHINE_ERROR = 8

# use internal market
INTERNAL_EXECUTION_MODE = COMMON.InternalExecutionMode.exchange_base_price

# NOT MODIFIABLE

# DEFAULT PRODUCTS FILTER TO BE USED IF NO VALID VALUE GIVEN
PRODUCTS_FILTER_DEFAULT = 0  # allow all products

# SLOT NAMES
SELL_SLOTNAME = "sell_flex"
BUY_SLOTNAME = "buy_flex"
SELL_TRADEBACK_SLOTNAME = "sell_tradeback"
BUY_TRADEBACK_SLOTNAME = "buy_tradeback"

TRADEBACK_PLACEMENT_MODE = "TB"

RAMP_DEFAULT = 10000.

# USED ORDERBOOK LEVELS
# indicator levels used in this strategy
# currently deepest orderbook level is hardcoded to 10MW
ORDER_DEPTH_QTY_STEP = 5  # indicators have 5 MW step size
MAX_ORDERBOOK_DEPTH = 10  # maximum depth
MAX_ORDERBOOK_DEPTH_IDX = MAX_ORDERBOOK_DEPTH // ORDER_DEPTH_QTY_STEP
MIDDLE_ORDERBOOK_DEPTH = 5
MIDDLE_ORDERBOOK_DEPTH_IDX = MIDDLE_ORDERBOOK_DEPTH // ORDER_DEPTH_QTY_STEP
IND_CURRENT_IDX = 0

# ADDITIONAL INFO FIELDS TO TRACK PLACEMENT VIA SLOT INFO
PLACEMENT_INFO_NO_SCALE = "N"
PLACEMENT_INFO_SCALE_INFO = "-SC(%s//%s)"    # relevant scales used
PLACEMENT_INFO_MIN_OF_BUY = "-bmin"
PLACEMENT_INFO_NO_BUY_QTY = "-b0qty"
PLACEMENT_INFO_MAX_OF_SELL = "-smax"
PLACEMENT_INFO_NO_SELL_QTY = "-s0qty"
PLACEMENT_INFO_OMT = "-omt[c_%d_p_%0.1f_t_%s]"  # count, percent and type
PLACEMENT_PUBLIC_OB = "-po[b_%0.1f@%0.2f_s_%0.1f@%0.2f]"  # count, percent and type
PLACEMENT_PUBLIC_OB_EMPTY = "-no_po"  # used if no public orderbook info is available


def get_public_ob_info(front_buy_price, front_buy_qty, front_sell_price, front_sell_qty):
    return (
        "-po[b_"
        + ("%0.1f" % (front_buy_price,) if front_buy_price is not None else "x")
        + "@"
        + ("%0.2f" % (front_buy_qty,) if front_buy_qty is not None else "x")
        + "_s_"
        + ("%0.1f" % (front_sell_price,) if front_sell_price is not None else "x")
        + "@"
        + ("%0.2f" % (front_sell_qty,) if front_sell_qty is not None else "x")
        + "]"
    )


@autotrader_lib.functools_lru_cache.lru_cache(24 * 2 * 4)
def get_interval_description(ts_from, ts_until):
    return "Block: {}-{} [{}-{}]".format(
        ts_from, ts_until,
        CETUTIL.utc_ts2cet_str(ts_from, add_timezone_info=True),
        CETUTIL.utc_ts2cet_str(ts_until, add_timezone_info=True))


# Indicator constants
IND_BUY = 0
IND_SELL = 1

# allowed exchanges for this strategy:
ALLOWED_EXCHANGES = (COMMON.Exchange.epex, COMMON.Exchange.nordpool)

# products can be grouped in blocks of these durations.
# grouping them is necessary to take traded amounts of overlapping products into account
ALLOWED_BLOCK_DURATION = (COMMON.ProductDurations.ID.HOUR, COMMON.ProductDurations.ID.BLOCK_4_HOUR)

# TRADING LATENCIES [sec]
# used to avoid trading too much, the higher the latency,
# the longer the wait after a trade to continue trading on the same product
LATENCY_SAFE_MORE_THAN_5MIN_TO_TRADE = 2
LATENCY_SAFE_LESS_THAN_5MIN_TO_TRADE = 0

LATENCY_BALANCED_MORE_THAN_5MIN_TO_TRADE = 10
LATENCY_BALANCED_BTW_5MIN_2MIN_TO_TRADE = 2
LATENCY_BALANCED_LESS_THAN_2MIN_TO_TRADE = 0

LATENCY_UNSAFE_MORE_THAN_10MIN_TO_TRADE = 90
LATENCY_UNSAFE_BTW_10MIN_5MIN_TO_TRADE = 20
LATENCY_UNSAFE_LESS_THAN_2MIN_TO_TRADE = 10

LATENCY_HIGH_OMT = 40

# Ramp element used for asymmetric ramps
RampElement = collections.namedtuple("RampElement", ["ramp_buy", "ramp_sell"])

# do not repeat the same warning log about refusing order placement for this many messages
OMT_REFUSE_WARNING_SILENCE_PERIOD = 10000


def mk_stat(mode, raw_qty, placed_qty):
    """Create statistics to add to the slot entry for additional info on the placement behaviour and positions

    :type mode: str
    :type raw_qty: float
    :type placed_qty: float
    :rtype: str
    """
    return "%s/r%.1f/p%.1f" % (mode, raw_qty, placed_qty)


def rd(x):
    """round to precision for trading"""
    return round(x, ROUND_DIGITS) if x is not None else x


def rd_me(x):
    """round to avoid machine error"""
    return round(x, DIGITS_TO_AVOID_MACHINE_ERROR) if x is not None else x


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
    NO_IND = "NO_IND"  # if indicators are not available to base placement on public data


def trunc_1digit(number):
    """truncate to 1 digit, used for quantity truncation

    :type number: float
    :rtype: float
    """
    return ((number * 10) // 1) / 10


class MatrixBuilder(strategy.StrategyBase):

    def __init__(self, *args, **kwargs):
        self._stored_scales = {}
        super(MatrixBuilder, self).__init__(*args, **kwargs)

    def on_strategy_update(self, strategy_json):
        # The timeseries can only change in the `on_strategy_update` function, so this is when we have to
        # delte the cached scale matrix
        self._stored_scales = {}
        super(MatrixBuilder, self).on_strategy_update(strategy_json)

    def on_strategy_configuration_update(self, strategy_json):
        # The timeseries can only change in the `on_strategy_update` function, so this is when we have to
        # delte the cached scale matrix
        self._stored_scales = {}
        super(MatrixBuilder, self).on_strategy_configuration_update(strategy_json)

    def build_scale_steering_matrix(self, ts_from, ts_until):
        """Build scales for 1-Hour 2-Hour or 4-Hour time ranges, defining price and quantity levels for each quarter hour

        :param ts_from: start timestamp
        :param ts_until: end timestamp (after 3600 / 7200 / 14400 seconds duration)
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

        Example for 1 Hour:
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

        Modifications for 2h and 4h:

        -> scale instead of lengths 4, has lengths 8 and 16, since there is 1 entry for each quarter hour
        Example with 2 hours (8 quarters, 1 scale each on buy and sell side):
        [
            [[[10.0, 25.0]], [[10.0, 42.0]]],
            [[[10.0, 25.0]], [[10.0, 42.0]]],
            [[[10.0, 25.0]], [[10.0, 42.0]]],
            [[[10.0, 25.0]], [[10.0, 42.0]]],
            [[[10.0, 25.0]], [[10.0, 42.0]]],
            [[[10.0, 25.0]], [[10.0, 42.0]]],
            [[[10.0, 25.0]], [[10.0, 42.0]]],
            [[[10.0, 25.0]], [[10.0, 42.0]]]
        ]

        """

        # scale is [interval_index][<buy/sell>][scale_number, 0...][quantity=0,price=1]
        # the quantity in the scale is not accumulative, thus a scale of
        # [3, 40], [5, 43] means that a total quantity of 8 is available for 2 different prices
        if (ts_from, ts_until) not in self._stored_scales:
            self._stored_scales[(ts_from, ts_until)] = self._build_scale_steering_matrix_inner(ts_from, ts_until)
        return self._stored_scales[(ts_from, ts_until)]

    def _build_scale_steering_matrix_inner(self, ts_from, ts_until):
        scale = [[[], []] for unused_interval in range(ts_from, ts_until, COMMON.QUARTER)]

        def from_timeseries(name, ts, default):
            try:
                series = getattr(self, name)
            except AttributeError:
                return default
            return series.get((ts, ts + COMMON.QUARTER), default)

        # first add the standard timeseries to the scale (as scale 0)
        for idx, ts in enumerate(range(ts_from, ts_until, COMMON.QUARTER)):
            scale[idx][0].append((from_timeseries(COMMON.StrategyJsonKey.TS.pos_buy, ts, 0.) or 0.,
                                  from_timeseries(COMMON.StrategyJsonKey.TS.price_buy, ts, None)))
            scale[idx][1].append((from_timeseries(COMMON.StrategyJsonKey.TS.pos_sell, ts, 0.) or 0.,
                                  from_timeseries(COMMON.StrategyJsonKey.TS.price_sell, ts, None)))

        # then extend the scales by the information from the user timeseries for scales, if they exist
        for scale_idx in range(1, MAX_NUMBER_SCALES + 2):

            for idx, ts in enumerate(range(ts_from, ts_until, COMMON.QUARTER)):
                scale[idx][0].append((from_timeseries(COMMON.StrategyJsonKey.UDFTS.pos_buy_scale.format(scale_idx),
                                                      ts, 0.) or 0.,
                                      from_timeseries(COMMON.StrategyJsonKey.UDFTS.price_buy_scale.format(scale_idx),
                                                      ts, None)))
                scale[idx][1].append((from_timeseries(COMMON.StrategyJsonKey.UDFTS.pos_sell_scale.format(scale_idx),
                                                      ts, 0.) or 0.,
                                      from_timeseries(COMMON.StrategyJsonKey.UDFTS.price_sell_scale.format(scale_idx),
                                                      ts, None)))

        for scale_interval in scale:
            # side:0 - buy, side: 1 sell
            scale_interval[0] = [[qty, prc] for qty, prc in scale_interval[0] if prc is not None]
            # the buy side has to be sorted from higher to lower prices
            scale_interval[0].sort(key=lambda scale: scale[1], reverse=True)
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

        ts_until-ts_from should always be 3600, 7200 or 14400 (1h, 2h or 4h)

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
                                traded_quantities[idx][abs(index - 1)] = round(traded_quantities[idx][abs(index - 1)],
                                                                               8)
                            else:
                                traded_quantities[idx][index] += trade.quantity
                                traded_quantities[idx][index] = round(traded_quantities[idx][index], 8)

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
                    scale_item[0] = round(scale_item[0], 8)

        return remaining_scale, traded_quantities

    def compress_scale_remaining_matrix(self, raw_scale):
        """Compress by taking the minimum of quantities and min or max of front-most prices depending on direction

        :param raw_scale: distribution of price and quantity levels for each side for each quarter hour
        :type raw_scale: list
        :return: compressed scales, depending on number of 15min entries to 30min, 1h, or more
        :rtype: list
        """
        scale = copy.deepcopy(raw_scale)

        def compress_side(index, aggregator, descending):
            # type: (int, T.FunctionType, bool) -> T.ListType[list]
            """Method modifying the scales by compressing high resolution to lower resolution, e.g. 15min->30min"""
            result = []
            res = collections.defaultdict(int)
            min_qty = 0.
            for unused_iteration in range(200):
                for scale_part in scale:
                    if not scale_part[index]:
                        return sorted([[q, p] for p, q in res.items() if q > 0.],
                                      key=lambda x: x[1], reverse=descending)
                    scale_part[index][0][0] -= min_qty
                    if scale_part[index][0][0] <= 0.:
                        # pop that item
                        del scale_part[index][0]
                        if not scale_part[index]:
                            return sorted([[q, p] for p, q in res.items() if q > 0.],
                                          key=lambda x: x[1], reverse=descending)
                min_qty = min(scale_part[index][0][0] for scale_part in scale)
                aggregated_price = aggregator(scale_part[index][0][1] for scale_part in scale)
                result.append([min_qty, aggregated_price])
                res[aggregated_price] += min_qty
                res[aggregated_price] = rd_me(res[aggregated_price])
            raise Exception("Should never be here")

        buy_scales = compress_side(0, min, True)
        sell_scales = compress_side(1, max, False)
        return [[buy_scales, sell_scales]]

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
        return [round(x, 8) for x in traded_quantity]

    @staticmethod
    def get_l1_percent(exchange):
        if exchange.internal_id == COMMON.Exchange.epex:
            return exchange.get_relevant_omt().l1_percent
        return 0

    def determine_dynamic_placement_position(
            self,
            exchange,  # type: APIEXCH.Epex or APIEXCH.NordPool
            product,  # type: APITR.Product
            behaviour,  # type: str
            area,  # type: str
            seconds_left,  # type: float
    ):  # -> tuple
        """Place buy and sell price based on placement mode and orderbook.

        The more aggressive the mode, the more a ask price goes into the bid side of the orderbook.

        :param exchange: current exchange object (Epex, Nordpool, Trayport, ...)
        :type exchange: APIEXCH.Epex or APIEXCH.NordPool
        :param product: current product
        :type product: APITR.Product
        :param behaviour: Strategy Behaviour, can be aggressive (unsafe), balanced or passive (safe)
        :type behaviour: str
        :param area: delivery area id
        :type area: str
        :param seconds_left: seconds left until trading stop on this product
        :type seconds_left: float
        :return: mode, sell_price, sell_price_upper, sell_price_lower, buy_price, buy_price_upper, buy_price_lower
        :rtype: tuple
        """

        try:
            indicators = product.orders.indicators(area)[IND_CURRENT_IDX].mw_prices
        except IndexError:
            return PlacementMode.NO_IND, None, None, None, None, None, None

        return self.get_sell_buy_price_levels(
            mode=self.get_placement_mode(
                behaviour=behaviour,
                omt_l1_percent=self.get_l1_percent(exchange),
                seconds_left=seconds_left,
            ),
            indicators=indicators,
        )

    @staticmethod
    def get_placement_mode(behaviour, omt_l1_percent, seconds_left):
        """Get placement mode depending on behaviour, otr limits and seconds.

        The mode will define the price finding mechanism

        :param behaviour: Strategy Behaviour, can be aggressive (unsafe), balanced or passive (safe)
        :type behaviour: str
        :param omt_l1_percent: OMT L1 percent
        :type omt_l1_percent: float
        :param seconds_left: seconds left until trading stop on this product
        :type seconds_left: float
        :return: Placement mode
        :rtype: str
        """
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
        if omt_l1_percent >= BRUTE_FORCE_PERCENT_OF_MAX_OMT:
            mode = PlacementMode.bruteforce
        elif omt_l1_percent >= FORCE_PERCENT_OF_MAX_OMT and mode != PlacementMode.bruteforce:
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

        buy_price_middle = indicators[IND_BUY][MIDDLE_ORDERBOOK_DEPTH_IDX]
        buy_price_deep = indicators[IND_BUY][MAX_ORDERBOOK_DEPTH_IDX]
        sell_price_middle = indicators[IND_SELL][MIDDLE_ORDERBOOK_DEPTH_IDX]
        sell_price_deep = indicators[IND_SELL][MAX_ORDERBOOK_DEPTH_IDX]

        if mode == PlacementMode.lazy:
            if notnone(buy_price_middle, buy_price_deep, sell_price_middle, sell_price_deep):
                mid = (buy_price_deep + sell_price_deep) * 0.5
                sell_price = (sell_price_middle + sell_price_deep) / 2  # between 5MW and 10 MW
                sell_price_lower = mid  # mid
                sell_price_upper = sell_price_deep  # 10 MW
                buy_price = (buy_price_middle + buy_price_deep) / 2  # between 5MW and 10 MW
                buy_price_lower = buy_price_deep  # 10 MW
                buy_price_upper = mid  # mid
        elif mode == PlacementMode.active:
            if notnone(buy_price_middle, buy_price_middle, sell_price_middle, sell_price_middle):
                mid = (buy_price_middle + sell_price_middle) * 0.5
                sell_price = sell_price_middle  # 5 MW
                sell_price_lower = mid  # 5 MW
                sell_price_upper = sell_price_middle  # 5 MW
                buy_price = buy_price_middle  # 5 MW
                buy_price_lower = buy_price_middle  # 5 MW
                buy_price_upper = mid  # 5 MW
        elif mode == PlacementMode.progressive:
            if notnone(buy_price_middle, buy_price_middle, sell_price_middle, sell_price_middle):
                sell_price = sell_price_middle * 0.7 + buy_price_middle * 0.3  # in spread, more on the sell side
                sell_price_lower = buy_price_middle * 0.7 + sell_price_middle * 0.3  # 5 MW
                sell_price_upper = sell_price_middle  # 5 MW
                buy_price = buy_price_middle * 0.7 + sell_price_middle * 0.3  # in spread, more on the buy side
                buy_price_lower = buy_price_middle  # 5 MW
                buy_price_upper = sell_price_middle * 0.7 + buy_price_middle * 0.3  # 5 MW
        elif mode == PlacementMode.aggressive:
            if notnone(buy_price_middle, buy_price_middle, sell_price_middle, sell_price_middle):
                # in spread, more on the buy side minus 10 cent
                sell_price = sell_price_middle * 0.3 + buy_price_middle * 0.7 - 0.1
                sell_price_lower = buy_price_middle  # 5 MW
                sell_price_upper = sell_price_middle  # 5 MW
                # in spread, more on the sell side plus 10 cent
                buy_price = buy_price_middle * 0.3 + sell_price_middle * 0.7 + 0.1
                buy_price_lower = buy_price_middle  # 5 MW
                buy_price_upper = sell_price_middle  # 5 MW
        elif mode == PlacementMode.bruteforce:  # just trade it
            if notnone(buy_price_middle, buy_price_deep, sell_price_middle, sell_price_deep):
                # hit order
                sell_price = buy_price_deep
                sell_price_lower = buy_price_deep
                sell_price_upper = buy_price_deep
                # hit order
                buy_price = sell_price_deep
                buy_price_lower = sell_price_deep
                buy_price_upper = sell_price_deep
        return mode, sell_price, sell_price_lower, sell_price_upper, buy_price, buy_price_lower, buy_price_upper

    @staticmethod
    def truncate_quantity_by_behaviour(maximum_order_book, behaviour, quantity):
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

        if behaviour == StrategyBehavior.safe:
            upper_limit = min(max(quantity * SAFE_QTY_STEP, MIN_ORDER_BOOK_QUANTITY), maximum_order_book)
        elif behaviour == StrategyBehavior.balanced:
            upper_limit = min(max(quantity * BALANCED_QTY_STEP, MIN_ORDER_BOOK_QUANTITY), maximum_order_book)
        else:
            upper_limit = min(max(quantity * UNSAFE_QTY_STEP, MIN_ORDER_BOOK_QUANTITY), maximum_order_book)

        # quantity has to be restricted to 1 digit
        return trunc_1digit(max(min(quantity, upper_limit), 0))

    def build_placement_for_products(
        self,
        tradable_active_products,
        remaining_matrix,
        maximum_order_book,
        behaviour,
        area,
        ts_from,
        ts_until,
        timestamp,
        trading_end_before_market_closure,
    ):
        """Build packets for placement of the quantities in remaining_matrix using the available products.

        The quantities are filled from the longer term (hour) products to the shorter term (quarter) products
        filling the longer term products only with consistent packets over every quarter.
        The maximum order size depends on the base quantity of the scale and the mode set for the strategy
        (StrategyBehavior) and on the maximum_order_book setting.
        The quantity itself is dependent on the position of the order in the order book, depending on the
        product's indicators

        :return dictionary,
                key: product id,
                value: tuple: (raw_buy_quantity, buy_amount, buy_price, buy_price_lower,
                               buy_price_upper, raw_sell_quantity, sell_amount, sell_price,
                               sell_price_lower, sell_price_upper, placement_mode, seconds_left)
        :rtype: T.Dict[str, tuple]

        """
        placement = dict()
        remaining_matrix = copy.deepcopy(remaining_matrix)
        # all_range_products should be a list of all the products delivering in ts_from-ts_until and suitable for
        # trading of this product.
        # ts_until-ts_from should always be 3600 (complete hour)
        # now sort the all_available_products list by the delivery interval
        tradable_active_products.sort(key=lambda prod: prod.delivery_end - prod.delivery_start, reverse=True)

        # for logging, keep track of placement reason

        for product in tradable_active_products:
            # is this product currently being traded?
            # This check should be made by the product filter, we check here again to be defensive
            if product.state(area) != COMMON.DeliveryAreaState.active:
                continue
            trading_end = product.delivery_start - trading_end_before_market_closure
            seconds_left = trading_end - timestamp
            if seconds_left < 0:
                # still active, but trading is over now
                self.debug_log(
                    "Trading stop due to ended trading time. "
                    "Stop before delivery: %f" % trading_end_before_market_closure,
                    product
                )
                placement[product.product_id] = (0., 0., 0., 0., 0., 0., 0., 0., 0., 0., "X", 0.)
                continue
            # determine dynamic placement position for buy and sell
            (
                placement_mode, sell_price, sell_price_lower, sell_price_upper, buy_price,
                buy_price_lower, buy_price_upper
            ) = self.determine_dynamic_placement_position(
                self.exchange, product, behaviour, area, seconds_left
            )
            # lookup the price positions in the matrix
            # ... for every quarter of the product delivery

            duration = product.delivery_end - product.delivery_start
            block_length = ts_until - ts_from
            parts = block_length // COMMON.QUARTER
            segments = block_length // duration
            segment_length = parts / segments
            seconds_since_block_start = product.delivery_start - ts_from

            scale_interval_index = seconds_since_block_start // duration
            min_idx = scale_interval_index * segment_length
            max_idx = (scale_interval_index + 1) * segment_length

            if duration == COMMON.QUARTER:
                # only for quarters go through each quarter
                use_matrix = remaining_matrix
            else:
                # for all other granularities, only go through zeroth idx,
                # since remaining matrix is reduced to relevant values
                part_to_compress = remaining_matrix[min_idx:max_idx]
                use_matrix = self.compress_scale_remaining_matrix(part_to_compress)
                scale_interval_index = 0

            # look up the quantity for the product's placement prices in the remaining matrix.
            # if there is a quantity for that price, use it. If not (price too high or low),
            # place the fixed order at the lowest scale, if there's still quantity
            sell_amounts_interval = []
            buy_amounts_interval = []

            # accumulate buy from scales

            # default buy price, will be replaced with next highest scale price
            buy_scale_start = -100000.
            # describes whether or which scale is used to find the price
            buy_scale_idx = PLACEMENT_INFO_NO_SCALE
            sell_scale_idx = PLACEMENT_INFO_NO_SCALE

            for buy_scale_idx, scale in enumerate(use_matrix[scale_interval_index][0]):
                # with each iteration, the price at scale[1] will be falling, since we go deeper.
                # this means the first iteration sets the buy_scale_start, the upper limit at which the bid can be set.
                buy_scale_start = max(buy_scale_start, scale[1])

                if (buy_price is None or scale[1] < buy_price) and buy_scale_idx == 0:
                    # only for the first scale, accept a price inside the price tolerance
                    buy_amounts_interval.append((scale[0], scale[1]))
                    break

                # if scale exceeds the buy_price set by the placement mechanism, then use the buy_price
                if scale[1] >= buy_price:
                    buy_amounts_interval.append((scale[0], buy_price))
                else:
                    break

            # accumulate sell from scales
            sell_scale_start = 100000.  # default sell price, will be replaced with next highest scale price

            for sell_scale_idx, scale in enumerate(use_matrix[scale_interval_index][1]):
                sell_scale_start = min(sell_scale_start, scale[1])
                if (sell_price is None or scale[1] > sell_price) and sell_scale_idx == 0:
                    # only for the first scale, accept a price inside the price tolerance
                    sell_amounts_interval.append((scale[0], scale[1]))
                    break
                if scale[1] <= sell_price:
                    sell_amounts_interval.append((scale[0], sell_price))
                else:
                    break

            placement_mode += PLACEMENT_INFO_SCALE_INFO % (buy_scale_idx, sell_scale_idx)

            if buy_amounts_interval:
                # buy price should be the lowest across all quarters involved in this duration
                raw_buy_quantity = sum(elem[0] for elem in buy_amounts_interval)
                buy_amount = self.truncate_quantity_by_behaviour(maximum_order_book, behaviour, raw_buy_quantity)
                buy_price = min(elem[1] for elem in buy_amounts_interval)
                placement_mode += PLACEMENT_INFO_MIN_OF_BUY
            else:
                # no placement, if the scales did not show any quantity to trade for this duration
                raw_buy_quantity = 0.
                buy_amount = 0.
                buy_price = 0.
                placement_mode += PLACEMENT_INFO_NO_BUY_QTY
            if sell_amounts_interval:
                # sell price should be the highest across all quarters involved in this duration
                raw_sell_quantity = sum(elem[0] for elem in sell_amounts_interval)
                sell_amount = self.truncate_quantity_by_behaviour(maximum_order_book, behaviour, raw_sell_quantity)
                sell_price = max(elem[1] for elem in sell_amounts_interval)
                placement_mode += PLACEMENT_INFO_MAX_OF_SELL
            else:
                # no placement, if the scales did not show any quantity to trade for this duration
                raw_sell_quantity = 0.
                sell_amount = 0
                sell_price = 0
                placement_mode += PLACEMENT_INFO_NO_SELL_QTY

            # now remove the quantity from the overall scale, so the other products don't get it
            for ts in range(product.delivery_start, product.delivery_end, COMMON.QUARTER):
                scale_interval_index = (ts - ts_from) / COMMON.QUARTER
                # buy
                # 2 options here:
                # using raw_buy_quantity: makes sure that largest chunk remains reserved for the longest product
                # using buy_amount: quantities traded equally among products of all duration
                # amount_to_deduct = buy_amount
                amount_to_deduct = raw_buy_quantity

                for idx, scale in enumerate(remaining_matrix[scale_interval_index][0]):
                    deduct = min(scale[0], amount_to_deduct)
                    scale[0] -= deduct
                    scale[0] = rd_me(scale[0])
                    amount_to_deduct -= deduct
                    amount_to_deduct = rd_me(amount_to_deduct)

                # sell
                # using raw_sell_quantity: makes sure that largest chunk remains reserved for the longest product
                # using sell_amount: quantities traded equally among products of all duration
                # amount_to_deduct = sell_amount
                amount_to_deduct = raw_sell_quantity

                for idx, scale in enumerate(remaining_matrix[scale_interval_index][1]):
                    deduct = min(scale[0], amount_to_deduct)
                    scale[0] -= deduct
                    scale[0] = rd_me(scale[0])
                    amount_to_deduct -= deduct
                    amount_to_deduct = rd_me(amount_to_deduct)

            # memorize the data for this product
            buy_price_lower = rd_me(min(min(buy_price_lower, buy_price), buy_scale_start))
            buy_price_upper = rd_me(min(max(buy_price_upper, buy_price), buy_scale_start))
            sell_price_lower = rd_me(max(min(sell_price_lower, sell_price), sell_scale_start))
            sell_price_upper = rd_me(max(max(sell_price_upper, sell_price), sell_scale_start))
            placement[product.product_id] = (
                raw_buy_quantity, buy_amount, buy_price, buy_price_lower, buy_price_upper,
                raw_sell_quantity, sell_amount, sell_price, sell_price_lower, sell_price_upper, placement_mode,
                seconds_left
            )
        return placement

    def build_tradeback_placement_for_products(self, tradable_active_products, traded_quantities, maximum_order_book,
                                               sell_limit_prices, buy_limit_prices, area, ts_from, timestamp,
                                               trading_end_before_market_closure):
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
        Currently, the passed limit prices are taken from the time series:
        - strategy_limit_maximum_purchase_price
        - strategy_limit_maximum_sales_price

        Price Aggregation:
        - bid: minimum value of quarter hours is taken, if product has longer duration
        - ask: maximum value of quarter hours is taken, if product has longer duration
        """
        placement = dict()
        traded_quantities = copy.deepcopy(traded_quantities)

        # tradeback quantities: positive means, we sold more than we bought -> need to buy back
        net_tradeback_by_quarter = [rd_me(sell - buy) for buy, sell in traded_quantities]

        # all_range_products should be a list of all the products delivering in ts_from-ts_until and suitable for
        # trading of this product.
        # ts_until-ts_from should always be 3600 (complete hour)
        # now sort the all_available_products list by the delivery interval
        tradable_active_products.sort(key=lambda prod: prod.delivery_end - prod.delivery_start, reverse=True)

        for product in tradable_active_products:
            # is this product currently being traded?
            if product.state(area) != COMMON.DeliveryAreaState.active:
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

                # Example:
                # 1) transform traded amounts to net amounts
                # [
                #     [2.2, 2.0], -> 0.2
                #     [2.2, 1.4], -> 0.8
                #     [6.2, 6.4], -> -0.2
                #     [3.7, 2.4], -> 1.3
                # ]
                #
                # 2) collect buy amounts and sell amounts
                # buy_amounts_product => [(0.2, 28), (0.8, 27), (0, 26.5), (1.3, 27.5)]
                # sell_amounts_product =>  [(0, 30), (0, 29), (0.2, 29.5), (0, 30.5)]

                scale_interval_index = (ts - ts_from) / COMMON.QUARTER
                # accumulate buy from the current sold quantities
                buy_amounts_product.append((max(net_tradeback_by_quarter[scale_interval_index], 0),
                                            buy_limit_prices[scale_interval_index]))
                # accumulate sell from the current bought quantities
                sell_amounts_product.append((max(-net_tradeback_by_quarter[scale_interval_index], 0),
                                             sell_limit_prices[scale_interval_index]))

            # now evaluate the quantities over all intervals
            buy_amount = buy_price = 0.
            sell_amount = sell_price = 0.
            if buy_amounts_product:
                buy_amount = min(elem[0] for elem in buy_amounts_product)
                buy_price = min(elem[1] for elem in buy_amounts_product)
            if sell_amounts_product:
                sell_amount = min(elem[0] for elem in sell_amounts_product)
                sell_price = max(elem[1] for elem in sell_amounts_product)

            # restrict placement by maximum order book setting
            pos = min(rd_me(buy_amount - sell_amount), maximum_order_book)

            if abs(pos) < MIN_ORDER_BOOK_QUANTITY:
                placement[product.product_id] = (
                    0, buy_price,
                    0, sell_price
                )
                continue

            # now remove the quantity from the net_tradeback_by_quarter, so the other products don't get it
            for ts in range(product.delivery_start, product.delivery_end, COMMON.QUARTER):
                scale_interval_index = (ts - ts_from) / COMMON.QUARTER
                # buy
                net_tradeback_by_quarter[scale_interval_index] -= pos
                net_tradeback_by_quarter[scale_interval_index] = rd_me(net_tradeback_by_quarter[scale_interval_index])

            # memorize the data for this product

            if pos > 0:
                placement[product.product_id] = (
                    rd(pos), buy_price,
                    0, sell_price
                )
            elif pos < 0:
                placement[product.product_id] = (
                    0, buy_price,
                    rd(-pos), sell_price
                )
        return placement


class FlexibilityStrategyError(Exception):
    def __init__(self, msg):
        super(FlexibilityStrategyError, self).__init__(msg)


def mk_df_ts():
    #  type: () -> strategy.StrategyTimeSeries
    return strategy.StrategyTimeSeries(ts_raster=COMMON.QUARTER)


class CustomStrategy(strategy.Strategy, strategy.ProductsFilterMixin, MatrixBuilder):
    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        self.log = log
        self.position = strategy.Position()
        self.behavior = StrategyBehavior.balanced
        self.delivery_area_id = None
        self.only_log_every_n_omt_warnings = OMT_REFUSE_WARNING_SILENCE_PERIOD
        self.omt_warn_log_counter = 0

        self.strategy_position_tradable_position_long = mk_df_ts()  # type: strategy.StrategyTimeSeries
        self.strategy_position_tradable_position_short = mk_df_ts()  # type: strategy.StrategyTimeSeries
        self.strategy_price_purchase_immediate_vesting = mk_df_ts()  # type: strategy.StrategyTimeSeries
        self.strategy_price_sales_immediate_vesting = mk_df_ts()  # type: strategy.StrategyTimeSeries
        self.strategy_limit_maximum_sales_volume = mk_df_ts()  # type: strategy.StrategyTimeSeries
        self.strategy_limit_maximum_purchase_volume = mk_df_ts()  # type: strategy.StrategyTimeSeries
        self.strategy_limit_maximum_purchase_price = mk_df_ts()  # type: strategy.StrategyTimeSeries
        self.strategy_limit_minimum_sales_price = mk_df_ts()  # type: strategy.StrategyTimeSeries
        self.strategy_price_minimum_spread_buyback = mk_df_ts()  # type: strategy.StrategyTimeSeries
        self.strategy_price_purchase = mk_df_ts()  # type: strategy.StrategyTimeSeries
        self.strategy_price_sales = mk_df_ts()  # type: strategy.StrategyTimeSeries

        # AUT-1219: asymmetric ramps, add ramp for buy and sell side
        # initialize with none, later check, only use if not none, i.e. it was set in on_strategy_update
        # these ramps are the technical ramps of the power plant
        self.strategy_ramp_buy = mk_df_ts()  # type: strategy.StrategyTimeSeries
        self.strategy_ramp_sell = mk_df_ts()  # type: strategy.StrategyTimeSeries

        # AUT-1221: dayahead schedule ramps to be considered for ramp calculations
        # Once every update, the strategy receives a timeseries with the positions closed before intraday
        self.strategy_closed_positions_before_intraday = mk_df_ts()  # type: strategy.StrategyTimeSeries
        # and based on that it can calculate the new possible ramp ranges, which are valid for intraday
        # if technical ramps are 10/10, and 10MW-20MW were bought before intraday in 2 adjacent products
        # the new ramps would be 0/20
        self.strategy_calc_used_ramp_before_intraday = mk_df_ts()  # type: strategy.StrategyTimeSeries
        # temporary timeseries which combines the values from asymmetric, default and fallback symmetric ramp values
        self.strategy_calc_ramp_buy = mk_df_ts()  # type: strategy.StrategyTimeSeries
        self.strategy_calc_ramp_sell = mk_df_ts()  # type: strategy.StrategyTimeSeries
        # asymmetric timeseries which take the amount traded previous to intraday into account
        # these are the adjusted ramps
        self.strategy_calc_ramp_buy_intraday = mk_df_ts()  # type: strategy.StrategyTimeSeries
        self.strategy_calc_ramp_sell_intraday = mk_df_ts()  # type: strategy.StrategyTimeSeries

        # AUT-1219: asymmetric ramps, keep symmetric ramp as fall back, if both buy and sell side are not defined
        # initialize with none, later check, only use if not none, i.e. it was set in on_strategy_update
        self.strategy_ramp = mk_df_ts()  # type: strategy.StrategyTimeSeries

        # remember placed quantities in the current run
        self.sent_slots = collections.defaultdict(
            lambda: {COMMON.Direction.buy: 0, COMMON.Direction.sell: 0}
        )

    @staticmethod
    @autotrader_lib.functools_lru_cache.lru_cache(24 * 4 * 2)  # max-size is the number of quarter hours in 2 days
    def get_block_interval(start_ts, block_hours=1):
        """return 1h block or 4h block interval for the given start and end time

        :type start_ts: int
        :type block_hours: int
        :rtype: tuple[int, int]
        """
        # only allow blocks of 1 hour or 4 hour duration
        assert block_hours in (1, 4)

        start_cet_dt = ALCU.utc_ts2cet_dt(start_ts)
        starting_hour = start_cet_dt.hour // block_hours * block_hours
        start_cet_dt = datetime.datetime.combine(start_cet_dt.date(), datetime.time(starting_hour))
        start_block = ALCU.cet_dt2int_ts(start_cet_dt)

        closing_hour = start_cet_dt.hour // block_hours * block_hours + block_hours
        shift_day = closing_hour // 24
        shift_hours = closing_hour % 24
        end_cet_dt = datetime.datetime.combine(start_cet_dt.date() + datetime.timedelta(days=shift_day),
                                               datetime.time(shift_hours))
        end_block = ALCU.cet_dt2int_ts(end_cet_dt)

        return start_block, end_block

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
                latency = LATENCY_SAFE_MORE_THAN_5MIN_TO_TRADE
            else:
                latency = LATENCY_SAFE_LESS_THAN_5MIN_TO_TRADE
        elif behaviour == StrategyBehavior.balanced:
            if seconds_left > COMMON.MINUTE * 5:
                latency = LATENCY_BALANCED_MORE_THAN_5MIN_TO_TRADE
            elif seconds_left > COMMON.MINUTE * 2:
                latency = LATENCY_BALANCED_BTW_5MIN_2MIN_TO_TRADE
            else:
                latency = LATENCY_BALANCED_LESS_THAN_2MIN_TO_TRADE
        else:
            if seconds_left > COMMON.MINUTE * 10:
                latency = LATENCY_UNSAFE_MORE_THAN_10MIN_TO_TRADE
            elif seconds_left > COMMON.MINUTE * 5:
                latency = LATENCY_UNSAFE_BTW_10MIN_5MIN_TO_TRADE
            else:
                latency = LATENCY_UNSAFE_LESS_THAN_2MIN_TO_TRADE
        if self.get_l1_percent(self.exchange) > OMT_PERCENT_LIMIT_TO_PLACE_WITH_10SEC_LATENCY:
            latency = LATENCY_HIGH_OMT
        return bool(product.trades.get(buy_delivery_area=None, sell_delivery_area=None,
                                       delivery_area=self.delivery_areas[0],
                                       portfolio_key=self.strategy_id,
                                       trade_filter=API.TradeFilter.own,
                                       timerange=(timestamp - latency, timestamp + 10)))

    @staticmethod
    def calc_used_ramps(strategy_closed_positions_before_intraday):
        """sort the entries of the closed positions timeseries and return the differences between each quarter hour

        positions are long (sell) positions.
        increase in a long (sell) positions means, more is sold.
        calc_ramp_sell must be decreased.
        calc_ramp_buy must be increased

        :param strategy_closed_positions_before_intraday: time series of closed positions before intraday trading
        :type strategy_closed_positions_before_intraday: dict
        :return: dictionary of used ramps based on intraday position changes
        :rtype: dict
        """

        used_ramps = {}
        # check to keep compatibility if these timeseries do not exist
        if not strategy_closed_positions_before_intraday or len(strategy_closed_positions_before_intraday) == 0:
            return used_ramps

        # filter to user quarter hours only
        strategy_closed_positions_before_intraday = {k: v for k, v in strategy_closed_positions_before_intraday.items()
                                                     if k[1] - k[0] == 900}
        # sorting the tuples is enough, accessing the first element of the start/end tuple is not necessary
        # in python sorting tuples works by consecutively comparing the elements with the same index beginning with
        # index 0.
        sorted_vals = sorted(strategy_closed_positions_before_intraday.items(), key=lambda x: operator.itemgetter(0)(x))

        last_start = None
        last_end = None
        last_value = None

        for (start, end), value in sorted_vals:
            if (end - start == 900 and start == last_end and value is not None and last_value is not None):
                used_ramps[(last_start, last_end)] = value - last_value
            else:
                used_ramps[(last_start, last_end)] = None
            last_start, last_end, last_value = start, end, value

        # remove entry of used round
        del used_ramps[(None, None)]
        # add last interval, unknown value since we dont know the next closed day-ahead position
        used_ramps[(last_start, last_end)] = None

        return used_ramps

    @staticmethod
    def calc_buy_sell_ramps(ramp_buy, ramp_sell, ramp, default_ramp):
        """Calculate the valid buy/sell ramps for the strategy based on ramp input values

        :param ramp_buy: ramp_buy of input timeseries
        :type ramp_buy: dict
        :param ramp_sell: ramp_sell of input timeseries
        :type ramp_sell: dict
        :param ramp: ramp of input timeseries
        :type ramp: dict
        :param default_ramp: default_ramp of input timeseries
        :type default_ramp: float
        :return: calculated buy and sell ramps based on input timeseries and fallback values
        :rtype: tuple[dict, dict]
        """
        keys = list(set([x for k in [ramp_buy, ramp_sell, ramp] if k is not None for x in k.keys()]))

        calc_ramps_buy = {}
        calc_ramps_sell = {}

        # if both asymmetric timeseries exist, then use asymmetric prices as far as possible
        for interval in keys:
            ramp_buy_entry = ramp_buy.get(interval)
            ramp_sell_entry = ramp_sell.get(interval)

            if ramp_buy_entry is None:
                ramp_buy_entry = ramp.get(interval, default_ramp)
            if ramp_sell_entry is None:
                ramp_sell_entry = ramp.get(interval, default_ramp)

            if ramp_buy_entry is None:
                ramp_buy_entry = default_ramp
            if ramp_sell_entry is None:
                ramp_sell_entry = default_ramp

            calc_ramps_buy[interval] = ramp_buy_entry
            calc_ramps_sell[interval] = ramp_sell_entry

        # if both asymmetric timeseries do not exist, then fall back on symmetric timeseries
        return calc_ramps_buy, calc_ramps_sell

    @staticmethod
    def calc_intraday_ramps(calc_ramp_buy, calc_ramp_sell, calc_used_ramp_before_intraday,
                            default_ramp):
        """Calculate final intraday ramps, based on used day-ahead and available intra-day ramp time series

        :param calc_ramp_buy: calculated ramp buy, combined from ramp_buy and ramp time series
        :type calc_ramp_buy: T.DictType[T.TupleType[int, int], float]
        :param calc_ramp_sell: calculated ramp buy, combined from ramp_sell and ramp time series
        :type calc_ramp_sell: T.DictType[T.TupleType[int, int], float]
        :param calc_used_ramp_before_intraday: calculated used ramp,
            calculated from strategy_closed_positions_before_intraday time series
        :type calc_used_ramp_before_intraday: T.DictType[T.TupleType[int, int], float]
        :param default_ramp: default value to replace missing values or None values in the time series
        :type default_ramp: float
        :return: final calculated buy and sell ramp
        :rtype: (T.DictType[T.TupleType[int, int], float], T.DictType[T.TupleType[int, int], float])
        """
        keys = list(
            set([x for k in [calc_ramp_buy, calc_ramp_sell, calc_used_ramp_before_intraday] if k is not None for x in
                 k.keys()]))

        calc_intraday_ramps_buy = {}
        calc_intraday_ramps_sell = {}

        # if both asymmetric timeseries exist, then use asymmetric prices as far as possible
        for interval in keys:
            ramp_buy_entry = calc_ramp_buy.get(interval)
            ramp_sell_entry = calc_ramp_sell.get(interval)

            if ramp_buy_entry is None:
                ramp_buy_entry = default_ramp
            if ramp_sell_entry is None:
                ramp_sell_entry = default_ramp

            # used ramp defaults to 0
            used_ramp = calc_used_ramp_before_intraday.get(interval, 0) or 0

            calc_intraday_ramps_buy[interval] = ramp_buy_entry + used_ramp
            calc_intraday_ramps_sell[interval] = ramp_sell_entry - used_ramp

        return calc_intraday_ramps_buy, calc_intraday_ramps_sell

    @staticmethod
    def evaluate_ramp_minmaxes(pos_before, pos, pos_after,
                               ramp_before, ramp,
                               slots_before_buy=0, slots_buy=0, slots_after_buy=0,
                               slots_before_sell=0, slots_sell=0, slots_after_sell=0):
        """Get max_buy and max_sell qty restricted by surrounding ramps and positions, and capped to 10% of ramp before

        There are 2 steps, first considering the ramps, and targeting a certain stepsize of the total ramp,
         and then including already placed quantities in the estimation

        :param pos_before: pos at t-900s
        :type pos_before: float
        :param pos: pos at t
        :type pos: float
        :param pos_after: pos at t+900s
        :type pos_after: float
        :param ramp_before: ramp starting at t-900s
        :type ramp_before: RampElement
        :param ramp: ramp starting at t
        :type ramp: RampElement
        :type slots_before_buy: float
        :type slots_buy: float
        :type slots_after_buy: float
        :type slots_before_sell: float
        :type slots_sell: float
        :type slots_after_sell: float
        :return: max_buy and max_sell, capped order sizes in buy and sell direction respecting ramp and positions.
        :rtype: T.TupleType[float, float]
        """

        # buy: maximum reachable position based on position before and the allowed buy ramp from before to now
        max_before = pos_before + RAMP_SAFETY * ramp_before.ramp_buy
        # sell: maximum reachable position based on position after and the allowed sell ramp from now to after
        max_after = pos_after + RAMP_SAFETY * ramp.ramp_sell
        # maximum reachable position combining both restrictions
        max_joined = min(max_before, max_after)

        # sell: minimum reachable positions based on position before and the allowed sell ramp from before to now
        min_before = pos_before - RAMP_SAFETY * ramp_before.ramp_sell
        # buy: minimum reachable positions based on position after and the allowed buy ramp from now to after
        min_after = pos_after - RAMP_SAFETY * ramp.ramp_buy
        # minimum reachable position combining both restrictions
        min_joined = max(min_before, min_after)

        # now take the current position into account and
        # get allowed range of position change, based on the max and min of the allowed position in the
        # current delivery duration
        max_diff_to_target = max_joined - pos
        min_diff_to_target = pos - min_joined

        # get the leftover buy potential, by checking how much of the buy ramp is left over from the position before
        # ex. rampbuy 10, pos_before 5, pos 10 -> rest_buy_potential 5
        # ex. rampbuy 10, pos_before 10, pos 5 -> rest_buy_potential 15
        # ex. rampbuy 0, pos_before 5, pos 10 -> rest_buy_potential -5  -> 0
        rest_buy_potential = max(ramp_before.ramp_buy - (pos - pos_before), 0)

        # get the leftover sell potential, by checking how much of the sell ramp is left over from the position before
        # ex. rampsell 10, pos_before 5, pos 10 -> rest_sell_potential 15
        # ex. rampsell 10, pos_before 10, pos 5 -> rest_sell_potential 5
        # ex. rampsell 0, pos_before 10, pos 5 -> rest_sell_potential -5  -> 0
        rest_sell_potential = max(ramp_before.ramp_sell + (pos - pos_before), 0)

        buyable = max((rest_buy_potential, ramp_before.ramp_buy, 0))
        sellable = max((rest_sell_potential, ramp_before.ramp_sell, 0))
        max_buy = rd(min(max(max_diff_to_target, 0), RAMP_MAX_ORDER_SIZE_FRACTION * buyable))
        max_sell = rd(min(max(min_diff_to_target, 0.), RAMP_MAX_ORDER_SIZE_FRACTION * sellable))

        # additional restrictions due to placed orders
        used_start_ramp = pos - pos_before
        used_end_ramp = pos_after - pos
        # also consider already placed slots
        reserved_buy_before_to_now = slots_before_sell - slots_buy
        reserved_buy_now_to_after = slots_sell - slots_after_buy
        reserved_sell_before_to_now = slots_before_buy - slots_sell
        reserved_sell_now_to_after = slots_buy - slots_after_sell
        # ramp reduced by
        buy_ramp_reduction_by_before = used_start_ramp + reserved_buy_before_to_now
        sell_ramp_reduction_by_before = -used_start_ramp + reserved_sell_before_to_now
        buy_ramp_reduction_by_after = used_end_ramp + reserved_buy_now_to_after
        sell_ramp_reduction_by_after = -used_end_ramp + reserved_sell_now_to_after
        # get the leftover ramps, which will limit how much the position can move based on surrounding positions
        rest_buy_before_to_now = ramp_before.ramp_buy - buy_ramp_reduction_by_before
        rest_sell_before_to_now = ramp_before.ramp_sell - sell_ramp_reduction_by_before
        rest_buy_now_to_after = ramp.ramp_buy - buy_ramp_reduction_by_after
        rest_sell_now_to_after = ramp.ramp_sell - sell_ramp_reduction_by_after
        # cap tradeable quantities by the placed quantities
        max_buy = max(min(max_buy, rest_buy_before_to_now, rest_sell_now_to_after), 0)
        max_sell = max(min(max_sell, rest_sell_before_to_now, rest_buy_now_to_after), 0)
        return max_buy, max_sell

    @staticmethod
    def get_qty_with_reason(slot_qty, qty_limit, maximum_order_book, ramp_limit):
        """Get quantity limited by positions, maximum orderbook, placements and ramp

        :param slot_qty: quantity of the original slot
        :param qty_limit: quantity limited by the volume limits, traded and placed amounts
        :param maximum_order_book: limitations by the maximum orderbook parameter
        :param ramp_limit: limitations by the ramp limit
        :return: final quantity and an info on the limitation applied
        :rtype: (float, str)
        """
        qty = max(min(
            [slot_qty, maximum_order_book, qty_limit, ramp_limit]
        ), 0)
        if qty == slot_qty:
            return qty, "/"
        elif qty == maximum_order_book:
            return qty, "/lmt.ob"
        elif qty == qty_limit:
            return qty, "/lmt.qty_limit"
        elif qty == ramp_limit:
            return qty, "/lmt.rmp"
        else:
            return qty, "/none"

    def get_limit_ts_vals(self, product):
        """Read limit values valid for this product from the timeseries, use default as fallback

        :param product: Product
        :type product: autotrader_core.exchange_trading.Product
        :return: limit for (buy price, sales price, buy volume, sales volume)
        :rtype:(float, float, float, float)
        """
        product_interval = (product.delivery_start, product.delivery_end)

        limit_maximum_purchase_price = self.strategy_limit_maximum_purchase_price.get(product_interval, None)
        limit_minimum_sales_price = self.strategy_limit_minimum_sales_price.get(product_interval, None)
        limit_maximum_purchase_volume = self.strategy_limit_maximum_purchase_volume.get(product_interval, None)
        limit_maximum_sales_volume = self.strategy_limit_maximum_sales_volume.get(product_interval, None)

        if limit_maximum_purchase_price is None:
            limit_maximum_purchase_price = DEFAULT_LIMIT_MAXIMUM_PURCHASE_PRICE
            self.warn_log("No limit_maximum_purchase_price set for {interval}, using default value: {def_val}"
                          .format(interval=product_interval, def_val=limit_maximum_purchase_price), product)

        if limit_minimum_sales_price is None:
            limit_minimum_sales_price = DEFAULT_LIMIT_MINIMUM_SALES_PRICE
            self.warn_log("No limit_minimum_sales_price set for {interval}, using default value: {def_val}"
                          .format(interval=product_interval, def_val=limit_minimum_sales_price), product)

        if limit_maximum_purchase_volume is None:
            limit_maximum_purchase_volume = DEFAULT_LIMIT_MAXIMUM_PURCHASE_VOLUME
            self.warn_log("No limit_maximum_purchase_volume set for {interval}, using default value: {def_val}"
                          .format(interval=product_interval, def_val=limit_maximum_purchase_volume), product)

        if limit_maximum_sales_volume is None:
            limit_maximum_sales_volume = DEFAULT_LIMIT_MAXIMUM_SALES_VOLUME
            self.warn_log("No limit_maximum_sales_volume set for {interval}, using default value: {def_val}"
                          .format(interval=product_interval, def_val=limit_maximum_sales_volume), product)

        return (
            limit_maximum_purchase_price, limit_minimum_sales_price,
            limit_maximum_purchase_volume, limit_maximum_sales_volume
        )

    def act_for_interval(self, ts_from, ts_until, timestamp):
        duration = ts_until - ts_from
        duration_n_quarters = duration // COMMON.QUARTER

        if duration not in ALLOWED_BLOCK_DURATION:
            self.debug_log("duration {} not in allowed block durations: {}".format(duration, ALLOWED_BLOCK_DURATION))
            return

        # calculate the volume and price matrix from the scale data
        scale = self.build_scale_steering_matrix(ts_from, ts_until)
        if self.exchange.internal_id not in (COMMON.Exchange.epex, COMMON.Exchange.nordpool):
            raise NotImplementedError("This strategy does not support Exchange: {}".format(self.exchange.internal_id))

        all_range_products_raw = self.exchange.products.get_overlapping_with_timerange(ts_from - COMMON.QUARTER,
                                                                                       ts_until + COMMON.QUARTER)

        # all range products: all products to be considered for the calculation of traded amounts
        all_range_products = [p for p in all_range_products_raw
                              if p.delivery_end - p.delivery_start <= duration
                              ]

        before_products = [p for p in all_range_products if p.delivery_end <= ts_from]
        after_products = [p for p in all_range_products if p.delivery_start >= ts_until]
        all_range_products = [p for p in all_range_products
                              if ts_from <= p.delivery_start < p.delivery_end <= ts_until]

        # now take the traded amounts into account, and reduce the quantities in the scale by the traded amounts
        # the traded amounts:
        # - will then be considered for the tradeback positions
        # - the amounts are put into scales by quarter hours
        remaining_quantities_scale, traded_quantities = self.build_scale_remaining_matrix(all_range_products,
                                                                                          scale, ts_from,
                                                                                          ts_until)

        # maximum absolute order size of a slot in the orderbook. absolute value in MW
        maximum_order_book = abs(self.strategy_settings["maximum_order_book"] or DEFAULT_MAX_ORDER_BOOK_QUANTITY)
        trading_end_before_market_closure = (
            self.strategy_settings["trading_end_before_market_closure"] or 0
        ) * COMMON.MINUTE

        tradable_active_products = self.get_allowed_products(all_range_products, timestamp, self.delivery_areas[0])

        # get placement prices and positions according to behaviour
        # this will be additionally limited by ramp limits
        product_placement_dict = self.build_placement_for_products(
            tradable_active_products,
            remaining_quantities_scale,
            maximum_order_book,
            self.behavior,
            self.delivery_area_id,
            ts_from,
            ts_until,
            timestamp,
            trading_end_before_market_closure,
        )

        # now place the orders for buyback, don't forget to sort the items, they are unsorted!!
        a = range(ts_from, ts_until + COMMON.QUARTER, COMMON.QUARTER)
        intervals = list(zip(a[:-1], a[1:]))

        sell_limit_prices = [self.strategy_limit_minimum_sales_price.get(interval) for interval in intervals]
        buy_limit_prices = [self.strategy_limit_maximum_purchase_price.get(interval) for interval in intervals]

        if not sell_limit_prices or not buy_limit_prices:
            return

        n_sell_limit_prices = len(sell_limit_prices)
        n_buy_limit_prices = len(buy_limit_prices)
        n_traded_quantities = len(traded_quantities)

        if not (n_sell_limit_prices == n_buy_limit_prices == n_traded_quantities):
            raise FlexibilityStrategyError(
                "Length of limit sell prices (%d) and buy prices (%d) and length of traded quantities (%d) not equal" %
                (n_sell_limit_prices, n_buy_limit_prices, n_traded_quantities)
            )

        # get tradeback placement prices and positions according to behaviour
        # this will be additionally limited by ramp limits
        product_placement_dict_tradeback = self.build_tradeback_placement_for_products(
            tradable_active_products,
            traded_quantities,
            maximum_order_book,
            sell_limit_prices,
            buy_limit_prices,
            self.delivery_area_id,
            ts_from,
            timestamp,
            trading_end_before_market_closure
        )

        n_product_placement_dict = len(product_placement_dict)
        n_product_placement_dict_tradeback = len(product_placement_dict_tradeback)

        if n_product_placement_dict != n_product_placement_dict_tradeback:
            raise FlexibilityStrategyError(
                "Length of product placement dict (%d) and product_placement_dict_tradeback (%d) not equal" %
                (n_product_placement_dict, n_product_placement_dict_tradeback)
            )

        # RAMP Calculations
        # get quantity targets and current positions for ramp limits

        quantity_before = self.get_single_traded_quantity(before_products, ts_from - COMMON.QUARTER)
        quantity_after = self.get_single_traded_quantity(after_products, ts_until)

        target_positions = (
            [quantity_before[0] - quantity_before[1]]
            + [q[0] - q[1] for q in traded_quantities]
            + [quantity_after[0] - quantity_after[1]]
        )

        ramps = [
            RampElement(
                self.strategy_calc_ramp_buy_intraday.get((ts, ts + COMMON.QUARTER), RAMP_DEFAULT),
                self.strategy_calc_ramp_sell_intraday.get((ts, ts + COMMON.QUARTER), RAMP_DEFAULT)
            ) for ts in range(ts_from - COMMON.QUARTER, ts_until, COMMON.QUARTER)
        ]

        ts_before = ts_from - COMMON.QUARTER
        ramp_minmaxes = dict(
            (x * COMMON.QUARTER + ts_from,
             self.evaluate_ramp_minmaxes(
                 target_positions[x], target_positions[x + 1],
                 target_positions[x + 2], ramps[x], ramps[x + 1],
                 slots_before_buy=self.sent_slots[ts_before + x * COMMON.QUARTER][COMMON.Direction.buy],
                 slots_buy=self.sent_slots[ts_before + (x + 1) * COMMON.QUARTER][COMMON.Direction.buy],
                 slots_after_buy=self.sent_slots[ts_before + (x + 2) * COMMON.QUARTER][COMMON.Direction.buy],
                 slots_before_sell=self.sent_slots[ts_before + x * COMMON.QUARTER][COMMON.Direction.sell],
                 slots_sell=self.sent_slots[ts_before + (x + 1) * COMMON.QUARTER][COMMON.Direction.sell],
                 slots_after_sell=self.sent_slots[ts_before + (x + 2) * COMMON.QUARTER][COMMON.Direction.sell],
             ))
            for x in range(duration_n_quarters)
        )

        tradable_active_products.sort(key=lambda prod: prod.delivery_end - prod.delivery_start, reverse=True)

        # check the placement for all tradable active products
        for product in tradable_active_products:

            # public orderbook information to keep with order placement
            current_orderbook_indicators = product.orders.indicators(self.delivery_area_id)

            if current_orderbook_indicators:
                front_buy_price = current_orderbook_indicators[0].mw_prices[0][0]
                front_sell_price = current_orderbook_indicators[0].mw_prices[1][0]
                front_buy_qty = current_orderbook_indicators[0].eur_quantities[0][0]
                front_sell_qty = current_orderbook_indicators[0].eur_quantities[1][0]
                po_info = get_public_ob_info(front_buy_price, front_buy_qty, front_sell_price, front_sell_qty)
            else:
                po_info = PLACEMENT_PUBLIC_OB_EMPTY

            net_traded_in_timerange = target_positions[((product.delivery_start - ts_from) // COMMON.QUARTER) + 1]

            limit_buy_price, limit_sell_price, limit_buy_qty, limit_sell_qty = self.get_limit_ts_vals(product)

            # ramp limits based on positions (traded amounts) of current and nearby products
            # for longer products, take the minimum of first and last buy size
            product_ramp_max_buy_size = min(
                ramp_minmaxes[ts][0] for ts in range(product.delivery_start, product.delivery_end, COMMON.QUARTER)
            )
            product_ramp_max_sell_size = min(
                ramp_minmaxes[ts][1] for ts in range(product.delivery_start, product.delivery_end, COMMON.QUARTER)
            )

            block_log = ("Block: %s, rql: %s//%s, t: %s, po: %s" % (
                get_interval_description(ts_from, ts_until),
                product_ramp_max_buy_size, product_ramp_max_sell_size,
                traded_quantities, po_info
            ))
            self.debug_log(block_log, product)

            def safe_place_slots(slots):
                # type: (list[strategy.PositionSlot]) -> list[strategy.SlotResponse]
                slot_responses = []
                if product.state(self.delivery_area_id) != COMMON.DeliveryAreaState.active:
                    self.warn_log("Ignore placement on inactive area: {}".format(self.delivery_area_id), product)
                    return [strategy.SlotResponse(False, COMMON.SlotResponseAction.ignore,
                                                  COMMON.SlotResponseReason.inactive_area)] * len(slots)

                # check OMT before placement of any slot
                omt_info = ""
                if self.exchange.internal_id == COMMON.Exchange.epex:
                    relevant_omt = self.exchange.get_relevant_omt()
                    current_omt_l1_percent = relevant_omt.l1_percent
                    omt_info = PLACEMENT_INFO_OMT % (relevant_omt.current_level,
                                                     current_omt_l1_percent,
                                                     relevant_omt.limit_type)
                    if current_omt_l1_percent >= OMT_L1_PERCENT_LIMIT:
                        if self.omt_warn_log_counter % self.only_log_every_n_omt_warnings == 0:
                            self.warn_log(
                                "refuse order placement of slots due to"
                                " strategy OMT ({omt_type}) limit breach:"
                                " currently at {actual_omt}%,"
                                " limit set to {omt_limit}. Silenced for {n_silenced} same warnings.".format(
                                    omt_type=relevant_omt.limit_type,
                                    actual_omt=current_omt_l1_percent,
                                    omt_limit=OMT_L1_PERCENT_LIMIT,
                                    n_silenced=self.only_log_every_n_omt_warnings
                                ),
                                product
                            )
                            self.omt_warn_log_counter = 0
                        self.omt_warn_log_counter += 1
                        response_list = [
                            strategy.SlotResponse(
                                False,
                                COMMON.SlotResponseAction.ignore,
                                COMMON.SlotResponseReason.omt_too_high
                            )
                        ] * len(slots)
                        for slot in slots:
                            slot.info += omt_info  # omt placement info
                            slot.info += po_info  # public orderbook info
                        self.debug_log("placing slot on %s: %s" %
                                       (self.delivery_area_id,
                                        ", ".join("%s [r=%s]" % (slot.short(True, True), response)
                                                  for slot, response in zip(slots, response_list))),
                                       product)
                        return response_list

                # final quantity adjustments of all the slots
                for slot in slots:
                    slot.quantity = min(slot.quantity, maximum_order_book)

                    max_placed = max(
                        [self.sent_slots[ts][slot.direction] for ts in
                         range(product.delivery_start, product.delivery_end, COMMON.QUARTER)]
                    )

                    if slot.direction == COMMON.Direction.buy:
                        qty_limit = limit_buy_qty - net_traded_in_timerange - max_placed
                        qty, info = self.get_qty_with_reason(slot.quantity, qty_limit, maximum_order_book,
                                                             product_ramp_max_buy_size)
                    else:
                        qty_limit = limit_sell_qty + net_traded_in_timerange - max_placed
                        qty, info = self.get_qty_with_reason(slot.quantity, qty_limit, maximum_order_book,
                                                             product_ramp_max_sell_size)

                    slot.info += info  # quantity and price finding info
                    slot.info += omt_info  # omt placement info
                    slot.info += po_info  # public orderbook info
                    slot.quantity = max(qty, 0)
                    slot.quantity_range_lo = slot.quantity_range_hi = slot.quantity

                responses = self.place_slots(
                    {}, product, timestamp, self.delivery_area_id,
                    slots, [], limit_sell_price, limit_buy_price,
                    INTERNAL_EXECUTION_MODE
                )
                slot_responses.extend(responses)

                for slot, resp in zip(slots, slot_responses):
                    if not resp.succeeded:
                        continue
                    for ts in range(product.delivery_start, product.delivery_end, COMMON.QUARTER):
                        self.sent_slots[ts][slot.direction] += slot.quantity
                return slot_responses

            try:
                (
                    raw_buy_quantity, buy_amount, buy_price, buy_price_lower, buy_price_upper, raw_sell_quantity,
                    sell_amount, sell_price, sell_price_lower, sell_price_upper, placement_mode, seconds_left
                ) = product_placement_dict[product.product_id]
            except KeyError:
                # cancel all orders which are out on the market
                cancel_buy_price = min(limit_buy_price, 0)
                cancel_sell_price = max(limit_sell_price, 0)
                cancel_slots = [
                    strategy.PositionSlot(BUY_SLOTNAME, COMMON.Direction.buy, 0.,
                                          cancel_buy_price, info="CNCL"),
                    strategy.PositionSlot(SELL_SLOTNAME, COMMON.Direction.sell, 0.,
                                          cancel_sell_price, info="CNCL"),
                    strategy.PositionSlot(BUY_TRADEBACK_SLOTNAME, COMMON.Direction.buy, 0.,
                                          cancel_buy_price, info="CNCL"),
                    strategy.PositionSlot(SELL_TRADEBACK_SLOTNAME, COMMON.Direction.sell, 0.,
                                          cancel_sell_price, info="CNCL")
                ]
                safe_place_slots(cancel_slots)
                continue

            # take a break for that product because of a trade?
            if self.trade_action_locks_strategy(product, self.behavior, timestamp, seconds_left):
                continue  # do nothing

            # get left over depending on limits
            # net traded negative if already sold
            # example:
            # sell:
            # limit 2, sold 1
            # 2 + (-1) = 1
            # limit 2, bought 1
            # 2 + (+1) = 3
            buy_qty_until_limit = limit_buy_qty - net_traded_in_timerange
            sell_qty_until_limit = limit_sell_qty + net_traded_in_timerange

            # reduce amounts by periotheus limits
            order_buy_amount = max(min([buy_amount, buy_qty_until_limit]), 0)
            order_sell_amount = max(min([sell_amount, sell_qty_until_limit]), 0)

            # reduce amounts by ramp limits
            order_buy_amount = max(min([order_buy_amount, product_ramp_max_buy_size]), 0)
            order_sell_amount = max(min([order_sell_amount, product_ramp_max_sell_size]), 0)

            buy_slot = strategy.PositionSlot(
                BUY_SLOTNAME, COMMON.Direction.buy, rd(order_buy_amount), rd(buy_price),
                rd(buy_price_lower), rd(buy_price_upper),
                info=mk_stat(placement_mode, raw_buy_quantity, order_buy_amount)
            )

            sell_slot = strategy.PositionSlot(
                SELL_SLOTNAME, COMMON.Direction.sell, rd(order_sell_amount), rd(sell_price),
                rd(sell_price_lower), rd(sell_price_upper),
                info=mk_stat(placement_mode, raw_sell_quantity, order_sell_amount))

            tradeback_buy_amount, tradeback_buy_price, tradeback_sell_amount, tradeback_sell_price = \
                product_placement_dict_tradeback[product.product_id]

            tradeback_buy_amount_capped = min(tradeback_buy_amount, product_ramp_max_buy_size)
            tradeback_sell_amount_capped = min(tradeback_sell_amount, product_ramp_max_sell_size)

            buy_tb = strategy.PositionSlot(
                BUY_TRADEBACK_SLOTNAME, COMMON.Direction.buy,
                rd(tradeback_buy_amount_capped), rd(tradeback_buy_price),
                info=mk_stat(TRADEBACK_PLACEMENT_MODE, tradeback_buy_amount_capped, tradeback_buy_amount_capped)
            )

            sell_tb = strategy.PositionSlot(
                SELL_TRADEBACK_SLOTNAME, COMMON.Direction.sell,
                rd(tradeback_sell_amount_capped), rd(tradeback_sell_price),
                info=mk_stat(TRADEBACK_PLACEMENT_MODE, tradeback_sell_amount_capped, tradeback_sell_amount_capped)
            )

            safe_place_slots([buy_slot, sell_slot, buy_tb, sell_tb])

    def custom_act(self, log_data, timestamp, products=None):
        """Find intervals to act on, and place orders where necessary according to calculations

        :type log_data: list
        :type timestamp: float
        :type products: list[autotrader_core.exchange_trading.Product]
        """
        if not products:
            return

        # by default: get hourly intervals to run on, since we always look at 1h the same time
        # in addition for uk, allow longer products, such as 2h and 4h products
        intervals = self.products_to_intervals(self.exchange.products.get_active_products(self.delivery_area_id))

        # in test open orders cannot be tested.
        # in general, it is better to reserve the placed quantities with the placements
        # that went through onto the market
        # so only reset them once after all products have been processed.
        delivery_interval_start_ts = min(i[0] for i in intervals) if intervals else 0
        delivery_interval_end_ts = max(i[1] for i in intervals) if intervals else 0
        self.reset_placed_quantities_memory(delivery_interval_start_ts, delivery_interval_end_ts)

        # keep the intervals up to the latest product which has to be updated
        latest_delivery_end = max(p.delivery_end for p in products)
        intervals = (i for i in intervals if i[0] <= latest_delivery_end)

        # loop through the ordered intervals
        for interval in intervals:
            self.act_for_interval(*interval, timestamp=timestamp)

    def inactive_products_overlapping_interval(self, start_ts, end_ts):
        return (
            p for p in self.exchange.products.get_overlapping_with_timerange(start_ts, end_ts)
            if (p.state(self.delivery_area_id) != COMMON.DeliveryAreaState.active)
        )

    def reset_placed_quantities_memory(self, delivery_interval_start_ts, delivery_interval_end_ts):
        """Reset the memory of placed orders and adds orders currently placed on inactive products"""
        self.sent_slots.clear()
        self.sent_slots = self.get_placed_quantities_on_product(
            self.inactive_products_overlapping_interval(delivery_interval_start_ts, delivery_interval_end_ts),
            self.strategy_id,
            self.delivery_area_id
        )

    @staticmethod
    def get_placed_quantities_on_product(products, strategy_id, delivery_area_id):
        """Track placed orders on passed products"""
        placed_ordersizes = collections.defaultdict(lambda: {COMMON.Direction.buy: 0, COMMON.Direction.sell: 0})
        for product in products:
            own_orders = product.orders.get(
                delivery_area_id=delivery_area_id,
                order_filter=COMMON.OrderFilter.own,
                portfolio_key=strategy_id
            )
            pos_qty = sum(o.quantity for o in own_orders if o.direction == COMMON.Direction.buy)
            neg_qty = sum(o.quantity for o in own_orders if o.direction == COMMON.Direction.sell)
            for ts in range(product.delivery_start, product.delivery_end, COMMON.QUARTER):
                placed_ordersizes[ts][COMMON.Direction.buy] += pos_qty
                placed_ordersizes[ts][COMMON.Direction.sell] += neg_qty
        return placed_ordersizes

    def _calc_strategy_ramps(self):
        """Update intraday ramps to be used by the strategy to restrict trading in buy and sell direction"""

        # calculate the asymmetric ramps to be used for buy and sell
        self.strategy_calc_ramp_buy, self.strategy_calc_ramp_sell = self.calc_buy_sell_ramps(
            self.strategy_ramp_buy,
            self.strategy_ramp_sell,
            self.strategy_ramp,
            RAMP_DEFAULT,
        )

        # now calculate the used ramps based on the day ahead schedule of the previous day
        self.strategy_calc_used_ramp_before_intraday = self.calc_used_ramps(
            self.strategy_closed_positions_before_intraday
        )

        # final calculations to get correct ramps, taking used flexibilities traded before intraday into account
        self.strategy_calc_ramp_buy_intraday, self.strategy_calc_ramp_sell_intraday = self.calc_intraday_ramps(
            self.strategy_calc_ramp_buy, self.strategy_calc_ramp_sell, self.strategy_calc_used_ramp_before_intraday,
            RAMP_DEFAULT
        )

    def _set_ts(self, ts_name, ts_data, aggr_rule):
        """set timeseries of strategy, fail if strategy does not have an attribute as the timeseries name

        :param ts_name: name of the timeseries as transferred
        :type ts_name: str
        :param ts_data: timeseries list of dict data as transferred from periotheus
        :type ts_data: list[dict]
        :param aggr_rule: one of :class:`COMMON.AggregatorRule`
        :type aggr_rule: str
        :return: None
        """
        if not hasattr(self, ts_name):
            raise AttributeError("Flex Strategy does not have timeseries with name ", ts_name)
        setattr(self, ts_name, strategy.mk_strategy_tr_dict(ts_data, aggr_rule))

    def on_strategy_update(self, strategy_json):
        super(CustomStrategy, self).on_strategy_update(strategy_json)
        self.behavior = strategy_json[COMMON.StrategyJsonKey.behavior] or StrategyBehavior.balanced

        n_delivery_areas = len(self.delivery_areas)
        if n_delivery_areas != 1:
            raise FlexibilityStrategyError("Number of delivery areas > 1: {}".format(n_delivery_areas))
        self.delivery_area_id = self.delivery_areas[0]

        # regular timeseries reading
        for ts_name, aggr_rule in (
            (COMMON.StrategyJsonKey.TS.pos_sell, COMMON.AggregatorRule.min),
            (COMMON.StrategyJsonKey.TS.pos_buy, COMMON.AggregatorRule.min),
            (COMMON.StrategyJsonKey.TS.price_imm_buy, COMMON.AggregatorRule.min),
            (COMMON.StrategyJsonKey.TS.price_imm_sell, COMMON.AggregatorRule.max),
            (COMMON.StrategyJsonKey.TS.price_buy, COMMON.AggregatorRule.min),
            (COMMON.StrategyJsonKey.TS.price_sell, COMMON.AggregatorRule.max),
            (COMMON.StrategyJsonKey.TS.price_min_spread_buyback, COMMON.AggregatorRule.min_nonone),
        ):
            setattr(self, ts_name, strategy.mk_strategy_tr_dict(strategy_json.get(ts_name), aggr_rule))

        # userdefined timeseries to be read, including scales
        if COMMON.StrategyJsonKey.user_defined_timeseries in strategy_json:
            udf = strategy_json[COMMON.StrategyJsonKey.user_defined_timeseries]

            # the timeseries are only referenced here to make sure they exist and
            # for readability of the timeseries to be written to
            for ts_name, aggr_rule in (
                (COMMON.StrategyJsonKey.UDFTS.pos_closed, COMMON.AggregatorRule.max),
                (COMMON.StrategyJsonKey.UDFTS.ramp_buy, COMMON.AggregatorRule.max),
                (COMMON.StrategyJsonKey.UDFTS.ramp_sell, COMMON.AggregatorRule.max),
                (COMMON.StrategyJsonKey.UDFTS.ramp, COMMON.AggregatorRule.max),
                (COMMON.StrategyJsonKey.UDFTS.omt, COMMON.AggregatorRule.min),
            ):
                setattr(self, ts_name, strategy.mk_strategy_tr_dict(udf.get(ts_name), aggr_rule))

            for scale in range(1, MAX_NUMBER_SCALES + 1):
                scale_pos_sell = COMMON.StrategyJsonKey.UDFTS.pos_sell_scale.format(scale)
                scale_pos_buy = COMMON.StrategyJsonKey.UDFTS.pos_buy_scale.format(scale)
                scale_price_buy = COMMON.StrategyJsonKey.UDFTS.price_buy_scale.format(scale)
                scale_price_sell = COMMON.StrategyJsonKey.UDFTS.price_sell_scale.format(scale)

                setattr(self, scale_pos_sell,
                        strategy.mk_strategy_tr_dict(udf.get(scale_pos_sell), COMMON.AggregatorRule.min))
                setattr(self, scale_pos_buy,
                        strategy.mk_strategy_tr_dict(udf.get(scale_pos_buy), COMMON.AggregatorRule.min))
                setattr(self, scale_price_buy,
                        strategy.mk_strategy_tr_dict(udf.get(scale_price_buy), COMMON.AggregatorRule.min))
                setattr(self, scale_price_sell,
                        strategy.mk_strategy_tr_dict(udf.get(scale_price_sell), COMMON.AggregatorRule.max))

        # calculate intraday ramps from received ramp timeseries
        # this will take into account asymmetric ramps and day ahead traded values, to get the right ramps for the day
        self._calc_strategy_ramps()

        # export some timeseries to mongo for analysis
        self._export_timeseries()

    def _export_timeseries(self):
        """Export Position and Intraday Buy and Sell Ramps to MongoDB for analysis"""

        def mk_ts_exp(ts):
            return dict((ts_from, value) for (ts_from, ts_to), value in ts.items() if
                        ts_to - ts_from == COMMON.QUARTER) if ts else {}

        self.api_export_timeseries(
            {
                "pos_long": (
                    "Position Long", "MW", "MW", COMMON.QUARTER,
                    mk_ts_exp(self.strategy_position_tradable_position_long)
                ),
                "pos_short": (
                    "Position Short", "MW", "MW", COMMON.QUARTER,
                    mk_ts_exp(self.strategy_position_tradable_position_short)
                ),
                "strategy_calc_ramp_buy_intraday": (
                    "Intraday Ramp Buy (Calculated)", "MW", "MW", COMMON.QUARTER,
                    mk_ts_exp(self.strategy_calc_ramp_buy_intraday)
                ),
                "strategy_calc_ramp_sell_intraday": (
                    "Intraday Ramp Sell (Calculated)", "MW", "MW", COMMON.QUARTER,
                    mk_ts_exp(self.strategy_calc_ramp_sell_intraday)
                ),
            }
        )

    def custom_on_order_book_update(self, orders, timestamp):
        """React only to public orders, and not own orders

        We also filter for orderbook updates, which are within the orderbook depth that
        can have an effect on order placement
        """

        check = {
            COMMON.Direction.buy:
                lambda order_price, indicator:
                    (indicator.mw_prices[0][MAX_ORDERBOOK_DEPTH_IDX] is None)
                    or (order_price >= indicator.mw_prices[0][MAX_ORDERBOOK_DEPTH_IDX]),
            COMMON.Direction.sell:
                lambda order_price, indicator:
                    (indicator.mw_prices[1][MAX_ORDERBOOK_DEPTH_IDX] is None)
                    or (order_price <= indicator.mw_prices[1][MAX_ORDERBOOK_DEPTH_IDX]),
        }

        relevant_orders = [
            o for o in orders if
            o.product.orders.indicators(o.delivery_area_id)
            and check[o.direction](o.price, o.product.orders.indicators(o.delivery_area_id)[0])
        ]

        order_ids_by_product = [
            a[0] for a in list(itertools.chain.from_iterable(
                o.product.orders.get_own_order_ids(o.delivery_area_id, o.direction) for o in relevant_orders))
        ]

        # 'if getattr(o, "order_id", None)' can filter out own orders, as they may not have an order id attribute
        products = set(o.product for o in relevant_orders if getattr(o, "order_id", None) not in order_ids_by_product)

        if products:
            self.act(timestamp, products)

    def custom_on_trade_update(self, trades, timestamp):
        self.act(timestamp, set(o.product for o in trades))

    def custom_on_products_queue(self, products, timestamp):
        self.act(timestamp, products)
