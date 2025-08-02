from __future__ import absolute_import
from __future__ import print_function
import datetime
import errno
import os.path
import json
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
import zipfile

import pymongo
import six

if six.PY2:
    import autotrader_lib.fast_logging_py2 as FLOG
else:
    import autotrader_lib.fast_logging_py3 as FLOG
from six.moves import range

# make fast_logger the real logger. This line does not work anywhere else! It has to come before autotrader imports
FLOG.make_standard_logging_module()

import autotrader_lib.compliance_log_templates as LOGTEMP
import autotrader_lib.util as ALU
import autotrader_lib.mongo_data_export as MDE
import autotrader_lib._strategy_managing as SM
import autotrader_lib.common as COMMON
import backtesting.transfer_strategy_definition as TRANSD
from backtesting import DEFAULT_TRADE_EXPORT_COLUMNS
import backtesting.strategy_definition as SD

try:
    import i9ntests.util as I9NUTIL
except ImportError:
    I9NUTIL = None

LOGGER = FLOG.getLogger("autotrader")

CONFIG_TEMPLATE = textwrap.dedent("""
        [autotrader_mongo]
        host = {mongodb_host}
        port = {mongodb_port}
        username = {mongodb_username}
        password = {mongodb_password}
        database = {database_name}

        [autotrader_epex-manager]
        exchangefeed_file = {epex_exchange_feed}

        [autotrader_nordpool-manager]
        exchangefeed_file = {nordpool_exchange_feed}

        [autotrader_trayport-manager]
        exchangefeed_file = {trayport_exchange_feed}
        tp_initfile_directory = {tp_initfile_dir}

        [autotrader]
        console = False
        host = 0.0.0.0
        submission_port = {0}
        status_port = {1}
        logs_port = {2}
        periotheus_submission_port = {3}
        use_persistence = True
        epex = {epex}
        nordpool = {nordpool}
        trayport = {trayport}
        num_child_processes = {num_child_processes}
        parent_to_child_sub_port = {4}
        parent_to_child_pub_port = {5}
        playback_speed = {playback_speed}
        backtesting = True
        write_public_orders_to_db = {write_public_orders_to_db}""")


