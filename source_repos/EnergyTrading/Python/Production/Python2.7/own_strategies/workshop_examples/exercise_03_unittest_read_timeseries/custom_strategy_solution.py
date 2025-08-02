#!/usr/bin/env python
# -*- coding: utf-8 -*-
import autotrader_core.common as COMMON
import autotrader_core.strategy as STRAT
import logging


log = logging.getLogger('autotrader.exercise_03_unittest_read_timeseries')


class CustomStrategy(STRAT.Strategy):
    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        # pass strategy logger to base, to show distinct handle
        self.log = log

        self.strategy_position_tradable_position_long = {}
        self.strategy_position_tradable_position_short = {}
        self.strategy_price_purchase = {}
        self.strategy_price_sales = {}

    def custom_act(self, log_data, timestamp, products=None):
        """when act is called, mostly reacting to changes in products

        :type log_data: dict
        :type timestamp: float
        :type products: list[APITR.Product]
        :return:
        """
        if not products:
            return

        for product in products:
            self.act_for_product(product, timestamp)

    def custom_act_for_product(self, log_data, product, timestamp, *args, **kwargs):
        self.debug_log(text="Act for product", product=product)
        indicators = product.orders.indicators(self.delivery_area_id)
        current_best_buy = None
        if indicators:
            self.debug_log(text="No indicators available, Skipping...", product=product)
            current_best_buy = indicators[0].mw_prices[0][0]

        if current_best_buy is not None:
            slot = STRAT.PositionSlot("front", COMMON.Direction.sell, 0.1, current_best_buy)
            slot_resp = self.place_slots(
                log_data, product, timestamp, self.delivery_area_id, [slot], ["placement_info"]
            )
            self.debug_log("Placed Slot with response: {}".format(slot_resp))

        else:
            pos = self.strategy_position_tradable_position_long.get((product.delivery_start, product.delivery_end))
            price = self.strategy_price_sales.get((product.delivery_start, product.delivery_end))

            slot = STRAT.PositionSlot("front", COMMON.Direction.sell, pos, price)
            slot_resp = self.place_slots(
                log_data, product, timestamp, self.delivery_area_id, [slot], ["placement_info"]
            )
            self.debug_log("Placed Slot Based on Timeseries with response: {}".format(slot_resp))

    def on_strategy_update(self, strategy_json):
        """The json is sent from Periotheus or from REST API (strategy steering call)

        strategy json comes unchanged -> can call anything
        api/strategy_steering

        :type strategy_json: dict
        :rtype: None
        """
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

    def custom_on_products_queue(self, products, timestamp):
        """Replacement for timer

        Products get queued by urgency via ProductsPriorityQueue

        This is the best entrypoint to call code periodically

        e.g. with
        self.act(timestamp, products)

        :type products: list[APITR.Product]
        :type timestamp: float
        :rtype: None
        """
        self.act(timestamp, products)
