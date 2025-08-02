#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""Empty Strategy with the most important callbacks"""

import autotrader_core.strategy as STRAT
import logging

log = logging.getLogger('autotrader.example_00_empty_strategy')


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

    def on_strategy_update(self, strategy_json):
        """The json is sent from Periotheus or from REST API (strategy steering call)

        strategy json comes unchanged -> can call anything
        api/strategy_steering

        :type strategy_json: dict
        :rtype: None
        """

        if strategy_json.get("message_type") == "forecast_ticker":
            # distinguish between steering call and Periotheus strategy update
            # Steering Call might have a message_type set to "forecast_ticker"
            # so the messages canbe filtered by that.
            self.debug_log("received rest steering information %s", strategy_json)
        else:
            # Otherwise continue with normal handling of strategy_jsons sent from Periotheus
            super(CustomStrategy, self).on_strategy_update(strategy_json)

    def custom_on_order_book_update(self, orders, timestamp):
        """On Order Book

        :type orders: list[APITR.Order]
        :type timestamp: float
        :rtype: None
        """
        pass

    def custom_on_trade_update(self, trades, timestamp):
        """On Own Trades only

        :type trades: list[APITR.Trade]
        :type timestamp: float
        :rtype: None
        """
        pass

    def custom_on_public_trade_update(self, trades, timestamp):
        """On Public Trades only

        :type trades: list[APITR.Trade]
        :type timestamp: float
        :rtype: None
        """
        pass

    def custom_on_products_update(self, products, timestamp):
        """Only when exchange sends a messages about a product changing

        E.g. change from active to inactive, trading interval, ...

        :type products: list[APITR.Product]
        :type timestamp: float
        :rtype: None
        """
        pass

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
        pass

    def custom_on_timer(self, timestamp):
        pass  # products queue is enough

    def custom_on_error(self, errors, timestamp):
        """React on custom error, such as market state errors"""
        pass

    def on_synthetic_order(self, payload):
        """ This callback will be called whenever a new SyntheticOrder object is collected from MongoDB
        (strategies collection). The payload and response works in a similar fashion as the steering calls.
        This function will take care of the cascading and configuration logic. It will catch any foreseeable errors
        to forward them as a response."""
        pass

    def on_strategy_configuration_update(self, strategy_json):
        """This callback function is used for new strategies/ strategy updates from the REST-API.

        It is called when a COMMON.MongoDBObjects.strategy_configuration object is updated in
        mongo and it sets some attribute on the object."""
        pass
