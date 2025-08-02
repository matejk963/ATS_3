#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Write a strategy which places a sell order at the price
of the best available public price

Fill in all the gaps marked with "# TASK"

Run the backtest and debug to check your code while you develop it
"""
import autotrader_core.strategy as STRAT
import logging


log = logging.getLogger('autotrader.exercise_01_backtest')


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
        pass
        # TASK: try to find the best buy price with an indicator
        # TASK: if the orderbook is empty or the indicator is not available, do not place
        # TASK: if the best buy price is available, then place a sell, 0.1MW, at the best public buy price

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
