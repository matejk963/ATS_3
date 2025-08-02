import logging
import six
import time
import sys


class JsonFormatter(logging.Formatter):
    """
    Logging.formatter that returns a dictionary instead of a string. It overwrites the formatTime method as well to make
    the time compatible with autotrader log standard.
    """
    def __init__(self, fmt=None, datefmt="%Y-%m-%dT%H:%M:%S", msec_format="%s.%03d"):
        if six.PY3 and sys.version_info >= (3, 8):
            super(JsonFormatter, self).__init__(fmt, datefmt, validate=False)
        else:
            super(JsonFormatter, self).__init__(fmt, datefmt)
        self.fmt_dict = fmt if fmt is not None else {"message": "message"}
        self.default_time_format = datefmt
        self.default_msec_format = msec_format
        self.datefmt = None
        self.converter = time.gmtime

    def usesTime(self):
        """
        Overwritten to look for the attribute in the format dict values instead of the fmt string.
        """
        return "asctime" in self.fmt_dict.values()

    def formatTime(self, record, datefmt=None):
        """
        Return the creation time of the specified LogRecord as formatted text.

        This method should be called from format() by a formatter which
        wants to make use of a formatted time. This method can be overridden
        in formatters to provide for any specific requirement, but the
        basic behaviour is as follows: if datefmt (a string) is specified,
        it is used with time.strftime() to format the creation time of the
        record. Otherwise, the ISO8601 format is used. The resulting
        string is returned. This function uses a user-configurable function
        to convert the creation time to a tuple. By default, time.localtime()
        is used; to change this for a particular formatter instance, set the
        'converter' attribute to a function with the same signature as
        time.localtime() or time.gmtime(). To change it for all formatters,
        for example if you want all logging times to be shown in GMT,
        set the 'converter' attribute in the Formatter class.
        """
        ct = self.converter(record.created)
        if datefmt:
            s = time.strftime(datefmt, ct)
        else:
            t = time.strftime("%Y-%m-%dT%H:%M:%S", ct)
            s = "%s.%03d" % (t, record.msecs)
        return s

    def formatMessage(self, record):
        """
        Overwritten to return a dictionary of the relevant LogRecord attributes instead of a string.
        KeyError is raised if an unknown attribute is provided in the fmt_dict.

        :param record: A record to be processed
        :type record: logging.LogRecord
        :return: Dict containing at least all keys specified in logging.yml section for this formatter
        :rtype: dict
        """
        return {fmt_key: record.__dict__[fmt_val] for fmt_key, fmt_val in self.fmt_dict.items()}

    def format(self, record):
        """
        Mostly the same as the parent's class method, the difference being that a dict is manipulated and dumped as JSON
        instead of a string.

        :param record: A record to be processed
        :type record: logging.LogRecord
        :return: Dictionary with all relevant fields extracted from log record
        :rtype: dict
        """
        record.message = record.getMessage()

        if self.usesTime():
            record.asctime = self.formatTime(record, self.datefmt)

        message_dict = self.formatMessage(record)

        if record.exc_info:
            # Cache the traceback text to avoid converting it multiple times
            # (it's constant anyway)
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)

        if record.exc_text:
            message_dict["exc_info"] = record.exc_text

        return message_dict


class ConsoleJsonFormatter(JsonFormatter):
    """
    Logging.formatter that outputs logs in compliance with autotrader log standard. The only difference being that the
    message is in form of a dict rather than a string.
    """

    def __init__(self, fmt=None, datefmt="%Y-%m-%dT%H:%M:%S"):
        super(ConsoleJsonFormatter, self).__init__(fmt, datefmt)

    def format(self, record):
        """
        Mostly the same as the parent's class method, the difference being that string representation of the dict is
        returned

        :param record: A record to be processed
        :type record: logging.LogRecord
        :return: String formatted to standard autotrader log format
        :rtype: str
        """

        return "%s [%s] %s %s" % (record.asctime, record.component, record.levelname, record.msg)
