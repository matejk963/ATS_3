import zmq
import logging
import autotrader_lib.common as COMMON
import autotrader_lib.config_helper as ATCONF
import six


class NullSocket(object):
    """Dummy socket class to avoid None"""

    def send_multipart(self, content):
        pass

    def close(self, linger=None):
        pass


class SocketsBase(object):
    """Base class for zmq Sockets"""

    def __init__(self, socket_spec, zmq_ctx=None, logger=None):
        # type: (dict[str, any], zmq.Context, logging.Logger) -> None
        """Initialize sockets in sockets_spec according to given options

        :param socket_spec: e.g. dict(status_subscriber={"socket": socket,
                                                         "connect_address": "tcp://...",
                                                         "use_poller": False})
        :type socket_spec: dict[str, dict[str,any]]
        :type zmq_ctx: zmq.Context
        :type logger: logging.Logger
        """
        self.poller = zmq.Poller()
        self._sockets = socket_spec
        self._zmq_ctx = zmq_ctx
        self._log = logger
        self.connect_all_sockets(self._sockets)

    def _bind_and_log(self, socket, address):
        """ Bind a socket to an address and return a error message if it fails."""
        try:
            socket.bind(address)
        except zmq.error.ZMQError as e:
            self._log.error("Failed to bind socket to address: {}. Reason: {}.".format(address, str(e)))
            raise

    def connect_all_sockets(self, socket_spec):
        """Connect/bind all of the sockets given in socket_spec"""
        for name, info in six.iteritems(socket_spec):
            self._log.debug("connecting %s %s", name, info)
            socket = info["socket"]
            if isinstance(socket, NullSocket):
                if self._log:
                    self._log.warning("Socket is NullSocket, not binding, {}".format(name))
                continue
            bind = "bind_address" in info
            address = info["bind_address"] if bind else info["connect_address"]
            self.connect_socket(socket, info.get("use_poller", False), address, name, bind)
            self._log.debug("connected %s %s", name, info)

    def connect_socket(self, socket, use_poller, address, name, bind=False):
        # type: (zmq.Socket, bool, str, str, bool) -> None
        """Connect or Binding sockets to an address considering use of poller

        :param socket: socket to bind
        :type socket: zmq.Socket
        :param use_poller: flag showing whether to use poller
        :type use_poller: bool
        :param address: address to bind or connect to
        :type address: str
        :param name: name of the socket, under which it can be referenced
        :type name: str
        :param bind: flag to show whether the socket is binding or connecting
        :type bind: bool
        """
        if isinstance(socket, NullSocket):
            if self._log:
                self._log.warning("Socket is NullSocket, not binding, {}".format(name))
            return
        if use_poller:
            self.poller.register(socket, zmq.POLLIN)
            self._log.debug("successfully registered to poller {} to {}".format(name, address))
        if bind:
            if self._log:
                self._log.debug("binding {} to {}".format(name, address))
            self._bind_and_log(socket, address)
            self._log.debug("successfully bound to {} to {}".format(name, address))
        else:
            if self._log:
                self._log.debug("connecting {} to {}".format(name, address))
            # Note: if connect requires DNS resolution, this can block until the address is resolved or
            #       gethostbyname times out, where the timeout is OS dependent.
            socket.connect(address)
            self._log.debug("successfully connected to {} to {}".format(name, address))

    def close_socket(self, socket, use_poller):
        # type: (zmq.Socket, bool) -> None
        """Close Socket and unregister poller if necessary"""
        if use_poller:
            try:
                self.poller.unregister(socket)
            except (zmq.error.ZMQError, KeyError) as zme:
                self._log.exception("Error unregistering from socket poller: %s", zme)
        try:
            socket.close(linger=0)
        except zmq.error.ZMQError as zme:
            self._log.exception("Error closing socket: %s", zme)

    def close(self):
        """Close all zmq sockets of this instance gracefully and terminate the context"""
        for name, info in six.iteritems(self._sockets):
            if "socket" in info:
                self.close_socket(info["socket"], info.get("use_poller"))
                del info["socket"]
            if self._log:
                self._log.debug("socket {} closed".format(name))
        if self._zmq_ctx:
            # enforce again that all sockets of this context are shut down.
            # note: while destroy is synonymous to term in libzmq, pyzmq has different semantics for the two functions
            self._zmq_ctx.destroy(linger=0)

    def __getattr__(self, name):
        """get socket by checking the internal _sockets dict

        :param name: name of socket
        :type name: str
        :return: socket with referenced name
        :rtype zmq_ctx: zmq.Socket
        """
        if name in self._sockets:
            return self._sockets[name].get("socket")
        raise AttributeError(name)  # super with object doesn't work for __getattr__


