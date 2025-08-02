#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""Write a strategy which places a sell order at the price
of the best available public price

Run the backtest and debug to check your code while you develop it
"""

import autotrader_lib.common as COMMON
import autotrader_core.strategy as STRAT
import logging

log = logging.getLogger('autotrader.exercise_05_steering_call')


class CustomStrategy(STRAT.Strategy):
    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        # pass strategy logger to base, to show distinct handle
        self.log = log

    def handle_steering_call(self, payload):
        self.debug_log(text="{}".format(payload))
        # TASK: debug and check what payload is sent after you fix the backtesting setup
        if payload["operation"] == "update_timeseries":
            self.debug_log("Updating Strategy with: {}".format(payload))
            print(("Updating Strategy with Steering Call: {}".format(payload)))

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
        # TASK: debug and check what payload is sent after you fix the backtesting setup
        self.debug_log("Updating Strategy with Configuration: {}".format(strategy_json))
        print(("Updating Strategy with Configuration: {}".format(strategy_json)))
