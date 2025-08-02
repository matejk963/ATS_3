from __future__ import absolute_import
import operator

import autotrader_lib.common as COMMON
import autotrader_lib.compliance_log_templates as LOGTEMP
import autotrader_core.persistence as PERSIST
import six
from six.moves import range

if six.PY2:
    import autotrader_lib.fast_logging_py2 as FLOG
else:
    import autotrader_lib.fast_logging_py3 as FLOG


log = FLOG.getLogger("limit_management")


class StrategyTimeSeries(dict):
    """
    Wrapper class of a dict object, which holds timeseries data and additional timeseries raster attribute
    """
    def __init__(self, ts_raster=None, _aggregator=None, **kwargs):
        """

        :param ts_raster: specifies timeseries raster in seconds
        :type ts_raster: int
        :param kwargs:
        :type kwargs: dict
        """
        super(StrategyTimeSeries, self).__init__(**kwargs)
        self.ts_raster = ts_raster
        # The following is for lazy creation of different rasters,
        # i.e. for aggregating from ts_raster (e.g. 15 mins) to a higher aggregation (e.g. to hours) on demand.
        self._aggregator = _aggregator

    @classmethod
    def from_tr_data(cls, tr_data, aggregator=None):
        """Factory function, which creates a StrategyTimeSeries object from the provided timeseries data as
        transferred from Periotheus

        :param tr_data: timeseries data as transferred from Periotheus
        :type tr_data: typing.List[typing.Dict]
        :param aggregator: function additionally aggregating 15 minutes timeseries on hourly base
        :type aggregator: funct
        :return: StrategyTimeSeries object with the data corresponding to the provided tr_data
        :rtype: :class:`StrategyTimeSeries`
        """
        tr_data.sort(key=operator.itemgetter("begin"))
        raster = tr_data[0]["end"] - tr_data[0]["begin"]
        instance = cls(ts_raster=raster)
        for entry in tr_data:
            instance[(entry["begin"], entry["end"])] = entry["value"]

        tr_begin = tr_data[0]["begin"]
        tr_end = tr_data[-1]["end"]

        # Fill in empty values
        for entry_begin in range(tr_begin, tr_end, instance.ts_raster):
            instance.setdefault((entry_begin, entry_begin + instance.ts_raster))

        instance._aggregator = aggregator

        return instance

    def get(self, key, default=None):
        """
        In the get function, also perform lazy aggregation using __missing__

        The standard implementation of .get does not call __missing__ and instead returns the default, so we have to
        provide an implementation which always calls __getitem__ and thus __missing__.
        """
        try:
            return self[key]
        except KeyError:
            return default

    def __missing__(self, key):
        """
        Aggregate on demand

        This function is called when __getitem__ fails with the key.
        Then whatever this function returns or raises is returned or raised.

        Here, we use this logic to lazily aggregate to higher aggregations. The first time this is called with a
        duration to which we can aggregate, we do so and store the result in the timeseries,
        thus saving computation time on the next try.
        As we typically always want to aggregate to the same durations (e.g. 4h for 4h products, if we trade in the UK),
        it makes sense to store the aggregated result. Aggregating on the initialization of StrategyTimeseries is tricky
        with target aggregations greater than 1 hour, as daylight saving time can make problems.
        Plus aggregating lazily only when needed safes computation time.
        """
        begin, end = key
        duration = end - begin
        if self.ts_raster not in [COMMON.QUARTER, COMMON.HOUR]:
            raise KeyError("Cannot aggregate from rasters other than 15min or hours to other durations. "
                           "Current raster is {}, key was {}.".format(self.ts_raster, key))
        if self._aggregator is None:
            raise KeyError("Cannot aggregate to {}, because no aggregator function is set.".format(key))
        if duration == self.ts_raster:
            self[key] = None
            return None
        self._duration_checks(begin, end, duration)
        aggregated = self._aggregate(begin, end)
        self[key] = aggregated
        return aggregated

    def _duration_checks(self, begin, end, duration):
        if begin % self.ts_raster != 0:
            raise KeyError("Invalid begin time not aligned to the raster: {}".format(begin))
        if duration % self.ts_raster != 0:
            raise KeyError("We cannot aggregate to durations that are not multiples of the raster."
                           " Found: {}-{} with duration {}".format(begin, end, duration))
        if duration > COMMON.DAY * 367:
            # For durations longer than a year, we never want to aggregate, as it is not performant.
            raise KeyError("We cannot aggregate to durations longer than a year."
                           " Found: {}-{} with duration {}".format(begin, end, duration))

    def _aggregate(self, begin, end):
        values = []
        for quarter in range(begin, end, self.ts_raster):
            val = self.get((quarter, quarter + self.ts_raster))
            values.append(val)
        return self._aggregator(values)


