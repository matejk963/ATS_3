#!/usr/bin/env python
# -*- coding: utf-8 -*-

# README:
# In this example, we will learn how to configure SO and see how position closing can be implemented with SO
# To work with this example you need:
# - Environment configured to work with Back-testing
# - backtesting_example.py (this file) as a high-level end point to work with Back-testing
# - strategies: configured via EXAMPLE_STRATEGIES_FOLDER
#               position_closing_so/custom_strategy.py - strategy for showing how to implement position closing
#               so_config_and_management/custom_strategy.py - strategy for showing different config sor SO
#
# Adding a new strategy to a simulation, normally, happens in this order:
# - inserting new strategy
# - configuring the inserted strategy
# - activating the configured strategy
# For every step corresponding strategy events are generated and added to the simulation.
# To simplify this process you can use the method `create_strategy_config_workflow`.
#
# # In total there are two examples implemented in two separate methods:
# # - `example_configuring_so`: try to apply different config to SO and see the result
# # - `example_position_closing_so`: implements position closing, print traded quantity
# for product_id = 'dummy_10000302_1_20210615-20'
#
# BONUS TASK: assert additional conditions in position closing, try to get traded volume = 250
# DO NOT FORGET to look into unit-tests

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
                                         "example_13_synthetic_orders_position_closing")


def create_strategy_config_workflow(strategy_id, strategy_package, strategy_settings):
    strategy_config = SCON.StrategyConfiguration(strategy_id=strategy_id,
                                                 instrument_ids=[COMMON.Area.ttf],
                                                 strategies_folder=EXAMPLE_STRATEGIES_FOLDER,
                                                 caption="Backtesting strategy",
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


def example_configuring_so():
    strategy_name = "example_strategy"
    strategy_package = "so_config_and_management"

    strategy_settings_good = {"sequence_item_id": "10000302_1",
                              "order_type": "SimpleSyntheticOrderOne",
                              "config_option": True,
                              "position": 100}

    strategy_settings_wrong_type = {"sequence_item_id": "10000302_1",
                                    "order_type": "SimpleSyntheticOrderOne",
                                    "config_option": "bla",
                                    "position": 100}

    strategy_settings_wrong_value = {"sequence_item_id": "10000302_1",
                                     "order_type": "SimpleSyntheticOrderOne",
                                     "config_option": True,
                                     "position": 50000}

    strategy_settings_other_so = {"sequence_item_id": "10000302_1",
                                  "order_type": "SimpleSyntheticOrderTwo",
                                  "config_option": True,
                                  "position": 50000}

    messages = create_strategy_config_workflow(strategy_id=strategy_name,
                                               strategy_package=strategy_package,
                                               strategy_settings=strategy_settings_good)

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


def example_position_closing_so():
    strategy_name = "example_strategy"
    strategy_package = "position_closing_so"
    strategy_settings = {"sequence_item_id": "10000302_1",
                         "order_type": "PositionClosingBehavior",
                         "slot_size": 10,
                         "spread": 0.5,
                         "position": 100,
                         }

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
                              feed_paths=[os.path.join(ROOT_PATH,
                                                       "own_strategies", "workshop_examples", "assets", "ttf",
                                                       "20210615T14-15_ttfhical_gas_wd.zip")],
                              simulated_exchanges=(COMMON.Exchange.trayport, ),
                              use_persistence=False,
                              strategies_folder=EXAMPLE_STRATEGIES_FOLDER)

    simulator.run(write_logfiles=False)

    product_id = 'dummy_10000302_1_20210615-20'
    own_trades = simulator.autotrader.trayport.products.get_by_id(product_id).trades.get(
        trade_filter=COMMON.TradeFilter.own)
    print(sum(t.quantity for t in own_trades))


def main():
    # how to configure so and handle errors
    example_configuring_so()

    # implementing the position closing
    example_position_closing_so()


if __name__ == "__main__":
    main()
