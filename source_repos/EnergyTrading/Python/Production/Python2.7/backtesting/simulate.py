from __future__ import print_function

import base64
import collections
import copy
import datetime
import functools
import gzip
import json
import mock
import os
import time
import zipfile

import numpy as np

import autotrader_lib.fast_logging as FLOG

# make fast_logger the real logger. This line does not work anywhere else! It has to come before autotrader imports
FLOG.make_standard_logging_module()

import autotrader_core.api
import autotrader_core.common as COMMON
import autotrader_core.compliance_log_templates as LOGTEMP
import autotrader_core.exchange_trading as APITR
import autotrader_core.exchanges as APIEXCH
import autotrader_core.persistence as PERSIST
import autotrader_core.i9ntests.simulation_definition_reader
import autotrader_core.i9ntests.util as I9NUTIL
import autotrader_core.utils
import autotrader_core.exchange_simulator as EXCHSIM

import autotrader_lib.config_helper as ATCONF
import autotrader_lib.mongo_data_export as MDE
import autotrader_lib.cet_util as CETUTIL
import autotrader_lib.unit_util as UU
import autotrader_lib.util as ALU

from backtesting import DEFAULT_TRADE_EXPORT_COLUMNS
import backtesting.iterative_simulator as ITSIM
import backtesting.strategy_definition as SD

LOGGER = FLOG.getLogger("autotrader")

DATABASE_NAME = "autoTRADER_simulation_test"


def log_send_msg(exchange, *args, **kwargs):
    LOGGER.debug("Sent to %s: args: %s, kwargs: %s", exchange, args, kwargs)


def with_log(f):
    def inner(*args, **kwargs):
        LOGGER.debug("Called %s with %s, %s", f, args, kwargs)
        return f(*args, **kwargs)

    return inner


class SimulationError(Exception):
    """ This error is raised if there are any errors during the runtime of the simulation """


