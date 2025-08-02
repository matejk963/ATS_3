#!/usr/bin/env python
# -*- coding: utf-8 -*-

# README:
# In this example, we will refresh the knowledge, and give a short summary on working with
# Back-testing autoTRADER strategies. To work with this example you need:
# - Environment configured to work with Back-testing
# - backtesting_example.py (this file) as a high-level end point to work with Back-testing
# - strategies: configured via EXAMPLE_STRATEGIES_FOLDER
#               example_configs/custom_strategy.py - strategy for showing how to configure a strategy before simulation
#               example_limits/custom_strategy.py - strategy for showing how to work with strategy limits
# - empty Trayport feed: configured via EXAMPLE_TRAYPORT_EMPTY_FEED
#                        autotrader_core/i9ntests/simulation_tests/assets/EmptyTrayportFeed.jsonl
#
# Adding a new strategy to a simulation, normally, happens in this order:
# - inserting new strategy
# - configuring the inserted strategy
# - activating the configured strategy
# For every step corresponding strategy events are generated and added to the simulation.
# To simplify this process you can use the method `create_strategy_config_workflow`.
#
# In total there are two examples implemented in two separate methods:
# - `example_configs`: after getting a strategy update, it prints the config and active flag
# - `example_limits`: after getting a strategy update, it prints strategy limits in case it's active
#
# Expected output:
# ------------------------
# Getting an update call!
# ------------------------
# Strategy is active:
# False
# ------------------------
# Getting an update call!
# ------------------------
# {'algo': 'BALANCED'}
# test
# [1, 2, 3, 'X']
# 10.0
# Strategy is active:
# False
# ------------------------
# Getting an update call!
# ------------------------
# {'algo': 'BALANCED'}
# test
# [1, 2, 3, 'X']
# 10.0
# Strategy is active:
# True
#
# LimitContainer(strategy_id=<example_strategy_with_limits>, exchange_id=<TRAYPORT>)
#
# BONUS TASKS:
# - make `example_config` strategy to print also the keys with values
# - make `example_limits` strategy to print some additional info on strategy configuration

import datetime
import os.path

import autotrader_core.common as COMMON
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
                                         "example_10_backtesting_warm_up")

EXAMPLE_TRAYPORT_EMPTY_FEED = os.path.join(ROOT_PATH,
                                           "own_strategies",
                                           "workshop_examples",
                                           "assets",
                                           "EmptyTrayportFeed.jsonl")


def create_strategy_config_workflow(strategy_id, strategy_package, strategy_settings=None):
    """
    Creates event messages for adding a new strategy
    :param strategy_id: id of a strategy
    :param strategy_package: strategies folder or zip file
    :param strategy_settings: dict with strategy parameters
    :return: strategy insert messages, strategy configure messages, strategy activate messages
    """
    strategy_config = SCON.StrategyConfiguration(
        strategy_id=strategy_id,
        instrument_ids=[COMMON.Area.ttf],
        strategies_folder=EXAMPLE_STRATEGIES_FOLDER,
        package_name=strategy_package,
        exchange=COMMON.Exchange.trayport,
        caption="Test Rest Api Call to create and configure a strategy",
    )

    strategy_insert_message = SBU.create_strategy_config_message(timestamp=dt_to_ts(DT(2020, 9, 6, 4, 0, 0)),
                                                                 strategy_id=strategy_id,
                                                                 strategy_configuration=strategy_config)

    if strategy_settings:
        strategy_config.update(strategy_settings)
    strategy_configure_message = SBU.create_strategy_config_message(timestamp=dt_to_ts(DT(2020, 9, 6, 4, 1, 0)),
                                                                    strategy_id=strategy_id,
                                                                    strategy_configuration=strategy_config)

    strategy_config.update(dict(active=True))
    strategy_activate_message = SBU.create_strategy_config_message(timestamp=dt_to_ts(DT(2020, 9, 6, 4, 2, 0)),
                                                                   strategy_id=strategy_id,
                                                                   strategy_configuration=strategy_config)

    return strategy_insert_message, strategy_configure_message, strategy_activate_message


def example_configs():
    """
    Before we can work with the strategies we need to be able to configure them.
    We can do this by sending them configuration events via the simulator.
    """
    strategy_name = "example_strategy"
    strategy_package = "example_configs"

    # some examples of what the settings could be
    strategy_settings = {"setting_x": 10.,
                         "setting_y": "test",
                         "setting_list": [1, 2, 3, "X"],
                         "setting_dict": dict(algo="BALANCED")}

    # IMPORTANT: Look into the function!
    messages = create_strategy_config_workflow(strategy_id=strategy_name,
                                               strategy_package=strategy_package,
                                               strategy_settings=strategy_settings)

    # IMPORTANT: The insert and configure message do not need to be separate, but the activate does need to come later
    strategy_insert_message, strategy_configure_message, strategy_activate_message = messages

    simulator = SIM.Simulator(event_messages=[strategy_insert_message,
                                              strategy_configure_message,
                                              strategy_activate_message],
                              feed_paths=[os.path.join(EXAMPLE_TRAYPORT_EMPTY_FEED)],
                              simulated_exchanges=(COMMON.Exchange.trayport, ),
                              use_persistence=False,
                              # this is important for the simulator to find the appropriate strategy
                              strategies_folder=EXAMPLE_STRATEGIES_FOLDER,
                              )

    simulator.run(write_logfiles=False)


def example_limits():
    strategy_name = "example_strategy_with_limits"
    strategy_package = "example_limits"
    strategy_settings = {}

    messages = create_strategy_config_workflow(strategy_id=strategy_name,
                                               strategy_package=strategy_package,
                                               strategy_settings=strategy_settings)
    strategy_insert_message, _, strategy_activate_message = messages

    # The strategy needs limits to be set-up for the products to be able to ensure safety
    limits_payload = {"limits_per_sequence": {"maximum_purchase_volume": {"10000302": 1000},
                                              "minimum_sales_price": {"10000302": 1000}},
                      "limits_per_sequence_item": {"maximum_purchase_volume": {"10000302_1": 1000},
                                                   "maximum_purchase_price": {"10000302_1": 1000}}}

    limits_setup_message = SBU.create_per_products_limit_message(timestamp=dt_to_ts(DT(2020, 9, 6, 4, 1, 0)),
                                                                 strategy_id=strategy_name,
                                                                 limits_dict=limits_payload)

    simulator = SIM.Simulator(event_messages=[strategy_insert_message,
                                              limits_setup_message,
                                              strategy_activate_message],
                              feed_paths=[os.path.join(EXAMPLE_TRAYPORT_EMPTY_FEED)],
                              simulated_exchanges=(COMMON.Exchange.trayport, ),
                              use_persistence=False,
                              strategies_folder=EXAMPLE_STRATEGIES_FOLDER,
                              )

    simulator.run(write_logfiles=False)


def main():
    # working with config endpoints
    example_configs()

    # working with new limits
    example_limits()


if __name__ == "__main__":
    main()
