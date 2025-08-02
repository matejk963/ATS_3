#!/usr/bin/python3
# -*- coding: utf-8 -*-

import autotrader_lib.common as COMMON
import autotrader_core.strategy as STRAT
import autotrader_lib.cet_util as CETUTIL
import collections
import logging
from six.moves import range


log = logging.getLogger('autotrader.new_position_closer')


def float_or_none(value):
    return None if value is None else float(value)


class CustomStrategy(STRAT.Strategy):
    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        # pass strategy logger to base, to show distinct handle
        self.log = log

        # and we need to define their update ourselves
        self.strategy_position_tradable_position_long = STRAT.StrategyTimeSeries(COMMON.QUARTER)
        self.strategy_position_tradable_position_short = STRAT.StrategyTimeSeries(COMMON.QUARTER)

        self.strategy_price_purchase = STRAT.StrategyTimeSeries(COMMON.QUARTER)
        self.strategy_price_sales = STRAT.StrategyTimeSeries(COMMON.QUARTER)

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

        for product in sorted(products, key=lambda p: p.delivery_start):
            self.act_for_product(product=product, timestamp=timestamp)

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

        # overlapping products
        overlap_products = self.exchange.products.get_overlapping_with_timerange(
            product.delivery_start, product.delivery_end
        )
        net_traded = collections.defaultdict(int)

        # loop over overlapping products and get the trades for each
        for p in overlap_products:
            balance = p.trades.get_balance(self.delivery_area_id, self.strategy_id)
            # for each quarter hour spanned by this product, add the net traded amount to the net_traded dict.
            for ts in range(p.delivery_start, p.delivery_end, COMMON.QUARTER):
                net_traded[ts] += balance

        # get positions set in periotheus (or by REST API)
        product_interval = (product.delivery_start, product.delivery_end)
        long_target = self.strategy_position_tradable_position_long.get(product_interval, 0.) or 0.
        short_target = self.strategy_position_tradable_position_short.get(product_interval, 0.) or 0.
        open_position = short_target - long_target

        traded_vals = [net_traded[ts] for ts in range(product.delivery_start, product.delivery_end, COMMON.QUARTER)]
        if open_position > 0:
            # example: max traded: [-10, 0, 10, 5] => 10, open: 5 ->  -5 => sell 5
            open_position -= max(traded_vals)
        else:
            # example: min traded: [-10, 0, 10, 5] => -10, open: -15 ->  -5 => sell 5 more
            open_position -= min(traded_vals)

        # get best public orderbook prices
        best_public_buy_price = None
        best_public_sell_price = None
        indicators = product.orders.indicators(self.delivery_area_id)
        if indicators:
            best_public_buy_price = indicators[0].mw_prices[0][0]
            best_public_sell_price = indicators[0].mw_prices[1][0]

        ##############################################################
        # create slots with price and quantity rounded to tick sizes #
        ##############################################################

        slot = STRAT.PositionSlot("front", COMMON.Direction.buy, quantity=0, price=0)
        max_slot_size = 0.1
        step_size = 0.1

        if open_position > 0:
            slot.direction = COMMON.Direction.buy
            slot.quantity = min(open_position, max_slot_size)
            if best_public_buy_price is not None:
                slot.price = best_public_buy_price + step_size
            else:
                slot.price = self.strategy_price_purchase.get(product_interval)

        elif open_position < 0:
            slot.direction = COMMON.Direction.sell
            slot.quantity = min(abs(open_position), max_slot_size)
            if best_public_sell_price is not None:
                slot.price = best_public_sell_price - step_size
            else:
                slot.price = self.strategy_price_sales.get(product_interval)

        # add bot race protection.
        # only modify order on the market, if it would change by more than the price tolerance in any direction.
        price_tolerance = 0.5
        slot.price_range_lo = slot.price - price_tolerance
        slot.price_range_hi = slot.price + price_tolerance

        # info to be saved with the order/trade
        slot.info = "net_target_pos: {}|| fronts: {}//{}".format(
            open_position, float_or_none(best_public_buy_price), float_or_none(best_public_sell_price)
        )

        # place slots and save response
        slot_responses = self.place_slots({}, product, timestamp, self.delivery_area_id, [slot])

        self.debug_log(text="Slot Placement Results: {}".format(slot_responses), product=product)

    def on_strategy_update(self, strategy_json):
        super(CustomStrategy, self).on_strategy_update(strategy_json)
        # on strategy update sets the self.delivery_areas from the passed json

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

    def custom_on_order_book_update(self, orders, timestamp):
        self.act(timestamp, set(o.product for o in orders))

    def custom_on_products_update(self, products, timestamp):
        self.act(timestamp, products)

    def custom_on_products_queue(self, products, timestamp):
        self.act(timestamp, products)
