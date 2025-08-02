#!/usr/bin/python3
# -*- coding: utf-8 -*-
import atexit
import collections
import datetime
import errno
import json
import os
import sys
import threading
import time
import traceback

import autotrader_lib.compliance_log_templates as LOGTEMP
import autotrader_lib.version as ATVER

NOW = datetime.datetime.now
NOW_UTC = datetime.datetime.utcnow
FORCE_ROTATION_INTERVAL = 4 * 60 * 60


class FastLoggingImporter(object):
    """Importer class for making this module the only logging module in this realm."""

    def find_module(self, fullname, unused_path=None):
        if fullname == "logging":
            return self
        return None

    @staticmethod
    def load_module(unused_fullname):
        return sys.modules[__name__]


# global switch that turns off and on the logging to stdout - additionally to the logfile
log_to_stdout = False

# module private members
_filename = ""
_file_pointer = None
_file_base_path = ""
_counter = 0
_rotation_line_count = 3000000
_next_rotation_timestamp = float("inf")  # no rotation until this is set.
_force_daily_rotation_compliance = NOW_UTC().day
# initially, flush after every entry. When switching to logfile in setup, that setting is increased.
# Before that, the background flushing thread is not yet active and we want to see the lines in stdout.
_cached_lines = 1

_entries = []
_lock = threading.Lock()
_flushing_thread = None

_filename_json = ""
_file_pointer_json = None
_counter_json = 0
_rotation_line_count_json = 3000000

_entries_json = []
_silence_time = 60  # seconds
# text and timestamp as key and object as value
_silence_entries_obj = {}
_silence_entries_counter = collections.defaultdict(collections.Counter)
_lock_json = threading.Lock()

_silence_msg = "| repeated {}x within the last silence period ({} seconds, last at {})"

_last_flush_timestamp = 0.

_run_thread = True

_server_role = ""

INFO = "INFO"
DEBUG = "DEBUG"
WARNING = "WARNING"
ERROR = "ERROR"


# TODO: datetime.isoformat() is still the fastest way to produce timestamp string, with datetime.now() being the
#       bottleneck. Implement a function in c that does time.time() and from that directly produces the string
#       with split-seconds. That will me MUCH faster. Maybe do the formatting in C as well

def reset_to_defaults():
    """reset all global used variables to their default values"""
    global log_to_stdout, _filename, _file_pointer, _file_base_path, _counter, _rotation_line_count
    global _next_rotation_timestamp, _cached_lines, _entries, _lock, _flushing_thread, _filename_json
    global _file_pointer_json, _counter_json, _rotation_line_count_json, _entries_json, _silence_entries_counter
    global _lock_json, _last_flush_timestamp, _run_thread, _server_role, _silence_time, _silence_entries_obj

    log_to_stdout = False
    _filename = ""
    _file_pointer = None
    _file_base_path = ""
    _counter = 0
    _rotation_line_count = 3000000
    _next_rotation_timestamp = float("inf")
    _cached_lines = 1
    _entries = []
    _lock = threading.Lock()
    _flushing_thread = None
    _filename_json = ""
    _file_pointer_json = None
    _counter_json = 0
    _rotation_line_count_json = 3000000
    _entries_json = []
    _silence_entries_counter = collections.defaultdict(collections.Counter)
    _silence_entries_obj = {}
    _lock_json = threading.Lock()
    _last_flush_timestamp = 0.
    _run_thread = True
    _server_role = ""
    _silence_time = 60


def set_server_role(role):
    """
    Sets server role from outer module
    :param role: server role from the config
    :type role: str
    """
    global _server_role
    _server_role = role


def get_server_role():
    """
    Gets server role for outer module
    :return: server role from the config
    :rtype: str
    """
    global _server_role
    return _server_role


