#!/usr/bin/env python
# -*- coding: utf-8 -*-

import StringIO
import contextlib
import datetime
import hashlib
import os
import os.path
import zipfile
import types as T

import base64
import numpy as np

import autotrader_lib.util as ALU
import autotrader_core.common as COMMON


DEFAULT_LIMIT_VALUES = {
    COMMON.StrategyJsonKey.TS.limit_buy_price: 10000.0,
    COMMON.StrategyJsonKey.TS.limit_buy_vol: 10000.0,
    COMMON.StrategyJsonKey.TS.limit_sell_vol: 10000.0,
    COMMON.StrategyJsonKey.TS.limit_sell_price: -10000,
}

# dict to map standard  timeseries names with "strategy_" to the ones without, as used in configurations
TIMESERIES_NAMES_MAP = {
    "position_tradable_position_long": COMMON.StrategyJsonKey.TS.pos_sell,
    "position_tradable_position_short": COMMON.StrategyJsonKey.TS.pos_buy,
    "position_deviation": COMMON.StrategyJsonKey.TS.pos_dev,
    "price_forecast_trend": COMMON.StrategyJsonKey.TS.price_forecast_trend,
    "price_purchase_immediate_vesting": COMMON.StrategyJsonKey.TS.price_imm_buy,
    "price_sales_immediate_vesting": COMMON.StrategyJsonKey.TS.price_imm_sell,
    "price_purchase": COMMON.StrategyJsonKey.TS.price_buy,
    "price_sales": COMMON.StrategyJsonKey.TS.price_sell,
    "price_minimum_spread_buyback": COMMON.StrategyJsonKey.TS.price_min_spread_buyback,
    "storage_capacity": "strategy_storage_capacity",
    "storage_actual_level": "strategy_storage_actual_level",
    "storage_level_after_trading": "strategy_storage_level_after_trading",
    "limit_maximum_purchase_price": COMMON.StrategyJsonKey.TS.limit_buy_price,
    "limit_maximum_purchase_volume": COMMON.StrategyJsonKey.TS.limit_buy_vol,
    "limit_maximum_sales_volume": COMMON.StrategyJsonKey.TS.limit_sell_vol,
    "limit_minimum_sales_price": COMMON.StrategyJsonKey.TS.limit_sell_price,
}


def own_strategies_dir():
    return os.path.join(os.path.abspath(os.path.join(__file__, "../..")), "own_strategies")


