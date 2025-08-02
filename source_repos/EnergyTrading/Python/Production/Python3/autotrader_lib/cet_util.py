"""
This module contains utility functions for dealing with (local) times in CET.

Other time-related utility functions that deal with only UTC and naive datetime objects are in autotrader_lib.util
"""

import datetime
import logging
import types as T
from six.moves import range

try:
    import pytz  # Can't be imported in trayport proxy
except ImportError:
    logging.error("Could not import pytz. Note: pytz is not available in the trayportproxy.")
    raise

import autotrader_lib.common as COMMON
import autotrader_lib.util as ALU


def convert_timezones(dt, from_zone, to_zone):
    # type: (datetime.datetime, str, str) -> datetime.datetime
    """Change unlocalized datetime from 1 timezone to another timezone"""
    return pytz.timezone(from_zone).localize(dt).astimezone(pytz.timezone(to_zone)).replace(tzinfo=None)


def cet_dt2utc_dt(cet_dt):
    # type: (datetime.datetime) -> datetime.datetime
    """Convert a naive CET datetime into a UTC datetime and remove tzinfo after conversion"""
    return convert_timezones(cet_dt, 'CET', 'UTC')


def utc_dt2cet_dt(utc_dt):
    # type: (datetime.datetime) -> datetime.datetime
    """Convert a naive UTC datetime into a CET datetime and remove tzinfo after conversion"""
    return convert_timezones(utc_dt, 'UTC', 'CET')


def cet_dt2ts(dt):
    # type: (datetime.datetime) -> float
    """convert datetime to timestamp"""
    return utc_dt2ts(cet_dt2utc_dt(dt))


def cet_ymd2ts(*args):
    """
    Get the timestamp corresponding to the given year, month, day, hour and minute.

    :param args: Arguments that will be passed to datetime.datetime
    :return: An epoch timestamp
    :rtype: float
    """
    return cet_dt2ts(datetime.datetime(*args))


def cet_ymd2utc_dt(*args):
    """Create a datetime object in utc, given year, month, day, hour and minute in CET.
    :param args: Arguments that will be passed to datetime.datetime
    :return: A datetime object, converted from CET/CEST to UTC
    :rtype: datetime.datetime
    """
    return cet_dt2utc_dt(datetime.datetime(*args))


def cet_dt2int_ts(dt):
    # type: (datetime.datetime) -> int
    """convert datetime to timestamp"""
    return int(cet_dt2ts(dt))


def utc_dt2ts(dt):
    # type: (datetime.datetime) -> float
    """convert datetime to timestamp"""
    return ALU.convert_dt_to_float_timestamp(dt)


def utc_ts2cet_dt(utc_ts):
    # type: (float) -> datetime.datetime
    """Convert a UTC timestamp into a CET datetime"""
    return utc_dt2cet_dt(utc_ts2utc_dt(utc_ts))


def utc_ts2utc_dt(utc_ts):
    # type: (float) -> datetime.datetime
    """Convert UTC timestamp into a UTC datetime, no timezones involved"""
    return datetime.datetime.utcfromtimestamp(utc_ts)


def utc_ts2utc_str(timestamp, extended=False, add_timezone_info=False):
    # type: (float | int, bool, bool) -> str
    """Convert utc timestamp to utc string"""
    timezone_info = "[UTC]" if add_timezone_info else ""
    return utc_ts2utc_dt(timestamp).strftime("%d.%m.%Y %H:%M:%S" if extended else "%d.%m %H:%M") + timezone_info


def utc_ts2cet_str(timestamp, extended=False, add_timezone_info=False, add_year=False):
    # type: (float | int, bool, bool, bool) -> str
    """Convert utc timestamp to cet string"""

    year = ".%Y" if add_year else ""
    seconds = ":%S" if extended else ""
    cet = "[CET/CEST]" if add_timezone_info else ""
    fmt = "%d.%m{} %H:%M{}{}".format(year, seconds, cet)
    return utc_ts2cet_dt(timestamp).strftime(fmt)


def get_product_delivery_ranges(
        start_time,  # type: datetime.datetime
        end_time  # type: datetime.datetime
):  # type: (...) -> T.DictType[int, T.ListType[T.TupleType[datetime.datetime, datetime.datetime]]]
    """times in without timezone information, returned datetimes in same tz"""
    times = ALU.create_time_range(start_time, end_time)

    if len(times) < 2:
        raise ValueError("time range needs to be large enough to have "
                         "at least 2 quarter hours (start={}, end={})".format(start_time, end_time))

    product_ranges = {
        COMMON.QUARTER: [],
        COMMON.HALF: [],
        COMMON.HOUR: [],
        2 * COMMON.HOUR: [],
        4 * COMMON.HOUR: []
    }

    for i in range(len(times)):
        for j in range(i + 1, len(times)):
            if ALU.duration_check(cet_dt2ts(times[i]), cet_dt2ts(times[j]), _raise_value_error=False):
                duration = int((times[j] - times[i]).total_seconds())
                product_ranges[duration].append((times[i], times[j]))
    return product_ranges
