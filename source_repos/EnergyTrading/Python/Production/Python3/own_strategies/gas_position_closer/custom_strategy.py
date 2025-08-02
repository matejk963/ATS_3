#!/usr/bin/python3
# -*- coding: utf-8 -*-
import decimal
import logging
import math
from collections import defaultdict

import autotrader_lib.common as COMMON
import autotrader_core.gas_strategy_parameters as PARAMS
import autotrader_core.strategy as STRATEGY
import autotrader_core.strategy_utils as SU
import autotrader_core.utils as UTIL
from six.moves import range
from six.moves import zip

log = logging.getLogger('autotrader.position_closer_gas')

TRAYPORT_BROKER_ID = COMMON.Broker.eexs

######################
# Strategy Constants #
######################

# price tolerance for the botrace protection. (Reluctance to move to a price that is worse for us)
PRICE_TOLERANCE = 0.0

# default min amount for quantities to not be considered for order modify ("virtual iceberg")
MIN_QTY_PLACEMENT = None

# default maximum placement size. If this is less than the instrument's minimum quantity, the strategy halts itself!
MAX_ORDERBOOK_DEFAULT = 1

# slot names
LUCKY = "lucky"
CONSERVATIVE = "cons"
FORCE = "force"


class ForceOrderMode(object):
    """
    The mode (added to the text field) of force orders.

    Note: When the order is removed, the mode is not defined and can be any of the modes below (as the order is not
    visible on the exchange anyway).

    aggress: If the strategy has closed way less of the position than planned for the current time, then it aggresses
    counter orders.
    almost_agress: If the strategy wants to aggress, but cannot, because it has to place an all or nothing order
                   and the counter order has insufficient quantity. In this case it will place an AON order 1 tick
                   size in front of the counter order, to maximize the likelihood that it gets traded.
    immediate_vesting: Based on the price timeseries for immediate execution, the strategy aggresses counter orders.
    front_runner: Otherwise, the strategy tries to stay at front of the orderbook.
    """
    immediate_vesting = "iv"
    aggress = "ag"
    almost_aggress = "aa"
    front_runner = "fr"


DAY = 24


def get_value_or_zero(value):
    """Function that changes None to zero"""
    return value or 0.


def get_remaining_position(position, traded):
    return get_value_or_zero(position) + get_value_or_zero(traded)


def calculate_wd_delivery_borders(delivery_end):
    """
    Calculate start of the gas day, DST changes taken into account.

    :param delivery_end: (utc) timestamp
    :type delivery_end: int
    :return: gas day start, end
    :rtype: (int, int)
    """
    prod_day, prod_start_day_start, prod_start_day_end = UTIL.cet_date_of_timestamp(delivery_end)
    gas_day_start = prod_start_day_start - COMMON.HOUR * 18  # Gas Days start at 6 AM
    gas_day_end = prod_start_day_end - COMMON.HOUR * 18
    return gas_day_start, gas_day_end


