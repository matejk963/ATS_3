#!/usr/bin/python3
# -*- coding: utf-8 -*-
from __future__ import absolute_import
import bisect
import collections
import itertools
import logging
import math
import random
from collections import defaultdict

import autotrader_core._strategy_datastructures as STRATDATA
import autotrader_core.api as api
import autotrader_lib.common as COMMON
import autotrader_core.strategy as strategy
import autotrader_lib.cet_util as CETUTIL
import autotrader_lib.py2_funcs as PY2LIB
from autotrader_lib.common import (DeliveryAreaState, Direction)
from autotrader_core.strategy import PositionSlot
import autotrader_lib.util as ALU  # noqa - typehints
from six.moves import range


log = logging.getLogger('autotrader.position_closing_strategy')


# defines what a deep price in the orderbook means, in 5 MW steps (1 = 5 MW, 4 = 20 MW inside of the order book)
DEEP_FRONT_POSITION = 4
# defines front price in 5 MW steps (0 = best ask or bid)
FRONT_PRICE_POSITION = 0
# when placing an order at the top of the orderbook, place it x € in front of the current best order
FRONT_PRICE_SHIFT = -0.1
# positions for replacement tolerances, positions in 5 MW steps, price shifts in €
FRONT_PRICE_LOWER_POSITION = 0
FRONT_PRICE_LOWER_SHIFT = -0.3
FRONT_PRICE_UPPER_POSITION = 1
FRONT_PRICE_UPPER_SHIFT = 0.0

# GRACE PERIOD SETTINGS

# milder trading mode since last change in seconds for grace (normal mode)
GRACE_PERIOD_DURATION = 600  # 20% used if short grace period is configured
# limit at how many seconds left to trade the grace period is deactivated to enable more aggressive trading
GRACE_PERIOD_DURATION_STOP_BEFORE_END = 300  # double this value is used if short grace period is configured
# extended milder trading mode since last change in seconds for grace
EXTENDED_GRACE_PERIOD_DURATION = 1200  # 20% used if short grace period is configured
# extended limit at how many seconds left to trade the grace period is deactivated to enable more aggressive trading
EXTENDED_GRACE_PERIOD_DURATION_STOP_BEFORE_END = 600  # double this value is used if short grace period is configured

# PLACEMENT PARAMETERS TO REDUCE NUMBER OF ORDER UPDATES DEEP IN OWN ORDERBOOK
MAX_OWN_DEPTH_ORDER_PLACEMENT_ABS_EURO = 2  # absolute euros behind front on own order side
MAX_OWN_DEPTH_ORDER_PLACEMENT_RELATIVE_EURO = 0.05  # relative price behind front own order price

# PLACEMENT MODE BY PERCENTAGES OF OMT LIMITS
OMT_FORCE = 70
OMT_BRUTE = 90
OMT_FORCE_BOOST = 80

# Start slot size increase at this OMT
OMT_SHIFT_SIZES = 30

OmtPriceTolerance = collections.namedtuple("OmtPriceTolerance", ["omt", "price_tolerance"])

# Scaling Price Tolerance Range with OMT
# read: until ... OMT is reached, add TOLERANCE ... to the higher and lower price limit
# Example: OmtPriceTolerance(10, 0) -> until OMT 10 is reached, add 0 to the both ends of the price tolerance range
OMT_TOLERANCE_STEPS = (
    OmtPriceTolerance(10, 0),
    OmtPriceTolerance(15, 0.03),
    OmtPriceTolerance(20, 0.05),
    OmtPriceTolerance(25, 0.10),
    OmtPriceTolerance(30, 0.20),
    OmtPriceTolerance(40, 0.40),
    OmtPriceTolerance(50, 0.50),
    OmtPriceTolerance(OMT_FORCE, 1),
    OmtPriceTolerance(OMT_FORCE_BOOST, 2),
    OmtPriceTolerance(OMT_BRUTE - 1, 3),
)

# Internal execution mode, used with every place slots
INTERNAL_EXECUTION_MODE = COMMON.InternalExecutionMode.default

# same for immediate execution (place where the aggression order is put)
DUMP_PRICE_POSITION = 0
# negative shift means worse price, the quantity is dumped on the other side of the orderbook
DUMP_PRICE_SHIFT = -0.5

# standard value defining when the position closer closes all the remaining quantities by aggressing
DUMP_IN_LAST_SECONDS = 60

# fill value used in definition of placement curve below
no_value = 0.1

# default value for trading start before delivery in minutes
TRADING_END_BEFORE_DELIVERY_MINUTES = 0
TRADING_START_BEFORE_DELIVERY_MINUTES = 3 * 60  # This is 3H, not 3 minutes. Do not replace with COMMON.MINUTE

# close position in final N minutes. set target volume to 100% in the last n minutes before end of trading window
CLOSE_IN_LAST_N_MIN = 5

# default allowed imbalance (i.e. position deviation) on product at market close
DEFAULT_MAXIMUM_IMBALANCE_ON_MARKET_CLOSURE = 0.

# default allowed maximum order book size in MW
DEFAULT_MAXIMUM_ORDER_BOOK = 1000.


def timestamp_log(timestamp, extended=False):
    # type: (float | int, bool) -> str
    """Convert utc timestamp to cet string"""
    return CETUTIL.utc_ts2cet_str(timestamp, extended, True)


class TradeIndex(object):
    """TradeIndex is a helper struct that keeps key information of trading for a certain period of time"""
    def __init__(self, volume, avg_price, min_price, max_price):
        self.volume = volume
        self.avg_price = avg_price
        self.min_price = min_price
        self.max_price = max_price


class ProductVolumeFactor(object):
    """ProductVolumeFactor is instanced and used in order to get a current trading factor based on
    a curve and the remaining time for trading"""
    risk_affinity = None
    price_development = None
    initialized = False

    def __init__(self, trading_start_before, risk_affinity, price_development, delivery_start,
                 trading_end_before, check_exchange_timestamp_halt, use_fixed_random_seed=False, use_random=True):
        # type: (float, float, float, float, float, type(abs), bool, bool) -> ()
        """
        initialize object for a specific parameter set. Lots of the calculations are done here,
        in order to reduce the load on the get_factor function.

        :param trading_start_before: number of minutes before gate closure, when the trading will start
        :type trading_start_before: float
        :param risk_affinity: value between 0 and 1, defining the effect of the price prediction
        :type risk_affinity: float
        :param price_development: value between -1 and 1 that defines the expected price movements from falling
            to rising
        :type price_development: float
        :param delivery_start: ts when delivery starts
        :type delivery_start: float
        :param trading_end_before: number of minutes before gate closure, when the trading will end
        :type trading_end_before: float
        :param check_exchange_timestamp_halt: a function that checks if a timestamp lies within an expected
            halt of the exchange and shifts the timestamp to the beginning of the halt if it does
        :type check_exchange_timestamp_halt: function
        :param use_fixed_random_seed: switch for simulations. Many values are randomized. For testing, a fixed seed is
            favourable.
        :type use_fixed_random_seed: bool
        :param use_random: switch for simulations. Enable training of random to check curve values.
        :type use_random: bool
        """
        # check definition list
        local_random = random.Random(1 if use_fixed_random_seed else None)
        self.rand1 = local_random.uniform(0.9, 1.1) if use_random else 1
        self.rand2 = local_random.uniform(0.9, 1.1) if use_random else 1

        self.set_price_development_risk_affinity(price_development, risk_affinity)
        self.delivery_start = delivery_start

        # make last 2 minutes "closing" minutes with a factor of 1.
        self.end_trading_activity_at = int(delivery_start - 60 * trading_end_before)
        self.start_trading_activity_at = int(delivery_start - 60 * trading_start_before)

        # this method returns the starting timestamp of a halt that a given timestamp is within,
        # if there is a halt at that time
        self.check_exchange_timestamp_halt = check_exchange_timestamp_halt

        # if the trading end is in a halt, try to close the position before that
        timestamp_check_halt = check_exchange_timestamp_halt(self.end_trading_activity_at)
        if timestamp_check_halt:
            halt_start_ts = timestamp_check_halt[0]
            self.end_trading_activity_at = halt_start_ts

        # full position should be reached and kept in the last minutes of trading anyway
        self.reach_full_at = self.end_trading_activity_at - CLOSE_IN_LAST_N_MIN * COMMON.MINUTE

        self.initialized = True

    def set_price_development_risk_affinity(self, price_development, risk_affinity):
        if isinstance(risk_affinity, list):  # For TestWithOrderBookEPEX.test Python3 compatibility
            self.risk_affinity = self.rand1
        else:
            self.risk_affinity = PY2LIB.py2max([PY2LIB.py2min([risk_affinity, 1.]), 0.]) * self.rand1
        self.price_development = PY2LIB.py2max([PY2LIB.py2min([price_development, 1.]), -1.]) * self.rand2

    def curve_formula(self, rate):
        """y = x ^ (10 ^ (price_development * risk_affinity * 2))

        :param rate: percentage of tradable duration which has passed. Between 0 (start) and 1 (finish)
        :type rate: float
        :return: factor
        :rtype: float
        """
        return min(max(rate ** (10 ** (self.price_development * self.risk_affinity * 2)), 0), 1)

    def get_factor(self, timestamp):
        # type: (float) -> float
        """get_factor returns a factor between 0 and 1 for a given timestamp

        :param timestamp: timestamp
        :type timestamp: float
        :return: a factor between 0 and 1 for a given timestamp
        :rtype: float
        """
        if (
            not self.initialized
            or self.check_exchange_timestamp_halt(timestamp)
            or self.start_trading_activity_at > timestamp
        ):
            return 0.
        elif self.end_trading_activity_at > timestamp > self.reach_full_at:
            return 1.
        elif timestamp > self.end_trading_activity_at:
            return 0.

        # find timestamp in list
        duration = self.reach_full_at - self.start_trading_activity_at
        since_start = float(timestamp - self.start_trading_activity_at)  # always go to end of quarter
        if duration < 1:
            return 0.
        # rate is the percentage of passed tradable time.
        # if the trading window is 3h long (e.g. trading start 4h before delivery, trading end 1h before delivery)
        # and 1h has passed, then rate is 0.33
        return self.curve_formula(rate=max(min(round(since_start / duration, 2), 1), 0))