def _get_complex_filename(filename, on_startup=False):
    """
    Return the log filename path followed by the date - for rotation.
    Appends a "C" for "Crash" to the filename, if the rotation was triggered on a restart.
    :param filename: name of the file
    :type filename: str
    :param on_startup: flag telling is a function called on startup
    :type on_startup: bool
    :return: log file name with the date
    :rtype: str
    """
    return os.path.join(
        _get_filename(filename) + "." + NOW().isoformat().replace(":", "_") + ("C" if on_startup else ""))


def _get_filename(filename):
    """
    Return the log filename path
    :param filename: name of the file
    :type filename: str
    :return: log file name
    :rtype: str
    """
    return os.path.join(_file_base_path, filename)


def _rotate_file(filename, on_startup=False):
    """Rename file from base version to version with date in it."""
    try:
        os.rename(_get_filename(filename), _get_complex_filename(filename, on_startup))
    except OSError as error:
        # Ignore only "No such file or directory" errors, which happen on startup.
        if error.errno != errno.ENOENT:
            raise


def _rotate_file_log(filename, on_startup=False):
    """rotate the compliance log and set a new timestamp for the next rotation"""
    _rotate_file(filename, on_startup)
    global _next_rotation_timestamp
    _next_rotation_timestamp = time.time() + FORCE_ROTATION_INTERVAL


def _rotate_file_compliancelog(filename, on_startup=False):
    """rotate the compliance log and set the day when file was rotated"""
    _rotate_file(filename, on_startup)
    global _force_daily_rotation_compliance
    _force_daily_rotation_compliance = NOW_UTC().day


def last_flush():
    """Return the last autoflushing time as unix timestamp."""
    return _last_flush_timestamp


def _flushing_thread_target():
    """Target for the autoflushing thread. Every 5 seconds, a flush is triggered,
    no matter how much log traffic we have."""
    global _last_flush_timestamp, _run_thread
    flushing_logger = Logger("log_flushing")
    while _run_thread:
        start = time.time()
        flushing_logger.debug("Flushing log")
        n_lines = flushing_logger.conditional_flush_and_rotate()
        n_compl_lines = flushing_logger.compliance_flush_and_rotate()
        flushing_logger.debug("Flushing log finished n_lines: %s, n_compl_lines %s, elapsed: %s" %
                              (n_lines, n_compl_lines, time.time() - start))
        _last_flush_timestamp = time.time()
        time.sleep(5)


def make_standard_logging_module():
    """Register the FastLoggingImporter in order to make this module the global logging module,
    replacing the standard python logger."""
    sys.meta_path.append(FastLoggingImporter())
    try:
        sys.modules.pop("logging")
    except Exception:
        pass


def setup(base_path, base_filename, p_log_to_stdout=False, rotation_line_count=3000000, cached_lines=500,
          disable_flushing_thread=False, silence_time=60):
    """Set up this module and by that also activate the logging to the file.

    :param base_path: the path where the logfile is created
    :param base_filename: name of the file, will be extended by datetime during rotation of log files
    :param p_log_to_stdout: the "log_to_stdout" switch can be modified by this parameter
    :param rotation_line_count: maximum number of lines in one logfile
    :param cached_lines: number of events accumulated in the cache until content is sent to the file
        in case of info and debug entries. All other log levels are written and flushed immediately
    :param silence_time: for how many seconds a particular message can't be repeated in compliance logs"""
    global _filename, _file_pointer, _file_base_path, _rotation_line_count, _cached_lines, _flushing_thread
    global _filename_json, _file_pointer_json, _rotation_line_count_json, _force_daily_rotation_compliance
    global log_to_stdout, _silence_time

    log_to_stdout = p_log_to_stdout
    _silence_time = silence_time

    _file_base_path = base_path
    _filename = base_filename
    _filename_json = "{}_compliance.log".format(base_filename.split(".")[0])
    if _file_pointer is not None:
        _file_pointer.close()
    if _file_pointer_json is not None:
        _file_pointer_json.close()
    # On startup, we always rotate, but not for the compliancelog
    _force_daily_rotation_compliance = NOW_UTC().day
    _rotate_file_log(_filename, on_startup=True)
    _file_pointer = open(_get_filename(_filename), "a")
    _file_pointer_json = open(_get_filename(_filename_json), "a")
    _rotation_line_count = rotation_line_count
    _rotation_line_count_json = rotation_line_count
    _cached_lines = cached_lines
    # start the flushing thread if it's not yet there
    if _flushing_thread is None and not disable_flushing_thread:
        _flushing_thread = threading.Thread(target=_flushing_thread_target)
        _flushing_thread.setDaemon(True)
        _flushing_thread.start()


