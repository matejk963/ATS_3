
from __future__ import print_function

import datetime
import os
import unittest

import autotrader_core.common as COMMON
import autotrader_lib.cet_util as CETUTIL
import backtesting.simulate as SIM
import backtesting.strategy_definition as SD
import backtesting.synchronous_backtesting_utils as SBU
from backtesting import ROOT_PATH
from backtesting.strategy_configuration import StrategyConfiguration


def common_workshop_asset(*asset):
    return os.path.join(ROOT_PATH, "own_strategies", "workshop_examples", "assets", *asset)


# the folder in which the current folder is
EXAMPLE_STRATEGIES_FOLDER = os.path.dirname(os.path.dirname(__file__))

# for short simulation
EPEX_EXCHANGE_FEED_JULY_18 = common_workshop_asset(
    "epex", "2021-07-18_COMPLETE_finished_apg_08-09_prod_12363625_12363598_filtered_4hbefore.zip"
)


class PowerStrategyBacktest(unittest.TestCase):
    def test_01(self):
        ################################################
        # Define simulation and message transfer times #
        ################################################

        strategy_id = os.path.basename(os.path.dirname(__file__))

        area = COMMON.Area.apg
        exchange = COMMON.Exchange.epex

        # UTC time
        # we want 8-9 CET, so 6-7 UTC
        # timeseries will be entered for values from here
        start_time = datetime.datetime(2021, 7, 18, 6, 0, 0)

        # transfer time, strategy starts to trade from here, utc datetime
        transfer_time = start_time - datetime.timedelta(hours=6)

        ###########################################
        # Strategy Definition and fill Timeseries #
        ###########################################
        user_ts = []

        strategy = SD.StrategyDefinition(
            strategy_id=strategy_id,
            valid_from=start_time,
            valid_until=start_time + datetime.timedelta(hours=1),
            algo_name="USERDEF",
            market_area_1=area,
            strategy_package=strategy_id,
            package_path=os.path.dirname(__file__),
            ts_raster=COMMON.QUARTER,
            exchange=exchange,
            user_ts=user_ts,
        )

        # Exercise:
        # to check what happens on limit violation, uncomment these 2 lines, and force a violation:
        # strategy.fill("limit_maximum_sales_volume", values=0)
        # strategy.fill("limit_maximum_purchase_volume", values=0)

        # timeseries name without prepended "strategy_"
        strategy.fill("limit_maximum_purchase_price", values=100)
        strategy.fill("limit_minimum_sales_price", values=0)
        strategy.fill("position_tradable_position_long", values=12)
        strategy.fill("position_tradable_position_short", values=0)
        strategy.fill("price_purchase", values=30)
        strategy.fill("price_sales", values=40)
        strategy.params["active"] = True

        ############################################
        # Add simulated steering call with payload #
        ############################################
        # Using the create_steering_call helper function, we wrap our payload in an envelope understood by the simulator
        steering_call = SBU.create_steering_call(
            strategy_id=strategy_id,
            steering_msg={"steering_call": {
                "operation": "update_timeseries",
                "start": CETUTIL.cet_dt2ts(start_time),
                "end": CETUTIL.cet_dt2ts(start_time) + COMMON.HOUR,
                "ts_raster": COMMON.QUARTER,
                "ts_name": "price_forecasts",
                "value": 50,
            }},
            timestamp=CETUTIL.utc_dt2ts(start_time - datetime.timedelta(hours=5))
        )

        #######################################
        # Add configuration call with payload #
        #######################################
        strategy_config = StrategyConfiguration(
            strategy_id=strategy_id,
            strategies_folder=EXAMPLE_STRATEGIES_FOLDER,
            caption="A strategy",
            package_name=strategy_id,
            instrument_ids=[COMMON.Area.apg],
            exchange=COMMON.Exchange.epex,
        )

        strategy_config.update(dict(active=True))
        strategy_config_msg = SBU.create_strategy_config_message(
            timestamp=CETUTIL.utc_dt2ts(start_time - datetime.timedelta(hours=5)) + 100,
            strategy_id=strategy_id,
            strategy_configuration=strategy_config
        )

        ############################################
        # Add add all messages to the feed and run #
        ############################################
        strategy_messages = [strategy.export(CETUTIL.utc_dt2ts(transfer_time)),
                             steering_call,
                             strategy_config_msg]

        simulator = SIM.Simulator(strategy_messages,
                                  feed_paths=[EPEX_EXCHANGE_FEED_JULY_18],
                                  simulated_exchanges=(COMMON.Exchange.epex, ),
                                  use_persistence=False,  # set this to True to use MongoDB
                                  strategies_folder=EXAMPLE_STRATEGIES_FOLDER,
                                  )

        simulator.run(write_logfiles=False)  # Set write_logfiles to True to write logfiles (in the current directory)
        simulator.get_net_traded_amounts_by_strategy(printout=True, only_traded=False)


if __name__ == '__main__':
    print("Starting simple example")
    unittest.main()