class ProductVolumeFactorContainer(object):
    """ProductVolumeFactorContainer provides a caching mechanism for ProductVolumeFactor objects"""

    def __init__(self, strategy_settings, check_exchange_timestamp_halt, direction,
                 use_fixed_random_seed=False):
        """
        Lots of the calculations are done here, in order to reduce the load on the get_factor function.

        :param strategy_settings: global strategy input dict containing the complete setup information
        :type strategy_settings: dict
        :param check_exchange_timestamp_halt: a function that checks if a timestamp lies within an expected
            halt of the exchange and shifts the timestamp to the beginning of the halt if it does
        :type check_exchange_timestamp_halt: function
        :param direction: value of type Direction, Direction.buy or Direction.sell
        :type direction: str
        :param use_fixed_random_seed: switch for simulations. Many values are randomized. For testing, a fixed seed is
            favourable.
        :type use_fixed_random_seed: bool
        """
        self.pvf = dict()
        self.strategy_settings = strategy_settings
        self.check_exchange_timestamp_halt = check_exchange_timestamp_halt
        self.direction = direction
        self.use_fixed_random_seed = use_fixed_random_seed

    def get_factor(self, delivery_start_ts, timestamp, end_trading_activity_at):
        # type: (float, float, float) -> float
        """get_factor returns a factor between 0 and 1 for a given delivery quarter, timestamp and trade end

        :param delivery_start_ts: timestamp determining the delivery start of a quarter hour
        :type delivery_start_ts: float
        :param timestamp: timestamp of current time
        :type timestamp: float
        :param end_trading_activity_at: timestamp where trading for the delivery ends
        :type end_trading_activity_at: float
        :return: a factor between 0 and 1 for a given timestamp
        :rtype: float
        """
        # get risk affinity from strategy
        risk_affinity = self.strategy_settings["risk_affinity"] or 0.

        # get price expectation from strategy
        ptr = [
            x["value"] or 0.
            for x in self.strategy_settings[COMMON.StrategyJsonKey.TS.price_forecast_trend]
            if delivery_start_ts == x["begin"]
        ]
        price_development = sum(ptr) / len(ptr) if ptr else 0.

        if self.direction == Direction.buy:
            price_development *= -1

        if delivery_start_ts not in self.pvf:
            # get trading start hours, counting back from Gate Closure time
            # 180.0 default value is set in Strategy.on_strategy_update(), but until it's not executed first (None),
            # or it's 0, we need the default value here as well, not to divide by false value in scaling
            trading_end_before_market_closure_sec = float(delivery_start_ts - end_trading_activity_at)
            trading_end_before_market_closure = trading_end_before_market_closure_sec / COMMON.MINUTE

            # if trading start is set to 0 (which equals delivery start) still the default value will be taken.
            trading_start = self.strategy_settings.get("trading_start") or TRADING_START_BEFORE_DELIVERY_MINUTES

            # create and store the calculation object in the cache
            self.pvf[delivery_start_ts] = ProductVolumeFactor(
                trading_start, risk_affinity, price_development, delivery_start_ts,
                trading_end_before_market_closure, self.check_exchange_timestamp_halt, self.use_fixed_random_seed)

        # set the current price development and risk affinity
        self.pvf[delivery_start_ts].set_price_development_risk_affinity(
            price_development, risk_affinity
        )

        return self.pvf[delivery_start_ts].get_factor(timestamp)


class PositionDeviationHandler(object):
    """Retrieves standard deviation for position for timestamp X"""

    def __init__(self, strategy_settings):
        # type: (dict) -> ()
        """
        Initialize and fill standard deviation dict from set values of TS strategy_position_deviation.

        :param strategy_settings: global strategy input dict containing the complete setup information
        :type strategy_settings: dict
        """
        self.deviation_dict = dict()
        for e in strategy_settings[COMMON.StrategyJsonKey.TS.pos_dev]:
            if e["value"] is not None:
                # remember standard deviation for a timestamp
                self.deviation_dict[e["begin"]] = e["value"]

    def get_stddev(self, position_start):
        # type: (float) -> float
        """Gets std deviation for given timestamp.

        :param position_start: timestamp determining the deliver start of a quarter hour
        :type position_start: float
        :return: standard deviation for timestamp
        :rtype: float
        """
        if position_start in self.deviation_dict:
            return self.deviation_dict[position_start]
        return 0.


