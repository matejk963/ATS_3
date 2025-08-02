import datetime
import os
import unittest

import autotrader_lib.common as COMMON
import autotrader_lib.util as ALU
import backtesting.simulate as SIM
import backtesting.strategy_configuration as SCON
import backtesting.synchronous_backtesting_utils as SBU
from backtesting import ROOT_PATH


EXAMPLE_STRATEGIES_FOLDER = os.path.dirname(__file__)

TRAYPORT_EXCHANGE_FEED = os.path.join(ROOT_PATH, "own_strategies", "workshop_examples", "assets",
                                      "ttf", "20210615T14-15_ttfhical_gas_wd_1msg.jsonl")

DT = datetime.datetime
dt_to_ts = ALU.convert_dt_to_float_timestamp


class StrategyConfigurationTest(unittest.TestCase):
    def test(self):
        strategy_id = "strat_1"
        strategy_package = "synth_ord_strategy"

        # This pretends that previously a REST call has already been made to POST /packages
        #  with a content {"package_name": "synth_ord_strategy", "package_zip": <<FILE.ZIP>>}
        # in the simulation the package is known, because we tell the simulator the path to the strategy folder

        strategy_config = SCON.StrategyConfiguration(
            strategy_id=strategy_id,
            instrument_ids=[COMMON.Area.ttf],
            strategies_folder=EXAMPLE_STRATEGIES_FOLDER,
            caption="Example strategy",
            package_name=strategy_package,
            active=False,
            so_products=[COMMON.SequenceId.gas_prompt + "_" + COMMON.GasPromptItemId.within_day]  # 10000302_1
        )
        # activation needs to be after creation...
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

        simulator = SIM.Simulator([strategy_activate_message, limits_setup_message],
                                  feed_paths=[TRAYPORT_EXCHANGE_FEED],
                                  simulated_exchanges=(COMMON.Exchange.trayport,),
                                  use_persistence=False,
                                  strategies_folder=EXAMPLE_STRATEGIES_FOLDER)
        simulator.run(write_logfiles=False)
        simulator.get_net_traded_amounts_by_strategy(True, True)


if __name__ == '__main__':
    unittest.main()
