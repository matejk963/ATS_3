# -*- coding: utf-8 -*-

"""
Read-only Simulation mode: Autotrader is conncted to an exchange, but does not place any orders there.
Instead, OwnOrders are matched with PublicOrders (and incoming public Trades) by ExchangeSimulator.
Read-only mode uses a full suite of Autotrader parent and child processes.
"""
from __future__ import absolute_import

import autotrader_lib.adapters.base_adapter as BA
import autotrader_lib.common as COMMON


class ReadonlySimAdapter(BA.BaseAdapter):
    """
    Connect to an exchange in read-only, simulation mode.

    Receive messages from the exchange but feed all modifying messages to the simulator instead of the exchange.
    Messages that request lists of trades/ orders are still forwarded to the exchange.

    Internally, this uses a buffer unprocessed_outgoing_messages, so multiple messages from AT are passed to exchange
    simulator at once.

    A single message from the exchange can create multiple messages after simulation, which cause the step function
    to call on_message_callback multiple times.

    All modifying answers by AutoTrader are in the meantime stored in unprocessed_outgoing_messages. On the next call
    to `step`, they are fed through the Exchange Simulator to on_message_callback.
    """
    def __init__(self, log, exchange_simulator, connectionmanager_adapter, on_message_callback, is_backtesting=False):
        """
        :param log: the python log to log messages to
        :type log: logging.Logger or autotrader_lib.fast_logging.Logger
        :type exchange_simulator: autotrader_core.exchange_simulator.ExchangeSimulator
        """
        super(ReadonlySimAdapter, self).__init__(log, "ReadonlySimulationAdapter", on_message_callback)
        self.exchange_simulator = exchange_simulator
        self.connection_manager_adapter = connectionmanager_adapter
        self.connection_manager_adapter._on_message_callback = self._receive_through_simulator_callback
        self.unprocessed_outgoing_msgs = []
        self.is_backtesting = is_backtesting
        self.connected = self.connection_manager_adapter.connected

    def send(self, body_dict, properties=None, **kwargs):
        if not self.is_backtesting and body_dict.get("message_type", "") in COMMON.READONLY_MESSAGES:
            self.connection_manager_adapter.send(body_dict, properties, **kwargs)
        elif body_dict.get("message_type", "") != COMMON.EpexResponse.omt_status:
            self.unprocessed_outgoing_msgs.append({"body": body_dict, "properties": properties})

    def step(self, events, timestamp):
        # Perform the pending simulation.
        if self.unprocessed_outgoing_msgs:
            self._log.debug("%s step: calling exchange_simulator.send with message types: %s", self.name,
                            [x["body"]["message_type"] for x in self.unprocessed_outgoing_msgs])
            try:
                simulated_responses = self.exchange_simulator.send(self.unprocessed_outgoing_msgs)
            except Exception as exception:  # pylint: disable=W0703
                self._log.exception("An Error occurred in the exchange simulator for messages %s."
                                    "Ignoring them and requesting a restart of exchange. (%s)",
                                    self.unprocessed_outgoing_msgs, exception)
                self.connection_manager_adapter._exchange_restart_needed = True  # Request a restart.
                return
            finally:
                self.unprocessed_outgoing_msgs = []
            for msg in simulated_responses:
                self._on_message_callback(self, msg)
        else:
            # No pending simulation. Receive next message from exchange.
            # Note: We only care about the pub_msg_no in the CMA (i.e. when receiving from the exchange),
            #       not when we receive from the simulator.
            self.connection_manager_adapter.step(events, timestamp)
            self.connected = self.connection_manager_adapter.connected

    def _receive_through_simulator_callback(self, adapter, data):
        """
        Put incoming messages from the exchange to the exchange simulator
        """
        try:
            simulated_responses = self.exchange_simulator.receive(data)
        except Exception:  # pylint: disable=W0703
            self._log.exception("An Error occurred in the exchange simulator. Ignoring message %s. "
                                "Requesting a restart of exchange.",
                                data)
            self.connection_manager_adapter._exchange_restart_needed = True
        else:
            for msg in simulated_responses:
                self._on_message_callback(adapter, msg)

    def requires_restart_of_exchange(self, events):
        return self.connection_manager_adapter.requires_restart_of_exchange(events)