class TradingDistributionCalculator(object):
    """
    This defines a curve defining at what time we should trade what fraction of the position.
    Users would define non-default curves here to reflect their estimation of when the market has the highest liquidity.

    These curves are defined by a simple list per product with one positive number per quarter hour,
    the last of which is the quarter hour immediately before delivery start (with special treatment for WD).
    Values are weights, so they will be normalized and cumulated, and for time-stamps between full quarter hours,
    linear interpolation is performed.

    In other words, the higher the number the steeper the curve at this point of time.
    """

    def __init__(self, trading_distribution_definition=None):
        if trading_distribution_definition is None:
            # default for live operations
            #   be aware, that the configuration defines, what fraction of the total volume SHOULD
            #   be traded by that time, if the market does not provide the liquidity the actual
            #   traded volume might be less
            #   all products apart from WD must not trade the hour 02:00-03:00, otherwise there
            #      would be an overlap which is not supported therefore, the last 4 hours
            #      (=16 15 minutes slots) are set to 0. The "reservation" for the last 15 minutes slot
            #      is irrelevant in this regards, as it cannot be traded on the exchange.
            # Parameters of the Configuration:
            #    col 1: product
            #    col 2: maximal hours (incl) between trading start and delivery start where this curve still applies
            #    col 3: minimal hours (excl.) between trading start and delivery start where this curve still applies
            #    col 4: distribution in 15 minutes slots. The value for the distribution can be any value
            #           representing the portion of the volume that should be traded over the time related to
            #           the total of the volumes
            #               e.g. 100 slots all [1]
            #                    --> [1] = 1/100 of the total volume
            #               e.g. 90 slots all [1] + 10 slots all [5] =  90+50 = 140
            #                    --> [1] would be 1/140, [5] would be 5/140
            #           the standard configuration shows only [1] for trade and [0] for do not trade
            #    together the first 3 parameters are used to select the correct distribution:
            #        The WD product is special, as for the purpose of this distribution,
            #        the delivery start is always the start of the whole day,
            #        while the trading start is always the start of the hour.
            #        Thus trading_start can be after delivery start, and we allow negative values in the
            #        boundaries:
            #        e.g. WD, 4, -DAY --> trading start is 4 hours before delivery_start
            #                             until the product is rotated such that the reading start is
            #                             24 hours after delivery start: pick this line
            #                             (that then contains 28*4 = 112 values per quarterly hour)
            #             the values in that line define when trading should happen
            #                   the [4] * 4  : four times more in the first hour of the WD product
            #                                  than in the next 20 hours
            #                   the [1] * 84 : trade for 21 hours evenly
            #                                  (before the last 6 hours where there is no trading)
            #                   the [0] * 24 : do not plan to trade the last 6 hours of the period at all
            #                                  (note that this includes the time when the product is already closed)
            #             In contrast to all other distributions, for WD the right hand side of the distribution aligns
            #             with the delivery END, not start,
            #      e.g. DA, DAY + 3, DAY + 2: Trading starts DAY+3 hours before delivery
            #                   this line is typically used, if DA is Tuesday to Friday,
            #                   the [1] * 92        : trade for 23 hours evenly
            #                   the [0] * 15 + [0]  : do not trade for the last 4 hours
            #                                         and do not keep reserves for within-day
            #                   the [0] * 15 + [x]  : do not trade for the last 4 hours
            #                                         and keep relative x as reserves for within-day
            #
            #            DA, 2*DAY+3, 2*DAY+2 --> Trading starts 2 DAYS + 3 hours before delivery.
            #                   this is used for a single holiday in the middle of the weeks
            #                   (which can never occur with the current bank holiday calendar)
            #                   [1] * 96 + [1] * 92 means we trade linearely for 24+23 = 47 hours,
            #                   and stop trading 4h before delivery
            #
            #            DA, 3*DAY+4, 3*DAY+1 -->
            #                   This line is used on Friday if day ahead is Monday.
            #                   Here it is important to have 1h tolerance in the borders (i.e. DAY+4 until DAY+1)
            #                   so this curve gets selected even on weekends with the daylight saving switch
            #
            #            DA, 4*DAY+3, 4*DAY+2 -->
            #                   This line is used if Friday or is Monday is a holiday.
            #
            #            DA, 5*DAY+3, 5*DAY+2 -->
            #                   This line is used if Friday and Monday is a holiday, e.g. on easter.
            #
            #           ...
            #       e.g. WE/END:
            #           do not trade for the last 4 hours, before that trade for 71 h evenly
            #           and do not trade before that
            # values for reserves: (based on the samples below: (92*[1]; (92+96*x)*[1]):
            #       10% ~ 10, 21, 32, 43,  53,  64
            #       20% = 23, 47, 71, 95, 119, 143
            #
            #
            # Additional information on gas trading in general and the trading distributions:
            #
            #  Gas day is from 6am d+0 to 6am d+1 - As follows, "d" denotes a gas day starting at 6am.
            #
            #   WithinDay: Trading from d+0 -3h (i.e. 3am, so at the end of the previous gas day) to d+1
            #              Delivery from d+0 to d+1
            #   DayAhead: Trading from d+0 -3h to d+1,
            #             Delivery from d+1 to d+2
            #             Here d+2 denotes the next trading day - because of this we have multiple distributions for DA,
            #             accounting for various edge cases.
            #   Weekend: Trading from Wednesday d+0 -3h to Saturday 6am
            #            Delivery from Saturday 6am to Monday 6am
            #   Saturday: Trading from Thursday d+0 -3h to Saturday 6am
            #             Delivery from Saturday 6am to Sunday 6am
            #             Note: Not supported yet!
            #   Sunday: Trading from Wednesday 6am to Sunday 6am
            #           Delivery from Sunday 6am to Monday 6am
            #           Note: Not supported yet!
            #
            # On EEXS it is generally not possible to trade the last 4 hours (3h59m) before delivery start.
            #
            # Note:
            # The distribution is not stretched over the trading time window.
            # The distribution aligns with its right hand side to the delivery start (or delivery end for WD).
            # If the distribution is longer than the trading phase, then we start trading at a point
            # in time after the beginning of the distribution, such that the strategy will act like it
            # does when being behind schedule for closing the position (i.e. too aggressive behavior at the beginning)
            # If the distribution is shorter than the trading phase, then it is as if there were leading zeros
            # at the beginning of the distribution, and the strategy starts trading later.
            #
            # The distribution's right hand side is aligned with the delivery start of the product.
            # This means: 16 cells with zero at the right side of the distribution ==> finish trading 4h before delivery
            # and 20 cells with zero at the right side of the distribution ==> finish trading 5h before delivery

            trading_distribution_definition = {

                ("WD", 4, -DAY): [4] * 4 + [1] * 84 + [0] * 24,
                ("DA", DAY + 3, DAY + 2): [1] * 92 + [0] * 15 + [0],
                ("DA", 2 * DAY + 3, 2 * DAY + 2): [1] * 96 * 1 + [1] * 92 + [0] * 15 + [0],
                ("DA", 3 * DAY + 4, 3 * DAY + 1): [1] * 96 * 2 + [1] * 92 + [0] * 15 + [0],
                ("DA", 4 * DAY + 3, 4 * DAY + 2): [1] * 96 * 3 + [1] * 92 + [0] * 15 + [0],
                ("DA", 5 * DAY + 3, 5 * DAY + 2): [1] * 96 * 4 + [1] * 92 + [0] * 15 + [0],
                ("DA", 6 * DAY + 3, 6 * DAY + 2): [1] * 96 * 5 + [1] * 92 + [0] * 15 + [0],
                ("W/END", 6 * DAY + 3, 0): [0] * 96 * 3 + [1] * 96 * 2 + [1] * 92 + [0] * 15 + [0],

                # Trading on SAT/SUN products will be implemented in a followup ticket
                ("Saturday", 6 * DAY + 3, 0): [0] * 96 * 4 + [1] * 96 * 1 + [1] * 92 + [0] * 15 + [0],
                ("Sunday", 6 * DAY + 3, 0): [0] * 96 * 3 + [1] * 96 * 2 + [1] * 92 + [0] * 15 + [0],
            }

        def convert_trading_distribution(trading_distribution):
            """
            Transform the trading distribution from probability density to cumulative distribution.

            :param trading_distribution: single trading distribution
            :type trading_distribution: [int]
            :return: cumulated trading distribution(s) for each product
            :rtype: [float]
            """
            trading_distribution_cumulated = list(trading_distribution)
            for idx in range(len(trading_distribution_cumulated) - 1):
                trading_distribution_cumulated[idx + 1] += trading_distribution_cumulated[idx]

            distmax = float(max(trading_distribution_cumulated))
            if distmax > 0:
                for idx in range(len(trading_distribution_cumulated)):
                    trading_distribution_cumulated[idx] /= distmax
            return trading_distribution_cumulated

        self.trading_distribution_dict_cumulated = {k: convert_trading_distribution(d) for k, d in
                                                    trading_distribution_definition.items()}

    def get_distribution_value(self, product_type, delivery_start, delivery_end, trading_phase, timestamp):
        """
        Get the value of the distribution for the current timestamp.
        If the ts falls between 2 distribution segments, linear interpolation is used to calculate the value.

        :param product_type: "WD", "DA", "Saturday", "Sunday" or "W/END"
        :type product_type: str
        :param delivery_start: timestamp
        :type delivery_start: int
        :param delivery_end: timestamp
        :type delivery_end: int
        :param trading_phase: (`<unix_timestamp_start>`, `<unix_timestamp_end>`, `<state>`)
        :type trading_phase: (int, int, str)
        :param timestamp: current timestamp as custom_act gets it
        :type timestamp: int
        :return: value of the distribution
        :rtype: float
        """

        # calculate delta between trading and delivery and find applicable distribution
        trading_start_delivery_delta_hours = (delivery_start - trading_phase[0]) / COMMON.HOUR
        trading_distribution_cumulated = None
        for (filter_type, filter_h_start, filter_h_end), value in self.trading_distribution_dict_cumulated.items():
            if product_type == filter_type and filter_h_end < trading_start_delivery_delta_hours <= filter_h_start:
                trading_distribution_cumulated = value
                break
        if trading_distribution_cumulated is None:
            return 0.

        if product_type == "WD":
            # this is special, because WD can be traded although delivery has already started
            index_from_end = delivery_end - timestamp
        else:
            index_from_end = delivery_start - timestamp
        if index_from_end < 0:
            return trading_distribution_cumulated[-1]
        index_from_end /= float(COMMON.QUARTER)
        index_from_end += 1

        # linear interpolation between values
        floor = int(math.floor(index_from_end))
        ceil = int(math.ceil(index_from_end))
        if floor == ceil:
            try:
                return trading_distribution_cumulated[-floor]
            except IndexError:
                return 0.
        floor_distance = index_from_end - floor
        ceil_distance = ceil - index_from_end
        try:
            return (
                trading_distribution_cumulated[-floor] * ceil_distance
                + trading_distribution_cumulated[-ceil] * floor_distance
            )
        except IndexError:
            return 0.


