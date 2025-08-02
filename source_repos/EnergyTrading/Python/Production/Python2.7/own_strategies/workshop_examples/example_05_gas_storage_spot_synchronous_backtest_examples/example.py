from __future__ import print_function
import os
import datetime
import unittest

import autotrader_core.common as COMMON
import autotrader_core.compliance_log_templates as LOGTEMP
import backtesting.simulate as SIM
import backtesting.strategy_definition as SD
import backtesting.synchronous_backtesting_utils as SBU
from backtesting import ROOT_PATH


def path(asset_filename):
    return os.path.join(os.path.dirname(__file__), "..", "assets", asset_filename)


class TestExampleSimulation(unittest.TestCase):
    def setUp(self):
        print("Starting simple example")
        super(TestExampleSimulation, self).setUp()

    def test(self):
        """
        Basic example of a backtest

        You need:
        1) an exchange feed file
        2) a strategy definition
        3) a Simulator
        """

        # 1. The exchange feed file
        trayport_exchange_feed = path("TrayportFeed_1000302_SHORT.zip")

        # 2. The strategy definition is the same as in the multiprocessed_backtesting example.
        strategy = SD.StrategyDefinition(
            strategy_id="test_gas_storage_strategy",
            # valid_from and valid_to defines, how many values each timeseries holds. In UTC
            valid_from=datetime.datetime(2020, 9, 6, 4, 0, 0),
            valid_until=datetime.datetime(2020, 9, 7, 4, 0, 0),
            # User-defined timeseries used by the algorithm. They have to start with "strategy_"
            user_ts=["strategy_storage_cutoff_purchase", "strategy_storage_cutoff_sell"],
            # The path to the strategy folder.
            # This folder should contain at least the files __init__.py and custom_strategy.py
            # If the package_path is in own_strategies, debug points can be set inside the strategy.
            package_path=os.path.join(ROOT_PATH, "own_strategies", "gas_strategy_storage"),
            set_default_limits=True,  # Set very wide limits that will never get triggered.
            exchange_1=COMMON.Exchange.trayport,
            market_area_1="10002806",  # Use an instrument_id as string here
            # Currently, only 15 min and hourly rasters are fully supported by autoTRADER.
            # Periotheus currently only transfers data in 15 minutes rasters.
            ts_raster=COMMON.HOUR,
            active=True  # Trading active has to be set explicitly
        )

        # Fill the Timeseries
        # The standard timeseries are:
        # "price_purchase", "price_sales", "position_tradable_position_short", "position_tradable_position_long",
        # "price_minimum_spread_buyback", "price_forecast_trend", "price_purchase_immediate_vesting",
        # "position_deviation", "price_sales_immediate_vesting"
        # The standard limit timeseries are:
        # "limit_maximum_purchase_price", "limit_minimum_sales_price"
        # "limit_maximum_purchase_volume", "limit_maximum_sales_volume"
        # Buy position
        # As the timeseries is valid for 24 hours and we use a hourly raster, we have to fill in 24 values...
        strategy.fill("position_tradable_position_short",
                      [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0])
        # ... or we use a single value that will be used for all hours.
        strategy.fill("price_purchase_immediate_vesting", 11.0)
        strategy.fill("price_purchase", 11.25)
        strategy.fill("strategy_storage_cutoff_purchase", 11.45)  # user-defined tiemseries, defined above.
        # Sell position
        strategy.fill("position_tradable_position_long", 5)
        strategy.fill("strategy_storage_cutoff_sell", 11.55)  # user-defined tiemseries, defined above.
        strategy.fill("price_sales", 11.75)
        strategy.fill("price_sales_immediate_vesting", 12.0)

        # Limits are as follows when set_default_limits=True
        # To change the limits, use set_default_limits=False in the StrategyDefinition and uncomment the following code.
        # strategy.fill("limit_maximum_purchase_price", 1000)
        # strategy.fill("limit_maximum_purchase_volume", 1000)
        # strategy.fill("limit_maximum_sales_volume", 1000)
        # strategy.fill("limit_minimum_sales_price", -1000)

        # 3. Create a simulator and start the simulation
        # the strategy, potential strategy updates and steering calls have to be defined upfront
        # in strategy.export, we can give a time, at which this strategfy should be transferred.
        # if no time is given, it is transferred 1 minute before valid_from.
        # Note: Transferring the strategy earlier than the exchange feed
        # will unnecessarily increase the runtime of the simulation.
        strategy_messages = [strategy.export()]

        simulator = SIM.Simulator(strategy_messages,
                                  feed_paths=[trayport_exchange_feed],
                                  simulated_exchanges=(COMMON.Exchange.trayport, ),
                                  use_persistence=False,  # set this to True to use MongoDB
                                  )
        simulator.run(write_logfiles=False)  # Set write_logfiles to True to write logfiles (in the current directory)

        # 4. Investigate the result of the simulation
        # After the simulation, you have direct access to the exchange object which you can use to validate the
        # simulation results. WARNING: If you don't store the results, the data is garbage collected by python.

        # In this example, we simply assert that the strategy has placed an order
        orders = simulator.autotrader.trayport.products.get_by_id("10000302_1").orders.get_own_order_ids()
        assert orders

        # 4.1 Additionally, you can write some of the test results to the compliance log file. See the example below:
        # (works only if `write_logfiles` is set to `True` when running simulation)
        # Currently, two message types are available:
        # - INFO messages. One is to use LOGTEMP.BacktestingLogs.info_message template here
        # - ERROR messages. One is to use LOGTEMP.BacktestingLogs.error_message template here
        # The only mandatory keyword argument for these message types is "message",
        # so it has to be passed to the compliance_log method.
        # Other keyword arguments will appear in the compliance logs as additional field of an json log entry.

        simulator.compliance_log(LOGTEMP.BacktestingLogs.info_message,
                                 message="Strategy has placed orders: {}".format(orders),
                                 orders=str(orders))

        simulator.compliance_log(LOGTEMP.BacktestingLogs.error_message,
                                 message="This is not an actual error, just an example")