class _NumpyTSFrame(object):
    """The class implements a data frame storing a collection of timeseries as numpy array

    :cvar timeseries: aggregated numpy array with timeseries data
    """

    def __init__(self, valid_from, valid_to, ts_raster, strategy_columns, userdef_columns):
        """

        :param valid_from: timestamp or datetime defining the start for the timeseries in the data frame
        :type valid_from: int or datetime.date
        :param valid_to: timestamp defining the end for the timeseries in the data frame
        :type valid_to: int or datetime.date
        :param ts_raster: specifies number of seconds for timeseries rasterization
        :type ts_raster: int
        :param strategy_columns: list of timeseries names stored in columns of the dataframe
        :type strategy_columns: List[str]
        :param userdef_columns: list of userdefined timeseries names stored in columns of the dataframe
        :type userdef_columns: List[str]
        """

        # standard strategy timeseries might need transformation of the timeseries name by adding the "strategy_"
        self.strategy_columns = strategy_columns
        # userdefined timeseries do not need any transformation
        self.userdef_columns = userdef_columns
        # keep track of all columns with self.columns
        self.columns = self.strategy_columns + userdef_columns

        self.ts_raster = ts_raster
        self.valid_from = valid_from
        self.valid_to = valid_to

        # define the structure of the array with initialization.
        # Important! with this it means, that we cannot add timeseries later in the simulation,
        # if the were not added when the strategy definition got initialized.
        self.dtype = np.dtype(
            [("start", np.int), ("end", np.int)]
            + [(value_name, np.float) for value_name in self.columns]
        )
        self.timeseries = self.empty_ts()

    def empty_ts(self):
        """Creates empty timeseries array placeholder based on valid_to, valid_from and ts_raster"""
        num_entries = int((self.valid_to - self.valid_from) / self.ts_raster) + 1
        validities = [
            self.valid_from + ind * self.ts_raster for ind in range(num_entries)
        ]
        nans = [np.nan for i in self.columns]
        timeseries = np.array(
            [
                tuple([validities[i], validities[i + 1]] + nans)
                for i in range(num_entries - 1)
            ],
            dtype=self.dtype,
        )
        return timeseries

    def fill(self, name, values, from_ts=None, to_ts=None, overwrite=True):
        """Allows to fill the timeseries defined by name with provided values

        :param name: name of a timeseries to be filled with values as stored in self.columns
        :type name: str
        :param values: a number or a list of numbers to fill the timeseries with. If only one number is provided,
                       it will be broadcasted to the whole timeseries
        :type values: float or List[float]
        :param from_ts: first timestamp, must be within validity
        :type from_ts: int
        :param to_ts: last timestamp, must be within validity
        :type to_ts: int
        :param overwrite: overwrite value even if value is not nan in the numpy array
        :type overwrite: bool
        """

        # transform the name from the ones used in the backtesting definitions to the ones how they are defined
        # in real use

        if from_ts is None:
            from_ts = self.valid_from
        if to_ts is None:
            to_ts = self.valid_to
        if isinstance(values, list):
            assert len(self.timeseries[name]) == len(values), (
                "Timeseries should have length {}, but {} values were submitted".format(
                    len(self.timeseries[name]), len(values))
            )

        if overwrite:
            ts_idx = np.where((self.timeseries["start"] >= from_ts) & (self.timeseries["end"] <= to_ts))
        else:
            ts_idx = np.where((self.timeseries["start"] >= from_ts) & (self.timeseries["end"] <= to_ts) & (
                np.isnan(self.timeseries[name])))
        if len(ts_idx) > 0:
            self.timeseries[name][ts_idx] = values

    def __repr__(self):
        str_header = "|".join(
            "{:{align}{width}}".format(entry, align="^", width="12") for entry in ["start", "end"] + self.columns
        ) + "\n"
        return str_header + "\n".join(
            "|".join("{:{align}{width}}".format(entry, align="^", width="12") for entry in entries)
            for entries in self.timeseries
        )

    def __getitem__(self, item):
        """Get column name which will be a timeseries name or start or end"""
        # transform the name from the ones used in the backtesting definitions to the ones how they are defined
        return self.timeseries[item]

    def __setitem__(self, item, value):
        self.fill(item, value)

    @staticmethod
    def np_record_to_pt_timeseries_entry(record):
        # type: (T.TupleType[int, int, float]) -> T.DictType[str, any]
        """Convert a row in the numpy timeseries array into periotheus-style row/entry in pt-timeseries

        Transform a record tuple with start-end-column value to dict with keys begin-end-value and the corresponding
         value. Numpy has a special numpy nan which has to be replaced with a Python-None so the strategies can
         understand it.
        """
        return dict(zip(["begin", "end", "value"], (record[0], record[1], None) if np.isnan(record[2]) else record))

    def np_timeseries_to_pt_timeseries(self, column):
        # type: (str) -> T.ListType[T.DictType[str, any]]
        """Convert numpy timeseries into periotheus-style timeseries

        Transform a timeseries columns in the numpy array with start and end column to a periotheus styles timeseries,
        which is a list of dicts with the keys begin, end, value
        """
        return [self.np_record_to_pt_timeseries_entry(record) for record in self.timeseries[["start", "end", column]]]

    def to_dict(self):
        """Convert numpy-timeseries to a periotheus-style timeseries

        Periotheus style timeseries are lists of dictionaries with the keys begin, end, value
        stategies in the autotrader expect timeseries to be in the periotheus-style way, so the numpy array has to
        be transformed, so the strategy can be converted correctly into a json when it is sent to autotrader in
        simulation.

        Also, distinguish between user defined timeseries and strategy timeseries
        """
        strategy_timeseries = {}
        for column in self.strategy_columns:
            strategy_timeseries[column] = self.np_timeseries_to_pt_timeseries(column)

        if self.userdef_columns:
            # package user defined timeseries in their own structure in the strategy json
            strategy_timeseries["user_defined_timeseries"] = {}
            for column in self.userdef_columns:
                strategy_timeseries["user_defined_timeseries"][column.strip()] = (
                    self.np_timeseries_to_pt_timeseries(column)
                )
        return strategy_timeseries

    @staticmethod
    def _convert_nan(value):
        """Helper function to convert numpy nan values to None compatible with the autotrader timeseries structure"""
        return None if np.isnan(value) else value.item()