def close_file(file_pointer):
    """
    Flushes and closes a file
    :param file_pointer: pointer to a file
    :type file_pointer: file
    """
    if file_pointer is not None:
        file_pointer.flush()
        file_pointer.close()


def disable():
    """Turns off logging completely."""
    global _file_pointer, _filename, log_to_stdout
    global _file_pointer_json, _filename_json
    close_file(_file_pointer)
    _file_pointer = None
    _filename = ""
    close_file(_file_pointer_json)
    _file_pointer_json = None
    _filename_json = ""
    log_to_stdout = False


class Logger(object):
    """Base logger class. Behaves quite similar as logging.Logger"""

    def __init__(self, scope):
        """Constructor.

        :param scope: A string that identifies the scope for this logger. The scope is printed in the
            log line and usually refers to the module or a functional area in a program, like::

            LOGGER = logging.LOGGER("customer_management.customer_credit_check")"""
        if isinstance(scope, str):
            scope = scope.decode("utf-8")
        self.scope = scope

    @staticmethod
    def _flush_logs(file_pointer, records):
        """
        flushes records (logs) to the given file_pointer

        :param file_pointer: file pointer for the log files
        :type file_pointer: file
        :param records: logs which should be written to a file
        :type records: str
        :return: bool if file_pointer exists
        :rtype: bool
        """
        global log_to_stdout
        if log_to_stdout:
            sys.stdout.write(records.encode("utf-8"))
            if len(records) > 1:
                sys.stdout.write("\n")
            sys.stdout.flush()
        if file_pointer is not None:
            file_pointer.write(records.encode("utf-8"))
            file_pointer.flush()
            return True
        return False

    @staticmethod
    def _rotate_log(file_pointer, counter, rotation_line_count):
        """
        rotates log file after rotation_line_count lines are written  or if _next_rotation_timestamp is passed

        :param file_pointer: file pointer for the log files
        :type file_pointer: file
        :param counter: currently written log lines before any rotation
        :type counter: int
        :param rotation_line_count: rotations happens after that many lines
        :type rotation_line_count: int
        :return: returns the log file and line counter
        :rtype: file, int
        """
        global _next_rotation_timestamp
        curr_timestamp = time.time()
        if counter >= rotation_line_count or curr_timestamp > _next_rotation_timestamp:
            counter = 0
            file_pointer.close()
            _rotate_file_log(file_pointer.name)
            file_pointer = open(_get_filename(file_pointer.name), "a")
        return file_pointer, counter

    @staticmethod
    def _rotate_compliancelog(file_pointer, counter, rotation_line_count):
        """
        rotates compliance log file after rotation_line_count lines are written  or if its the start of a new day

        :param file_pointer: file pointer for the log files
        :type file_pointer: file
        :param counter:  currently written log lines before any rotation
        :type counter: int
        :param rotation_line_count: rotations happens after that many lines
        :type rotation_line_count: int
        :return: returns the log file and line counter
        :rtype: file, int
        """
        global _force_daily_rotation_compliance
        current_day = NOW_UTC().day
        if counter >= rotation_line_count or current_day != _force_daily_rotation_compliance:
            counter = 0
            file_pointer.close()
            _rotate_file_compliancelog(file_pointer.name)
            file_pointer = open(_get_filename(file_pointer.name), "a")
        return file_pointer, counter

    @classmethod
    def conditional_flush_and_rotate(cls):
        """
        Writes the cached entries to the log file and/or stdout and rotates the log file,
        if the maximum line count is reached
        """
        global _counter, _entries, _file_pointer, _rotation_line_count, _lock
        # locking here protects the flushing and rotating
        with _lock:
            # the next 3 lines protect _entries from being cleared while being extended in another thread
            num_entries = len(_entries)
            content_to_write = "".join(entry + "\n" for entry in _entries[:num_entries])
            _entries[:num_entries] = []

            if cls._flush_logs(file_pointer=_file_pointer, records=content_to_write):
                _file_pointer, _counter = cls._rotate_log(
                    file_pointer=_file_pointer,
                    counter=_counter,
                    rotation_line_count=_rotation_line_count)
            return num_entries

    @classmethod
    def compliance_flush_and_rotate(cls):
        """
        Writes the entries to the log file and/or stdout and rotates the log file

        log file is rotated after _rotation_line_count_json lines or on a new day.
        """
        global _counter_json, _entries_json, _file_pointer_json, _rotation_line_count_json, _lock_json

        with _lock_json:
            # the next 6 lines protect _entries_json from being cleared while being extended in another thread
            num_entries_json = len(_entries_json)
            content_to_write = ""
            current_time = NOW_UTC()

            # if entering from the 5 sec flushing thread, check for messages which were silenced before,
            # and are allowed to be printed.
            if num_entries_json == 0:
                content_to_write = cls._prep_compliance_for_flushing_thread(current_time)
            else:
                content_to_write = cls._prep_compliance_for_entries(current_time)

            if cls._flush_logs(file_pointer=_file_pointer_json, records=content_to_write):
                _file_pointer_json, _counter_json = cls._rotate_compliancelog(
                    file_pointer=_file_pointer_json,
                    counter=_counter_json,
                    rotation_line_count=_rotation_line_count_json)
            return num_entries_json

    @classmethod
    def _prep_compliance_for_entries(cls, current_time):
        """
         checks if a message should be sileneced or is ready to be flushed.

        :param current_time: datetime in utc (datetime.datetime.utcnow())
        :type current_time: datetime.datetime
        :return: jsonlines message which will be flushed into the compliance log file
        :rtype: str
        """

        global _counter_json, _entries_json, _silence_entries_counter, _silence_entries_obj
        content_to_write = ""
        for entry in _entries_json:
            comp_text = entry[u"text"]
            if not _silence_entries_counter[comp_text]:
                if not entry["log_code"] in LOGTEMP.DENY_SILENCE:
                    # If there is no counter yet, it means that it is the first time the message was seen.
                    # Therefore we log the message and create a Counter when the next message with the same key
                    # will be allowed again. There should be no more than 1 timestamp for each key in the counter
                    # the key for the counter is the next allowed time when to print the text again.
                    _silence_entries_counter[comp_text][current_time + datetime.timedelta(seconds=_silence_time)] += 1
                content_to_write += json.dumps(entry, ensure_ascii=False, encoding='utf8',
                                               default=str) + "\n"
                _counter_json += 1
            else:
                # there should only be 1 timestamp in the Counter anyway
                allowed_time = _silence_entries_counter[comp_text].keys()[0]
                if allowed_time > current_time:
                    _silence_entries_counter[comp_text][allowed_time] += 1
                    _silence_entries_obj[comp_text] = entry
                elif allowed_time <= current_time:
                    silenced_count = _silence_entries_counter[comp_text][allowed_time] - 1
                    # since we are allowed to log again, we need to delete the old timestamp and generate a new entry
                    # with the current silence restriction. Since the function is called in a thread lock, only 1 entry
                    # should exist for a given key at any time. This allows us to NOT calculate the allowed_time and
                    # just use the value of the first entry in the counter.
                    del _silence_entries_counter[comp_text][allowed_time]
                    _silence_entries_counter[comp_text][current_time + datetime.timedelta(seconds=_silence_time)] = 1
                    # if a message was silenced append the text
                    if silenced_count:
                        silenced_obj = _silence_entries_obj[entry[u"text"]]
                        del _silence_entries_obj[comp_text]
                        entry[u"text"] = cls._append_silence_msg(comp_text,
                                                                 silenced_count,
                                                                 _silence_time,
                                                                 silenced_obj[u"utc_timestamp"])
                    content_to_write += json.dumps(entry, ensure_ascii=False, encoding='utf8') + "\n"
                    _counter_json += 1
        _entries_json[:len(_entries_json)] = []
        return content_to_write

    @classmethod
    def _prep_compliance_for_flushing_thread(cls, current_time):
        """
        checks for unflushed silenced compliance log and flushes them if needed.

        The idea is to go through the list of all currently silenced entries (every 5 seconds) and check if they are
        allowed to be flushed. When the message is flushed the _silence_entries_counter for the given message is reset,
        and the silenced object is removed. A new silence period for the flushed message is created afterwards.

        :param current_time: datetime in utc (datetime.datetime.utcnow())
        :type current_time: datetime.datetime
        :return: jsonlines message which will be flushed into the compliance log file
        :rtype: str
        """
        global _counter_json, _silence_entries_obj, _silence_entries_counter
        content_to_write = ""
        for entry_text in list(_silence_entries_obj):
            allowed_time = _silence_entries_counter[entry_text].keys()[0]
            if allowed_time > current_time:
                continue
            elif allowed_time <= current_time:
                silenced_count = _silence_entries_counter[entry_text][allowed_time] - 1
                # delete old counter and set new one
                del _silence_entries_counter[entry_text][allowed_time]
                _silence_entries_counter[entry_text][current_time + datetime.timedelta(seconds=_silence_time)] = 1
                silenced_utc_timestamp = _silence_entries_obj[entry_text][u"utc_timestamp"]
                _silence_entries_obj[entry_text][u"text"] = cls._append_silence_msg(entry_text,
                                                                                    silenced_count,
                                                                                    _silence_time,
                                                                                    silenced_utc_timestamp)

                line = json.dumps(_silence_entries_obj[entry_text], ensure_ascii=False, encoding='utf8')
                del _silence_entries_obj[entry_text]
                _counter_json += 1
                content_to_write += line + "\n"
        return content_to_write

    @staticmethod
    def _append_silence_msg(text, silenced_count, silence_time, utc_timestamp, postfix=None):
        """
        appends a predefined postfix message (_silence_msg) to the given text

        _silence_msg will be formatted with silenced_count, silence_time and utc_timestamp.
        _silence_msg is ignored if a postfix message is given, but still needs to contain the mentioned formatting.

        :param text: custom text to which a postfix will be appended
        :type text: str
        :param silenced_count: count of how many messages of this type have been silenced
        :type silenced_count: int
        :param silence_time: currently used silence_time
        :type silence_time: int
        :param utc_timestamp: utc timestamp in isoformat
        :type utc_timestamp: str
        :param postfix: message which needs to contain formatting for silenced_count, silence_time and utc_timestamp
        :type postfix: str
        :return: log message text with appended silence message
        :rtype: str
        """
        global _silence_msg
        if postfix is not None:
            msg = postfix
        else:
            msg = _silence_msg
        return " ".join((text, msg.format(silenced_count, silence_time, utc_timestamp)))

    def log(self, level, string, *args):
        self._log_object(level, string, args)

    def _log_json_object(self, level, string, **kwargs):
        """
        Logs a JSON object

        :param level: logging level. Can be one of INFO, WARNING, DEBUG, ERROR, CRYTICAL, EXCEPTION
        :type level: str
        :param string: logging message, will be written into "text" field of JSON
        :type string: str
        :param kwargs: key word arguments to be written to JSON as it is (we just copy these arguments to dict)
        :type kwargs: dict[str]
        """
        global _entries_json
        log_entry = self._prepare_log_entry(level, string, **kwargs)
        _entries_json.append(log_entry)

    def _prepare_log_entry(self, level, string, **kwargs):
        """
        Prepares json msg to be logged

        :param level: logging level
        :type: str
        :param string: msg to be logged
        :type string: str
        :param kwargs: arguments to be passed for logging
        :type kwargs: dict(str -> Any)
        :return: ready to log json object with needed fields
        :rtype: dict(str -> Any)
        """

        log_entry = {u"utc_timestamp": str(NOW_UTC().isoformat()),
                     u"component": self.scope,
                     u"level": level,
                     u"at_version": ATVER.VERSION,
                     u"server_role": _server_role}
        if isinstance(string, basestring):
            if isinstance(string, str):
                string = string.decode("utf-8")
            if kwargs:
                for key in kwargs:
                    if isinstance(kwargs[key], str):
                        kwargs[key] = kwargs[key].decode("utf-8")
                # .format(kwargs) will only populate the string if it has some formatters needed
                log_entry[u"text"] = string.format(**kwargs)
            else:
                log_entry[u"text"] = string
        else:
            log_entry[u"text"] = string
        log_entry.update(kwargs)
        return log_entry

    def compliance_log(self, log_entry, **log_entry_input):
        """
        High-level function for compliance logging

        :param log_entry: a tuple for particular even. Should be one from autotrader_core/compliance_log_templates.py
        :type log_entry: tuple[int, str, str]
        :param log_entry_input: dict of parameters to be passed for logging
        :type log_entry_input: dict[str, Any]
        """

        log_entry_input.update(log_code=log_entry[0])
        self._log_json_object(level=log_entry[1], string=log_entry[2], **log_entry_input)

        self.compliance_flush_and_rotate()

    def _log_object(self, level, string, args):
        """Format logging parameters depending on their type. Called by the public logging functions."""
        global _entries
        if isinstance(string, basestring):
            if isinstance(string, str):
                string = string.decode("utf-8")
            if args:
                try:
                    _entries.append((u"%s [%s] %s " + string) % ((NOW().isoformat(), self.scope, level) + args))
                except UnicodeDecodeError:
                    args = tuple([element.decode("utf-8") if isinstance(element, str) else element for element in args])
                    _entries.append((u"%s [%s] %s " + string) % ((NOW().isoformat(), self.scope, level) + args))
            else:
                _entries.append(u"%s [%s] %s %s" % (NOW().isoformat(), self.scope, level, string))
        else:
            _entries.append((u"%s [%s] %s %r") % (NOW().isoformat(), self.scope, level, string))

    def debug(self, string, *args):
        """Add an debug log entry. Take care: writing to file only happens on every
        _cached_lines's event. Parameters are like in debug."""
        global _counter
        self._log_object("DEBUG", string, args)
        _counter += 1
        if _counter % _cached_lines == 0:
            self.conditional_flush_and_rotate()

    def info(self, string, *args):
        """Add an info log entry. Take care: writing to file only happens on every
        _cached_lines's event. Parameters are like in debug."""
        global _counter
        self._log_object("INFO", string, args)
        _counter += 1
        if _counter % _cached_lines == 0:
            self.conditional_flush_and_rotate()

    def warning(self, string, *args):
        """Add a warning log entry. Parameters are like in debug."""
        global _counter
        self._log_object("WARNING", string, args)
        _counter += 1
        self.conditional_flush_and_rotate()

    def error(self, string, *args):
        """Add an error log entry. Parameters are like in debug."""
        global _counter
        self._log_object("ERROR", string, args)
        _counter += 1
        self.conditional_flush_and_rotate()

    def critical(self, string, *args):
        """Add a critical log entry. Parameters are like in debug."""
        global _counter
        self._log_object("CRITICAL", string, args)
        _counter += 1
        self.conditional_flush_and_rotate()

    def exception(self, string, *args):
        """Log an exception as error. The parameters are the same as in error. But here,
        additionally, the current exception traceback is logged as well.
        """
        global _counter
        self._log_object("ERROR", string, args)
        # get exception info and log that as well
        exc_type, exc_value, exc_traceback = sys.exc_info()
        exc_str = traceback.format_exception(exc_type, exc_value, exc_traceback)
        for i, exc in enumerate(exc_str):
            if isinstance(exc, str):
                exc_str[i] = exc.decode("utf-8")
        _entries.append(u"".join(exc_str))
        _counter += 1
        # delete traceback to avoid traceback cycle problem
        del exc_traceback
        self.conditional_flush_and_rotate()

    def addHandler(self, *args):
        pass

    def removeHandler(self, *args):
        pass


