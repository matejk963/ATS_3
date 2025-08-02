# -*- encoding: utf-8 -*-
import datetime
import time

import zmq

import autotrader_lib.common as COMMON
import autotrader_lib.adapters.base_adapter as BA
import autotrader_lib.codec.msgpackcodec
import autotrader_lib.status
from autotrader_lib.common import READONLY_MESSAGES
from six.moves import range


CONNECTION_MANAGER_SOCKET_TIMEOUT = COMMON.MINUTE * 30


class ConnectionManagerAdapter(BA.BaseAdapter):
    """Adapter to connect connection managers to autotrader core.

    Opens three zmq sockets:
    - push to send things to the connection manager
    - subscriber to listen to messages from the connection manager
    - subscriber for status messages

    This class checks that the publisher message number is continuous.
    """

    def __init__(self, log, exchange, on_message_callback, remote_host, manager_config, sockets, read_only=False,
                 manager_timeout_sec=120):
        """

        :param log: see BA.BaseAdapter
        :param exchange: The exchange this adapter talks to
        :type exchange: str
        :param on_message_callback: see BA.BaseAdapter
        :param remote_host: Remote host the connection manager is executed on
        :type remote_host: str
        :param manager_config: Config section of the connection manager
        :type manager_config: ManagerConfig
        :param sockets: sockets object to manage this adapter
        :type sockets: autotrader_lib.sockets.CoreAdapterSockets
        :param read_only: if adapter is in read_only mode
        :type read_only: bool
        """
        name = "{}_Adapter".format(exchange)
        super(ConnectionManagerAdapter, self).__init__(log, name, on_message_callback)

        self.exchange = exchange
        self.remote_host = remote_host
        self.manager_config = manager_config
        self.socket_spec = None

        self._last_inbound_no = None
        self._exchange_restart_needed = False
        self._receive_socket = None
        self._send_socket = None
        self._status_socket = None
        self._session_started_dt = datetime.datetime(1900, 1, 1)
        self._session_restarted = False
        self.read_only = read_only
        self._manager_timeout_sec = manager_timeout_sec
        self._manager_timeout_ts = time.time() + self._manager_timeout_sec
        self._sockets_timeout_ts = time.time() + CONNECTION_MANAGER_SOCKET_TIMEOUT
        self.sockets = sockets
        self.sockets.add_adapter(self)
        self._log.debug("%s adapter is initialized.", name)
        self.connected = False

    def send(self, body_dict, properties=None, **kwargs):
        # If Adapter is in read_only mode and message to be forwarded to exchange is an
        # order(s) editing message, it is not sent to the exchange.
        if self.read_only and body_dict.get("message_type", "") not in READONLY_MESSAGES:
            self._log.warning("%s is in read-only mode: msg is not sent - %s", self.name, body_dict)
            return
        expiration_ts = datetime.datetime.utcnow() + datetime.timedelta(seconds=COMMON.ORDER_LOCK_TIMEOUT - 10)
        content = dict(exchange=self.exchange, body=body_dict, properties=properties or {},
                       expiration_timestamp=expiration_ts, **kwargs)
        msg = autotrader_lib.codec.msgpackcodec.serialize(content)
        if content["body"]["message_type"] == COMMON.Request.change_password:
            self._log.debug("send to %s: message_type=%s", self.exchange, COMMON.Request.change_password)
        else:
            self._log.debug("send to %s: body=%s", self.exchange, str(content))
        num_send_tries = 5
        for i in range(num_send_tries):
            try:
                self._send_socket.send(msg, flags=zmq.NOBLOCK)
            except zmq.ZMQError as err:
                self._log.warning("Could not send message (try %d/%d): %r", i + 1, num_send_tries, err)
                if i + 1 == num_send_tries:
                    self._log.exception("Giving up trying to send message. Error:")
                else:
                    time.sleep(0.002 * (i + 1))
            else:
                return
        # Try to reconnect the sockets.
        self.reconnect_sockets()
        raise COMMON.RestartExchangeException(self.exchange,
                                              "Restarting exchange {} after connectivity problem between autoTRADER "
                                              "and the connection manager".format(self.exchange))

    def create_socket_spec(self, zmq_context):
        """Returns a socket specification dictionary that works with SOCK.SocketsBase.

        :param zmq_context: The ZeroMQ context
        :type zmq_context: zmq.Context
        :return: A dict mapping socket names to socket specifications
        :rtype: dict[str, dict[str, any]]
        """
        spec = dict()

        if self.manager_config.host is None:
            raise autotrader_lib.SocketConfigurationError("No host configured for adapter {}".format(self))
        if self.manager_config.publisher_port is None:
            raise autotrader_lib.SocketConfigurationError("No publisher_port configured for adapter {}".format(self))
        if self.manager_config.submission_port is None:
            raise autotrader_lib.SocketConfigurationError("No submission_port configured for adapter {}".format(self))

        # inbound -- receiving messages
        self._receive_socket = zmq_context.socket(zmq.SUB)
        connect_address = "tcp://{}:{}".format(self.remote_host, self.manager_config.publisher_port)
        spec["{}_subscriber".format(self.name)] = dict(socket=self._receive_socket, connect_address=connect_address,
                                                       use_poller=True)
        self._receive_socket.SUBSCRIBE = ""  # subscribe to everything

        # outbound -- sending messages
        self._send_socket = zmq_context.socket(zmq.PUSH)
        connect_address = "tcp://{}:{}".format(self.remote_host, self.manager_config.submission_port)
        spec["{}_submitter".format(self.name)] = dict(socket=self._send_socket, connect_address=connect_address)

        self._status_socket = zmq_context.socket(zmq.SUB)
        connect_address = "tcp://{}:{}".format(self.remote_host, self.manager_config.status_port)
        spec["{}_status".format(self.name)] = dict(socket=self._status_socket, connect_address=connect_address,
                                                   use_poller=True)
        self._status_socket.SUBSCRIBE = ""  # subscribe to everything

        self.socket_spec = spec
        return spec

    def _try_receive(self, events):
        """ This function attempts to receive a message and returns it as a dict or None if there is no message """
        if self._receive_socket in events:
            msg = self._receive_socket.recv()
            return autotrader_lib.codec.msgpackcodec.deserialize(msg)

    def step(self, events, timestamp=None):
        message_data_dict = self._try_receive(events)
        now = time.time()
        if message_data_dict:
            self.connected = True
            self._manager_timeout_ts = now + self._manager_timeout_sec
            curr_msg_no = message_data_dict["pub_msg_no"]
            if self._last_inbound_no != 1 and curr_msg_no == 1:
                # reset of the connection manager process, always accept messages with number 1
                pass
            elif self._last_inbound_no is not None and curr_msg_no != (self._last_inbound_no + 1):
                # the remote side may have been restarted, or a message has been sent twice. In the case that
                # the messages are out of sync, the adapter sets the _exchange_restart_needed flag to True
                # (causing a exchange restart) and sets the last inbound message number back to None as if it restarted.
                # Note: after an out-of-sync restart the last inbound message can be reset to any number of the
                # message received

                # example error:
                # ERROR ConnectionManagerAdapter Adapter NORD_Adapter out of sequence
                # (got #1000, expected #999).Setting flag to request an exchange restart.
                # ensure that the connection manager does not mix up message orders to avoid this.

                self._exchange_restart_needed = True
                self._log.error("ConnectionManagerAdapter {} out of sequence (got #{}, expected #{})."
                                "Setting flag to request an exchange restart."
                                .format(self, curr_msg_no, self._last_inbound_no + 1))
                self._last_inbound_no = None

                # don't process any further messages if we're out of sync
                return

            self._last_inbound_no = curr_msg_no
            self._send_to_core(message_data_dict)
        elif now >= self._manager_timeout_ts:
            self._log.warning("{}: Manager has timed out".format(self.name))
            self._manager_timeout_ts = now + self._manager_timeout_sec / 2
            self.connected = False

    def requires_restart_of_exchange(self, events):
        """This adapter requires a restart if the received message number is out of sync or a new session started"""
        session_restarted = False
        if self._status_socket in events:
            msg = self._status_socket.recv()
            data_dict = autotrader_lib.codec.msgpackcodec.deserialize(msg)
            self._log.debug("received status message : %s", data_dict)
            msg_type = data_dict["type"]
            status = data_dict["status"]
            self._sockets_timeout_ts = time.time() + CONNECTION_MANAGER_SOCKET_TIMEOUT
            if msg_type == "heartbeat":
                self.connected = True
                self._manager_timeout_ts = time.time() + self._manager_timeout_sec
                session_since = status["since"]
                if session_since > self._session_started_dt:
                    self._session_started_dt = session_since
                    session_restarted = True
                    self._log.info("new session: {}".format(self))
                    self._log.warning("%s: read only is set to %s", self.name, self.read_only)
            elif msg_type == "change":
                if data_dict == autotrader_lib.status.Status.NO_CONNECTION:
                    self.connected = False
                    # TODO (bet) Discuss in the team: We could react in autoTRADER on this information.
            else:
                raise NotImplementedError(msg_type)
        elif time.time() > self._sockets_timeout_ts:
            self.reconnect_sockets()

        ret = self._exchange_restart_needed or session_restarted
        self._exchange_restart_needed = False
        return ret

    def reconnect_sockets(self):
        """ Will reconnect"""
        self._log.debug("Reconnecting the sockets for adapter: %s", self.name)
        self._sockets_timeout_ts = time.time() + CONNECTION_MANAGER_SOCKET_TIMEOUT
        self.sockets.reconnect_adapter(self.name)