class StrategyDefinitionBase(object):
    """The base class implementing base strategy definition object

    :cvar params: dictionary with the corresponding parameters of the strategy definitions
    :type params: dict
    :cvar ts_frame: timeseries frame build with columns aggregated from self.ts_names, self.algo_ts_names and
                    self.limits_ts_names
    :type ts_frame: class:`NumpyTSFrame`
    """
    ts_names = []

    algo_ts_names = []

    user_ts = []

    limits_ts_names = [
        "limit_maximum_purchase_volume",
        "limit_maximum_purchase_price",
        "limit_maximum_sales_volume",
        "limit_minimum_sales_price",
    ]

    strategy_objects = "strategy_objects"

    ts_names_map_additional = {}

    def get_additional_ts_map(self):
        raise NotImplementedError()

    def __init__(
            self,
            strategy_id,  # type: str
            valid_from,  # type: T.Union[datetime.date, int]
            valid_until,  # type: T.Union[datetime.date, int]
            ts_raster=COMMON.QUARTER,  # type: int
            algo_name="USERDEF",  # type: str
            package_path=None,  # type: str
            set_default_limits=True,  # type: bool
            additional_algo_ts=None,  # type: T.ListType[str]
            user_ts=None,  # type: T.ListType[str]
            **kwargs  # type: dict
    ):  # -> None
        """

        :param strategy_id: unique strategy id
        :type strategy_id: str
        :param valid_from: UTC validity start range for Trading Bot
        :type valid_from: T.Union[datetime.date, int]
        :param valid_until: UTC validity end range for Trading Bot
        :type valid_until: T.Union[datetime.date, int]
        :param ts_raster: time series time slot duration
        :type ts_raster: int
        :param algo_name: name of used algorithm
        :type algo_name: str
        :param package_path: path to strategy package
        :type package_path: str
        :param set_default_limits: set default limit values for purchase/sales volume/price
        :type set_default_limits: bool
        :param additional_algo_ts: time series to be added directly to the strategy strategy json, as opposed to user_ts
        :type additional_algo_ts: list[Str]
        :param user_ts: time series to be added under 'user_defined_timeseries' in the strategy json
        :type user_ts: list[Str]
        """
        self.ts_names_map = TIMESERIES_NAMES_MAP.copy()
        self.ts_names_map.update(self.ts_names_map_additional)
        self.ts_names_map.update(self.get_additional_ts_map())

        self.strategy_id = strategy_id
        self.package_path = package_path
        self.params = self.default_params(algo_name)

        # convert timeseries names to be the standard ones if necessary.
        # this maintains compatibility with the abbreviated timeseries names,
        # such as "price_purchase", which could be used in backtests instead
        # of the standard name "strategy_price_purchase"
        kwargs = {self.tsname2realtsname(k): v for k, v in kwargs.items()}

        self.params.update(kwargs)

        # Make and fill the TS frame with the provided validities and rasterization
        self.ts_raster = ts_raster
        if isinstance(valid_from, datetime.date):
            valid_from = ALU.convert_dt_to_timestamp(valid_from)
        if isinstance(valid_until, datetime.date):
            valid_until = ALU.convert_dt_to_timestamp(valid_until)
        self.valid_from = valid_from
        self.valid_until = valid_until

        if user_ts is not None:
            # add user timeseries seperate from other algo timeseries
            # such that it can packaged seperately when creating the strategy_json message.
            self.user_ts = user_ts
        if additional_algo_ts and len(additional_algo_ts) > 0:
            self.algo_ts_names.extend(additional_algo_ts)

        self.ts_names = [self.tsname2realtsname(c) for c in self.ts_names]
        self.algo_ts_names = [self.tsname2realtsname(c) for c in self.algo_ts_names]
        self.limits_ts_names = [self.tsname2realtsname(c) for c in self.limits_ts_names]
        self.user_ts = [self.tsname2realtsname(c) for c in self.user_ts]

        self.ts_frame = _NumpyTSFrame(
            self.valid_from, self.valid_until, self.ts_raster,
            self.ts_names + self.algo_ts_names + self.limits_ts_names, self.user_ts
        )

        for ts_name in self.ts_names + self.algo_ts_names + self.limits_ts_names + self.user_ts:
            ts_values = self.params.get(ts_name)
            if not ts_values:  # if ts_values is None or no values are set, then skip
                continue
            for begin, end, value in [(v["begin"], v["end"], v["value"]) for v in ts_values]:
                self.fill(ts_name, value, begin, end, overwrite=True)

        for ts_name, ts_values in kwargs.get("timeseries", {}).iteritems():
            self.fill(ts_name, ts_values, overwrite=True)

        if set_default_limits:
            self.set_default_limits()

    def set_default_limits(self):
        """Sets default limits to the corresponding limit timeseries in the ts_frame of the strategy"""
        for ts_name, ts_values in DEFAULT_LIMIT_VALUES.iteritems():
            self.fill(ts_name, values=ts_values, from_ts=None, to_ts=None, overwrite=False)

    def default_params(self, unused_algo_name):
        """Returns default parameters of the strategy definition"""
        return {}

    def prepare_package(self):
        """
        Helper function that takes the strategy package file(s) and returns it as base64 encoded string.
        :return: The strategy package as base64 encoded string
        :rtype: string
        """
        if self.package_path.endswith(".zip"):
            with open(self.package_path, "rb") as f:
                return base64.b64encode(f.read())
        else:
            return zip_folder(self.package_path)

    def fill(self, ts_name, values=0.0, from_ts=None, to_ts=None, overwrite=True):
        """Fills timeseries with ts_name stored in the strategy ts_frame with the given values"""
        self.ts_frame.fill(self.tsname2realtsname(ts_name), values, from_ts=from_ts, to_ts=to_ts, overwrite=overwrite)

    def to_dict(self):
        # start building all params by taking the timeseries from numpy
        ts_params = self.ts_frame.to_dict()
        # get the standard parameters
        params = self.params.copy()
        # update standard parameters by timeseries filled into the strategy definition
        params.update(ts_params)
        return params

    def export(self, timestamp=None):
        """
        Export the strategy data into a message understood by autoTRADER.
        :param timestamp: The time at which the strategy/ strategy update should be sent to autoTRADER
        :type timestamp: float or datetime.datetime
        :return: A dictionary representing the strategy
        :rtype: dict
        """
        if timestamp is None:
            # If no timestamp is given, start 1 minute before the timeseries become valid.
            timestamp = self.valid_from - COMMON.MINUTE
        elif isinstance(timestamp, datetime.date):
            timestamp = ALU.convert_dt_to_float_timestamp(timestamp)
        return {
            "message_type": "strategy",
            "exchange": "PERIOTHEUS",
            "data": {self.strategy_objects: {self.strategy_id: self.to_dict()}},
            "timestamp": timestamp
        }

    def tsname2realtsname(self, tsname):
        """Map timeseries names as used in backtesting (without "strategy_") to real timeseries names of standard ts

        :type tsname: str
        :rtype: str
        """
        return self.ts_names_map.get(tsname, tsname)


