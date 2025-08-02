from __future__ import print_function

import copy
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


# the folder in which the current folder is
EXAMPLE_STRATEGIES_FOLDER = os.path.dirname(os.path.dirname(__file__))

# for short simulation
EPEX_EXCHANGE_FEED_JULY_18 = common_workshop_asset(
    "epex",
    "2021-07-18_COMPLETE_finished_apg_08-09_prod_12363625_12363598_2_orders_slim_feed.jsonl"
)


class OTRCalcCheckBacktest(unittest.TestCase):

    def test_otr_for_normal_trades(self):
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
        strategy.fill("limit_maximum_sales_volume", values=500)
        strategy.fill("limit_maximum_purchase_volume", values=500)

        # timeseries name without prepended "strategy_"
        strategy.fill("limit_maximum_purchase_price", values=100)
        strategy.fill("limit_minimum_sales_price", values=0)
        strategy.fill("position_tradable_position_long", values=12)
        strategy.fill("position_tradable_position_short", values=0)
        strategy.fill("price_purchase", values=30)
        strategy.fill("price_sales", values=40)
        strategy.params["active"] = True

        ###############################################
        # Add second strategy with opposite positions #
        ###############################################
        strategy2 = copy.deepcopy(strategy)
        strategy2.strategy_id = strategy.strategy_id
        strategy2.fill("price_purchase", values=31)
        strategy2.fill("price_sales", values=41)
        strategy2.fill("position_tradable_position_long", values=0)
        strategy2.fill("position_tradable_position_short", values=12)

        # start simulation and check for expected outcomes
        strategy_messages = [
            strategy.export(ALCU.utc_dt2ts(transfer_time)),
            strategy2.export(ALCU.utc_dt2ts(transfer_time) + 60),
        ]

        # and now start to run the simulation

        simulator = SIM.Simulator(strategy_messages,
                                  feed_paths=[EPEX_EXCHANGE_FEED_JULY_18],
                                  simulated_exchanges=(COMMON.Exchange.epex,),
                                  use_persistence=False,  # set this to True to use MongoDB
                                  strategies_folder=EXAMPLE_STRATEGIES_FOLDER,
                                  )

        simulator.run(write_logfiles=False)  # Set write_logfiles to True to write logfiles (in the current directory)
        product_id = "12363625"
        product = simulator.autotrader_child.epex.products.get_by_id(product_id)

        # assert OTR 0 for internal trades
        self.assertEqual(product.order_to_trade_ratio(area), 2)

    def test_otr_for_internal_trades_after_placing_on_market(self):
        ################################################
        # Define simulation and message transfer times #
        ################################################

        simulated_strategy = os.path.basename(os.path.dirname(__file__))

        area = COMMON.Area.rwe
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
        strategy.fill("limit_maximum_sales_volume", values=500)
        strategy.fill("limit_maximum_purchase_volume", values=500)

        # timeseries name without prepended "strategy_"
        strategy.fill("limit_maximum_purchase_price", values=100)
        strategy.fill("limit_minimum_sales_price", values=0)
        strategy.fill("position_tradable_position_long", values=12)
        strategy.fill("position_tradable_position_short", values=0)
        strategy.fill("price_purchase", values=30)
        strategy.fill("price_sales", values=40)
        strategy.params["active"] = True

        ###############################################
        # Add second strategy with opposite positions #
        ###############################################
        other_strategy = copy.deepcopy(strategy)
        other_strategy.strategy_id = strategy.strategy_id + "_other"
        other_strategy.fill("price_purchase", values=35)
        other_strategy.fill("price_sales", values=45)
        other_strategy.fill("position_tradable_position_long", values=0)
        other_strategy.fill("position_tradable_position_short", values=12)

        ###############################################
        # Add second strategy with opposite positions #
        ###############################################
        other_strategy2 = copy.deepcopy(strategy)
        other_strategy2.strategy_id = strategy.strategy_id + "_other"
        other_strategy2.fill("price_purchase", values=100)
        other_strategy2.fill("price_sales", values=120)
        other_strategy2.fill("position_tradable_position_long", values=0)
        other_strategy2.fill("position_tradable_position_short", values=12)

        ###############################################
        # Add second strategy with opposite positions #
        ###############################################
        strategy2 = copy.deepcopy(strategy)
        strategy2.strategy_id = strategy.strategy_id
        strategy2.fill("price_purchase", values=31)
        strategy2.fill("price_sales", values=41)
        strategy2.fill("position_tradable_position_long", values=50)
        strategy2.fill("position_tradable_position_short", values=0)

        # start simulation and check for expected outcomes
        strategy_messages = [
            strategy.export(ALCU.utc_dt2ts(transfer_time)),
            other_strategy.export(ALCU.utc_dt2ts(transfer_time) + 1),
            other_strategy2.export(ALCU.utc_dt2ts(transfer_time) + 60),
            strategy.export(ALCU.utc_dt2ts(transfer_time) + 60),
        ]

        # and now start to run the simulation

        simulator = SIM.Simulator(strategy_messages,
                                  feed_paths=[EPEX_EXCHANGE_FEED_JULY_18],
                                  simulated_exchanges=(COMMON.Exchange.epex,),
                                  use_persistence=False,  # set this to True to use MongoDB
                                  strategies_folder=EXAMPLE_STRATEGIES_FOLDER,
                                  )

        simulator.run(write_logfiles=False)  # Set write_logfiles to True to write logfiles (in the current directory)
        product_id = "12363625"
        product = simulator.autotrader_child.epex.products.get_by_id(product_id)

        # assert OTR 0 for internal trades
        self.assertEqual(product.order_to_trade_ratio(area), 2)

    def test_otr_for_internal_trades(self):
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
        strategy.fill("limit_maximum_sales_volume", values=500)
        strategy.fill("limit_maximum_purchase_volume", values=500)

        # timeseries name without prepended "strategy_"
        strategy.fill("limit_maximum_purchase_price", values=100)
        strategy.fill("limit_minimum_sales_price", values=0)
        strategy.fill("position_tradable_position_long", values=12)
        strategy.fill("position_tradable_position_short", values=0)
        strategy.fill("price_purchase", values=30)
        strategy.fill("price_sales", values=40)
        strategy.params["active"] = True

        ###############################################
        # Add second strategy with opposite positions #
        ###############################################
        other_strategy = copy.deepcopy(strategy)
        other_strategy.strategy_id = strategy.strategy_id + "_other"
        other_strategy.fill("price_purchase", values=100)
        other_strategy.fill("price_sales", values=120)
        other_strategy.fill("position_tradable_position_long", values=0)
        other_strategy.fill("position_tradable_position_short", values=12)

        ###############################################
        # Add second strategy with opposite positions #
        ###############################################
        strategy2 = copy.deepcopy(strategy)
        strategy2.strategy_id = strategy.strategy_id
        strategy2.fill("price_purchase", values=30)
        strategy2.fill("price_sales", values=40)
        strategy2.fill("position_tradable_position_long", values=50)
        strategy2.fill("position_tradable_position_short", values=0)

        # start simulation and check for expected outcomes
        strategy_messages = [
            strategy.export(ALCU.utc_dt2ts(transfer_time)),
            other_strategy.export(ALCU.utc_dt2ts(transfer_time) + 1),
            strategy.export(ALCU.utc_dt2ts(transfer_time) + 60),
        ]

        # and now start to run the simulation

        simulator = SIM.Simulator(strategy_messages,
                                  feed_paths=[EPEX_EXCHANGE_FEED_JULY_18],
                                  simulated_exchanges=(COMMON.Exchange.epex,),
                                  use_persistence=False,  # set this to True to use MongoDB
                                  strategies_folder=EXAMPLE_STRATEGIES_FOLDER,
                                  )

        simulator.run(write_logfiles=False)  # Set write_logfiles to True to write logfiles (in the current directory)
        product_id = "12363625"
        product = simulator.autotrader_child.epex.products.get_by_id(product_id)

        # assert OTR 0 for internal trades
        self.assertEqual(product.order_to_trade_ratio(area), 1)


if __name__ == '__main__':
    unittest.main()