def getLogger(scope):
    """Return a Logger instance"""
    return Logger(scope)


class NullHandler(object):
    pass


_module_logger = Logger("")


def debug(string, *args):
    """Compatibility function, don't use if not absolutely required. Instantiate a Logger object instead"""
    _module_logger.debug(string, *args)


def info(string, *args):
    """Compatibility function, don't use if not absolutely required. Instantiate a Logger object instead"""
    _module_logger.info(string, *args)


def warning(string, *args):
    """Compatibility function, don't use if not absolutely required. Instantiate a Logger object instead"""
    _module_logger.warning(string, *args)


def error(string, *args):
    """Compatibility function, don't use if not absolutely required. Instantiate a Logger object instead"""
    _module_logger.error(string, *args)


def critical(string, *args):
    """Compatibility function, don't use if not absolutely required. Instantiate a Logger object instead"""
    _module_logger.critical(string, *args)


def exception(string, *args):
    """Compatibility function, don't use if not absolutely required. Instantiate a Logger object instead"""
    _module_logger.exception(string, *args)


class BacktestingComplianceLoggerMixin:
    """
    Unitility mixin for compliance logging from within backtesting, just add it to your test class and implement
    the method `_get_strat_hashes`.
    """
    strategy_hash_str = "__UNDEFINED__"

    _logger = None
    _write_logs = False
    _logs_initialized = False
    _log_filename = None
    role = "500: backtesting"

    def _get_strat_hashes(self):
        """
        Implement this in you derived class. This method should get or calculate the hash of the strategy and store it
        in the variable `strategy_hash_str`. It will get called from `init_logs`
        :return: None
        :rtype: None
        """
        raise NotImplementedError

    def init_logs(self, logger, write_logfiles=True, filename="autotrader_backtesting.log"):
        """
        initializes compliance logging
        :param logger: the used logger instance
        :type logger: Logger
        :param write_logfiles: flag to enable/disable writing of compliance logs
        :type write_logfiles: bool
        :param filename: used filename for compliance logs
        :type filename: str
        :return: None
        :rtype: None
        """
        self._write_logs = write_logfiles
        if self._write_logs:
            self._logger = logger
            base_path = "/".join(filename.split("/")[:-1])
            setup(base_path, filename)
            set_server_role(self.role)

            # save latest log file name if file is needed in tests after logger has been shut down/reset
            self._log_filename = _file_pointer_json.name

            self._get_strat_hashes()
            self._logs_initialized = True
        else:
            disable()

    def get_compliance_log_filename(self):
        """
        :return: name of the used json logfile used for compliance logging
        :rtype:  str
        """
        return self._log_filename

    def compliance_log(self, log_entry, **kwargs):
        """
        Writes a log entry to backtesting compliance logs
        :param log_entry: log entry tuple from autotrader_core/compliance_log_templates.py
        :type log_entry: tuple[int, str, str]
        :param kwargs: key word arguments for formatting
        :type kwargs: str
        """
        if not self._write_logs:
            return
        if not self._logs_initialized:
            raise RuntimeError("Logs are not initialized")
        self._logger.compliance_log(log_entry, **kwargs)


@atexit.register
def at_exit():
    """Makes sure we do not loose any messages at interpreter shutdown"""
    last_logger = Logger("fastlogging.at_exit")
    last_logger.debug("Flushing logs at shutdown.")
    Logger.conditional_flush_and_rotate()
    Logger.compliance_flush_and_rotate()
