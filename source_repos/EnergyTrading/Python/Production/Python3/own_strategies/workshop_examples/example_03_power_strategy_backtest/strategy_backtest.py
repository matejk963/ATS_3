

import datetime
import os
import unittest

import autotrader_lib.common as COMMON
import autotrader_lib.cet_util as ALCU
import backtesting.simulate as SIM
import backtesting.strategy_definition as SD

from backtesting import ROOT_PATH


def common_workshop_asset(*asset):
    return os.path.join(ROOT_PATH, "own_strategies", "workshop_examples", "assets", *asset)


# the folder in which the current folder is
EXAMPLE_STRATEGIES_FOLDER = os.path.dirname(os.path.dirname(__file__))

# for short simulation
EPEX_EXCHANGE_FEED_JULY_18 = common_workshop_asset(
    "epex",
    "2021-05-17_DelRng_0800-0900_FeedRng_0600-0605_PrSh_1_Amprion_RTE_APG_TenneT_50Hz_dur_15_60.jsonl.gz"
)


class PowerStrategyBacktest(unittest.TestCase):
    def test_01(self):
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

        # start simulation and check for expected outcomes
        strategy_messages = [strategy.export(ALCU.utc_dt2ts(transfer_time))]

        # to show more what export does in this example, we make some additional tests here:
        # check if package was built correctly
        # we assume a strategy message, which is simulated to be sent from periotheus, and has the strategy object in it
        self.assertEqual(strategy_messages[0]["message_type"], "strategy")
        self.assertEqual(strategy_messages[0]["exchange"], COMMON.Exchange.periotheus)
        self.assertEqual(strategy_messages[0]["data"]['strategy_objects'][simulated_strategy]["active"], True)
        self.assertEqual(
            strategy_messages[0]["data"]['strategy_objects'][simulated_strategy]["user_defined_timeseries"],
            {})

        # check if timeseries were converted correctly
        # we assume a strategy message, which is simulated to be sent from periotheus, and has the strategy object in it
        self.assertEqual(
            strategy_messages[0]["data"]['strategy_objects'][simulated_strategy][COMMON.StrategyJsonKey.TS.price_sell],
            [{'begin': 1626588000, 'end': 1626588900, 'value': 40.0},
             {'begin': 1626588900, 'end': 1626589800, 'value': 40.0},
             {'begin': 1626589800, 'end': 1626590700, 'value': 40.0},
             {'begin': 1626590700, 'end': 1626591600, 'value': 40.0}]
        )
        self.assertEqual(
            strategy_messages[0]["data"]['strategy_objects'][simulated_strategy][
                COMMON.StrategyJsonKey.TS.limit_buy_price],
            [{'begin': 1626588000, 'end': 1626588900, 'value': 100.0},
             {'begin': 1626588900, 'end': 1626589800, 'value': 100.0},
             {'begin': 1626589800, 'end': 1626590700, 'value': 100.0},
             {'begin': 1626590700, 'end': 1626591600, 'value': 100.0}]
        )

        # and now start to run the simulation

        simulator = SIM.Simulator(strategy_messages,
                                  feed_paths=[EPEX_EXCHANGE_FEED_JULY_18],
                                  simulated_exchanges=(COMMON.Exchange.epex, ),
                                  use_persistence=False,  # set this to True to use MongoDB
                                  overwrite_database=True,
                                  save_results=False,
                                  database_name=self.__class__.__name__ + "-" + self._testMethodName,
                                  strategies_folder=EXAMPLE_STRATEGIES_FOLDER,
                                  timer_timestep=COMMON.HOUR,
                                  timer_fast_timestep=COMMON.HOUR,
                                  )

        simulator.run(write_logfiles=False)  # Set write_logfiles to True to write logfiles (in the current directory)
        traded_by_strategy = simulator.get_net_traded_amounts_by_strategy(printout=True)

        print("===TRADED BY STRAT===")
        print(traded_by_strategy)
        print("=====================")

        simulator.export_market_data(trade_type="PublicTrade", exchange_id="EPEX")

        simulator.export_own_trades()
        simulator.export_public_trades()


if __name__ == '__main__':
    print("Starting simple example")
    unittest.main()
