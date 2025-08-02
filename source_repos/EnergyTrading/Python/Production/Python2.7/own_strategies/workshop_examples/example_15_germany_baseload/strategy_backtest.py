from __future__ import print_function

import os
import unittest

from datetime import date, datetime
import autotrader_lib.cet_util as ALCU
import backtesting.simulate as SIM
import backtesting.strategy_definition as SD
import autotrader_core.common as COMMON
import backtesting.synchronous_backtesting_utils as SBU

DE_BASELOAD_EEX = COMMON.Area.de_bl

TRAYPORT_CONFIG = {
    "venues": "OTC, EEX, EEXWD, IENX, EEX A",
    "commodities": "Gas, Euro, EUA",
    "product_subscription_max_years": 2,
    "product_subscription_shortterm_days": 2,
    "product_subscription_midterm_count": 200,
    "product_subscription_longterm_count": 100
}

CUSTOM_STRATEGIES_FOLDER = os.path.dirname(os.path.dirname(__file__))

DT = date(2022, 3, 25)

# init files can be in the directory as zip to save space, but we have to pass them without the zip
INIT_DIRECTORY = os.path.join(os.path.dirname(__file__), 'init_files_{}'.format(DT.strftime('%Y-%m-%d')))
# zipped the jsonl MAR file, to save space. here passing the zip is fine too.
FEED_FILE = os.path.join(os.path.dirname(__file__), 'MAR-220325_de_baseload_10641710.zip')


class BaseloadStrategyBacktest(unittest.TestCase):
    def test_example_simulation(self):
        simulated_strategy = os.path.basename(os.path.dirname(__file__))
        print(CUSTOM_STRATEGIES_FOLDER, INIT_DIRECTORY, FEED_FILE, simulated_strategy)

        # UTC times
        transfer_time = datetime(DT.year, DT.month, DT.day, 7, 0, 0)
        start_time = datetime(DT.year, DT.month, DT.day, 8, 0, 0)
        end_time = datetime(DT.year, DT.month, DT.day, 10, 0, 0)

        strategy = SD.StrategyDefinition(
            strategy_id=simulated_strategy,
            valid_from=start_time,
            valid_until=end_time,
            strategy_package=simulated_strategy,
            package_path=os.path.dirname(__file__),
            set_default_limits=False,
            exchange_1=COMMON.Exchange.trayport,
            market_area_1=DE_BASELOAD_EEX,
            ts_raster=COMMON.DAY,
            active=True,
            maximum_bid=200,
            maximum_ask=200,
            maximum_order_book=1000
        )
        strategy.params["active"] = True
        strategy_message_1 = strategy.export(ALCU.utc_dt2ts(transfer_time))
        strategy.params["active"] = False
        strategy_message_2 = strategy.export(ALCU.utc_dt2ts(transfer_time) + 7200)

        # set some high limits, since without limits trading is not allowed.
        thousand = dict.fromkeys([str(n) for n in range(10000100, 10000108)], 1000)
        zero = dict.fromkeys([str(n) for n in range(10000100, 10000108)], 0)
        limits_payload = {
            "limits_per_sequence": {"maximum_purchase_volume": thousand,
                                    "minimum_sales_price": zero,
                                    "maximum_sales_volume": thousand,
                                    "maximum_purchase_price": thousand}
        }

        limits_setup_message = SBU.create_per_products_limit_message(timestamp=ALCU.utc_dt2ts(transfer_time) + 1,
                                                                     strategy_id=strategy.strategy_id,
                                                                     limits_dict=limits_payload)

        # speed up the simulation by setting the timer to have bigger than 10s steps
        simulator = SIM.Simulator([strategy_message_1, strategy_message_2, limits_setup_message],
                                  feed_paths=[FEED_FILE],
                                  simulated_exchanges=(COMMON.Exchange.trayport,),
                                  use_persistence=False,
                                  trayport_init_directory=INIT_DIRECTORY,
                                  strategies_folder=CUSTOM_STRATEGIES_FOLDER,
                                  trayport_config=TRAYPORT_CONFIG,
                                  save_results=False,  # turn this on, if you would like to keep a snapshot of this run
                                  timer_timestep=360,
                                  timer_fast_timestep=360,
                                  simulation_stop=ALCU.utc_dt2ts(transfer_time) + 7201
                                  )
        simulator.run(write_logfiles=False)
        # export trades, to have a csv ready in the ./backtesting_results folder
        # simulator.export_own_trades()

        # retrieve the traded amounts by strategy and run some additional asserts
        # turn printout on to get a result table outputted to the terminal
        # turn only_traded on to only print out the products which have traded in the result tabel
        traded_by_strategy = simulator.get_net_traded_amounts_by_strategy(printout=False, only_traded=False)

        # check traded amount for a specific product
        traded = traded_by_strategy[strategy.strategy_id]
        self.assertEqual(traded['10000106_20']['net_volume'], 41.0)
        self.assertEqual(traded['10000106_20']['start'], 1672527600)
        self.assertEqual(traded['10000106_20']['end'], 1704063600)
        self.assertEqual(traded['10000106_20']['name'], u'Euro - Euro Years_2023_2023')
        self.assertEqual(traded['10000106_20']['total_volume'], 43.0)


if __name__ == '__main__':
    print("Starting...")
    unittest.main()
