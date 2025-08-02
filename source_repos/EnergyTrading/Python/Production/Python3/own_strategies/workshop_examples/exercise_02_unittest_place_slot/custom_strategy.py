#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""Use this strategy and write a unittest for it, the unittest should simulate public orders.
please see the file "strategy_unit_test.py" for more info
and check whether the strategy places correctly

"""
import autotrader_lib.common as COMMON
import autotrader_core.strategy as STRAT
import logging


log = logging.getLogger('autotrader.exercise_02_unittest_place_slot')


class CustomStrategy(STRAT.Strategy):
    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        # pass strategy logger to base, to show distinct handle
        self.log = log

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
            slot_resp = self.place_slots(log_data, product, timestamp, self.delivery_area_id, [slot],
                                         ["placement_info"])
            self.debug_log("Placed Slot with response: {}".format(slot_resp))

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
