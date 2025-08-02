# -*- coding: utf-8 -*-

from __future__ import absolute_import
import collections

import autotrader_lib.common as COMMON
from six.moves import range


class ParameterTimeseries(collections.defaultdict):
    """
    Timeseries representation as dictionary timestamp-> value, where the timestamp is the hour of the start.
    """
    def __init__(self, *args, **kwargs):
        super(ParameterTimeseries, self).__init__(float)

    def min_of_range(self, ts_from, ts_until):
        values = [self.get(ts, None) for ts in range(ts_from, ts_until, COMMON.HOUR)]
        return None if None in values else min(values)

    def max_of_range(self, ts_from, ts_until):
        values = [self.get(ts, None) for ts in range(ts_from, ts_until, COMMON.HOUR)]
        return None if None in values else max(values)


class Parameters(object):
    """
    Object that stores strategy- and user-defined timeseries as attributes.
    """
    def __init__(self):
        pass

    def update(self, strategy_json):
        """
        Fill this object from the strategy json.
        """
        for key, parameter in strategy_json.items():
            if key.startswith("strategy_") and isinstance(parameter, list):
                if not hasattr(self, key):
                    setattr(self, key, ParameterTimeseries())
                paramdict = getattr(self, key)
                for element in parameter:
                    # We assume hourly resolution, so we do not store the end!
                    paramdict[element["begin"]] = element["value"]
            if key == "user_defined_timeseries":
                # recurse into those subelements
                self.update(parameter)
