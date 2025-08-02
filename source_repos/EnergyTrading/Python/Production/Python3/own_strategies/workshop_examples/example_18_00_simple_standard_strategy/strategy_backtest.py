import datetime
import os
import unittest

import autotrader_lib.common as COMMON
import autotrader_lib.cet_util as ALCU
import backtesting.simulate as SIM
import backtesting.strategy_definition as SD
from backtesting import ROOT_PATH


EXAMPLE_STRATEGIES_FOLDER = os.path.dirname(os.path.dirname(__file__))

TRAYPORT_EXCHANGE_FEED = os.path.join(ROOT_PATH, "own_strategies", "workshop_examples", "assets",
                                      "ttf", "20210615T14-15_ttfhical_NEW_1msg.jsonl")


class GasStrategyBacktest(unittest.TestCase):
    def test_example_simulation(self):

        simulated_strategy = os.path.basename(os.path.dirname(__file__))

        # !!! It's very important to choose the start_time so that the following intervals starting from this section
        # cover the product interval with a match on the start and end times !!!

        start_time = datetime.datetime(2021, 6, 15, 12, 0, 0)
        strategy = SD.StrategyDefinition(
            strategy_id=simulated_strategy,
            valid_from=start_time,
            valid_until=datetime.datetime(2021, 6, 16, 12, 0, 0),
            strategy_package=simulated_strategy,
            package_path=os.path.dirname(__file__),
            set_default_limits=True,
            exchange_1=COMMON.Exchange.trayport,
            market_area_1=COMMON.Area.ttf,
            ts_raster=COMMON.HOUR,
            active=True
        )

        # Create a simulator and start the simulation:
        # the strategy, potential strategy updates and steering calls have to be defined upfront
        # in strategy.export, we can give a time, at which this strategy should be transferred.
        # if no time is given, it is transferred 1 minute before valid_from.
        # Note: Transferring the strategy earlier than the exchange feed
        # will unnecessarily increase the runtime of the simulation.
        strategy_messages = [strategy.export(ALCU.cet_dt2ts(start_time))]

        simulator = SIM.Simulator(strategy_messages,
                                  feed_paths=[TRAYPORT_EXCHANGE_FEED],
                                  simulated_exchanges=(COMMON.Exchange.trayport, ),
                                  use_persistence=False,  # set this to True to use MongoDB
                                  strategies_folder=EXAMPLE_STRATEGIES_FOLDER,
                                  )
        simulator.run(write_logfiles=False)  # Set write_logfiles to True to write logfiles (in the current directory)
        simulator.get_net_traded_amounts_by_strategy(printout=True, only_traded=True)


if __name__ == '__main__':
    unittest.main()