class OrderVolumeCalculator(object):
    """OrderVolumeCalculator provides an interface that returns order size recommendations for the current trading
    situation"""

    # preferably, orders should only have those sizes in order to mimic manual trading behaviour
    # we add additional elements to account for higher slot sizes due to increased OMT numbers
    slot_size_categories = (0.2, 0.5, 1., 2., 5., 10., 20., 50., 100., 500., 1000., 10000.)

    def __init__(self, maximum_imbalance_on_market_closure=None, maximum_order_book=None):
        """Initialize and set maximums.

        :param maximum_imbalance_on_market_closure: is a tolerance setting for rare cases when an algo overshoots
        :type maximum_imbalance_on_market_closure: float
        :type maximum_order_book: float
        """

        if maximum_imbalance_on_market_closure is None:
            maximum_imbalance_on_market_closure = DEFAULT_MAXIMUM_IMBALANCE_ON_MARKET_CLOSURE
        self.maximum_imbalance_on_market_closure = maximum_imbalance_on_market_closure

        if maximum_order_book is None:
            maximum_order_book = DEFAULT_MAXIMUM_ORDER_BOOK
        self.maximum_order_book = abs(maximum_order_book)

    @staticmethod
    def round_order_volume(maximum_order_exposure, order_volume, slot_size):
        # type: (float, float, float) -> float
        """Rounds quantity to slot size packet.

        :param maximum_order_exposure: current overall open position
        :type maximum_order_exposure: float
        :param order_volume: current volume to be placed on the market
        :type order_volume: float
        :param slot_size: target packet size of orders
        :type slot_size: float
        :return: a rounded quantity
        :rtype: float
        """
        if 0. in (order_volume, slot_size):
            return 0.

        if abs(maximum_order_exposure) < slot_size:
            # remaining quantity smaller than packet -> take remaining quantity
            order_volume_rounded = maximum_order_exposure
        else:
            # round to packet size
            order_volume_rounded = int((order_volume + 0.5 * slot_size) // slot_size) * slot_size

        if abs(order_volume_rounded) > abs(maximum_order_exposure):
            # if volume smaller than overall position, use overall position
            order_volume_rounded = maximum_order_exposure
        return order_volume_rounded

    def shrink_slot_size(self, slot_size, ratio):
        # type: (float, float) -> float
        """shrink_slot_size is a helper function that scales down a given size of order packets by a ratio.
        It's being used for determining the slot size of sub-products (e.g. global slot size calculated with
        position, part of it traded in hourly product, rest in quarterly - the quarterly placement has to have
        smaller packets.

        :param slot_size: previous slot size
        :type slot_size: float
        :param ratio: downsizing ratio
        :type ratio: float
        :return: smaller, scaled packet size
        :rtype: float
        """
        shrunk_slot_size = slot_size * ratio * 0.7
        for category in self.slot_size_categories:
            if shrunk_slot_size <= category:
                return category

    def calculate_exposures(self, position, traded, stddev, factor, global_position=0, global_traded=0, omt_percent=0.):
        # type: (float, float, float, float, float, float, float) -> (float, float, float, float, float)
        """handles slot size calculation, maximum exposure calculation and standard deviation for subsequent functions

        :param position: positive or negative, the balance to be traded
        :type position: float
        :param traded: amount already traded (positive or negative)
        :type traded: float
        :param stddev: allowed deviation value for that interval of time
        :type stddev: float
        :param factor: 0 ... 1, the current trading factor following the trading curve set in the strategy
                        starting with 0 at the opening of the product, ending at 1 at trading closure
        :type factor: float
        :param global_position: only used by spontaneous position closer - non-local balance for quarter hour
        :type global_position: float
        :param global_traded: only used by spontaneous position closer - non-local traded quantity for quarter hour
        :type global_traded: float
        :param omt_percent: 1 .. 100, current omt percentage
        :type omt_percent: float
        :return: maximum_order_exposure, traded, slot_size, use_maximum_order_book, factor
        :rtype: (float, float, float, float, float)
        """
        # stddev must not be less that 0
        stddev = max(0., stddev)
        # factor must be 0 ... 1
        factor = min(max(0., factor), 1.)
        # slot_size: maximum order size based on position and traded quantity
        raw_slot_size = max(abs(global_position), abs(global_traded), abs(position), abs(traded),
                            abs(position - traded)) / 18.

        # shift is responsible to increase the minimum slot size
        shift = 0
        if omt_percent > OMT_SHIFT_SIZES:
            shift = int((omt_percent - OMT_SHIFT_SIZES) // 10) + 1

        # now let's see how we can round the slot size
        slot_size = None
        for category in self.slot_size_categories:
            if raw_slot_size <= category:
                slot_size = category
                break

        slot_size *= max(1, shift)

        if not slot_size:
            raise Exception("slot size far too big")
        if slot_size >= self.maximum_order_book:
            slot_size = self.maximum_order_book

        # the deviation is scaled with the inverse factor, so that at the beginning of the trading
        # we take 100% of the deviation in account and at the end of the trading
        # the algorithms is able to exactly match the given quantity
        stddev_factor = stddev * (1 - factor)

        # boundaries for the current target position hi and low
        pos_lo = position - stddev_factor
        pos_hi = position + stddev_factor

        if pos_lo <= traded <= pos_hi:
            # within stddev interval, no direct action is taken here
            # so the order volume is 0.
            maximum_order_exposure = 0.
        elif traded <= pos_lo:
            maximum_order_exposure = pos_lo - traded
        else:
            maximum_order_exposure = pos_hi - traded

        # maximum_order_exposure ... maximum amount that is allowed to be placed
        # traded ... traded quantity
        # slot size ... recommended order size
        # use_maximum_order_book ... pass-through, setting from config
        # factor ... pass-through, current trading factor
        return maximum_order_exposure, traded, slot_size, self.maximum_order_book, factor

    def prepare_order_volumes(self, maximum_order_exposure, traded, use_maximum_order_book, slot_size, factor):
        # type: (float, float, float, float, float) -> (float, float)
        """Determines order size based on factor and quantity input.

        :param maximum_order_exposure: maximum amount that is allowed to be placed
        :type maximum_order_exposure: float
        :param traded: traded quantity
        :type traded: float
        :param use_maximum_order_book: setting from config, maximal order size recommendation
        :type use_maximum_order_book: float
        :param slot_size: recommended order size
        :type slot_size: float
        :param factor: 0 ... 1, the current trading factor following the trading curve set in the strategy
                        starting with 0 at the opening of the product, ending at 1 at trading closure
        :type factor: float
        :return: order_volume_rounded, order_volume
        :rtype: (float, float)
        """

        # compare the target factor and where trading is currently
        try:
            actual_factor = traded / (traded + maximum_order_exposure)
        except ZeroDivisionError:
            actual_factor = 2.

        factor_ahead = factor - actual_factor

        if actual_factor <= 1 and factor_ahead < 0.:
            # nothing to be done, we're well ahead in trading
            return 0., 0.

        if actual_factor > 1:
            # trade back, order volume is calculated from factor and excess of position
            order_volume = math.copysign(min(abs(maximum_order_exposure), 3 * slot_size), maximum_order_exposure)
        else:
            try:
                order_volume = maximum_order_exposure * (factor_ahead / (1 - actual_factor))
            except ZeroDivisionError:
                order_volume = 0.

        if abs(maximum_order_exposure) > use_maximum_order_book:
            # cap at maximum order book size
            maximum_order_exposure = math.copysign(use_maximum_order_book, maximum_order_exposure)

        # round total quantity to be traded to 0.1 MW
        maximum_order_exposure = round(maximum_order_exposure, 1)

        # round to slot packet size
        order_volume_rounded = self.round_order_volume(maximum_order_exposure, order_volume, slot_size)
        return order_volume_rounded, order_volume


class PriceCurveContainer(object):
    """PriceCurveContainer provides a cached calculation of linear price developments in discrete steps
    for the low liquidity mode of the PositionCloser"""

    def __init__(self, debug_log=None):
        self.price_curves = dict()  # product_id -> curve
        self.price_starts = dict()  # product_id -> factor_start
        # fixed random seed again for simulation and testing purposes
        self.use_fixed_random_seed = False  # Can be changed in on_strategy_update
        self.debug_log = debug_log or log.debug

    def clean_up(self, product_id):
        """
        Remove the given products from the cached curves.

        This is needed to avoid a memory leak

        :param product_id: The id of the product for which all cached data should be deleted.
        :type product_id: str
        """
        self.price_curves.pop(product_id, None)
        self.price_starts.pop(product_id, None)

    def get_price(self, product_id, start_price, end_price, factor):
        # type: (str, float, float, float) -> (float or None)
        """Get a price recommendation for the current timestamp, given a linear development between start and end price.

        :param product_id: product id we're looking at, used for caching
        :type product_id: str
        :param start_price: starting price for the development
        :type start_price: float
        :param end_price: ending price for the development
        :type end_price: float
        :param factor: 0 ... 1, the current pricing factor starting with 0, ending at 1.
                       This is not the trading quantity factor!
        :type factor: float
        :return: price
        :rtype: float or None
        """
        if None in (start_price, end_price):
            return None
        if product_id in self.price_curves:
            # caching case, retrieve the intervals lists for the calculation
            curve = self.price_curves[product_id]
            starts = self.price_starts[product_id]
            num_elements = len(curve)
        else:
            # again, never use global random functions because of threads
            local_random = random.Random(1 if self.use_fixed_random_seed else None)
            # randomize number of steps
            num_elements = 30 if self.use_fixed_random_seed else local_random.randint(26, 35)
            # generate num_elements intervals between prices with randomized price steps
            # The curve holds factors between 0 and 1 indicating how far between the two prices we are
            # with 0 meaning start_price and 1 meaning end_price
            curve = [0]
            for idx in range(num_elements - 1):
                curve.append(local_random.uniform(0.4, 1.6) + curve[-1])
            # normalize
            curve = [i / curve[-1] for i in curve]
            # generate list of step lengths, also randomized
            starts = [(idx + local_random.uniform(-0.3, 0.3)) / float(num_elements) for idx in range(num_elements)]
            self.price_starts[product_id] = starts
            self.price_curves[product_id] = curve
            self.debug_log("Created random price curve for product {}: "
                           "interval starts: {}, prices: {}".format(product_id, starts, curve))
        # determine current position in the interval lists and retrieve factor of interval
        factor_shift = 1. / num_elements
        curve_index = bisect.bisect_left(starts, factor - factor_shift)
        curve_index = max(0, min(curve_index, num_elements - 1))
        curve_factor = curve[curve_index]
        # return the interpolation between the prices given the step factor
        return round(start_price * (1. - curve_factor) + end_price * curve_factor, 2)


class LiquidityMeasurementContainer(object):
    """LiquidityMeasurementContainer provides a stateful interface to answer the question, if the low liquidity mode
    should apply to the current product"""
    def __init__(self, llq1_ind, llq1_limit, llq2_ind, llq2_limit, debug_log=None):
        self.switch_to_lo_ts = dict()  # product_id -> last timestamp that we switched to lo. None == hi liquidity mode
        self.llq1_ind = llq1_ind
        self.llq1_limit = llq1_limit
        self.llq2_ind = llq2_ind
        self.llq2_limit = llq2_limit
        self.debug_log = debug_log or log.debug
        self.spread_info = ""

    def use_lo_liquidity(self, product_id, area, mw_prices, timestamp):
        """Check if we shall use low liquidity mode.

        :param product_id: product id we're looking at, used for caching
        :type product_id: string
        :param area: area of trading
        :type area: string
        :param mw_prices: object from the order book indicators, mw_prices[0][0] is best bid, mw_prices[1][0] best ask
        :type mw_prices: List
        :param timestamp: current time
        :type timestamp: float
        :return: if low liquidity mode shall be used
        :rtype: bool
        """
        try:
            # render the distance between the first 10 MW and the first 100 MW in the order book - between sell and buy
            spread_size_shallow = mw_prices[1][self.llq1_ind] - mw_prices[0][self.llq1_ind]
            spread_size_deep = mw_prices[1][self.llq2_ind] - mw_prices[0][self.llq2_ind]
        except (TypeError, IndexError):
            spread_size_shallow, spread_size_deep = None, None
        self.spread_info = "spreads %s MW: %s, %s MW: %s" % (
            self.llq1_ind * 5 if self.llq1_ind is not None else None,
            spread_size_shallow,
            self.llq2_ind * 5 if self.llq2_ind is not None else None,
            spread_size_deep
        )
        # get timestamp of last switch, a switch shall only happen less than once per minute
        last_switch = self.switch_to_lo_ts.get(product_id, None)
        # only for these areas ...
        if area in (COMMON.Area.nl, COMMON.Area.uk, COMMON.Area.ee):
            if last_switch and last_switch + 60 > timestamp:
                # we have to stay in this mode for at least 60 seconds in order to avoid flapping behaviour
                return True
            if None in (spread_size_shallow, spread_size_deep):
                # almost empty order book
                lo_liquidity = True
            else:
                # wide spreads
                lo_liquidity = spread_size_shallow > self.llq1_limit or spread_size_deep > self.llq2_limit
            if not lo_liquidity and last_switch:
                self.switch_to_lo_ts[product_id] = None
            if lo_liquidity and not last_switch:
                # remember that we just switched to lo
                self.switch_to_lo_ts[product_id] = timestamp
            return lo_liquidity
        else:
            return False


class StrategyBehavior(object):
    """defines the 3 strategy modes that can be selected in the GUI"""
    balanced = "BALANCED"
    safe = "SAFE_CLOSURE"
    unsafe = "UNSAFE_CLOSURE"


class PlacementMode(object):
    """Available placement modes, depending on OMT, urgency, pricing, liquidity"""
    end = "end"
    bruteforce = "bruteforce"
    force_boosted_grace = "force_boosted_grace"
    force_boosted = "force_boosted"
    force_grace = "force_grace"
    force = "force"
    std_grace = "std_grace"
    std = "std"
    ivest = "ivest"
    lolq = "lolq"
    omt90 = "omt90/bruteforce"
    omt80 = "omt80/force_boosted"
    omt70 = "omt70/force"


class GraceMode(object):
    no_grace_period = "no_grace_period"
    short_grace_period = "short_grace_period"
    normal_grace_period = "normal_grace_period"


class PositionSlotGenerator(object):
    """PositionSlotGenerator provides an interface for determining the actual order properties for the placement"""
    def __init__(self, strategy_settings, use_grace_mode=True, omt_steps_settings=OMT_TOLERANCE_STEPS):
        self.behavior = strategy_settings["behavior"]
        self.grace_mode = strategy_settings.get(COMMON.StrategyJsonKey.grace_period_mode,
                                                GraceMode.normal_grace_period)
        # grace mode is only used in standard position closer, but not if disabelled
        if self.grace_mode == GraceMode.no_grace_period:
            self.use_grace_mode = False
        else:
            self.use_grace_mode = use_grace_mode

        if self.use_grace_mode:
            log.debug("PositionSlotGenerator initialized with grace mode enabled (grace_mode_setting=%s)",
                      self.grace_mode)
        else:
            log.debug("PositionSlotGenerator initialized without grace mode")
        self.omt_steps_settings = omt_steps_settings

    @staticmethod
    def get_pricetolerance_by_omt(current_omt_percent, omt_steps_settings):
        for omt, pricestep in omt_steps_settings:
            if current_omt_percent <= omt:
                return pricestep
        return 0

    def get_slots(
            self,
            indicators,  # type: list
            seconds_left,  # type: float
            purchase_immediate_vesting_price,  # type: float
            sales_immediate_vesting_price,  # type: float
            low_liquidity_purchase_price,  # type: float
            low_liquidity_sales_price,  # type: float
            order_volume,  # type: float
            maximum_order_exposure,  # type: float
            slot_size,  # type: float
            raw_order_volume,  # type: float
            duration_from_last_change_to_now,  # type: float
            trading_indices,  # type: list
            spread_indicator,  # type: float
            lo_liquidity,  # type: bool
            omt_percent,  # type: int
    ):  # type: (...) -> (str, str, list)
        """get concrete order placement for current trading situation

        :param indicators: order book indicators list, containing order book statistics history
        :type indicators: :class:`autotrader_core.exchange_trading.OrderBookIndicators`
        :param seconds_left: seconds left to trade
        :type seconds_left: float
        :param purchase_immediate_vesting_price: price for immediate execution
        :type purchase_immediate_vesting_price: float
        :param sales_immediate_vesting_price: price for immediate execution
        :type sales_immediate_vesting_price: float
        :param low_liquidity_purchase_price: reference price for low liquidity placement
        :type low_liquidity_purchase_price: float
        :param low_liquidity_sales_price: reference price for low liquidity placement
        :type low_liquidity_sales_price: float
        :param order_volume: desired volume to place
        :type order_volume: float
        :param maximum_order_exposure: maximum remaining tradeable volume
        :type maximum_order_exposure: float
        :param slot_size: order placement packet size
        :type slot_size: float
        :param raw_order_volume: unrounded desired volume to place
        :type raw_order_volume: float
        :param duration_from_last_change_to_now: seconds since the last change of the position
        :type duration_from_last_change_to_now: float
        :param trading_indices: trading statistics of the near past
        :type trading_indices: list
        :param spread_indicator: historic spread size average
        :type spread_indicator: float
        :param lo_liquidity: use low liquidity mode
        :type lo_liquidity: bool
        :param omt_percent: OMT limit value in percent (between 0 and 100)
        :type omt_percent: float
        :return: ([description], mode, [order slots])
        :rtype: (list[str], str, list[PositionSlot]])
        """

        # collector for log message parts
        description = []

        def add_description(key, value):
            description.append("{}: {}".format(key, value))

        # if big changes in position happen, grace mode gives 10 minutes for the changes
        # to be taken from the market passively until we actively grab the volumes.
        # extended grace mode does that for 20 minutes.
        if self.use_grace_mode:
            if self.grace_mode == GraceMode.short_grace_period:
                duration_factor = 0.2
                end_time_factor = 2
            else:
                duration_factor = 1
                end_time_factor = 1

            grace_duration = GRACE_PERIOD_DURATION * duration_factor
            extended_grace_duration = EXTENDED_GRACE_PERIOD_DURATION * duration_factor
            grace_stop_before_end = GRACE_PERIOD_DURATION_STOP_BEFORE_END * end_time_factor
            extended_grace_stop_before_end = EXTENDED_GRACE_PERIOD_DURATION_STOP_BEFORE_END * end_time_factor

            grace_mode = (duration_from_last_change_to_now < grace_duration
                          and seconds_left > grace_stop_before_end)
            extended_grace_mode = (duration_from_last_change_to_now < extended_grace_duration
                                   and seconds_left > extended_grace_stop_before_end)
        else:
            grace_mode = extended_grace_mode = False

        # determine direction from the volumes
        direction = (Direction.buy if order_volume < -0.05 else
                     (Direction.sell if order_volume > 0.05 else
                      (Direction.buy if maximum_order_exposure < -0.05 else
                       (Direction.sell if maximum_order_exposure > 0.05 else None))))

        if direction is None:
            # no offer or there is no spread information from the order book, remove all orders
            add_description("direction", direction)
            return description, "", [
                PositionSlot(PositionSlot.front, direction, 0, None,
                             info="no_dir_ov_%s" % (round(order_volume, 2),))
            ]

        # next part is a bit tricky, as it applies for both trading directions, depending on the flags
        sgn = -1. if direction == Direction.buy else 1.
        indicators_main_index = 0 if direction == Direction.buy else 1
        indicators_others_main_index = 1 if direction == Direction.buy else 0

        def my_mw_price(index):
            # get order book price for my order book side (I sell -> sell side)
            if not indicators:
                return None
            return indicators[0].mw_prices[indicators_main_index][index]

        def other_mw_price(index):
            # get order book price for other order book side (I buy -> sell side)
            if not indicators:
                return None
            return indicators[0].mw_prices[indicators_others_main_index][index]

        def add_price(price, add):
            # "adds" a delta to a price in such a way that adding a positive value always adds for selling and
            # subtracts for buying
            if price is None:
                return None
            return price + sgn * add

        def better_price(*prices):
            # selects the better price depending on trading direction
            use_prices = [price for price in prices if price is not None]
            if not use_prices:
                return None
            if direction == Direction.buy:
                return min(use_prices)
            else:
                return max(use_prices)

        def worse_price(*prices):
            # selects the worse price depending on trading direction
            use_prices = [price for price in prices if price is not None]
            if not use_prices:
                return None
            if direction == Direction.buy:
                return max(use_prices)
            else:
                return min(use_prices)

        # in case something is negative, repair
        order_volume = abs(order_volume)
        raw_order_volume = abs(raw_order_volume)
        maximum_order_exposure = abs(maximum_order_exposure)

        if direction is not None and lo_liquidity:
            # low liquidity mode is simple, just place the order at the given price
            info = PlacementMode.lolq
            add_description("direction", direction)
            # minimum place 1 MW, else 2 slot sizes
            quantity = min(maximum_order_exposure, max(slot_size * 2, 1.))
            if direction == Direction.buy and low_liquidity_purchase_price is not None:
                return description, "", [PositionSlot(
                    PositionSlot.front, direction, quantity, low_liquidity_purchase_price, info=info)]
            elif direction == Direction.sell and low_liquidity_sales_price is not None:
                return description, "", [PositionSlot(
                    PositionSlot.front, direction, quantity, low_liquidity_sales_price, info=info)]
            else:
                return description, "", [PositionSlot(
                    PositionSlot.front, COMMON.Direction.buy, 0., 0., info=info + "/no_dir")]

        if not spread_indicator:
            add_description("spread_indicator", spread_indicator)
            return description, "", [
                PositionSlot(PositionSlot.front, direction, 0, None,
                             info="no_spread_si_%s" % (round(spread_indicator, 2) if spread_indicator else None))
            ]

        # price for aggressing
        other_zero_price = add_price(other_mw_price(DUMP_PRICE_POSITION), DUMP_PRICE_SHIFT)
        # price for more aggressive placing
        my_zero_price = add_price(my_mw_price(FRONT_PRICE_POSITION), FRONT_PRICE_SHIFT)
        # price for passive placing
        my_deep_price = my_mw_price(DEEP_FRONT_POSITION)

        if None in (my_zero_price, other_zero_price):
            # no prices, no action
            front = PositionSlot(PositionSlot.front, direction, 0., 0., info="no_own_or_pub_price")
            add_description("my_zero_price", my_zero_price)
            add_description("other_zero_price", other_zero_price)
            return description, "", [front]

        # we always place only 1 order, this is the slot that's being returned
        front = PositionSlot(PositionSlot.front, direction, info="")

        # price within the spread
        outprice = (other_mw_price(DUMP_PRICE_POSITION) + my_mw_price(FRONT_PRICE_POSITION)) / 2.

        # depending on the behaviour setting, define factors for the time at the end of trading
        # where we start to aggress and the factor for the maximum order size placed
        if self.behavior == StrategyBehavior.safe:
            end_dump_time = 2
            place_slots = 1
        elif self.behavior == StrategyBehavior.balanced:
            end_dump_time = 1
            place_slots = 2
        else:
            end_dump_time = -1
            place_slots = 3

        # last minutes, aggress if necessary
        if seconds_left <= DUMP_IN_LAST_SECONDS * end_dump_time:
            # do it with dump. if possible, stay at or above 1 MW order size, because of EPEX OMT rules
            quantity = min(maximum_order_exposure, max(slot_size * 2, 1.))
            front.set_quantity(quantity)
            front.set_prices(other_zero_price)
            front.info = PlacementMode.end
            return description, "", [front]

        # immediate vesting prices hit? then aggress
        if maximum_order_exposure > 0:
            if (
                direction == Direction.buy
                and None not in (purchase_immediate_vesting_price, other_zero_price)
                and other_zero_price <= purchase_immediate_vesting_price
            ):
                quantity = min(maximum_order_exposure, max(slot_size * 2, 1.))
                front.set_quantity(quantity)
                front.set_prices(other_zero_price)
                front.info = PlacementMode.ivest
                return description, "", [front]
            if (
                direction == Direction.sell
                and None not in (sales_immediate_vesting_price, other_zero_price)
                and other_zero_price >= sales_immediate_vesting_price
            ):
                quantity = min(maximum_order_exposure, max(slot_size * 2, 1.))
                front.set_quantity(quantity)
                front.set_prices(other_zero_price)
                front.info = PlacementMode.ivest
                return description, "", [front]

        def bruteforce(placement_quantity):
            # places order aggressing the quantity
            front.set_quantity(placement_quantity)
            front.set_prices(add_price(other_zero_price, DUMP_PRICE_SHIFT))

        def get_trade_index_info():
            # extract the historic price info from trades depending on in what time interval we find a reference
            # those prices are used for the less aggressive placement modes
            # attach to 2 or 10 or 30 minutes price, dependent on volume in trade history
            if trading_indices[1].volume < 10.:
                # almost no volume in the last 10 minutes, take 30 min average
                # get min/max from history, depending what's better for our placement
                index = better_price(trading_indices[2].max_price, trading_indices[2].min_price)
                # get the average if it is worse
                index_lower = worse_price(index, trading_indices[2].avg_price)
                return index, index_lower, 1.2
            elif trading_indices[0].volume < 10.:
                # almost no volume in the last 2 minutes, take 10 min average
                index = better_price(trading_indices[1].max_price, trading_indices[1].min_price)
                index_lower = worse_price(index, trading_indices[1].avg_price)
                return index, index_lower, 1.0
            else:
                # else 2 min average
                index = better_price(trading_indices[0].max_price, trading_indices[0].min_price)
                index_lower = worse_price(index, trading_indices[0].avg_price)
                return index, index_lower, 0.8

        def place_with_laziness(placement_quantity, use_price, lower_limit, upper_limit):
            # less aggressive mode
            # if we would place uselessly deep inside of the order book, retract order or freeze
            if better_price(use_price, my_mw_price(4)) == use_price:
                add_description("lazy_place - use_price", use_price)
                add_description("lazy_place - my_mw_price(4)", my_mw_price(4))
                # if order already there (qty tolerance), keep order where it is
                front.set_quantity(0., 0., placement_quantity)
                # same applies for the price tolerance
                front.set_prices(use_price, lower_limit, add_price(upper_limit, 100.))
            else:
                # else just place
                front.set_quantity(placement_quantity, placement_quantity, placement_quantity)
                omt_price_tolerance = self.get_pricetolerance_by_omt(omt_percent, self.omt_steps_settings)
                # guarantee that upper limit is the higher limit to apply tolerances correctly
                if upper_limit < lower_limit:
                    lower_limit, upper_limit = upper_limit, lower_limit
                front.set_prices(use_price, upper_limit + omt_price_tolerance, lower_limit - omt_price_tolerance)

        def standard(placement_quantity):
            # normal passive placing
            # get useful reference prices from public trades
            index, index_lower, spread_factor = get_trade_index_info()
            add_description("spread_indicator", spread_indicator)
            add_description("index", index)
            add_description("index_lower", index_lower)
            add_description("spread_factor", spread_factor)
            if index is None or spread_indicator is None:
                # dead market, we do not initiate here
                front.info = "no_index/no_spread"
                front.set_quantity(0., 0., 0.)
                return
            # based on the indices, calculate the price and the tolerance
            # use whats better: last trade price max/min, our own order book front or a safety distance from
            # the other order book side
            use_price = better_price(index,
                                     my_zero_price,
                                     add_price(other_zero_price, spread_indicator * spread_factor))
            # tolerance limits provide some wiggle space for placement, preventing ever ongoing change of order
            upper_limit = better_price(index,
                                       my_deep_price,
                                       add_price(other_zero_price, spread_indicator * spread_factor))
            lower_limit = better_price(index_lower,
                                       outprice,
                                       add_price(other_zero_price, spread_indicator * spread_factor * 0.5))
            place_with_laziness(placement_quantity, use_price, lower_limit, upper_limit)

        def force(placement_quantity):
            # a more aggressive version of "standard"
            index, index_lower, spread_factor = get_trade_index_info()
            add_description("spread_indicator", spread_indicator)
            add_description("index", index)
            add_description("index_lower", index_lower)
            add_description("spread_factor", spread_factor)
            if index is None or spread_indicator is None:
                # dead market, we do not initiate here
                front.set_quantity(0., 0., 0.)
                front.info = "no_index/no_spread"
                return
            use_price = better_price(index_lower,
                                     add_price(my_zero_price, -0.2),
                                     add_price(other_zero_price, spread_indicator * spread_factor * 0.5))
            upper_limit = better_price(index_lower,
                                       my_zero_price,
                                       add_price(other_zero_price, spread_indicator * spread_factor * 0.5))
            lower_limit = better_price(outprice,
                                       add_price(other_zero_price, spread_indicator * spread_factor * 0.2))
            place_with_laziness(placement_quantity, use_price, lower_limit, upper_limit)

        def force_boosted(placement_quantity):
            # most aggressive, but still passive placement, no influence of the trade history any more
            add_description("spread_indicator", spread_indicator)
            if spread_indicator is None:
                # dead market, we do not initiate here
                front.set_quantity(0., 0., 0.)
                front.info = "no_spread"
                return
            spread_factor = 1.
            use_price = better_price(outprice,
                                     add_price(other_zero_price, spread_indicator * spread_factor * 0.4))
            upper_limit = better_price(my_zero_price,
                                       add_price(other_zero_price, spread_indicator * spread_factor * 0.7))
            lower_limit = better_price(outprice,
                                       add_price(other_zero_price, spread_indicator * spread_factor * 0.2))
            place_with_laziness(placement_quantity, use_price, lower_limit, upper_limit)

        if omt_percent > OMT_FORCE:
            if omt_percent > OMT_BRUTE:
                # place order regardless of the current index, 1 MW is the target order size for small quantities
                # because that's what EPEX accepts as non-tiny trades
                bruteforce(min(maximum_order_exposure, max(slot_size, 1.)))
                front.info = PlacementMode.omt90
            elif omt_percent > OMT_FORCE_BOOST:
                force_boosted(min(maximum_order_exposure, order_volume * 0.6, slot_size))
                front.info = PlacementMode.omt80
            else:
                force(min(maximum_order_exposure, order_volume * 0.6, slot_size))
                front.info = PlacementMode.omt70
        else:
            # place according to quantity. if we're far behind our trading volume schedule, do it more aggressively.
            # grace mode (after changes of the position) blocks the more aggressive behaviour for some minutes
            if raw_order_volume > slot_size * (place_slots * 1.5 + 1) and not grace_mode and not extended_grace_mode:
                bruteforce(min(maximum_order_exposure, order_volume, max(slot_size, 1.)))
                front.info = PlacementMode.bruteforce
            elif raw_order_volume > slot_size * (place_slots + 1) and not grace_mode:
                force_boosted(min(maximum_order_exposure, order_volume, slot_size * place_slots))
                front.info = PlacementMode.force_boosted_grace if extended_grace_mode else PlacementMode.force_boosted
            elif raw_order_volume > slot_size * (place_slots * 0.5 + 1):
                force(min(maximum_order_exposure, order_volume, slot_size * place_slots))
                front.info = PlacementMode.force_grace if grace_mode or extended_grace_mode else PlacementMode.force
            else:
                standard(min(maximum_order_exposure, order_volume, slot_size * place_slots))
                front.info += PlacementMode.std_grace if grace_mode or extended_grace_mode else PlacementMode.std
        front.info += " omt_%.1f" % (omt_percent, ) if omt_percent is not None else " omt_none"
        if front.price_range_hi is not None:
            front.info += " pxrng_%.2f_%.2f" % (front.price_range_lo, front.price_range_hi)
        else:
            front.info += " pxrng_none"
        return description, "", [front]


class PositionClosingBase(strategy.Strategy, strategy.ProductsFilterMixin):
    """Base class for standard position closer and spontaneous position closer"""
    def __init__(self, *args, **kwargs):
        super(PositionClosingBase, self).__init__(*args, **kwargs)
        # position management class instance
        self.log = log

        self.position = strategy.Position()
        # for measuring the liquidity based on market and order book
        self.liquidity_measurement_container = None
        # low liquidity order development calculation containers
        self.price_curve_container_sell = PriceCurveContainer(self.debug_log)
        self.price_curve_container_buy = PriceCurveContainer(self.debug_log)
        # containers for the volume distribution curve over time
        self.product_volume_factor_buy = None
        self.product_volume_factor_sell = None
        # container for standard deviation calculation
        self.position_deviation_handler = None
        # calculator for order volume
        self.order_volume_calculator = None
        # generator for concrete order placement
        self.position_slot_generator = None
        # behaviour setting (safe, balanced, better price)
        self.behavior = None
        # timeseries from intraday trading object in GUI
        self.strategy_price_purchase_immediate_vesting = None
        self.strategy_price_sales_immediate_vesting = None
        self.strategy_price_purchase = None
        self.strategy_price_sales = None
        self.strategy_limit_maximum_sales_volume = None
        self.strategy_limit_maximum_purchase_volume = None
        self.strategy_limit_maximum_purchase_price = None
        self.strategy_limit_minimum_sales_price = None
        self.strategy_price_minimum_spread_buyback = None

        # timeseries restricting order updates in the depth of the orderbook
        self.strategy_order_update_absolute_depth_limit = STRATDATA.StrategyTimeSeries()
        self.strategy_order_update_relative_depth_limit = STRATDATA.StrategyTimeSeries()

        # mapping from timestamp (quarterly) to the timestamp of last change for the position of this quarter
        self.last_change_timestamps = defaultdict(lambda: None)
        # storage for the trade index for products
        self.trade_indices = dict()
        self.product_evaluation_dict = dict()

        # maximum order size to be placed at once, global limit
        self.maximum_order_book = None

    def get_omt_step_settings(self):
        return OMT_TOLERANCE_STEPS

    def check_exchange_timestamp_halt(self, timestamp):
        """This method checks if timestamp is in within the boundaries of a predefined market halt set in periotheus.

        If the timestamp is within a market halt period the method will return a
        list with the beginning timestamp of the market halt period.
        If the time span is not within a market halt it will return an empty list.
        """
        try:
            market_halt_set = self.exchange.market_halt_set
        except AttributeError:
            return []
        timestamp_in_halt = [market_halt_set[i][0] for i in range(len(market_halt_set))
                             if market_halt_set[i][0] <= timestamp < market_halt_set[i][1]]
        return timestamp_in_halt

    def spread_indicator(self, evaluate_product, depth_index=1):
        """calculates an estimation of the average spread in the last minutes"""
        indicators = evaluate_product.orders.indicators(self.delivery_area_id)
        # make sure, we have at least 1 Minute
        if len(indicators) < 7:
            return None
        # take the average of the max from the last minute and the average of the last 5 Minutes
        minute = []
        complete = []
        for idx, element in enumerate(indicators):
            sell = element.mw_prices[1][depth_index]
            buy = element.mw_prices[0][depth_index]
            if None in (sell, buy):
                continue
            spread = sell - buy
            if idx < 7:
                minute.append(spread)
            complete.append(spread)
        if len(minute) < 6 or len(complete) < 10:
            return None
        # 80% of the newest max and 20% of the 5 minutes mix
        return 0.8 * max(minute) + 0.2 * (sum(complete) / len(complete))

    def calculate_product_volume(self, product_type, area, interval, timestamp):
        """calculates total traded volume of all products of the type given in the interval given.
        this result is used to evaluate the liquidity in different product types"""
        products = [
            p for p in self.exchange.products.get_all()
            if (
                p.product_type == product_type
                and p.delivery_end - p.delivery_start == interval
                and p.delivery_start > timestamp - 36 * COMMON.HOUR
                and p.delivery_end < timestamp + 12 * COMMON.HOUR
            )
        ]
        volumes = 0.
        counter = 0.
        for product in products:
            for trade in product.trades.get(trade_filter=COMMON.TradeFilter.public, delivery_area=area):
                volumes += trade.quantity
            counter += 1
        if not counter:
            return 0.
        else:
            # return the volume in MWh
            return volumes * interval / (counter * COMMON.HOUR)

    def product_volume_evaluation(self, product, area, timestamp):
        """caching mechanism for 'calculate_product_volume'"""
        interval = product.delivery_end - product.delivery_start
        evaluation_item = self.product_evaluation_dict.get((product.product_type, area, interval), None)
        # if there is nothing in the cache, recalculate, do that also if the last calculation is more than 1 hour ago
        if evaluation_item is None or evaluation_item[0] + COMMON.HOUR < timestamp:
            # calculate and save
            evaluation_item = (timestamp,
                               self.calculate_product_volume(product.product_type, area, interval, timestamp))
            self.product_evaluation_dict[(product.product_type, area, interval)] = evaluation_item
        return evaluation_item[1]

    def invalidate_rolling_average_cache(self, evaluate_product):
        """invalidator for the trade index cache"""
        self.trade_indices.pop(evaluate_product.product_id, None)

    def rolling_average(self, evaluate_product, timestamp):
        """return 2, 10 and 30 minute average price from public trades"""
        if ((evaluate_product.product_id in self.trade_indices)
                and (timestamp - self.trade_indices[evaluate_product.product_id][0] < 60)):
            # still fresh, return from cache
            return self.trade_indices[evaluate_product.product_id][1]
        # Collect all the trades for all products with same delivery period.
        # This is necessary because we have to merge xbid and non xbid products.
        products = self.exchange.products.get_by_timerange(
            evaluate_product.delivery_start, evaluate_product.delivery_end)
        # collect trades
        collected_trades = []
        for product in products:
            if ((product.delivery_start != evaluate_product.delivery_start)
                    or (product.delivery_end != evaluate_product.delivery_end)):
                continue
            # get for the last 30 minutes
            trades = product.trades.get(trade_filter=COMMON.TradeFilter.public,
                                        timerange=(timestamp - 60 * 30, timestamp))

            # filter for delivery_area, special case for germany, because 30 minutes before delivery
            # all german zones are merged
            collected_trades.extend([trade for trade in trades if trade.match_delivery_areas([self.delivery_area_id])])

        # now calculate volume, price for 2, 10, 30 minutes
        def indexes(minutes):
            timestamp_filter = timestamp - minutes * 60
            revenue, volume = 0., 0.
            trades_analyzed = []
            for trade in collected_trades:
                if trade.execution_time < timestamp_filter:
                    continue
                trades_analyzed.append(trade)
                revenue += trade.price * trade.quantity
                volume += trade.quantity
            if volume == 0.:
                return TradeIndex(0., None, None, None)
            prices = [trade.price for trade in trades_analyzed]
            return TradeIndex(volume, revenue / volume, min(prices), max(prices))
        # save for cache
        self.trade_indices[evaluate_product.product_id] = (timestamp, (indexes(2), indexes(10), indexes(30)))
        return self.trade_indices[evaluate_product.product_id][1]

    def get_omt_percent(self):
        # type: () -> int
        omt_l1_percent = 0
        if self.exchange.internal_id == COMMON.Exchange.epex:
            # OMT is currently only implemented for EPEX
            short_omt = self.exchange.short_omt
            long_omt = self.exchange.long_omt
            relevant_omt = short_omt if short_omt.l1_percent > long_omt.l1_percent else long_omt
            omt_l1_percent = relevant_omt.l1_percent
            self.debug_log("OMT L1 percent short: %.2f, long: %.4f. Creating slots considering %s OMT" %
                           (short_omt.l1_percent, long_omt.l1_percent, relevant_omt.limit_type))
        return omt_l1_percent

    def custom_act_for_product(self, log_data, product, timestamp,
                               order_volume, maximum_order_exposure, slot_size, raw_order_volume,
                               average_price, last_change_timestamp, seconds_left, traded):
        """prepare data and do slot generation an actual placement"""

        product_interval = int(product.delivery_start), int(product.delivery_end)

        if product.state(self.delivery_area_id) != DeliveryAreaState.active:
            return

        # get trading data from cache
        trading_indices = self.rolling_average(product, timestamp)

        # prepare info for limiting
        limit_maximum_sales_volume = self.strategy_limit_maximum_sales_volume.get(product_interval, None)
        limit_maximum_purchase_volume = self.strategy_limit_maximum_purchase_volume.get(product_interval, None)

        traded_sell, traded_buy = traded

        limit_minimum_sales_price, limit_maximum_purchase_price = self.get_order_price_limits(
            maximum_order_exposure, traded_sell - traded_buy, average_price, product_interval)

        stats = ["{:0.1f}_{:0.1f}_{:0.1f}_{:0.1f}".format(
            order_volume, maximum_order_exposure, slot_size, raw_order_volume
        )]

        # do a limit check on volumes here, additionally to the limiter
        if (order_volume > 0. or maximum_order_exposure > 0.) and limit_maximum_sales_volume is not None:
            tradeable = max(0., limit_maximum_sales_volume - traded_sell)
            if tradeable < order_volume:
                order_volume = tradeable
                self.debug_log("limiting order_volume to tradeable: {}".format(order_volume), product)

            if tradeable < maximum_order_exposure:
                maximum_order_exposure = tradeable
                self.debug_log("limiting maximum_order_exposure to tradeable: {}".format(maximum_order_exposure),
                               product)

        if (order_volume < 0. or maximum_order_exposure < 0.) and limit_maximum_purchase_volume is not None:
            tradeable = max(0., limit_maximum_purchase_volume - traded_buy)
            neg_tradeable = tradeable * -1.

            if neg_tradeable > order_volume:
                order_volume = neg_tradeable
                self.debug_log("increasing order_volume to -tradeable: {}".format(order_volume), product)

            if neg_tradeable > maximum_order_exposure:
                maximum_order_exposure = neg_tradeable
                self.debug_log("increasing maximum_order_exposure to -tradeable: {}".format(maximum_order_exposure),
                               product)

        # retrieve prices for product
        purchase_immediate_vesting_price = self.strategy_price_purchase_immediate_vesting.get(
            (product_interval[0], product_interval[0] + 900), None)
        sales_immediate_vesting_price = self.strategy_price_sales_immediate_vesting.get(
            (product_interval[0], product_interval[0] + 900), None)
        purchase_price = self.strategy_price_purchase.get((product_interval[0], product_interval[0] + 900), None)
        sales_price = self.strategy_price_sales.get((product_interval[0], product_interval[0] + 900), None)

        # get tolerance value for order updates deep in order book either from timeseries
        # fallback to constants in strategy if timeseries are not available.
        max_own_depth_order_placement_abs_euro = self.strategy_order_update_absolute_depth_limit.get(
            (product_interval[0], product_interval[0] + 900), MAX_OWN_DEPTH_ORDER_PLACEMENT_ABS_EURO
        )
        max_own_depth_order_placement_relative_euro = self.strategy_order_update_relative_depth_limit.get(
            (product_interval[0], product_interval[0] + 900), MAX_OWN_DEPTH_ORDER_PLACEMENT_RELATIVE_EURO
        )

        indicators = product.orders.indicators(self.delivery_area_id)
        if not indicators:
            return

        spread_indicator = self.spread_indicator(product)

        mw_prices = indicators[0].mw_prices

        # determine, if we need to use low liquidity mode
        low_liquidity = self.liquidity_measurement_container.use_lo_liquidity(
            product.product_id, self.delivery_area_id, mw_prices, timestamp)

        low_liquidity_sell_price, low_liquidity_purchase_price = None, None
        if low_liquidity:
            # loq liquidity order placement moves in the last 2 hours of trading
            time_factor = (3600. - seconds_left * 0.5) / 3600.
            low_liquidity_sell_price = self.price_curve_container_sell.get_price(product.product_id,
                                                                                 sales_immediate_vesting_price,
                                                                                 sales_price, time_factor)
            low_liquidity_purchase_price = self.price_curve_container_buy.get_price(product.product_id,
                                                                                    purchase_immediate_vesting_price,
                                                                                    purchase_price, time_factor)
            self.debug_log("LLPs {} {}".format(low_liquidity_sell_price, low_liquidity_purchase_price), product)

        # decide on omt, to pass correct percentage to position slot generator
        omt_l1_percent = self.get_omt_percent()

        description, mode, slots = self.position_slot_generator.get_slots(indicators, seconds_left,
                                                                          purchase_immediate_vesting_price,
                                                                          sales_immediate_vesting_price,
                                                                          low_liquidity_purchase_price,
                                                                          low_liquidity_sell_price, order_volume,
                                                                          maximum_order_exposure, slot_size,
                                                                          raw_order_volume,
                                                                          timestamp - last_change_timestamp,
                                                                          trading_indices, spread_indicator,
                                                                          low_liquidity, omt_l1_percent)

        stats.append(mode)

        log_data = dict()

        for idx in range(len(slots)):
            slot = slots[idx]
            if slot.direction == COMMON.Direction.buy and PY2LIB.bigger_than(slot.price, limit_maximum_purchase_price):
                slots[idx] = PositionSlot(slot.slot_type, slot.direction, slot.quantity,
                                          limit_maximum_purchase_price, info=slot.info + " lmt_px")
                self.warn_log("Limit-Price-Adj {}=>{}:{}".format(
                    slots[idx].price, limit_maximum_purchase_price, slots[idx].short()),
                    product
                )
            elif slot.direction == COMMON.Direction.sell and PY2LIB.bigger_than(limit_minimum_sales_price, slot.price):
                slots[idx] = PositionSlot(slot.slot_type, slot.direction, slot.quantity,
                                          limit_minimum_sales_price, info=slot.info + " lmt_px")
                self.warn_log("Limit-Price-Adj {}=>{}:{}".format(
                    slots[idx].price, limit_minimum_sales_price, slots[idx].short()),
                    product
                )

        # cap slot quantities by global maximum order size limits:
        for slot in slots:
            qty = slot.quantity
            if self.maximum_order_book is not None and self.maximum_order_book < qty:
                qty = self.maximum_order_book
            if slot.direction == COMMON.Direction.buy and self.maximum_bid is not None and self.maximum_bid < qty:
                qty = self.maximum_bid
            elif slot.direction == COMMON.Direction.sell and self.maximum_ask is not None and self.maximum_ask < qty:
                qty = self.maximum_ask
            slot.quantity = qty

        slotlog = " / ".join(["{} {} {}@{} ({}-{})".format(s.slot_type, s.direction, s.quantity, s.price,
                                                           s.price_range_lo, s.price_range_hi) for s in slots])
        spread_info = self.liquidity_measurement_container.spread_info
        slot_stats = "{} {}, m:{} ov:{} me:{} ss:{} ro:{} - {} | {}".format(timestamp_log(timestamp, extended=True),
                                                                            product.name, mode, order_volume,
                                                                            maximum_order_exposure, slot_size,
                                                                            raw_order_volume, slotlog,
                                                                            spread_info)
        if description:
            slot_stats += " | " + " / ".join(description)
        self.debug_log(slot_stats, product)

        self.place_slots(log_data, product, timestamp, self.delivery_area_id, slots, stats, limit_minimum_sales_price,
                         limit_maximum_purchase_price, execmode=INTERNAL_EXECUTION_MODE,
                         max_own_depth_order_placement_abs_euro=max_own_depth_order_placement_abs_euro,
                         max_own_depth_order_placement_rel_euro=max_own_depth_order_placement_relative_euro)

    def get_order_price_limits(self, maximum_exposure, traded, average_price, product_interval):
        """Get average prices of our own trades so far, add spread setting for buyback and return the result as
        a hard limit for trading."""
        limit_maximum_purchase_price = self.strategy_limit_maximum_purchase_price[product_interval]
        limit_minimum_sales_price = self.strategy_limit_minimum_sales_price[product_interval]
        spread_buyback = self.strategy_price_minimum_spread_buyback[product_interval]

        if None not in (spread_buyback, average_price):
            if maximum_exposure > 0 > traded:
                # long position for sell, but we have
                # bought more than we have sold
                min_price_for_order = average_price + spread_buyback
                if limit_minimum_sales_price is not None:
                    limit_minimum_sales_price = PY2LIB.py2max((limit_minimum_sales_price, min_price_for_order))
                else:
                    limit_minimum_sales_price = min_price_for_order
            elif maximum_exposure < 0 < traded:
                # short position for buy, but we have
                # sold more than we have bought
                max_price_for_order = average_price - spread_buyback
                if limit_maximum_purchase_price is not None:
                    limit_maximum_purchase_price = PY2LIB.py2min((limit_maximum_purchase_price, max_price_for_order))
                else:
                    limit_maximum_purchase_price = max_price_for_order

        return limit_minimum_sales_price, limit_maximum_purchase_price

    def calculate_exposures(self, ts_from, ts_until, traded, trading_start_before_market_closure_sec,
                            trading_end_before_market_closure_sec, timestamp, omt_percent=0):
        """stub for the functions defined in derived classes"""
        raise NotImplementedError

    def act_for_interval(self, ts_from, ts_until, timestamp):
        """Do what has to be done for the given interval, usually 1 hour in central europe and 4 hours in UK.

        :param ts_from: start of the blocked duration
        :type ts_from: int
        :param ts_until: end of the blocked duration
        :type ts_until: int
        :type timestamp: float
        :rtype: None
        """
        duration = ts_until - ts_from

        if duration not in COMMON.ProductDurations.ID.ALL:
            self.warn_log("Duration {} not in allowed block durations: {}. Skip {} {}-{} [{}-{}]".format(
                duration, COMMON.ProductDurations.ID.ALL,
                CETUTIL.utc_ts2cet_dt(ts_from).strftime("%Y-%m-%d"),
                CETUTIL.utc_ts2cet_dt(ts_from).strftime("%H:%M"),
                CETUTIL.utc_ts2cet_dt(ts_until).strftime("%H:%M"),
                ts_from, ts_until)
            )
            return
        else:
            self.debug_log("Act on Interval: {} {}-{} [{}-{}]".format(
                CETUTIL.utc_ts2cet_dt(ts_from).strftime("%Y-%m-%d"),
                CETUTIL.utc_ts2cet_dt(ts_from).strftime("%H:%M"),
                CETUTIL.utc_ts2cet_dt(ts_until).strftime("%H:%M"),
                ts_from, ts_until)
            )

        # get all products (inactivates included), exactly for the interval range
        products = self.exchange.products.get_by_timerange(ts_from, ts_until)
        allowed_products = self.get_allowed_products(products, timestamp, active_on_area=self.delivery_areas[0])
        allowed_product_ids = set([p.product_id for p in allowed_products])

        product_rank = []
        # rank products by volumes usually traded in their product types. we need this to select the right products
        # for distribution of our volumes
        for product in products:
            if product.state(self.delivery_area_id) == COMMON.DeliveryAreaState.active:
                if product.product_id not in allowed_product_ids:
                    product_rank.append((-1, product.delivery_end - product.delivery_start, product))
                    continue
                product_eval = self.product_volume_evaluation(product, self.delivery_area_id, timestamp)
                if product.orders.get(order_filter=COMMON.OrderFilter.own, portfolio_key=self.strategy_id):
                    # favour this product, if there are already orders in it
                    product_eval *= 1.3
                product_rank.append((product_eval, product.delivery_end - product.delivery_start, product))
        product_rank.sort(reverse=True)

        self.debug_log("product_rank: {}".format([(p[0], p[1], p[2].name) for p in product_rank]))

        # setting from the GUI in minutes converted to seconds
        trading_end_before_market_closure_sec = (
            (
                self.strategy_settings["trading_end_before_market_closure"] or TRADING_END_BEFORE_DELIVERY_MINUTES
            ) * COMMON.MINUTE
        )
        trading_start_before_market_closure_sec = (
            (
                self.strategy_settings.get("trading_start") or TRADING_START_BEFORE_DELIVERY_MINUTES
            ) * COMMON.MINUTE
        )

        # calculate traded_position in 15 minutes resolution, summing up all products in the range
        traded = defaultdict(float)
        traded_per_product = defaultdict(lambda: (0., 0.))
        product_to_average_price = dict()
        for product in products:
            own_trades = product.trades.get(
                delivery_area=self.delivery_area_id,
                trade_filter=api.TradeFilter.own,
                portfolio_key=self.strategy_id
            )
            traded_sell = sum(t.quantity for t in own_trades if t.direction == Direction.sell)
            traded_buy = sum(t.quantity for t in own_trades if t.direction == Direction.buy)
            traded_per_product[product.product_id] = (traded_sell, traded_buy)
            for ts in range(int(product.delivery_start), int(product.delivery_end), COMMON.QUARTER):
                traded[ts] += traded_sell - traded_buy
            if own_trades:
                average_price = sum(t.quantity * t.price for t in own_trades) / (traded_sell + traded_buy)
            else:
                average_price = None
            product_to_average_price[product.product_id] = average_price

        # then determine volumes
        exposures, seconds_left = self.calculate_exposures(
            ts_from, ts_until, traded,
            trading_start_before_market_closure_sec,
            trading_end_before_market_closure_sec,
            timestamp
        )

        # go through products as they are ranked, starting with high volume products first
        # in case a fine-granular product type has a higher volume than a lower granularity type, the
        # fine grained one will take the quantities, not leaving any quantities for the other
        for interval, rank, product in product_rank:
            p_trading_end = product.delivery_start - trading_end_before_market_closure_sec
            p_trading_start = product.delivery_start - trading_start_before_market_closure_sec
            timestamp_check_halt = self.check_exchange_timestamp_halt(p_trading_end)
            if timestamp_check_halt:
                # shift moment of trading end
                p_trading_end = timestamp_check_halt[0]
            if p_trading_start < timestamp < p_trading_end and product.product_id in allowed_product_ids:
                # all q's in this product, build the current max exposure block and the max-factor for the hour
                (pmaximum_order_exposure, ptraded, pslot_size,
                 puse_maximum_order_book, pfactor) = exposures[product.delivery_start]
                pseconds_left = seconds_left[product.delivery_start]
                plast_change_timestamp = self.last_change_timestamps[int(product.delivery_start)][0]
                # iterate through all quarter delivery hours in the product
                for qts in range(int(product.delivery_start) + COMMON.QUARTER,
                                 int(product.delivery_end), COMMON.QUARTER):
                    maximum_order_exposure, traded, slot_size, use_maximum_order_book, factor = exposures[qts]
                    # last change counts
                    plast_change_timestamp = max(plast_change_timestamp, self.last_change_timestamps[qts][0])
                    # min of seconds left counts
                    pseconds_left = min(pseconds_left, seconds_left[qts])
                    # take the max of the factor, otherwise we might miss out on quantities
                    pfactor = max(pfactor, factor)
                    # smallest packet out of quarters
                    pslot_size = min(pslot_size, slot_size)
                    # largest max order size setting
                    puse_maximum_order_book = max(puse_maximum_order_book, use_maximum_order_book)
                    # depending on the direction of trading, take the min or the max for overall volume and
                    # traded quantity
                    if maximum_order_exposure < 0:
                        if pmaximum_order_exposure > 0:
                            pmaximum_order_exposure, ptraded, puse_maximum_order_book, pfactor = 0, 0, 0, 0
                        elif pmaximum_order_exposure <= 0:
                            pmaximum_order_exposure = max(pmaximum_order_exposure, maximum_order_exposure)
                            ptraded = max(ptraded, traded)
                    else:
                        if pmaximum_order_exposure < 0:
                            pmaximum_order_exposure, ptraded, puse_maximum_order_book, pfactor = 0, 0, 0, 0
                        elif pmaximum_order_exposure >= 0:
                            pmaximum_order_exposure = min(pmaximum_order_exposure, maximum_order_exposure)
                            ptraded = min(ptraded, traded)
                # based on the aggregated volumes we determined, calculate the placement volume for product
                porder_volume, praw_order_volume = self.order_volume_calculator.prepare_order_volumes(
                    pmaximum_order_exposure, ptraded, puse_maximum_order_book, pslot_size, pfactor)

                # deduct product exposure from quarter values before we go to the next product
                for qts in range(int(product.delivery_start), int(product.delivery_end), COMMON.QUARTER):
                    maximum_order_exposure, traded, slot_size, use_maximum_order_book, factor = exposures[qts]
                    if maximum_order_exposure < 0:
                        new_exposure = min(maximum_order_exposure - pmaximum_order_exposure, 0)
                        # need this ratio to correct the slot size for the reduced quantity
                        ratio = abs(new_exposure) / abs(maximum_order_exposure) if maximum_order_exposure != 0. else 0.
                        exposures[qts] = (new_exposure, traded - ptraded,
                                          self.order_volume_calculator.shrink_slot_size(slot_size, ratio),
                                          use_maximum_order_book, factor)
                    else:
                        new_exposure = max(maximum_order_exposure - pmaximum_order_exposure, 0)
                        ratio = abs(new_exposure) / abs(maximum_order_exposure) if maximum_order_exposure != 0. else 0.
                        exposures[qts] = (new_exposure, traded - ptraded,
                                          self.order_volume_calculator.shrink_slot_size(slot_size, ratio),
                                          use_maximum_order_book, factor)

                # run order placement for this product
                self.act_for_product(product, timestamp,
                                     porder_volume, pmaximum_order_exposure, pslot_size, praw_order_volume,
                                     product_to_average_price[product.product_id], plast_change_timestamp,
                                     pseconds_left, traded_per_product[product.product_id])
            else:
                # remove order
                self.act_for_product(product, timestamp, 0., 0., 0., 0., 0., 0., 0., (0., 0.))

    def custom_act(self, log_data, timestamp, products=None):
        """Find intervals to act on, and place orders where necessary according to calculations

        :type log_data: list
        :type timestamp: float
        :type products: list[autotrader_core.exchange_trading.Product]
        :rtype: None
        """
        if not products:
            return

        for interval in self.products_to_intervals(products):
            self.act_for_interval(*interval, timestamp=timestamp)

    def on_strategy_update(self, strategy_json):
        # for variable descriptions, see __init__
        super(PositionClosingBase, self).on_strategy_update(strategy_json)

        self.delivery_area_id = self.delivery_areas[0]
        # depending on market, the interval of interest is different, UK has a 4 hour product

        self.position.update_from_json(
            strategy_json[COMMON.StrategyJsonKey.TS.pos_sell],
            strategy_json[COMMON.StrategyJsonKey.TS.pos_buy])
        use_fixed_random_seed = strategy_json.get("use_fixed_random_seed", False)
        # In simulation, the low liquidity curve containers use a fixed seed.
        self.price_curve_container_sell.use_fixed_random_seed = use_fixed_random_seed
        self.price_curve_container_buy.use_fixed_random_seed = use_fixed_random_seed
        self.product_volume_factor_buy = ProductVolumeFactorContainer(
            self.strategy_settings, self.check_exchange_timestamp_halt, Direction.buy,
            use_fixed_random_seed)
        self.product_volume_factor_sell = ProductVolumeFactorContainer(
            self.strategy_settings, self.check_exchange_timestamp_halt, Direction.sell,
            use_fixed_random_seed)

        self.position_deviation_handler = PositionDeviationHandler(self.strategy_settings)

        self.order_volume_calculator = OrderVolumeCalculator(
            self.strategy_settings.get(COMMON.StrategyJsonKey.maximum_imbalance_on_market_closure),
            self.strategy_settings.get(COMMON.StrategyJsonKey.maximum_order_book)
        )

        self.behavior = strategy_json[COMMON.StrategyJsonKey.behavior] or StrategyBehavior.balanced
        self.strategy_price_purchase_immediate_vesting = strategy.mk_strategy_tr_dict(
            strategy_json[COMMON.StrategyJsonKey.TS.price_imm_buy], COMMON.AggregatorRule.min)
        self.strategy_price_sales_immediate_vesting = strategy.mk_strategy_tr_dict(
            strategy_json[COMMON.StrategyJsonKey.TS.price_imm_sell], COMMON.AggregatorRule.max)

        # userdefined timeseries to limit orderupdates deep in the orderbook
        if COMMON.StrategyJsonKey.user_defined_timeseries in strategy_json:
            udf = strategy_json[COMMON.StrategyJsonKey.user_defined_timeseries]
            if COMMON.StrategyJsonKey.UDFTS.order_update_absolute_depth_limit in udf:
                self.strategy_order_update_absolute_depth_limit = strategy.mk_strategy_tr_dict(
                    udf[COMMON.StrategyJsonKey.UDFTS.order_update_absolute_depth_limit],
                    COMMON.AggregatorRule.min
                )
            else:
                self.strategy_order_update_absolute_depth_limit = STRATDATA.StrategyTimeSeries()

            if COMMON.StrategyJsonKey.UDFTS.order_update_relative_depth_limit in udf:
                self.strategy_order_update_relative_depth_limit = strategy.mk_strategy_tr_dict(
                    udf[COMMON.StrategyJsonKey.UDFTS.order_update_relative_depth_limit],
                    COMMON.AggregatorRule.min
                )
            else:
                self.strategy_order_update_relative_depth_limit = STRATDATA.StrategyTimeSeries()

        if COMMON.StrategyJsonKey.TS.price_buy in strategy_json:
            self.strategy_price_purchase = strategy.mk_strategy_tr_dict(
                strategy_json[COMMON.StrategyJsonKey.TS.price_buy], COMMON.AggregatorRule.min)
        else:
            self.strategy_price_purchase = STRATDATA.StrategyTimeSeries()

        if COMMON.StrategyJsonKey.TS.price_sell in strategy_json:
            self.strategy_price_sales = strategy.mk_strategy_tr_dict(
                strategy_json[COMMON.StrategyJsonKey.TS.price_sell], COMMON.AggregatorRule.max)
        else:
            self.strategy_price_sales = STRATDATA.StrategyTimeSeries()

        self.strategy_price_minimum_spread_buyback = strategy.mk_strategy_tr_dict(
            strategy_json[COMMON.StrategyJsonKey.TS.price_min_spread_buyback],
            COMMON.AggregatorRule.min_nonone
        )

        self.maximum_order_book = strategy_json.get(COMMON.StrategyJsonKey.maximum_order_book)

        self.liquidity_measurement_container = LiquidityMeasurementContainer(
            self.llq_spread1_indicator, self.llq_spread1_limit, self.llq_spread2_indicator, self.llq_spread2_limit,
            self.debug_log
        )
        # export some info to MongoDB fpr the REST API
        self.api_export_timeseries({
            "pos_long": ("Position Long", "MW", "MW", COMMON.QUARTER, self.position.positions_long),
            "pos_short": ("Position Short", "MW", "MW", COMMON.QUARTER, self.position.positions_short)})

    def custom_on_order_book_update(self, orders, timestamp):
        """React only to public orders, and not own orders

        We also filter for orderbook updates, which are within the orderbook depth that
        can have an effect on order placement
        """
        deepest_relevant_ob_idx = max(DEEP_FRONT_POSITION, self.llq_spread1_indicator, self.llq_spread2_indicator)
        # Lookup table, how to check an order's relevance
        check = {
            COMMON.Direction.buy:
                lambda order_price, indicator:
                    (indicator.mw_prices[0][deepest_relevant_ob_idx] is None)
                    or (order_price >= indicator.mw_prices[0][deepest_relevant_ob_idx]),
            COMMON.Direction.sell:
                lambda order_price, indicator:
                    (indicator.mw_prices[1][deepest_relevant_ob_idx] is None)
                    or (order_price <= indicator.mw_prices[1][deepest_relevant_ob_idx]),
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

        # 'if getattr(o, "order_id", None)' can filter out own orders, since they might not have an order id
        products = set(o.product for o in relevant_orders if getattr(o, "order_id", None) not in order_ids_by_product)

        if products:
            self.act(timestamp, products)

    def custom_on_trade_update(self, trades, timestamp):
        self.act(timestamp, set(o.product for o in trades))

    def custom_on_public_trade_update(self, trades, timestamp):
        products = set(o.product for o in trades)
        for product in products:
            self.invalidate_rolling_average_cache(product)

    def custom_on_products_update(self, products, timestamp):
        # Delete the price curves for all inactive products.
        # If the product becomes active again, a new price curve will be created when needed anyway,
        # which does not hurt us.
        for product in products:
            if product.state(self.delivery_area_id) != COMMON.DeliveryAreaState.active:
                self.price_curve_container_sell.clean_up(product.product_id)
                self.price_curve_container_buy.clean_up(product.product_id)

        # no order action here, because of the XBID product switches
        # EPEX sends the product updates in separate documents, so
        # reacting on those documents directly causes premature order
        # placement for products that may already be closed at the exchange
        # but we can't see that yet.
        pass

    def custom_on_products_queue(self, products, timestamp):
        self.act(timestamp, products)

    def custom_on_timer(self, timestamp):
        pass  # products queue is enough
