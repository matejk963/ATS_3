# -*- coding: utf-8 -*-


import abc
import calendar
import contextlib
import copy
import collections
import datetime
import errno
import functools
import glob
import inspect
import itertools
import json
import logging
import os
import random
import re
import shutil
import socket
import tempfile
import threading
import time
import types as T

import six
from six.moves import map
from six.moves import range

import autotrader_lib.common as COMMON

if six.PY2:
    import autotrader_lib.fast_logging_py2 as FLOG
else:
    import autotrader_lib.fast_logging_py3 as FLOG

log = FLOG.getLogger("autotrader_lib.util")


try:
    import lxml.etree
    import zmq
except ImportError:
    # at the moment we use this module for backtesting in windows environments with pypy
    # as it is not easy to install these dependencies there and they are not needed
    # for backtesting, we can ignore the error here.
    zmq = None
    lxml = None
    log.error("lxml.etree and zmq were not imported due to PyPy incompatibility.")

import autotrader_lib
import autotrader_lib.codec.msgpackcodec


class MsgExpired(Exception):
    pass


class ConfigError(Exception):
    pass


class ConnectionError(Exception):
    pass


class LoginError(Exception):
    pass


class TimeoutError(Exception):
    pass


class CriticalError(Exception):
    pass


class MessageTypeNotImplemented(Exception):
    pass


class InvalidDateFormatError(ValueError):
    pass


def is_close(first, second):
    return abs(first - second) < 1e-8


class WaitForItDataCollector(object):
    """
    A class to collect log messages.

    This class poassed by the wait_for_it decorator (when run with with_log=True) to the decorated function. The
    decorated function can then add data to it on every call. If wait_for_it raises a TimeoutError,
    then the log messages from this class are appended to the error message.
    """
    def __init__(self):
        self.loglist = []
        self.separator = ", "
        self.header = ""

    def append_log(self, message):
        """
        Add a message to the list of logs of this class.

        Used if the function wants data from every iteration to be logged.
        """
        self.loglist.append(message)

    def set_log(self, message):
        """
        Replace the existing list of logs by this single message.

        Used, if only data from the last iteration should be shown.
        """
        self.loglist = [message]

    def get_message(self):
        """
        Get a printable representation of the collected log messages
        :rtype: str
        """
        return " " + self.header + self.separator.join(map(str, self.loglist))

    def __nonzero__(self):
        return bool(self.loglist)


def get_logger(logger_name, default_level=logging.DEBUG):
    logger = logging.getLogger(logger_name)
    logger.setLevel(default_level)
    return logger


def is_sublist(expected, received, keep_relative_indexes=True):
    """
    Check if `expected` is a subset of `received`. If `keep_relative_indexes` is True, expected can be
    written from an `i` index like received[i, i+j]. Otherwise only the ordered elements in `expected`
    match the corresponding elements in `received`, ordered and unique, i.e. duplicate elements of `received`
    and elements existing only in `received` are ignored (duplicate elements in `expected` will never match).

    :type expected: list
    :type received: list
    :type keep_relative_indexes: bool
    :rtype: bool
    """
    # if we don't have the proper distinct elements, fail early
    if not set(expected).issubset(received):
        return False
    # if we need to retain the neighbouring relations, we simply use `expected` as a sliding window
    if keep_relative_indexes:
        for i in range(0, len(received) - len(expected) + 1):
            if expected == received[i:(i + len(expected))]:
                return True
        return False
    else:
        unique_sequence = []
        for el in received:
            if el in expected and el not in unique_sequence:
                unique_sequence.append(el)
        return unique_sequence == expected


