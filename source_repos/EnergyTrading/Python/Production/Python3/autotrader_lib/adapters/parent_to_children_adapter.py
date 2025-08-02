import zmq
import collections
import autotrader_lib.common as COMMON
import autotrader_lib.adapters.base_adapter as BA
import autotrader_lib.codec.msgpackcodec


class ParentToChildrenAdapter(BA.BaseAdapter):
    """Adapter to connect a strategy child process to the autotrader parent process.

        Opens two zmq sockets:
        - publish to send things to the children
        - subscriber to listen to messages from children
        """

    def __init__(self, log, on_message_callback, at_config, sockets):
        """

        :param log: see BA.BaseAdapter
        :param on_message_callback: see BA.BaseAdapter
        :param sockets: sockets object to manage this adapter
        :type sockets: autotrader_lib.sockets.CoreAdapterSockets
        """
        self.exchange = COMMON.Exchange.children

        name = "{}_Adapter".format(self.exchange)
        super(ParentToChildrenAdapter, self).__init__(log, name, on_message_callback)

        self._receive_socket = None
        self._send_socket = None
        self.subscribe_port = at_config.parent_to_child_sub_port
        self.publish_port = at_config.parent_to_child_pub_port
        self.socket_spec = None
        self._pub_msg_no = collections.Counter()

        sockets.add_adapter(self)
        self._log.debug("%s adapter is initialized.", name)

    def send(self, content):
        exchange_name = content.get("exchange_id") or content.get("exchange")
        if exchange_name is None and isinstance(content.get("body"), dict):
            exchange_name = content["body"].get("exchange")
        exch_short = exchange_name[:COMMON.Exchange.UNIQUE_EXCH_BYTES].encode()

        self._pub_msg_no[exchange_name] += 1
        content["pub_msg_no"] = self._pub_msg_no[exchange_name]
        msg = autotrader_lib.codec.msgpackcodec.serialize(content)
        self._log.debug("send to %s: body=%s", self.exchange, str(content))
        self._send_socket.send(exch_short + msg)

    def create_socket_spec(self, zmq_context):
        """Returns a socket specification dictionary that works with SOCK.SocketsBase.

        :param zmq_context: The ZeroMQ context
        :type zmq_context: zmq.Context
        :return: A dict mapping socket names to socket specifications
        :rtype: dict[str, dict[str, any]]
        """
        spec = dict()

        # inbound -- receiving messages
        self._receive_socket = zmq_context.socket(zmq.PULL)
        connect_address = "tcp://127.0.0.1:{}".format(self.subscribe_port)
        spec["{}_subscriber".format(self.name)] = dict(socket=self._receive_socket, bind_address=connect_address,
                                                       use_poller=True)

        # outbound -- sending messages
        self._send_socket = zmq_context.socket(zmq.PUB)

        # The default zmq limit for its internal buffer (high water mark) for the PUB socket is
        # 1000 messages. In a case where we cannot consume messages fast enough we would drop messages
        # and trigger a message out of order exception in the child.
        # Because of that we have to set the high water mark to a higher number.
        self._send_socket.set_hwm(300000)

        connect_address = "tcp://127.0.0.1:{}".format(self.publish_port)
        spec["{}_submitter".format(self.name)] = dict(socket=self._send_socket, bind_address=connect_address)

        self.socket_spec = spec
        return spec

    def _try_receive(self, events):
        """ This function attempts to receive a message and returns it as a dict or None if there is no message """
        if self._receive_socket in events:
            msg = self._receive_socket.recv()
            return autotrader_lib.codec.msgpackcodec.deserialize(msg)

    def step(self, events, timestamp=None):
        message_data_dict = self._try_receive(events)
        if message_data_dict:
            self._send_to_core(message_data_dict)
