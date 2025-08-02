from __future__ import absolute_import
import collections
import datetime as DT
import logging
import pprint
import subprocess
import sys
import time
import copy

import autotrader_core.autotrader_core_main_base as ACMB
import autotrader_core.exchanges as APIEXCH
import autotrader_lib.common as COMMON
import autotrader_core.persistence as PERSIST
import autotrader_core.exchange_simulator as ATSIM
import autotrader_lib
import autotrader_lib.adapters.connection_manager_adapter as CMA
import autotrader_lib.adapters.exchange_feed_adapter as EFA
import autotrader_lib.adapters.readonly_simulation_adapter as ROSA
import autotrader_lib.adapters.parent_to_children_adapter as PTCA
import autotrader_lib.adapters.periotheus_adapter as PA
import autotrader_lib.log
import autotrader_lib.util
from six.moves import range

log = logging.getLogger("autotrader")


class AutotraderCoreMainParent(ACMB.AutotraderCoreMainBase):
    """This class holds the main entry point for the autotrader core executable for the parent process.

    It acts on the given configuration, instantiates the autotrader core and connects it to the outside world using
    various adapters. It also holds the main loop driving the autotrader.
    """
    _num_allowed_restart_attempts = 5

    def __init__(self, at_config, mongo_config, epex_config, epex_manager_config,
                 nordpool_config, nordpool_manager_config, trayport_config, trayport_manager_config):
        """

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

        super(AutotraderCoreMainParent, self).__init__(True, at_config, mongo_config, epex_config, epex_manager_config,
                                                       nordpool_config, nordpool_manager_config, trayport_config,
                                                       trayport_manager_config)

        # stores the pid of the child process for a strategy. dict[int, subprocess.Popen]
        self._child_processes = {}
        # store child ids that are not fully initialized yet. list[int]
        self._uninitialized_child_ids = []
        # store child_ids that do not have the exchange fully initialized
        self._exchange_restart_pending_children = dict()  # key: exchange, value: list of children.
        # Store the sequence number of restarts for an exchange key: exchange, value: int of the most recent restart
        self._active_exchange_restarts_id = collections.defaultdict(int)

        # Store for each exchange a list of times when it was restarted
        self._active_exchange_restarts_times = collections.defaultdict(
            lambda: collections.deque(maxlen=self._num_allowed_restart_attempts))
        self._allowed_restart_period = DT.timedelta(hours=1)

        self._fully_initialized = False

        # keep track of exchanges becoming (un)initialized
        self._last_exchange_init_state = collections.defaultdict(lambda: False)

        # spawn child processes
        self._spawn_children(self.at_config.num_child_processes)

    def _init_adapters(self):
        parent_to_child_adapter = PTCA.ParentToChildrenAdapter(log=log,
                                                               on_message_callback=self._on_child_msg,
                                                               at_config=self.at_config,
                                                               sockets=self.sockets)
        self.adapters[COMMON.Exchange.children] = parent_to_child_adapter

        self.adapters[COMMON.Exchange.periotheus] = PA.PeriotheusAdapter(log,
                                                                         self._handle_internal_request_callback,
                                                                         self.at_config,
                                                                         self.sockets)

        self.autotrader_core.send_to_children = self._forward
        self.autotrader_core.send_to_pt = self.adapters[COMMON.Exchange.periotheus].send

    def _periodic_tasks_slow(self, now):
        super(AutotraderCoreMainParent, self)._periodic_tasks_slow(now)
        if self.at_config.backtesting:
            backtesting_complete = [adapter.connection_manager_adapter.backtesting_simulation_complete for adapter in
                                    self.adapters.values() if hasattr(adapter, "connection_manager_adapter")]
            if backtesting_complete and all(backtesting_complete):
                log.warning("All backtesting simulations completed. Stopping")
                self.stop()
        if now >= self.next_heartbeat_unix_ts:
            self.emit_heartbeat()
            self.next_heartbeat_unix_ts = now + self.at_config.heartbeat_interval_sec
        if now >= self.next_nagios_unix_ts:
            self.update_nagios_files(now)

    def _periodic_tasks_fast(self, now):
        """Periodic tasks only executed by the parent process"""
        super(AutotraderCoreMainParent, self)._periodic_tasks_fast(now)
        self._check_children_state()

    def _after_receive_from_adapters_hook(self):
        if not self._uninitialized_child_ids and not self._fully_initialized:
            # initialize exchanges after all children are spawned
            self._init_after_all_children_are_alive()

        # check if the exchange initialized status changed and forward that information to the children
        for exchange in self.autotrader_core.all_exchanges:
            cur_initialized = self.autotrader_core.is_exchange_initialized(exchange)
            if cur_initialized and not self._last_exchange_init_state[exchange.internal_id]:
                # exchange became active
                self._forward(dict(message_type=COMMON.ParentChildMessages.exchange_initialized,
                                   exchange_id=exchange.internal_id))
            self._last_exchange_init_state[exchange.internal_id] = cur_initialized

    def _exchange_restart_required_detected(self, exchange_id):

        exchange = self.autotrader_core.get_exchange(exchange_id)
        is_initialized = exchange.init_files_ready()

        current_time = DT.datetime.utcnow()
        exchange_restart_times = self._active_exchange_restarts_times[exchange_id]
        historic_restart_time = exchange_restart_times[-self._num_allowed_restart_attempts] \
            if len(exchange_restart_times) >= self._num_allowed_restart_attempts else None

        if (historic_restart_time is not None
                and current_time - historic_restart_time <= self._allowed_restart_period
                and is_initialized):
            log.critical("Attempted to restart exchange: %s, "
                         "more then maximum allowed times: %s within the time period: %s, halting!",
                         exchange_id, self._num_allowed_restart_attempts, str(self._allowed_restart_period))
            log.debug("The restarts in the last period happened with timestamps: %s", exchange_restart_times)
            log.info("Resetting the exchange_restart_times since a manual un-halt is required next")
            self._active_exchange_restarts_id[exchange_id] = 0
            self._active_exchange_restarts_times[exchange_id] = collections.deque(
                maxlen=self._num_allowed_restart_attempts)
            self._stop_exchange(exchange,
                                remove_orders=True,
                                reason="Too many restart attempts in a small period of time",
                                critical=True,
                                username=COMMON.PeriotheusSystemUsers.autotrader)
            return

        self._restart_exchange(exchange.internal_id, current_time, is_initialized)

    def _restart_exchange(self, exchange_id, current_time, is_initialized):
        """
        Restarts exchange on parent and children

        :param exchange_id: exchange id
        :type exchange_id: str
        :param current_time: time
        :type current_time: datetime.datetime
        """
        old_exchange = self.autotrader_core.get_exchange(exchange_id)
        if not isinstance(old_exchange, APIEXCH.NullExchange):
            if exchange_id in [COMMON.Exchange.trayport, COMMON.Exchange.epex]:  # Nordpool has no delete_all request
                log.debug("Sending a delete_all request to exchange %s before restarting the exchange", exchange_id)
                old_exchange.send(old_exchange.delete_all_orders())
            if exchange_id == COMMON.Exchange.trayport:
                # Send a relogin_request to JD conmgr, this unsubscribes from all topics so during exchange restart
                # the queue is not overflown with messages.
                # This message should not be sent to NullExchange to prevent warning log
                old_exchange.send({"message_type": COMMON.TrayportRequest.relogin})

        self._replace_exchange(exchange_id)

        current_restart_id = self._active_exchange_restarts_id[exchange_id] + 1
        self._active_exchange_restarts_id[exchange_id] = current_restart_id
        if is_initialized:
            self._active_exchange_restarts_times[exchange_id].append(current_time)
            log.debug("Appending current timestamp to self._active_exchange_restart_times,"
                      " now: %s", self._active_exchange_restarts_times[exchange_id])
        log.info("Restarting the exchange %s (initialized=%s) for the %s time, with the timestamp: %s!",
                 exchange_id, is_initialized, current_restart_id, current_time)

        # Wait for all children's exchange restart
        if exchange_id in COMMON.Exchange.get_external():
            self._exchange_restart_pending_children[exchange_id] = copy.copy(
                self.at_config.child_id_per_exchange[exchange_id]
            )
        else:
            self._exchange_restart_pending_children[exchange_id] = list(self._child_processes.keys())
        self._forward(dict(message_type=COMMON.ParentChildMessages.begin_exchange_restart,
                           exchange_id=exchange_id,
                           current_restart_id=current_restart_id))

    def _after_children_exchange_restarted(self, exchange_id):
        """
        This is called once all children have (re)started the exchange
        and means we can start exchange communication.

        We do not communicate with the exchange until all children have (re)started the exchange.
        :param exchange_id:
        :type exchange_id: str
        :return:
        :rtype:
        """
        send_func = self.adapters[exchange_id].send
        exchange = self.autotrader_core.get_exchange(exchange_id)
        exchange.send_func = send_func
        log.info("Initializing exchange %s", exchange.internal_id)
        exchange.initialize()

    def _on_child_msg(self, unused_adapter, message):
        child_id = message.get("child_id", "unknown")
        log.debug("Received message from child %s: %s", child_id, message)
        message_type = message.get("message_type")

        if message_type == COMMON.ParentChildMessages.child_initialized:
            if child_id in self._uninitialized_child_ids:
                self._uninitialized_child_ids.remove(child_id)
            log.info("Child process %s initialized", child_id)

        elif message_type == COMMON.ParentChildMessages.child_request_exchange_restart:
            if not self._exchange_restart_pending_children[message["exchange_id"]]:
                self._exchange_restart_required_detected(message["exchange_id"])

        elif message_type == COMMON.ParentChildMessages.exchange_restarted:
            exchange_id = message["exchange_id"]
            message_restart_id = message["current_restart_id"]
            # ignore any messages from restarts which are not the most recent
            if message_restart_id != self._active_exchange_restarts_id[exchange_id]:
                log.debug("Ignoring an old exchange restarted message for exchange %s with restart id %s",
                          exchange_id, message_restart_id)
                return

            if child_id in self._exchange_restart_pending_children[exchange_id]:
                self._exchange_restart_pending_children[exchange_id].remove(child_id)

            if not self._exchange_restart_pending_children[exchange_id]:
                # All children have restarted the exchange
                self._after_children_exchange_restarted(exchange_id)

        elif message_type == COMMON.ParentChildMessages.strategy_stop:
            self.autotrader_core.send_to_pt(message, want_reply=False, properties={})

        elif message_type == COMMON.ParentChildMessages.exchange_halt:
            exchange = self.autotrader_core.get_exchange(message["exchange_id"])
            # Exchange halts triggered by the child are always critical, and the user is always autotrader.
            # User-halts via REST-API always origin at the parent.
            exchange.stop_exchange(reason=message["data"][0]["reason"],
                                   timestamp=message["data"][0]["timestamp"],
                                   remove_orders=message["data"][0].get("remove_orders", True),
                                   critical=True,
                                   username=COMMON.PeriotheusSystemUsers.autotrader)
            self._forward(message)

        elif message_type == COMMON.ParentChildMessages.trading_halt:
            data = message["data"][0]
            username = COMMON.PeriotheusSystemUsers.get_username_from_obj(data, "halting_user")
            self.autotrader_core.stop_trading(critical=data["critical"], reason=data["reason"],
                                              remove_orders=data.get("remove_orders", True),
                                              username=username)
            self._forward(message)

        elif message_type == COMMON.ParentChildMessages.strategy_request:
            self.autotrader_core.update_from_strategy_request(message)
        else:
            log.warning("Unknown message type received on parent.")

    def _init_after_all_children_are_alive(self):
        """Called once all the children are ready. Initializes communication with the exchanges."""
        if self._fully_initialized:
            log.error("Trying to initialize exchange adapters twice")
            return

        log.info("All children ready, starting full initialization")

        self._fully_initialized = True

        if self.at_config.epex:
            self._init_exchange_adapter(COMMON.Exchange.epex,
                                        self.at_config.epex_conmgr_host,
                                        self.epex_manager_config,
                                        self.epex_config.read_only)

        if self.at_config.nordpool:
            self._init_exchange_adapter(COMMON.Exchange.nordpool,
                                        self.at_config.nordpool_conmgr_host,
                                        self.nordpool_manager_config,
                                        self.nordpool_config.read_only)
        if self.at_config.trayport:
            self._init_exchange_adapter(COMMON.Exchange.trayport,
                                        self.at_config.trayport_conmgr_host,
                                        self.trayport_manager_config,
                                        self.trayport_config.read_only)

        if self.at_config.backtesting:
            self.start_simulation_time = min(adapter.connection_manager_adapter.start_simulation_time
                                             for adapter in self.adapters.values()
                                             if isinstance(adapter, ROSA.ReadonlySimAdapter))
            self.init_walltime = time.time()
            self._forward(dict(message_type=COMMON.ParentChildMessages.backtesting_start,
                               start_simulation_time=self.start_simulation_time,
                               init_walltime=self.init_walltime,
                               exchange=COMMON.Exchange.autotrader))

    def _init_exchange_adapter(self, exchange_id, conmgr_host, manager_config, read_only):
        """
        Instantiate an adapter for the given exchange based on the configuration, and store it in self.adapters

        :param exchange_id: The id of the exchange, one of COMMON.Exchange
        :type exchange_id: string
        :param conmgr_host: The connection manager host from ATConfig.
                            Typically localhost or the name of the docker container.
        :type conmgr_host: string
        :param manager_config: The connectionmanager config ()
        :type manager_config: autotrader_lib.config_helper.ManagerConfig
        :param read_only: True if the connection-manager should connect in read-only mode
        :type read_only: bool
        """
        if self.at_config.backtesting:
            # In backtesting mode, we do not connect to a connection manager, but instead to an exchange-feed file
            # from which we read the exchange messages...
            exchange_adapter = EFA.ExchangeFeedAdapter(log,
                                                       manager_config.exchangefeed_file,
                                                       self.at_config.playback_speed)
        else:
            exchange_adapter = CMA.ConnectionManagerAdapter(
                log,
                exchange_id,
                self._core_update_from_json_callback,
                conmgr_host,
                manager_config,
                self.sockets,
                read_only or self.at_config.simulation_mode or manager_config.simulation_mode,
                manager_timeout_sec=self.at_config.manager_timeout_sec)
        if self.at_config.simulation_mode or manager_config.simulation_mode or self.at_config.backtesting:
            if hasattr(manager_config, "tp_initfile_directory"):
                init_dir = manager_config.tp_initfile_directory
            else:
                init_dir = None
            exchange_simulator = ATSIM.ExchangeSimulator(self.autotrader_core,
                                                         exchange_id,
                                                         trayport_init_directory=init_dir)
            self.adapters[exchange_id] = ROSA.ReadonlySimAdapter(log,
                                                                 exchange_simulator,
                                                                 exchange_adapter,
                                                                 self._core_update_from_json_callback,
                                                                 self.at_config.backtesting)
            log.warning("%s Adapter for simulation/ backtesting mode initialized", exchange_id)
        else:
            self.adapters[exchange_id] = exchange_adapter

    def emit_heartbeat(self):
        self.sockets.status_publisher.send_string(DT.datetime.utcnow().strftime("%Y%m%dT%H:%M:%S.%fZ"))

    def update_nagios_files(self, now):

        if not self.autotrader_core.critical_halt:
            autotrader_lib.util.touch_nagios_file(self.at_config.nagios)
            self.next_nagios_unix_ts = now + self.at_config.nagios_interval_sec
        if self.autotrader_core.is_persistence_initialized():  # mongo
            autotrader_lib.util.touch_nagios_file(self.at_config.nagios_init_pt)
            self.next_nagios_unix_ts = now + self.at_config.nagios_interval_sec
        if self.autotrader_core.is_epex_initialized() and not self.autotrader_core.epex.critical_exchange_halt:
            autotrader_lib.util.touch_nagios_file(self.at_config.nagios_init_epex)
            self.next_nagios_unix_ts = now + self.at_config.nagios_interval_sec
        if self.autotrader_core.is_nordpool_initialized() and not self.autotrader_core.nordpool.critical_exchange_halt:
            autotrader_lib.util.touch_nagios_file(self.at_config.nagios_init_nordpool)
            self.next_nagios_unix_ts = now + self.at_config.nagios_interval_sec
        if self.autotrader_core.is_trayport_initialized() and not self.autotrader_core.trayport.critical_exchange_halt:
            autotrader_lib.util.touch_nagios_file(self.at_config.nagios_init_trayport)
            self.next_nagios_unix_ts = now + self.at_config.nagios_interval_sec

    def kill_all_child_processes(self):
        """Terminate all child processes"""
        log.info("Killing all child processes")
        alive_children = list(self._child_processes.values())
        for proc in alive_children:
            proc.poll()
            if proc.returncode is None:
                proc.terminate()

        # give the children 5 seconds to shut down cleanly
        for _i in range(50):
            alive_left = []
            for proc in alive_children:
                proc.poll()
                if proc.returncode is None:
                    alive_left.append(proc)
                else:
                    log.info("Child process %s terminated", proc.pid)
            alive_children = alive_left
            if not alive_children:
                break
            time.sleep(0.1)
        else:
            # then kill the ones still alive
            for proc in alive_children:
                log.warning("Killing child process %s with SIGKILL", proc.pid)
                proc.kill()

    def _spawn_children(self, number_of_child_processes):
        """Recreates all strategy child processes. Blocks until all children are up and running.
        """
        for child_id in range(number_of_child_processes):
            child_process = self._spawn_child(child_id)
            self._uninitialized_child_ids.append(child_id)
            self._child_processes[child_id] = child_process
        # All children's exchanges are uninitialized at the start.
        for exchange in self.autotrader_core.all_exchanges:
            if exchange.allowed:
                self._exchange_restart_pending_children[exchange.internal_id] = copy.copy(
                    self.at_config.child_id_per_exchange[exchange.internal_id]
                )
        log.debug("STARTUP: uninitialized exchanges: %s", self._exchange_restart_pending_children)

    def _spawn_child(self, child_id):
        """Spawns a new strategy child process with the given id

        :param child_id: ID of the newly spawned child
        :type child_id: int
        :return: A subprocess.Popen object for the new process
        :rtype: subprocess.Popen
        """
        # pass in executable and command line parameters from parent process, plus the child id
        child_call = [sys.executable] + sys.argv + ["--child_id", str(child_id)]
        # make the new process run in the background
        # if no stdout, stderr, stdin are passed in the process wil run in the background
        child_proc = subprocess.Popen(child_call, close_fds=True)
        log.info("Spawned new child process child_id=%s pid=%s", child_id, child_proc.pid)

        return child_proc

    def _core_update_from_json_callback(self, unused_adapter, data_dict):

        if data_dict["body"]["message_type"] == COMMON.Response.password_changed:
            # send message from parent to periotheus adapter/REST
            self.adapters[COMMON.Exchange.periotheus].send(data_dict["body"], False)

        elif self.autotrader_core.update_from_json(data_dict["body"], data_dict["properties"]):

            self._forward(data_dict)

    def _check_children_state(self):
        """Make sure child processes are still alive and restart them if necessary. Blocks until all children are up."""
        for child_id, child_process in self._child_processes.items():
            child_process.poll()
            if child_process.returncode is not None:
                # child process ended
                log.warning("Child {} exited with code {}, pid={}".format(
                    child_id, child_process.returncode, child_process.pid))
                # kill myself and child processes
                self.stop()
                break

    def _handle_internal_request_callback(self, message):
        """
        handle messages send from periotheus/rest to autotrader_parent
        """
        message_type = message["message_type"]
        if message_type == "emergency_halt_state_info":
            return self._handle_emergency_halt(message)
        if message_type == COMMON.Request.change_password:
            return self._handle_password_change(message)
        if self.autotrader_core:
            return self.autotrader_core.handle_request(message)
        else:
            log.warning("Received message from periotheus/ restapi before autotrader "
                        "is initialized: %s", pprint.pformat(message, depth=2, indent=0, width=1000000))

    def _handle_password_change(self, message):
        """
        Sends message for a password change request to a specific exchange defined in the message.

        :param message: message to be sent to the respective exchange adapter
        :type message: dict
        :rtype: None
        """
        exchange_id = message['body'].get("exchange")
        log.debug("Password change request received for Exchange: %s . Forwarding request to Exchange", exchange_id)
        if exchange_id not in self.adapters:
            log.error("Cannot handle password change request. Exchange %s does not exist.", exchange_id)
        else:
            self.adapters[exchange_id].send(message)

    def _handle_emergency_halt(self, message):
        """Handles emergency halt request to immediately halt/activate autotrader or a specified exchange"""
        log.debug("Received message in _handle emergency halt: %s", message)
        halt_state_received = message["data"].get("is_halted", False)
        exchange_id = message["data"].get("exchange_id", None)
        remove_orders = message["data"].get("remove_orders", True)
        username = COMMON.PeriotheusSystemUsers.get_username_from_obj(message["data"], "halting_user")
        reply = {"exchange": COMMON.Exchange.autotrader,
                 "timestamp": int(time.time()),
                 "message_type": "status_info",
                 "data": dict()}
        user_disconnected = message["data"].get("user_disconnected", False)
        reason = (COMMON.HaltReasonAutotrader.USER_DISCONNECTED
                  if user_disconnected else COMMON.HaltReasonAutotrader.HALTED_BY_USER_ORDERS_REMOVED
                  if remove_orders else COMMON.HaltReasonAutotrader.HALTED_BY_USER_ORDERS_NOT_REMOVED)
        if exchange_id is None:  # autoTRADER
            if halt_state_received:
                self._stop_trading(critical=False, reason=reason, remove_orders=remove_orders, username=username)
            else:
                self.autotrader_core.start_trading(username=username)
                parent_child_message = dict(exchange_id=COMMON.Exchange.autotrader,
                                            message_type=COMMON.ParentChildMessages.trading_resume,
                                            data=[{"halting_user": username}])
                self._forward(parent_child_message)

            log.debug("message_type: %s: Setting Autotrader and Strategy 'halted' flags to: %s",
                      message["message_type"], self.autotrader_core.halted)
            reply["data"] = dict(is_running=not self.autotrader_core.halted)
        else:
            exchange = self.autotrader_core.get_exchange(exchange_id.upper())
            if isinstance(exchange, APIEXCH.NullExchange):
                log.warning("message_type: %s: Attempt to halt/resume an uninitialized exchange %s",
                            message.get("message_type", "unknown"), exchange_id)
                reply["data"] = dict(is_running=None, exchange_id=exchange_id)
                return reply
            else:
                if halt_state_received:
                    self._stop_exchange(exchange, reason, remove_orders=remove_orders, critical=False,
                                        username=username)
                else:
                    unhalt_from_critical = exchange.critical_exchange_halt
                    exchange.start_exchange(username=username)
                    parent_child_message = dict(exchange_id=exchange.internal_id,
                                                message_type=COMMON.ParentChildMessages.exchange_resume,
                                                data=[])
                    self._forward(parent_child_message)
                    if unhalt_from_critical:
                        self._restart_exchange(exchange.internal_id, DT.datetime.utcnow(), exchange.init_files_ready())
                        exchange = self.autotrader_core.get_exchange(exchange_id.upper())
                reply["data"] = dict(is_running=not exchange.halted, exchange_id=exchange_id)
                log.debug("message_type: %s: Setting %s Exchange 'halted' flag to: %s",
                          message.get("message_type", "unknown"), exchange_id, exchange.halted)
        return reply

    def stop(self):
        # halt autotrader (which removes the orders from all exchanges)
        if not self.at_config.backtesting:
            self.stop_trading_on_restart()
        super(AutotraderCoreMainParent, self).stop()

    def run_until_condition(self):
        """Defines condition to break the while loop.
           If we are backtesting then exit the loop as soon as should_die is set
           If self.should_die is not set continue until it is set
           If self.should_ide is set (and we are not running a backtest) then we change condition to exit when there
           are no orders left of 30 seconds have elapsed.
        """

        if self.should_die.is_set() and not self.at_config.backtesting:
            return not self._wait_for_all_orders_removed()
        else:
            return not self.should_die.is_set()

    def _wait_for_all_orders_removed(self):
        if self.time_limit_to_die:
            return self._are_all_orders_removed() or time.time() > self.time_limit_to_die
        #  first time it gets called
        self.time_limit_to_die = time.time() + 30
        return self._are_all_orders_removed()

    def terminate(self):
        log.info("Stop was called on parent and will proceed with killing child processes")
        try:
            # First stop the writer thread, so queued autoTRADER status messages won't be written to the database.
            log.debug("closing persistence writer thread.")
            PERSIST.MongoDBConnector().stop()  # gracefully exit the persistence thread
            log.debug("closed persistence writer thread.")
            # Then update the status in the database
            PERSIST.MongoDBConnector().update_db_set_uninitialized()
        except Exception:
            log.exception("Could not set autotrader to uninitialized in persistence before shutdown")
        self.kill_all_child_processes()

    def _forward(self, message):
        """
        Forward the passed message to children

        :param message: The message that will be sent to the children.
        :type message: dict
        :rtype: None
        """
        self.adapters[COMMON.Exchange.children].send(message)

    def stop_trading_on_restart(self):
        """
        Halt autotrader. If autotrader was already halted we set halt_reason to the previous reason. If
        halt_reason was not set already we set it to "autoTRADER is being restarted".
        """
        halt_reason = self.autotrader_core.halt_reason or COMMON.HaltReasonAutotrader.RESTART_AT
        self._stop_trading(halt_reason, remove_orders=True, critical=self.autotrader_core.critical_halt,
                           username=COMMON.PeriotheusSystemUsers.system)
