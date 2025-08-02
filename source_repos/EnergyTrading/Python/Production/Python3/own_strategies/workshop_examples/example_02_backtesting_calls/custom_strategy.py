#!/usr/bin/python3
# -*- coding: utf-8 -*-
import collections
import logging

import autotrader_lib.common as COMMON
import autotrader_core.strategy as STRAT
import autotrader_core.strategy_utils as SU
import autotrader_lib.cet_util as CETUTIL
from six.moves import range

SELL_SLOTNAME = "sell_slot"
BUY_SLOTNAME = "buy_slot"
log = logging.getLogger('autotrader.example_02_backtesting_calls')


class CustomStrategy(STRAT.Strategy):
    def __init__(self, autotrader_instance, strategy_id, caption, strategy_package_name):
        super(CustomStrategy, self).__init__(autotrader_instance, strategy_id, caption, strategy_package_name)
        self.smallest_timestep = COMMON.QUARTER
        self.price_forecasts = STRAT.StrategyTimeSeries()

        self.strategy_position_tradable_position_long = STRAT.StrategyTimeSeries()
        self.strategy_position_tradable_position_short = STRAT.StrategyTimeSeries()
        self.strategy_price_purchase = STRAT.StrategyTimeSeries()
        self.strategy_price_sales = STRAT.StrategyTimeSeries()

        self.ts_by_name = {
            "price_forecasts": self.price_forecasts,
            COMMON.StrategyJsonKey.TS.pos_sell: self.strategy_position_tradable_position_long,
            COMMON.StrategyJsonKey.TS.pos_buy: self.strategy_position_tradable_position_short,
            COMMON.StrategyJsonKey.TS.price_buy: self.strategy_price_purchase,
            COMMON.StrategyJsonKey.TS.price_sell: self.strategy_price_sales,
        }

        # dictionary to keep track of traded amounts
        self.traded = {}

    def _get_traded_amount(self, start_ts, end_ts):
        """get traded amount per timestep

        :type start_ts: int
        :type end_ts: int
        :return: dict[int, float]
        """
        # overlapping products
        products = self.exchange.products.get_overlapping_with_timerange(start_ts, end_ts)
        net_traded = collections.defaultdict(float)
        for p in products:
            own_trades = p.trades.get(
                delivery_area=self.delivery_area_id,
                trade_filter=COMMON.TradeFilter.own,
                portfolio_key=self.strategy_id
            )
            traded_sell = sum(t.quantity for t in own_trades if t.direction == COMMON.Direction.sell)
            traded_buy = sum(t.quantity for t in own_trades if t.direction == COMMON.Direction.buy)
            net_val = round(traded_buy - traded_sell, SU.PREC_DIGITS)
            for ts in range(p.delivery_start, p.delivery_end, self.smallest_timestep):
                net_traded[ts] += net_val
        return net_traded

    def custom_act(self, log_data, timestamp, products=None):
        """when act is called, mostly reacting to changes in products

        :type log_data: dict
        :type timestamp: float
        :type products: list[APITR.Product]
        :return:
        """
        self.debug_log(text="Running")

        #############################
        # Act on product one by one #
        #############################
        if not products:
            return

        min_start_ts = min(p.delivery_start for p in products)
        max_end_ts = max(p.delivery_end for p in products)
        self.traded = self._get_traded_amount(min_start_ts, max_end_ts)

        for product in products:
            self.act_for_product(product, timestamp)

    def custom_act_for_product(self, log_data, product, timestamp, *args, **kwargs):
        self.debug_log(text="Act for product", product=product)

        #################################
        # Filter only tradable products #
        #################################
        if not product.is_tradable(timestamp, self.delivery_area_id):
            start_ts, end_ts, state = product.trading_phase(self.delivery_area_id)
            self.debug_log(text="skip untradable product. state: {}, interval: {}-{}, now:{}".format(
                state,
                CETUTIL.utc_ts2cet_str(start_ts, True, True),
                CETUTIL.utc_ts2cet_str(end_ts, True, True),
                CETUTIL.utc_ts2cet_str(timestamp, True, True),
            ),
                product=product
            )

        #####################################
        # find left over positions to trade #
        #####################################
        # get traded amount
        traded_vals = [self.traded[ts] for ts in range(product.delivery_start, product.delivery_end, COMMON.QUARTER)]
        most_bought = max(0, max(traded_vals))
        most_sold = min(0, min(traded_vals))
        common_traded = most_bought + most_sold
        common_traded = round(common_traded, 2)

        # get positions set in periotheus (or by REST API)
        product_interval = (product.delivery_start, product.delivery_end)
        long_target = self.strategy_position_tradable_position_long.get(product_interval, 0.) or 0.
        short_target = self.strategy_position_tradable_position_short.get(product_interval, 0.) or 0.
        open_position = short_target - long_target

        # calculate left over
        rest = round(open_position - common_traded, SU.PREC_DIGITS)

        ##############################################################
        # create slots with price and quantity rounded to tick sizes #
        ##############################################################

        buy_slot = STRAT.PositionSlot(BUY_SLOTNAME, COMMON.Direction.buy, quantity=0, price=0)
        sell_slot = STRAT.PositionSlot(SELL_SLOTNAME, COMMON.Direction.sell, quantity=0, price=0)

        if rest > 0:
            buy_slot.quantity = rest
            buy_slot.price = self.strategy_price_purchase.get(product_interval)
            if buy_slot.price is not None:
                buy_slot.price = round(buy_slot.price, SU.PREC_DIGITS)
        elif rest < 0:
            sell_slot.quantity = -rest
            sell_slot.price = self.strategy_price_sales.get(product_interval)
            if sell_slot.price is not None:
                sell_slot.price = round(sell_slot.price, SU.PREC_DIGITS)

        #############################################
        # found best public orders for this product #
        #############################################

        best_public_buy_price = None
        best_public_sell_price = None
        indicators = product.orders.indicators(self.delivery_area_id)
        if indicators:
            best_public_buy_price = indicators[0].mw_prices[0][0]
            best_public_sell_price = indicators[0].mw_prices[1][0]

        #####################################
        # place slots with slot information #
        #####################################

        # place buy slot
        buy_slot.info = (
            "buy_state:normal||trd:{:.1f}||net_target_pos:{}||"
            "rest:{}||{}".format(
                common_traded, open_position, rest, po_slot_info(best_public_buy_price, best_public_sell_price)
            )
        )

        sell_slot.info = (
            "sell_state:normal||trd:{:.1f}||net_target_pos:{}||"
            "rest:{}||{}".format(
                common_traded, open_position, rest, po_slot_info(best_public_buy_price, best_public_sell_price)
            )
        )

        # place buy and sell slot
        slot_responses = self.place_slots({}, product, timestamp, self.delivery_area_id,
                                          [buy_slot, sell_slot], [],
                                          limit_minimum_sales_price=-9999,
                                          limit_maximum_purchase_price=9999,
                                          execmode=COMMON.InternalExecutionMode.average_price)

        self.debug_log(text="Buy Slot Placement Results: {}".format(slot_responses), product=product)

        # place sell slot
        sell_slot.info = (
            "sell_state:normal||trd:{:.1f}||net_target_pos:{}||"
            "rest:{}||{}".format(
                common_traded, open_position, rest, po_slot_info(best_public_buy_price, best_public_sell_price)
            )
        )

        slot_responses = self.place_slots({}, product, timestamp, self.delivery_area_id,
                                          [sell_slot], [],
                                          limit_minimum_sales_price=-9999,
                                          limit_maximum_purchase_price=9999,
                                          execmode=COMMON.InternalExecutionMode.exchange_base_price)

        self.debug_log(text="Sell Slot Placement Results: {}".format(slot_responses), product=product)

    def handle_update_timeseries(self, timeseries_update):
        # "Never update timeseries which come from Periotheus with a steering call,
        # because in Production the steering call's values will be overwritten by Periotheus regularly."

        ts_name = timeseries_update["ts_name"]
        timeseries_to_update = self.ts_by_name[ts_name]

        # if the timeseries is a periotheus timeseries
        if ts_name in (COMMON.StrategyJsonKey.TS.pos_sell,
                       COMMON.StrategyJsonKey.TS.pos_buy,
                       COMMON.StrategyJsonKey.TS.price_buy,
                       COMMON.StrategyJsonKey.TS.price_sell):
            self.warn_log("Updating periotheus timeseries: {}! "
                          "These values will be overwritten by the next periotheus update sent to the autotrader."
                          .format(ts_name))
        for ts in range(int(timeseries_update["start"]),
                        int(timeseries_update["end"]),
                        int(timeseries_update["ts_raster"])):
            timeseries_to_update[(ts, ts + COMMON.QUARTER)] = timeseries_update["value"]
        self.debug_log(text="Successfully updated: {}".format(timeseries_update["ts_name"]))

    def handle_steering_call(self, payload):
        self.debug_log(text="{}".format(payload))
        if payload["operation"] == "update_timeseries":
            self.handle_update_timeseries(payload)

    def on_strategy_update(self, strategy_json):
        if "steering_call" in strategy_json:
            self.handle_steering_call(strategy_json["steering_call"])
        else:
            super(CustomStrategy, self).on_strategy_update(strategy_json)
            self.strategy_position_tradable_position_long = STRAT.mk_strategy_tr_dict(
                strategy_json[COMMON.StrategyJsonKey.TS.pos_sell], "min"
            )
            self.strategy_position_tradable_position_short = STRAT.mk_strategy_tr_dict(
                strategy_json[COMMON.StrategyJsonKey.TS.pos_buy], "min"
            )

            self.strategy_price_purchase = STRAT.mk_strategy_tr_dict(
                strategy_json[COMMON.StrategyJsonKey.TS.price_buy], "min"
            )
            self.strategy_price_sales = STRAT.mk_strategy_tr_dict(
                strategy_json[COMMON.StrategyJsonKey.TS.price_sell], "max"
            )
            self.debug_log(text="Loaded strategy update")

    def on_strategy_configuration_update(self, strategy_json):
        # call on super also handles active field
        super(CustomStrategy, self).on_strategy_configuration_update(strategy_json)

    def custom_on_products_queue(self, products, timestamp):
        self.act(timestamp, products)


def po_slot_info(best_public_buy_price, best_public_sell_price):
    """Helper to print slot information

    :type best_public_buy_price: float or None
    :type best_public_sell_price: float or None
    :return: str
    """
    return "".join([
        "fronts:",
        "{:.1f}".format(best_public_buy_price or 0.) if best_public_buy_price is not None else "None",
        "//",
        "{:.1f}".format(best_public_sell_price or 0.) if best_public_sell_price is not None else "None",
    ])