class StrategyDefinition(StrategyDefinitionBase):
    """Definition of strategy with common set of timeseries for tradable positions and prices for all algorithms.
    Models strategies transferred from Periotheus (for strategies transferred via the REST-API, use
    backtesting/strategy_configuration.py)
    """

    ts_names = [
        "price_purchase",
        "price_sales",
        "position_tradable_position_short",
        "position_tradable_position_long",
        "price_purchase_immediate_vesting",
        "price_sales_immediate_vesting",
        "price_minimum_spread_buyback",
        "price_forecast_trend",
        "position_deviation",
    ]

    def get_additional_ts_map(self):
        return {}

    def __init__(
            self,
            strategy_id,  # type: str
            valid_from,  # type: T.Union[datetime.date, int]
            valid_until,  # type: T.Union[datetime.date, int]
            ts_raster=COMMON.QUARTER,  # type: int
            algo_name="USERDEF",  # type: str
            package_path=None,  # type: str
            set_default_limits=True,  # type: bool
            additional_algo_ts=None,  # type: T.ListType[str]
            user_ts=None,  # type: T.ListType[str]
            **kwargs  # type: dict
    ):  # -> None
        """

        :param strategy_id: unique strategy id. If more strategies will be sent with the same id,
                            it will simulate an update
        :param valid_from: utc datetime! timeseries will be filled from this time with the given raster size
        :param valid_until: utc datetime! timeseries will be filled until this time with the given raster size
        :param ts_raster: mostly 15min or hour, timeseries values granularity
        :param algo_name: name of the algorithm
        :param package_path: folder which contains the custom_strategy.py
        :param set_default_limits: let backtesting set the default limits
        :param additional_algo_ts: algorithm timeseries to be set, which are not userdefined timeseries
        :param user_ts: names of timeseries which are in the userdefined part of the strategy json
        :param kwargs: arguments such as packagename, which are the foldername which contains the custom_strategy.py
        """
        if algo_name == "STRATEGY_FLEXIBILTY_ALGO":
            # if using the flexibility algorithm as a strategy, then add the
            # flex specific timeseries in a way that they are reachable as user_defined_timeseries
            self.user_ts = [COMMON.StrategyJsonKey.UDFTS.pos_closed,
                            COMMON.StrategyJsonKey.UDFTS.prod_filter,
                            COMMON.StrategyJsonKey.UDFTS.ramp]
            for i in range(1, 8):
                self.user_ts.extend([COMMON.StrategyJsonKey.UDFTS.pos_sell_scale.format(i),
                                     COMMON.StrategyJsonKey.UDFTS.pos_buy_scale.format(i),
                                     COMMON.StrategyJsonKey.UDFTS.price_buy_scale.format(i),
                                     COMMON.StrategyJsonKey.UDFTS.price_sell_scale.format(i)])

        if package_path is not None and kwargs.get("packagename") is None:
            if package_path.endswith(".zip"):
                kwargs["packagename"] = "package"
            else:
                kwargs["packagename"] = os.path.basename(os.path.normpath(package_path))

        super(StrategyDefinition, self).__init__(strategy_id, valid_from, valid_until,
                                                 ts_raster, algo_name, package_path,
                                                 set_default_limits, additional_algo_ts, user_ts, **kwargs)

    def default_params(self, algo_name):
        params = {
            COMMON.StrategyJsonKey.internal_number: self.strategy_id,
            COMMON.StrategyJsonKey.comment: None,
            COMMON.StrategyJsonKey.maximum_purchase_price: 100,
            COMMON.StrategyJsonKey.maximum_neg_buyback: 4,
            COMMON.StrategyJsonKey.user_defined_timeseries: {},
            COMMON.StrategyJsonKey.stop_on_limit_violation: None,
            COMMON.StrategyJsonKey.approved_group: None,
            COMMON.StrategyJsonKey.maximum_bid: 100,
            COMMON.StrategyJsonKey.standard_deviation_end: None,
            COMMON.StrategyJsonKey.market_area_1: "10YDE-VE-------2",
            COMMON.StrategyJsonKey.valid_from: None,
            COMMON.StrategyJsonKey.maximum_sales_volume_per_product: 100,
            COMMON.StrategyJsonKey.standard_deviation_begin: None,
            COMMON.StrategyJsonKey.minimum_sales_price: 0,
            COMMON.StrategyJsonKey.maximum_purchase_volume_per_product: 100,
            COMMON.StrategyJsonKey.minimum_spread_for_buyback: None,
            COMMON.StrategyJsonKey.last_prognosis_before_market_closure: None,
            COMMON.StrategyJsonKey.short_name: None,
            COMMON.StrategyJsonKey.packagename: None,
            COMMON.StrategyJsonKey.trading_end_before_market_closure: None,
            COMMON.StrategyJsonKey.approved_privs: "NONE",
            COMMON.StrategyJsonKey.immediate_purchase_price: None,
            COMMON.StrategyJsonKey.maximum_order_book: None,
            COMMON.StrategyJsonKey.global_privs: "NONE",
            COMMON.StrategyJsonKey.active: None,
            COMMON.StrategyJsonKey.lifecycle: 3000,
            COMMON.StrategyJsonKey.owner_group: None,
            COMMON.StrategyJsonKey.risk_affinity: None,
            COMMON.StrategyJsonKey.neg_buyback_period: 120,
            COMMON.StrategyJsonKey.immediate_sales_price: None,
            COMMON.StrategyJsonKey.valid_to: None,
            COMMON.StrategyJsonKey.maximum_imbalance_on_market_closure: None,
            COMMON.StrategyJsonKey.behavior: "BALANCED",
            COMMON.StrategyJsonKey.exchange_1: "EPEX",
            COMMON.StrategyJsonKey.maximum_ask: 100,
            COMMON.StrategyJsonKey.algorithm: algo_name,
            COMMON.StrategyJsonKey.hour: None,
        }
        # Extract the package for user-defined strategies
        if algo_name == "USERDEF":
            assert self.package_path is not None
            params["package"] = self.prepare_package()
        return params

    @staticmethod
    def strat_identifier_from_params(params):
        """
        creates a strategy identifier from provided strategy params
        :param params: StrategyDefinition params
        :type params: typing.Dict[str, Any]
        :return:
        :rtype: str
        """
        if params.get("object_type") == "StrategyConfigurationObject":
            id_parts = [params["internal_number"], params["package_name"]]
        else:
            # For Periotheus strategies we use ID, hash, algorithm and packagename (sic!)
            # The packagename is spelled without underscore for Periotheus strategies,
            # but with for StrategyConfigurationObjects
            if params["algorithm"] == "USERDEF":
                strat_hash = hashlib.md5(params["package"]).hexdigest()
            else:
                package_path = os.path.join(
                    own_strategies_dir(),
                    COMMON.SupportedStrategies.get_algorithm_from_mongo_name(params["algorithm"])
                )
                b64_package = base64.b64encode(zip_folder(package_path))
                strat_hash = hashlib.md5(b64_package).hexdigest()

            id_parts = [params["internal_number"], strat_hash, params["algorithm"]]
            if params["algorithm"] == "USERDEF":
                id_parts.append(params["packagename"])

        return "__".join(id_parts)


def zip_folder(folder):
    """
    Returns a string with a zip archive containing the contents of provided folder
    :param folder: the folder
    :type folder: str
    :return: the zip archive
    :rtype: str
    """
    ziparchive = StringIO.StringIO()
    with contextlib.closing(zipfile.ZipFile(ziparchive, "w")) as archive:
        for file in os.listdir(folder):
            if file.endswith(".py"):
                with open(os.path.join(folder, file), "r") as fl_content:
                    archive.writestr(file, fl_content.read())
    package = ziparchive.getvalue()
    ziparchive.close()
    return package