class ConnectionManagerSockets(SocketsBase):
    """Sockets class used for connection managers.

    Contains a status publisher, a publisher for messages and a pull socket to receive commands.
    """

    def __init__(self, host, exch2at_msg_port, exch2at_status_port, at2exch_msg_port, logger=None):
        # type: (str, int, int, int, logging.Logger) -> None
        """init sockets for communication between connection manager and autotrader

       :param host: host running the socket
       :type host: str
       :param exch2at_msg_port: port used to send messages from connection manager to autotrader
       :type exch2at_msg_port: int
       :param exch2at_status_port: port used to send manager status from connection manager to autotrader
       :type exch2at_status_port: int
       :param at2exch_msg_port: port used to send messages from autotrader to connection manager
       :type at2exch_msg_port: int
       :param logger: logger
       """
        ctx = zmq.Context()
        spec = {"msg_publisher": dict(socket=ctx.socket(zmq.PUB),
                                      bind_address="tcp://{}:{}".format(host, exch2at_msg_port)),
                "status_publisher": dict(socket=ctx.socket(zmq.PUB),
                                         bind_address="tcp://{}:{}".format(host, exch2at_status_port)),
                "submission_service": dict(socket=ctx.socket(zmq.PULL),
                                           bind_address="tcp://{}:{}".format(host, at2exch_msg_port),
                                           use_poller=True
                                           )}

        spec["msg_publisher"]["socket"].set_hwm(300000)  # setting high water mark
        super(ConnectionManagerSockets, self).__init__(spec, ctx, logger=logger)


class CoreAdapterSockets(SocketsBase):
    """Sockets manager for autotrader_core_main. Able to dynamically attach adapters."""

    def __init__(self, at_config, logger=None, publish_status=True):
        # type: (ATCONF.ATConfig, logging.Logger, bool) -> None
        """

        :type logger: logging.Logger
        """
        ctx = zmq.Context()

        spec = dict()
        if publish_status:
            # for publishing status information:
            spec["status_publisher"] = dict(
                socket=ctx.socket(zmq.PUB),
                bind_address="tcp://{}:{}".format(at_config.host, at_config.status_port),
            )

        super(CoreAdapterSockets, self).__init__(spec, ctx, logger)

        self.adapters_dict = dict()

    def add_adapter(self, adapter, exchanges=None):
        """
         Create the given adapter's sockets and connect them
        :param adapter: adapters connecting various components
        :type adapter: BA.BaseAdapter
        :param exchanges: allowed exchanges for the child
        :type exchanges: set[str]
        """
        self._log.debug("Adding adapter: %s", adapter.name)
        self.adapters_dict[adapter.name] = adapter
        # autotrader parent has child as adapter, autotrader child has parent as adapter
        if adapter.name == "{}_Adapter".format(COMMON.Exchange.parent):
            socket_spec = adapter.create_socket_spec(self._zmq_ctx, exchanges)
        else:
            socket_spec = adapter.create_socket_spec(self._zmq_ctx)
        self.connect_all_sockets(socket_spec)
        self._sockets.update(socket_spec)

    def reconnect_adapter(self, adapter_name):
        adapter_obj = self.adapters_dict[adapter_name]

        # Get the old socket spec for closing the sockets
        adapter_socket_spec = adapter_obj.socket_spec
        self._log.debug("Disconnecting all sockets for adapter: %s", adapter_name)
        for name, info in adapter_socket_spec.items():
            self.close_socket(info["socket"], info.get("use_poller"))
            del self._sockets[name]

        # Now create a new socket spec (this changes the socket objects in the dict)
        adapter_socket_spec = adapter_obj.create_socket_spec(self._zmq_ctx)

        self._log.debug("Reconnecting all sockets for adapter: %s", adapter_name)
        self.connect_all_sockets(adapter_socket_spec)
        self._sockets.update(adapter_socket_spec)
