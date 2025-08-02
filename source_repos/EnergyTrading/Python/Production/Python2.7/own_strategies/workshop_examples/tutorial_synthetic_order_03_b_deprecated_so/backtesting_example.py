#!/usr/bin/env python
# -*- coding: utf-8 -*-

import datetime
import os.path
import unittest

import autotrader_core.common as COMMON
import autotrader_lib.util as ALU
import backtesting.simulate as SIM
import backtesting.strategy_configuration as SCON
import backtesting.synchronous_backtesting_utils as SBU

from backtesting import ROOT_PATH

DT = datetime.datetime
dt_to_ts = ALU.convert_dt_to_float_timestamp

EXAMPLE_STRATEGIES_FOLDER = os.path.dirname(__file__)


class StrategyConfigurationTest(unittest.TestCase):
    def test(self):
        strategy_id = "strat_1"
        strategy_package = "synth_ord_strategy"
        # This pretends that previously a REST call has already been made to POST /packages
        #  with a content {"package_name": "synth_ord_strategy", "package_zip": <<FILE.ZIP>>}
        # in the simulation the package is known, because we tell the simulator the path to the strategy folder

        strategy_config = SCON.StrategyConfiguration(strategy_id=strategy_id,
                                                     instrument_ids=[COMMON.Area.ttf],
                                                     strategies_folder=EXAMPLE_STRATEGIES_FOLDER,
                                                     caption="Example strategy",
                                                     package_name=strategy_package)

        # simulate how the rest api transforms the payload to an internal message
        strategy_insert_message = SBU.create_strategy_config_message(timestamp=dt_to_ts(DT(2021, 6, 15, 12, 0, 0)),
                                                                     strategy_id=strategy_id,
                                                                     strategy_configuration=strategy_config)

        strategy_config.update(
            dict(
                so_products=[COMMON.SequenceId.gas_prompt + "_" + COMMON.GasPromptItemId.within_day,  # 10000302_1
                             COMMON.SequenceId.gas_prompt + "_" + COMMON.GasPromptItemId.day_ahead,  # 10000302_2
                             COMMON.SequenceId.gas_prompt + "_" + COMMON.GasPromptItemId.bow]  # 10000302_3
            )
        )  # COMMON.GasPromptProductId could also be used here

        strategy_load_so_message = SBU.create_strategy_config_message(timestamp=dt_to_ts(DT(2021, 6, 15, 12, 2, 1)),
                                                                      strategy_id=strategy_id,
                                                                      strategy_configuration=strategy_config)

        strategy_config.update(dict(active=True))
        strategy_activate_message = SBU.create_strategy_config_message(timestamp=dt_to_ts(DT(2021, 6, 15, 12, 2, 2)),
                                                                       strategy_id=strategy_id,
                                                                       strategy_configuration=strategy_config)

        limits_payload = {
            "limits_per_sequence": {"maximum_purchase_volume": {"10000301": 1000, "10000302": 1000, "10000104": 1000,
                                                                "10000105": 1000, "10000106": 1000},
                                    "minimum_sales_price": {"10000301": 0, "10000302": 0, "10000104": 0,
                                                            "10000105": 0, "10000106": 0},
                                    "maximum_sales_volume": {"10000301": 1000, "10000302": 1000, "10000104": 1000,
                                                             "10000105": 1000, "10000106": 1000},
                                    "maximum_purchase_price": {"10000301": 1000, "10000302": 1000, "10000104": 1000,
                                                               "10000105": 1000, "10000106": 1000}},
            "limits_per_sequence_item": {
                "maximum_purchase_volume": {"10000104_1": 1000, "10000105_1": 1000, "10000106_1": 1000,
                                            "10000104_2": 1000, "10000105_2": 1000, "10000106_2": 1000},
                "maximum_purchase_price": {"10000104_1": 1000, "10000105_1": 1000, "10000106_1": 1000,
                                           "10000104_2": 1000, "10000105_2": 1000, "10000106_2": 1000}}}

        limits_setup_message = SBU.create_per_products_limit_message(timestamp=dt_to_ts(DT(2021, 6, 15, 12, 2, 3)),
                                                                     strategy_id=strategy_id,
                                                                     limits_dict=limits_payload)

        simulator = SIM.Simulator([strategy_insert_message, strategy_load_so_message, strategy_activate_message,
                                   limits_setup_message],
                                  feed_paths=[os.path.join(ROOT_PATH, "own_strategies", "workshop_examples", "assets",
                                                           "ttf", "20210615T14-15_ttfhical_gas_wd.zip")],
                                  simulated_exchanges=(COMMON.Exchange.trayport,),
                                  use_persistence=False,
                                  strategies_folder=EXAMPLE_STRATEGIES_FOLDER)
        simulator.run(write_logfiles=False)
        traded_by_strategy = simulator.get_net_traded_amounts_by_strategy(True, True)

        # check traded amount for a specific product
        traded = traded_by_strategy[strategy_id]

        self.assertEqual(traded['10000302_1']['net_volume'], 4.0)
        self.assertEqual(traded['10000302_1']['start'], 1623780000)
        self.assertEqual(traded['10000302_1']['end'], 1623816000)
        self.assertEqual(traded['10000302_1']['name'], u'Gas - NG Prompt_WD_20210615-20')
        self.assertEqual(traded['10000302_1']['total_volume'], 2004.0)


if __name__ == '__main__':
    unittest.main()