def wait_for_it(timeout, with_log=False):
    """
    Helper function to execute func with a timeout.

    The decorated function is executed once every second until the timeout is reached, or the function returns
    True (indicating success).
    If the function returns always False (indicating "please try again later") until the timeout is reached, a
    TimeoutError is raised.

    If with_log is True, then the decorated function will be called with an additional Keyword argument
    "_log_collector" set to an instance of WaitForItDataCollector. The function can than use this data collector to
    add additional log data which will be shown as part part of the TimeoutError's message.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            log_list = WaitForItDataCollector()
            if with_log:
                kwargs["_log_collector"] = log_list
            for _ in range(timeout):
                result = func(*args, **kwargs)
                if result:
                    return result
                time.sleep(1)
            else:
                if six.PY2:
                    argspec = inspect.getargspec(func)
                else:
                    argspec = inspect.getfullargspec(func)
                # Include all args (except self) in the displayed function call.
                # argspec[0] is the list of argument names
                is_self = (argspec[0] and argspec[0][0] == "self")
                signature = [str(arg) for arg in args[is_self:]]
                # Add all keyword arguments, except _log_list, which is a detail of this decorator's implementation
                signature += ["{}={}".format(key, value) for key, value in kwargs.items() if key != "_log_collector"]
                raise TimeoutError("The execution of {}({}) took longer than {} seconds.{}".format(
                    func.__name__, ", ".join(signature), timeout, log_list.get_message()))
        return wrapper
    return decorator


class ExponentialStart(object):
    def __init__(self, start_file_path, logger):
        self.path = start_file_path
        self.waiting = 0
        self.logger = logger

    def __enter__(self):
        with open(self.path, "a") as fo:
            fo.write(str(time.time()) + "\n")

        with open(self.path) as fo:
            last_waitings = fo.readlines()[-2:]
        if len(last_waitings) != 2:
            pass
        else:
            next_to_last, last = [float(x.strip()) for x in last_waitings]
            last_waiting = last - next_to_last
            self.waiting = 2 * last_waiting + 60

    def __exit__(self, exc_type, value, traceback):
        self.logger.warning("EXITING: %s, %s, %s", exc_type, value, traceback)
        if not exc_type:
            try:
                if os.path.exists(self.path):
                    os.remove(self.path)
            except IOError as err:
                self.logger.error("Could not remove tempfile: %s", self.path)
                self.logger.error(err)
        else:
            self.logger.exception("Unhandled error")
            self.logger.debug("exponential waiting time because of error, "
                              "waiting {} seconds".format(round(self.waiting)))
            time.sleep(self.waiting)


class StoppableThread(threading.Thread):
    """Thread class with a stop() method"""

    def __init__(self, *args, **kwargs):
        super(StoppableThread, self).__init__(*args, **kwargs)
        self._should_stop = threading.Event()

    def stop(self):
        self._should_stop.set()

    def run(self):
        self._should_stop.wait()


def get_free_port():
    # type: () -> int
    """Return a single free port number to bind a server to"""
    return get_free_ports(1)[0]


def get_free_ports(num_ports):
    # type: (int) -> list[int]
    """Returns a list of free port numbers to bind a server to.

    Since acquiring a free port number and actually binding to it is not done atomically, the possibility of a race
    between two processes for the same free port exists. To mitigate this, the function touches a file in
    /tmp/autotrader_ports for each port number returned.
    Any file in that directory older than 2 hours is deleted when calling this function to ensure a continuous supply
    of free ports.
    """
    def _touch_file_mutex(file_path):
        """try to create the mutex file. returns True/False to indicate success."""
        try:
            # create the file only if it does not exist yet
            fd = os.open(file_path, os.O_CREAT | os.O_EXCL)
        except OSError as e:
            if e.errno == errno.EEXIST:
                return False
            else:
                raise
        else:
            # file created successfully - port should be free
            os.close(fd)
            return True

    base_mutex_dir = os.path.join(tempfile.mkdtemp(), "autotrader_ports")
    if not os.path.exists(base_mutex_dir):
        os.mkdir(base_mutex_dir)

    # delete port mutex files older than two hours
    current_time = time.time()
    for filepath in glob.glob(os.path.join(base_mutex_dir, "*")):
        if not os.path.isfile(filepath):
            continue
        modification_time = os.path.getmtime(filepath)
        if current_time - modification_time > 2 * COMMON.HOUR:
            log.debug("Removing tmp file: {}".format(filepath))
            os.unlink(filepath)

    ports = set()
    while len(ports) < num_ports:
        port = random.randint(10000, 30000)
        if port in ports:
            continue

        with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            result = sock.connect_ex(("localhost", port))
            if result == errno.ECONNREFUSED:
                port_mutex_path = os.path.join(base_mutex_dir, str(port))
                if _touch_file_mutex(port_mutex_path):
                    ports.add(port)

    return list(ports)


def touch_nagios_file(path):
    # type: (str) -> None
    if path:
        directory = os.path.dirname(path)
        if directory:
            try:
                os.makedirs(directory)
            except os.error as err:
                # we also get this if the directory already exists..
                if not os.path.isdir(directory):
                    log.error("cannot touch nagios path: {}".format(err))
                    return
        with open(path, "a"):
            os.utime(path, None)  # set mtime and atime to now


def copy_full_tree(from_destination, to_destination):
    """A helper function which copies a directory and its contents to another directory

    NOTE: Does not erase existing files in the folder in which we are copying

    Was made since existing shutil.copytree, is not good at handling existing locations
    https://bugs.python.org/issue20849
    https://stackoverflow.com/q/1868714
    https://stackoverflow.com/questions/15034151/copy-directory-contents-into-a-directory-with-python
    """
    for root, dirs, files in os.walk(from_destination):
        for curr_dir in dirs:
            rel_path = os.path.relpath(os.path.join(root, curr_dir), from_destination)
            make_path = os.path.join(to_destination, rel_path)
            if not os.path.exists(make_path):
                os.makedirs(make_path)
        for curr_file in files:
            rel_path = os.path.relpath(os.path.join(root, curr_file), from_destination)
            shutil.copy2(src=os.path.join(root, curr_file), dst=os.path.join(to_destination, rel_path))


def convert_string_to_dt(date_string, date_format):
    """
    Helper function to convert string to datetime with a given format string, trying not to use strptime.

    :param date_string: the string which represents the datetime to be converted
    :type date_string: str
    :param date_format: format string for strptime function
    :type date_format: str
    :return: the converted datetime
    :raises: InvalidDateFormatError on conversion errors
    :rtype: datetime.datetime
    """

    assignments = {
        "%Y-%m-%d": DTConv.str2y_m_d,
        "%Y-%m-%dT%H:%M:%S": DTConv.str2y_m_d_h_m_s,
        "%Y-%m-%dT%H:%M:%SZ": DTConv.str2y_m_d_h_m_s,
        "%Y%m%dT%H:%M:%S.%f": DTConv.str2ymd_h_m_s_f,
        "%Y%m%dT%H:%M:%S.%fZ": DTConv.str2ymd_h_m_s_f,
        "%Y-%m-%dT%H:%M:%S.%f": DTConv.str2y_m_d_h_m_s_f,
        "%Y-%m-%dT%H:%M:%S.%fZ": DTConv.str2y_m_d_h_m_s_f
    }
    used_fun = assignments.get(date_format, datetime.datetime.strptime)
    return used_fun(date_string, date_format)


def convert_to_timestamp(date_string, date_format):
    # type: (str, str) -> int
    """convert utc date string with date format to timestamp"""
    dt = convert_string_to_dt(date_string, date_format)
    return convert_dt_to_timestamp(dt)


def convert_to_float_timestamp(date_string, date_format):
    # type: (str, str) -> float
    """convert utc date string with date format to float timestamp"""
    dt = convert_string_to_dt(date_string, date_format)
    return convert_dt_to_float_timestamp(dt)


def convert_dt_to_timestamp(date):
    # type: (datetime.date) -> int
    """convert utc datetime to utc timestamp"""
    return calendar.timegm(date.timetuple())


def convert_dt_to_float_timestamp(date):
    # type: (datetime.datetime) -> float
    """convert utc datetime to float utc timestamp"""
    return calendar.timegm(date.timetuple()) + date.microsecond * 10e-7


def convert_dt_to_string(date, date_format):
    # type: (datetime.datetime, str) -> str
    """convert local datetime to utc date string"""
    # TODO: This is dangerous, it takes a local datetime date.
    # TODO: here CET to UTC conversion should be used since this is mostly used for epex messages
    timestamp = time.mktime(date.timetuple()) + date.microsecond * 10e-7
    return convert_from_timestamp(timestamp, date_format)


def convert_from_timestamp(timestamp, date_format):
    # type: (float | int, str) -> str
    """Convert utc timestamp to utc string"""
    return convert_utc_timestamp_to_dt(timestamp).strftime(date_format)


def convert_utc_timestamp_to_dt(timestamp):
    # type: (float | int) -> datetime.datetime
    """Convert utc timestamp to utc datetime"""
    return datetime.datetime.utcfromtimestamp(int(timestamp))


def make_xml_element(tag, parameters, children=None):
    # type: (str, dict, list[six.string_types]) -> str
    params = " ".join(["{}=\"{}\"".format(k, v.replace('"', "&quot;"))
                       for k, v in sorted(parameters.items())])
    if not children:
        return "<{tag} {params}/>".format(tag=tag, params=params)
    else:
        return "<{tag} {params}>{children}</{tag}>".format(
            tag=tag, params=params, children="\n".join(children))


def _escape_order_tag(tag):
    """
    Escape forbidden symbols inside order tags using the following rules:

    ':' is not allowed and irreversibly replaced by '?'
    '%' is reversibly replaced by '%%'
    '|' is reversibly replaced by '%P'

    :param tag: the string to escape
    :type tag: string
    :return: the escaped string
    :rtype: string
    """
    if isinstance(tag, six.string_types):
        if six.PY2:
            tag = tag.encode("utf-8")
        tag = tag.replace(":", "?").replace("%", "%%").replace("|", "%P")
    return tag


def _unescape_order_tag(tag):
    """
    Undo _escape_order_tag except for the irreversible step (':'->'?')

    :param tag: The escaped string
    :type tag: string
    :return: the unescaped string
    :rtype: string
    """
    # The ':'-character cannot be used inside the tag, so we use it as an intermediary character for our replacements.
    return tag.replace("%%", ":").replace("%P", "|").replace(":", "%")


def serialize_order_tags(tags, private=False):
    # type: (dict, bool) -> six.text_types
    internal_id = tags.get("internal_id", "")
    portfolio_key = tags.get("portfolio_key", "")
    portfolio_key = "" if portfolio_key is None else portfolio_key
    other_tags = ""
    for key, value in tags.items():
        if (key in ["internal_id", "portfolio_key"]) or (key.startswith("_")):
            continue
        key = _escape_order_tag(key)
        value = _escape_order_tag(value)
        other_tags += "|{}:{}".format(key, value)
    s = "{}|{}{}".format(internal_id, portfolio_key, other_tags)
    if six.PY2:
        s = s.decode("utf-8")
    return s


def parse_order_tags(tags):
    # type: (str) -> dict
    if not tags:
        return {}
    if isinstance(tags, str):
        if six.PY2:
            tags = tags.decode("utf-8")
    try:
        tag = json.loads(tags)
        if not isinstance(tag, dict):
            return {"text": six.text_type(tag)}
        return tag
    except Exception:
        parsed = {}
        splitted = tags.split("|")
        if len(splitted) == 1:
            return {"text": six.text_type(splitted[0])}
        for i, s in enumerate(splitted):
            if s != "":
                if i == 0:
                    parsed["internal_id"] = s
                elif i == 1:
                    parsed["portfolio_key"] = str(s)
                else:
                    try:
                        key, value = s.split(":")
                    except ValueError:
                        continue
                    key = _unescape_order_tag(key)
                    value = _unescape_order_tag(value)
                    parsed[key] = value
        return parsed


def convert_datestring(datestr):
    # type: (str or datetime.datetime) -> datetime.datetime or None
    if type(datestr) == datetime.datetime:
        return datestr
    try:
        if datestr and datestr.endswith("Z"):
            # we assume that all dates are in UTC
            datestr = datestr.replace("Z", "")
        # probe for isoformat with float element
        if "." in datestr:
            return DTConv.str2y_m_d_h_m_s_f(datestr, "%Y-%m-%dT%H:%M:%S.%f")
        else:
            return DTConv.str2y_m_d_h_m_s(datestr, "%Y-%m-%dT%H:%M:%S")
    except (TypeError, ValueError):
        return None


def memoize_with_dict(cache):
    def decorator(func):
        @functools.wraps(func)
        def call(*a):
            try:
                return cache[a]
            except KeyError:
                result = func(*a)
                cache[a] = result
                return result
        return call
    return decorator


def memoize(func):
    cache = {}
    return memoize_with_dict(cache)(func)


def handle_exchange_event(exchange, zmq_socket, handler, logger):
    """Handle events for the passed exchange communication of the passed zmq_socket
    :param exchange: Unique string describing the exchange (e.g. EPEX)
    :param zmq_socket: ZMQ socket used for communication
    :param handler: Handler of the received message
    :param logger: Logging Handler to be used
    """

    parts = zmq_socket.recv(flags=zmq.NOBLOCK)
    payload = None
    try:
        if len(parts) <= 1:
            raise autotrader_lib.SerializationError("envelope expected to comprise at least 2 parts")

        # Get message handler from cached handler list (create if needed)
        envelope_version = parts[0]
        envelope_handler = _get_exchange_handler(handler, envelope_version)

        payload = envelope_handler.handle(parts)
        payload_handler = handler.payload.for_version(payload["version"])
        payload_handler.handle(payload)
        return envelope_handler.repack(payload)
    except [autotrader_lib.SerializationError, AttributeError] as err:
        log.exception("cannot read invalid %s message", exchange)
        log.warning("cannot read invalid %s message: %s (%r)", exchange, err, parts)
    except MessageTypeNotImplemented as err:
        log.warning("not forwarding %s message: %r." % (exchange, err))
        log.debug("not forwarding message: %s: %r." % (err, parts))
    except Exception as err:
        stage = "envelope" if payload is None else "payload"
        log.warning("ignoring %s message (%s): %s." % (exchange, stage, err))
        log.debug("ignoring %s message (%s): %s: %r." % (exchange, stage, err, parts))


@memoize
def _get_exchange_handler(exchange, version):
    handler_cls = exchange.envelope.for_version(version)
    return handler_cls()


def coroutine(func):
    """Decorator which primes a coroutine func by advancing to first `yield`"""
    @functools.wraps(func)
    def prime(*args, **kwargs):
        """Prime the function"""
        gen = func(*args, **kwargs)
        next(gen)
        return gen
    return prime


class ManagerStatus(object):
    """Placeholder class for manager status update"""
    STATUS_CODES = dict(STARTING_MANAGER=1,
                        ONLINE=2,
                        CONNECTION_TEARDOWN=3,
                        NO_CONNECTION=4,
                        HALT=5)

    @classmethod
    def handle(cls, message, session):
        msg_type = message["type"]
        status = message["status"]
        if msg_type == "heartbeat":
            session.update(status["since"])
        elif msg_type == "change":
            return
        else:
            raise NotImplementedError(msg_type)


class XMLToDict(object):
    """Base class converting xml to a dict

    class holds function for easy parsing any given xml to a dict by providing a translation_map dict.

    To parse any xml to a dict use`parse_xml` function, which takes an xml, a tag to start parsing with and
    a translation map. Translation map is a dict of the specifying attributes and children of the provided tag.
    The dict has a recursive structure providing translations for any number of children, sub-children etc.

    :Example:

    Given the following xml structure:

        >>> xml_msg = '''<?xml version="1.0" encoding="utf-16"?>
        ...                  <GV8APIDATA xmlns="gv8api-trayport-com">
        ...                      <TERMFORMAT TermFormatID="1290213982" Type="Market">
        ...                         <TERM Label="Execution" Default="" Type="string" Phase="price" MaxLength="256">
        ...                           <FLAGS Read-only="0"/>
        ...                           <CONTROL Type="ComboboxString">blah</CONTROL>
        ...                         </TERM>
        ...                      </TERMFORMAT>
        ...                  </GV8APIDATA>/'''

        and for the following tranlsation_map
        >>> translation_map = {"attributes": {"term_format_id": ("TermFormatID", str),
        ...                                   "term_type": ("Type", six.text_type)},
        ...                    "children": {"TERM": {"name": "term",
        ...                                          "attributes": {"label": ("Label", str)},
        ...                                          "children": {"CONTROL": {"name": "control",
        ...                                                                   "attributes": {},
        ...                                                                   "children": {},
        ...                                                                   "text": True}}}}}

        The output of the `parse_xml` function will be
        >>> XMLToDict.parse_xml(xml_msg, "TERMFORMAT", translation_map)
        [{'term': [{'control': [{'value': 'blah'}], 'label': 'Execution'}],
          'term_format_id': '1290213982',
          'term_type': u'Market'}]

    Each translation map key under "attributes" corresponds to a translated xml tag, and each value is a tuple
    with a tag name and a callable, which is applied to the extracted attribute values of the xml.
    """

    @staticmethod
    def get_xml_tree(xml_msg):
        # in python 2.7 if xml_msg is str and contains unicode characters, encode throws ascii codec error
        if isinstance(xml_msg, six.text_type):
            xml_msg = xml_msg.encode("utf-8", errors="ignore")
        parser = lxml.etree.XMLParser(ns_clean=True, recover=True, encoding="utf-8")
        tree = lxml.etree.fromstring(xml_msg, parser=parser)
        try:
            nsmap = tree.nsmap[None]
        except KeyError:
            nsmap = ""
        return tree, nsmap

    @staticmethod
    def _get_element_info(entry, translation_map):
        """Helper function to obtain lxml element information following rules specified in translation map

        :param entry: xml Element of :class:`lxml.etree.Element` to be parsed
        :param dict translation_map: dict providing tranlation rules for the given entry Element
        :return: dict with translated keys and values
        """
        element = dict()
        for key, (attr_name, callback) in translation_map.items():
            value = entry.attrib.get(attr_name, None)
            if value and callable(callback):
                element[key] = callback(value)
            else:
                element[key] = value
        return element

    @classmethod
    def _build_dict(cls, tree, nsmap, tag_name, translation_map):
        """Helper function to recusirely drive the parsing of xml attributes and children elements

        :param tree: lxml.etree
        :param str nsmap: namespace prefix
        :param str tag_name: name of the tag to be parsed
        :param dict translation_map: dict providing tranlation rules for the given element
        :return: a list object with all parsed elements
        :rtype: list
        """
        data = []
        tree_iterator = tree.iter("{{{}}}{}".format(nsmap, tag_name))
        for entry in tree_iterator:
            element = {}
            if translation_map.get("attributes", False):
                element = cls._get_element_info(entry, translation_map["attributes"])
            if translation_map.get("text", False):
                element["value"] = "" if entry.text is None else entry.text
            if translation_map.get("children", False):
                for child_name, child_translation_map in translation_map["children"].items():
                    element[child_translation_map["name"]] = cls._build_dict(
                        entry, nsmap, child_name, child_translation_map)
            data.append(element)
        return data

    @classmethod
    def parse_xml(cls, xml_msg, starting_tag, translation_map):
        """

        :param str xml_msg: string with an xml
        :param str starting_tag: name of the tag to start parsing with
        :param dict translation_map: dict providing tranlation rules for the given xml
        :return: a list object with all parsed elements
        :rtype: list
        """
        tree, nsmap = cls.get_xml_tree(xml_msg)
        return cls._build_dict(tree, nsmap, starting_tag, translation_map)


def hour_to_delivery_by_ts(start):
    # type: (float) -> float
    """Get timestamp 1 hour before"""
    return start - 3600


def five_min_to_delivery_by_ts(start):
    # type: (float) -> float
    """Get timestamp 5 minutes before"""
    return start - COMMON.MINUTE * 5


def _delta_day(dt, days_diff):
    # type: (datetime.date, int) -> datetime.date
    """move date by days_diff days"""
    return dt + datetime.timedelta(days=days_diff)


def _delta_day_at(dt, days_diff, hour, minute, second):
    # type: (datetime.datetime, int, int, int, int) -> datetime.datetime
    """calculate datetimes at times of days relative to the passed datetime

    Examples:
    - yesterday at 15:00:
        - delta_day_at(dt, -1, 15)
    - tomorrow at 00:00
        - delta_day_at(dt, 1)
    """
    return datetime.datetime.combine(_delta_day(dt.date(), days_diff),
                                     datetime.time(hour=hour, minute=minute, second=second))


def delta_day_at(dt, days_diff=0, hour=0, minute=0, second=0):
    # type: (datetime.datetime, int, int, int, int) -> datetime.datetime
    """Move datetime by days_diff days to time of hours/minutes/second of target date"""
    return _delta_day_at(dt, days_diff, hour, minute, second)


def delta_minutes(dt, minutes):
    # type: (datetime.datetime, int) -> datetime.datetime
    """Move datetime by minutes"""
    return dt + datetime.timedelta(minutes=minutes)


def create_time_range(start_time, end_time):
    # type: (datetime.datetime, datetime.datetime) -> T.ListType[datetime.datetime]
    """Create time range in 15 minute steps from start_time to end_time"""
    times = []
    if start_time.minute % 15 != 0 or end_time.minute % 15 != 0:
        raise ValueError("products must start and end on full quarter hours")

    while start_time <= end_time:
        times.append(start_time)
        start_time += datetime.timedelta(minutes=15)
    return times


def replace_to_full_hour(datetime_object, hour):
    """
    Get a datetime object with the clock set to the given full hour, with support for hours >23.

    :param datetime_object: The datetime object of which a copy with the adjusted time will be returned
    :type datetime_object: datetime.datetime
    :param hour: The hour to which the clock will be set. Hours > 23 cause the day to be advanced as well...
    :type hour: int
    :return: The new datetime object
    :rtype: DT.datetime
    """
    days = 0
    while hour > 23:
        hour -= 24
        days += 1
    return datetime_object.replace(hour=hour, minute=0, second=0, microsecond=0) + datetime.timedelta(days=days)


def duration_check(delivery_start, delivery_end, _raise_value_error=True):
    # type: (float, float, bool) -> bool
    """Check validity of delivery start and delivery end"""
    duration = delivery_end - delivery_start
    if duration not in (COMMON.QUARTER, COMMON.HALF, COMMON.HOUR, 2 * COMMON.HOUR, 4 * COMMON.HOUR):
        if _raise_value_error:
            raise ValueError("product duration must be 15min, 30min, 60min, 120min or 240min, but was: {} minutes"
                             .format(duration / 60))
        else:
            return False
    if duration == COMMON.QUARTER and (delivery_end % COMMON.QUARTER != 0 or delivery_start % COMMON.QUARTER != 0):
        if _raise_value_error:
            raise ValueError("delivery start must by on a full quarter hour of any time")
        else:
            return False
    elif duration == COMMON.HALF and (delivery_end % COMMON.HALF != 0 or delivery_start % COMMON.HALF != 0):
        if _raise_value_error:
            raise ValueError(
                "delivery end and start must by on a full half hour of any time if the product duration is 30 minutes")
        else:
            return False
    elif duration in (COMMON.HOUR, 2 * COMMON.HOUR, 4 * COMMON.HOUR) and (delivery_end % COMMON.HOUR != 0
                                                                          or delivery_start % COMMON.HOUR != 0):
        if _raise_value_error:
            raise ValueError(
                "delivery end and start must by on a full hour of any time if the product duration is 1, 2 or 4 hours")
        else:
            return False
    return True


class DTConv:
    """
    This class collects custom conversion functions, which are converting to a datetime object.

    Conversions which try to replace datetime.datetime.strptime, follow these steps:
      a. Split strings by predefined positions, convert the parts to int and call datetime.datetime constructor.
      b. Do the same as above, but split by non-digit characters (regular expression is needed)
      c. If none of the above works, apply datetime.datetime.strptime

    Based on quick profilings, the performance relations between the three methods are approximately:
      a:b:c ~ 2:4:13

    TODO: Existing datetime converters can be moved here later, now it's not possible
    TODO: (because of backward compatibility of the strategy API)
    """

    @staticmethod
    def strptime_fallback(input_str, format_str, caught_err):
        """
        Backup function used in error handling to try the "old" strptime conversion before letting the error thrown.
        If format_str == None, it means that the error message in parameter should be forwarded.

        :param input_str: the string which represents the datetime to be converted
        :type input_str: str
        :param format_str: format string for strptime function
        :type format_str: str
        :param caught_err: Error object caught in error handling, it has to be thrown if format string is not given
        :type caught_err: Error or Exception
        :return: the converted datetime
        :raises: InvalidDateFormatError, when strptime is not required, or on conversion errors
        :rtype: datetime
        """

        if format_str is None:
            raise InvalidDateFormatError(caught_err)
        try:
            return datetime.datetime.strptime(input_str, format_str)
        except ValueError as ve:
            raise InvalidDateFormatError(ve)

    @staticmethod
    def str2y_m_d(datetime_str, format_str=None):
        """
        String to datetime converter for input matching originally the format string "%Y-%m-%d".
        Now it handles input matching the following regular expressions:
          - ideally: \\d{4}.\\d{2}.\\d+
          - still works: \\d+\\D\\d+\\D\\d+

        :param datetime_str: the string which represents the datetime to be converted
        :type datetime_str: str
        :param format_str: format string from the previous strptime function. If given, strptime backup should be tried.
        :type format_str: str
        :return: the converted datetime
        :raises: InvalidDateFormatError on conversion errors
        :rtype: datetime
        """

        # easiest and fastest conversion
        try:
            return datetime.datetime(int(datetime_str[:4]), int(datetime_str[5:7]), int(datetime_str[8:]))
        except ValueError:
            pass
        # if the above doesn't succeed, we try regular expressions, which is a bit slower
        try:
            digit_list = re.split(r"\D", datetime_str)
            if len(digit_list) != 3:
                raise InvalidDateFormatError("Not 3 arguments for datetime after regular expression split")
            return datetime.datetime(*list(map(int, digit_list)))
        except ValueError as ve:
            DTConv.strptime_fallback(datetime_str, format_str, ve)

    @staticmethod
    def str2y_m_d_h_m_s(datetime_str, format_str=None):
        """
        String to datetime converter for input matching originally the format string "%Y-%m-%dT%H:%M:%SZ".
        Now it handles input matching the following regular expressions:
          - ideally: \\d{4}.\\d{2}.\\d{2}.\\d{2}.\\d{2}.\\d+Z?
          - still works: \\d+\\D\\d+\\D\\d+\\D\\d+\\D\\d+\\D\\d+Z?

        :param datetime_str: the string which represents the datetime to be converted
        :type datetime_str: str
        :param format_str: format string from the previous strptime function. If given, strptime backup should be tried.
        :type format_str: str
        :return: the converted datetime
        :raises: InvalidDateFormatError on conversion errors
        :rtype: datetime.datetime
        """

        dt_string_wo_z = datetime_str.strip('Z')  # 'Z' at the end is not used, we convert to naive datetime objects
        # easiest and fastest conversion
        try:
            return datetime.datetime(int(dt_string_wo_z[:4]), int(dt_string_wo_z[5:7]), int(dt_string_wo_z[8:10]),
                                     int(dt_string_wo_z[11:13]), int(dt_string_wo_z[14:16]), int(dt_string_wo_z[17:]))
        except ValueError:
            pass
        # if the above doesn't succeed, we try regular expressions, which is a bit slower
        try:
            digit_list = re.split(r"\D", dt_string_wo_z)
            if len(digit_list) != 6:
                raise InvalidDateFormatError("Not 6 arguments for datetime after regular expression split")
            return datetime.datetime(*list(map(int, digit_list)))
        except ValueError as ve:
            DTConv.strptime_fallback(datetime_str, format_str, ve)

    @staticmethod
    def str2ymd_h_m_s_f(datetime_str, format_str=None):
        """
        String to datetime converter for input matching originally the format string "%Y%m%dT%H:%M:%S.%fZ".
        Now it handles input matching the following regular expressions:
          - ideally: \\d{4}\\d{2}\\d{2}.\\d{2}.\\d{2}.\\d{2}.\\d+Z?
          - still works: \\d+{7,8}\\D\\d+\\D\\d+\\D\\d+\\D\\d+Z?

        :param datetime_str: the string which represents the datetime to be converted
        :type datetime_str: str
        :param format_str: format string from the previous strptime function. If given, strptime backup should be tried.
        :type format_str: str
        :return: the converted datetime
        :raises: InvalidDateFormatError on conversion errors
        :rtype: datetime
        """

        dt_string_wo_z = datetime_str.strip('Z')  # 'Z' at the end is not used, we convert to naive datetime objects
        # easiest and fastest conversion
        try:
            return datetime.datetime(int(dt_string_wo_z[:4]), int(dt_string_wo_z[4:6]), int(dt_string_wo_z[6:8]),
                                     int(dt_string_wo_z[9:11]), int(dt_string_wo_z[12:14]), int(dt_string_wo_z[15:17]),
                                     int(dt_string_wo_z[18:].ljust(6, '0')))
        except ValueError:
            pass
        # if the above doesn't succeed, we try regular expressions, which is a bit slower
        try:
            digit_list = re.split(r"\D", dt_string_wo_z)
            if len(digit_list) != 5:
                raise InvalidDateFormatError("Not 5 arguments for datetime after regular expression split")
            return datetime.datetime(int(digit_list[0][:4]), int(digit_list[0][4:6]), int(digit_list[0][6:]),
                                     int(digit_list[1]), int(digit_list[2]), int(digit_list[3]),
                                     int(digit_list[4].ljust(6, '0')))
        except ValueError as ve:
            DTConv.strptime_fallback(datetime_str, format_str, ve)

    @staticmethod
    def str2y_m_d_h_m_s_f(datetime_str, format_str=None):
        """
        String to datetime converter for input matching originally the format string "%Y-%m-%dT%H:%M:%S.%fZ".
        Now it handles input matching the following regular expressions:
          - ideally: \\d{4}.\\d{2}.\\d{2}.\\d{2}.\\d{2}.\\d{2}.\\d+Z?
          - still works: \\d+\\D\\d+\\D\\d+\\D\\d+\\D\\d+\\D\\d+\\D\\d+Z?

        :param datetime_str: the string which represents the datetime to be converted
        :type datetime_str: str
        :param format_str: format string from the previous strptime function. If given, strptime backup should be tried.
        :type format_str: str
        :return: the converted datetime
        :raises: InvalidDateFormatError on conversion errors
        :rtype: datetime
        """

        dt_string_wo_z = datetime_str.strip('Z')  # 'Z' at the end is not used, we convert to naive datetime objects
        # easiest and fastest conversion
        try:
            return datetime.datetime(int(dt_string_wo_z[:4]), int(dt_string_wo_z[5:7]), int(dt_string_wo_z[8:10]),
                                     int(dt_string_wo_z[11:13]), int(dt_string_wo_z[14:16]), int(dt_string_wo_z[17:19]),
                                     int(dt_string_wo_z[20:].ljust(6, '0')))
        except ValueError:
            pass
        # if the above doesn't succeed, we try regular expressions, which is a bit slower
        try:
            digit_list = re.split(r"\D", dt_string_wo_z)
            if len(digit_list) != 7:
                raise InvalidDateFormatError("Not 7 arguments for datetime after regular expression split")
            return datetime.datetime(int(digit_list[0]), int(digit_list[1]), int(digit_list[2]),
                                     int(digit_list[3]), int(digit_list[4]), int(digit_list[5]),
                                     int(digit_list[6].ljust(6, '0')))
        except ValueError as ve:
            DTConv.strptime_fallback(datetime_str, format_str, ve)


def sanitize_msg(msg):
    """
    Removes sensitive information from log messages.

    :param msg: message object to be logged
    :type msg: dict
    :rtype: dict
    """
    msg = copy.deepcopy(msg)  # otherwise we change the object to be sent to the exchange
    if msg["body"]["message_type"] == COMMON.Request.change_password:
        del msg["body"]["body"]["old_password"]
        del msg["body"]["body"]["new_password"]
    return msg


def silence_logs(current_counter, message, logger, maximum_counter=1000):
    """
    Helper function to avoid too many warning logs for certain scenarios
    :param current_counter: The counter to compare to the maximum counter
    :type current_counter: int
    :param message: The WARNING log's message
    :type message: str
    :param logger: The logger object to write the WARNING log with
    :param maximum_counter: The limit after how many calls the WARNING log should be written
    :type maximum_counter: int
    :return: The incremented call count, or 1 if the log is written
    :rtype: int
    """
    if current_counter % maximum_counter == 0:
        logger.warning(message)
        return 1
    current_counter += 1
    return current_counter


class TrayportRouteHelper(object):
    """
    Helper Class with methods and consts for routes to market
    """

    multiple_routes_configured = "multiple_routes"
    multiple_routes_detected = "multiple_routes_detected"
    route_automatically_detected = "detected_route"
    route_not_allowed = "route_not_allowed"
    route_is_set = "route_is_set"
    no_allowed_routes = "no_allowed_routes"

    @staticmethod
    def validate_route(configured_routes, allowed_routes):
        """
        Validates configured routes, and returns route id to be used as default and corresponding event name

        :param configured_routes: non-empty list of routes from system.cfg
        :type configured_routes: list(str)
        :param allowed_routes: list of routes received from JD
        :type allowed_routes: list(str)
        :returns: tuple with route id to be used as default and corresponding event name
        :rtype: str, str
        """

        default_route = None
        event = None

        # even if routes are not configured, we should receive at least a list with one empty element [""]
        if not configured_routes:
            raise ValueError("The list of configured routes should be at least of length 1")

        # check for having only one route configured in system.cfg
        # remove to allow multiple routes; but in this case do not forget to add either default value or some logic
        # how to select the route when placing orders etc
        if len(configured_routes) > 1:
            event = TrayportRouteHelper.multiple_routes_configured

        # no route specified in system.cfg
        elif configured_routes[0] == "":
            # no allowed routes
            if tuple(allowed_routes) in ((), ("",)):
                event = TrayportRouteHelper.no_allowed_routes
            # in case there is the only allowed route, set it up as default
            elif len(allowed_routes) == 1:
                default_route = allowed_routes[0]
                event = TrayportRouteHelper.route_automatically_detected
            # there is more than one allowed route
            else:
                event = TrayportRouteHelper.multiple_routes_detected

        # wrong route id specified in system.cfg
        elif configured_routes[0] not in allowed_routes:
            event = TrayportRouteHelper.route_not_allowed

        # in config there is the only route id which is allowed
        else:
            default_route = configured_routes[0]
            event = TrayportRouteHelper.route_is_set

        return default_route, event


def round_float(float_number, precision=COMMON.FLOAT_ROUNDING_PRECISION):
    """
    Rounds a float number to defined precision.
    Sometimes fields like "price" if not set up are passed as "None";
    rounding does not happen in this case and None is returned.
    :param float_number: a number to round
    :type float_number: float or None
    :param precision: precision for rounding
    :type precision: int
    :return: rounded float number or None
    :rtype: float or None
    """
    return round(float_number, precision) if float_number is not None else float_number


def round_qty_to_ticksize(quantity, tick):
    """
    Helper function to round a quantity down to the closest multiple of the tick size
    :type quantity: float or int
    :type tick: float or int
    :rtype: float
    """
    return round((quantity + 10 ** -COMMON.FLOAT_ROUNDING_PRECISION) // tick * tick, COMMON.FLOAT_ROUNDING_PRECISION)


def extract_data_from_correlation_id(message_struct, label):
    """extract a string from the correlation_id of the message. The string must include the label in its text.

    :param message_struct: The received message dict
    :type message_struct: dict
    :param label: unique label of the data to be extracted
    :type label: str
    :return: The data (including the label) or None if not found
    :rtype: str or None
    """
    correlation_id = message_struct.get("correlation_id", "")
    fields = correlation_id.split('|')
    for field in fields:
        if label in field:
            return field
    return None


def append_correlation_id_data(correlation_id, data_str):
    """Append the given data string to the given correlation_id.

    :param correlation_id: Existing correlation_id
    :type correlation_id: str
    :param data_str: Data to add
    :type data_str: str
    :return: New correlation_id
    :rtype: str
    """
    if correlation_id:
        return correlation_id + '|' + data_str
    return data_str


class ActionRateParameters(object):

    _attributes = tuple()  # Override this with whatever attributes are used in the child class for storing parameters
    limit_type = None  # type: str

    def _apply_data(self, data, initiate_empty):
        for key in self._data_keys:
            if initiate_empty or data.get(key) is not None:
                setattr(self, key, data.get(key))

    @staticmethod
    def _percent(current, limit):
        return (float(current) / limit if limit else 1) * 100.

    def __init__(self, **kwargs):
        # Attributes that will be in the generated JSON
        self._data_keys = tuple(s for s in self._attributes if not s.startswith("_")) + ("limit_type", )
        self._apply_data(kwargs, True)

    def from_dict(self, data):
        """Fill parameters from a dict

        :param data: the data that should be assigned, partial data is accepted
        :type data: dict
        :return: itself
        :rtype: ActionRateParameters
        """
        if isinstance(data, dict):
            self._apply_data(data, False)
        return self

    def to_dict(self, skip_none=False):  # type: (bool) -> dict[str, any]
        """Generates a json dict from itself for messaging and persistence

        :param skip_none: whether to exclude attributes that have a None value
        """
        return {key: getattr(self, key) for key in self._data_keys if not skip_none or getattr(self, key) is not None}

    @abc.abstractproperty
    def current_level(self):
        pass


class BaseOMTParameters(ActionRateParameters):
    """Basic OMT parameters, only contains values that are from the exchange. Used for transferring the data."""

    _attributes = (
        "received_omt",
        "observation_period",
        "tolerance_period",
        "cooldown_period",
        "lower_threshold",
        "upper_threshold",
        "status",
    )

    received_omt = None  # type: int
    observation_period = None  # type: int
    tolerance_period = None  # type: int
    cooldown_period = None  # type: int
    lower_threshold = None  # type: int
    upper_threshold = None  # type: int
    status = None  # type: str

    def to_dict(self, from_exchange=False):  # type: (bool) -> dict[str, any]
        data = super(BaseOMTParameters, self).to_dict(skip_none=from_exchange)
        if from_exchange:
            data["from_exchange"] = True
        return data


class OMTParameters(BaseOMTParameters):
    """Used for storing and transferring OMT parameters and current status.

    lower_threshold (int) = L1
    upper_threshold (int) = L2

    received_omt (int): Is the current OMT received in the Throttling Status Messages.
                        This value could be a few seconds old, not recommended for use in strategies.

    current_level (int): The locally calculated value. Always up to date. Recommended for use in strategies.
                         Ack-Messages from the EPEX are used to calculate this value. So it can still lag a bit behind,
                         depending on queue_lag.
                         If the received_omt from EPEX is higher as the calculated_omt the difference is seamlessly
                         added to calculated_omt. Therefore, there is no need to check received_omt for comparing it
                         to the limits.

    observation_period (int): The time frame spanning all buckets. Request that are older than this time span don't
                              count towards omt anymore.

    tolerance_period (int): The maximum time the OMT may be between L1 and L2 and requests will still be resolved.
                            -> WARNING State
                            After this time span (or after reaching L2) all further requests will resolve to an Error.
                            (These requests still count towards OMT.)
                            -> RESTRICTED State


    cooldown_period (int): The time (after reaching the Restricted state AND falling back under L1) after which requests
                           will be accepted again. -> NO_RESTRICTION State (default)

    status (string): tells the current state from the exchange (only updated with every throttling status response)

    exchange_difference (int): The difference of locally calculated OMT compared to the received_omt, will be 0 if
                               received_omt is lower than the locally calculated OMT

    cooldown_end_ts (float): The estimated end time of the cooldown after reaching the RESTRICTED state, after this
                             cooldown timestamp the state is expected to be NO_RESTRICTION

    tolerance_end_ts (float): The estimated end time of the tolerance while in WARNING state, after this timestamp the
                              state is going to change to RESTRICTED, unless the OMT gets back under L1

    recovery_target (int): After reaching BLOCKING state, how low does the omt need to go to get back to NON_BLOCKING

    throttling_status (string): The current state of autotrader throttling. NON_BLOCKING or BLOCKING

    epex_status_since (float): Timestamp when the status was last changed.

    throttling_status_since (float): Timestamp when the throttling_status was last changed.

    throttling_threshold (int): The threshold when autotrader starts blocking requests, configurable using the
                                short_throttling_limit/long_throttling_limit
    """

    _attributes = (
        "_calculated_omt",
        "exchange_difference",
        "cooldown_end_ts",
        "tolerance_end_ts",
        "recovery_target",
        "throttling_status",
        "epex_status_since",
        "throttling_status_since",
        "throttling_threshold",
    ) + BaseOMTParameters._attributes

    exchange_difference = None  # type: int
    cooldown_end_ts = None  # type: float
    tolerance_end_ts = None  # type: float
    recovery_target = None  # type: int
    throttling_status = None  # type: str
    epex_status_since = None  # type: float
    throttling_status_since = None  # type: float
    throttling_threshold = None  # type: int

    def __init__(self, **kwargs):
        super(OMTParameters, self).__init__(**kwargs)
        self._calculated_omt = 0

    def to_dict(self, from_exchange=False):
        """Generates a json dict from itself

        If from_exchange is True: adds from_exchange field to json. Additionally skip all attributes without values.
        Otherwise adds calculated_omt field.

        :param from_exchange: set to true if this data came from the exchange, defaults to False
        :type from_exchange: bool, optional
        :return: generated json dict
        :rtype: dict
        """
        data = super(OMTParameters, self).to_dict(from_exchange)
        if not from_exchange:
            data["calculated_omt"] = self.current_level
        return data

    @property
    def current_level(self):  # type: () -> int
        """Current OMT value"""
        return self._calculated_omt

    @property
    def l1_percent(self):
        """Returns the current percent of L1 (lower_threshold) reached.

        If the lower_threshold is None, 100 will be returned, as we don't want the strategy to trade yet if the
        parameters from the exchange haven't been received.
        If the lower_threshold is 0, 100 will be returned as we evaluate 0 as we can't trade. Note: during the trial
        phase, the "unlimited" threshold given by the exchange was 999999, therefore we assume 0 doesn't mean unlimited.

        :return: Percent of lower_threshold reached with calculated_omt
        :rtype: float
        """
        return self._percent(self.current_level, self.lower_threshold)


def get_list(setting, elem_type=str):
    # type: (str, any) -> list
    if isinstance(setting, list):
        return setting
    elif isinstance(setting, six.string_types):
        if setting == "":
            return []
        return [elem_type(x.strip()) for x in setting.split(",")]
    else:
        return []


get_int_list = functools.partial(get_list, elem_type=int)


def get_exchange_child_distribution(at_config):
    """
    Calculates how the child_ids are distributed by exchange
    from config values num_child_processes, {epex,trayport,nordpool}_child_ids
    :param at_config: current timestamp
    :type at_config: ATCONF.ATConfig
    :returns: distribution by exchange or None if misconfigured
    :rtype: dict
    """
    num_child_processes = int(at_config.num_child_processes)
    free_children = set(range(0, num_child_processes))
    distribution = dict.fromkeys(["EPEX", "TRAYPORT", "NORD"], None)

    # in sysconfig, number of "nordpool" child ids is referred to as nordpool_child_ids,
    # however in internal processing, nordpool is referred to as "nord"
    exchange_name_to_sysconfig_name = {
        "epex": "epex",
        "trayport": "trayport",
        "nord": "nordpool"
    }
    exchange_valid = dict()
    # calculate available children and set children for the exchanges
    for exchange in list(distribution.keys()):
        exchange_valid[exchange] = getattr(at_config, exchange_name_to_sysconfig_name[exchange.lower()])
        if not exchange_valid[exchange]:
            distribution[exchange] = []
            continue
        assigned_child_ids = sorted(get_int_list(getattr(at_config, "{}_child_ids".format(
            exchange_name_to_sysconfig_name[exchange.lower()]), [])))
        free_children.difference_update(assigned_child_ids)
        distribution[exchange] = assigned_child_ids
        if len(assigned_child_ids) > 0 and max(distribution[exchange]) >= num_child_processes:
            msg = ("{}_child_ids configuration is invalid!"
                   " Trying to add child {} when there are only {} children available."
                   .format(exchange.lower(), max(distribution[exchange]), num_child_processes))
            log.critical(msg)
            raise ConfigError(msg)

    for exchange, assigned_child_ids in distribution.items():
        if exchange_valid[exchange]:
            if len(assigned_child_ids) == 0:
                # If no free children are available, we raise an issue
                if len(free_children) == 0:
                    msg = ("No child configured for {}_child_ids configuration!".format(
                        exchange_name_to_sysconfig_name[exchange.lower()]))
                    log.critical(msg)
                    raise ConfigError(msg)
            else:
                for child_id in assigned_child_ids:
                    if child_id < 0:
                        msg = ("Negative value child configured for {}_child_ids configuration!".format(
                            exchange_name_to_sysconfig_name[exchange.lower()]))
                        log.critical(msg)
                        raise ConfigError(msg)
            if not distribution[exchange]:
                distribution[exchange] = list(free_children)
        else:
            distribution[exchange] = []

    if not any(exchange_valid.values()):
        return distribution

    # check that all children are assigned correctly on valid exchanges
    used_children = set(itertools.chain.from_iterable(list(distribution.values())))
    if not free_children.issubset(used_children):
        msg = ("children {} are not configured correctly. Please assign them to an exchange."
               .format(list(free_children)))
        log.critical(msg)
        raise ConfigError(msg)

    return distribution


def swap_to_child_exchange_dist(num_child_processes, exchange_child_distribution):
    """
    Converts the exchange_child_distribution dict, so one could search for the child_id and get
    all available exchanges

    :param num_child_processes:
    :type num_child_processes: int
    :param exchange_child_distribution: exchanges as key, available childs for the exchange as value
    :type exchange_child_distribution: dict
    :return: child as keys and available exchanges for the child as value
    :rtype: dict
    """
    distribution = collections.defaultdict(set)
    for exchange, child_ids in exchange_child_distribution.items():
        for child_id in range(0, num_child_processes):
            if child_id in child_ids:
                distribution[child_id].add(exchange)
    return distribution


def get_regions(sell_delivery_area, buy_delivery_area, exchange_id):
    """helper function that returns the regions for a delivery area which is a union of zones and areas"""
    zones = set([COMMON.Area.get_zone(sell_delivery_area, exchange_id),
                 COMMON.Area.get_zone(buy_delivery_area, exchange_id)])
    areas = set([buy_delivery_area, sell_delivery_area])
    return {el for el in zones | areas if el is not None and el != ""}


def is_file_last_modified_within(file_path, time_window):
    """
    Checks if mtime of file described by path is within provided time_window
    :param file_path: path to file
    :type file_path: str
    :param time_window: threshold [s], was the file modified between now and this many seconds ago
    :type time_window: int | float
    :return: tuple containing boolean flag signalling whether file is within time_window or not,
             and the file's mtime as float or None if no file was found
    :rtype: tuple[bool, float|None]
    """
    if not os.path.isfile(file_path):
        log.warning("File not found at '{p}'!".format(p=file_path))
        return False, None

    file_mtime = os.path.getmtime(file_path)  # time of last modification of the file
    file_modified = (time.time() - time_window) <= file_mtime  # was the file modified within the time window

    return file_modified, file_mtime
