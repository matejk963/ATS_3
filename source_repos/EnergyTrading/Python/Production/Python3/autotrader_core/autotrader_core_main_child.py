from __future__ import absolute_import

import datetime
import os
import time

import six

import autotrader_core.autotrader_core_main_base as ACMB
import autotrader_lib.common as COMMON
import autotrader_core.exchanges as EXCH
import autotrader_core.persistence as PERSIST
import autotrader_core.utils as UTIL
import autotrader_lib.adapters.child_to_parent_adapter as CTPA
import autotrader_lib.adapters.persistence_adapter as PEA
import autotrader_lib.config_helper as ATCONF

if six.PY2:
    import autotrader_lib.fast_logging_py2 as FLOG
else:
    import autotrader_lib.fast_logging_py3 as FLOG

import autotrader_lib.compliance_log_templates as LOGTEMP

log = FLOG.getLogger("autotrader")


class AutotraderCoreMainChild(ACMB.AutotraderCoreMainBase):
    """This class holds the main entry point for the autotrader core executable for child processes.

    It acts on the given configuration, instantiates the autotrader core and connects it to the outside world using
    various adapters. It also holds the main loop driving the autotrader.
    """

    def __init__(
            self,
            child_id,  # type: int
            at_config,  # type:  ATCONF.ATConfig
            mongo_config,  # type:  ATCONF.MongoConfig
            epex_config,  # type: ATCONF.EpexConfig
            epex_manager_config,  # type: ATCONF.ManagerConfig
            nordpool_config,  # type: ATCONF.NordpoolConfig
            nordpool_manager_config,  # type: ATCONF.ManagerConfig
            trayport_config,  # type: ATCONF.TrayportConfig
            trayport_manager_config,  # type: ATCONF.TrayportManagerConfig
    ):
        """

        :param child_id: ID of this child process
        :type child_id: int
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

        self.child_id = child_id

        super(AutotraderCoreMainChild, self).__init__(False, at_config, mongo_config, epex_config, epex_manager_config,
                                                      nordpool_config, nordpool_manager_config, trayport_config,
                                                      trayport_manager_config)
        self.autotrader_core.child_id = child_id
        self.parent_process_id = None
        self._establish_initial_parent_id()
        self._exchange_restart_requested = set()

        # inform parent that the process is ready now
        self._forward(dict(message_type=COMMON.ParentChildMessages.child_initialized))
        log.info("Initialization message sent to parent from child %s", self.child_id)

    def _init_adapters(self):
        child_to_parent_adapter = CTPA.ChildToParentAdapter(log=log,
                                                            on_message_callback=self._on_parent_msg,
                                                            at_config=self.at_config,
                                                            sockets=self.sockets,
                                                            child_id=self.child_id)
        self.adapters[COMMON.Exchange.parent] = child_to_parent_adapter

        persistence_adapter = PEA.PersistenceAdapter(log=log,
                                                     persistence=PERSIST.MongoDBConnector(),
                                                     on_message_callback=self._core_update_from_persistence_callback,
                                                     on_change_callback=self._on_change_message)

        self.adapters[COMMON.Exchange.persistence] = persistence_adapter

        self.autotrader_core.send_to_parent = self._forward

    def _periodic_tasks_slow(self, now):
        super(AutotraderCoreMainChild, self)._periodic_tasks_slow(now)

        # check if the parent is dead (by the process ID not existing)
        if not UTIL.pid_exists(self.parent_process_id):
            log.error("The parent process (with the PID: %s) has died. Stopping child %s with the PID: %s",
                      self.parent_process_id, self.child_id, os.getpid())
            self.stop()

    def _exchange_restart_required_detected(self, exchange_id):
        # if a child detects on its own that an exchange needs to be restarted,
        # it has to inform the parent, because
        # exchange restarts can only be performed by the parent

        self._forward(dict(message_type=COMMON.ParentChildMessages.child_request_exchange_restart,
                           exchange_id=exchange_id))

        # mark that this exchange is in the process of being restarted so that messages can be ignored
        self._exchange_restart_requested.add(exchange_id)

        # Invalidate the old exchange and replace it by a
        # temporary exchange until the true restart triggered by a parent message.
        self._replace_exchange(exchange_id)

    def _establish_initial_parent_id(self):
        if self.parent_process_id is None:
            log.info("Established parent id: %s", self.parent_process_id)
            self.parent_process_id = os.getppid()

    def _on_parent_msg(self, adapter, message):
        """Called when a message from the parent process is received"""
        message_type = message.get("message_type")

        if message_type:
            log.debug("Received message from parent on child %s, type: %s", self.child_id, message_type)

        # try and get the exchange id, if its not in the first level, try to extract it from the body
        message_exchange_id = message.get("exchange_id")
        if message_exchange_id is None and "body" in message and isinstance(message["body"], dict):
            message_exchange_id = message["body"].get("exchange")

        # ignore messages from an exchange which is in the process of being restarted
        if message_exchange_id in self._exchange_restart_requested \
                and not message_type == COMMON.ParentChildMessages.begin_exchange_restart:
            if not message_type:
                message_type = message.get("body", dict()).get("message_type")
            log.debug("Exchange %s is in the process of restarting. Message %s was ignored.",
                      message_exchange_id, message_type)
            return

        if message_type == COMMON.ParentChildMessages.exchange_initialized:
            # the parent has fully initialized the exchange. whatever we have in our correlation ids array is
            # thus void. => manually mark the exchange as initialized by setting all correlation ids to True
            exchange = self.autotrader_core.get_exchange(message_exchange_id)
            for ci in exchange.init_files_correlation_ids:
                exchange.init_files_correlation_ids[ci] = True
            if isinstance(exchange, EXCH.Trayport):
                exchange.update_synthetic_products(self.autotrader_core.current_timestamp)
        elif message_type == COMMON.ParentChildMessages.begin_exchange_restart:
            self._handle_exchange_restart(message)
        elif message_type == COMMON.ParentChildMessages.exchange_halt:
            exchange = self.autotrader_core.get_exchange(message_exchange_id)
            remove_orders = message["data"][0].get("remove_orders", True)
            username = COMMON.PeriotheusSystemUsers.get_username_from_obj(message["data"][0], "halting_user")
            exchange.stop_exchange(reason=message["data"][0]["reason"],
                                   timestamp=message["data"][0]["timestamp"],
                                   remove_orders=remove_orders,
                                   username=username)
            self.autotrader_core.call_strategies_on_at_or_exchange_halt(remove_orders=remove_orders,
                                                                        exchange=exchange)
        elif message_type == COMMON.ParentChildMessages.exchange_resume:
            exchange = self.autotrader_core.get_exchange(message_exchange_id)
            exchange.start_exchange(username=COMMON.PeriotheusSystemUsers.autotrader)
            self.autotrader_core.call_strategies_on_at_or_exchange_halt(remove_orders=False,
                                                                        exchange=exchange)
        elif message_type == COMMON.ParentChildMessages.trading_halt:
            data = message["data"][0]
            username = COMMON.PeriotheusSystemUsers.get_username_from_obj(data, "halting_user")
            self.autotrader_core.stop_trading(critical=data["critical"], reason=data["reason"],
                                              remove_orders=data.get("remove_orders", True),
                                              username=username)
        elif message_type == COMMON.ParentChildMessages.trading_resume:
            username = COMMON.PeriotheusSystemUsers.unset
            if message.get("data") is not None and len(message["data"]) > 0:
                username = COMMON.PeriotheusSystemUsers.get_username_from_obj(message["data"][0], "halting_user")
            self.autotrader_core.start_trading(username=username)
        elif message_type == COMMON.ParentChildMessages.backtesting_start:
            self.start_simulation_time = message["start_simulation_time"]
            self.init_walltime = message["init_walltime"]
        elif message_type in COMMON.Response.internal_messages:
            self.autotrader_core.update_from_json(message, {})
        else:
            self.autotrader_core.update_from_json(message["body"], message["properties"])

    def _handle_exchange_restart(self, message):
        exchange_id = message["exchange_id"]
        self._replace_exchange(exchange_id)

        # mark the restaring process complete if requested by child
        if exchange_id in self._exchange_restart_requested:
            self._exchange_restart_requested.remove(exchange_id)

        exchange = self.autotrader_core.get_exchange(exchange_id)  # The new, replaced exchange
        # make it obvious that the child process is waiting for the parent's exchange initialized message
        exchange.init_files_correlation_ids["received_exchange_initialized"] = False
        self._forward(dict(message_type=COMMON.ParentChildMessages.exchange_restarted,
                           exchange_id=exchange_id,
                           current_restart_id=message["current_restart_id"]))

    def _on_change_message(self, change_message):
        """processes the change message according to its type"""
        change_object_type = change_message.get("object_type", None)
        change_object_child_id = change_message.get("child_id", None)
        try:
            change_message_int_num = change_message["internal_number"]
        except KeyError:
            if change_object_type in [
                COMMON.MongoDBObjects.strategy,
                COMMON.MongoDBObjects.strategy_configuration, COMMON.MongoDBObjects.strategy_steering,
                COMMON.MongoDBObjects.per_product_limits, COMMON.MongoDBObjects.dump_strategy_request,
                COMMON.MongoDBObjects.synthetic_order
            ]:
                raise
            change_message_int_num = None

        # accept only messages intended for this child
        if change_object_child_id is not None and change_object_child_id != self.child_id:
            # if it's a strategy update message, and there is remainder of this strategy on this child, we delete it
            if change_object_type in [COMMON.MongoDBObjects.strategy, COMMON.MongoDBObjects.strategy_configuration] \
               and change_message_int_num in self.autotrader_core.strategies:
                log.warning("Strategy object {} will be deleted on child {}, because it's configured on child {}"
                            .format(change_message_int_num, self.child_id, change_object_child_id))
                del self.autotrader_core.strategies[change_message_int_num]
            return

        # if child_id is correct, there are more cases based on change_object_type
        if change_object_type in [COMMON.MongoDBObjects.strategy,
                                  COMMON.MongoDBObjects.strategy_configuration]:
            for exchange_key in ["exchange", "exchange_1"]:
                exchange = change_message.get(exchange_key)
                if exchange and exchange not in self.at_config.child_exchange_distribution[self.child_id]:
                    log.debug("Received mongodb message for {} exchange {}, but it is not configured on child {}"
                              .format(change_message.get("_id", None), exchange, self.child_id))
                    return

            # we check if a strategy is known by the child. If its deleted, it will be removed in
            # _core_update_from_persistence_callback from the self.autotrader_core.strategies and should trigger
            # a compliance log message.
            strategy_known_to_child = change_message_int_num in self.autotrader_core.strategies
            self._core_update_from_persistence_callback(strategy_id=change_message_int_num,
                                                        message=change_message)
            if strategy_known_to_child and change_message_int_num not in self.autotrader_core.strategies:
                log.compliance_log(log_entry=LOGTEMP.StrategyBasicLogs.strategy_deleted,
                                   username=COMMON.PeriotheusSystemUsers.get_username_from_obj(
                                       change_message, "username"),
                                   strategy_id=change_message_int_num)
            log.debug("Received StrategyObject from persistence. type: %s, internal_number: %s",
                      change_object_type, change_message_int_num)

        elif change_object_type == COMMON.MongoDBObjects.market_state_timeseries:
            exchange_name = change_message.get("exchange", None)
            self._update_market_state(change_message, exchange_name)
            log.debug("Received MarketState from persistence with %s values.",
                      len(change_message["values"]) if "values" in change_message else "missing key for")

        elif (change_object_type == COMMON.MongoDBObjects.strategy_steering
                and change_message_int_num in self.autotrader_core.strategies
                and self._is_msg_current(change_message)):
            if change_message.get("halt_or_resume"):
                response = self.autotrader_core.handle_strategy_halt(strategy_id=change_message_int_num,
                                                                     message=change_message["payload"])
            else:
                response = self._core_update_from_persistence_callback(strategy_id=change_message_int_num,
                                                                       message=change_message["payload"])
            if response is None:
                response = {"ok": True}
            self._send_response_to_mongo(object_type=COMMON.MongoDBObjects.strategy_steering,
                                         strategy_id=change_message_int_num,
                                         response=response,
                                         affiliated_request_hash=change_message["request_hash"])

            # log the response and internal number of the StrategySteering
            log.debug("received %s from persistence. Message internal number: %s, Result: %s",
                      COMMON.MongoDBObjects.strategy_steering, change_message_int_num, response)
            if not self._is_msg_current(change_message):
                # This process could in theory hang between _core_update_from_json
                # and _send_steering_response_to_mongo. In this case the REST-API could have reported a timeout.
                log.warning("Strategy steering call from %s was accepted while it timed out."
                            "The REST-API might have reported a timeout instead of an OK.",
                            change_message["alteration_time"])

        elif (change_object_type == COMMON.MongoDBObjects.per_product_limits
                and change_message_int_num in self.autotrader_core.strategies
                and self._is_msg_current(change_message)):
            response = self.autotrader_core.update_strategy_limits(strategy_id=change_message_int_num,
                                                                   message=change_message["payload"],
                                                                   overwrite_limits=change_message["overwrite_limits"])
            self._send_response_to_mongo(object_type=COMMON.MongoDBObjects.per_product_limits,
                                         strategy_id=change_message_int_num,
                                         response=response,
                                         affiliated_request_hash=change_message["request_hash"])

        elif change_object_type == COMMON.MongoDBObjects.dump_strategy_request and self._is_msg_current(change_message):
            self._send_state_dump_to_database(change_message["_id"], change_message_int_num)

        elif (change_object_type == COMMON.MongoDBObjects.synthetic_order
                and change_message_int_num in self.autotrader_core.strategies
                and self._is_msg_current(change_message)):
            response = self.autotrader_core.on_synthetic_order(strategy_id=change_message_int_num,
                                                               payload=change_message["payload"])
            if response is None:
                response = {"ok": True}
            self._send_response_to_mongo(COMMON.MongoDBObjects.synthetic_order,
                                         strategy_id=change_message_int_num,
                                         response=response,
                                         affiliated_request_hash=change_message["request_hash"])

    @staticmethod
    def _is_msg_current(change_message):
        """
        Returns True, if the message has not timed out and has not been answered

        :param change_message: Should have the field "alteration_time"
        :type change_message: dict
        """
        alteration_time = change_message["alteration_time"]
        timedelta = datetime.timedelta(seconds=COMMON.REST_API_TIMEOUT)
        if alteration_time < datetime.datetime.utcfromtimestamp(time.time()) - timedelta:
            if "payload" in change_message:
                # Depending on the customer, the payload can be huge, so remove it from the log.
                change_message["payload"] = "[...]"
            log.warning("Message from mongoDB is expired: %s", change_message)
            return False
        if "response" in change_message:
            # When we put a response into the DataBase, the PersistenceAdapter
            # notices the alteration of the object and queues it again.
            # In this case, we can ignore the message.
            return False
        return True

    def _update_market_state(self, change_message, exchange_name):
        exchange = self.autotrader_core.get_exchange(exchange_name)
        exchange.update_market_halt(change_message.get("values", None))

    def _send_state_dump_to_database(self, msg_id, strategy_id):
        """
        Add a response field with the strategy state-dump into the corresponding mongo-db document.

        :param msg_id: The _id value used in mongo-db. The corresponding document will be updated.
        :param strategy_id: The strategy to dump.
        :return: None
        """
        strategy = self.autotrader_core.strategies.get(strategy_id)
        if not strategy:
            # Do nothing, if strategy is on another child.
            return
        try:
            response = {strategy_id: six.moves.cPickle.dumps(strategy.dump_state())}
        except Exception:
            log.exception("Cannot correctly pickle strategy %s", strategy_id)
            response = {strategy_id: "ERROR"}

        log.debug("Sending state dump to database: %s for strategies %s", msg_id, list(response.keys()))
        self._respond_in_mongo(msg_id, response, upsert=False)

    def _send_response_to_mongo(self, object_type, strategy_id, response, affiliated_request_hash):
        """
        send the response for a given steering call / limit change to mongodb by
        updating the response field of the original steering object document

        :param object_type: Object type of the message to reply to. One of COMMON.MongoDBObjects
        :type object_type: str
        :param strategy_id: id of the strategy for which the message was
        :type strategy_id: str
        :param response: The response document
        :type response: dict
        :param affiliated_request_hash: Request hash of the message to which to respond
        :type affiliated_request_hash: str
        """
        msg_id = "{object_name}_{strategy_id}_{msg_hash}".format(object_name=object_type,
                                                                 strategy_id=strategy_id,
                                                                 msg_hash=affiliated_request_hash)
        self._respond_in_mongo(msg_id, response, upsert=True)

    @staticmethod
    def _respond_in_mongo(object_id, response, upsert):
        """
        Insert the key-value pair "response": response at the top-level of the database entry with the given object id

        :param object_id: The "_id" of the object to update
        :param response: The value to insert. Typically a dictionary.
        :param upsert: Bool. The upsert flag passed to `update_one`
        """
        PERSIST.MongoDBConnector().write_response_into_mongo(object_id=object_id, response=response, upsert=upsert)

    def _core_update_from_persistence_callback(self, strategy_id, message):
        return self.autotrader_core.update_strategy(strategy_id, message)

    def _forward(self, message):
        """
        Sends message to parent.

        :param message: message object
        :type message: dict
        """
        message.update(child_id=self.child_id)
        self.adapters[COMMON.Exchange.parent].send(message)
