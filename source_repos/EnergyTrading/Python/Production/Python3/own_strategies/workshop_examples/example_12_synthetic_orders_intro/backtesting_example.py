#!/usr/bin/python3
# -*- coding: utf-8 -*-

# README:
# In this example, we will learn how to interact with synthetic orders in Back-testing, explore local views, and
# create your first order from synthetic order. To work with this example you need:
# - Environment configured to work with Back-testing
# - backtesting_example.py (this file) as a high-level end point to work with Back-testing
# - strategies: configured via EXAMPLE_STRATEGIES_FOLDER
#               placeholder_lv_exploration/custom_strategy.py - strategy for showing how to work with localview in SO
#               so_slot_strategy/custom_strategy.py - strategy for showing order placed with synthetic order
# - feed folder: configured via EXAMPLE_FEEDS_ROOT
#
# Adding a new strategy to a simulation, normally, happens in this order:
# - inserting new strategy
# - configuring the inserted strategy
# - activating the configured strategy
# For every step corresponding strategy events are generated and added to the simulation.
# To simplify this process you can use the method `create_strategy_config_workflow`.
#
# Expected output:
# Lots of messages:
# ('Front Sell', 28.275)
# ('Front Buy', 27.325)
# ('Spread', 0.9499999999999993)
# Long sequence of numbers: 10.0, 210.0, 10.0 ...
#
# BONUS TASK: make strategies printing additional info


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
                                         "example_12_synthetic_orders_intro")


def create_strategy_config_workflow(strategy_id, strategy_package, strategy_settings):
    """
    Creates event messages for adding a new strategy
    :param strategy_id: id of a strategy
    :param strategy_package: strategies folder or zip file
    :param strategy_settings: dict with strategy parameters
    :return: strategy insert messages, strategy configure messages, strategy activate messages
    """

    strategy_config = SCON.StrategyConfiguration(strategy_id=strategy_id,
                                                 instrument_ids=[COMMON.Area.ttf],
                                                 strategies_folder=EXAMPLE_STRATEGIES_FOLDER,
                                                 caption="Example strategy",
                                                 package_name=strategy_package)

    strategy_insert_message = SBU.create_strategy_config_message(timestamp=dt_to_ts(DT(2021, 6, 15, 12, 0, 0)),
                                                                 strategy_id=strategy_id,
                                                                 strategy_configuration=strategy_config)

    strategy_config.update(strategy_settings)
    strategy_configure_message = SBU.create_strategy_config_message(timestamp=dt_to_ts(DT(2021, 6, 15, 12, 1, 0)),
                                                                    strategy_id=strategy_id,
                                                                    strategy_configuration=strategy_config)

    strategy_config.update(dict(active=True))
    strategy_activate_message = SBU.create_strategy_config_message(timestamp=dt_to_ts(DT(2021, 6, 15, 12, 2, 0)),
                                                                   strategy_id=strategy_id,
                                                                   strategy_configuration=strategy_config)

    return strategy_insert_message, strategy_configure_message, strategy_activate_message


def example_exploring_local_views():
    strategy_name = "example_strategy"
    strategy_package = "placeholder_lv_exploration"
    strategy_settings = {"so_products": ["10000302_1", "10000302_2", "10000302_3"]}

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


def example_slots_from_so():
    strategy_name = "example_strategy"
    strategy_package = "so_slot_strategy"
    strategy_settings = {"so_products": ["10000302_1", "10000302_2", "10000302_3"]}

    messages = create_strategy_config_workflow(strategy_id=strategy_name,
                                               strategy_package=strategy_package,
                                               strategy_settings=strategy_settings)

    strategy_insert_message, strategy_configure_message, strategy_activate_message = messages

    limits_payload = {"limits_per_sequence": {"maximum_purchase_volume": {"10000302": 1000},
                                              "minimum_sales_price": {"10000302": 1000}},
                      "limits_per_sequence_item": {"maximum_purchase_volume": {"10000302_1": 1000},
                                                   "maximum_purchase_price": {"10000302_1": 1000}}}

    limits_setup_message = SBU.create_per_products_limit_message(timestamp=dt_to_ts(DT(2021, 6, 15, 12, 1, 0)),
                                                                 strategy_id=strategy_name,
                                                                 limits_dict=limits_payload)

    simulator = SIM.Simulator([strategy_insert_message,
                               limits_setup_message,
                               strategy_configure_message,
                               strategy_activate_message],
                              feed_paths=[os.path.join(ROOT_PATH, "own_strategies", "workshop_examples", "assets",
                                                       "ttf", "20210615T14-15_ttfhical_gas_wd.zip")],
                              simulated_exchanges=(COMMON.Exchange.trayport, ),
                              use_persistence=False,
                              strategies_folder=EXAMPLE_STRATEGIES_FOLDER)

    # let us look at the logs!
    simulator.run(write_logfiles=True)


def main():
    # local view exploration
    example_exploring_local_views()

    # placing slots via synthetic orders
    example_slots_from_so()


if __name__ == "__main__":
    main()
