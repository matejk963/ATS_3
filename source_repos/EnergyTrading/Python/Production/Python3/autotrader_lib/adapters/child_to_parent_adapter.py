import zmq
import collections

import autotrader_lib.common as COMMON
import autotrader_lib.adapters.base_adapter as BA
import autotrader_lib.codec.msgpackcodec


class ChildToParentAdapter(BA.BaseAdapter):
    """Adapter to connect a strategy child process to the autotrader parent.

        Opens two zmq sockets:
        - publisher to send things to the parent
        - subscriber to listen to messages from the parent
        """

    def __init__(self, log, on_message_callback, at_config, sockets, child_id):
        """

        :param log: see BA.BaseAdapter
        :param on_message_callback: see BA.BaseAdapter
        :param sockets: sockets object to manage this adapter
        :type sockets: autotrader_lib.sockets.CoreAdapterSockets
        :param child_id: id of the specific child
        :type child_id: int
        """
        self.exchange = COMMON.Exchange.parent

        name = "{}_Adapter".format(self.exchange)
        super(ChildToParentAdapter, self).__init__(log, name, on_message_callback)

        self.socket_spec = None

        self._receive_socket = None
        self._send_socket = None
        self.publish_port = at_config.parent_to_child_sub_port
        self.subscribe_port = at_config.parent_to_child_pub_port
        self._last_inbound_no = collections.Counter()
        sockets.add_adapter(self, self._check_available_exchanges(at_config, child_id))
        self._log.debug("%s adapter is initialized.", name)

    @staticmethod
    def _check_available_exchanges(at_config, child_id):
        """
        Returns a list of available exchanges for the specific child_id and child adapter
        :param at_config: Config class with settings for autotrader section
        :type at_config: ATCONF.ATConfig
        :param child_id: child_id used for the child process
        :type child_id: int
        :return: set of allowed exchanges for the given child_id
        :rtype: set[str]
        """
        exchanges = set()
        exchanges.update(at_config.child_exchange_distribution[child_id])
        # add the standard exchanges for autotrader as well, COMMON.Exchange.children does not send between children
        # therefore can be omitted.
        exchanges.update([COMMON.Exchange.parent, COMMON.Exchange.autotrader, COMMON.Exchange.persistence,
                          COMMON.Exchange.periotheus])
        return exchanges

    def send(self, content):
        msg = autotrader_lib.codec.msgpackcodec.serialize(content)
        self._log.debug("send to %s: body=%s", self.exchange, str(content))
        self._send_socket.send(msg)

    def create_socket_spec(self, zmq_context, allowed_exchanges=None):
        """Returns a socket specification dictionary that works with SOCK.SocketsBase.

        :param zmq_context: The ZeroMQ context
        :type zmq_context: zmq.Context
        :param allowed_exchanges: allowed exchanges for the child
        :type allowed_exchanges: set[str]
        :return: A dict mapping socket names to socket specifications
        :rtype: dict[str, dict[str, any]]
        """
        spec = dict()

        # inbound -- receiving messages
        self._receive_socket = zmq_context.socket(zmq.SUB)
        if not allowed_exchanges:
            self._receive_socket.setsockopt(zmq.SUBSCRIBE, "")
        else:
            for exchange in allowed_exchanges:
                self._receive_socket.setsockopt(zmq.SUBSCRIBE, str.encode(exchange[:COMMON.Exchange.UNIQUE_EXCH_BYTES]))
        connect_address = "tcp://127.0.0.1:{}".format(self.subscribe_port)
        spec["{}_subscriber".format(self.name)] = dict(socket=self._receive_socket, connect_address=connect_address,
                                                       use_poller=True)

        # outbound -- sending messages
        self._send_socket = zmq_context.socket(zmq.PUSH)
        connect_address = "tcp://127.0.0.1:{}".format(self.publish_port)
        spec["{}_submitter".format(self.name)] = dict(socket=self._send_socket, connect_address=connect_address)

        self.socket_spec = spec
        return spec

    def _try_receive(self, events):
        """ This function attempts to receive a message and returns it as a dict or None if there is no message """
        if self._receive_socket in events:
            return autotrader_lib.codec.msgpackcodec.deserialize(
                self._receive_socket.recv()[COMMON.Exchange.UNIQUE_EXCH_BYTES:])

    def step(self, events, timestamp=None):
        message_data_dict = self._try_receive(events)

        if message_data_dict:
            exchange_name = message_data_dict.get("exchange_id") or message_data_dict.get("exchange")
            if exchange_name is None and "body" in message_data_dict and isinstance(message_data_dict["body"], dict):
                exchange_name = message_data_dict["body"].get("exchange")
            curr_msg_no = message_data_dict["pub_msg_no"]
            if curr_msg_no != self._last_inbound_no[exchange_name] + 1:
                self._log.error("ChildToParentAdapter %s out of sync (got #%s, expected #%s)", self, curr_msg_no,
                                self._last_inbound_no[exchange_name] + 1)
                raise COMMON.OutOfSyncChildException(self)

            self._last_inbound_no[exchange_name] = curr_msg_no
            self._send_to_core(message_data_dict)

    def requires_restart_of_exchange(self, events):
        # This adapter is recreated if the exchanges are restarted, and thus never triggers a restart on its own
        return False