class MultiprocessingBacktestingTest(unittest.TestCase, FLOG.BacktestingComplianceLoggerMixin):
    """
    Base class for running autoTRADER in backtesting mode as a background process.

    This class is used to spawn an autoTRADER in multiprocessing mode as a background process
    and to communicate with in via mongoDB.

    Customers can subclass from this class to write their own backtesting scenarios.

    See also the example_test for a more detailled description.
    """
    root_path = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
    out_path = None
    playback_speed = 30
    overwrite_database = False

    # The default username and password are for running on a local machine,
    # where an insecure password is fine.
    mongodb_username = "vt"
    mongodb_password = "vt"
    num_child_processes = 1
    epex_exchange_feed = ""
    nordpool_exchange_feed = ""
    trayport_exchange_feed = ""
    trayport_initfile_dir = ""

    _strategies = []

    def setUp(self):
        self.name = "{}_{}".format(self.__class__.__name__, self._testMethodName)
        self.setup_persistence()
        self.main_process = None
        self.temp_cfg = None
        if self.out_path is None:
            self.out_path = tempfile.mkdtemp(prefix="aT-backtesting-results-")
        print(("Log files and exported data will go to: {}".format(self.out_path)))

    def tearDown(self):
        if I9NUTIL is not None:
            I9NUTIL.dump_mongo(LOGGER, self.database, self._testMethodName)

        if self.temp_cfg is not None:
            self.temp_cfg.close()
        if self.main_process is not None:
            try:
                LOGGER.debug("Tear Down: Shutting down autoTRADER process")
                os.kill(self.main_process.pid, signal.SIGTERM)
            except OSError as err:
                if err.errno != errno.ESRCH:  # No such process, i.e. it has already terminated
                    raise

    def start_autotrader(self):
        """
        Start autoTRADER as a background process running based on the simulation file.
        """
        if not os.path.exists(os.path.join(self.out_path, "var", "log", "autotrader")):
            os.makedirs(os.path.join(self.out_path, "var", "log", "autotrader"))

        self.init_logs(LOGGER,
                       filename=os.path.join(self.out_path, "var", "log", "autotrader", "autotrader_backtesting.log"))

        for feed_path in [self.epex_exchange_feed, self.nordpool_exchange_feed, self.trayport_exchange_feed]:
            if not feed_path:
                # skip loading if the feedpath is not set
                continue

            # if feedpath is set, check if it is a valid file
            # usually a feedpath is a json or jsonl file
            # if it is not present, check if there is a zip file with the same basename and try to extract
            if not os.path.isfile(feed_path):
                zipname = os.path.splitext(feed_path)[0] + ".zip"
                if os.path.isfile(zipname):
                    self._extract_zip(zipname)

            # if the feedfile is still not available after attempt to extract it from a zip, then fail
            if not os.path.isfile(feed_path):
                raise ValueError("The exchange feed could not be found at: {}".format(feed_path))

        if not isinstance(self.num_child_processes, int) or self.num_child_processes < 1:
            raise ValueError("Invalid number of child processes specified.")
        free_ports = ALU.get_free_ports(6)
        config = CONFIG_TEMPLATE.format(*free_ports,
                                        mongodb_username=self.mongodb_username,
                                        mongodb_password=self.mongodb_password,
                                        mongodb_host=self.database_host,
                                        mongodb_port=self.database_port,
                                        database_name=self.database_name,
                                        epex_exchange_feed=self.epex_exchange_feed,
                                        nordpool_exchange_feed=self.nordpool_exchange_feed,
                                        trayport_exchange_feed=self.trayport_exchange_feed,
                                        epex="True" if self.epex_exchange_feed else "False",
                                        nordpool="True" if self.nordpool_exchange_feed else "False",
                                        trayport="True" if self.trayport_exchange_feed else "False",
                                        num_child_processes=self.num_child_processes,
                                        playback_speed=self.playback_speed,
                                        tp_initfile_dir=self.trayport_initfile_dir,
                                        write_public_orders_to_db="true")
        self.temp_cfg = tempfile.NamedTemporaryFile(prefix="aT-backtesting-cfg-")
        self.temp_cfg.write(config.encode())
        self.temp_cfg.flush()

        path = os.path.join(self.root_path, "autotrader_core", "bin", "autotrader_core_main.py")
        exec_args = [sys.executable, path, "-c", self.temp_cfg.name, "--nbroot", self.out_path]
        action_limit_file = os.path.join(self.out_path, "etc", "autotrader", COMMON.ActionLimits.filename)
        broker_config_file = os.path.join(self.out_path, "etc", "autotrader", COMMON.BrokerSpecs.filename)
        if self.trayport_exchange_feed and not os.path.isfile(action_limit_file):
            if not os.path.exists(os.path.join(self.out_path, "etc", "autotrader")):
                os.makedirs(os.path.join(self.out_path, "etc", "autotrader"))
            with open(action_limit_file, "w") as json_file:
                action_limits_dict = {
                    COMMON.Exchange.trayport: {
                        COMMON.Broker.eex: {u"action_rate_interval": 30, u"action_rate_limit": 200},
                        COMMON.Broker.eexs: {u"action_rate_interval": 5, u"action_rate_limit": 100}
                    },
                    COMMON.ActionLimits.version: u"backtesting_default"
                }
                json.dump(action_limits_dict, json_file)

        if self.trayport_exchange_feed and not os.path.isfile(broker_config_file):
            if not os.path.exists(os.path.join(self.out_path, "etc", "autotrader")):
                os.makedirs(os.path.join(self.out_path, "etc", "autotrader"))
            with open(broker_config_file, "w") as json_file:
                broker_config_dict = {
                    COMMON.Exchange.trayport:
                        dict.fromkeys([
                            COMMON.Broker.eex, COMMON.Broker.ice, COMMON.Broker.eex_t7_uat, COMMON.Broker.eex_t7_prod
                        ], {COMMON.BrokerSpecs.does_combine_public_orders: True}),
                    COMMON.BrokerSpecs.version: u"backtesting_default"
                }
                json.dump(broker_config_dict, json_file)

        print(("Starting autoTRADER: {}".format(" ".join(exec_args))))
        self.compliance_log(LOGTEMP.BacktestingLogs.testing_started, strat_hashes=self.strategy_hash_str)

        self.main_process = subprocess.Popen(exec_args)

    def _extract_zip(self, zipname):
        """
        If the feed path does not exist, but a zip file with the same name exists, extract it.

        :param zipname: Path to the zipfile to extract.
        :type zipname: str
        """
        if os.path.isfile(zipname):
            print(("Extracting {}".format(zipname)))
            directory = os.path.split(zipname)[0]
            with zipfile.ZipFile(zipname, 'r') as zip_ref:
                zip_ref.extractall(directory)

    def setup_persistence(self):
        """
        Set up the parameters of the MongoDB and open the corresponding connection
        """
        self.database_host = os.environ.get("AUTOTRADER_PERSISTENCE_HOST", "localhost")
        self.database_port = int(os.environ.get("AUTOTRADER_PERSISTENCE_PORT", 27017))
        self.database_name = "backtesting_{}".format(self.name)
        self.auth_source = os.environ.get("AUTOTRADER_AUTH_SOURCE", "autoTRADER")
        if len(self.database_name) > 63:
            raise ValueError("The name of the test is too long. "
                             "The class and test name together should be at most 51 characters, "
                             "but {} is {} characters long".format(self.name, len(self.name)))
        self.mongo_client = pymongo.MongoClient(self.database_host, self.database_port,
                                                username=self.mongodb_username,
                                                password=self.mongodb_password,
                                                authSource=self.auth_source)
        if self.database_name in self.mongo_client.list_database_names():
            if self.overwrite_database:
                self.mongo_client.drop_database(self.database_name)
            else:
                raise RuntimeError("The database {} already exists. If you want to overwrite the existing database"
                                   " on test start, set the class-level variable "
                                   "`overwrite_database` to True.".format(self.database_name))
        self.database = self.mongo_client.get_database(self.database_name)

    def has_autotrader_parent_terminated(self):
        """
        Checks if the autoTRADER background process has already finished to run.
        :return: True if autoTRADER has terminated.
        :rtype: bool
        """
        if self.main_process is None:
            raise RuntimeError("Cannot wait for termination of the autoTRADER process before"
                               " it is started (with self.start_autotrader)")
        self.main_process.poll()
        if self.main_process.returncode is not None:
            return True
        return False

    def wait_for_process_termination(self, timeout):
        """
        Wait until the autoTRADER background process has terminated (i.e. the simulation has finished).

        If the timeout is reached, an assertion error is raised, which (if unhandled) will cause the test to fail
        and tearDown to be called, where the autoTRADER process is then killed.

        :param timeout: The maximal waiting time in seconds.
                        This should usually be more than the expected run-time
        :type timeout: float
        """
        try:
            ALU.wait_for_it(timeout)(self.has_autotrader_parent_terminated)()
            self.compliance_log(LOGTEMP.BacktestingLogs.testing_finished, strat_hashes=self.strategy_hash_str)
        except Exception as e:
            self.compliance_log(LOGTEMP.BacktestingLogs.error_message,
                                message="Simulation did not finish in time: {}".format(six.text_type(e)))
            raise

    def get_autotrader_json(self):
        """
        Get autoTRADER status information from the database.

        :return: A dict with object_type: AutoTrader
        :rtype: dict
        """
        try:
            return next(self.database.state.find({"object_type": "AutoTrader"}))
        except StopIteration:
            return {}

    def _get_autotrader_child_jsons(self):
        """
        Get autoTRADER status information for child 0 from the database.

        :return: A dict with object_type: AutoTraderChild
        :rtype: dict
        """
        try:
            return self.database.state.find({"object_type": "AutoTraderChild"})
        except StopIteration:
            return {}

    def get_own_orders_json(self):
        """
        Get own orders from the database.

        :return: A list of dicts with object_type: OwnOrder
        :rtype: dict
        """
        return list(self.database.state.find({"object_type": "OwnOrder"}))

    def get_public_orders_json(self):
        """
        Get public orders from the database.

        :return: A list of dicts with object_type: PublicOrder
        :rtype: list(dict)
        """
        return list(self.database.state.find({"object_type": "PublicOrder"}))

    def get_own_trades_json(self):
        """
        Get own trades from the database.

        :return: A list of dicts with object_type: OwnTrade
        :rtype: list(dict)
        """
        return list(self.database.state.find({"object_type": "OwnTrade"}))

    def get_public_trades_json(self):
        """
        Get public trades from the database.

        :return: A list of dicts with object_type: PublicTrade
        :rtype: list(dict)
        """

        return list(self.database.state.find({"object_type": "PublicTrade"}))

    @ALU.wait_for_it(timeout=30)
    def wait_for_own_order(self, slot_type, quantity=None, price=None):
        query = {"object_type": "OwnOrder", "slot_type": slot_type}
        if quantity is None:
            query["quantity"] = {"$gt": 0}
        else:
            query["quantity"] = quantity
        if price is not None:
            query["price"] = price
        result = list(self.database.state.find(query))
        return result

    @ALU.wait_for_it(timeout=30)
    def wait_for_autotrader_initialization(self):
        at_object = self.get_autotrader_json()
        at_child_objects = self._get_autotrader_child_jsons()
        return (at_object and at_object["initialized"] and at_child_objects
                and all(child["initialized"] for child in at_child_objects))

    def sleep_for_seconds(self, seconds_simulation_time, raise_on_autotrader_exit):
        """
        Sleep for a given number of seconds simulation time.

        Checks if autoTRADER is alive during this time.
        Has only roughly 30sec (simulation time) accuracy.

        :param seconds_simulation_time: The seconds simulation time to sleep
        :type seconds_simulation_time: int
        :param raise_on_autotrader_exit: Defines what happens if the autoTRADER background process exits during
                                         the waiting time.
                                         If True, it raises a RuntimeError, otherwise it just prints
                                         a message and stops waiting.
        :type raise_on_autotrader_exit: bool
        """
        deciseconds_real_time = int(seconds_simulation_time / float(self.playback_speed) * 10)
        for unused_i in range(deciseconds_real_time):
            if self.has_autotrader_parent_terminated():
                if raise_on_autotrader_exit:
                    raise RuntimeError("autoTRADER has unexpectedly terminated.")
                else:
                    print("Stopping to wait, because autoTRADER has terminted.")
                    return
            time.sleep(0.1)

    def _get_strat_hashes(self):
        hashes = []
        for strategy in self._strategies:
            hashes.append(SD.StrategyDefinition.strat_identifier_from_params(strategy.params))
        if not hashes:
            raise RuntimeError("No strategy hash found!")
        self.strategy_hash_str = ", ".join(hashes)

    def transfer_strategy(self, strategy):
        """
        Transfer the strategy parameters and timeseries to autoTRADER, mimicking a periotheus strategy transfer.
        :param strategy: The strategy definition object, holding the parameters, timeseries
                         and the path to the strategy source code.
        :type strategy: backtesting.strategy_definition.StrategyDefinition
        """

        self._strategies.append(strategy)

        strategy_msg = strategy.export()
        database_host = os.environ.get("AUTOTRADER_PERSISTENCE_HOST", "localhost")
        database_port = int(os.environ.get("AUTOTRADER_PERSISTENCE_PORT", 27017))
        auth_source = os.environ.get("AUTOTRADER_AUTH_SOURCE", "autoTRADER")
        TRANSD.transfer(strategy_msg, host=database_host, port=database_port, username=self.mongodb_username,
                        password=self.mongodb_password,
                        database_name=self.database_name, num_child_processes=self.num_child_processes,
                        auth_source=auth_source)

    def export_market_data(self, exchange_id, trade_type, group_by_product_id,
                           delivery_start=None, delivery_end=None,
                           filename=None, delimiter=",", decimal_delimiter="."):
        """
        Helper function to export market data.

        :exchange_id: exchange ID
        :type exchange_id: str
        :param trade_type: trade type, e.g. OwnTrade, PublicTrade etc
        :type trade_type: str
        :param group_by_product_id: flag telling whether results should be grouped by product_id.
                                    This is mostly used to separate local and XBID products on EPEX.
                                    When False grouping by time period will be used.
                                    Exclusive to time period: delivery_start and delivery_end
        :type group_by_product_id: bool
        :param delivery_start: start of delivery. Exclusive to group_by_product_id
        :type delivery_start: date string
        :param delivery_end: end of delivery. Exclusive to group_by_product_id
        :type delivery_end: date string
        :param filename: name of the file to export to. If not specified the following name will be used
                         "{out_path}/market_data_{utc_timestamp}.csv".
        :type filename: str
        :param delimiter: csv field delimiter. Default value is ",".
                          Possible values are a comma (,), a semicolon (;), a tab (\t), a space ( ) and a pipe (|)
        :type delimiter: str
        :param decimal_delimiter: decimal delimiter for float numbers. Default value is ".".
        :type decimal_delimiter: str
        """

        if not filename:
            filename = "{}/market_data_{}.csv".format(self.out_path, time.time())

        MDE.export_market_data(database=self.database, exchange_id=exchange_id, trade_type=trade_type,
                               group_by_product_id=group_by_product_id,
                               delivery_start=delivery_start, delivery_end=delivery_end,
                               filename=filename, delimiter=delimiter, decimal_delimiter=decimal_delimiter)

    def export_own_trades(self, exchange_id, area_id=None, product_ids=None,
                          execution_until=None, execution_after=datetime.datetime.min, internal=None,
                          filename=None, delimiter=",", decimal_delimiter="."):
        """
        Query trades and export them to a csv file.
        :param exchange_id: exchange ID. One of "TRAYPORT", "EPEX" or "NORD"
        :type exchange_id: str
        :param area_id: delivery area ID. If given, the return result will contain only records with this ID.
                        For Trayport, this is the instrument id, e.g. "10002806" for TTF Hi Cal
                        For EPEX and Nordpool, this is the EIC code, e.g. "10YAT-APG------L" for APG (Austria)
        :type area_id: str
        :param product_ids: list of product IDs. If given, the return result will contain only records
                            from these products
        :type product_ids: list[str]
        :param execution_until: filter trades that are executed until the given datetime.
                                Can be used only with execution_after
        :type execution_until: datetime.datetime
        :param execution_after: filter trades that are executed after the given datetime.
                                If not given, all trades are returned (which is different to the REST-API,
                                where only trades from the last 3 days are returned)
        :type execution_after: datetime.datetime
        :param internal: When given, limit trades to internal trades (if True) or exchange trades (if False).
        :type internal: bool or None
        :param filename: Absolute path of the file to export to. If not given, the csv will be exported to a new file
                         in the temporary directory given by self.out_path
        :type filename: str or None
        :param delimiter: csv field delimiter. Default value is ",". Possible values are in DELIMITERS
        :type delimiter: str
        :param decimal_delimiter: decimal delimiter for float numbers. Default value is ".".
                                  Possible values are in DECIMAL_DELIMITERS
        :type decimal_delimiter: str
        """
        if not filename:
            filename = "{}/own_trades_{}.csv".format(self.out_path, time.time())
        MDE.export_trades(self.database, exchange_id, "OwnTrade", area_id=area_id, product_ids=product_ids,
                          execution_until=execution_until, execution_after=execution_after, internal=internal,
                          filename=filename, delimiter=delimiter, decimal_delimiter=decimal_delimiter,
                          columns=DEFAULT_TRADE_EXPORT_COLUMNS + ["internal"])

    def export_public_trades(self, exchange_id, area_id=None, product_ids=None,
                             execution_until=None, execution_after=datetime.datetime.min,
                             filename=None, delimiter=",", decimal_delimiter="."):
        """
        Query trades and export them to a csv file.
        :param exchange_id: exchange ID. One of "TRAYPORT", "EPEX" or "NORD"
        :type exchange_id: str
        :param area_id: delivery area ID. If given, the return result will contain only records with this ID.
                        For Trayport, this is the instrument id, e.g. "10002806" for TTF Hi Cal
                        For EPEX and Nordpool, this is the EIC code, e.g. "10YAT-APG------L" for APG (Austria)
        :type area_id: str
        :param product_ids: list of product IDs. If given, the return result will contain only records
                            from these products
        :type product_ids: list[str]
        :param execution_until: filter trades that are executed until the given datetime.
                                Can be used only with execution_after
        :type execution_until: datetime.datetime
        :param execution_after: filter trades that are executed after the given datetime.
                                If not given, all trades are returned.
        :type execution_after: datetime.datetime
        :param filename: Absolute path of the file to export to. If not given, the csv will be exported to a new file
                         in the temporary directory given by self.out_path
        :type filename: str
        :param delimiter: csv field delimiter. Default value is ",". Possible values are in DELIMITERS
        :type delimiter: str
        :param decimal_delimiter: decimal delimiter for float numbers. Default value is ".".
                                  Possible values are in DECIMAL_DELIMITERS
        :type decimal_delimiter: str
        """
        if not filename:
            filename = "{}/public_trades_{}.csv".format(self.out_path, time.time())
        MDE.export_trades(self.database, exchange_id, "PublicTrade", area_id=area_id, product_ids=product_ids,
                          execution_until=execution_until, execution_after=execution_after,
                          filename=filename, delimiter=delimiter, decimal_delimiter=decimal_delimiter,
                          columns=DEFAULT_TRADE_EXPORT_COLUMNS)

    def strategy_steering(self, strategy_id, payload):
        """
        Helper function to steer a strategy.

        :param strategy_id: ID of a strategy to steer
        :type strategy_id: str
        :param payload: strategy payload
        :type payload: dict[str, any]
        :return: The found mongo entry's result field
        :rtype: dict[str, str]
        """

        return SM.strategy_steering(self.database, strategy_id=strategy_id, payload=payload)