class Simulator(object, FLOG.BacktestingComplianceLoggerMixin):
    """Class to run backtesting of a provided `strategy_dict` using historical data as stored in the `feed_path`"""

    # Define the max actions per period limits
    action_limit_data = {
        COMMON.Exchange.trayport: {
            COMMON.Broker.eex: {u"action_rate_interval": 30, u"action_rate_limit": 200},
            COMMON.Broker.ice: {u"action_rate_interval": 5, u"action_rate_limit": 100}
        },
        COMMON.ActionLimits.version: u"backtesting_default"}

    broker_spec_data = {
        COMMON.Exchange.trayport:
            dict.fromkeys([
                COMMON.Broker.eex, COMMON.Broker.ice, COMMON.Broker.eex_t7_uat, COMMON.Broker.eex_t7_prod
            ], {COMMON.BrokerSpecs.does_combine_public_orders: True}),
        COMMON.BrokerSpecs.version: u"backtesting_default"
    }

    def __init__(
            self,
            event_messages,
            json_feed=None,
            feed_path=None,
            feed_paths=None,
            at_config=None,
            epex_config=None,
            trayport_config=None,
            nordpool_config=None,
            nasty_orders_generators=None,
            reraise_on_strategy_exception=True,
            simulated_exchanges=(COMMON.Exchange.epex,),
            callback_start=None,
            callback_timer=None,
            callback_finish=None,
            use_persistence=True,
            database_name=None,
            trayport_init_directory=None,
            overwrite_database=False,
            strategies_folder=None,
            timer_fast_timestep=10,
            timer_timestep=10,
            save_results=False,
            simulation_stop=None,
            short_omt_parameters=None,
            long_omt_parameters=None
    ):
        """

        :param event_messages: strategy messages with timestamp, data, exchange and message_type
        :type event_messages: list[dict]
        :param feed_paths: specifies the paths to files with historical data feed
        :type feed_paths: list[str]
        :param at_config: provides autotrader configuration
        :type at_config: class:`autotrader_lib.config_helper.ATConfig` or None
        :param epex_config: provides epex configuration
        :type epex_config: class:`autotrader_lib.config_helper.EpexConfig` or None
        :param trayport_config: provides trayport configuration
        :type trayport_config: class:`autotrader_lib.config_helper.TrayportConfig` or None
        :param nordpool_config: provides nordpool configuration
        :type nordpool_config: class:`autotrader_lib.config_helper.NordpoolConfig` or None
        :param nasty_orders_generators: list of function to generate orders
        :type nasty_orders_generators: list
        :param reraise_on_strategy_exception: If the autotrader should be stopped once strategy raised an exception
        :type reraise_on_strategy_exception: bool
        :param simulated_exchanges: allowed exchanges which could be simulated.
                                    NOTE: Trayport offers no support for simulations involving more than 1 exchange.
        :type simulated_exchanges: tuple[str]
        :param callback_start: callback executed before the backtesting starts
        :type callback_start: callable
        :param callback_timer: callback executed on timer. It gets 2 arguments, the autotrader_child instance and
                               the (simulation) timestamp
        :type callback_start: callable
        :param callback_finish: callback executed after the backtesting ends
        :type callback_start: callable
        :param use_persistence: flag indicating use of MongoDB, useful for debugging and visualization
        :type use_persistence: bool
        :param database_name: use custom database name instead of default
        :type database_name: str or None
        :param overwrite_database: If true, we overwrite the database in case it already exists,
                                   if false an error is raised.
        :type overwrite_database: bool
        :param timer_fast_timestep: fast timer calls for strategy to run high frequency callbacks
        :type timer_fast_timestep: float
        :param timer_timestep: fast calls for strategy to run low frequency callbacks
        :type timer_timestep: float
        :param save_results: save backtest results (strategy, own_trades, best orders ca. every minute) in final json
        :type save_results: bool
        :param simulation_stop: timestamp when the simulation is stopped at the latest
        :type simulation_stop: int
        :param short_omt_parameters: simulated omt limit parameters for the short observation window
        :type short_omt_parameters: ALU.OMTParameters
        :param long_omt_paramerets: simulated omt limit parameters for the long observation window
        :type long_omt_parameters: ALU.OMTParameters
        """
        self.simulation_stop = simulation_stop
        assert not (feed_path and feed_paths), "Please only use feed_path or feed_paths parameter, but not both"
        if feed_path:
            LOGGER.warning("DEPRECATION-WARNING: Argument `feed_path` is replaced by `feed_paths`. "
                           "`feed_paths` can also accept a list of files, please use `feed_paths` in future."
                           "Example: `feed_paths=[my_file.zip]`")
        # keep feed_path parameter for backward compatibility
        if feed_path and not feed_paths:
            feed_paths = [feed_path]

        assert json_feed is not None or feed_paths is not None, (
            "Need a valid feed, either json_feed (list) or feed_path (list[str], paths to json/jsonl/zip-files)"
        )

        self.use_persistence = use_persistence
        self.save_results = save_results

        # select the strategies folder
        self.strategies_folder = strategies_folder

        if use_persistence:
            connector_params = dict(
                host=os.environ.get("AUTOTRADER_PERSISTENCE_HOST", "localhost"),
                port=os.environ.get("AUTOTRADER_PERSISTENCE_PORT", 27017),
                username=os.environ.get("AUTOTRADER_PERSISTENCE_USERNAME", None),
                password=os.environ.get("AUTOTRADER_PERSISTENCE_PASSWORD", None),
                write_concern=1,
                database_name="autoTRADER_backtest_{}".format(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")),
                expiry_interval=999999999,
                reset_counter=True)
            if database_name is not None:
                connector_params["database_name"] = database_name
            print("Using database {}".format(connector_params["database_name"]))
            PERSIST.MongoDBConnector._set_instance(PERSIST.MongoDBConnector, I9NUTIL.MockNonThreadedMongoDB())
            PERSIST.MongoDBConnector().initialize(**connector_params)
            if database_name in PERSIST.MongoDBConnector().client.list_database_names() and not overwrite_database:
                raise RuntimeError("The database {} already exists and "
                                   "overwrite_database is set to False".format(database_name))
            PERSIST.MongoDBConnector().db.state.drop()

            self.database = PERSIST.MongoDBConnector().db
        else:
            self.database = None
            try:
                if PERSIST.MongoDBConnector().db:
                    PERSIST.MongoDBConnector().db.state.drop()
                    LOGGER.info("Dropped GLOBAL state database")
            # having an exception in this case would mean we do not use mongo and we can do nothing
            except Exception:
                pass

        self.event_messages = sorted(event_messages, key=lambda m: m["timestamp"])

        # at least one of these sources has to be set
        self.json_feed = json_feed
        self.feed_paths = feed_paths

        self.epex_config = epex_config
        self.trayport_config = trayport_config
        self.nordpool_config = nordpool_config

        self.nasty_orders_generators = nasty_orders_generators
        self.reraise_on_strategy_exception = reraise_on_strategy_exception

        # set backtesting to true since we are in the simulator
        default_config = {
            "hwm_queu_lag": 10e10,
            "backtesting": True
        }

        if not simulated_exchanges:
            raise ValueError("Need to simulate at least 1 exchange")
        if COMMON.Exchange.epex in simulated_exchanges:
            default_config["epex"] = True
        if COMMON.Exchange.trayport in simulated_exchanges:
            default_config["trayport"] = True
        if COMMON.Exchange.nordpool in simulated_exchanges:
            default_config["nordpool"] = True

        if at_config:
            default_config.update(at_config)
        self.at_config = ATCONF.ATConfig(LOGGER).set_configs_from_dict(default_config)

        self.omt_simulator = EXCHSIM.OMTSimulator(short_omt_parameters, long_omt_parameters)

        auto_trader_parent, auto_trader_child = self.init_autotrader(self.at_config, epex_config, nordpool_config,
                                                                     trayport_config)
        self.autotrader = auto_trader_parent
        self.autotrader_child = auto_trader_child

        epex_exchange_simulator = ITSIM.IterativeSimulator(auto_trader_parent, COMMON.Exchange.epex,
                                                           ITSIM._convert_to_list(nasty_orders_generators),
                                                           omt_simulator=self.omt_simulator)
        nordpool_exchange_simulator = ITSIM.IterativeSimulator(auto_trader_parent, COMMON.Exchange.nordpool,
                                                               ITSIM._convert_to_list(nasty_orders_generators))
        trayport_exchange_simulator = ITSIM.IterativeSimulator(auto_trader_parent, COMMON.Exchange.trayport,
                                                               ITSIM._convert_to_list(nasty_orders_generators),
                                                               trayport_init_directory)

        # set exchange simulators depending on set simulated exchanges
        self.exchange_simulators = {
            # COMMON.Exchange.periotheus: (None, None),
            COMMON.Exchange.epex: (self.autotrader.epex.send_func, epex_exchange_simulator),
            COMMON.Exchange.nordpool: (self.autotrader.nordpool.send_func, nordpool_exchange_simulator),
            COMMON.Exchange.trayport: (self.autotrader.trayport.send_func, trayport_exchange_simulator),
        }

        self.exchange_simulators = {k: v for k, v in self.exchange_simulators.items() if k in simulated_exchanges}

        # initialize as None, this will be a coroutine to fill in the timer and strategy messages
        self.run_timer_and_event_message = None

        # set callbacks
        self.callback_timer = callback_timer
        self.callback_start = callback_start
        self.callback_finish = callback_finish

        # settings for calling the timer callbacks on the strategies
        self.timer_fast_timestep = timer_fast_timestep
        self.timer_timestep = timer_timestep

        self.next_timer_fast_event = 0
        self.next_timer_event = 0

        self._logs_initialized = False

        # record best orders to later visualization
        self.best_orders = collections.defaultdict(list)

    def init_autotrader(self, at_config, epex_config, nordpool_config, trayport_config):

        autotrader = autotrader_core.api.AutoTrader(
            create_dummy_products=False,
            no_live_data=True,
            use_own_strategies_folder=True,
            config=at_config,
            reraise_on_strategy_exception=self.reraise_on_strategy_exception,
        )

        if self.at_config.epex:
            exch_config_dict = {"autotrader_user": "AT_USER"}
            if epex_config:
                exch_config_dict.update(epex_config)
            exch_config = ATCONF.EpexConfig(LOGGER).set_configs_from_dict(
                exch_config_dict
            )

            autotrader.epex = APIEXCH.Epex(
                I9NUTIL.mem_send,
                create_dummy_products=False,
                allowed=True,
                exchange_config=exch_config,
            )

            # Since this is not called in backtest, as backtest does not call initialize,
            # the omt settings and the next omt request has to be set manually
            # this is only true for backtest, but not true for read-only simulation mode
            autotrader.epex._load_omt(self.omt_simulator.short_config, self.omt_simulator.long_config, True,
                                      autotrader.current_timestamp)
            autotrader.epex.next_omt_request = autotrader.current_timestamp + autotrader.epex.OMT_REFRESH_RATE
            autotrader.epex.init_files_correlation_ids = {"initialized": True}

        if self.at_config.nordpool:
            exch_config_dict = {"autotrader_user": "TEST_API_VISOTECH"}
            if nordpool_config:
                exch_config_dict.update(nordpool_config)
            exch_config = ATCONF.NordpoolConfig(LOGGER).set_configs_from_dict(
                exch_config_dict
            )

            autotrader.nordpool = APIEXCH.NordPool(
                I9NUTIL.mem_send,
                create_dummy_products=False,
                allowed=True,
                exchange_config=exch_config,
            )
            autotrader.nordpool.init_files_correlation_ids = {"initialized": True}

        if self.at_config.trayport:
            exch_config_dict = {"autotrader_user": "14"}
            if trayport_config:
                exch_config_dict.update(trayport_config)
            exch_config = ATCONF.TrayportConfig(LOGGER).set_configs_from_dict(
                exch_config_dict
            )

            autotrader.trayport = APIEXCH.Trayport(
                I9NUTIL.mem_send,
                create_dummy_products=False,
                allowed=True,
                exchange_config=exch_config,
            )
            # Mock the value of the action limit file instead of reading from a file.
            autotrader.trayport._read_action_limit_file = lambda: self.action_limit_data
            autotrader.trayport._read_broker_spec_file = lambda: self.broker_spec_data
            # Consider all brokers connected in backtesting, as we don't have (dis-)connect messages in the feed
            autotrader.trayport.is_broker_connected = lambda broker_id: True

            autotrader.trayport.init_files_correlation_ids = {"initialized": True}

        autotrader.send_to_pt = lambda *args, **kwargs: log_send_msg(
            COMMON.Exchange.periotheus, args, kwargs
        )

        auto_trader_child = copy.deepcopy(autotrader)
        auto_trader_child.is_parent = False
        auto_trader_child.send_to_parent = with_log(autotrader.update_from_strategy_request)

        if self.strategies_folder:
            print("The strategies location is currently specified as: {}".format(self.strategies_folder))
            auto_trader_child.get_custom_strategies_path = lambda: self.strategies_folder

        autotrader.send_to_children = with_log(functools.partial(auto_trader_child.update_from_json, properties={}))

        FLOG.log_to_stdout = False
        return autotrader, auto_trader_child

    @staticmethod
    def _close_order_book(exchange, timestamp):
        for product in exchange.products.get_all():
            for order in product.orders.get():
                order.quantity = 0
                order.update_db(timestamp=timestamp)
            product.orders = APITR.OrderBook()

    @property
    def strategy_messages(self):
        return [event_message for event_message in self.event_messages if event_message["message_type"] == "strategy"]

    def get_first_strategy_timestamp(self):
        active_strategies_times = []
        for msg in self.event_messages:
            message_type = msg.get("message_type")
            for strat_dict in msg["data"].values():
                if message_type.startswith("strategy"):
                    for strat_set in strat_dict.values():
                        if strat_set.get("active"):
                            active_strategies_times.append(msg["timestamp"])

        if active_strategies_times:
            return min(active_strategies_times)

        raise ValueError("Need to pass at least 1 active strategy when starting simulation.")

    @ALU.coroutine
    def invoke_timer_and_event_message(self):
        """This combines the strategy messages and the timer messages with the exchange feed

        This creates a generator, which:

        Makes sure that timer, fast time, and strategy messages are sent to the autotrader at the right times as the
        simulations goes through the exchange feed.

        This generator directly sends the messages to autotrader if it is necessary for the passed timestamp,
        and does not return anything

        :rtype: None
        """
        first_active_strategy_time = self.get_first_strategy_timestamp()

        self.next_timer_fast_event = first_active_strategy_time
        self.next_timer_event = first_active_strategy_time
        next_strategy_event = first_active_strategy_time
        received_timestamp = None
        self.event_messages.sort(key=lambda m: m["timestamp"])

        while True:
            current_timestamp = yield received_timestamp
            if len(self.event_messages) and current_timestamp > next_strategy_event:
                event_messages_due = [m for m in self.event_messages if m["timestamp"] <= current_timestamp]
                for (event_message) in event_messages_due:
                    self.send_timer_if_necessary(event_message["timestamp"])
                    message_type = event_message["message_type"]
                    if message_type in ("strategy", "strategy_steering_call"):
                        for strategy_data in event_message["data"].values():
                            for strategy_id, strategy_dict in strategy_data.items():
                                package = {
                                    "package_name": strategy_dict.get("package_name", ""),
                                    "package": strategy_dict.get("package", "")
                                }
                                with mock.patch("autotrader_core.persistence.MongoDBConnector.load_package",
                                                return_value=package):
                                    self.autotrader_child.update_strategy(strategy_id, strategy_dict)
                            # On strategy update might send something to the exchange.
                            # check all exchanges
                            for (send_func, exchange_simulator) in self.exchange_simulators.values():
                                at_response_messages = send_func.cache().get("res", [])
                                send_func.clear_cache()
                                exchange_simulator.send(at_response_messages)

                    elif message_type == "per_products_limits":
                        for limit_data in event_message["data"].values():
                            for strategy_id, strategy_limits_dict in limit_data.items():
                                self.autotrader_child.update_strategy_limits(strategy_id=strategy_id,
                                                                             message=strategy_limits_dict)

                    elif message_type == "synthetic_orders":
                        for strategy_id, payload in event_message["data"]["synthetic_orders"].items():
                            returned_error = self.autotrader_child.on_synthetic_order(strategy_id, payload)
                            if returned_error:
                                raise SimulationError(returned_error)
                        for (send_func, exchange_simulator) in self.exchange_simulators.values():
                            at_response_messages = send_func.cache().get("res", [])
                            send_func.clear_cache()
                            exchange_simulator.send(at_response_messages)

                    elif message_type == "emergency_halt_state_info":
                        self.autotrader.stop_trading(False, reason="stop the parent for test")
                        self.autotrader_child.stop_trading(False, reason="stop the child for test")
                        send_func_epex = self.exchange_simulators[COMMON.Exchange.epex][0]
                        at_response_messages = send_func_epex.cache().get("res", [])
                        send_func_epex.clear_cache()
                        exchange_simulator.send(at_response_messages)

                self.event_messages = [m for m in self.event_messages if m["timestamp"] > current_timestamp]
                if self.event_messages:
                    next_strategy_event = min(m["timestamp"] for m in self.event_messages)
                else:
                    next_strategy_event = None

            self.send_timer_if_necessary(current_timestamp)

    def send_timer_if_necessary(self, current_timestamp):
        run_next_timer = current_timestamp > self.next_timer_event
        run_next_fast_timer = current_timestamp > self.next_timer_fast_event
        while run_next_timer or run_next_fast_timer:
            if run_next_fast_timer:
                for (send_func, exchange_simulator) in self.exchange_simulators.values():
                    exchange_simulator.run_once(action_type=COMMON.TimerEvent.timer_fast,
                                                timestamp=self.next_timer_fast_event,
                                                auto_trader_child=self.autotrader_child, send_func=send_func)
                self.next_timer_fast_event += self.timer_fast_timestep
                run_next_fast_timer = current_timestamp > self.next_timer_fast_event
            if run_next_timer:
                for (send_func, exchange_simulator) in self.exchange_simulators.values():
                    exchange_simulator.run_once(action_type=COMMON.TimerEvent.timer, timestamp=self.next_timer_event,
                                                auto_trader_child=self.autotrader_child, send_func=send_func)
                if self.callback_timer:
                    self.callback_timer(self.autotrader_child, self.next_timer_event)
                self.next_timer_event += self.timer_timestep
                run_next_timer = current_timestamp > self.next_timer_event

    @staticmethod
    def get_feed_iterable_multi_file(filepaths=None, consecutive_files_aggregation=False):
        # type: (list[str], bool) -> dict
        """Method to create a generator, which allows to iterate through the messages of the given source

        if files are json:
            -> entire json is read and the content is returned one by one, if one file is finished,
            the method will continue with the next file given in the paths list

        if files are jsonl:
            -> in this case, the files are read line by line to reduce memory usage

        if files are zip files:
            -> each zipfile is scanned for the files it contains, and then the files are iterated through
            -> each file is checked whether it is a json or jsonl file, and then read as described for these 2 cases.
        :param consecutive_files_aggregation: flag whether to reaggregate the consecutive jsonl files meaningfully
        :type consecutive_files_aggregation: bool
        """
        if filepaths is None:
            yield {}
        assert all(os.path.exists(f) for f in filepaths), "Some files of {} could not be found.".format(filepaths)

        # Right now this option works only if the we have a list of jsonl files with consecutive dates
        if consecutive_files_aggregation:
            # initialize the index which we use to iterate through the files
            feed = Simulator.get_feed_iterable_single_file(filepaths.pop(0))

            # open feed files and use generators to loop through the feed
            next_feed = Simulator.get_feed_iterable_single_file(filepaths.pop(0))

            # get first messages and timestamps for the first comparisons, to know how to interlace the messages
            json_msg_current_file = next(feed)
            json_msg_next_file = next(next_feed)
            timestamp_current = json_msg_current_file["timestamp"]
            timestamp_next = json_msg_next_file["timestamp"]

            # we iterate through the first feed.
            # each time the timestamp of the first feed is bigger than the second, take the second
            # if the second feed finish, then we replace it with the next feed file
            # if the second feed finishes, and there is no next, we set the second feed to None
            # if the first feed finishes, we set the next to be the first, and load the next file for the next feed
            # if the second is None, and the first feed finishes,
            # we overwrite the first with the second. both feeds are now None, and the simulation stops
            while feed is not None:
                if (timestamp_current <= timestamp_next) or (next_feed is None):
                    yield json_msg_current_file
                    try:
                        json_msg_current_file = next(feed)
                        timestamp_current = json_msg_current_file["timestamp"]
                    except StopIteration:
                        LOGGER.info("Finished iterating through current file")
                        feed = next_feed
                        timestamp_current = timestamp_next
                        json_msg_current_file = json_msg_next_file
                        if filepaths:
                            next_feed = Simulator.get_feed_iterable_single_file(filepaths.pop(0))
                            json_msg_next_file = next(next_feed)
                            timestamp_next = json_msg_next_file["timestamp"]
                        else:
                            next_feed = None
                else:
                    yield json_msg_next_file
                    try:
                        json_msg_next_file = next(next_feed)
                        timestamp_next = json_msg_next_file["timestamp"]
                    except StopIteration:
                        LOGGER.info("Finished iterating through next file")
                        if filepaths:
                            next_feed = Simulator.get_feed_iterable_single_file(filepaths.pop(0))
                        else:
                            next_feed = None

        else:
            for filepath in filepaths:
                feed = Simulator.get_feed_iterable_single_file(filepath)
                for m in feed:
                    yield m

    @staticmethod
    def get_feed_iterable_single_file(filepath=None):
        # type: (str) -> dict
        """Method to create a generator, which allows to iterate through the messages of the given source

        if files are json:
            -> entire json is read and the content is returned one by one, if one file is finished,
            the method will continue with the next file given in the paths list
        if files are jsonl:
            -> in this case, the files are read line by line to reduce memory usage

        if files are zip files:
            -> each zipfile is scanned for the files it contains, and then the files are iterated through
            -> each file is checked whether it is a json or jsonl file, and then read as described for these 2 cases.
        """
        assert os.path.exists(filepath), "File of {} could not be found.".format(filepath)

        # Right now this option works only if the we have a list of jsonl files with consecutive dates
        filename = os.path.basename(filepath)
        if filename.endswith(".json"):
            with open(filepath, "r") as data_feeds:
                for m in json.load(data_feeds):
                    yield m
        elif filename.endswith(".jsonl"):
            with open(filepath, "r") as data_feeds:
                for line in data_feeds:
                    yield json.loads(line)
        elif filename.endswith(".zip"):
            with zipfile.ZipFile(filepath, "r") as myzip:
                for zipfilecontent in myzip.filelist:
                    if zipfilecontent.filename.endswith(".json"):
                        for data in json.loads(myzip.read(zipfilecontent).decode("utf-8")):
                            yield data
                    elif zipfilecontent.filename.endswith(".jsonl"):
                        for data in myzip.open(zipfilecontent):
                            yield json.loads(data)
                    else:
                        print("Could not read zipped file content: {} {}".format(filepath,
                                                                                 zipfilecontent.filename))
        elif filename.endswith("jsonl.gz"):
            with gzip.open(filepath, "rb") as f:
                for data in f:
                    yield json.loads(data)
        else:
            raise ValueError("File-extension not understood (feed {})".format(filepath))

    def run(
        self,
        write_logfiles=True,
        filename="autotrader_backtesting.log",
        consecutive_files_aggregation=False,
        **kwargs
    ):
        """Run simulation from zip-file, json-file or json-object

        :param write_logfiles: flag whether log files should be created. if true -> the backtest runs slower
        :type write_logfiles: bool
        :param filename: filename for backtesting compliance logs
        :type filename: str
        :param consecutive_files_aggregation: flag whether to re-aggregate the consecutive jsonl files in order.
        :type consecutive_files_aggregation: bool
        :return: None
        :rtype: None
        """
        for key in kwargs:
            LOGGER.warning("Used deprecated keyword argument when running simulation: %s", key)

        self.init_logs(LOGGER, write_logfiles=write_logfiles, filename=filename)
        self.compliance_log(LOGTEMP.BacktestingLogs.testing_started, strat_hashes=self.strategy_hash_str)
        print()
        print("---- START RUN ----")
        print("Configs: ")
        print(
            "Timed Callbacks: Fast every {}sec, Slow every {}sec".format(self.timer_fast_timestep, self.timer_timestep))
        print("Strategy messages: ", len(self.event_messages))
        print("Json Feed Set: ", bool(self.json_feed))
        print("Feed Paths Set:", self.feed_paths)
        print("Persistence:", self.database)
        print("===========")
        print()
        if write_logfiles:
            FLOG.setup(base_path="", base_filename=filename)
            FLOG.set_server_role("500: backtesting")
        else:
            FLOG.disable()

        area_exchanges = [
            (strat_def["market_area_1"], strat_def.get("exchange", strat_def.get("exchange_1", COMMON.Exchange.epex)))
            for m in self.strategy_messages
            for strat_def in m["data"]["strategy_objects"].values()
        ]

        # if json feed, an iterable of message dictionaries, is not given,
        # then create one based on the passed feed files
        if self.json_feed is None:
            # if we only have a single file, then make it into a list
            if isinstance(self.feed_paths, basestring):
                self.feed_paths = [self.feed_paths]

            # pass the feed paths and create an object to iterate through the messages one by one
            # this makes it consistent, no matter if a list is passed or a generator
            if len(self.feed_paths) == 1:
                self.json_feed = self.get_feed_iterable_single_file(self.feed_paths[0])
            else:
                self.json_feed = self.get_feed_iterable_multi_file(self.feed_paths, consecutive_files_aggregation)

        if self.callback_start is not None:
            self.callback_start(self.autotrader_child)

        if isinstance(self.json_feed, list):
            first_msg = self.json_feed.pop(0)
        else:
            first_msg = next(self.json_feed)

        if COMMON.Exchange.trayport in self.exchange_simulators:
            self._initialize_trayport(first_msg["timestamp"])
            assert self.autotrader.trayport.init_files_ready()
            # In production, the parent process sends a message to the child to mark the exchange as initialized.
            # In simulation, we have to do it manually
            child_trayport = self.autotrader_child.trayport
            for ci in child_trayport.init_files_correlation_ids:
                child_trayport.init_files_correlation_ids[ci] = True
            child_trayport.update_synthetic_products(self.autotrader_child.current_timestamp)

        # initialize at what times the timer messages are inserted into the stream.
        self.run_timer_and_event_message = self.invoke_timer_and_event_message()

        # some variables to keep track of simulation progress
        start = totalstart = time.time()
        num_steps = 0
        last_timestamp = 0
        last_timestamp_end = first_msg["timestamp"]
        print_per_n = 1000

        # since the first message was remove, we start by running it once with the first one,
        # to not forget any messages
        self.run_feed_step(first_msg)

        last_best_orders_update = first_msg["timestamp"]

        # start iteration through all messages
        for idx, feed in enumerate(self.json_feed):
            if not feed:
                continue
            last_timestamp = feed["timestamp"]
            if self.simulation_stop is not None and last_timestamp > self.simulation_stop:
                break
            self.run_feed_step(feed)
            if self.save_results and last_timestamp > last_best_orders_update + 60:
                self.record_best_orders(area_exchanges, last_timestamp)
                last_best_orders_update = last_timestamp

            num_steps = idx + 1
            if num_steps % print_per_n == 0:
                end = time.time()
                elapsed_simulation_time = feed["timestamp"] - first_msg["timestamp"]
                elapsed_since_last = feed["timestamp"] - last_timestamp_end
                last_timestamp_end = feed["timestamp"]
                print("Step: {:d}, Elapsed: {:.2f}s, {:.2f}it/s, simulation-time (UTC): {}, "
                      "simulation speed(x real time: {}, avg: {})\r"
                      .format(num_steps,
                              round(end - totalstart, 2),
                              round(print_per_n / (end - start), 2),
                              datetime.datetime.utcfromtimestamp(int(feed["timestamp"])).isoformat(),
                              round(elapsed_since_last / float(end - start), 2),
                              round(elapsed_simulation_time / (end - totalstart), 1)
                              )
                      )
                start = end

        for leftover_strat_msg in self.event_messages:
            self.run_timer_and_event_message.send(leftover_strat_msg["timestamp"])

        elapsed_simulation_time = last_timestamp - first_msg["timestamp"]
        end = time.time()
        to_print = (
            "Finished! Step: {:d}, Elapsed: {:.2f}s, {:.2f}it/s, simulation-time (UTC): {}, "
            "simulationSpeed(x realTime avg: {})\r".format(
                num_steps,
                round(end - totalstart, 2),
                round((num_steps % 1000 or 1000) / (end - start), 2),
                datetime.datetime.utcfromtimestamp(int(last_timestamp)).isoformat(),
                round(elapsed_simulation_time / (end - totalstart), 1),
            )
        )
        print(to_print)
        LOGGER.debug(to_print)

        results_file = "backtest_result_{}.json".format(datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
        backtesting_result_folder = os.path.join(os.path.abspath(os.curdir), "backtest_results")
        if not os.path.exists(backtesting_result_folder):
            os.makedirs(backtesting_result_folder)
        results_path = os.path.join(backtesting_result_folder, results_file)

        def get_own_trades(product):
            # type:(APITR.Product) -> list[dict]
            trades = product.trades.get(trade_filter=COMMON.TradeFilter.own)
            return [
                {
                    "product": {
                        "name": t.product.name,
                        "product_type": t.product.product_type,
                        "product_id": t.product.product_id,
                        "delivery_start": t.product.delivery_start,
                        "delivery_end": t.product.delivery_end
                    },
                    "buy_delivery_area": t.buy_delivery_area,
                    "sell_delivery_area": t.sell_delivery_area,
                    "quantity": t.quantity,
                    "price": t.price,
                    "execution_time": t.execution_time,
                    "tags": t.tags,
                    "portfolio_key": t.portfolio_key,
                    "direction": t.direction,
                    "trade_id": t.trade_id,
                    "aggressor_broker_id": t.aggressor_broker_id,
                    "initiator_broker_id": t.initiator_broker_id,
                    "order_id": t.order_id,
                    "exchange": t.exchange,
                }
                for t in trades
            ]

        def package_strategy(strategy):
            strategy["package"] = base64.b64encode(strategy.get("package", ""))
            return strategy

        # collect results in dicts, to write them into result json
        if self.save_results:
            results = {}
            trade_results = {}
            results["strategy_settings"] = {strat_id: package_strategy(strat.strategy_settings) for strat_id, strat in
                                            self.autotrader_child.strategies.items()}
            trade_results["epex"] = {p.product_id: get_own_trades(p) for p in
                                     self.autotrader_child.epex.products.get_all()}
            trade_results["nordpool"] = {p.product_id: get_own_trades(p) for p in
                                         self.autotrader_child.nordpool.products.get_all()}
            trade_results["trayport"] = {p.product_id: get_own_trades(p) for p in
                                         self.autotrader_child.trayport.products.get_all()}

            results["trade_results"] = trade_results
            results["best_orders_history"] = self.best_orders

            with open(results_path, "w") as f:
                json.dump(results, f)
                print("----------------------------------")
                print("Results saved in: ", results_path)
                print("----------------------------------")

        if self.callback_finish is not None:
            try:
                self.callback_finish(self.autotrader_child)
            except Exception:
                LOGGER.exception("Callback Finish after simulation ended raised exception.")
        self.compliance_log(LOGTEMP.BacktestingLogs.testing_finished, strat_hashes=self.strategy_hash_str)

        print()
        print("==== FINISHED RUN ====")
        print()

    def _plot_omt(self):
        """ Generates and shows a plot for short and long OMT values over time of the backtesting.

        We do not offer support for this method or any other matplotlib related questions. This method was developed for
        internal use.
        """
        if COMMON.Exchange.epex not in self.exchange_simulators.keys():
            print("No epex exchange was running, nothing to plot...")
            return
        try:
            import matplotlib.pyplot as plt
            data = self.exchange_simulators[COMMON.Exchange.epex][1].omt_historical_data
            x = [datetime.datetime.fromtimestamp(d["timestamp"]) for d in data]
            short_y = [d["short"] for d in data]
            long_y = [d["long"] for d in data]

            _, (ax1, ax2) = plt.subplots(2)
            ax1.set_title("Short OMT")
            ax1.plot(x, short_y)
            ax1.axhline(y=self.omt_simulator._short.lower_threshold, color='lightcoral', linestyle='-')
            ax1.axhline(y=self.omt_simulator._short.upper_threshold, color='maroon', linestyle='-')

            ax2.set_title("Long OMT")
            ax2.plot(x, long_y)
            ax2.axhline(y=self.omt_simulator._long.lower_threshold, color='lightcoral', linestyle='-')
            ax2.axhline(y=self.omt_simulator._long.upper_threshold, color='maroon', linestyle='-')
            plt.show()
        except ImportError:
            print("matplotlib is not installed")

    def export_historical_omt_data(self, filename=None, delimiter=",", decimal_delimiter="."):
        """ Exports the short and long OMT values over time of the backtesting into a CSV file.

        :param filename: Absolute path of the file to export to. If not given, the csv will be exported to a new file
                         in the current directory
        :type filename: str or None
        :param delimiter: csv field delimiter. Default value is ",". Possible values are in DELIMITERS
        :type delimiter: str
        :param decimal_delimiter: decimal delimiter for float numbers. Default value is ".".
                                  Possible values are in DECIMAL_DELIMITERS
        :type decimal_delimiter: str
        """
        if COMMON.Exchange.epex not in self.exchange_simulators.keys():
            print("No epex exchange was running, nothing to export...")
            return

        if not filename:
            filename = "historical_omt_{}.csv".format(datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
            backtesting_result_folder = os.path.join(os.path.abspath(os.curdir), "backtest_results")
            if not os.path.exists(backtesting_result_folder):
                os.makedirs(backtesting_result_folder)
            filename = os.path.join(backtesting_result_folder, filename)

        columns = ["timestamp", "short", "long"]
        MDE.write_to_csv_file(self.exchange_simulators[COMMON.Exchange.epex][1].omt_historical_data,
                              decimal_delimiter, delimiter, filename, csv_columns=columns)

    def _get_strat_hashes(self):
        """
        Extracts strategy hashes from the strategy messages feed, stores them in the self.strategy_hash_str
        """
        hashes = []
        for msg in self.strategy_messages:
            for strat_id, params in msg["data"]["strategy_objects"].items():
                hashes.append(SD.StrategyDefinition.strat_identifier_from_params(params))
        if not hashes:
            raise RuntimeError("No strategy hash found!")
        self.strategy_hash_str = ", ".join(hashes)

    def run_feed_step(self, msg):
        timestamp = msg["timestamp"]

        self.run_timer_and_event_message.send(timestamp)

        if msg["message_type"] == "new_session":
            exchange_id = msg.get("exchange")
            if exchange_id is None:
                print("WARNING: Could not determine Exchange for new session in feed message: {}. "
                      "Removing known orderbook in all exchanges which are used by at least 1 strategy in "
                      "simulation, as if new session concerns each."
                      "This only needs special treatment, if more than 1 exchange is simulated, "
                      "with feeds of more than 1 exchange.".format(msg))
                for exchange in {strat.exchange for strat in self.autotrader.strategies.values()}:
                    self._close_order_book(exchange, timestamp)
            else:
                exchange = self.autotrader.get_exchange(msg["exchange"])
                self._close_order_book(exchange, timestamp)
        else:
            exchange, message_type = (msg.get(key) for key in ["exchange", "message_type"])
            try:
                (send_func, current_exchange_simulator) = self.exchange_simulators[exchange]
                current_exchange_simulator.receive({"body": msg, "properties": {}})
            except COMMON.RestartExchangeException:
                if "message_type" == "market_state":
                    print("catching RestartExchangeException for ", msg)
                    return
                else:
                    raise

    def _initialize_trayport(self, feed_start_time):
        """
        Send initialization requests to the simulator and process the answers

        On Trayport, products are not included in the exchange feed, but created inside of autoTRADER
        as synthetic products, based on sequences and instruments. For this reason, setting no_live_data to True
        is not enough: We have to properly initialize the exchange here.

        :param feed_start_time: Epoch timestamp. The time at which the feed starts.
                                Needed to create the correct prompt products
        :type feed_start_time: int
        """
        send_func, exchange_simulator = self.exchange_simulators[COMMON.Exchange.trayport]
        # autoTRADER's time is used by the simulator for the response messages
        self.autotrader.current_timestamp = feed_start_time
        self.autotrader_child.current_timestamp = feed_start_time
        self.autotrader.trayport.initialize()
        messages = send_func.cache().get("res", [])
        send_func.clear_cache()
        exchange_simulator.send(messages)

    def evaluate(self):
        raise NotImplementedError

    def export_market_data(self, trade_type,
                           group_by_product_id=False,
                           delivery_start=None,
                           delivery_end=None,
                           filename=None,
                           delimiter=",",
                           decimal_delimiter=".",
                           exchange_id=None):
        """
        Function to export back-testing market data to a csv file.

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
        :param filename: name of the file to export to
        :type filename: str
        :param delimiter: csv field delimiter. Default value is ",". Possible values are in DELIMITERS
        :type delimiter: str
        :param decimal_delimiter: decimal delimiter for float numbers. Default value is ".".
                                  Possible values are in DECIMAL_DELIMITERS
        :type decimal_delimiter: str
        :param exchange_id: exchange ID. One of "TRAYPORT", "EPEX" or "NORD".
                            Not needed if only 1 exchange is simulated.
        :type exchange_id: str
        :return: Number of exported records (lines)
        :rtype: int
        """
        if exchange_id is None:
            if len(self.exchange_simulators) == 1:
                exchange_id = self.exchange_simulators.keys()[0]
            else:
                raise ValueError("Please specify the exchange to export for simulations with more than 1 exchange!")
        if filename is None:
            filename = "market_data_{}_{}.csv".format(trade_type, datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
            backtesting_result_folder = os.path.join(os.path.abspath(os.curdir), "backtest_results")
            if not os.path.exists(backtesting_result_folder):
                os.makedirs(backtesting_result_folder)
            filename = os.path.join(backtesting_result_folder, filename)

        if self.use_persistence:
            MDE.export_market_data(database=self.database, exchange_id=exchange_id, trade_type=trade_type,
                                   group_by_product_id=group_by_product_id,
                                   delivery_start=delivery_start, delivery_end=delivery_end,
                                   filename=filename, delimiter=delimiter, decimal_delimiter=decimal_delimiter)
        else:
            is_own = "own" in trade_type.lower()
            if is_own:
                trades = self.get_own_trades()
            else:
                trades = self.get_public_trades()

            stats = self.get_trade_stats(trades, is_own)
            csv_columns = MDE._get_csv_headers(stats,
                                               sort_function=lambda field: "{}_{}".format(field.split("_")[-1], field))
            MDE.write_to_csv_file(stats, decimal_delimiter, delimiter, filename, csv_columns)

    def get_trade_stats(self, trades, is_own=True):
        """Get statistics of trades based on area id and product

        :param is_own:
        :type trades: list[APITR.Trade]
        :return:
        """
        trade_type_str = "own" if is_own else "pub"

        array_type = np.dtype([('execution_time', 'f8'), ('delivery_start', np.int32), ('delivery_end', np.int32),
                               ('product_id', '|S30'), ('buy_delivery_area', '|S30'), ('sell_delivery_area', '|S30'),
                               ('price', 'f8'), ('quantity', 'f8')])
        trade_array = np.array([(t.execution_time, t.product.delivery_start, t.product.delivery_end,
                                 t.product.product_id, t.buy_delivery_area, t.sell_delivery_area, t.price, t.quantity)
                                for t in trades], array_type)

        product_ids = set(np.unique(trade_array["product_id"]).tolist())
        areas = set(np.unique(trade_array["buy_delivery_area"]).tolist()
                    + np.unique(trade_array["sell_delivery_area"]).tolist())

        stat_entries = []
        for product_id in product_ids:
            product_trade_array = trade_array[trade_array["product_id"] == product_id]
            for area in areas:
                product_area_trade_array = product_trade_array[
                    (product_trade_array["buy_delivery_area"] == area)
                    & (product_trade_array["sell_delivery_area"] == area)
                ]
                if product_area_trade_array.shape[0] > 0:
                    min_price = trade_array["price"].min()
                    max_price = trade_array["price"].max()
                    total_traded = trade_array["quantity"].sum()
                    (
                        last_execution_time, last_delivery_start, last_delivery_end, last_product_id, last_buy_area,
                        last_sell_area, last_price, last_quantity
                    ) = trade_array[trade_array["execution_time"].argmax()]
                    (
                        first_execution_time, first_delivery_start, first_delivery_end, first_product_id,
                        first_buy_area, first_sell_area, first_price, first_quantity
                    ) = trade_array[trade_array["execution_time"].argmin()]
                    vwap = (trade_array["price"] * trade_array["quantity"]).sum() / total_traded

                    stat_entries.append(
                        {"product_id": last_product_id,
                         "delivery_start": last_delivery_start,
                         "delivery_end": last_delivery_end,
                         "area": area,
                         "own_or_public": trade_type_str,
                         "high_price": max_price,
                         "low_price": min_price,
                         "traded_volume": total_traded,
                         "vwap": round(vwap, 2),
                         "last_price": last_price,
                         "last_quantity": last_quantity,
                         "last_trade_time": last_execution_time,
                         "first_price": first_price,
                         "first_quantity": first_quantity,
                         "first_trade_time": first_execution_time
                         }
                    )

        return stat_entries

    def record_best_orders(self, area_exchanges, last_timestamp):
        """Add the best orders to self.best_orders for current timestamp. This history can then be persisted

        :param area_exchanges: areas and exchanges which will be checked for best orders in all their active products
        :type area_exchanges: list[tuple[str, str]]
        :param last_timestamp: timestamp, for which the values are going to be kept
        :type last_timestamp: float
        :rtype: None
        """
        for area, exchange_name in area_exchanges:
            exchange = self.autotrader_child.get_exchange(exchange_name)
            products = exchange.products.get_active_products(area)
            for p in products:
                ind = p.orders.indicators(area)
                if ind:
                    best_buy = ind[0].mw_prices[0][0]
                    best_sell = ind[0].mw_prices[0][1]
                else:
                    best_buy = None
                    best_sell = None
                self.best_orders["___".join(map(str, [area, exchange_name, p.delivery_start, p.delivery_end]))].append(
                    (last_timestamp, best_buy, best_sell)
                )

    def export_own_trades(self, area_id=None, product_ids=None,
                          execution_until=None, execution_after=datetime.datetime.min, internal=None,
                          filename=None, delimiter=",", decimal_delimiter=".", exchange_id=None):
        """
        Query trades and export them to a csv file.
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
                         in the current directory
        :type filename: str or None
        :param delimiter: csv field delimiter. Default value is ",". Possible values are in DELIMITERS
        :type delimiter: str
        :param decimal_delimiter: decimal delimiter for float numbers. Default value is ".".
                                  Possible values are in DECIMAL_DELIMITERS
        :type decimal_delimiter: str
        :param exchange_id: exchange ID. One of "TRAYPORT", "EPEX" or "NORD".
                            Not needed if only 1 exchange is simulated.
        :type exchange_id: str
        """
        if not filename:
            filename = "own_trades_{}.csv".format(datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
            backtesting_result_folder = os.path.join(os.path.abspath(os.curdir), "backtest_results")
            if not os.path.exists(backtesting_result_folder):
                os.makedirs(backtesting_result_folder)
            filename = os.path.join(backtesting_result_folder, filename)

        if exchange_id is None:
            if len(self.exchange_simulators) == 1:
                exchange_id = self.exchange_simulators.keys()[0]
            else:
                raise ValueError("Please specify the exchange to export for simulations with more than 1 exchange!")
        if self.use_persistence:
            MDE.export_trades(self.database, exchange_id, "OwnTrade", area_id=area_id, product_ids=product_ids,
                              execution_until=execution_until, execution_after=execution_after, internal=internal,
                              filename=filename, delimiter=delimiter, decimal_delimiter=decimal_delimiter,
                              columns=DEFAULT_TRADE_EXPORT_COLUMNS + ["internal"])
        else:
            # Cannot export trades from Mongo without persistence. Using in-memory Data.
            trades = self.get_own_trades()
            profit = sum([trade.price * trade.quantity for trade in trades])
            print("Total Sales: ", profit, " Euro")
            columns = DEFAULT_TRADE_EXPORT_COLUMNS + ["internal", "slot_type", "stats"]
            MDE.write_to_csv_file([t.to_dict() for t in trades], decimal_delimiter, delimiter, filename,
                                  csv_columns=columns)

    def export_public_trades(self, area_id=None, product_ids=None,
                             execution_until=None, execution_after=datetime.datetime.min,
                             filename=None, delimiter=",", decimal_delimiter=".", exchange_id=None):
        """
        Query trades and export them to a csv file.
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
                         in the current directory
        :type filename: str
        :param delimiter: csv field delimiter. Default value is ",". Possible values are in DELIMITERS
        :type delimiter: str
        :param decimal_delimiter: decimal delimiter for float numbers. Default value is ".".
                                  Possible values are in DECIMAL_DELIMITERS
        :type decimal_delimiter: str
        :param exchange_id: exchange ID. One of "TRAYPORT", "EPEX" or "NORD".
                            Not needed if only 1 exchange is simulated.
        :type exchange_id: str
        """
        if not filename:
            filename = "public_trades_{}.csv".format(datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
            backtesting_result_folder = os.path.join(os.path.abspath(os.curdir), "backtest_results")
            if not os.path.exists(backtesting_result_folder):
                os.makedirs(backtesting_result_folder)
            filename = os.path.join(backtesting_result_folder, filename)

        if exchange_id is None:
            if len(self.exchange_simulators) == 1:
                exchange_id = self.exchange_simulators.keys()[0]
            else:
                raise ValueError("Please specify the exchange to export for simulations with more than 1 exchange!")
        if self.use_persistence:
            MDE.export_trades(self.database, exchange_id, "PublicTrade", area_id=area_id, product_ids=product_ids,
                              execution_until=execution_until, execution_after=execution_after,
                              filename=filename, delimiter=delimiter, decimal_delimiter=decimal_delimiter,
                              columns=DEFAULT_TRADE_EXPORT_COLUMNS)
        else:
            # Cannot export trades from Mongo without persistence. Using in-memory Data.
            trades = self.get_public_trades()
            columns = DEFAULT_TRADE_EXPORT_COLUMNS + ["internal"]
            MDE.write_to_csv_file([t.to_dict() for t in trades], decimal_delimiter, delimiter, filename,
                                  csv_columns=columns)

    def get_net_traded_amounts_by_strategy(self, printout=False, only_traded=False):
        """Get the net and total traded amounts by strategy and product, and print out if needed

        :param printout: flag whether a summary table should be printed to the terminal or not
        :type printout: bool
        :param only_traded: flag whether only the products with at least 1 own trade should be in the summary table
        :type only_traded: bool
        :return: traded amounts, traded[strategy[prodict_id->net/total-volume]]
        :rtype: dict[str, dict[str, any]]
        """

        net_traded_by_strategy = {}
        columns_header = ("|                     Strategy                      |"
                          "    start-end [Europe/Vienna]  | "
                          "total-traded | net-traded |"
                          "        product-id        |"
                          "        area-id        |"
                          "  unit  |"
                          "      product-type     |"
                          "                             product-name                              |")
        lengths = map(len, columns_header.split("|"))[1:]
        if printout:
            print("=" * len(columns_header))
            print(columns_header)
            print("-" * len(columns_header))
        for stratid, strategy in self.autotrader_child.strategies.items():
            net_traded_by_strategy[stratid] = {}
            productslist = strategy.exchange.products
            for product in productslist.get_all():
                all_areas_total_traded = 0
                all_areas_net_traded = 0
                by_areas = {}
                trades = product.trades.get(trade_filter=COMMON.TradeFilter.own)
                areas = set(t.buy_delivery_area for t in trades).union(set(t.sell_delivery_area for t in trades))
                for area in (a for a in areas if a):

                    # For Trayport, check the unit of the area
                    # For EPEX and Nordpool, always use MW
                    if product.exchange == COMMON.Exchange.trayport:
                        area_property = self.autotrader.trayport.trayport_areas[area]
                        unit = getattr(area_property, 'unit', "").upper()
                        if unit == "MWH":
                            unit = "MWH/H"
                    else:
                        unit = "MW"

                    total_volume = product.trades.get_volume(
                        delivery_area_id=area,
                        trade_filter=COMMON.TradeFilter.own,
                        portfolio_key=stratid,
                    )
                    net_volume = product.trades.get_balance(
                        delivery_area_id=area,
                        portfolio_key=stratid,
                    )
                    total_volume = round(total_volume, 4)
                    all_areas_total_traded += UU.convert_units(total_volume, unit, COMMON.Units.MW,
                                                               round(product.duration / float(COMMON.HOUR), 6))
                    net_volume = round(net_volume, 4)
                    all_areas_net_traded += UU.convert_units(net_volume, unit, COMMON.Units.MW,
                                                             round(product.duration / float(COMMON.HOUR), 6))
                    by_areas.update({
                        area: {
                            "total_volume": total_volume,
                            "net_volume": net_volume,
                            "unit": unit,
                        }
                    })
                    net_traded_by_strategy[stratid][product.product_id] = {
                        "name": product.name,
                        "start": product.delivery_start,
                        "end": product.delivery_end,
                        "total_volume": all_areas_total_traded,
                        "net_volume": all_areas_net_traded,
                        "areas": by_areas
                    }
                    if total_volume == 0 and only_traded:
                        continue
                    if printout:
                        text = "|"
                        for idx, entry in enumerate(
                                (stratid,
                                 "{}-{}".format(CETUTIL.utc_ts2cet_str(product.delivery_start),
                                                CETUTIL.utc_ts2cet_str(product.delivery_end)),
                                 str(total_volume),
                                 str(net_volume),
                                 product.product_id,
                                 area,
                                 unit,
                                 product.product_type,
                                 product.name)):
                            text += entry.ljust(lengths[idx])
                            text += "|"
                        print(text)
                        print("-" * len(columns_header))

        return net_traded_by_strategy

    def get_own_trades(self):
        """Return the own trades saved in memory in the simulation

        :rtype: list[APITR.OwnTrade]
        """
        own_trades = []
        for stratid, strategy in self.autotrader_child.strategies.items():
            productslist = strategy.exchange.products
            for product in productslist.get_all():
                own_trades.extend(product.trades.get(
                    portfolio_key=stratid,
                    trade_filter=COMMON.TradeFilter.own,
                ))
        own_trades.sort(key=lambda t: t.execution_time)
        return own_trades

    def get_public_trades(self):
        """Return the public trades saved in memory in the simulation

        :rtype: list[APITR.PublicTrade]
        """
        trades = []
        done = []
        for stratid, strategy in self.autotrader_child.strategies.items():
            productslist = strategy.exchange.products
            all_products = productslist.get_all()
            for product in all_products:
                if (product.product_id, strategy.delivery_area_id) in done:
                    continue
                trades.extend(product.trades.get(
                    delivery_area=strategy.delivery_area_id,
                    trade_filter=COMMON.TradeFilter.public,
                ))
                done.append((product.product_id, strategy.delivery_area_id))
        trades.sort(key=lambda t: t.execution_time)
        return trades
