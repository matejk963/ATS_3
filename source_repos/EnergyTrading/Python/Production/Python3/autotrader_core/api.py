#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""Core API of the autoTRADER Project

This module contains the classes neccesary to project all exchange activity
onto a python class tree. The classes contained include the parsing functions
for the json standard format for exchange communications.
"""
from __future__ import absolute_import
from __future__ import print_function
import collections
import datetime
import imp
import os
import os.path
import random
import sys
import time
import traceback

import autotrader_lib.common as COMMON
from autotrader_lib.common import Area, TradeFilter
import autotrader_lib.compliance_log_templates as LOGTEMP
import autotrader_core.exchange_trading as APITR
import autotrader_core.exchanges as APIEXCH
import autotrader_core.persistence as PERSIST
import autotrader_core.order_guard
import autotrader_core.simulation_data
import autotrader_core.strategy
import autotrader_core.utils as UTILS

import autotrader_lib._strategy_managing as SM
import autotrader_lib.cet_util as CETUTIL
import autotrader_lib.config_helper as ATCONF  # Needed by Pycharm typing - pylint: disable=W0611
import autotrader_lib.util as ALU
import autotrader_synthetic.synthetic_order_strategies.synthetic_order_strategy_base as SYSTRAT
import autotrader_synthetic.local_view as LV
import six
from six.moves import range

if six.PY2:
    import autotrader_lib.fast_logging_py2 as FLOG
else:
    import autotrader_lib.fast_logging_py3 as FLOG

__all__ = ["Area", "TradeFilter"]

log = FLOG.getLogger("autotrader.api")

DBG_CONDITION = APITR.dbg_condition


class AutoTrader(object):

    def __init__(self,
                 create_dummy_products=True,
                 config=None, use_own_strategies_folder=False, reraise_on_strategy_exception=False,
                 is_parent=True, child_id=None):
        # type: (bool, bool, ATCONF.ATConfig, bool, bool, bool, int) -> None

        self.strategies = dict()  # type: dict[str, autotrader_core.strategy.Strategy]
        self.current_timestamp = 0 if config and config.backtesting else time.time()
        self.initialization_timestamp = time.time()

        is_atconf = isinstance(config, ATCONF.ATConfig)
        ex_list = COMMON.Exchange.get_configured(config) if is_atconf else COMMON.Exchange.get_external()
        self.max_queue_lag = {ex: 0. for ex in ex_list}
        self.queue_lag = {ex: 0. for ex in ex_list}
        self.child_id = child_id

        # for the process autoTRADER - Import [1.11] to work, update_indicators_on_parent needs to be
        # activated in the system.cfg, to allow the calculation of the indicators on the parent.
        indicator_update = (config and config.update_indicators_on_parent) or not is_parent
        log.debug("Orderbook Indicator Status: is_parent: %s, update indicators: %s", is_parent, indicator_update)
        self.epex = APIEXCH.NullExchange(config.epex if config else False,
                                         internal_id=COMMON.Exchange.epex,
                                         indicator_update=indicator_update)  # type: APIEXCH.Epex
        self.nordpool = APIEXCH.NullExchange(config.nordpool if config else False,
                                             internal_id=COMMON.Exchange.nordpool,
                                             indicator_update=indicator_update)  # type: APIEXCH.NordPool
        self.trayport = APIEXCH.NullExchange(config.trayport if config else False,
                                             internal_id=COMMON.Exchange.trayport,
                                             indicator_update=indicator_update)  # type: APIEXCH.Trayport

        # default value in default config is 5 seconds. If we run on no config (simulations, tests),
        # deactivate by using very high value
        self.hwm_queue_lag = config.hwm_queue_lag if config and not config.backtesting else 10E10
        self.last_incoming_message_timestamp = 0.  # type: float
        self.halted = False  # emergency stop flag
        self.critical_halt = False
        self.halt_reason = ""
        self.remove_orders = True
        self.create_dummy_products = create_dummy_products
        self.use_own_strategies_folder = use_own_strategies_folder
        self.reraise_on_strategy_exception = reraise_on_strategy_exception

        now = time.time()
        self.last_ioc_cleanup_run = int(now)
        self._last_orderbook_cleanup_run = 0.  # As this has to work in simulation, we cannot use time.time here!

        self.external_log_container = collections.defaultdict(int)
        self.config = config
        self.is_parent = is_parent

        self.last_cleanup_run = now
        self.automatic_maintenance_time = datetime.datetime.fromtimestamp(now) + datetime.timedelta(days=1)
        if self.config:
            self._set_automatic_maintenance_time()

        self._initialization_states = dict()
        # this field is updated everytime we call self.update_db
        # Warning ! Do not rely on this field to know if the autotrader is initialized or not, instead use the
        # check_initialized function! This attribute is used in the persistence to reflect the state of the autotrader.
        self.initialized = None

        self.route = None
        self.configured_routes = None
        self._load_from_db()

    def __setattr__(self, key, value):
        # Allow to set only callables to the send_func attribute
        if key.startswith("send_to") and not callable(value):
            return
        super(AutoTrader, self).__setattr__(key, value)

    @property
    def keep_strategy_history(self):
        return self.config.keep_strategy_history if self.config else 0

    @staticmethod
    def send_to_pt(*unused_args, **unused_kwargs):
        """Function allowing to send messages to Periotheus"""
        return None

    @staticmethod
    def send_to_children(*unused_args, **unused_kwargs):
        """Function to send messages to all children"""
        return None

    @staticmethod
    def send_to_parent(*unused_args, **unused_kwargs):
        """Function to send messages to parent"""
        return None

    def send_to_active_exchanges(self, products_to_intmarket=None):
        products_to_intmarket_by_exchange = collections.defaultdict(list)
        if products_to_intmarket:
            for product in products_to_intmarket:
                products_to_intmarket_by_exchange[product.exchange].append(product)
        for exchange in self.all_active_exchanges:
            send_prod = products_to_intmarket_by_exchange.get(exchange.internal_id)
            self.send_to_exchange(exchange, send_prod)

    def _parent_send_to_exchange(self, exchange, orders_to_send):
        """Send orders to the exchange as parent.

        :param exchange: The exchange object the orders should be sent to
        :type exchange: APIEXCH.ExchangeBase
        :param orders_to_send: The orders that should be sent to the exchange
        :type orders_to_send: dict[str, list]
        """
        messages_to_send = []

        if self.halted or exchange.halted:
            # we allow only deletions of our own orders and nothing else
            # for epex we want to delete everything at once
            # here we do not want to remove comtrades orders, only orders from autotrader!
            orders_to_delete = [o for o in orders_to_send[COMMON.ResolverState.delete_orders] if o.portfolio_key]
            if isinstance(exchange, (APIEXCH.Epex, APIEXCH.Trayport)):
                # we send a "delete all" only if we had orders to delete in the first place
                if orders_to_delete:
                    # we actually do not use the list set here but we want to set the value to something else than
                    # the default []
                    log.debug("Converting order delete requests to an order_delete_all request, because %s is halted",
                              "autoTRADER" if self.halted else exchange.internal_id)
                    orders_to_send[COMMON.ResolverState.delete_all_orders] = orders_to_delete
                    messages_to_send.extend(
                        exchange.order_modify_chunking(
                            orders_to_send[COMMON.ResolverState.delete_all_orders], COMMON.Request.order_delete_all))
                    # we overwrite the order that we would be deleting individually
                    orders_to_send[COMMON.ResolverState.delete_orders] = []
            else:
                orders_to_send[COMMON.ResolverState.delete_orders] = orders_to_delete

        messages_to_send.extend(
            exchange.order_modify_chunking(
                orders_to_send[COMMON.ResolverState.delete_orders], COMMON.Request.order_delete))

        messages_to_send.extend(
            exchange.order_modify_chunking(
                orders_to_send[COMMON.ResolverState.delete_orders_for_locked_product], COMMON.Request.order_delete))

        if not (self.halted or exchange.halted):
            # do not send messages when halted
            messages_to_send.extend(
                exchange.order_modify_chunking(
                    orders_to_send[COMMON.ResolverState.modify_orders], COMMON.Request.order_modify))
            messages_to_send.extend(
                exchange.order_modify_chunking(
                    orders_to_send[COMMON.ResolverState.deactivate_orders], COMMON.Request.order_deactivate))
            messages_to_send.extend(
                exchange.order_modify_chunking(
                    orders_to_send[COMMON.ResolverState.activate_orders], COMMON.Request.order_activate))
            messages_to_send.extend(
                exchange.order_modify_chunking(
                    orders_to_send[COMMON.ResolverState.entry_orders], COMMON.Request.order_entry))
            messages_to_send.extend(
                exchange.trade_order_chunking(orders_to_send[COMMON.ResolverState.trade_orders]))

        for message in messages_to_send:
            log.debug("MODIFY %s", message)
            exchange.send(message)

        internal_at_messages = []
        # internal trade locks should be sent first, to ensure the product gets
        # locked before any other messages could unlock it
        if orders_to_send[COMMON.ResolverState.internal_trade_lock]:
            orders = orders_to_send[COMMON.ResolverState.internal_trade_lock]
            data = []
            for order in orders:
                quantity = broker_id = None
                for message in messages_to_send:
                    if (message["message_type"] == COMMON.TrayportRequest.trade_order
                            and message["data"][0]["txt"].startswith(order.internal_id)):
                        quantity = message["data"][0]["quantity"]
                        broker_id = message["data"][0]["broker_id"]
                data.append({"order_id": order.internal_id,
                             "product_id": order.product.product_id,
                             "timestamp": self.current_timestamp,
                             "broker_id": broker_id,
                             # For quantity, we need the tradeorder quantity for the trade_lock
                             "quantity": quantity})
            internal_at_messages.append(dict(exchange=exchange.internal_id,
                                             message_type=COMMON.Response.internal_trade_lock,
                                             data=data,
                                             timestamp=self.current_timestamp))
        if orders_to_send[COMMON.ResolverState.internal_order_executions]:
            internal_at_messages.append(dict(exchange=exchange.internal_id,
                                             message_type=COMMON.Response.internal_order_execution,
                                             data=orders_to_send[COMMON.ResolverState.internal_order_executions],
                                             timestamp=self.current_timestamp,
                                             route_id=self.route,
                                             ))
        if orders_to_send[COMMON.ResolverState.internal_trades]:
            internal_at_messages.append(dict(exchange=exchange.internal_id,
                                             message_type=COMMON.Response.internal_trade,
                                             data=orders_to_send[COMMON.ResolverState.internal_trades],
                                             timestamp=self.current_timestamp,
                                             route_id=self.route,
                                             ))
        if orders_to_send[COMMON.ResolverState.internal_order_reject]:
            orders = orders_to_send[COMMON.ResolverState.internal_order_reject]
            internal_at_messages.append(UTILS.internal_order_reject(exchange.internal_id,
                                                                    orders,
                                                                    exchange.internal_market.reject_reasons,
                                                                    self.current_timestamp))

        for message in internal_at_messages:
            # For simulation mode, it is important to first update the parent before updating the child.
            self.update_from_json(message, {})
            self.send_to_children(message)

    def _child_send_to_exchange(self, exchange, orders_to_send):
        """Send orders that should be processed to parent as child.

        :param exchange: The exchange object the orders should be sent to
        :type exchange: APIEXCH.ExchangeBase
        :param orders_to_send: The orders that should be sent to the exchange
        :type orders_to_send: dict[str, list]
        """
        data = [{order_types: [o.serialize() for o in orders]
                 for order_types, orders in orders_to_send.items()
                 if orders}]
        if any(data[0].values()):
            self.send_to_parent(dict(exchange=exchange.internal_id,
                                     message_type=COMMON.ParentChildMessages.strategy_request,
                                     data=data,
                                     timestamp=self.current_timestamp
                                     ))

    def send_to_exchange(self, exchange, products_to_intmarket=None):
        """Send the generated orders to the correct exchange or parent.

        :param exchange: The exchange object the orders should be sent to
        :type exchange: APIEXCH.ExchangeBase
        :param products_to_intmarket: products to be checked on the internal market even if the strategy does not
                                      request any actions Default: None
        :type products_to_intmarket: list
        """
        order_cache = getattr(exchange.modify_orders, "cache", None)
        if order_cache is None or (not order_cache() and not products_to_intmarket):
            return

        orders_to_send = exchange.resolve_order_conflicts(self.current_timestamp, products_to_intmarket, self.is_parent)

        if self.is_parent:
            self._parent_send_to_exchange(exchange, orders_to_send)
        else:
            self._child_send_to_exchange(exchange, orders_to_send)

    def get_exchange(self, name):
        """Get an exchange by name

        :param name: The name of the exchange as str or string-like or None
        :type name: str | None
        :return: The corresponding exchange object
        :rtype: APIEXCH.ExchangeBase
        """

        exchange_dict = {
            COMMON.Exchange.nordpool: self.nordpool,
            COMMON.Exchange.epex: self.epex,
            COMMON.Exchange.trayport: self.trayport
        }

        if name in exchange_dict:
            exchange = exchange_dict.get(name)
        elif isinstance(name, six.string_types) or name is None:
            log.warning("Trying to access non-existent exchange with name %s", name)
            exchange = APIEXCH.NullExchange(False, name)
        else:
            raise TypeError("get_exchange() called with non-string argument '{}'.".format(name))

        return exchange

    def log(self, level, title, message):
        """Place a log message in the global container for logs.

        The logs are pulled by Periotheus once a minute and placed into the
        Periotheus eventlog.

        :param level: Log level, "DEBUG", "INFO", "WARNING" or "ERROR"
        :param title: Title (short description)
        :param message: Message (longtext)
        :type level: str
        :type title: str
        :type message: str
        """
        self.external_log_container[(level, title, message)] += 1

    def _load_from_db(self):
        autotrader_state = PERSIST.MongoDBConnector().load_db_autotrader_state()
        if autotrader_state:
            self.halted = autotrader_state.get("halted", False)
            self.critical_halt = autotrader_state.get("critical_halt", False)
            self.halt_reason = autotrader_state.get("halt_reason", "")
            if self.halt_reason == COMMON.HaltReasonAutotrader.RESTART_AT:  # aT has restarted, unhalt it
                self.halted = False
                self.critical_halt = False
                self.halt_reason = ""
                history_fields = ["halted", "critical_halt", "halt_reason"]
                self.update_db(history_fields=history_fields)

            log.debug("Setting autotrader state from db: halted: %s, critical halt: %s, halt_reason: %s",
                      self.halted, self.critical_halt, self.halt_reason)

    def _set_automatic_maintenance_time(self):
        now = datetime.datetime.now()
        if self.config.automatic_maintenance_time:
            try:
                restart_timestamp = datetime.datetime.strptime(self.config.automatic_maintenance_time,
                                                               "%H:%M:%S").time()
            except ValueError:
                error_text = ("The format of automatic_maintenance_time parameter set in system.cfg is incorrect. "
                              "Expected format is `HH:MM:SS` (24 hours format), received {!r}."
                              .format(self.config.automatic_maintenance_time))

                log.exception(error_text)
                raise ValueError(error_text)

            self.automatic_maintenance_time = datetime.datetime.combine(now, restart_timestamp)

            if self.automatic_maintenance_time < now:
                # To avoid immediate restart if time now has passed the timestamp of the day.
                self.automatic_maintenance_time += datetime.timedelta(days=1)

    def update_indicators(self, timestamp):
        """
        Update indicators on all active exchanges if child or `update_indicators_on_parent` is set.
        :param timestamp: timestamp
        :type timestamp: int|float
        """
        if self.config and self.config.update_indicators_on_parent or not self.is_parent:
            for ex in self.all_active_exchanges:
                ex.update_indicators(timestamp)

    def is_exchange_configured(self, exchange_id):
        """
        The Exchange is ready when it is both configured and initialized
        :param exchange_id: EPEX | TRAYPORT | NORDPOOL
        :type exchange_id: str
        """
        return (
            getattr(self, exchange_id).allowed
            and (
                self.is_parent
                or self.child_id in getattr(self.config, "{}_child_ids".format(exchange_id.lower()), [])
            )
        )

    def check_initialized(self):
        exchanges = {
            "epex": False,
            "trayport": False,
            "nordpool": False,
        }
        if not any([getattr(x, "allowed") for x in [getattr(self, e) for e in exchanges.keys()]]):
            return False
        if self.is_persistence_initialized():
            for exchange_key in exchanges.keys():
                exchange = getattr(self, exchange_key)
                if self.is_exchange_configured(exchange_key):
                    if self.is_exchange_initialized(exchange):
                        exchanges[exchange_key] = True
                else:
                    exchanges[exchange_key] = True
        return all([v for v in exchanges.values()])

    def is_persistence_initialized(self):
        return PERSIST.MongoDBConnector().is_initialized

    def is_epex_initialized(self):
        return self.is_exchange_initialized(self.epex)

    def is_nordpool_initialized(self):
        return self.is_exchange_initialized(self.nordpool)

    def is_trayport_initialized(self):
        return self.is_exchange_initialized(self.trayport)

    def is_exchange_initialized(self, exchange):
        return exchange.init_files_ready()

    def _run_timer_once(self, timestamp):
        """ Triggers timed periodic tasks """
        current_timestamp = datetime.datetime.now()
        if current_timestamp >= self.automatic_maintenance_time:
            self.automatic_maintenance_time += datetime.timedelta(days=1)
            self.epex.remove_old_products()
            self.nordpool.remove_old_products()
            # Since Trayport implements this by a RestartExchangeException,
            # we need to ensure it's only being called by the parent to avoid multiple restarts.
            if self.is_parent:
                self.trayport.remove_old_products()

        now = int(time.mktime(current_timestamp.timetuple()))
        next_ioc_cleanup = self.last_ioc_cleanup_run + 60
        if now >= next_ioc_cleanup:
            self.epex.remove_old_ioc_orders(now - 60)
            self.last_ioc_cleanup_run = now

        if timestamp > self._last_orderbook_cleanup_run + COMMON.ORDERBOOK_CLEANUP_INTERVAL:
            log.debug("Running hourly cleanup of outdated orderbooks. Now is %s (UTC)",
                      CETUTIL.utc_ts2utc_str(timestamp))
            for exchange in self.all_active_exchanges:
                exchange.remove_old_orderbook(timestamp)
            self._last_orderbook_cleanup_run = timestamp

        # clean up the orders with timeouts if they are already elapsed
        for exchange in self.all_active_exchanges:
            for product, oid_ts_tuples in exchange.orders_with_timeout.items():
                order_ids_to_remove = [order_id for order_id, order_ts in oid_ts_tuples if
                                       order_ts + exchange.lock_timeout < timestamp]
                product.remove_own_orders_from_book(order_ids_to_remove, timestamp, "the order timeout elapsed")

    def run_once(self, action_type=COMMON.TimerEvent.timer, timestamp=None):
        """Triggers housekeeping tasks, etc.

        Meant to be called periodically.
        """
        try:
            if timestamp is None:
                timestamp = time.time()
            timer_struct = {"exchange": COMMON.Exchange.periotheus,
                            "message_type": action_type,
                            "timestamp": timestamp}
            if action_type == COMMON.TimerEvent.timer_fast and self.trayport.allowed:
                callbacks_to_run = self.trayport.bookkeeping_on_timer_fast(timestamp)
                for callback_name, modified_objects in callbacks_to_run.items():
                    if modified_objects:
                        log.debug("State was changed during bookkeeping tasks on timer fast. "
                                  "Running strategy callback: %s", callback_name)
                        self._run_strategy_callbacks(timer_struct, modified_objects, callback_name)

            self.update_from_json(timer_struct, {})
        except (COMMON.HaltExchangeException, COMMON.RestartExchangeException):
            raise
        except Exception:
            log.info("Ignoring strategy callback triggered by action_type: %s", action_type)
            log.exception("Exception in run once")
            raise
        if self.is_parent:
            for exchange in self.all_active_exchanges:
                self.send_to_exchange(exchange, products_to_intmarket=exchange.get_vault_products())
        if action_type == COMMON.TimerEvent.timer:
            self._run_timer_once(timestamp)

    def get_custom_strategies_path(self):
        if self.use_own_strategies_folder:
            path = "own_strategies"
        else:
            path = "custom_strategies"
        module_path = os.path.abspath(__file__)
        strategies_path = os.path.split(os.path.split(module_path)[0])[0]
        strategies_path = os.path.join(strategies_path, path)
        try:
            os.makedirs(strategies_path)
        except OSError:
            # EAFP: Checking existence of strategies_path before creating it is not atomic and multiple threads
            # may create conflicts. Therefore we first *try* to create the directory. If this fails because
            # it already exists, then no problem. If there's any other issue, raise it.
            # In Python 3, we will™ replace this with strategies_path.mkdir(exist_ok=True)
            if not os.path.exists(strategies_path):
                raise
        return strategies_path

    def _halt_strategy(self, strategy, halted, remove_orders=True, halt_reason=None, username=None):
        """Halts/Activates the specified strategy and removes its orders if required

        :param STRATEGY.Strategy strategy: strategy object to be modified
        :param bool halted: if the halt is set
        :param bool remove_orders: if own orders should be removed or not
        :param str halt_reason: The reason for the halt, if the strategy gets halted.
        :param str username: The name of the user who unhalted/halted the strategy. Used for compliance logging.
        :return:
        """
        history_fields = []
        if strategy.halted != halted or (strategy.halted and strategy.halt_reason != halt_reason):
            history_fields.append("halted")
            if halted:
                history_fields.extend(["halt_reason", "remove_orders"])

        strategy.on_strategy_emergency_update(halted=halted,
                                              halt_reason=halt_reason,
                                              remove_orders=remove_orders,
                                              username=username)
        log.debug("Set halted flag: '%s' for strategy %s. Reason : %s", halted, strategy.strategy_id, halt_reason)
        if halted and remove_orders:
            strategy.remove_orders_of_product()
            # After running `_halt_strategy` the delete order requests are cached in the exchange.modify_orders
            # The following call sends these cached requests to the exchange or parent immediately after the halt
            self.send_to_exchange(strategy.exchange)

        if not strategy.halted:
            # If the strategy was unhalted, update the halt reason in case at/ the exchange is halted
            halt_reason_updated = self._write_global_haltinfo_into_strategy_haltreason(strategy)
            if halt_reason_updated and "halt_reason" not in history_fields:
                history_fields.append("halt_reason")

        PERSIST.MongoDBConnector().update_db_trading_portfolios(
            strategy, timestamp=self.current_timestamp, history_fields=history_fields
        )
        PERSIST.MongoDBConnector().update_db_strategy_config(strategy)

    def call_strategies_on_at_or_exchange_halt(self, remove_orders=True, exchange=None,
                                               username=COMMON.PeriotheusSystemUsers.unset):
        """
        Remove orders if requested and indicate exchange and autotrader halt in tha halt reason of unhalted strategies.

        :param bool remove_orders: if own orders should be removed or not
        :param APIEXCH.ExchangeBase exchange: if given, only the strategies corresponding to the provided exchange
                                              are modified
        :param username: The name of the user who (un-)halted autotrader or the strategy. Used for compliance logging.
        """
        for strategy in self.strategies.values():
            # For unhalted strategies, we indicate the autotrader/exchange halt in the halt reason.
            # Halted strategies have their own reason and are not touched.
            if not strategy.halted and (exchange is None or strategy.exchange == exchange):
                halt_reason_changed = self._write_global_haltinfo_into_strategy_haltreason(strategy)

                strategy.update_active_flag(username)

                if remove_orders:
                    strategy.remove_orders_of_product()
                    log.debug("Remove own orders for strategy %s", strategy.strategy_id)

                PERSIST.MongoDBConnector().update_db_trading_portfolios(
                    strategy,
                    timestamp=self.current_timestamp,
                    history_fields=["halt_reason"] if halt_reason_changed else [])
                PERSIST.MongoDBConnector().update_db_strategy_config(strategy)
            # For halted strategies, the SO status_text needs to be updated when halting/resuming the aT/exchange
            elif strategy.halted and (exchange is None or strategy.exchange == exchange):
                strategy.update_active_flag(username)

        # Send the order delete requests to the exchange
        self.send_to_active_exchanges()

    def _write_global_haltinfo_into_strategy_haltreason(self, strategy):
        """
        Indicate the autoTRADER and/or exchange halt in the strategy's halt reason
        :param strategy: The strategy for which to update the halt_reason
        :type strategy: autotrader_core.strategy.Strategy
        :return: True if the strategy's halt-reason was updated, False otherwise
        :rtype: bool
        """
        what = []
        if self.halted:
            what.append("autoTRADER")
        if strategy.exchange.halted:
            what.append(strategy.exchange.internal_id)
        if what:
            halt_reason = "Not trading, because {} {} halted".format(" and ".join(what), ["is", "are"][len(what) - 1])
        else:
            halt_reason = None
        if strategy.halt_reason != halt_reason:
            strategy.halt_reason = halt_reason
            log.debug("Updating strategy halt reason for %s to %s", strategy.strategy_id, strategy.halt_reason)
            return True
        return False

    def stop_trading(self, critical, reason="", remove_orders=True, username=None):
        """
        Stops trading on error or by user

        :param bool critical: if trading is stopped due to critical error
        :param str reason: stop reason
        :param bool remove_orders: specifies if own orders should be removed while trading is stopped
        """
        history_fields = []
        # if we are not already halted or if we are already halted but the critical_halt/halt_reason is different
        # we should add an entry to the history.
        if not self.halted or self.halted and (critical != self.critical_halt or self.halt_reason != reason):
            history_fields.extend(["halted", "critical_halt", "halt_reason", "remove_orders"])

        self.halted = True
        self.critical_halt = critical
        self.halt_reason = reason
        self.remove_orders = remove_orders
        self.update_db(history_fields=history_fields)
        self.call_strategies_on_at_or_exchange_halt(remove_orders=remove_orders, username=username)
        log.warning("Stopped trading. Reason: '%s', critical flag: '%s', remove_orders: %s",
                    reason, critical, remove_orders)
        log.compliance_log(log_entry=LOGTEMP.AutoTraderBasic.autotrader_halted,
                           reason=reason,
                           critical=critical,
                           remove_orders=remove_orders,
                           username=username)

    def start_trading(self, username=None):
        history_fields = []
        # if we are currently halted and about to resume trading, we add an entry to the history
        if self.halted:
            history_fields.extend(["halted", "critical_halt"])

        self.halted = False
        self.remove_orders = True
        self.critical_halt = False
        self.halt_reason = ""
        self.update_db(history_fields=history_fields)
        self.call_strategies_on_at_or_exchange_halt(remove_orders=False, username=username)
        log.info("Started trading.")
        log.compliance_log(log_entry=LOGTEMP.AutoTraderBasic.autotrader_started,
                           username=username)

    def handle_request(self, message):
        message_type = message["message_type"]
        log.debug("received message: %s", message_type)
        if message_type == "request_status_info":
            return self._handle_request_status_info(message)
        elif message_type == COMMON.Request.order_book:
            ex = self.get_exchange(message["data"]["exchange"])
            return ex.serialize_order_book(message)
        if message_type == COMMON.Request.market_state:
            return self.epex.serialize_market_state()
        elif message_type == COMMON.Request.product:
            return self.serialize_products()
        elif message_type == COMMON.Request.own_trade:
            return self.serialize_trades()
        elif message_type == "dump_request":
            with open("{}".format("{}-nordpool".format(message["path"])), "w") as f_write:
                six.moves.cPickle.dump(self.nordpool.products, f_write)
            with open("{}".format("{}-epex".format(message["path"])), "w") as f_write:
                six.moves.cPickle.dump(self.epex.products, f_write)
        elif message_type == "slot_request":
            self._handle_slot_request(message["data"])

    def _handle_request_status_info(self, message):
        """Handles request for activity status of autotrader or a specified exchange"""
        reply = {"exchange": COMMON.Exchange.autotrader,
                 "timestamp": int(time.time()),
                 "message_type": "status_info",
                 "data": dict()}
        exchange_id = message["data"].get("exchange_id", None)
        if exchange_id:
            exchange = self.get_exchange(exchange_id.upper())
            if exchange is None:
                log.warning("message_type: %s: Requesting status of a non-existing exchange %s",
                            message.get("message_type", "unknown"), exchange_id)
            elif isinstance(exchange, APIEXCH.NullExchange):
                log.warning("message_type: %s: Requesting status of an uninitialized exchange %s",
                            message.get("message_type", "unknown"), exchange_id)
            else:
                reply["data"] = dict(is_running=not exchange.halted, exchange_id=exchange_id)
        else:
            reply["data"] = dict(is_running=not self.halted)
        return reply

    def handle_strategy_halt(self, message, strategy_id):
        """
        Set halted/active state to strategy and db according to the message

        :param message: The payload of the steering message, containing the information to halt or resume the strategy
        :type message: dict
        :param strategy_id: internal number of the strategy, coming in the steering call
        :type strategy_id: str
        """
        strategy = self.strategies.get(strategy_id)
        if strategy:
            username = COMMON.PeriotheusSystemUsers.get_username_from_obj(message, "halting_user")
            self._halt_strategy(strategy=strategy,
                                halted=message.get("halted", True),
                                remove_orders=message.get("remove_orders", True),
                                halt_reason=message.get("halt_reason", None),
                                username=username)

    def _handle_slot_request(self, slots):
        """This helper method can be used to simulate strategy slot requests

        :param list slots: list of slots that should be defined as dictionary with following keys:

        product_id: (optional: can be product_name instead)
        product_name: (optional: can be product_id instead)
        strategy_key: key of the strategy that will send the slots to the exchange
        direction: COMMON.Direction
        quantity: (optional) float
        price: (optional) float
        price_range_lo: (optional)
        price_range_hi: (optional)
        execution_restriction: (optional) COMMON.ExecutionRestriction
        order_type: (optional: default COMMON.OrderType.order)
        clip_quantity: (optional) float,
        slot_type: any string that strictly defines the purpose of the order
        execmode: (optional, default COMMON.InternalExecutionMode.default)
        """

        for slot in slots:
            generated_slot = autotrader_core.strategy.PositionSlot(
                slot["slot_type"], slot["direction"],
                slot.get("quantity", None), slot.get("price", None),
                slot.get("price_range_lo", None), slot.get("price_range_hi", None),
                slot.get("execution_restriction", COMMON.ExecutionRestriction.non),
                slot.get("order_type", COMMON.OrderType.order),
                slot.get("clip_quantity", None), slot.get("price_delta", 0.0))
            for strategy_key, strategy in self.strategies.items():
                if slot.get("exchange") == COMMON.Exchange.nordpool:
                    exchange = self.nordpool
                elif slot.get("exchange") == COMMON.Exchange.epex:
                    exchange = self.epex

                if strategy_key == slot["strategy_key"]:
                    strategy.place_slots({},
                                         exchange.products.get_slot_product(slot),
                                         time.time(),
                                         strategy.delivery_area_id,
                                         [generated_slot],
                                         execmode=slot.get("execmode", COMMON.InternalExecutionMode.default))

    def serialize_products(self):
        products = []
        for ex in self.all_active_exchanges:
            products.extend(ex.serialize_products(self.current_timestamp))
        message = {"exchange": COMMON.Exchange.autotrader,
                   "timestamp": int(time.time()),
                   "message_type": COMMON.Response.product,
                   "data": products}
        return message

    def serialize_trades(self):
        trades = []
        for ex in self.all_active_exchanges:
            trades.extend(ex.serialize_trades())
        message = {"exchange": COMMON.Exchange.autotrader,
                   "timestamp": int(time.time()),
                   "message_type": COMMON.Response.own_trade,
                   "data": trades}
        return message

    def update_from_strategy_request(self, struct):
        """
        Called when a message from a child process is received.

        :type struct: dict
        :param struct: autotrader message
        :return: empty list if exchange was not initialized or None
        """
        exchange = self.get_exchange(struct["exchange"])
        if not self.config or not self.config.backtesting:
            # Never move back in time with multiprocessed backtesting.
            self.current_timestamp = struct.get("timestamp", time.time())

        if not self.is_exchange_initialized(exchange):
            return []

        for entry in struct["data"]:
            # Filter out non existing orders
            received_orders = {types: [APITR.OwnOrder.deserialize(exchange, order_dict)
                                       for order_dict in values]
                               for types, values in entry.items()}
            orders_to_send = collections.defaultdict(list)
            for order_type, orders in received_orders.items():
                if order_type in [COMMON.ResolverState.modify_orders,
                                  COMMON.ResolverState.delete_orders,
                                  COMMON.ResolverState.delete_orders_for_locked_product]:
                    for order in orders:
                        if order.product.orders.get_own_order_by_order_id(order.order_id, broker_id=order.broker_id):
                            key = order_type
                        else:
                            key = COMMON.Response.internal_order_reject
                        orders_to_send[key].append(order)
                else:
                    orders_to_send[order_type] = orders
            exchange.modify_orders.update(orders_to_send)
            self.send_to_exchange(exchange, products_to_intmarket=None)

    def update_from_xml(self, exchange, body, properties):
        """
        Only used in tests, not used in production
        """
        if exchange == COMMON.Exchange.epex:
            # Globally import autotrader_lib.standard_message_adapter causes the simulation tests to
            # fail on windows (as installing lxml is a PITA). So import it locally
            import autotrader_lib.standard_message_adapter as ALSMA  # Local import is OK

            # convert from xml
            json_export = ALSMA.M7TranslatorMixIn.from_xml_to_json(body, timestamp=self.current_timestamp)
            if json_export["timestamp"] is None:
                json_export["timestamp"] = time.time()
            self.update_from_json(json_export, properties)

    def update_db(self, history_fields=None):
        if history_fields is None:
            history_fields = []

        was_initialized = self.initialized
        self.initialized = self.check_initialized()
        if was_initialized != self.initialized:
            history_fields.append("initialized")

        PERSIST.MongoDBConnector().update_db_autotrader(self, history_fields=history_fields)
        PERSIST.MongoDBConnector().update_db_autotrader_child(self)
        is_atconf = isinstance(self.config, ATCONF.ATConfig)
        ex_list = COMMON.Exchange.get_configured(self.config) if is_atconf else COMMON.Exchange.get_external()
        self.max_queue_lag = {ex: 0. for ex in ex_list}

    def update_from_json(self, struct, properties):
        """

        :type struct: dict
        :type properties: dict
        :return: call success status
        :rtype: bool
        """
        now = time.time()
        queue_lag = -99.
        if "timestamp" in struct:
            queue_lag = now - (struct["timestamp"] or now)
            if struct.get("exchange") in self.queue_lag:
                self.queue_lag[struct["exchange"]] = queue_lag
                self.max_queue_lag[struct["exchange"]] = max(self.max_queue_lag[struct["exchange"]], queue_lag)

        correlation_id = properties.get("correlation_id", "") if properties else ""
        if correlation_id:
            struct["correlation_id"] = correlation_id

        if self.config and self.config.backtesting:
            # Never move back in time when backtesting.
            self.current_timestamp = max(self.current_timestamp, struct.get("timestamp", self.current_timestamp))
        else:
            self.current_timestamp = struct.get("timestamp", time.time())
        if self.is_parent:
            result = self._update_parent(struct)
        else:
            result = self._update_child(struct)
        message_type = struct.get("message_type", "?")
        exchange = struct.get("exchange", "unknown exchange")
        if message_type != COMMON.TimerEvent.timer_fast:
            if self.config and self.config.backtesting:
                log.debug("message_type: %s from %s, exec_time: %s, simulation_timestamp: %.6f", message_type,
                          exchange, time.time() - now, self.current_timestamp)
            else:
                log.debug("message_type: %s from %s, exec_time: %.6f, queue_lag: %.6f", message_type, exchange,
                          time.time() - now, queue_lag)
        return result

    def _run_strategy_callbacks(self, struct, modified_objects=None, callback_name=None):
        """call strategy.<callback_name> with possibly filtered modified objects and callback_name

        :param struct: incoming message
        :type struct: dict
        :param modified_objects: will be filtered for types which have a method `match_delivery_areas`.
        :type modified_objects: list or NoneType
        :param callback_name: name of the strategy method to call
        :type callback_name: str
        """
        if not callback_name:
            return
        if struct.get("exchange") in self.queue_lag:
            if self.queue_lag[struct["exchange"]] > self.hwm_queue_lag:
                log.debug("Strategy will not run for exchange: {} because of queue lag".format(struct["exchange"]))
                return

        if self.halted:
            log.info("Autotrader is halted with reason %r and remove_orders=%s", self.halt_reason, self.remove_orders)
        for exchange in self.all_active_exchanges:
            if exchange.halted:
                log.info("Exchange %s is halted with reason %r and remove_orders=%s",
                         exchange.internal_id, exchange.halt_reason, exchange.remove_orders)

        for strategy in self.strategies.values():
            exchange = strategy.exchange

            if strategy.halted:
                if strategy.active:
                    log.debug("Strategy %s is halted with remove_orders=%s", strategy.strategy_id,
                              getattr(strategy, "remove_orders", True))
                else:
                    log.debug("Strategy %s is halted and deactivated", strategy.strategy_id)

            if callback_name == "on_timer" and ((self.halted and getattr(self, "remove_orders", True))
                                                or (exchange.halted and exchange.remove_orders)
                                                or (strategy.halted and getattr(strategy, "remove_orders", True))):
                log.debug("Removing orders for strategy %s due to a halt", strategy.strategy_id)
                strategy.remove_orders_of_product()
                continue

            if callback_name == "on_order_book_update" and isinstance(strategy, SYSTRAT.SyntheticOrderStrategyBase):
                self._remove_deleted_synthetic_orders_on_udel(modified_objects, strategy)

            if self.halted or exchange.halted or strategy.halted:
                continue

            if not strategy.active:
                if callback_name == "on_timer":
                    strategy.remove_orders_of_product()
                continue

            # no strategy callbacks if not all init files were answered
            if not self.is_exchange_initialized(exchange):
                log.debug("Exchange %s for strategy %s is not intialized and callback %s will not run",
                          exchange.caption, strategy.strategy_id, callback_name)
                continue

            # Filtered_modified_objects is just a flag to determine whether
            # any of the passed modified_objects is a valid product, order or trade.
            # If there is no matching one, result is [], if the object is a different type, result will be True
            filtered_modified_objects = []

            if struct["message_type"] == COMMON.Response.internal_order_reject:
                # Here modified orbjects is a list of dicts, not a list of orders.
                filtered_modified_objects = [
                    m for m in modified_objects if
                    m["portfolio_key"] == strategy.strategy_id
                ]
            elif modified_objects:
                try:
                    current_strategy_exchange_ids = [ex.internal_id for ex in strategy.exchanges]
                    filtered_modified_objects = [
                        m for m in modified_objects if
                        m.match_delivery_areas(set(strategy.delivery_areas) | set(strategy.view_delivery_areas))
                        and m.exchange in current_strategy_exchange_ids
                    ]
                except AttributeError:  # will happen in case of error messages
                    pass

            # now pass all arguments to the callback, which are not None
            # for timer events, modified_objects is None -> only timestamp is passed
            # for error events, modified_objects is a list -> errors and timestamp are passed
            # for products/trades/orders, modified_objects is a list -> objects and timestamp are passed

            if modified_objects is None:  # timer events (only need a timestamp)
                args = (struct["timestamp"],)
            elif struct["message_type"] == COMMON.Response.error_response:  # error events will be a list
                args = (modified_objects, struct["timestamp"])
            elif filtered_modified_objects:  # other object events (product, trades, orders)
                args = (filtered_modified_objects, struct["timestamp"])
            else:  # no valid objects were found, callbacks should not run
                continue
            # this should catch the timer_fast and timer messages
            if self.queue_lag[exchange.internal_id] > self.hwm_queue_lag:
                log.debug(
                    "Strategy: {} will not run on Exchange: {} because of high queue lag".format(strategy.strategy_id,
                                                                                                 exchange.internal_id))
                continue
            try:
                getattr(strategy, callback_name)(*args)
            except (COMMON.HaltExchangeException, COMMON.RestartExchangeException) as err:
                log.exception("Strategy: %s, Exchange Halt with Error: %s", strategy.strategy_id, err)
                raise
            except ALU.CriticalError as err:
                exc_info = sys.exc_info()
                lines = traceback.format_exception(*exc_info)
                log.exception("Strategy: %s, Stop Exchange %s due to Critical Error: %s",
                              strategy.strategy_id, exchange.internal_id, err)
                raise COMMON.HaltExchangeException(exchange.internal_id, "".join(lines))

            except Exception as err:
                exc_info = sys.exc_info()
                lines = traceback.format_exception(*exc_info)
                log.exception("Strategy: %s, an exception occurred while running callback on strategy! Error: %s",
                              strategy.strategy_id, str(err))
                if self.reraise_on_strategy_exception:
                    raise COMMON.HaltExchangeException(exchange.internal_id, "".join(lines))

    @staticmethod
    def _remove_deleted_synthetic_orders_on_udel(modified_objects, strategy):
        """
        Hard delete synthetic orders that are soft deleted, as soon as the exposed order is removed.

        This has to be done inside autoTRADER and not in the strategy, because strategy callbacks are not run for
        halted / inactive strategies, but we still want to remove SyntheticOrders which are in "deleting" state
        from the strategy and database as soon as possible, to provide good user experience to customers using the
        Joule integration for synthetic orders.

        :param modified_objects: The orders that were modified by this message
        :type modified_objects: list(APITR.OwnOrder)
        :param strategy: A synthetic order strategy
        :type strategy: SYSTRAT.SyntheticOrderStrategyBase
        :rtype: None
        """
        for order in modified_objects:
            if (isinstance(order, APITR.OwnOrder)
                    and order.portfolio_key == strategy.strategy_id
                    and order.quantity == 0):
                slotname = order.tags.get("strategy_slot")
                product_id = order.product.product_id
                synthetic_order = strategy.product_synthetic_order_mapping[product_id].get(slotname)
                if synthetic_order and synthetic_order.deleted:
                    localview = LV.LocalView(product=order.product,
                                             market_area=synthetic_order.market_area,
                                             strategy_id=strategy.strategy_id)
                    if not synthetic_order.exposed_order_volume(localview):
                        strategy._hard_delete_so(synthetic_order, product_id)

    def on_synthetic_order(self, strategy_id, payload):
        """ The callback which will be executed when a new synthetic order is collected from the REST-API via MongoDB

        NOTE: The incremental changes / messages from the REST-API are persisted, but they will not be
        recollected after a restart

        :param strategy_id: the id of the strategy for which the order is intended
        :type strategy_id: str
        :param payload: the JSON payload to be forwarded to the strategy callback
        :type payload: dict
        :return: None when everything worked, str with an error if any exceptions get raised
        :rtype: None or str
        """
        strategy_obj = self.strategies.get(strategy_id)
        if strategy_obj:
            # we just forward the payload and return the response if any
            try:
                response = strategy_obj.on_synthetic_order(payload)
            except Exception as err:
                response = "{}: {}".format(type(err).__name__, err)
            else:
                # to allow deletion of orders just after synthetic order registering [see the case AUT-2871]
                self.send_to_active_exchanges()
            return response
        else:
            return "No strategy with id: {} found!".format(strategy_id)

    def _remove_strategy(self, strategy_id):
        """ Removes the strategy with the given id from autotrader and mongo. """
        if strategy_id in self.strategies:
            del self.strategies[strategy_id]
            PERSIST.MongoDBConnector().delete_db_trading_portfolios(strategy_id, self.current_timestamp)
            PERSIST.MongoDBConnector().delete_db_per_product_limits(strategy_id)
            PERSIST.MongoDBConnector().delete_db_all_synthetic_orders(strategy_id)

    def update_strategy(self, strategy_id, strategy_data):
        """Update the strategy with internal_number==strategy_id with the given data

        :param strategy_id: internal number of the strategy to update
        :type strategy_id: str
        :param strategy_data: strategy data as fetched from mongo
        :type strategy_data: dict[str, any]
        :return: The return value of strategy.on_strategy_update
        :rtype: any
        """
        strategy_result = None
        self.current_timestamp = strategy_data.get(
            "timestamp",
            self.current_timestamp if self.config and self.config.backtesting else time.time()
        )
        if strategy_data.get("deleted", False):
            self._remove_strategy(strategy_id)
        else:
            strategy = self._load_strategy(strategy_id, strategy_data)

            # we cannot avoid storing the strategy data here:
            #   - the strategy update could be overwritten by the customer to already do something
            #   - if it fails, we have ambiguity which settings have perhaps been loaded and which not
            #   - if it runs for a long time on some part, but some setting was already set it might create issues
            # skip saving if its disabled (None or 0)
            if self.keep_strategy_history:
                PERSIST.MongoDBConnector().store_strategy_history(
                    strategy_data, current_timestamp=datetime.datetime.utcnow()
                )
            # we check if the state of the strategy is changing or not
            history_fields = (
                ["active", "halted", "halt_reason"]
                if self._has_strategy_active_state_changed(strategy_data, strategy)
                else []
            )

            strategy_result = self._trigger_on_strategy_update(strategy_data, strategy)
            if strategy:
                PERSIST.MongoDBConnector().update_db_trading_portfolios(
                    strategy, timestamp=self.current_timestamp, history_fields=history_fields
                )
                PERSIST.MongoDBConnector().update_db_strategy_config(strategy)

        object_type = strategy_data.get("object_type", "")
        if object_type == COMMON.MongoDBObjects.strategy and self.config and self.config.nagios_strategy != "":
            ALU.touch_nagios_file(self.config.nagios_strategy)

        return strategy_result

    def _trigger_on_strategy_update(self, strategy_data, strategy):
        """Triggers the `on_strategy_(configuration_)update` event depending on the type of strategy"""
        try:
            # Custom strategies can return something in their `on_strategy_update` implementation.
            if strategy_data.get("object_type") == COMMON.MongoDBObjects.strategy_configuration:
                strategy_result = strategy.on_strategy_configuration_update(strategy_data)
            else:
                strategy_result = strategy.on_strategy_update(strategy_data)
            self.send_to_active_exchanges()

            if strategy_data.get("exchange_1") == COMMON.Exchange.trayport:
                self._validate_trayport_market_area(strategy)

            if not strategy.halted:
                self._write_global_haltinfo_into_strategy_haltreason(strategy)

        except Exception:
            log.exception("strategy call error")
            strategy_result = "ERROR\n{}".format(traceback.format_exc())
        return strategy_result

    def _load_strategy(self, strategy_id, strategy_data):
        """Loads the strategy from the strategy_data depending on the type of strategy."""
        caption = strategy_data.get("short_name", "")
        # USERDEF for strategies and TRBOT_USER_ALGO for trading_bot
        if (strategy_data.get("object_type") == COMMON.MongoDBObjects.strategy_configuration
                or strategy_data.get("algorithm", "USERDEF") == "USERDEF"
                or "package" in strategy_data):
            username = COMMON.PeriotheusSystemUsers.get_username_from_obj(strategy_data, "username")
            return self._load_custom_strategy(caption, strategy_data, strategy_id, username)
        else:
            return self._load_vt_strategy(caption, strategy_data, strategy_id)

    def _validate_trayport_market_area(self, strategy):
        """Evaluates the trayport delivery_areas of a strategy. Will halt the strategy if invalid."""
        if not self.is_trayport_initialized():
            log.debug("Exchange %s is not initialized, skipping market area validation", COMMON.Exchange.trayport)
            return

        for strategy_area in strategy.delivery_areas:
            if strategy_area not in self.trayport.trayport_areas:
                log.error("Market area %s is invalid. Allowed market areas: %s",
                          strategy_area, list(self.trayport.trayport_areas))
                area_name = COMMON.Area.get_caption(strategy_area, COMMON.Exchange.trayport)
                if area_name:
                    halt_reason = "Market Area {} is not available on {}".format(area_name, COMMON.Exchange.trayport)
                else:
                    halt_reason = "Instrument ID {} is invalid".format(strategy_area)
                self._halt_strategy(strategy, halted=True, halt_reason=halt_reason, username="SYSTEM")

    def _has_strategy_active_state_changed(self, strategy_data, strategy):
        """Checks whether the strategy active state has changed

        :param strategy_data: modified strategy data from mongo
        :type strategy_data: dict
        :param strategy: strategy loaded in memory
        :return: True if the active state of the strategy has changed
        :rtype: bool
        """
        active = strategy_data.get("active")
        new_active_state = active and not strategy.halted and not self.halted and not strategy.exchange.halted
        return active is not None and new_active_state != strategy.active

    def update_strategy_limits(self, strategy_id, message, overwrite_limits=False):
        """
        Update the per-product limits of a strategy.

        Calls to this function are triggered by the autoTRADER REST-API.

        :param strategy_id: The id of the strategy for which the limits shall be changed
        :type strategy_id: str
        :param message: The message containing the (partial) change to the limits.
        :type message: dict
        :param overwrite_limits: flag telling if limits need to be overwritten
        :type overwrite_limits: bool
        :return: The new limits of the strategy after the changes have been applied.
        :rtype: dict
        """
        return self.strategies[strategy_id]._receive_new_limits(message, overwrite_limits=overwrite_limits)

    def _load_vt_strategy(self, caption, strategy_data, strategy_id):
        """Load a VisoTech strategy"""
        if (strategy_id not in self.strategies
                or self.strategies[strategy_id].strategy_package_name != strategy_data["algorithm"]):
            import own_strategies.spontaneous_position_closing_strategy.custom_strategy as LINEAR_CLOSE
            import own_strategies.position_closing_strategy.custom_strategy as VOLUME_CLOSE
            import own_strategies.manual_trading_strategy.custom_strategy as MANUAL_TRADING
            import own_strategies.gas_arbitrage.custom_strategy as GAS_ARBITRAGE
            import own_strategies.gas_position_closer.custom_strategy as GAS_POSITION_CLOSER
            import own_strategies.gas_strategy_storage.custom_strategy as GAS_STORAGE
            import own_strategies.flex_strategy_v2.custom_strategy as FLEX_V2
            standard_algorithms = {
                "LINEAR_CLOSE": LINEAR_CLOSE.CustomStrategy,
                "VOLUME_CLOSE": VOLUME_CLOSE.CustomStrategy,
                "TRBOT_POSITION_CLOSING_ALGO": VOLUME_CLOSE.CustomStrategy,
                "GAS_ARBITRAGE": GAS_ARBITRAGE.CustomStrategy,
                "GAS_POSITION_CLOSER": GAS_POSITION_CLOSER.CustomStrategy,
                "GAS_STORAGE": GAS_STORAGE.CustomStrategy,
                "MANUAL_TRADING": MANUAL_TRADING.CustomStrategy,
                "PWR_FLEX_V2": FLEX_V2.CustomStrategy,
            }
            strategy = standard_algorithms[strategy_data["algorithm"]](self, strategy_id, caption,
                                                                       strategy_data["algorithm"])
            self._restore_strategy_halt_state_from_db(strategy)
            self.strategies[strategy_id] = strategy
        else:
            strategy = self.strategies[strategy_id]
        strategy.strategy_type = COMMON.StrategyType.own
        return strategy

    @staticmethod
    def _restore_strategy_halt_state_from_db(strategy):
        """
        Load the strategy specific halt state and the halt reason from the database.
        :param strategy: The strategy object. Will be modified in-place
        :type strategy: autotrader_core.strategy.Strategy
        """
        strategy_id = strategy.strategy_id
        halt_info = PERSIST.MongoDBConnector().load_db_trading_portfolio(strategy_id)
        if halt_info:
            strategy.halted = halt_info.get("halted", False)
            strategy.halt_reason = halt_info.get("halt_reason")
            strategy._remove_orders = halt_info.get("_remove_orders", False)
            log.debug(
                "Loaded halted state for strategy %s from the database: halted=%s, halt_reason=%s, remove_orders=%s",
                strategy_id, halt_info.get("halted", "False (was not present in the database)"),
                halt_info.get("halt_reason", "None (was not present in the database)"),
                halt_info.get("remove_orders", "False (was not present in the database)"))
        else:
            log.debug("No halt info found in database for strategy_id {}."
                      " The strategy will start as unhalted.".format(strategy_id))

    def _make_package_folders(self, package_name):
        custom_strategy_packages_path = self.get_custom_strategies_path()
        strategy_module_path = os.path.join(custom_strategy_packages_path, package_name)
        if not os.path.exists(strategy_module_path):
            # this try accept block ensures that in the case of a collision
            # in making the directories we suppress such an error
            try:
                os.makedirs(strategy_module_path)
            except OSError:
                log.warning("Path: %s, already exists", strategy_module_path)
        return strategy_module_path

    def _load_strategy_with_backoff(self, package_name, unpackaged_package_name, strategy_id, caption):
        """Loads the strategy object from the package.custom_strategy module,
        with a backoff to handle potential collisions

        The logic here is attempt to load 5 times.
        On each load if it is unsuccessful wait a random and increased amount of time.
        This would ensure even if there are many strategies attempting to load at the same time,
        once a collision occurs the colliding strategies will wait a different
        amount of time reducing the chance for a collision. On each further collision,
        the time will increase giving a larger time range for the strategy to load
        and lowering the probability of collision
        """
        custom_strategy_packages_path = self.get_custom_strategies_path()
        for i in range(5):
            mod_file, mod_path, mod_descr = imp.find_module(unpackaged_package_name, [custom_strategy_packages_path])
            package_object = imp.load_module(unpackaged_package_name, mod_file, mod_path, mod_descr)
            try:
                strategy = package_object.custom_strategy.CustomStrategy(self, strategy_id, caption, package_name)
            except AttributeError:
                # sleep for an increasing and random amount of time in the case of a collision
                sleep_time = random.randint(1, (i + 1) * 100) / 100.
                log.exception("Could not load strategy, waiting for {}".format(sleep_time))
                time.sleep(sleep_time)
            else:
                self._restore_strategy_halt_state_from_db(strategy)
                return strategy
            finally:
                if mod_file:
                    mod_file.close()
        raise COMMON.StrategyLoadError("Could not load strategy after 5 attempts!")

    def _load_custom_strategy(self, caption, strategy_data, strategy_id, username):
        """Load or update a customer specific strategy"""
        package_name = strategy_data.get("package_name", strategy_data.get("packagename", None))
        if package_name is None:
            try:
                strategy = self.strategies[strategy_id]
            except KeyError:
                # Cannot link data to a strategy, ignore that packet of data
                log.debug("cannot find strategy %s", strategy_id)
                return None
        else:
            if self.use_own_strategies_folder:
                unpackaged_package_name = package_name
            else:
                unpackaged_package_name = "{}_{}".format(strategy_id.replace(".", "_"), package_name)
            if strategy_id in self.strategies and package_name == self.strategies[strategy_id].strategy_package_name:
                strategy = self.strategies[strategy_id]
            else:
                if strategy_data.get("object_type") == COMMON.MongoDBObjects.strategy_configuration:
                    package = PERSIST.MongoDBConnector().load_package(package_name)
                    strategy_data["package"] = package["package"]
                    # Recursively unimporting/ reloading a package is hardly possible in python, so we need to make sure
                    # that different code with the same name is imported under different names, which we do based on the
                    # upload_time. (Second resolution is enough, as we require a minimum of 1 second between
                    # upload and delete on the REST-API)
                    if not self.use_own_strategies_folder:
                        unpackaged_package_name += package["last_updated_utc"].strftime("_%Y-%m-%dT%H_%M_%S")
                strategy_module_path = self._make_package_folders(unpackaged_package_name)
                if not self.use_own_strategies_folder and "package" in strategy_data:
                    SM.unzip_custom_package(strategy_data["package"], into_dir=strategy_module_path)
                strategy = self._load_strategy_with_backoff(package_name=package_name,
                                                            unpackaged_package_name=unpackaged_package_name,
                                                            strategy_id=strategy_id,
                                                            caption=caption)
                self.strategies[strategy_id] = strategy
                strategy.strategy_type = COMMON.StrategyType.custom
                strategy.compliance_log(log_entry=LOGTEMP.StrategyBasicLogs.strategy_version_changed,
                                        username=username)

        return strategy

    def _handle_init_messages(self, struct, init_corr_id):
        """Handle an initialization message from the exchange.

        :param struct: Incoming message struct
        :type struct: dict
        :param init_corr_id: the correlation_id containing the init id
        :type init_corr_id: str
        :return: Whether the received message should be skipped.
        :rtype: boolean
        :raises COMMON.RestartExchangeException: On specific error messages from epex
        """
        if struct["message_type"] == COMMON.Response.error_response:
            message = ", ".join([error.get("error_message", "") for error in struct.get("data", [])])
            log.error("Received error response on initialization request for '%s'. "
                      "Error: '%s'. Autotrader will not initialize.", init_corr_id, message)
            if (struct["exchange"] == COMMON.Exchange.epex
                    and message == "The Core is down or busy, please try again later."):
                raise COMMON.RestartExchangeException(struct["exchange"], message)
        else:
            log.debug("Update correlation ids: %s, %s", struct.get("message_type"), init_corr_id)

            # we should not drop messages if the message is an order book or a public trade
            if (
                not self._update_init_correlation_ids(init_corr_id)
                and struct.get("message_type") not in [
                    COMMON.Response.order_book,
                    COMMON.Response.public_trade
                ]
            ):
                log.warning("Ignore message %s from exchange: %s, due to outdated correlation id %s",
                            struct.get("exchange"), struct.get("message_type"), init_corr_id)
                return True
        return False

    def _update_parent(self, struct):
        """Update the parent with the contents of the received message."""
        # check if we got an initialization response from the exchange
        init_corr_id = ALU.extract_data_from_correlation_id(struct, "init")
        if init_corr_id:
            is_outdated_message = self._handle_init_messages(struct, init_corr_id)
            if is_outdated_message:  # skip message
                return False

        if struct["exchange"] == COMMON.Exchange.periotheus and struct["message_type"] == COMMON.TimerEvent.timer:
            self._update_on_timer()

        if (struct["exchange"] == COMMON.Exchange.periotheus and struct["message_type"] == COMMON.TimerEvent.timer_fast
                and self.epex.allowed and self.is_exchange_initialized(self.epex)
                and isinstance(self.epex, APIEXCH.Epex)):
            self.epex.send_omt_status_request(struct["timestamp"])
        self._inner_update_from_json(struct)
        return True

    def _update_child(self, struct):
        if struct["exchange"] == COMMON.Exchange.periotheus:
            if struct["message_type"] == COMMON.TimerEvent.timer:
                # Internal autotrader updates (e.g. update of Trayport synthetic products) should be executed
                # before strategy runs the on_timer callback in _run_strategy_callbacks_timer
                self._update_on_timer()
                self._run_strategy_callbacks_timer(struct)
            elif struct["message_type"] == COMMON.TimerEvent.timer_fast:
                self._run_strategy_callbacks_timer_fast(struct)
            else:
                raise Exception("document type unknown")
        self._inner_update_from_json(struct)

    def _update_on_timer(self):
        for ex in self.all_exchanges:
            ex.update_db(self.current_timestamp)

        if self.trayport.allowed and self.is_exchange_initialized(self.trayport):
            # trayport needs the update because of the synthetic products generation
            self.trayport.update_on_timer(self.current_timestamp)
        self.update_db()

    def _inner_update_from_json(self, struct):
        products_to_intmarket = []
        if struct["message_type"] == COMMON.Response.exchange_halt:
            remove_orders = struct["data"].get("remove_orders", True)
            critical = struct["data"].get("critical", True)
            halt_reason = struct["data"].get("halt_reason", "halted by SYSTEM")

            exchange = self.get_exchange(struct['exchange'])
            exchange.stop_exchange(reason=halt_reason,
                                   remove_orders=remove_orders,
                                   critical=critical,
                                   username=COMMON.PeriotheusSystemUsers.system)
            self.call_strategies_on_at_or_exchange_halt(True, exchange, username=COMMON.PeriotheusSystemUsers.system)

        if struct["exchange"] != COMMON.Exchange.periotheus:
            self.last_incoming_message_timestamp = self.current_timestamp

            exchange = self.get_exchange(struct["exchange"])
            if not exchange:
                log.warning("Unknown exchange %s", struct["exchange"])
                return

            if struct.get("message_type") == COMMON.TrayportResponse.routes:
                self.route, event = ALU.TrayportRouteHelper.validate_route(
                    configured_routes=self.configured_routes,
                    allowed_routes=[route["route_id"] for route in struct["data"]])
                log.info("Setting Active route to market to: %s with event: %s", self.route, event)
                struct["default_route"] = self.route

            if self.is_parent and struct["message_type"] in [COMMON.Response.internal_order_reject,
                                                             COMMON.Response.internal_trade_lock]:
                return
            strategy_callbacks = exchange.update_from_json(struct, self.current_timestamp)

            if exchange not in self.all_active_exchanges:
                log.info("Exchange %s not initialized, no strategy callbacks", exchange)
                strategy_callbacks = {}

            for callback_name, modified_objects in strategy_callbacks.items():
                if not self.is_parent:
                    self._run_strategy_callbacks(struct, modified_objects, callback_name)

                executed_products = [order.product for order in modified_objects
                                     if isinstance(order, APITR.ComTraderOrder)]
                # Trigger internal market on Com Trader order update
                products_to_intmarket.extend(executed_products)
        elif (struct["message_type"] == COMMON.TimerEvent.timer_fast and isinstance(self.epex, APIEXCH.Epex)):
            self.epex.update_current_omt(self.current_timestamp)  # allow natural decay and state updates

        self.send_to_active_exchanges(products_to_intmarket=products_to_intmarket)

    def _update_init_correlation_ids(self, corr_id):
        """
        Returns True if message from exchange is correlated with a sent init message from AT,
        and sets the corresponding exchange init_files_correlation_ids to True
        if loaded from a database, returns True as well.

        :param corr_id: the relevant init correlation_id data string
        :type corr_id: str
        :return: True if init correlates from parent and exchange
        """
        prefix_map = {COMMON.InitCorrelationIds.epex_init: self.epex.init_files_correlation_ids,
                      COMMON.InitCorrelationIds.nordpool_init: self.nordpool.init_files_correlation_ids,
                      COMMON.InitCorrelationIds.trayport_init: self.trayport.init_files_correlation_ids}

        for prefix, dictionary in prefix_map.items():
            if corr_id.startswith(prefix):
                file_id = corr_id[len(prefix) + 1:]
                if file_id not in dictionary:
                    log.warning("received message with non existing correlation_id %s", file_id)
                    return False
                dictionary[file_id] = True
                return True
        return False

    def _run_strategy_callbacks_timer(self, struct):
        self.update_indicators(self.current_timestamp)
        self._run_strategy_callbacks(struct, callback_name="on_timer")

    def _run_strategy_callbacks_timer_fast(self, struct):
        def _get_next_queued_products(exchange):
            active_products = exchange.products.get_active_products()
            return exchange.products_queue.get_products(active_products,
                                                        self.current_timestamp)

        next_queued_products = []
        for ex in self.all_active_exchanges:
            next_queued_products += _get_next_queued_products(ex)

        if next_queued_products:
            log.debug("Next_queued_products: %s",
                      "; ".join("{prod.name} ({prod.next_action})".format(prod=next_prod) for next_prod in
                                next_queued_products))
            self._run_strategy_callbacks(struct,
                                         modified_objects=next_queued_products,
                                         callback_name="on_products_queue")

    def modify_orders(self, orders, execmode):
        """Update the orders passed on their exchanges.

        :param orders: List of orders to be added or updated
        :param execmode: Execution mode for internal market
        :type orders: list[OwnOrder]
        :type execmode: int, member of :class:`COMMON.InternalExecutionMode`
        :rtype: list[str]
        """
        orders_to_send = []
        # we count that not too many orders are send at the same time for the action limit to be violated
        order_to_send_count = collections.defaultdict(dict)
        # exclude 0 orders or zero orders
        for order in orders:
            if DBG_CONDITION(order.product):
                print((self.current_timestamp, "trymod", order.quantity, order.price, order.execution_restriction,
                      order.tags))

            # check limits for strategy
            found_limit_violations = []
            strategy = self.strategies.get(order.portfolio_key, None)
            if strategy is not None and order.quantity > 0.:
                found_limit_violations.extend(autotrader_core.order_guard.check_order(
                    strategy, order, self.get_exchange(order.exchange), self.current_timestamp))
            else:
                # we found no strategy for this order so no limits are assumed
                pass

            found_action_violation = autotrader_core.order_guard.check_actions_in_rolling_time(
                self.get_exchange(order.exchange), order.broker_id, self.current_timestamp, order_to_send_count)

            if found_limit_violations:
                log.warning(
                    "order %s (%s %s@%s, %s) cannot be processed because of limit violations: %s", order.internal_id,
                    order.direction, order.quantity, order.price, order.tags.get("strategy_slot", ""),
                    ",".join(found_limit_violations)
                )
                if hasattr(order, "order_id"):
                    # In case of limit violations during modifications, remove the original order.
                    # Why is this the desired behavior, even if the order on the exchange did not violate the limits?
                    # ANSWER: We do not want to leave an order at the exchange which the strategy tries to modify but
                    # fails to. What if the order has a very bad price and the strategy tries to change the price but
                    # fails to? Removing the order is the only reasonable thing to do here.
                    log.debug("Deleting order %s due to limit violations", order.order_id)
                    orders_to_send.append(order.modify(quantity=0))
                if strategy.stop_on_limit_violation and strategy.active:
                    strategy.active = False
                    log.warning("strategy deactivated because of limit violation halt: ID: %s", strategy.strategy_id)
                    self.send_to_parent({"message_type": COMMON.ParentChildMessages.strategy_stop,
                                         "data": {"strategy_id": strategy.strategy_id},
                                         "exchange": COMMON.Exchange.periotheus})
            elif found_action_violation:
                log.warning(
                    "order %s (%s %s@%s, %s) cannot be processed because of action violation: %s", order.internal_id,
                    order.direction, order.quantity, order.price, order.tags.get("strategy_slot", ""),
                    ",".join(found_action_violation)
                )
            else:
                orders_to_send.append(order)

        orders = orders_to_send

        for exch, exch_name in ((self.epex, COMMON.Exchange.epex),
                                (self.nordpool, COMMON.Exchange.nordpool),
                                (self.trayport, COMMON.Exchange.trayport)
                                ):
            exch_orders = [o for o in orders if o.exchange == exch_name]
            exch.modify_orders(exch_orders, execmode, exch.market_state)
        return found_limit_violations

    def list_strategies(self):
        return [(s.strategy_id, s.caption, s) for s in self.strategies.values()]

    @property
    def all_active_exchanges(self):
        """Returns a list of all exchange objects that are fully initialized and enabled in the configuration."""
        return [exch for exch in self.all_exchanges if exch.allowed and self.is_exchange_initialized(exch)]

    @property
    def all_exchanges(self):
        return [self.epex, self.nordpool, self.trayport]

    def update_initialization_states(self):
        """
        Updates initialization states for:
            - autoTRADER
            - EPEX
            - Nordpool
            - Trayport

        Called periodically in slow ticks.
        """
        init_calls = {COMMON.Exchange.autotrader: self.check_initialized,
                      COMMON.Exchange.epex: self.is_epex_initialized,
                      COMMON.Exchange.trayport: self.is_trayport_initialized,
                      COMMON.Exchange.nordpool: self.is_nordpool_initialized}

        for obj_name, init_func in init_calls.items():
            previous_state = self._initialization_states.get(obj_name, False)
            current_state = init_func()
            if current_state != previous_state:
                self._initialization_states[obj_name] = current_state
                log.compliance_log(log_entry=LOGTEMP.AutoTraderBasic.initialization_state_change,
                                   object_name=obj_name,
                                   new_state=current_state,
                                   old_state=previous_state)
