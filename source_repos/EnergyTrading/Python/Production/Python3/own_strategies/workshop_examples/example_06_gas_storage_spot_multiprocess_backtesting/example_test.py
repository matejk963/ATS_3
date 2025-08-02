
import datetime
import json
import os.path
import unittest
import uuid

import backtesting.multiprocessed_backtesting_base as BACKTESTBASE

import backtesting.strategy_definition as SD

import autotrader_lib.common as COMMON

import autotrader_lib.compliance_log_templates as LOGTEMP


def path(asset_filename):
    return os.path.join(os.path.dirname(__file__), "..", "assets", asset_filename)


class TrayportSimulationExampleTest(BACKTESTBASE.MultiprocessingBacktestingTest):
    """
    We recommend using the python unittest framework to start your multiprocessed backtesting simulations.
    This is done by inheriting from autotrader_core.i9ntests.backtesting_tests.base.MultiprocessingBacktestingTest

    All individual simulations have to be defined in methods of this class where the method name should
    start with "test_".

    The simulation can be configured by setting the variables described in the following - either on the class
    level or as attributes of the class instance inside the test methods (the python unittest framework is running
    each test in a separate instance of the class, so defining them as attributes can not have negative impacts on
    other tests.)

    The exchange feed file in jsonl format containing the orderbook and trade updates from the real exchange is
    configured using the variables:

    *trayport_exchange_feed*, *epex_exchange_feed* and *nordpool_exchange_feed*.
    At least one of the 3 variables must be set to run a simulation.

    *trayport_initfile_dir*
    For the initialization of Trayport, the definition of products and delivery areas (instrument definitions,
    instrument properties and sequence items) is not part of the exchange-feed file, but stored in separate files.
    For testing with Gas Prompt Products (sequence 10000302, broker 20,e.g. Within Day, Day Ahead,...), this value
    can probably remain unset, as the default assets shipped with autoTRADER should be valid independent of the
    simulation date.
    For testing other things, this variable gives you the ability to overwrite the default autoTRADER product and area
    definitions. This variable should be a absolute path pointing to a directory which contains some or all of the
    following files: inst_definitions.json, inst_properties.jsonl, sequence_items.json,
    term_format.json and user_info.json
    If this is set to a non-existing path, you will only see a warning inside the autotrader parent log.

    *out_path*
    Can be set to a directory, where autoTRADER should create its log files and export data to.
    It has to be an absolute path.
    If it is not set, a unique directory is created under the operating system's temporary directory.
    In any case, the value of this variable will be printed at the start of the simulation.

    *overwrite_database*
    Each test creates a database named with the name of the class and the test in your mongodb.
    This should not be more than 50 characters long.
    If that database already exists, the simulation will not start, unless *overwrite_database* is set to True,
    in which case the old data will be discarded. (default:false)

    *mongodb_username* and *mongodb_password*
    Have to be set to the values of your mongodb. You have to enable authentication when you set up your MongoDB,
    as autotrader will refuse to connect to a database without authentication. The authentication database currently
    has to be the admin database.
    Note that the default -insecure- password defined in the super class is not used in production.

    *num_child_processes*
    If you set this to a value higher than one, you will get multiple child processes where different strategies
    can run on different processes.
    Note that each process has to hold the full order-book in memory, so increasing the number of processes will also
    linearly increase the RAM usage. (default:1)

    *exporting market data after backtesting*
    To export data after backtesting to a csv file you can use the method export_market_data
    from the base class MultiprocessingBacktestingTest. See the sample using in the test method.
    Available parameters:
    - exchange_id: exchange ID. Should be one of "EPEX", "NORD" or "TRAYPORT"
    - trade_type: trade type, e.g. OwnTrade, PublicTrade etc
    - group_by_product_id: flag telling whether results should be grouped by product_id.
                           This is mostly used to separate local and XBID products on EPEX.
                           When False grouping by time period will be used.
                           Exclusive to time period: delivery_start and delivery_end
    - delivery_start: start of delivery. Exclusive to group_by_product_id
    - delivery_end: end of delivery. Exclusive to group_by_product_id
    - filename: name of the file to export to
    - delimiter: csv field delimiter. Default value is ",".
                 Possible values are a comma (,), a semicolon (;), a tab (\t), a space ( ) and a pipe (|)
    - decimal_delimiter: decimal delimiter for float numbers. Default value is ".". Possible values are in . and ,

    Run this file (in the root directory of autotrader_public) using
    `python -m own_strategies.workshop_examples.example_06_gas_storage_spot_multiprocess_backtesting.example_test`
    """

    # The example feed only contains data collected during ~1 hour, to make the example faster.
    trayport_exchange_feed = path("TrayportFeed_1000302_SHORT.jsonl")

    overwrite_database = True

    def test(self):
        # Transfer the strategy first, so it already exists when AT is started
        # In the strategy definition, the parameters of the strategy are configured. (=parameter configuration)
        strategy = SD.StrategyDefinition(
            strategy_id="test_gas_strategy",
            # valid_from and valid_to defines, how many values each timeseries holds. In UTC
            valid_from=datetime.datetime(2020, 9, 6, 4, 0, 0),
            valid_until=datetime.datetime(2020, 9, 7, 4, 0, 0),
            # User-defined timeseries used by the algorithm. They have to start with "strategy_"
            user_ts=["strategy_storage_cutoff_purchase", "strategy_storage_cutoff_sell"],
            # The path to the strategy folder.
            # This folder should contain at least the files __init__.py and custom_strategy.py
            package_path=os.path.join(self.root_path, "own_strategies", "gas_strategy_storage"),
            set_default_limits=True,  # Set very wide limits that will never get triggered.
            packagename=str(uuid.uuid4()),  # Use a uuid, so code-changes immediately take effect on subsequent runs.
            exchange_1=COMMON.Exchange.trayport,
            market_area_1=COMMON.Area.ttf,
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

        # Now transfer the strategy to autoTRADER.
        self.transfer_strategy(strategy)

        # Then start AT
        self.start_autotrader()
        self.wait_for_autotrader_initialization()

        # Wait 15 minutes in simulation time (30 seconds real time)
        # This helper function also checks if autoTRADER is alive, so we exit early on an error.
        self.sleep_for_seconds(COMMON.QUARTER, raise_on_autotrader_exit=True)

        # Now, we transfer an update to the strategy timeseries.
        print("\n15 minutes (simulation time) have passed. Now we transfer an update")
        strategy.fill("position_tradable_position_long",
                      [5, 5, 5, 5, 4, 4, 4, 4, 6, 6, 6, 6, 5, 5, 5, 5, 4, 4, 4, 4, 6, 6, 6, 6])

        self.transfer_strategy(strategy)

        # Now we wait, until the simulation is complete and autoTRADER exits
        # To be on the safe side, we set a timeout that is higher than the expected runtime of autoTRADER.
        # (The simulation test takes about 2 Minutes to run, therefore we wait for double the amount)
        self.wait_for_process_termination(timeout=COMMON.MINUTE * 4)

        # The first check should always be to ensure autoTRADER did not get halted by a strategy error.
        autotrader = self.get_autotrader_json()
        self.assertFalse(autotrader["halted"])

        # Now, just check that there are own and public orders in the database.
        # Here, you could do different assertions or analysis of the strategy performance.
        own_orders = self.get_own_orders_json()
        pub_orders = self.get_public_orders_json()
        own_trades = self.get_own_trades_json()
        pub_trades = self.get_public_trades_json()
        self.assertTrue(pub_orders)
        self.assertTrue(own_orders)
        self.assertTrue(own_trades)
        self.assertTrue(pub_trades)

        # Here, we can export market data to a csv file. Uncomment the function call to use export
        # self.export_market_data(exchange_id="TRAYPORT", trade_type="OwnTrade", group_by_product_id=False,
        #                         filename="backtesting_market_data.csv", delimiter=",", decimal_delimiter=".")

        # Additionally, we can export all simulated own trades to a csv file.
        # If the filename is not given, a new file self.out_path will be created.
        # WARNING Problems with Microsoft Excel 2019: When opening the CSV with Microsoft Excel, the last digits of
        #         the trade ids can get wrongly rounded down to 0, when excel thinks the column should be imported
        #         as numbers. To import everything as text without rounding, open an empty excel document and
        #         click "Data" -> "From Text/CSV", select the csv file and press import. In the popup window,
        #         select "Do not detect data types" in the "Data Type Detection" dropdown before importing the data.
        #         Then everything will be imported as text and you have to manually convert the price and quantity
        #         from text to numbers using "Data" -> "Text to columns"
        self.export_own_trades(exchange_id="TRAYPORT", filename=None)

        # some additional tests for the compliance logging from within the backtesting
        self.assertTrue(os.path.isfile(self.get_compliance_log_filename()))
        with open(self._log_filename, "r") as fp:
            lines = fp.readlines()
        json_lines = [json.loads(line) for line in lines[-2:]]

        # find start msg line:
        self.assertEqual(json_lines[0]["log_code"], LOGTEMP.BacktestingLogs.testing_started[0])
        self.assertIn("strat_hashes", json_lines[0])
        self.assertEqual(json_lines[1]["log_code"], LOGTEMP.BacktestingLogs.testing_finished[0])
        self.assertIn("strat_hashes", json_lines[1])


if __name__ == '__main__':
    print("WARNING - Multiprocess Backtesting currently not supported for windows machines!")
    unittest.main()
