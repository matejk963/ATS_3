from __future__ import print_function

import datetime
import os
import unittest

import autotrader_core.common as COMMON
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
    def test_01(self):
        ################################################
        # Define simulation and message transfer times #
        ################################################

        # TASK: set the exchange to the name of the folder
        strategy_id = os.path.basename(os.path.dirname(__file__))

        # TASK: set the area to apg
        area = None
        # TASK: set the exchange to epex
        exchange = None

        # UTC time
        # we want 8-9 CET, so 6-7 UTC
        # timeseries will be entered for values from here
        # TASK: set the strategy start and end validity to this 1 hour window
        start_time = None

        # transfer time, strategy starts to trade from here, utc datetime
        # TASK: set the strategy transfer time to a datetime 6 hours before the delivery start
        transfer_time = None

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
        # TASK: fill the timeseries "limit_maximum_purchase_price"with the value values=100
        # TASK: fill the timeseries "limit_minimum_sales_price"with the value values=0
        # TASK: fill the timeseries "position_tradable_position_long"with the value values=12
        # TASK: fill the timeseries "position_tradable_position_short"with the value values=0
        # TASK: fill the timeseries "price_purchase"with the value values=30
        # TASK: fill the timeseries "price_sales"with the value values=40
        # TASK: set the strategy active parameter

        # start simulation and check for expected outcomes
        # TASK: set the strategy messages by exporting the strategy definition
        strategy_messages = None

        simulator = SIM.Simulator(strategy_messages,
                                  feed_paths=[EPEX_EXCHANGE_FEED_JULY_18],
                                  simulated_exchanges=(COMMON.Exchange.epex, ),
                                  use_persistence=False,  # set this to True to use MongoDB
                                  strategies_folder=EXAMPLE_STRATEGIES_FOLDER,
                                  )

        simulator.run(write_logfiles=False)  # Set write_logfiles to True to write logfiles (in the current directory)
        simulator.get_net_traded_amounts_by_strategy(printout=True, only_traded=False)

        # export public trades and own trades for further analysis
        # TASK: export own trade, public trades and market data after the simulation


if __name__ == '__main__':
    print("Starting simple example")
    unittest.main()