def mean(iterable):
    """Returns mean of the provided iterable

    :param iterable: any iterable, for which the mean is to be evaluated
    :type iterable: typing.Iterable[float]
    :return: mean of the iterable
    :rtype: float
    """
    return sum(iterable) / float(len(iterable))


def drop_none(iterable):
    """Drops None in the provided iterable and returns a list with not None values

    :param iterable: any iterable, for which the None values should be dropped
    :type iterable: typing.Iterable[float]
    :return: list with not None values built from the iterable
    :rtype: list
    """
    return [itr for itr in iterable if itr is not None]


def aggregator_function(aggreg):
    """Wrapper function for the provided aggreg type returning a function, which performs the corresponding
    transformation on an iterable

    Valid values for aggreg are "min", "max", "avg", "min_nonone", "max_nonone", "avg_nonone". The options with
    "*_nonone" drop None from the provided iterable before any "min", "max", or ""avr" transformations.

    :param aggreg: specifies the type of aggregation
    :type aggreg: str
    :return: wrapped function according to the type of aggregation
    :rtype: func
    """
    values_transformation = None
    transformation = None
    if aggreg in COMMON.AggregatorRule.max_set:
        transformation = max
    elif aggreg in COMMON.AggregatorRule.min_set:
        transformation = min
    elif aggreg in COMMON.AggregatorRule.avg_set:
        transformation = mean

    if aggreg in COMMON.AggregatorRule.none_set:
        values_transformation = drop_none

    def wrapped_aggregator(iterable):
        """Wrapped function performing aggregation of an iterable"""
        iterable = values_transformation(iterable) if values_transformation else list(iterable)
        if None in iterable or not iterable:
            return None
        return transformation(iterable) if transformation else None
    return wrapped_aggregator


