#!/usr/bin/python3
# -*- coding: utf-8 -*-

# README:
# In this example, we will explore how to work with local views in strategies context
# To work with this example you need:
# - Environment configured to work with Back-testing
# - backtesting_example.py (this file) as a high-level end point to work with Back-testing
# - strategies: configured via EXAMPLE_STRATEGIES_FOLDER
#               lv_strategy/custom_strategy.py - strategy for showing how to work with local views
#
# Adding a new strategy to a simulation, normally, happens in this order:
# - inserting new strategy
# - configuring the inserted strategy
# - activating the configured strategy
# For every step corresponding strategy events are generated and added to the simulation.
# To simplify this process you can use the method `create_strategy_config_workflow`.
#
# - `example_configs`: see examples of working with local views and make strategy to print front price sell and buy


import datetime
import os.path

import autotrader_lib.common as COMMON
import autotrader_lib.util as ALU
import backtesting.simulate as SIM
import backtesting.strategy_configuration as SCON
import backtesting.synchronous_backtesting_utils as SBU

from backtesting import ROOT_PATH

DT = datetime.datetime
dt_to_ts = ALU.convert_dt_to_float_timestamp

EXAMPLE_STRATEGIES_FOLDER = os.path.join(ROOT_PATH,
                                         "own_strategies",
                                         "workshop_examples",
                                         "example_11_backtesting_local_views_intro")


def create_strategy_config_workflow(strategy_id, strategy_package, strategy_settings):
    strategy_config = SCON.StrategyConfiguration(
        strategy_id=strategy_id,
        instrument_ids=[COMMON.Area.ttf],
        strategies_folder=EXAMPLE_STRATEGIES_FOLDER,
        package_name=strategy_package,
        exchange=COMMON.Exchange.trayport,
        caption="Strategy which logs some LocalView indicators.",
        **strategy_settings
    )

    strategy_insert_message = SBU.create_strategy_config_message(
        timestamp=dt_to_ts(DT(2021, 6, 15, 12, 0, 0)),
        strategy_id=strategy_id,
        strategy_configuration=strategy_config
    )

    strategy_config.update(strategy_settings)
    strategy_configure_message = SBU.create_strategy_config_message(
        timestamp=dt_to_ts(DT(2021, 6, 15, 12, 1, 0)),
        strategy_id=strategy_id,
        strategy_configuration=strategy_config
    )

    strategy_config.update(dict(active=True))
    strategy_activate_message = SBU.create_strategy_config_message(
        timestamp=dt_to_ts(DT(2021, 6, 15, 12, 2, 0)),
        strategy_id=strategy_id,
        strategy_configuration=strategy_config
    )

    return strategy_insert_message, strategy_configure_message, strategy_activate_message


def example_exploring_local_views():
    strategy_name = "example_strategy"
    strategy_package = "lv_strategy"
    strategy_settings = {}

    messages = create_strategy_config_workflow(strategy_id=strategy_name,
                                               strategy_package=strategy_package,
                                               strategy_settings=strategy_settings)

    strategy_insert_message, strategy_configure_message, strategy_activate_message = messages

    simulator = SIM.Simulator([strategy_insert_message,
                               strategy_configure_message,
                               strategy_activate_message],
                              feed_paths=[os.path.join(ROOT_PATH, "own_strategies", "workshop_examples", "assets",
                                                       "ttf", "20210615T14-15_ttfhical_gas_wd.zip")],
                              simulated_exchanges=(COMMON.Exchange.trayport, ),
                              use_persistence=False,
                              strategies_folder=EXAMPLE_STRATEGIES_FOLDER)
    simulator.run(write_logfiles=False)


if __name__ == "__main__":
    example_exploring_local_views()
