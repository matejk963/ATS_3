#!/usr/bin/python3
# -*- coding: utf-8 -*-

import autotrader_lib.common as COMMON
import autotrader_core.strategy as STRAT
import logging


log = logging.getLogger('autotrader.new_position_closer')


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
