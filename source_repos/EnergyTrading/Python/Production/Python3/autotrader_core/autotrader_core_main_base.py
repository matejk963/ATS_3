from __future__ import absolute_import
import datetime
import errno
import threading
import time
import sys
import zmq

import autotrader_core.api
import autotrader_core.exchanges as APIEXCH
import autotrader_lib.common as COMMON
import autotrader_core.persistence as PERSIST
import autotrader_lib.adapters.connection_manager_adapter as CMA
import autotrader_lib.adapters.readonly_simulation_adapter as ROSA
import autotrader_lib.config_helper as ATCONF
import autotrader_lib.sockets as ATSOCK
import six

if six.PY2:
    import autotrader_lib.fast_logging_py2 as FLOG
else:
    import autotrader_lib.fast_logging_py3 as FLOG

log = FLOG.getLogger("autotrader")

MINIMAL_POLL_TIMEOUT_MILLISECONDS = 1


class AutotraderCoreMainBase(object):
    """This class holds the main entry point for the autotrader core executable.

    It acts on the given configuration, instantiates the autotrader core and connects it to the outside world using
    various adapters. It also holds the main loop driving the autotrader.
    """

    adapter_poll_timeout = 200  # Timeout for poll in receive_from_adapters. Can be set to a smaller value in tests

    def __init__(
            self,
            is_parent,  # type: bool
            at_config,  # type: ATCONF.ATConfig
            mongo_config,  # type: ATCONF.MongoConfig
            epex_config,  # type: ATCONF.EpexConfig
            epex_manager_config,  # type: ATCONF.ManagerConfig
            nordpool_config,  # type: ATCONF.NordpoolConfig
            nordpool_manager_config,  # type: ATCONF.ManagerConfig
            trayport_config,  # type: ATCONF.TrayportConfig
            trayport_manager_config,  # type: ATCONF.TrayportManagerConfig
    ):
        """

        :param is_parent: Whether this core is parent or child
        :type is_parent: bool
        :param at_config: Config class with settings for autotrader section
        :type at_config: ATCONF.ATConfig
        :param mongo_config: Config class with settings for mongo section
        :type mongo_config: ATCONF.MongoConfig
        :param epex_config: Config class with settings to login to epex Exchange, usually comxerv section
        :type epex_config: ATCONF.EpexConfig
        :param epex_manager_config: Config class with settings for epex connection to autotrader, usually epex-manager
        :type epex_manager_config: ATCONF.ManagerConfig
        :param nordpool_config: Config class with settings to login to nordpool Exchange, usually nordpool section
        :type nordpool_config: ATCONF.NordpoolConfig
        :param nordpool_manager_config: Config class with settings for nordpool connection to autotrader, usually
            nordpool-manager
        :type nordpool_manager_config: ATCONF.ManagerConfig
        :param trayport_config: Config class with settings to login to trayport Exchange, usually trayport section
        :type trayport_config: ATCONF.TrayportConfig
        :param trayport_manager_config: Config class with settings for trayport connection to autotrader, usually
            trayport-manager
        :type trayport_manager_config: ATCONF.ManagerConfig
        :return: None
        """

        self.is_parent = is_parent

        self.at_config = at_config
        self.mongo_config = mongo_config
        self.epex_config = epex_config
        self.epex_manager_config = epex_manager_config
        self.nordpool_config = nordpool_config
        self.nordpool_manager_config = nordpool_manager_config
        self.trayport_config = trayport_config
        self.trayport_manager_config = trayport_manager_config

        self.sockets = ATSOCK.CoreAdapterSockets(self.at_config, logger=log, publish_status=self.is_parent)
        self.next_autotrader_run_unix_ts = 0
        self.autotrader_run_interval_s = COMMON.TIMER_SLEEP_SLOW

        self.next_immediate_action = 0
        self.autotrader_immediate_action_s = COMMON.TIMER_SLEEP_FAST
        self.next_heartbeat_unix_ts = 0
        self.next_nagios_unix_ts = 0
        self.next_strategies_load_ts = 0

        # The timestamp of the beginning of the simulation, if run in backtesting mode
        self.start_simulation_time = None
        self.init_walltime = None
        self.time_limit_to_die = None

        self.total_poll_timeouts = 0
        self.log_poll_waiting_time = 0

        if self.at_config.backtesting and self.is_parent:
            # The exchange_feed adapter for backtesting mode has no sockets,
            # but could still have data ready from its file,
            # so we should not wait long for the sockets.
            self.adapter_poll_timeout = MINIMAL_POLL_TIMEOUT_MILLISECONDS

        self.should_die = threading.Event()

        PERSIST.MongoDBConnector().initialize(
            host=self.mongo_config.host,
            port=self.mongo_config.port,
            database_name=self.mongo_config.database,
            is_parent=is_parent,
            username=self.mongo_config.username,
            password=self.mongo_config.password,
            keep_strategy_history=self.at_config.keep_strategy_history,
            expiry_interval=999999999 if self.at_config.backtesting else None,
            auth_source=self.mongo_config.auth_source,
            store_public_orders=at_config.write_public_orders_to_db,
        )

        self.autotrader_core = self.new_autotrader()  # type: autotrader_core.api.AutoTrader

        self.autotrader_core.configured_routes = trayport_config.routes_to_market if trayport_config else None

        self.adapters = {}
        self._init_adapters()

        self.autotrader_core.update_initialization_states()

    def _init_adapters(self):
        """Initialize adapters during first initialization (i.e. establish parent/child communication)"""
        raise NotImplementedError()

    def run_until_condition(self):
        """Defines condition to break the while loop.
           Exit the while loop when self.should_die is set to True
        """
        return not self.should_die.is_set()

    def run(self):
        log.info("start-up complete.")
        self.log_poll_waiting_time = time.time()

        while self.run_until_condition():
            try:
                now = time.time()
                self.run_once(now)
            except Exception:
                # Ensure that the traceback is not swallowed somewhere...
                log.exception("Unhandled exception in main loop!")
                raise
            # clears all information relating to the current or last exception that occurred in the current thread
            try:
                sys.exc_clear()
            except Exception:
                pass

        if not self._are_all_orders_removed():
            log.critical("some orders removal was not confirmed by the exchange")
            self.log_unremoved_orders()

        log.debug("closing sockets.")
        self.sockets.close()
        self._close_adapters()
        log.debug("all sockets closed.")
        log.debug("closing persistence writer thread (if it is still alive).")
        PERSIST.MongoDBConnector().stop()  # gracefully exit the persistence thread
        log.debug("closed persistence writer thread.")
        log.info("halt")

    def run_once(self, now_ts):
        """
        Loop once over all adapters and process their messages.

        Additionally perform periodic tasks where appropriate

        :param now_ts: The current timestamp (in real time, not simulation time).
        :type now_ts: float
        """
        if self.at_config.backtesting:
            if self.start_simulation_time is None \
                    or (self.is_parent and any(self._exchange_restart_pending_children.values())):
                now_ts = 0  # Long in the past, way before any data feed starts
            else:
                timedelta_walltime = now_ts - self.init_walltime
                now_ts = self.start_simulation_time + timedelta_walltime * self.at_config.playback_speed
        try:
            if now_ts >= self.next_autotrader_run_unix_ts:
                self.next_autotrader_run_unix_ts = now_ts + self.autotrader_run_interval_s
                self._periodic_tasks_slow(now_ts)
            elif now_ts >= self.next_immediate_action:
                self.next_immediate_action = now_ts + self.autotrader_immediate_action_s
                self._periodic_tasks_fast(now_ts)
        except COMMON.HaltExchangeException as hee:
            log.exception("Received HaltExchangeException, halting %s reason '%s'", hee.exchange_id, hee)
            self._stop_exchange_on_exception(hee)
        except COMMON.RestartExchangeException as ree:
            log.warning(
                "Received RestartExchangeException, restarting exchange %s reason '%s'", ree.exchange_id, ree)
            self._exchange_restart_required_detected(ree.exchange_id)
        except COMMON.WriterThreadException:
            log.exception("Received WriterThreadException, stopping autoTRADER!")
            self.stop()
        except Exception as err:  # pylint: disable=W0703
            log.exception("Received exception during timer")
            self._stop_trading_on_exception(err)
        self._before_receive_from_adapters_hook()
        self._receive_from_adapters(now_ts)
        self._after_receive_from_adapters_hook()

    def _stop_trading_on_exception(self, error):
        reason = "{}: {}".format(error.__class__.__name__, error)
        self._stop_trading(reason, remove_orders=True, critical=True,
                           username=COMMON.PeriotheusSystemUsers.system)

    def _stop_trading(self, reason, remove_orders, critical, username):
        self.autotrader_core.stop_trading(critical=critical, reason=reason, remove_orders=remove_orders,
                                          username=username)
        parent_child_message = dict(exchange_id=COMMON.Exchange.autotrader,
                                    message_type=COMMON.ParentChildMessages.trading_halt,
                                    data=[{"reason": reason,
                                           "critical": critical,
                                           "remove_orders": remove_orders,
                                           "halting_user": username,
                                           "timestamp": time.time()}])
        self._forward(parent_child_message)

    def _stop_exchange_on_exception(self, error):
        try:
            exchange = self.autotrader_core.get_exchange(error.exchange_id)
            restart = error.restart
        except AttributeError:
            log.exception("No exchange specified in HaltExchangeException. Halting autoTRADER")
            self._stop_trading_on_exception(error)
        else:
            reason = str(error)
            if not reason:
                reason = "Received HaltExchangeException"
            self._stop_exchange(exchange, reason, remove_orders=True, critical=True,
                                username=COMMON.PeriotheusSystemUsers.system)
            if restart:
                self._exchange_restart_required_detected(exchange.internal_id)

    def _stop_exchange(self, exchange, reason, remove_orders, critical, username):
        """
        Halt the exchange

        :param exchange: The exchange object to halt
        :type exchange: APIEXCH.ExchangeBase
        :param reason: The halt reason
        :type reason: str
        :param remove_orders: If True, orders for all strategies of this exchange are removed, if False,
                              the orders stay (hands-off).
                              Note that hands-off can be overruled halts of the strategy/ autoTRADER  with
                              remove_orders=True
        :type remove_orders: bool
        :param critical: Is this a critical halt, i.e. triggered by a bug in autoTRADER and not by a manual trader
                         via the REST-API. Note that unhalting from a critical halt causes a (slow) re-initialization
                         of the exchange (because the bug that caused the critical halt could mean that the current
                         order book state is wrong and needs to be reset), while unhalting from non-critical halts
                         takes effect immediately without re-initialization.
        :type critical: bool
        :param username: The user who triggered the halt. Used for compliance logs
        :type username: str
        """
        exchange.stop_exchange(reason, critical=critical, remove_orders=remove_orders, username=username)
        self.autotrader_core.call_strategies_on_at_or_exchange_halt(remove_orders=remove_orders,
                                                                    exchange=exchange)
        parent_child_message = dict(exchange_id=exchange.internal_id,
                                    message_type=COMMON.ParentChildMessages.exchange_halt,
                                    data=[{"reason": reason,
                                           "critical": critical,
                                           "remove_orders": remove_orders,
                                           "timestamp": time.time(),
                                           "halting_user": username}])
        self._forward(parent_child_message)

    def _forward(self, message):
        """Helper function to forward messages between parent and children"""
        raise NotImplementedError

    def _periodic_tasks_slow(self, now):
        """Periodic tasks executed on the slow timer ticks"""
        self.autotrader_core.run_once(action_type=COMMON.TimerEvent.timer, timestamp=now)
        self.autotrader_core.update_initialization_states()

    def _periodic_tasks_fast(self, now):
        """Periodic tasks executed on the fast timer ticks"""
        self.autotrader_core.run_once(action_type=COMMON.TimerEvent.timer_fast, timestamp=now)
        if not PERSIST.MongoDBConnector().is_writer_alive():
            raise COMMON.WriterThreadException("Mongo writer thread has died, autoTRADER must exit")

    def _close_adapters(self):
        for adapter in self.adapters.values():
            adapter.close()

    def _before_receive_from_adapters_hook(self):
        """Callback to be overwritten by child classes."""
        pass

    def _after_receive_from_adapters_hook(self):
        """Callback to be overwritten by child classes."""
        pass

    def _exchange_restart_required_detected(self, exchange_id):
        """Called when the current process detects that an exchange requires a restart. Overwrite in child classes."""
        raise NotImplementedError()

    def _replace_exchange(self, exchange_id):
        """
        Replace old exchange instance with a new one. Also prevent sending messages on the old exchange by
        replacing its send_func method.

        :param exchange_id: Exchange to be replaced.
        :type exchange_id: str
        """
        log.info("Restarting exchange: %s", exchange_id)
        old_exchange = self.autotrader_core.get_exchange(exchange_id)

        send_func = self.send_prevent

        simulation_mode = isinstance(self.adapters.get(exchange_id), ROSA.ReadonlySimAdapter)
        indicator_update = self.at_config and self.at_config.update_indicators_on_parent or not self.is_parent

        if exchange_id == COMMON.Exchange.epex:
            self.autotrader_core.epex = APIEXCH.Epex(send_func,
                                                     self.autotrader_core.create_dummy_products,
                                                     True, self.epex_config,
                                                     indicator_update=indicator_update,
                                                     is_parent=self.is_parent)

            self.autotrader_core.epex.simulation_mode = simulation_mode

        elif exchange_id == COMMON.Exchange.nordpool and self.at_config.nordpool:
            self.autotrader_core.nordpool = APIEXCH.NordPool(send_func,
                                                             self.autotrader_core.create_dummy_products,
                                                             True, self.nordpool_config,
                                                             indicator_update=indicator_update,
                                                             is_parent=self.is_parent)
            self.autotrader_core.nordpool.simulation_mode = simulation_mode

        elif exchange_id == COMMON.Exchange.trayport and self.at_config.trayport:
            self.autotrader_core.trayport = APIEXCH.Trayport(send_func,
                                                             self.autotrader_core.create_dummy_products,
                                                             True, self.trayport_config,
                                                             indicator_update=indicator_update,
                                                             is_parent=self.is_parent)
            self.autotrader_core.trayport.simulation_mode = simulation_mode

        if old_exchange:
            # for safety reasons, render the old exchange object useless.
            # we don't have control over the customer's strategy code, and in case they keep a stale reference
            # we should rather throw errors than operate on the old object
            def _safe_throw_function(**unused_kwargs):
                """Raises a DanglingExchangeException if someone uses an old exchange that was restarted"""
                raise COMMON.DanglingExchangeException

            old_exchange.modify_orders = _safe_throw_function
            old_exchange.products = None
            old_exchange.update_db = _safe_throw_function

        log.info("Restart finished for exchange: %s", exchange_id)

    def _receive_from_adapters(self, timestamp):
        try:
            time_start = time.time()
            events = dict(self.sockets.poller.poll(timeout=self.adapter_poll_timeout))
            time_waiting_for_poll = time.time() - time_start
        except zmq.error.ZMQError as err:
            # ignore interrupts:
            if err.errno not in (errno.EINTR, zmq.EAGAIN):
                raise
            else:
                log.exception("Upon polling the sockets a ZMQError was encountered and skipped.")
                return
        self.total_poll_timeouts += time_waiting_for_poll
        # log total time waiting on zmq polls once per minute
        if self.log_poll_waiting_time + datetime.timedelta(seconds=60).total_seconds() < time_start:
            log.debug("Total time waiting on zmq polls: {} seconds. Out of {} seconds.".format(
                self.total_poll_timeouts, time.time() - self.log_poll_waiting_time))
            self.log_poll_waiting_time = time.time()
            self.total_poll_timeouts = 0
        for exchange_id, adapter in six.iteritems(self.adapters):
            if adapter.requires_restart_of_exchange(events):
                log.info("restarting exchange %s (requested by %s).", exchange_id, adapter)
                self._exchange_restart_required_detected(exchange_id)
            try:
                adapter.step(events, timestamp)
                if self.autotrader_core and isinstance(adapter,
                                                       (CMA.ConnectionManagerAdapter, ROSA.ReadonlySimAdapter)):
                    self.autotrader_core.get_exchange(exchange_id).update_connection_status(adapter.connected)
            except COMMON.HaltExchangeException as hee:
                log.exception("Received HaltExchangeException from %s, halting %s", adapter, hee.exchange_id)
                self._stop_exchange_on_exception(hee)
            except COMMON.RestartExchangeException as ree:
                log.warning("Received RestartExchangeException from %s, restarting exchange %s",
                            adapter, ree.exchange_id)
                self._exchange_restart_required_detected(ree.exchange_id)
            except COMMON.OutOfSyncChildException:
                log.exception("Received OutOfSyncChildException from %s, killing ourselves", adapter)
                self.stop()
                # we are out of sync and we don't want to do anything more
                break
            except COMMON.ChangeStreamException:
                log.exception("Received ChangeStreamException from %s, killing ourselves", adapter)
                self.stop()
                break
            except Exception as err:  # pylint: disable=W0703
                log.exception("Received exception on %s", adapter)
                if exchange_id in COMMON.Exchange.get_external():
                    exchange = self.autotrader_core.get_exchange(exchange_id)
                    self._stop_exchange(exchange, "{}: {}".format(type(err).__name__, err), remove_orders=True,
                                        critical=True, username=COMMON.PeriotheusSystemUsers.system)
                    self.autotrader_core.call_strategies_on_at_or_exchange_halt(remove_orders=True,
                                                                                exchange=exchange)

                else:
                    self._stop_trading_on_exception(err)

    @staticmethod
    def _are_all_orders_removed():
        return PERSIST.MongoDBConnector().are_all_orders_removed()

    def log_unremoved_orders(self):
        if self.is_parent:  # you only log once
            log.critical("Remaining open orders when restarting autotrader: {}".format(
                [{k: o[k] for k in ("order_id", "direction", "quantity", "price")} for o in
                    PERSIST.MongoDBConnector().find_unremoved_orders()]))

    def stop(self):
        self.should_die.set()
        log.info("Should die flag was set.")

    def terminate(self):
        pass

    @staticmethod
    def send_prevent(body_dict, unused_properties=None):
        """Does not send a message. This method is used for exchanges
           that are not allowed to act.
        """

        log.warning("attempt to send a message for a not configured/ not initialized exchange: %s", body_dict)

    def new_autotrader(self):
        self.autotrader_core = autotrader_core.api.AutoTrader(config=self.at_config,
                                                              is_parent=self.is_parent)

        log.info("Autotrader core initialized")
        return self.autotrader_core
