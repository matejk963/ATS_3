from __future__ import print_function

import datetime
import os
import unittest

import autotrader_core.common as COMMON
import autotrader_lib.cet_util as ALCU
import autotrader_lib.util as ALU
import backtesting.simulate as SIM
import backtesting.strategy_definition as SD

from backtesting import ROOT_PATH


def common_workshop_asset(*asset):
    return os.path.join(ROOT_PATH, "own_strategies", "workshop_examples", "assets", *asset)


# the folder in which the current folder is
EXAMPLE_STRATEGIES_FOLDER = os.path.dirname(os.path.dirname(__file__))

# for short simulation
EPEX_EXCHANGE_FEED_JULY_18 = common_workshop_asset(
    "epex", "2021-07-18_COMPLETE_finished_apg_08-09_prod_12363625_12363598_filtered_4hbefore.zip"
)


class PowerStrategyBacktest(unittest.TestCase):
    def test(self):
        ################################################
        # Define simulation and message transfer times #
        ################################################

        simulated_strategy = os.path.basename(os.path.dirname(__file__))

        area = COMMON.Area.apg
        exchange = COMMON.Exchange.epex

        # UTC time
        # we want 8-9 CET, so 6-7 UTC
        # timeseries will be entered for values from here
        start_time = datetime.datetime(2021, 7, 18, 6, 0, 0)
        end_time = start_time + datetime.timedelta(hours=1)
        # transfer time, strategy starts to trade from here, utc datetime
        transfer_time = start_time - datetime.timedelta(hours=6)

        ###########################################
        # Strategy Definition and fill Timeseries #
        ###########################################
        user_ts = []

        strategy = SD.StrategyDefinition(
            strategy_id=simulated_strategy,
            valid_from=start_time,
            valid_until=end_time,
            algo_name="USERDEF",
            market_area_1=area,
            strategy_package=simulated_strategy,
            package_path=os.path.dirname(__file__),
            ts_raster=COMMON.QUARTER,
            exchange=exchange,
            user_ts=user_ts,
        )

        # timeseries name without prepended "strategy_"
        strategy.fill("limit_maximum_purchase_price", values=100)
        strategy.fill("limit_minimum_sales_price", values=0)
        strategy.fill("position_tradable_position_long", values=12)
        strategy.fill("position_tradable_position_short", values=0)
        strategy.fill("price_purchase", values=30)
        strategy.fill("price_sales", values=40)
        strategy.params["active"] = True

        # start simulation and check for expected outcomes
        strategy_messages = [strategy.export(ALCU.utc_dt2ts(transfer_time))]

        # Define simulated OMT limits:
        short_omt = ALU.OMTParameters(
            status=COMMON.EpexOMTState.NO_RESTRICTION,
            received_omt=0,
            lower_threshold=20,
            upper_threshold=30,
            cooldown_period=10,
            observation_period=10,
            tolerance_period=5,
            limit_type="short"
        )

        # and now start to run the simulation
        simulator = SIM.Simulator(strategy_messages,
                                  feed_paths=[EPEX_EXCHANGE_FEED_JULY_18],
                                  simulated_exchanges=(COMMON.Exchange.epex, ),
                                  use_persistence=False,  # set this to True to use MongoDB
                                  overwrite_database=True,
                                  database_name=self.__class__.__name__ + "-" + self._testMethodName,
                                  strategies_folder=EXAMPLE_STRATEGIES_FOLDER,
                                  timer_timestep=10,
                                  timer_fast_timestep=1,
                                  save_results=True,
                                  short_omt_parameters=short_omt,
                                  # for long_omt_parameters the defaults will be used
                                  )

        simulator.run(write_logfiles=False)  # Set write_logfiles to True to write logfiles (in the current directory)
        traded_by_strategy = simulator.get_net_traded_amounts_by_strategy(printout=True)

        # Speed up post-simulation (only uncomment if interested):
        # simulator.export_market_data(trade_type="PublicTrade", exchange_id="EPEX")
        # simulator.export_own_trades()
        # simulator.export_public_trades()

        # Export the OMT values over time to csv:
        simulator.export_historical_omt_data()


if __name__ == '__main__':
    print("Starting simple example")
    unittest.main()
