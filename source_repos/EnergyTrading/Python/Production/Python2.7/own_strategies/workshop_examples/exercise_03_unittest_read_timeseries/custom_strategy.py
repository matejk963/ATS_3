#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Modify this strategy to place also, if the public orderbook is empty.
This task has 2 parts, the strategy part and test part

Strategy Part:

The price and quantities should be read from the timeseries:
- strategy_position_tradable_position_long, value: 12
- strategy_position_tradable_position_short, value: 0
- strategy_price_purchase, value: 10
- strategy_price_sales, value: 50

However, in this exercise, do not track the traded amount.
Goal is:

if a current_best_buy is available, then place a sell with that price, and quantity 0.1
if no current_best_buy is available,
    then place a sell read from the value in "strategy_price_sales",
    with quantity "strategy_position_tradable_position_long"

Test Part:
please modify "strategy_unit_test.py" to simulate strategy timeseries

"""
import autotrader_core.common as COMMON
import autotrader_core.strategy as STRAT
import logging


log = logging.getLogger('autotrader.exercise_03_unittest_read_timeseries')


class CustomStrategy(STRAT.Strategy):
    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        # pass strategy logger to base, to show distinct handle
        self.log = log

        # TASK: Task: fill in here the lines necessary to initialize the empty timeseries

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
        if not indicators:
            self.debug_log(text="No indicators available, Skipping...", product=product)
            return

        current_best_buy = indicators[0].mw_prices[0][0]
        if current_best_buy is not None:
            slot = STRAT.PositionSlot("front", COMMON.Direction.sell, 0.1, current_best_buy)
            slot_resp = self.place_slots(
                log_data, product, timestamp, self.delivery_area_id, [slot], ["placement_info"]
            )
            self.debug_log("Placed Slot with response: {}".format(slot_resp))

        else:
            # TASK: Task: handle the case if current_best_buy is None and we read the values from the timeseries
            pass

            # TASK: Task: place according to these timeseries

    def on_strategy_update(self, strategy_json):
        """The json is sent from Periotheus or from REST API (strategy steering call)

        strategy json comes unchanged -> can call anything
        api/strategy_steering

        :type strategy_json: dict
        :rtype: None
        """
        super(CustomStrategy, self).on_strategy_update(strategy_json)

        # TASK: Task: fill in here the lines necessary to read the timeseries from teh strategies json

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