class TestWithSteering(unittest.TestCase):
    def setUp(self):
        print("Starting example with steering calls")
        super(TestWithSteering, self).setUp()

    def test(self):
        # 1. The exchange feed file
        trayport_exchange_feed = path("TrayportFeed_1000302_SHORT.zip")

        # 2. The strategy definition is the same as in the multiprocessed_backtesting example.
        strategy = SD.StrategyDefinition(
            strategy_id="test_manual_strategy",
            # valid_from and valid_to defines, how many values each timeseries holds. In UTC
            valid_from=datetime.datetime(2020, 9, 6, 4, 0, 0),
            valid_until=datetime.datetime(2020, 9, 8, 4, 0, 0),
            # The path to the strategy folder.
            # This folder should contain at least the files __init__.py and custom_strategy.py
            # If the package_path is in own_strategies, debug points can be set inside the strategy.
            package_path=os.path.join(ROOT_PATH, "own_strategies", "manual_trading_strategy"),
            set_default_limits=True,
            exchange_1=COMMON.Exchange.trayport,
            market_area_1="10002806",
            active=True  # Trading active has to be set explicitly
        )
        strategy.fill("limit_maximum_purchase_volume", 30)

        # Now export the strategy into a message understood by autoTRADER.
        # If no timestamp is given, the strategy will be transferred to autoTRADER 1 minute before the
        # timeserie's valid_from date
        strategy_messages = [strategy.export()]

        # To update the timeseries at a specific simulation timestamp, we modify the strategy
        # and export it with a later date. The time can be given as naive datetime assumed to be in utc
        # or as epoch timestamp.
        strategy.fill("limit_maximum_purchase_volume", 60)
        strategy_messages.append(strategy.export(datetime.datetime(2020, 9, 6, 15)))

        # Create a steering call, as you would on the REST-API.
        # The syntax of this payload depends entirely on the strategy implementation.
        payload = {"manual_order": {"operation": "create",
                                    "broker_id": "20",
                                    "product_id": "10000302_2",
                                    "quantity": 30,
                                    "buy": True,
                                    "price": 15.6,
                                    "delivery_area": "10002806"}}
        # Using the create_steering_call helper function,
        # we wrap our payload in an envelope understood by the simulator
        # time is in UTC -> 16 CET/CEST
        steering_msg = SBU.create_steering_call("test_manual_strategy", payload, datetime.datetime(2020, 9, 6, 14))

        # All strategy definitions and steering calls are passed into the simulator as a list.
        # The order is not important, as the list will be sorted by timestamps.
        # You can add as many steering calls to the list as you like
        strategy_messages.append(steering_msg)

        simulator = SIM.Simulator(strategy_messages,
                                  feed_paths=[trayport_exchange_feed],
                                  simulated_exchanges=(COMMON.Exchange.trayport, ),
                                  use_persistence=False,  # set this to True to use MongoDB
                                  )
        simulator.run(write_logfiles=True)  # Set write_logfiles to True to write logfiles (in the current directory)

        # 4. Investigate the result of the simulation
        # After the simulation, you have direct access to the exchange object which you can use to validate the
        # simulation results. WARNING: If you don't store the results, the data is garbage collected by python.

        # Assert that the steering call lead to a trade.
        own_trades = simulator.autotrader.trayport.products.get_by_id("10000302_2").trades.get(
            trade_filter=COMMON.TradeFilter.own)
        self.assertEqual(len(own_trades), 1)
        self.assertEqual(own_trades[0].quantity, 30)
        self.assertLessEqual(own_trades[0].price, 15.6)
        print("A trade with trade_id {} was created in this simulation".format(own_trades[0].trade_id))

        # 4.1 Additionally, you can write some of the test results to the compliance log file. See the example below:
        # (works only if `write_logfiles` is set to `True` when running simulation)
        # Currently, two message types are available:
        # - INFO messages. One is to use LOGTEMP.BacktestingLogs.info_message template here
        # - ERROR messages. One is to use LOGTEMP.BacktestingLogs.error_message template here
        # The only mandatory keyword argument for these message types is "message",
        # so it has to be passed to the compliance_log method.
        # Other keyword arguments will appear in the compliance logs as additional field of an json log entry.

        simulator.compliance_log(LOGTEMP.BacktestingLogs.info_message,
                                 message="Strategy created own trades: {}".format(own_trades),
                                 own_trades=str(own_trades))

        simulator.compliance_log(LOGTEMP.BacktestingLogs.error_message,
                                 message="[Not a real error] Strategy created only these trades: {}".format(own_trades),
                                 own_trades=str(own_trades))