class CustomStrategy(STRATEGY.GasStrategy):

    def __init__(self, autotrader_instance, strategy_id, caption, strategy_package_name,
                 trading_distribution_definition=None, *args, **kwargs):
        super(CustomStrategy, self).__init__(autotrader_instance, strategy_id, caption, strategy_package_name, **kwargs)
        self.parameters = PARAMS.Parameters()
        self.maximum_order_book = 0
        self.delivery_area = None
        self.supported_products_types = ("WD", "DA", "W/END")
        self.distribution_calculator = TradingDistributionCalculator(trading_distribution_definition)
        self.broker_id = TRAYPORT_BROKER_ID
        self.price_tolerance = 0
        self.min_qty_placement = None

    def get_traded_amount_timeseries(self, products):
        result = defaultdict(int)  # ts -> value
        for product in products:
            trades = product.trades.get(trade_filter=COMMON.TradeFilter.own, portfolio_key=self.strategy_id)
            for t in trades:
                for ts in range(product.delivery_start, product.delivery_end, COMMON.HOUR):
                    # Note: We can use int here, because min_quantity and qty_tick are integers on
                    #       all instruments relevant to the gas position closer.
                    result[ts] += int(t.quantity * -1 if t.sell_delivery_area else t.quantity)
        return result

    @staticmethod
    def calculate_and_sum(formula, ts_from, ts_until, *parameters):
        # now just sum up
        return sum(CustomStrategy.calculate(formula, ts_from, ts_until, *parameters).values())

    @staticmethod
    def calculate(formula, ts_from, ts_until, *parameters):
        """
        Apply the formula "element-wise" to the time-series, in blocks of hours between ts_from and ts_until.

        :type formula: function
        :param ts_from: timestamp from
        :type ts_from: int
        :param ts_until: timestamp until
        :type ts_until: int
        :param parameters: List of timeseries with as many elements as the function takes attributes
        :type parameters: list
        :rtype: dict
        """
        result = defaultdict(float)
        try:
            for ts in range(ts_from, ts_until, 3600):
                result[ts] = formula(*[param[ts] for param in parameters])
        except (KeyError, TypeError):
            log.debug("cannot calculate")
            return result
        # now just sum up
        return result

    def get_price_with_aon_check(self, is_sell, public_orders, tick_size, quantity, placement_price):
        # aon dead zone problem
        if is_sell:
            check_orders = [o for o in public_orders if o.direction == COMMON.Direction.buy]
            if not check_orders:
                return placement_price
            check_orders.sort(key=lambda order: order.price, reverse=True)
            non_aon_orders = [
                o for o in check_orders
                if o.execution_restriction == COMMON.ExecutionRestriction.non and o.price >= placement_price
            ]
            if non_aon_orders or check_orders[0].quantity <= quantity:
                return placement_price
            self.debug_log(
                "sell price calculated based on aon check: %s, %s, %s, %s" % (
                    placement_price, quantity, check_orders[0].quantity, check_orders[0].price)
            )
            return max(placement_price, check_orders[0].price + tick_size)
        else:
            check_orders = [o for o in public_orders if o.direction == COMMON.Direction.sell]
            if not check_orders:
                return placement_price
            check_orders.sort(key=lambda order: order.price)
            non_aon_orders = [
                o for o in check_orders
                if o.execution_restriction == COMMON.ExecutionRestriction.non and o.price <= placement_price
            ]
            if non_aon_orders or check_orders[0].quantity <= quantity:
                return placement_price
            log.debug("buy price calculated based on aon check: %s, %s, %s, %s", placement_price, quantity,
                      check_orders[0].quantity, check_orders[0].price)
            return min(placement_price, check_orders[0].price - tick_size)

    def get_slots(self, product, is_sell, total_distributable_load, factor_delta, target_factor, slot_size,
                  factor_distributable_load, default_price_purchase, default_price_sell,
                  immediate_vesting_price_purchase, immediate_vesting_price_sell, limit_maximum_purchase_price,
                  limit_minimum_sales_price):
        # get exchange properties for current product, to get minimum quantity and step
        properties = self.get_trayport_properties(product_id=product.product_id)
        if self.maximum_order_book < properties.min_quantity:
            halt_reason = ("The configured maximum_order_book parameter ({}) is less than the instrument's"
                           " minimum quantity ({})").format(self.maximum_order_book, properties.min_quantity)
            self.warn_log(halt_reason)
            self.on_strategy_emergency_update(True, halt_reason=halt_reason, remove_orders=True,
                                              username=COMMON.Exchange.autotrader)
            return []
        tick_size = properties.price_tick

        def round_qty(qty, max_amount=None):
            return int(SU.load_rounder(qty, properties.min_quantity, properties.qty_tick, max_amount=max_amount))

        def limit_purchase(price):
            if price is None or limit_maximum_purchase_price is None:
                return price
            return round(math.floor((min(price, limit_maximum_purchase_price) + 0.0001) / tick_size) * tick_size, 4)

        def limit_sell(price):
            if price is None or limit_minimum_sales_price is None:
                return price
            return round(math.ceil((max(price, limit_minimum_sales_price) - 0.0001) / tick_size) * tick_size, 4)

        product_indicators = product.orders.indicators(self.delivery_area)

        if len(product_indicators) < 6:
            log.debug("product_indicators for {} are almost empty (indicator length = {}, num orders = {}), "
                      "no action".format(product.name, len(product_indicators), len(product.orders.get())))
            return []
        orders = []

        # If the minimum quantity is bigger than the quantity tick, we have to be careful when closing
        # the last remaining quantity, to not end up with less than the min quantity open volume.
        # aon_closing does not mean that we always place aon orders, just that we may have to place such orders.
        aon_closing = properties.min_quantity > properties.qty_tick

        indicator = product_indicators[0].mw_prices

        global_info = "fd:{:.2f}_tf:{:.2f}_ss:{:.0f}_tdl:{:.0f}_fdl:{:.0f}".format(factor_delta, target_factor,
                                                                                   slot_size, total_distributable_load,
                                                                                   factor_distributable_load)

        log.debug(
            "default prices: {}, {} - immediate execution prices: {}, {} - limit prices: {}, {} - "
            "indicators: {}/{}, {}/{}"
            .format(
                default_price_sell, default_price_purchase, immediate_vesting_price_sell,
                immediate_vesting_price_purchase, limit_minimum_sales_price, limit_maximum_purchase_price,
                indicator[1][0], indicator[1][8], indicator[0][0], indicator[0][8]
            )
        )

        # check, if we can actively hit a profitable order
        quantity = 0.
        public_orders = product.orders.get(order_filter=COMMON.OrderFilter.public,
                                           delivery_area_id=self.delivery_area)

        hitting_quantity = int(min(total_distributable_load, self.maximum_order_book))

        force_order = (FORCE, COMMON.Direction.sell, 0., 0., "", False)

        if is_sell and immediate_vesting_price_sell is not None:
            matching_bids = [
                o for o in public_orders
                if (
                    o.direction == COMMON.Direction.buy
                    and o.price >= immediate_vesting_price_sell
                    and o.execution_restriction != COMMON.ExecutionRestriction.aon
                )
            ]
            quantity = min(hitting_quantity, sum(o.quantity for o in matching_bids))
            # make sure, at least minimum load is set
            quantity = round_qty(quantity, self.maximum_ask)
            if aon_closing and total_distributable_load - quantity < properties.min_quantity:
                # Reduce immediate vesting quantity, so we have min_qty left afterwards.
                quantity = round_qty(total_distributable_load - properties.min_quantity, self.maximum_ask)
            force_order = (FORCE, COMMON.Direction.sell, quantity, immediate_vesting_price_sell,
                           "{}_{}".format(ForceOrderMode.immediate_vesting, global_info), False)
        elif not is_sell and immediate_vesting_price_purchase is not None:
            matching_asks = [
                o for o in public_orders
                if (
                    o.direction == COMMON.Direction.sell
                    and o.price <= immediate_vesting_price_purchase
                    and o.execution_restriction != COMMON.ExecutionRestriction.aon
                )
            ]
            quantity = min(hitting_quantity, sum(o.quantity for o in matching_asks))
            # make sure, at least minimum load is set
            quantity = round_qty(quantity, self.maximum_bid)
            if aon_closing and total_distributable_load - quantity < properties.min_quantity:
                # Reduce immediate vesting quantity, so we have min_qty left afterwards.
                quantity = round_qty(total_distributable_load - properties.min_quantity, self.maximum_bid)
            force_order = (FORCE, COMMON.Direction.buy, quantity, immediate_vesting_price_purchase,
                           "{}_{}".format(ForceOrderMode.immediate_vesting, global_info), False)

        # no hitting -> place aggressive order
        if (
                quantity == 0
                and (factor_delta > 0.2 or (factor_delta > 0.1 and target_factor > 0.9) or (target_factor > 0.97))
                and indicator[1][0] is not None
                and indicator[0][0] is not None
        ):

            # For the force order, we reduce the maximum orderbook quantity to half the original value if possible
            # (Note: At this place, we have already ensured that self.maximum_order_book >= properties.min_quantity)
            max_force_orderbook = max(self.maximum_order_book * 0.5, properties.min_quantity)
            quantity = int(min(factor_distributable_load,
                               max_force_orderbook,
                               slot_size))
            # get historic indication of spread size
            indicators = product_indicators[-5:-1]
            if len(indicators) == 4:
                sell_prices = [i.mw_prices[1][0] for i in indicators]
                buy_prices = [i.mw_prices[0][0] for i in indicators]
                if None not in sell_prices and None not in buy_prices:
                    avg_spread = sum([s - b for s, b in zip(sell_prices, buy_prices)]) * 0.25
                    spread_safety_distance = avg_spread * 0.3
                    if spread_safety_distance <= properties.price_tick:
                        spread_safety_distance = 0.
                    if factor_delta > 0.25 or target_factor > 0.95:
                        spread_safety_distance = -10.  # deactivate safety distance
                    aon = False
                    if is_sell:
                        if factor_delta > 0.4 or target_factor > 0.98:
                            placement = indicator[0][10]
                            force_mode = ForceOrderMode.aggress
                        else:
                            placement = indicator[1][0] - properties.price_tick
                            force_mode = ForceOrderMode.front_runner
                        if placement < spread_safety_distance + indicator[0][0]:
                            # to near to the other side, retract completely
                            quantity = 0

                        quantity = round_qty(quantity, self.maximum_ask)
                        # check if there is enough total_distributable_load left for non-aon order
                        if aon_closing and total_distributable_load - quantity < properties.min_quantity:
                            # We have 2 options: Increase or decrease the quantity to make it work.
                            # First we check whether we can stay within the target_factor
                            if factor_distributable_load > 2 * properties.min_quantity:
                                # decrease exposed quantity, such that the remaining load is larger than min quantity.
                                quantity = round_qty(factor_distributable_load - properties.min_quantity)
                            elif total_distributable_load > 2 * properties.min_quantity:
                                # decrease exposed quantity, such that the remaining load is larger than min quantity.
                                quantity = round_qty(total_distributable_load - properties.min_quantity)
                            else:
                                # increase exposed quantity for aon-order to total distributable load
                                quantity = round_qty(total_distributable_load)
                                aon = True
                        if (
                                aon
                                and force_mode == ForceOrderMode.aggress
                                and product_indicators[0].eur_quantities[0][0] < quantity
                        ):
                            self.debug_log("Cannot aggress due to AON restriction. Placing 1 tick in front", product)
                            placement = indicator[0][0] + properties.price_tick
                            force_mode = ForceOrderMode.almost_aggress
                        force_order = (FORCE, COMMON.Direction.sell, quantity,
                                       self.get_price_with_aon_check(is_sell, public_orders, tick_size, quantity,
                                                                     limit_sell(placement)),
                                       "{}_{}_ssd:{:.2f}".format(force_mode, global_info, spread_safety_distance), aon)
                    else:
                        if factor_delta > 0.4 or target_factor > 0.98:
                            placement = indicator[1][10]
                            force_mode = ForceOrderMode.aggress
                        else:
                            placement = indicator[0][0] + properties.price_tick
                            force_mode = ForceOrderMode.front_runner
                        if placement > indicator[1][0] - spread_safety_distance:
                            # to near to the other side, retract completely
                            quantity = 0.

                        quantity = round_qty(quantity, self.maximum_bid)
                        # check if there is enough total_distributable_load left for non-aon order
                        if aon_closing and total_distributable_load - quantity < properties.min_quantity:
                            # We have 2 options: Increase or decrease the quantity to make it work.
                            # First we check whether we can stay within the target_factor
                            if factor_distributable_load > 2 * properties.min_quantity:
                                # decrease exposed quantity, such that the remaining load is larger than min quantity.
                                quantity = round_qty(factor_distributable_load - properties.min_quantity)
                            elif total_distributable_load > 2 * properties.min_quantity:
                                # decrease exposed quantity, such that the remaining load is larger than min quantity.
                                quantity = round_qty(total_distributable_load - properties.min_quantity)
                            else:
                                # increase exposed quantity for aon-order to total distributable load
                                quantity = round_qty(total_distributable_load)
                                aon = True
                        if (
                                aon
                                and force_mode == ForceOrderMode.aggress
                                and product_indicators[0].eur_quantities[1][0] < quantity
                        ):
                            self.debug_log("Cannot aggress due to AON restriction. Placing 1 tick in front", product)
                            placement = indicator[1][0] - properties.price_tick
                            force_mode = ForceOrderMode.almost_aggress
                        force_order = (FORCE, COMMON.Direction.buy, quantity,
                                       self.get_price_with_aon_check(is_sell, public_orders, tick_size, quantity,
                                                                     limit_purchase(placement)),
                                       "{}_{}_ssd:{:.2f}".format(force_mode, global_info, spread_safety_distance), aon)

        orders.append(force_order)

        factor_distributable_load -= quantity
        if aon_closing:
            # For simplicity, we trade the last min_qty only as a force order,
            # so we do not have to worry about AON for the other order types.
            # This is achieved by setting the removing a reserve of min_qty from the load that is
            # distributable by the other order types.
            factor_distributable_load = max(0, factor_distributable_load - properties.min_quantity)
        # place for normal nursing
        quantity = 0.
        if factor_delta > 0.1:
            quantity = round_qty(min(factor_distributable_load, self.maximum_order_book, slot_size * 2))
            if is_sell and indicator[1][8] is not None:
                orders.append((CONSERVATIVE, COMMON.Direction.sell, quantity, limit_sell(indicator[1][8]),
                               "cs_{}".format(global_info), False))
            elif not is_sell and indicator[0][8] is not None:
                orders.append((CONSERVATIVE, COMMON.Direction.buy, quantity, limit_purchase(indicator[0][8]),
                               "cs_{}".format(global_info), False))
            else:
                orders.append((CONSERVATIVE, COMMON.Direction.buy, 0., 0.,
                               "cs_{}".format(global_info), False))
                quantity = 0.
        else:
            orders.append((CONSERVATIVE, COMMON.Direction.buy, 0., 0.,
                           "cs_{}".format(global_info), False))

        factor_distributable_load -= quantity
        # place big rest load at reference price
        if default_price_sell is not None and default_price_purchase is not None:
            quantity = round_qty(min(factor_distributable_load, self.maximum_order_book * 0.5, slot_size * 4))
            if is_sell:
                price = default_price_sell if indicator[1][8] is None else \
                    max(indicator[1][8] + properties.price_tick, default_price_sell)
                orders.append((LUCKY, COMMON.Direction.sell, quantity, limit_sell(price),
                               "lu_{}".format(global_info), False))
            else:
                price = default_price_purchase if indicator[0][8] is None else \
                    min(indicator[0][8] - properties.price_tick, default_price_purchase)
                orders.append((LUCKY, COMMON.Direction.buy, quantity, limit_purchase(price),
                               "lu_{}".format(global_info), False))
        else:
            orders.append((LUCKY, COMMON.Direction.buy, 0., 0.,
                           "lu_{}".format(global_info), False))
        return orders

    @staticmethod
    def calculate_actual_traded_factor(traded, remaining_position):
        # in case of the opposite direction (overtrade) it is difficult to decide what the desired behavior would be
        # therefore it is best to "buyback" at the same rate as the target factor is, disregarding
        # how much we overshot the position
        if traded * remaining_position > 0:  # opposite direction
            return 0.

        total_applicable_volume = abs(traded) + abs(remaining_position)

        return 0. if total_applicable_volume == 0. else abs(traded) / float(total_applicable_volume)

    def calculate_product_placement(self, product, traded_timeseries_dict, position_dict, timestamp):
        # a special: for the WD product, we have to modify the delivery start for loading of the traded and
        # position series, because we need the whole day from the timeseries, but the product trades for a
        # fraction of the day (current hour + 3 until end of trading day)

        properties = self.get_trayport_properties(product.product_id)
        if product.product_type == "WD":
            delivery_start, delivery_end = calculate_wd_delivery_borders(product.delivery_end)
        else:
            delivery_start, delivery_end = product.delivery_start, product.delivery_end

        remaining_position = self.calculate_and_sum(get_remaining_position, delivery_start, delivery_end,
                                                    position_dict, traded_timeseries_dict)

        # a negative value means we wish to buy
        position = self.calculate_and_sum(get_value_or_zero, delivery_start, delivery_end, position_dict)

        # a positive value means we have bought a negative that we sold
        traded = self.calculate_and_sum(get_value_or_zero, delivery_start, delivery_end, traded_timeseries_dict)

        # calculate the ratio between remaining and traded
        actual_traded_factor = self.calculate_actual_traded_factor(traded, remaining_position)

        # calculate target factor based on target distributions - i.e. how much should have been traded
        target_factor = self.distribution_calculator.get_distribution_value(product.product_type,
                                                                            delivery_start, delivery_end,
                                                                            product.trading_phase(self.delivery_area),
                                                                            timestamp)

        # calculate current target volume
        factor_delta = target_factor - actual_traded_factor

        # Until here, we used units of energy (e.g. MWh), now we convert to a unit of power (e.g. MW)
        product_interval_factor = float(COMMON.HOUR) / (product.delivery_end - product.delivery_start)
        total_distributable_load = int(abs(remaining_position * product_interval_factor))

        slot_size = max(properties.min_quantity, math.ceil(
            max(abs(remaining_position), abs(position), abs(traded)) * 0.1 * product_interval_factor))
        slot_size = SU.load_rounder(slot_size, properties.min_quantity, properties.qty_tick)

        # calculate the remaining distributable load to stay below the target factor (factor_distributable_load)
        # if traded load below target factor
        if factor_delta > 0:
            # To calculate the factor distributable load we need to understand the difference between the
            # (total distributable load) which is calculated from the remaining load and the (total load) that would
            # have been available if no trades have been done. Such a "total load" can be then used to calculate
            # the factor distributable load:
            #           factor_distributable_load = (total load) * (factor_delta)
            # and total load can be calculated as:
            #           total_distributable_load / (1 - actual_traded_factor)
            # rounding to counter floating point errors
            # Note: when target_factor = 1 -> factor_distributable_load == total_distributable_load
            factor_distributable_load = int(decimal.Decimal(
                total_distributable_load / (1 - actual_traded_factor) * factor_delta
            ).quantize(decimal.Decimal('1'), rounding=decimal.ROUND_HALF_UP))

        # if traded load at or above target factor
        else:
            factor_distributable_load = 0

        self.debug_log(
            "Work - traded: {}, remaining: {}, actual_traded_factor: {}, target_factor: {}, "
            "factor_delta: {}, total_distributable_load: {}, factor_distributable_load: {}"
            .format(traded, remaining_position, actual_traded_factor, target_factor, factor_delta,
                    total_distributable_load, factor_distributable_load),
            product
        )

        # get reference prices for placement
        default_price_purchase = \
            self.parameters.strategy_price_purchase.min_of_range(product.delivery_start, product.delivery_end)
        default_price_sell = \
            self.parameters.strategy_price_sales.max_of_range(product.delivery_start, product.delivery_end)

        # get immediate execution prices
        immediate_vesting_price_purchase = self.parameters.strategy_price_purchase_immediate_vesting.min_of_range(
            product.delivery_start, product.delivery_end)
        immediate_vesting_price_sell = self.parameters.strategy_price_sales_immediate_vesting.max_of_range(
            product.delivery_start, product.delivery_end)

        # get limit prices
        limit_maximum_purchase_price = self.parameters.strategy_limit_maximum_purchase_price.min_of_range(
            product.delivery_start, product.delivery_end)
        limit_minimum_sales_price = self.parameters.strategy_limit_minimum_sales_price.max_of_range(
            product.delivery_start, product.delivery_end)

        # retrieve the order placement wishes
        placements = self.get_slots(product, remaining_position >= 0., total_distributable_load, factor_delta,
                                    target_factor, slot_size, factor_distributable_load, default_price_purchase,
                                    default_price_sell, immediate_vesting_price_purchase, immediate_vesting_price_sell,
                                    limit_maximum_purchase_price, limit_minimum_sales_price)

        slots_to_place = []
        for name, direction, quantity, price, comment, aon in placements:
            price_range_low, price_range_high = self.apply_price_tolerance(name, direction, price, comment)
            # place slots with added price and quantity ranges
            if not quantity or not self.min_qty_placement:
                quantity_range_lo = None
            else:
                quantity_range_lo = min(quantity, self.min_qty_placement)
            slot = STRATEGY.PositionSlot(
                name, direction, quantity, price, price_range_lo=price_range_low,
                price_range_hi=price_range_high,
                quantity_range_lo=quantity_range_lo if not aon else None,
                execution_restriction=COMMON.ExecutionRestriction.aon if aon else COMMON.ExecutionRestriction.non,
                tick_size=properties.price_tick, broker_id=self.broker_id, info=comment)
            slots_to_place.append(slot)

        # deduct our block quantity from traded_timeseries_dict and position_dict
        # ATTENTION: delivery_start is the beginning of the calculation, not the product
        for ts in range(delivery_start, delivery_end, COMMON.HOUR):
            traded_timeseries_dict[ts] -= traded
            position_dict[ts] -= position

        return slots_to_place

    def custom_act(self, log_data, timestamp, products=None):
        # what we can currently trade
        active_products = [product for product in self.product_filter(self.exchange.products.get_all())
                           if product.state(self.delivery_area) == COMMON.DeliveryAreaState.active]

        if not active_products:
            return

        min_delivery_ts = min(p.delivery_start for p in active_products)
        max_delivery_ts = max(p.delivery_end for p in active_products)

        # deduct one day from min_ts, because we always start with a WD product that has a dynamic start#
        # and we have to cover the whole starting day
        min_delivery_ts -= COMMON.DAY

        # get all products delivering in that range
        range_products = [
            p for p in self.exchange.products.get_all()
            if p.delivery_start < max_delivery_ts and p.delivery_end > min_delivery_ts
        ]

        # calculate traded volume timeseries based on all products
        # Negative for what we solf, positive what we bought
        traded_timeseries = self.get_traded_amount_timeseries(range_products)

        # get position timeseries for this interval
        def position_formula(pos_short, pos_long):
            return (pos_long or 0) - (pos_short or 0)

        # target position. Positive for long (need to sell), negative for short (need to buy)
        position = self.calculate(position_formula,
                                  min_delivery_ts, max_delivery_ts,
                                  self.parameters.strategy_position_tradable_position_short,
                                  self.parameters.strategy_position_tradable_position_long)

        # now iterate through active products, determining order placement
        # products are sorted by delivery interval, so we start with the more liquid products
        for product in sorted(active_products, key=lambda p: (p.delivery_end - p.delivery_start, p.product_id),
                              reverse=True):
            # get wishes for order placement
            # CAVE! this function takes the timeseries, decides which block of traded qty and position is his
            # and MODIFIES the traded_timeseries and position for the next product
            slots_to_place = self.calculate_product_placement(
                product, traded_timeseries, position, timestamp)

            for slot in slots_to_place:
                self.place_slot_and_log(product, timestamp, slot)

    def apply_price_tolerance(self, name, direction, price, comment):
        """
        Return the price with price tolerance applied.

        :param name: The slot_name of the slot.
        :type name: str
        :param direction: buy or sell. The price tolerance is only applied in one direction, such that we
                          immediately move to a price better for us (less attractive for the counter party), but
                          only reluctantly move to a price that is worse for us (more attractive for the counter party).
        :type direction: str
        :param price: The original price, to which we apply the tolerance
        :type price: float
        :param comment: The slot information (=stats=mode) of the slot. We do not apply any price tolerance to
                        immeditate vesting and aggressing, as this would potentially prevent us from making a
                        trade when we want to.
        :type comment: str
        :return: The minimum and maximum price range.
        :rtype: (float, float)
        """
        if name == FORCE and comment.partition("_")[0] in (ForceOrderMode.immediate_vesting, ForceOrderMode.aggress):
            return price, price  # Disable price tolerance for immediate vesting and aggressing
        else:
            # Otherwise 1-sided price tolerance: If the price gets worse (for us),
            # we only change the price if the change exceeds the tolerance
            if direction == COMMON.Direction.sell:
                # If the price got lower compared to the last iteration (i.e. worse for us), but the old price is
                # below (new) price+self.price_tolerance, then don't adjust our price downwards.
                # If the price got higher (better from us), immediately follow, to never waste money.
                return price, price + self.price_tolerance
            else:
                return price - self.price_tolerance, price

    def place_slot_and_log(self, product, timestamp, slot):
        self.debug_log("(duration: {}): {}".format(product.duration / COMMON.HOUR, slot.short(True, True)), product)
        self.place_slots({}, product, timestamp, self.delivery_area,
                         [slot], execmode=COMMON.InternalExecutionMode.exchange_base_price)

    def on_strategy_update(self, strategy_json):
        super(CustomStrategy, self).on_strategy_update(strategy_json)
        self.maximum_order_book = int(abs(self.strategy_settings["maximum_order_book"] or MAX_ORDERBOOK_DEFAULT))

        # set parameters for bot-race-protection if available, else use default parameters
        self.price_tolerance = self.strategy_settings.get("price_tolerance", PRICE_TOLERANCE)
        self.min_qty_placement = self.strategy_settings.get("min_qty_placement", MIN_QTY_PLACEMENT)
        if self.min_qty_placement is not None:
            self.min_qty_placement = int(self.min_qty_placement)
        self.parameters.update(strategy_json)
        self.delivery_area = self.delivery_areas[0]
        self.debug_log("On strategy update of gas position closer")

        def mk_ts_exp(ts):
            return dict((begin, value) for begin, value in ts.items())

        self.api_export_timeseries(
            {
                "pos_long": (
                    "Position Long", "MW", "MW", COMMON.HOUR,
                    mk_ts_exp(self.parameters.strategy_position_tradable_position_long)
                ),
                "pos_short": (
                    "Position Short", "MW", "MW", COMMON.HOUR,
                    mk_ts_exp(self.parameters.strategy_position_tradable_position_short)
                )
            }
        )

    def product_filter(self, products):
        """
        Filter products we want to trade.

        :param products: all available products
        :type products: [Product]
        """
        return [product for product in products
                if product.product_type in self.supported_products_types
                and "dummy" not in product.product_id]

    def custom_on_order_book_update(self, orders, timestamp):
        self.act(timestamp)

    def custom_on_trade_update(self, trades, timestamp):
        self.act(timestamp)

    def custom_on_public_trade_update(self, trades, timestamp):
        pass

    def custom_on_products_update(self, products, timestamp):
        self.act(timestamp)

    def custom_on_products_queue(self, products, timestamp):
        pass

    def custom_on_timer(self, timestamp):
        self.act(timestamp)
