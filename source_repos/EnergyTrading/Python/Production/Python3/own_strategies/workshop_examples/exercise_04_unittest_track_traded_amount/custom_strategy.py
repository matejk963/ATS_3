#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""Read the already traded amount, compare it to the passed position, and trade the rest

Adjust the unit test, to simulate already traded amounts
"""
import autotrader_lib.common as COMMON
import autotrader_core.strategy as STRAT
import logging


log = logging.getLogger('autotrader.exercise_04_unittest_track_traded_amount')


class CustomStrategy(STRAT.Strategy):
    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        # pass strategy logger to base, to show distinct handle
        self.log = log

        self.strategy_position_tradable_position_long = STRAT.StrategyTimeSeries()
        self.strategy_position_tradable_position_short = STRAT.StrategyTimeSeries()
        self.strategy_price_purchase = STRAT.StrategyTimeSeries()
        self.strategy_price_sales = STRAT.StrategyTimeSeries()

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

        # TASK: read open position
        # TASK: read traded amounts
        # TASK: get leftover position, and adjust the order
        # TASK: if the leftover is 0, place a slot in that direction with 0 quantity
        # TASK: think about how you can make sure, that you can always place 2 slots

    def on_strategy_update(self, strategy_json):
        """The json is sent from Periotheus or from REST API (strategy steering call)

        strategy json comes unchanged -> can call anything
        api/strategy_steering

        :type strategy_json: dict
        :rtype: None
        """
        super(CustomStrategy, self).on_strategy_update(strategy_json)

        self.strategy_position_tradable_position_long = STRAT.mk_strategy_tr_dict(
            strategy_json["strategy_position_tradable_position_long"], "min"
        )
        self.strategy_position_tradable_position_short = STRAT.mk_strategy_tr_dict(
            strategy_json["strategy_position_tradable_position_short"], "min"
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