class TestWithMongo(unittest.TestCase):
    def setUp(self):
        print("Starting example test with MongoDB")
        super(TestWithMongo, self).setUp()

    def test(self):
        trayport_exchange_feed = path("TrayportFeed_1000302_SHORT.zip")

        strategy = SD.StrategyDefinition(
            strategy_id="test_gas_strategy",
            valid_from=datetime.datetime(2020, 9, 6, 4, 0, 0),
            valid_until=datetime.datetime(2020, 9, 8, 4, 0, 0),
            package_path=os.path.join(ROOT_PATH, "own_strategies", "gas_strategy_storage"),
            set_default_limits=True,
            user_ts=["strategy_storage_cutoff_purchase", "strategy_storage_cutoff_sell"],
            exchange_1=COMMON.Exchange.trayport,
            market_area_1="10002806",
            active=True
        )
        strategy.fill("price_purchase_immediate_vesting", 8.0)
        strategy.fill("price_purchase", 8.25)
        strategy.fill("strategy_storage_cutoff_purchase", 8.45)  # user-defined tiemseries, defined above.
        strategy.fill("strategy_storage_cutoff_sell", 9.55)  # user-defined tiemseries, defined above.
        strategy.fill("price_sales", 9.75)
        strategy.fill("price_sales_immediate_vesting", 10.0)
        strategy.fill("position_tradable_position_long", 20)

        # When using mongoDB, the following environment variables are used:
        # AUTOTRADER_PERSISTENCE_HOST, AUTOTRADER_PERSISTENCE_PORT (defaults: localhost and the standard MongoDB port)
        # AUTOTRADER_PERSISTENCE_USERNAME, AUTOTRADER_PERSISTENCE_PASSWORD (When authentication is required for MongoDB)
        simulator = SIM.Simulator([strategy.export(datetime.datetime(2020, 9, 6, 4, 0, 0))],
                                  feed_paths=[trayport_exchange_feed],
                                  simulated_exchanges=(COMMON.Exchange.trayport, ),
                                  use_persistence=True,
                                  # database_name is the name of the database to create in MongoDB.
                                  # Default: "autoTRADER_backtest_" + the current time
                                  database_name="MyDatabaseName",
                                  overwrite_database=True
                                  )
        simulator.run(write_logfiles=True)
        # If we run the simulation with persistence, we can use some
        # convenient functions for retrieving the resulting data.

        # you can use the following functions to export the simulated data to csv files:
        simulator.export_market_data("PublicTrade")
        simulator.export_market_data("OwnTrade")

        simulator.export_own_trades()
        simulator.export_public_trades()

        # 4.1 Additionally, you can write some of the test results to the compliance log file. See the example below:
        # (works only if `write_logfiles` is set to `True` when running simulation)
        # Currently, two message types are available:
        # - INFO messages. One is to use LOGTEMP.BacktestingLogs.info_message template here
        # - ERROR messages. One is to use LOGTEMP.BacktestingLogs.error_message template here
        # The only mandatory keyword argument for these message types is "message",
        # so it has to be passed to the compliance_log method.
        # Other keyword arguments will appear in the compliance logs as additional field of an json log entry.

        simulator.compliance_log(LOGTEMP.BacktestingLogs.info_message,
                                 message="In this simulation we used persistence")

        simulator.compliance_log(LOGTEMP.BacktestingLogs.error_message,
                                 message="[Not a real error] In this simulation we used persistence")


if __name__ == '__main__':
    unittest.main()
