# -*- coding: utf-8 -*-


class BaseAdapter(object):
    """Base class for adapters connecting various components to the autotrader core."""

    def __init__(self, log, name, on_message_callback):
        """

        :param log: the python log to log messages to
        :type log: logging.log
        :param name: Name of the adapter. Used eg for logging.
        :type name: str.
        :param on_message_callback: callback function taking (adapter, msg_dict) as arguments. Will be called when
            the adapter has received data that should be forwarded to the autotrader core.
        :type on_message_callback: callable(adapter, data)
        """
        self._log = log
        self.name = name
        self._on_message_callback = on_message_callback

    def __str__(self):
        return "Adapter {}".format(self.name)

    def send(self, data):
        """Send data to through the Adapter to its counterpart.

        Has to be implemented in the subclass

        :param data: The data to send
        :type data: Any
        """
        raise NotImplementedError()

    def step(self, events, timestamp=None):
        """Called on events by the autotrader core.

        Has to be implemented in the subclass.

        :param events: The events returned by zmq.Poller.poll as a dictionary
        :type events: dict[zmq socket, event]
        """
        raise NotImplementedError()

    def requires_restart_of_exchange(self, events):
        """Returns true if some change in the adapter should trigger a restart of the autotrader core.

        :param events: The events returned by zmq.Poller.poll as a dictionary
        :type events: dict[zmq socket, event]
        """
        return False

    def _send_to_core(self, data):
        """Internal helper function forwarding the data to the autotrader_parent.
        :param data: The data to be forwarded
        :type data: Any
        """
        self._on_message_callback(self, data)

    def close(self):
        """Closing function triggered when autotrader would stop, needed in some adapter subclasses"""
        pass
