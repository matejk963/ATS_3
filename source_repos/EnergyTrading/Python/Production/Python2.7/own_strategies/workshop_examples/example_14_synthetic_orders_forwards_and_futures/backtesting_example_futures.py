#!/usr/bin/env python
# -*- coding: utf-8 -*-

# README:
# In this example, we will learn how to interact with Forward and Future products on the example of Italy Baseload
# To work with this example you need:
# - Environment configured to work with Back-testing
# - backtesting_example.py (this file) as a high-level end point to work with Back-testing
# - strategy: configured via EXAMPLE_STRATEGIES_FOLDER
#               futures_example_strategy/custom_strategy.py - strategy for showing how to implement position closing
#
# Adding a new strategy to a simulation, normally, happens in this order:
# - inserting new strategy
# - configuring the inserted strategy
# - activating the configured strategy
# For every step corresponding strategy events are generated and added to the simulation.
# To simplify this process you can use the method `create_strategy_config_workflow`.
#
# In total there are two examples implemented in two separate methods:
# - `example_futures_example_strategy`: For printing some logs it is recommended to use self.debug_log("")
#   method because it will automatically include the strategy id.
#   additionally the product can be passed, and the log will include the product_id and product_name.
#
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
                                         "example_14_synthetic_orders_forwards_and_futures")
# zipped folder of init files
EXAMPLE_FEEDS_ROOT = os.path.join(ROOT_PATH,
                                  "own_strategies",
                                  "workshop_examples",
                                  "assets",
                                  "italy_baseload",
                                  "seqs_10000104_10000105_10000106_instr_10100480")

# zipped jsonl feed
feed_path = os.path.join(ROOT_PATH,
                         "own_strategies",
                         "workshop_examples",
                         "assets",
                         "italy_baseload",
                         "2021-06-22_COMPLETE_seqs_10000104_10000105_10000106_instr_10100480.zip")


def create_strategy_config_workflow(strategy_id, strategy_package, strategy_settings):
    strategy_config = SCON.StrategyConfiguration(strategy_id=strategy_id,
                                                 caption="My Synthetic Strategy",
                                                 package_name=strategy_package,
                                                 strategies_folder=EXAMPLE_STRATEGIES_FOLDER,
                                                 instrument_ids=[COMMON.Area.it_bl])

    strategy_insert_message = SBU.create_strategy_config_message(timestamp=dt_to_ts(DT(2021, 6, 21, 8, 0, 0)),
                                                                 strategy_id=strategy_id,
                                                                 strategy_configuration=strategy_config)

    strategy_config.update(strategy_settings)
    strategy_configure_message = SBU.create_strategy_config_message(timestamp=dt_to_ts(DT(2021, 6, 21, 8, 1, 0)),
                                                                    strategy_id=strategy_id,
                                                                    strategy_configuration=strategy_config)

    strategy_config.update(dict(active=True))
    strategy_activate_message = SBU.create_strategy_config_message(timestamp=dt_to_ts(DT(2021, 6, 21, 8, 2, 0)),
                                                                   strategy_id=strategy_id,
                                                                   strategy_configuration=strategy_config)

    return strategy_insert_message, strategy_configure_message, strategy_activate_message


def example_futures_example_strategy():
    strategy_name = "futures_example_strategy"
    strategy_package = "futures_example_strategy"
    strategy_settings = {
        "sequence_item_id": "10000104_211",  # we are looking into product on Jul-21 found in the sequence_item.json 211
        "order_type": "PositionClosingBehavior",
        "position": 20,
        "spread": 0.5,
        "slot_size": 5,
    }

    messages = create_strategy_config_workflow(strategy_id=strategy_name,
                                               strategy_package=strategy_package,
                                               strategy_settings=strategy_settings)

    strategy_insert_message, strategy_configure_message, strategy_activate_message = messages

    limits_payload = {
        "limits_per_sequence": {"maximum_purchase_volume": {"10000104": 1000, "10000105": 1000, "10000106": 1000},
                                "minimum_sales_price": {"10000104": 0, "10000105": 0, "10000106": 0},
                                "maximum_sales_volume": {"10000104": 1000, "10000105": 1000, "10000106": 1000},
                                "maximum_purchase_price": {"10000104": 1000, "10000105": 1000, "10000106": 1000}},
        "limits_per_sequence_item": {
            "maximum_purchase_volume": {"10000104_1": 1000, "10000105_1": 1000, "10000106_1": 1000,
                                        "10000104_2": 1000, "10000105_2": 1000, "10000106_2": 1000},
            "maximum_purchase_price": {"10000104_1": 1000, "10000105_1": 1000, "10000106_1": 1000,
                                       "10000104_2": 1000, "10000105_2": 1000, "10000106_2": 1000}}}

    limits_setup_message = SBU.create_per_products_limit_message(timestamp=dt_to_ts(DT(2021, 6, 21, 12, 1, 0)),
                                                                 strategy_id=strategy_name,
                                                                 limits_dict=limits_payload)

    simulator = SIM.Simulator([strategy_insert_message,
                               limits_setup_message,
                               strategy_configure_message,
                               strategy_activate_message],
                              feed_paths=[feed_path],
                              trayport_config={"venues": "EEX A",  # EEX A is crucial for italy baseload
                                               "commodities": "Gas, Euro",  # Euro is crucial for italy baseload
                                               "product_subscription_max_years": 5,
                                               "product_subscription_shortterm_days": 0,
                                               "product_subscription_midterm_count": 200,
                                               "product_subscription_longterm_count": 100},
                              simulated_exchanges=(COMMON.Exchange.trayport, ),
                              use_persistence=False,
                              overwrite_database=True,
                              database_name="italy_baseload_simu",
                              strategies_folder=EXAMPLE_STRATEGIES_FOLDER,
                              trayport_init_directory=EXAMPLE_FEEDS_ROOT)

    simulator.run(write_logfiles=False)
    simulator.get_net_traded_amounts_by_strategy(printout=True, only_traded=False)


if __name__ == "__main__":
    example_futures_example_strategy()
