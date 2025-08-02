#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Simple Power strategy to Demo Unit Tests OTR Calculations with and without Internal Markets"""
import collections

import autotrader_lib.cet_util as CETUTIL
import autotrader_core.common as COMMON
import autotrader_core.exchange_trading as APITR
import autotrader_core.strategy as STRAT
import autotrader_core.strategy_utils as SU

import logging

log = logging.getLogger("autotrader.example_09_power_strategy_backtest")

SELL_SLOTNAME = "sell_slot"
BUY_SLOTNAME = "buy_slot"


class CustomStrategy(STRAT.Strategy):
    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        # used for aggregations
        self.smallest_timestep = COMMON.QUARTER

        # pass strategy logger to base, to show distinct handle
        self.log = log
        # keep info about delivery area
        self.delivery_area_id = None

        # and we need to define their update ourselves
        self.strategy_position_tradable_position_long = STRAT.StrategyTimeSeries()
        self.strategy_position_tradable_position_short = STRAT.StrategyTimeSeries()

        self.strategy_price_purchase = STRAT.StrategyTimeSeries()
        self.strategy_price_sales = STRAT.StrategyTimeSeries()

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

    def calc_otr(self, products_obj, delivery_start, delivery_end, delivery_area, curr_prod):
        zone = COMMON.Area.get_zone(delivery_area) if delivery_area else None

        products = products_obj._products_by_delivery[(delivery_start, delivery_end)]
        if not products:
            raise COMMON.ProductNotFound(
                "cannot evaluate order_to_trade ratio as no products are available for delivery span: {}-{}".format(
                    delivery_start, delivery_end))
        trade_ids = set()
        order_ids = set()

        for product in products:
            if not delivery_area:
                for product_trade_ids in product.own_trade_ids.values():
                    trade_ids.update(product_trade_ids)
                for product_order_ids in product.executed_orders.values():
                    order_ids.update(product_order_ids)
            else:
                trade_ids.update(product.own_trade_ids[zone])
                order_ids.update(product.executed_orders[zone])
        trade_count = len(trade_ids)
        num_executed_orders = len(order_ids)
        if trade_count == 0.:
            otr = num_executed_orders
        else:
            otr = num_executed_orders / float(trade_count)
        self.debug_log("Getting OTR from-to: {}-{} [ts={}-{}] (area={}) (prodIds={}): tr#={}, ord#={}, otr={}".format(
            CETUTIL.utc_ts2cet_str(delivery_start),
            CETUTIL.utc_ts2cet_str(delivery_end),
            delivery_start, delivery_end,
            delivery_area,
            [p.product_id for p in products],
            trade_count, num_executed_orders, otr
        ), curr_prod)
        return otr

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
        products = self.exchange.products.get_active_products(self.delivery_area_id)
        if not products:
            return

        min_start_ts = min(p.delivery_start for p in products)
        max_end_ts = max(p.delivery_end for p in products)
        self.traded = self._get_traded_amount(min_start_ts, max_end_ts)

        for product in sorted(products, key=lambda p: p.delivery_start):
            self.act_for_product(product=product, timestamp=timestamp)

        for prod in products:
            otr = self.calc_otr(self.exchange.products, prod.delivery_start, prod.delivery_end, self.delivery_area_id,
                                prod)
            self.debug_log("OTR-CALC-RESULT: {}".format(otr), prod)

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

        ##############################################
        # place slots with info #
        ##############################################

        # place buy slot
        buy_slot.info = "buy_state:normal||trd:{}||net_target_pos:{}||rest:{}||order:{}@{}||fronts:{}//{}".format(
            common_traded, open_position, rest, buy_slot.quantity, buy_slot.price, best_public_buy_price,
            best_public_sell_price
        )
        slot_responses = self.place_slots({}, product, timestamp, self.delivery_area_id,
                                          [buy_slot], [],
                                          limit_minimum_sales_price=-9999,
                                          limit_maximum_purchase_price=9999,
                                          execmode=COMMON.InternalExecutionMode.exchange_base_price)

        self.debug_log(text="Buy Slot Placement Results: {}".format(slot_responses), product=product)

        # place sell slot
        sell_slot.info = "sell_state:normal||trd:{}||net_target_pos:{}||rest:{}||order:{}@{}||fronts:{}//{}".format(
            common_traded, open_position, rest, sell_slot.quantity, sell_slot.price, best_public_buy_price,
            best_public_sell_price
        )

        slot_responses = self.place_slots({}, product, timestamp, self.delivery_area_id,
                                          [sell_slot], [],
                                          limit_minimum_sales_price=-9999,
                                          limit_maximum_purchase_price=9999,
                                          execmode=COMMON.InternalExecutionMode.exchange_base_price)

        self.debug_log(text="Sell Slot Placement Results: {}".format(slot_responses), product=product)

    def on_strategy_update(self, strategy_json):
        """The json is sent from Periotheus or from REST API (strategy steering call)

        strategy json comes unchanged -> can call anything
        api/strategy_steering

        :type strategy_json: dict
        :rtype: None
        """

        super(CustomStrategy, self).on_strategy_update(strategy_json)
        # on strategy update sets the self.delivery_areas from the passed json
        self.delivery_area_id = self.delivery_areas[0]

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
        self.act(self.autotrader.current_timestamp)

    def custom_on_order_book_update(self, orders, timestamp):
        self.act(timestamp, set(o.product for o in orders))

    def custom_on_products_update(self, products, timestamp):
        self.act(timestamp, products)
