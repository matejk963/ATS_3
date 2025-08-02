from __future__ import print_function

import datetime
import os
import unittest

import autotrader_core.common as COMMON
import autotrader_lib.cet_util as ALCU
import backtesting.simulate as SIM
import backtesting.strategy_definition as SD
from backtesting import ROOT_PATH


def common_workshop_asset(*asset):
    return os.path.join(ROOT_PATH, "own_strategies", "workshop_examples", "assets", *asset)


def path(*asset_filename):
    return os.path.join(os.path.dirname(__file__), "..", "assets", *asset_filename)


class TestExampleSimulationTTF(unittest.TestCase):
    def setUp(self):
        print("Starting simple example")
        super(TestExampleSimulationTTF, self).setUp()

    def test(self):
        """
        Basic example of a backtest

        You need:
        1) an exchange feed file
        2) a strategy definition
        3) a Simulator
        """

        # 1. The exchange feed file
        trayport_exchange_feed = common_workshop_asset("ttf", "2021-05-04_COMPLETE_first_10000msg.zip")
        trayport_init_files = common_workshop_asset("ttf", "init_files_2021-05-04")
        start_time = datetime.datetime(2021, 5, 4, 0, 0, 0)
        strategy = SD.StrategyDefinition(
            strategy_id="test_gas_position_closer_strategy",
            valid_from=start_time,
            valid_until=datetime.datetime(2021, 5, 5, 0, 0, 0),  # The DST change was on Oct 25
            package_path=os.path.join(ROOT_PATH, "own_strategies", "gas_position_closer"),
            set_default_limits=True,
            exchange_1=COMMON.Exchange.trayport,
            market_area_1=COMMON.Area.ttf,
            ts_raster=COMMON.HOUR,
            active=True,
            maximum_order_book=2  # Needs to be at least 2, so maximum_order_book/2 can be rounded to an int.
        )

        daily_values = [[30] * 24]

        flat_list = [pos for subl in daily_values for pos in subl]

        strategy.fill("position_tradable_position_short", flat_list)
        strategy.fill("price_purchase", 12)
        strategy.fill("price_purchase_immediate_vesting", 10)

        # Sell position
        strategy.fill("price_sales", 24.0)
        strategy.fill("price_sales_immediate_vesting", 34.0)

        # 3. Create a simulator and start the simulation
        # the strategy, potential strategy updates and steering calls have to be defined upfront
        # in strategy.export, we can give a time, at which this strategfy should be transferred.
        # if no time is given, it is transferred 1 minute before valid_from.
        # Note: Transferring the strategy earlier than the exchange feed
        # will unnecessarily increase the runtime of the simulation.
        strategy_messages = [strategy.export(ALCU.cet_dt2ts(start_time))]

        simulator = SIM.Simulator(strategy_messages,
                                  feed_paths=[trayport_exchange_feed],
                                  simulated_exchanges=(COMMON.Exchange.trayport, ),
                                  use_persistence=False,  # set this to True to use MongoDB
                                  trayport_init_directory=trayport_init_files
                                  )
        simulator.run(write_logfiles=False)  # Set write_logfiles to True to write logfiles (in the current directory)


if __name__ == '__main__':
    unittest.main()
