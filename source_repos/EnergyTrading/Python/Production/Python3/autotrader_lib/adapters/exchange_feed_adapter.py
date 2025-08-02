import json
import time

import autotrader_lib.adapters.base_adapter as BA


# If the backtesting queue lag exceeds this high watermark, we log a debug message.
QUEUELAG_LOG_HWM = 3


class ExchangeFeedAdapter(BA.BaseAdapter):
    """
    This adapter is used to connect to an exchange feed file instead of a connection manager.

    As we cannot send anything to the file, this adpater should be used together with the ReadOnlySimulationAdapter.
    """
    def __init__(self, log, feed_filename, playback_speed):
        """

        :param log: A logger to log to.
        :type log: logging.Logger
        :param feed_filename: Filename of the file with the exchange feed.
        :type feed_filename: str
        :param playback_speed: autoTRADER's playback-speed. Only used to scale the adapter's idle sleep.
        :type playback_speed: float
        """
        log.info("Opening %s", feed_filename)
        self.feed_file = open(feed_filename)
        self.next_message = json.loads(next(self.feed_file))
        self.start_simulation_time = self.next_message["timestamp"]
        self.backtesting_simulation_complete = False
        self.playback_speed = playback_speed
        self.connected = not self.backtesting_simulation_complete
        # At startup, request 1 exchange restart, so autoTRADER can initialize the exchange.
        self._exchange_restart_needed = True
        super(ExchangeFeedAdapter, self).__init__(log, "ExchangeFeedAdapter", lambda: True)

    def send(self, body_dict, properties=None, **kwargs):
        """
        Never used, as there is no real exchange where we could send anything to...
        """
        pass

    def step(self, events, timestamp):
        """
        Receive the next message from the file, if it is already time for it.

        The message is sent to self._send_to_core, so nothing is returned.

        :param events: unused
        :type events: dict
        :param timestamp: The current timestamp in simulation time.
        :type timestamp: float
        """
        if self._exchange_restart_needed or self.backtesting_simulation_complete:
            return
        queue_lag = timestamp - self.next_message["timestamp"]
        if queue_lag < 0:
            # It is not yet the next message's turn.
            # Sleep a tiny bit to avoid wasting CPU on this thread and allow other threads to acquire the GIL,
            # but not too much, to correctly handle timer events and child messages.
            sleep_time = self._calculate_idle_sleep_time(-queue_lag)
            if sleep_time > 0.001:
                self._log.debug("Sleeping %s", sleep_time)
                time.sleep(sleep_time)
            return
        else:
            if queue_lag > QUEUELAG_LOG_HWM:
                self._log.info("Backtesting queue_lag is %s",
                               queue_lag)
            self._send_to_core({"body": self.next_message, "properties": {}})
            try:
                # Looping over the file using next is efficient. Quote from the documentation:
                # "In order to make a for loop the most efficient way of looping over the lines of a file
                # (a very common operation), the next() method uses a hidden read-ahead buffer"
                # https://docs.python.org/2.7/library/stdtypes.html#file.next
                self.next_message = json.loads(next(self.feed_file))
            except StopIteration:
                self._log.warning("End of simulation reached.")
                self.feed_file.close()
                self.backtesting_simulation_complete = True

    def _calculate_idle_sleep_time(self, wait_time):
        """
        If it is not yet the next message's turn, we sleep a tiny bit to
        :param wait_time: The time until the next message (in simulation time)
        :type wait_time: float
        :return: seconds to wait (in real wall clock time)
        :rtype: float
        """
        # The 0.2 corresponds to the adapter_poll_timeout in production
        # The division by the playback speed converts simulation time back to real time.
        return min(0.2 / self.playback_speed, -wait_time / (self.playback_speed))

    def requires_restart_of_exchange(self, events):
        """
        Checks if we need to restart the exchange.

        In backtesting, we only require a single restart at the beginning of the simulation
        :param events: Unused
        """
        # Request a single restart at startup, so the exchange gets initialized.
        if self._exchange_restart_needed:
            self._log.info("Exchange feed adapter requesting  exchange restart")
            self._exchange_restart_needed = False
            return True
        else:
            return False
