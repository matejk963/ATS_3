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
        strategy_config.update(dict(active=True))
        strategy_activate_message = SBU.create_strategy_config_message(timestamp=dt_to_ts(DT(2021, 6, 15, 12, 2, 0)),
                                                                       strategy_id=strategy_id,
                                                                       strategy_configuration=strategy_config)

        simulator = SIM.Simulator([strategy_insert_message, strategy_activate_message],
                                  feed_paths=[os.path.join(ROOT_PATH, "own_strategies", "workshop_examples", "assets",
                                                           "ttf", "20210615T14-15_ttfhical_gas_wd.zip")],
                                  simulated_exchanges=(COMMON.Exchange.trayport,),
                                  use_persistence=False,
                                  strategies_folder=EXAMPLE_STRATEGIES_FOLDER)
        simulator.run(write_logfiles=False)


if __name__ == '__main__':
    unittest.main()
