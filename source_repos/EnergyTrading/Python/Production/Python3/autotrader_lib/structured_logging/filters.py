import logging
import datetime


class SilenceFilter(logging.Filter):
    repeat_msg = " | repeated {}x within the last silence period ({} seconds, last at {})"

    def __init__(self, handlers, silence_window=60):
        """
        Constructor for silencing filter

        :param silence_window: for how many seconds should we silence a message
        :type silence_window: int
        :param handlers: To be able to print the previous message, we need a list of handlers from our logger
        :type handlers: list[logging.Handler]
        """
        self.handlers = handlers
        self.silence_window = silence_window

        self.last_check_timestamp = datetime.datetime.utcnow()
        self.latest_messages = {}

    def filter(self, record):
        """
        If this method returns True, the message will be forwarded to syslog, otherwise, the message is immediately
        discarded

        :param record: log record to examine if we silence or not
        :type record: logging.LogRecord
        :return: True if we want to log the message, otherwise False
        :rtype: bool
        """

        if "origin" not in record.__dict__.keys():
            # This is a "lost" message, we let it through and then syslog routing will most likely
            # discard it, unless we implement routing for messages that don't have a component specified
            return True

        origin = record.origin
        timestamp = datetime.datetime.utcnow()
        self.latest_messages.setdefault(origin, {})
        self.log_previous_msgs(timestamp, origin, record.created)  # check if any silence report needs to be logged
        message = self.extract_log_text_from_record(record)

        if message not in self.latest_messages[origin]:
            # If message is not tracked, we know we need to log it. Add it to tracking dict and return True
            self.latest_messages[origin][message] = {
                "record": record,
                "time": timestamp,
                "quantity": 0,
                "latest": datetime.datetime.utcfromtimestamp(record.created)
            }
            return True
        else:
            self.latest_messages[origin][message]["quantity"] += 1
            self.latest_messages[origin][message]["latest"] = datetime.datetime.utcfromtimestamp(record.created)
            return False

    def log_previous_msgs(self, timestamp, component, log_timestamp):
        """
        Iterate all silenced messages for this component, and check if silence report needs to be logged. I.e. if
        silence window amount of time passed since we started silencing this message.

        :param timestamp: A timestamp. We pass it to be able to sync with other methods. Mainly to avoid edge cases when
            execution time of this method might cause difference in calculated elapsed time in **filter()** method
        :type timestamp: datetime.datetime
        :param component: Component is a filed in our log records, syslog uses it to route messages to correct log files
        :type component: str
        :param log_timestamp: We use this to manually update the log timestamp to current time
        :type log_timestamp: int
        """
        if (timestamp - self.last_check_timestamp).seconds < (self.silence_window / 2):
            # this way we only check every 'half of silence window' amount of time
            return
        self.last_check_timestamp = timestamp

        to_delete = []
        for msg in self.latest_messages[component]:
            elapsed = (timestamp - self.latest_messages[component][msg]["time"]).seconds
            if elapsed >= self.silence_window:
                if self.latest_messages[component][msg]["quantity"]:
                    self.latest_messages[component][msg]["record"].created = log_timestamp
                    self.latest_messages[component][msg]["record"].msecs = (log_timestamp - int(log_timestamp)) * 1000
                    silence_report = self.repeat_msg.format(
                        self.latest_messages[component][msg]["quantity"],
                        self.silence_window,
                        self.latest_messages[component][msg]["latest"]
                    )
                    if isinstance(self.latest_messages[component][msg]["record"].msg, dict):
                        self.latest_messages[component][msg]["record"].msg["silence_report"] = silence_report
                    else:
                        self.latest_messages[component][msg]["record"].msg += silence_report
                    for handler in self.handlers:
                        handler.emit(self.latest_messages[component][msg]["record"])

                to_delete.append(msg)

        for msg in to_delete:
            del self.latest_messages[component][msg]

    def extract_log_text_from_record(self, record):
        """
        Our compliance logs accept both dicts and strings, so we need to take care of extracting the text message here

        :param record: A record being checked for silencing
        :type record: logging.LogRecord
        :return: Textual part of the log. In case of a dict we extract the "text" key.
        :rtype: str
        """
        if isinstance(record.msg, dict):
            try:
                message = self._item_to_tuple(record.msg)
            except Exception as _:
                for handler in self.handlers:
                    handler.emit(record)
                raise RuntimeError("Could not transform dict into a tuple")
        else:
            message = record.msg
        return message

    @classmethod
    def _item_to_tuple(cls, item):
        """
        A recursive helper method that transforms a dictionary into a tuple of tuples. The items of dictionary are
        sorted so it will allways be transformed in the same way.

        :param item: A dictionary to convert to a tuple. In reality, we just need it to be hashable so we can add it as
        a key to *self.latest_messages*
        :type item: dict
        :return: Tuple of tuples of sorted dictionary items
        :rtype: tuple
        """
        if isinstance(item, dict):
            tpl = ()
            for key, val in sorted(item.items()):
                tpl += ((key, cls._item_to_tuple(val)),)
        elif isinstance(item, list):
            tpl = (tuple([cls._item_to_tuple(i) for i in item]))
        else:
            tpl = (item)

        return tpl