class LimitContainer(object):
    """
    A container holding the limits per product (=sequence_item) and per sequence.

    Currently the behavior is only defined for the exchange TRAYPORT.
    """
    def __init__(self, strategy_id, exchange_id):
        """

        :param strategy_id: The id of the strategy. Used for logging
        :type strategy_id: str
        :param exchange_id: The internal id of the exchange. Currently only TRAYPORT is supported.
        :type exchange_id: str, None
        """
        self._strategy_id = strategy_id
        self._exchange_id = exchange_id
        # Limits per sequence (=> the fall-back for all products of a sequence, if no limit per product is given)
        self._per_sequence = {}
        # Limits per products. In public interfaces we always speak of "sequence_items" (Trayport terminology),
        # which is the same as products in autotrader terminology, as the product_id is sequence_id + item_id
        self._per_product = {}
        self.reset_limits()

    def __repr__(self):
        return "LimitContainer(strategy_id=<{}>, exchange_id=<{}>)".format(self._strategy_id, self._exchange_id)

    def __str__(self):
        return "{!r} --> PerProductLimits: {} ;PerSequenceLimits: {}".format(self, self._per_product, self._per_product)

    def get_limit(self, limit_name, product):
        """
        Get the limit for a given product.

        This will return the limit for the sequence_item when given
        and fall back to the limit for the sequence otherwise.
        :param limit_name: What kind of limit to retrieve. One of COMMON.PerProductLimits.supported_limits
        :type limit_name: str
        :param product: The product
        :type product: autotrader_core.exchange_trading.Product
        :return: The limit
        :rtype: float | None
        """
        if product.product_id in self._per_product[limit_name]:
            return self._per_product[limit_name][product.product_id]
        elif (self._exchange_id == COMMON.Exchange.trayport
                and product.sequence_id in self._per_sequence[limit_name]):
            return self._per_sequence[limit_name][product.sequence_id]
        else:
            return None

    def _expire_old_limits(self, exchange):
        """
        When called, this checks if it stores limits for expired products and removes them from memory.

        :param exchange: The exchange object. Must be Trayport.
        :type exchange: autotrader_core.exchanges.Trayport
        """
        for limit_name, limit_dict in self._per_product.items():
            for product_id in list(limit_dict):
                if exchange.is_product_id_long_expired(product_id):
                    log.compliance_log(LOGTEMP.AutoTraderLimiter.limit_expired,
                                       limit_name=limit_name,
                                       sequence_item_id=product_id,
                                       old_limit_value=limit_dict[product_id])
                    del limit_dict[product_id]

    @classmethod
    def from_db(cls, strategy_id):
        """
        Factory function for restoring the LimitContainer from the database.

        :param strategy_id: The id of the strategy for which to load the limits.
        :type strategy_id: str
        :returns: If found in the database, a reconstructed LimitContainer is returned, None otherwise
        :rtype: LimitContainer | None
        """
        db_object = PERSIST.MongoDBConnector().load_db_per_product_limits(strategy_id)
        if db_object is None:
            log.compliance_log(LOGTEMP.AutoTraderLimiter.no_per_product_limits_in_db,
                               strategy_id=strategy_id)
            return cls(strategy_id, None)
        instance = cls(strategy_id, db_object["exchange_id"])
        instance._per_product = db_object["limits_per_sequence_item"]
        instance._per_sequence = db_object["limits_per_sequence"]
        log.compliance_log(LOGTEMP.AutoTraderLimiter.limits_restored_from_db,
                           strategy_id=strategy_id,
                           per_sequence_id_limits=instance._per_sequence,
                           per_sequence_item_id_limits=instance._per_product)
        return instance

    def update_db(self, update_timestamp):
        """
        Store/ update this LimitContainer instance in the database
        :param update_timestamp: The timestamp to store as alteration_time in the database.
        :type update_timestamp: float
        """
        PERSIST.MongoDBConnector().update_db_per_product_limits(self, update_timestamp)

    def _set_for_sequence(self, limit_name, sequence_id, value, user, update_timestamp):
        """
        Set the limit for a sequence_id to the given value.

        :param limit_name: What kind of limit to set. One of COMMON.PerProductLimits.supported_limits
        :type limit_name: str
        :param sequence_id: The id of the sequence for which to set the limit.
        :type sequence_id: str
        :param value: The new limit value
        :type value: float
        :param user: The user who triggered the limit change. Used for compliance logging
        :type user: basestring
        :param update_timestamp: The timestamp when the limit is updated. Used for logging
        :type update_timestamp: float
        """
        old_value = self._per_sequence[limit_name].get(sequence_id)
        if old_value != value:
            log.compliance_log(log_entry=LOGTEMP.AutoTraderLimiter.per_sequence_id_limit_updated,
                               login_name=user,
                               limit_name=limit_name,
                               strategy_id=self._strategy_id,
                               sequence_id=sequence_id,
                               limit_value=value,
                               old_limit_value=old_value,
                               update_timestamp=update_timestamp)
        self._per_sequence[limit_name][sequence_id] = value

    def _set_for_product(self, limit_name, product_id, value, user, update_timestamp):
        """
        Set the given limit for a product_id to the given value.

        :param limit_name: What kind of limit to set. One of COMMON.PerProductLimits.supported_limits
        :type limit_name: str
        :param sequence_id: The id of the product for which to set the limit.
        :type sequence_id: str
        :param value: The new limit value
        :type value: float
        :param user: The user who triggered the limit change. Used for compliance logging
        :type user: basestring
        :param update_timestamp: The timestamp when the limit is updated. Used for logging
        :type update_timestamp: float
        """
        old_value = self._per_product[limit_name].get(product_id)
        if old_value != value:
            log.compliance_log(log_entry=LOGTEMP.AutoTraderLimiter.per_sequence_item_id_limit_updated,
                               login_name=user,
                               limit_name=limit_name,
                               strategy_id=self._strategy_id,
                               sequence_item_id=product_id,
                               limit_value=value,
                               old_limit_value=old_value,
                               update_timestamp=update_timestamp)
            self._per_product[limit_name][product_id] = value

    def reset_limits(self):
        """
        Resets the limits `_per_sequence` and `_per_product`
        :returns: None
        """
        self._per_sequence = {name: {} for name in COMMON.PerProductLimits.supported_limits}
        self._per_product = {name: {} for name in COMMON.PerProductLimits.supported_limits}
