#!/usr/bin/python3
# -*- coding: utf-8 -*-

from __future__ import absolute_import

import collections
import copy
import datetime
import json
import math
import time

import six
from six.moves import range
from six.moves import zip

import autotrader_core._strategy_datastructures as STRATDATA
import autotrader_lib.common as COMMON
import autotrader_lib.compliance_log_templates as LOGTEMP
import autotrader_core.exchange_trading as APITR
import autotrader_core.persistence as PERSIST
import autotrader_core.strategy_utils as SU
import autotrader_lib.cet_util as ALCU
import autotrader_lib.py2_funcs as PY2LIB
import autotrader_lib.unit_util as UU

if six.PY2:
    import autotrader_lib.fast_logging_py2 as FLOG
else:
    import autotrader_lib.fast_logging_py3 as FLOG

# replace this import as soon as typing is available.
# this also makes it python 3 compatible, where typing is a standard library
try:
    import typing  # pylint: disable=F0401
except ImportError:
    import types as typing

limit_logger = FLOG.getLogger("limit_management")
log = FLOG.getLogger("autotrader.strategy")

_MAX_VALID_TO = 4000000000

# Expose StrategyTimeSeries to the customer in the scope of this module
StrategyTimeSeries = STRATDATA.StrategyTimeSeries

# DEFAULT values, if exchange value is missing
DEFAULT_MIN_MWH_QTY = 240
DEFAULT_STEP_MWH_QTY = 10


def is_integer_multiple(number, tick, digits=COMMON.MACHINE_ERROR_DIGITS):
    """Check if number is an integer multiple of a positive tick, with rounding at defined machine error

    :param number: number to check
    :type number: float
    :param tick: smallest increments
    :type tick: float
    :param digits: digits to round of machine error
    :type digits: int
    :return: True if number is integer multiple of tick, otherwise False
    :rtype: bool
    """
    return number == 0 or (abs(number) >= tick > 0 and round(number / tick, digits).is_integer())


def mk_strategy_tr_dict(tr_data, aggregator=None):
    """Helper function returning StrategyTimeSeries object filled with tr_data

    :param tr_data: timeseries data as transferred from Periotheus
    :type tr_data: typing.List[typing.Dict]
    :param aggregator: specifies the type of the timeseries aggregation, if needed
    :type aggregator: str
    :return: StrategyTimeSeries object with the data corresponding to the provided tr_data
    :rtype: :class:`STRATDATA.StrategyTimeSeries`
    """
    if not tr_data:
        return StrategyTimeSeries()

    agg = STRATDATA.aggregator_function(aggregator)
    return StrategyTimeSeries.from_tr_data(tr_data, agg)


Property = collections.namedtuple("property", ["min_quantity", "price_tick", "qty_tick", "unit", "name"])


class SlotResponse(object):
    """
    The SlotResponseObject holds information if placing a slot was successful.

    The function place_slots returns a list of these objects, with one SlotResponse object per placed slot.

    The 3 public attributes of this object are "succeeded", "action" and "reason".
    This object evaluates to True if succeeded is True, which is the case, if placing the slot worked as intended.

    The action is one of COMMON.SlotResponseAction and the reason one of COMMON.SlotResponseReason.

    Actions do not map 1:1 to succeeded. E.g. If an order exists that exactly matches the slot,
    then succeeded would be True, action would be "ignored" and reason would be "unchanged".

    Similarly, if an otherwise invalid slot is placed with quantity 0, then succeeded would be True, because invalid
    slots cause order removal, just like quantity 0 slots do.

    If placing a slot for a non-existing order fails, then the action would be "ignored" again,
    but succeeded would be False and the reason would give more information on why it failed.

    Note that this only checks if placing the slot is possible, not if the resulting order will actually make it
    through the order_guard and internal market to the exchange as those are asynchronous processes.

    Additionally, sometimes placing a slot can fail in one iteration and work again in the next iteration,
    e.g. if we are waiting for confirmation of an entry order request for this slot_type.
    """

    def __init__(self, succeeded, action, reason, internal_id=""):
        """

        :type succeeded: bool
        :param action: member of `class:COMMON.SlotResponseAction`
        :type action: str
        :param reason: member of `class:COMMON.SlotResponseReason`
        :type reason: str
        :param internal_id: The internal_id of the order that is created/ updated by this slot. If one slot leads to
                            the deletion of multiple orders, the internal ids are concatenated with a comma. If no
                            order is created, this is empty.
                            Note: The internal_id is used mostly for logging and should not be used
                            by the strategy directly.
        :type internal_id: str
        """
        self.succeeded = succeeded
        self.action = action
        self.reason = reason
        self._internal_id = internal_id

    def __str__(self):
        details = []
        if self.reason:
            details.append(self.reason)
        if self._internal_id and self.action in [COMMON.SlotResponseAction.create, COMMON.SlotResponseAction.modify,
                                                 COMMON.SlotResponseAction.delete]:
            details.append(self._internal_id)
        if details:
            detail_str = " ({})".format("; ".join(details))
        else:
            detail_str = ""
        return "{}{}".format(self.action, detail_str)

    def __repr__(self):
        return "{}({}, {}, {}, {})".format(self.__class__.__name__, self.succeeded, self.action, self.reason,
                                           self._internal_id)

    def __bool__(self):
        return self.succeeded

    def __eq__(self, other):
        return self.succeeded == other.succeeded and self.action == other.action and self.reason == other.reason

    __nonzero__ = __bool__


class StrategyBase(object):
    """Class to Allow Strategy Mixins, to close diamond shape dependencies"""

    def __init__(self, *args, **kwargs):
        self.log = log
        self.caption = ""
        # initialize strategy_id, this will be overwritten by the first on_strategy_update in the child strategy
        self.strategy_id = "unset_strategy_id"

        # also define other standard strategy fields here, to enable them in the mixins
        self.additional_views = dict()
        self.exchange_1 = None
        self.exchange_2 = None
        self.delivery_areas = None
        self.delivery_area_id = None
        self.view_delivery_areas = set()
        self.strategy_settings = dict()
        self.strategy_settings.setdefault(None)
        self.valid_from = 0
        self.valid_to = _MAX_VALID_TO
        self.maximum_neg_buyback = 4
        self.neg_buyback_period = 120
        self.active = False
        self.halted = False  # emergency halt flag
        self.halt_reason = None
        self._remove_orders = False
        self.last_db_global_log_error = None
        self.last_db_global_log_info = None
        self.last_db_global_log_state = None
        self._pt_active = False
        self.llq_spread1_indicator = None
        self.llq_spread1_limit = None
        self.llq_spread2_indicator = None
        self.llq_spread2_limit = None
        self.trading_start = None
        self._compliance_logger = None
        self.strategy_type = "nonset"
        self.stop_on_limit_violation = False
        self.maximum_bid = None
        self.maximum_ask = None

    @property
    def remove_orders(self):
        return self._remove_orders

    def on_strategy_update(self, strategy_json):
        """empty method, such that the diamond relationships can resolve the call order"""
        pass

    def _add_header(self, text, product=None):
        """Return unified message pretext for log messages of a strategy

        :param text: log message
        :type text: str
        :param product: current product processed when log is called
        :type product: autotrader_core.exchange_trading.Product
        :rtype: str
        """

        if product is not None:
            return "%s[%s, %s]: %s" % (self.strategy_id, product.product_id, product.name, text)
        else:
            return "%s: %s" % (self.strategy_id, text)

    def debug_log(self, text, product=None):
        """This adds the strategy id, and optionally product id and name at the beginning of the debug log

        This additional information helps to identify log entries by a strategy, especially if multiple strategies are
        run with the same algorithm.

        :param text: log message
        :type text: str
        :param product: current product processed when log is called
        :type product: autotrader_core.exchange_trading.Product
        :rtype: NoneType
        """
        self.log.debug(self._add_header(text, product))

    def info_log(self, text, product=None):
        """This adds the strategy id, and optionally product id and name at the beginning of the info log

        :param text: log message
        :type text: str
        :param product: current product processed when log is called
        :type product: autotrader_core.exchange_trading.Product
        :rtype: NoneType
        """
        self.log.info(self._add_header(text, product))

    def error_log(self, text, product=None):
        """This adds the strategy id, and optionally product id and name at the beginning of the error log

        This additional information helps to identify log entries by a strategy, especially if multiple strategies are
        run with the same algorithm.

        :param text: log message
        :type text: str
        :param product: current product processed when log is called
        :type product: autotrader_core.exchange_trading.Product
        :rtype: NoneType
        """
        self.log.error(self._add_header(text, product))

    def warn_log(self, text, product=None):
        """This adds the strategy id, and optionally product id and name at the beginning of the warning log

        :param text: log message
        :type text: str
        :param product: current product processed when log is called
        :type product: autotrader_core.exchange_trading.Product
        :rtype: NoneType
        """
        self.log.warning(self._add_header(text, product))

    def exception_log(self, text, product=None):
        """This adds the strategy id, and optionally product id and name at the beginning of the exception log

        :param text: log message
        :type text: str
        :param product: current product processed when log is called
        :type product: autotrader_core.exchange_trading.Product
        :rtype: NoneType
        """
        self.log.exception(self._add_header(text, product))


class Strategy(StrategyBase):
    """Base class for Strategies.

    Inherit from that class and overwrite the ``'on_...'`` methods or the custom_act
    or custom_act_for_product methods in order to specify the strategy action.
    """

    def __init__(self, autotrader_instance, strategy_id, caption, strategy_package_name):
        # set logger handler to be the one defined in this file. baseclass also will use self.log for logging
        super(Strategy, self).__init__()
        self.log = log

        self.autotrader = autotrader_instance
        self.strategy_id = strategy_id
        self.caption = caption
        self.strategy_package_name = strategy_package_name
        self.set_compliance_logger(log)

        self.strategy_limit_maximum_sales_volume = STRATDATA.StrategyTimeSeries(COMMON.QUARTER,
                                                                                STRATDATA.aggregator_function(
                                                                                    "min_nonone"))
        self.strategy_limit_maximum_purchase_volume = STRATDATA.StrategyTimeSeries(COMMON.QUARTER,
                                                                                   STRATDATA.aggregator_function(
                                                                                       "min_nonone"))
        self.strategy_limit_maximum_purchase_price = STRATDATA.StrategyTimeSeries(COMMON.QUARTER,
                                                                                  STRATDATA.aggregator_function("min"))
        self.strategy_limit_minimum_sales_price = STRATDATA.StrategyTimeSeries(COMMON.QUARTER,
                                                                               STRATDATA.aggregator_function("max"))

        self._per_product_limits = STRATDATA.LimitContainer.from_db(self.strategy_id)

    @property
    def per_product_limits(self):
        """
        Gives read-only access to a container holding the limits per product of the strategy.

        Note: Currently, this feature is only supported for strategies on the TRAYPORT exchange.

        To get the actual limit value, use it like this:
        strategy_instance.per_product_limits.get_limit("maximum_purchase_volume", product_instance)

        :return: The limit container instance
        :rtype: STRATDATA.LimitContainer
        """
        return self._per_product_limits

    @property
    def exchange(self):
        return self.autotrader.get_exchange(self.exchange_1)

    @property
    def exchanges(self):
        if self.exchange_2:
            return [self.autotrader.get_exchange(self.exchange_1),
                    self.autotrader.get_exchange(self.exchange_2)]
        else:
            return [self.autotrader.get_exchange(self.exchange_1)]

    def on_strategy_emergency_update(self, halted, halt_reason=None, remove_orders=None, username=None):
        self.debug_log("Strategy Active is: {active}".format(active=self.active))
        self.debug_log("Update Emergency halt to: {halted}".format(halted=halted))
        if halted:
            self.compliance_log(log_entry=LOGTEMP.StrategyBasicLogs.strategy_halted,
                                reason=halt_reason,
                                orders_removed=remove_orders,
                                username=username)
            self._remove_orders = remove_orders
        elif self.halted:
            self.compliance_log(log_entry=LOGTEMP.StrategyBasicLogs.strategy_started,
                                username=username)
            self._remove_orders = False
        self.halted = halted
        self.halt_reason = halt_reason
        self.update_active_flag(username)

        self.debug_log("Update on halt: Strategy Emergency Halt flag to: {halted}, "
                       "strategy.active is now set to: {active}"
                       .format(halted=self.halted, active=self.active))

    def _handle_limits_on_strategy_update(self):
        """Set an empty limit container if no limits are set and update the database."""
        # In case the exchange was changed (should not happen), update it here to avoid unexpected behavior.
        # the container is created empty on init and we do not know the exchange yet on init
        self._per_product_limits._exchange_id = self.exchange_1
        self._per_product_limits.update_db(time.time())

    def on_strategy_update(self, strategy_json):
        """
        Callback used when we receive a new strategy object from mongo and sets some attribute on the object.
        :param strategy_json: the mongo object
        :type strategy_json: dict
        :return: returns None (method call always successful)
        :rtype: NoneType
        """
        # this is necessary to control the strategy with the emergency halt
        super(Strategy, self).on_strategy_update(strategy_json)
        self.strategy_settings = strategy_json

        # at least 1 market area has to be set
        delivery_areas = [
            strategy_json[COMMON.StrategyJsonKey.market_area_1]
            if COMMON.StrategyJsonKey.market_area_1 in strategy_json
            else strategy_json[COMMON.StrategyJsonKey.market_area]
        ]
        self.delivery_area_id = delivery_areas[0]

        # optional second market area
        if (COMMON.StrategyJsonKey.market_area_2 in strategy_json
                and strategy_json[COMMON.StrategyJsonKey.market_area_2] is not None):
            delivery_areas.append(strategy_json[COMMON.StrategyJsonKey.market_area_2])

        self.delivery_areas = delivery_areas

        # load max bid and ask used by orderguard to limit order size
        self.maximum_bid = strategy_json[COMMON.StrategyJsonKey.maximum_bid]
        self.maximum_ask = strategy_json[COMMON.StrategyJsonKey.maximum_ask]

        self.stop_on_limit_violation = strategy_json[COMMON.StrategyJsonKey.stop_on_limit_violation]

        # load limits used by order guard to check traded volume and order sizes
        self.strategy_limit_maximum_sales_volume = mk_strategy_tr_dict(
            strategy_json[COMMON.StrategyJsonKey.TS.limit_sell_vol],
            COMMON.AggregatorRule.min_nonone
        )
        self.strategy_limit_maximum_purchase_volume = mk_strategy_tr_dict(
            strategy_json[COMMON.StrategyJsonKey.TS.limit_buy_vol],
            COMMON.AggregatorRule.min_nonone
        )
        self.strategy_limit_maximum_purchase_price = mk_strategy_tr_dict(
            strategy_json[COMMON.StrategyJsonKey.TS.limit_buy_price],
            COMMON.AggregatorRule.min
        )
        self.strategy_limit_minimum_sales_price = mk_strategy_tr_dict(
            strategy_json[COMMON.StrategyJsonKey.TS.limit_sell_price],
            COMMON.AggregatorRule.max
        )

        self.maximum_neg_buyback = strategy_json.get(COMMON.StrategyJsonKey.maximum_neg_buyback, None) or 4
        self.neg_buyback_period = strategy_json.get(COMMON.StrategyJsonKey.neg_buyback_period, None) or 120
        self.valid_from = strategy_json[COMMON.StrategyJsonKey.valid_from] or 0
        self.valid_to = strategy_json[COMMON.StrategyJsonKey.valid_to] or _MAX_VALID_TO

        self.exchange_1 = strategy_json.get(COMMON.StrategyJsonKey.exchange_1,
                                            strategy_json.get(COMMON.StrategyJsonKey.exchange))

        # exchange_2 is DEPRECATED and should not be used! It is not fully supported and probably never will be
        self.exchange_2 = strategy_json.get(COMMON.StrategyJsonKey.exchange_2)
        if self.exchange_2:
            self.warn_log("Uses 2 exchanges which is not fully supported, never will be and is thus deprecated.")

        if self._pt_active and not strategy_json[COMMON.StrategyJsonKey.active]:
            self.debug_log("Strategy is switched to inactive. Removing all orders immediately")
            self.remove_orders_of_product()

        self._pt_active = strategy_json[COMMON.StrategyJsonKey.active]
        username = COMMON.PeriotheusSystemUsers.get_username_from_obj(strategy_json, COMMON.StrategyJsonKey.username)
        self.update_active_flag(username)

        # Limits to change into low Liquidity Mode:
        # 1 = 5 MW, 2 = 10 MW ... 19 = 95 MW - on BOTH SIDES of the orderbook
        self.llq_spread1_indicator = strategy_json.get(COMMON.StrategyJsonKey.llq_spread1_indicator, 2)
        # if MW spread 1 is higher than this value it is Low Liquidity mode
        self.llq_spread1_limit = strategy_json.get(COMMON.StrategyJsonKey.llq_spread1_limit, 3.)
        # 1 = 5 MW, 2 = 10 MW ... 19 = 95 MW - on BOTH SIDES of the orderbook
        self.llq_spread2_indicator = strategy_json.get(COMMON.StrategyJsonKey.llq_spread2_indicator, 19)
        # if MW spread 2 is higher than this value it is Low Liquidity mode
        self.llq_spread2_limit = strategy_json.get(COMMON.StrategyJsonKey.llq_spread2_limit, 30.)
        # Settings  2 / 3.0:   5MW - spread  >  3 EUR or no  10MW at all --> LLQ
        # Settings 20 / 30.0: 20MW - spread  > 30 EUR or no 100MW at all --> LLQ

        # Trading start = t: trading starts t hours before Gate Closure of the product
        self.trading_start = strategy_json.get(COMMON.StrategyJsonKey.trading_start, 180.)

        self._handle_limits_on_strategy_update()

        compliance_json = dict()
        for key in strategy_json:
            if type(strategy_json[key]) == list and len(strategy_json[key]) > 0 and type(
                    strategy_json[key][0]) == dict and "begin" in strategy_json[key][0]:
                # we filter out filled timeseries. If a timeseries is empty, it will be logged,
                # e.g. {..., "some_timeseries": [], ...}
                continue
            if key == COMMON.StrategyJsonKey.user_defined_timeseries:
                # user-defined timeseries have different format, e.g.
                # {... "user_defined_timeseries": {"some_name": [{"begin": 1614250800, ... }
                # so we filter here just by name
                continue
            if key == COMMON.StrategyJsonKey.package:
                # we also do not log the content of the archive with a strategy
                continue
            compliance_json[key] = strategy_json[key]
        for key in (COMMON.StrategyJsonKey.valid_to, COMMON.StrategyJsonKey.valid_from):
            if key in compliance_json and isinstance(compliance_json[key], int):
                compliance_json[key] = datetime.datetime.utcfromtimestamp(compliance_json[key]).strftime(
                    COMMON.DATEFORMAT)
        self.compliance_log(log_entry=LOGTEMP.StrategyBasicLogs.strategy_config_changed,
                            username=username,
                            config=compliance_json)
        return None

    def on_strategy_configuration_update(self, strategy_json):
        """This callback function is used for new strategies/ strategy updates from the REST-API.

        It is called when a COMMON.MongoDBObjects.strategy_configuration object is updated in
        mongo and it sets some attribute on the object.

        :param strategy_json: the mongo object
        :type strategy_json: dict
        :return: returns None (method call always successful)
        :rtype: NoneType
        """
        ignore = [COMMON.StrategyJsonKey.package]
        log.compliance_log(log_entry=LOGTEMP.StrategyBasicLogs.strategy_config_changed,
                           strategy_id=strategy_json.get(COMMON.StrategyJsonKey.internal_number),
                           username=strategy_json.get(COMMON.StrategyJsonKey.username),
                           data={key: value for key, value in strategy_json.items() if key not in ignore})
        self.caption = strategy_json[COMMON.StrategyJsonKey.caption]
        self.strategy_settings = strategy_json
        self.delivery_areas = [strategy_json.get(COMMON.StrategyJsonKey.market_area_1)]
        for optional_market_area in [COMMON.StrategyJsonKey.market_area_2,
                                     COMMON.StrategyJsonKey.market_area_3,
                                     COMMON.StrategyJsonKey.market_area_4,
                                     COMMON.StrategyJsonKey.market_area_5]:
            if strategy_json.get(optional_market_area) is not None:
                self.delivery_areas.append(strategy_json[optional_market_area])
            else:
                break  # if market area 2 is not defined then market area 3 won't be either

        self.delivery_area_id = strategy_json.get(COMMON.StrategyJsonKey.market_area_1)

        # Check if there are additional view types
        self.view_delivery_areas = set()
        self.additional_views = {}
        for key, value in strategy_json.items():
            if isinstance(value, dict) and value.get("_type") == "view":
                self.view_delivery_areas |= set(value.get("instrument_ids"))
                self.additional_views[key] = value.get("instrument_ids")

        self.stop_on_limit_violation = strategy_json.get(COMMON.StrategyJsonKey.stop_on_limit_violation)
        self.exchange_1 = (strategy_json.get(COMMON.StrategyJsonKey.exchange_1)
                           or strategy_json.get(COMMON.StrategyJsonKey.exchange))
        if self._pt_active and not strategy_json.get(COMMON.StrategyJsonKey.active):
            self.debug_log("Strategy is switched to inactive. Removing all orders immediately")
            self.remove_orders_of_product()
        self._pt_active = strategy_json.get(COMMON.StrategyJsonKey.active)
        self.update_active_flag(strategy_json.get(COMMON.StrategyJsonKey.username))
        self._handle_limits_on_strategy_update()
        return None

    def on_synthetic_order(self, payload):
        raise NotImplementedError("This only works for Synthetic Order strategy types")

    def check_epex_timestamp_halt(self, timestamp):
        """Legacy function in strategy.py"""
        return self.check_exchange_timestamp_halt(timestamp)

    def check_exchange_timestamp_halt(self, timestamp):
        """This method checks if timestamp is in within the boundaries of a predefined market halt set in periotheus.

        If the timestamp is within a market halt period the method will return a
        list with the beginning timestamp of the market halt period.
        If the timespan is not within a market halt it will return an empty list.
        """
        try:
            market_halt_set = self.exchange.market_halt_set
        except AttributeError:
            return []
        timestamp_in_halt = [market_halt_set[i][0] for i in range(len(market_halt_set))
                             if market_halt_set[i][0] <= timestamp < market_halt_set[i][1]]
        return timestamp_in_halt

    def get_strategy_timerow_settings(self, field_definitions, product_interval):
        # field definitions: (field_name, default)
        result = []
        for field_name, default in field_definitions:
            try:
                result.append(getattr(self, field_name).get(product_interval, default))
            except AttributeError:
                result.append(default)
        return result

    def filter_callback(self, attr_name, attr_value):
        """This callback should filter out attributes that should not be dumped on the strategies/state_dump call."""
        if attr_value is not None:
            return hasattr(attr_value, "__dict__")
        return True

    def dump_state(self):
        """This method will be called on the strategies/state_dump rest api call.
        It should return an object that can be pickled."""
        values = {}
        for attr_name, attr_value in self.__dict__.items():
            if not self.filter_callback(attr_name, attr_value):
                if isinstance(attr_value, collections.defaultdict):
                    values[attr_name] = dict(attr_value)
                else:
                    values[attr_name] = attr_value
        return values

    def remove_my_orders_from_product(self, product):
        """Remove all own orders of the strategy on the given product

        Note: This function is used for autoTRADER halts and by-passes some validations.
              Strategies should preferably place slots with quantity 0 instead of using this function.

        :type product: autotrader_core.exchange_trading.Product
        """
        orders = product.orders.get(portfolio_key=self.strategy_id)
        if orders:
            self.debug_log("Removing my orders from the product. "
                           "Internal ids: {}".format(", ".join(o.internal_id for o in orders)), product)
            for order in orders:
                if order.state == COMMON.OrderState.hibe and not isinstance(order, APITR.ComTraderOrder):
                    # we set reactivate here so we detect that the order should be removed when a halt happens
                    order.reactivate = True
            self.autotrader.modify_orders([o.modify(quantity=0.) for o in orders],
                                          execmode=COMMON.InternalExecutionMode.default)

    def act(self, timestamp, *args, **kwargs):
        if not self.active:
            return
        self.debug_log("act")
        log_data = []
        start_act_ts = time.time()
        self.custom_act(log_data, timestamp, *args, **kwargs)
        now = time.time()
        # log time elapsed since the call of custom act
        # log time since event, which references to the timestamp
        self.debug_log("act-finish: elapsed:%.6f s, time-since-event:%.6f s" % ((now - start_act_ts),
                                                                                (now - timestamp)))

    def custom_act(self, log_data, timestamp, products=None):
        pass

    def _check_area_active_criteria_on_product(self, product):
        """
        Function to verify that a product is active on all delivery areas
        :param product: The product to be checked
        :type product: APITR.Product
        :return: True if active on all areas False if not, and delivery area
        :rtype: (bool, str)
        """
        for delivery_area_id in self.delivery_areas:
            if product.state(delivery_area_id) != COMMON.DeliveryAreaState.active:
                return False, delivery_area_id
        return True, ""

    def act_for_product(self, product, timestamp, *args, **kwargs):
        # if market_halt: return
        log_data = {"product_caption": product.name}
        if self.exchange.market_state == COMMON.MarketState.hibernated:
            self.debug_log("Not active: because of market hibernation", product)
            log_data["err"] = "Not active: because of market hibernation, prod_id:" + product.product_id
            return log_data

        area_active_check_passed, inactive_area = self._check_area_active_criteria_on_product(product)
        if not area_active_check_passed:
            self.debug_log("Not active: because of inactive area {area}".format(area=inactive_area), product)
            log_data["err"] = (
                "Not active: because of inactive area " + inactive_area + ", prod_id: " + product.product_id)
            return log_data

        if not (self.valid_from <= product.delivery_start < self.valid_to):
            # remove all orders if this product is outside of the
            # validity range of the strategy
            # modify all orders to quantity 0.
            self.remove_my_orders_from_product(product)
            self.debug_log("outside of validity, all orders removed", product)
            log_data["err"] = "outside of validity, all orders removed prod_id " + product.product_id
            return log_data

        # remove orders if this strategy defines an earlier trading end
        trading_end_before_market_closure = self.strategy_settings.get("trading_end_before_market_closure")
        if trading_end_before_market_closure:
            end_trading_activity_at = product.delivery_start - trading_end_before_market_closure * 60
            if end_trading_activity_at < self.autotrader.current_timestamp:
                self.remove_my_orders_from_product(product)
                self.debug_log("outside of active trading interval, all orders removed", product)
                log_data["err"] = (
                    "outside of active trading interval, all orders removed, prod_id: " + product.product_id
                )
                return log_data

        res = self.custom_act_for_product(log_data, product, timestamp, *args, **kwargs)
        log_data["res"] = res

        return log_data

    def custom_act_for_product(self, log_data, product, timestamp, *args, **kwargs):
        """Act for single product

        :param log_data: additional log data to be used
        :type log_data: dict
        :param product: single product passed on this call
        :type product: APITR.Product
        :param timestamp: current timestamp
        :type timestamp: float
        :rtype: NoneType
        :return: None
        """
        return

    @staticmethod
    def get_depth_limit_reference_prices(max_own_depth_order_placement_abs_euro,
                                         max_own_depth_order_placement_relative_euro,
                                         indicators):
        """Calculate the reference prices which define what "deep in the orderbook" means

        :param max_own_depth_order_placement_abs_euro: Absolute depth in orderbook to front price in EUR
        :type max_own_depth_order_placement_abs_euro: float
        :param max_own_depth_order_placement_relative_euro: Relative depth in orderbook to front price in %
        :type max_own_depth_order_placement_relative_euro: float
        :param indicators: indicator object containing the information about bid and ask front prices
        :type indicators: :class:`OrderbookIndicator`
        :return: buy_reference, sell_reference, last_buy_price, last_sell_price
        :rtype: float, float, float, float
        """

        buy_reference = None
        sell_reference = None
        last_buy_price = None
        last_sell_price = None
        if (
            max_own_depth_order_placement_abs_euro is None
            or max_own_depth_order_placement_relative_euro is None
            or not indicators
        ):
            return buy_reference, sell_reference, last_buy_price, last_sell_price

        # get last front prices of indicators. need to use getattr,
        # because OrderBookParent does not have 'last_front_buy_orders' a.s.o.
        last_front_buy_orders = getattr(indicators, "last_front_buy_orders", [[]])
        last_front_sell_orders = getattr(indicators, "last_front_sell_orders", [[]])

        if len(last_front_buy_orders[-1]) > 0:
            last_buy_price = float(next(last_front_buy_orders[-1].__iter__()).price)
            vals = []
            if max_own_depth_order_placement_abs_euro is not None:
                vals.append(last_buy_price - max_own_depth_order_placement_abs_euro)
            if max_own_depth_order_placement_relative_euro is not None:
                vals.append(last_buy_price * (1 - max_own_depth_order_placement_relative_euro))
            if vals:
                buy_reference = float(min(vals))
        if len(last_front_sell_orders[-1]) > 0:
            last_sell_price = float(next(last_front_sell_orders[-1].__iter__()).price)
            vals = []
            if max_own_depth_order_placement_abs_euro is not None:
                vals.append(last_sell_price + max_own_depth_order_placement_abs_euro)
            if max_own_depth_order_placement_relative_euro is not None:
                vals.append(last_sell_price * (1 + max_own_depth_order_placement_relative_euro))
            if vals:
                sell_reference = float(max(vals))
        return buy_reference, sell_reference, last_buy_price, last_sell_price

    @staticmethod
    def is_update_within_reference(slot, buy_reference, sell_reference, curr_order):
        """Check if slot would mean a price update which is not pass reference prices and has a valid quantity update

        :param slot: Slot strategy intends to place
        :type slot: :class:`PositionSlot`
        :param buy_reference: reference buy price at a distance from the buy sell price
        :type buy_reference: float
        :param sell_reference: reference sell price at a distance from the from sell price
        :type sell_reference: float
        :param curr_order: currently placed own order or None
        :return: False, if the order would only update the price of a currently placed order,
                    and keep it beyond reference price.
                    True otherwise
        :rtype: bool
        """
        if curr_order is None:
            return True

        is_buy = slot.direction == COMMON.Direction.buy
        qty_change = slot.quantity != curr_order.quantity

        # ensure for later comparison, that we do not compare with None values
        if (is_buy and buy_reference is not None) or (not is_buy and sell_reference is not None):
            if is_buy:
                price_deep_in_own_side = PY2LIB.less_than(slot.price, buy_reference)
                curr_order_deep_in_own_side = curr_order.price < buy_reference
            else:
                price_deep_in_own_side = PY2LIB.bigger_than(slot.price, sell_reference)
                curr_order_deep_in_own_side = curr_order.price > sell_reference

            if (slot.quantity != 0) and (not qty_change) and (price_deep_in_own_side and curr_order_deep_in_own_side):
                return False
        return True

    @staticmethod
    def create_no_update_within_reference_msg(timestamp, max_own_depth_order_placement_abs_euro,
                                              max_own_depth_order_placement_rel_euro, last_buy_price, last_sell_price,
                                              buy_reference, sell_reference, slot, curr_order):
        # timestamp, rule, front, buy reference, sell reference, slot, current order
        return " [ts:%f, rl:%s EUR//%s rel, f: %s//%s, bref:%s, sref:%s, s:%s[%s-%s], co: %s]" % (
            timestamp,
            max_own_depth_order_placement_abs_euro,
            max_own_depth_order_placement_rel_euro,
            round(last_buy_price, 2) if last_buy_price is not None else "none",
            round(last_sell_price, 2) if last_sell_price is not None else "none",
            round(buy_reference, 2) if buy_reference is not None else "none",
            round(sell_reference, 2) if sell_reference is not None else "none",
            slot.short(False, False),
            round(slot.price_range_lo, 2) if slot.price_range_lo is not None else "none",
            round(slot.price_range_hi, 2) if slot.price_range_hi is not None else "none",
            "%s_%s@%s" % (curr_order.direction[0], curr_order.quantity, curr_order.price)
            if curr_order is not None else "none",
        )

    def place_slots(self,
                    log_data,  # type: dict
                    product,  # type: APITR.Product
                    timestamp,  # type: float
                    delivery_area_id,  # type: str
                    slots,  # type: list[PositionSlot]
                    stats=None,  # type: list | None
                    limit_minimum_sales_price=None,  # type: float | None
                    limit_maximum_purchase_price=None,  # type: float | None
                    execmode=COMMON.InternalExecutionMode.default,  # type: int
                    max_own_depth_order_placement_abs_euro=None,  # type: float | None
                    max_own_depth_order_placement_rel_euro=None  # type: float | None
                    ):
        """Pass slot to autotrader, make a sanity check and communicate to exchange if necessary

        :param dict log_data: Paste an empty (mutable) dict here, which will be filled with information
                         about the placed slots.

                         .. deprecated :: V1.108.5

                             Using this dict is DEPRECATED! Instead of evaluating this dict,
                             strategies should prefer to use the return value of this function to get information about
                             the placed slots.

        :type log_data: dict
        :param product: The product to place the slots for.
        :type product: APITR.Product
        :param timestamp: UNUSED! Kept only for backwards compatibility. Pass any value here.
        :type timestamp: float
        :param delivery_area_id: The id of the area where the slots should be placed. Note: The slot_type is only
                                 unique per area and product, not globally unique. So placing an existing slot on a
                                 different area will cause a second order, NOT a mdification from one area to another.
        :type delivery_area_id: string
        :param slots: A list of slots to place on this product/ area. Placing multiple slots for the same product/ area
                      in a single call to place_slots and not in subsequent calls (in the same strategy callback),
                      gives a slight performance improvement.
        :type slots: list[PositionSlot]
        :param stats: A list with extra information, which will be added to the text field of all the Orders
                      placed from the given slots. This is typically used to make the basis for the strategy's decision
                      to place this slot visible for debugging.

                      .. warning

                        This is not audit safe, as on Trayport, the
                        text field of trades can change afterwards if a partially traded order's text field is modified
                        after the trade was made.

                      .. deprecated:: V1.108.5

                        Use parameter ``info`` of :py:class:`~autotrader_core.strategy.PositionSlot` instead.

        :type stats: list
        :param limit_minimum_sales_price, limit_maximum_purchase_price: If a limit price is supplied, the slots are
             checked against this limit and in case of violations a 0-quantity slot is placed (remove the order, if it
             exists).

             .. note::

                 This possibility is provided for the convenience of the strategy developer, and is not
                 intended for risk management.
                 All orders are additionally checked against limits after they have been placed by the strategy,
                 independent of the limit value supplied here.
        :type limit_minimum_sales_price: float
        :type limit_maximum_purchase_price: float
        :param execmode: The internal execution mode of the Orders to be placed. This affects how the order is handled
                         in the internal market, and can be set to any value specified in COMMON.InternalExecutionMode.
                         (Note: COMMON.InternalExecutionMode.skip is not intended for production code,
                         as it an lead to cross trades.)
        :type execmode: int
        :param max_own_depth_order_placement_abs_euro: 0 .. unlimited.
                                                       orderbook placement beyond this depth will only be
                                                       placed once but not updates. None by default, skips this setting
                                                       order deep in the orderbook will not be updated further if
                                                       placed, except if their order quantity changes or if they are
                                                       cancelled
        :type max_own_depth_order_placement_abs_euro: float
        :param max_own_depth_order_placement_rel_euro: 0 .. 1
                                                            orderbook placement beyond this depth will only be
                                                            placed once but not updates. Depth is price relative
                                                            to front. None by default, skips this setting
        :type max_own_depth_order_placement_rel_euro: float
        :return: A list of SlotResponse objects, with the same length as slots
        :rtype: list[SlotResponse]
        """  # noqa: E501

        response_list = []
        if not self.autotrader.is_exchange_initialized(self.exchange):
            return [SlotResponse(succeeded=False,
                                 action=COMMON.SlotResponseAction.ignore,
                                 reason=COMMON.SlotResponseReason.exchange_not_initialized)]
        assert isinstance(delivery_area_id, six.string_types), \
            "delivery_area_id must be 'str' or 'unicode', but was {}".format(type(delivery_area_id))
        if product.state(delivery_area_id) != COMMON.DeliveryAreaState.active:
            return [SlotResponse(succeeded=False,
                                 action=COMMON.SlotResponseAction.ignore,
                                 reason=COMMON.SlotResponseReason.inactive_area)]

        slot_log = []
        if stats is None:
            stats = []

        strategy_orders = product.orders.get(delivery_area_id, COMMON.OrderFilter.own, portfolio_key=self.strategy_id)
        orders_by_name = collections.defaultdict(list)  # type: dict[str, list]

        for curr_order in strategy_orders:
            curr_order_name = curr_order.tags.get("strategy_slot", "")
            orders_by_name[curr_order_name].append(curr_order)

        # The orders from previous calls to place_slots (in the strategy callback)
        # A dictionary mapping the slot_name for this strategy to a list of
        # either OwnOrder objects or Slots; Both have a .quantity and .price and .direction attribute
        cached_orders_by_name = collections.defaultdict(list)
        for exchange in self.autotrader.all_active_exchanges:
            cached_order_dict = exchange.modify_orders.cache()
            for key in [COMMON.ResolverState.modify_orders,
                        COMMON.ResolverState.entry_orders,
                        COMMON.ResolverState.delete_orders]:
                for curr_order in cached_order_dict[key]:
                    if (curr_order.product == product
                            and curr_order.portfolio_key == self.strategy_id
                            and curr_order.delivery_area_id == delivery_area_id):
                        cached_orders_by_name[curr_order.tags.get("strategy_slot", "")].append(curr_order)

        indicators = product.orders.indicators(self.delivery_area_id)
        buy_reference = None
        sell_reference = None
        last_buy_price = None
        last_sell_price = None
        if (
                max_own_depth_order_placement_abs_euro is not None
                and max_own_depth_order_placement_rel_euro is not None
                and indicators
        ):
            buy_reference, sell_reference, last_buy_price, last_sell_price = self.get_depth_limit_reference_prices(
                max_own_depth_order_placement_abs_euro, max_own_depth_order_placement_rel_euro, indicators
            )

        for slot in slots:
            current_slot_name = slot.slot_type

            # copy stats valid for this slot only, to avoid adding stats to other PositionSlots
            slot_stats = copy.deepcopy(stats)

            # add slot information to stats field
            if slot.info:
                slot_stats.append(slot.info)

            if current_slot_name in cached_orders_by_name:
                offending_order = cached_orders_by_name[current_slot_name][0]
                self.error_log("Trying to place multiple slots with the same name '{slotname}' for area {area}; "
                               "Order {direction} {quantity}@{price} ignored, "
                               "because there is already {other_direction} {other_quantity}@{other_price}"
                               .format(slotname=current_slot_name, area=delivery_area_id,
                                       direction=slot.direction, quantity=slot.quantity, price=slot.price,
                                       other_direction=offending_order.direction,
                                       other_quantity=offending_order.quantity, other_price=offending_order.price),
                               product)

                response_list.append(
                    SlotResponse(succeeded=False,
                                 action=COMMON.SlotResponseAction.ignore,
                                 reason=COMMON.SlotResponseReason.duplicate_name)
                )
                continue

            # Add the slot to the cached_orders_by_name,
            # to prevent placing 2 orders with the same slotname in a single call to place_slots.
            cached_orders_by_name[current_slot_name].append(slot)

            # reduce placement frequency
            # condition, that strategy wants to move order from in-spread between front prices to outside
            # we will allow this once
            curr_order = dict(orders_by_name).get(slot.slot_type, [None])[0]

            # if we have a slot that has existing orders we will need to appropriately handle those
            if current_slot_name in orders_by_name:
                current_slot_orders = orders_by_name[current_slot_name]
                if len(current_slot_orders) == 1:
                    # if we know that this is not a duplicate, we check whether this update is within reference
                    if not self.is_update_within_reference(slot, buy_reference, sell_reference, curr_order):
                        msg = self.create_no_update_within_reference_msg(timestamp,
                                                                         max_own_depth_order_placement_abs_euro,
                                                                         max_own_depth_order_placement_rel_euro,
                                                                         last_buy_price, last_sell_price,
                                                                         buy_reference, sell_reference,
                                                                         slot, curr_order)
                        response = SlotResponse(succeeded=True, action=COMMON.SlotResponseAction.ignore,
                                                reason=(COMMON.SlotResponseReason.placement_too_deep_on_own_side + msg))
                        log_dict = slot.log_dict()
                    else:
                        # if there are not reference issues, then we go through the placement for existing order
                        log_dict, response = self._place_slot_for_existing_order(
                            current_slot_orders, slot, slot_stats, product, timestamp, limit_maximum_purchase_price,
                            limit_minimum_sales_price, execmode
                        )
                else:
                    log_dict, response = self._invalid_multiple_slots_placements(current_slot_orders, slot, product,
                                                                                 execmode)
                response_list.append(response)
                if log_dict is not None:
                    slot_log.append(log_dict)

            else:
                if slot.quantity is None or slot.quantity < COMMON.MIN_ORDER_QTY:
                    log_dict = slot.log_dict()
                    response = SlotResponse(succeeded=True,
                                            action=COMMON.SlotResponseAction.no_order,
                                            reason=COMMON.SlotResponseReason.ok)
                else:
                    log_dict, response = self.place_order(slot, product, slot_stats, limit_maximum_purchase_price,
                                                          limit_minimum_sales_price, execmode,
                                                          delivery_area_id=delivery_area_id)
                slot_log.append(log_dict)
                response_list.append(response)

        # Log all slots the strategy tries to place,
        # so we can do debugging if the strategy implementation forgets to log what it wants to place.
        # this logs will also show if orders cannot be placed due to limit violation
        self.debug_log("placing slot on %s: %s" %
                       (delivery_area_id,
                        ", ".join("%s [r=%s]" % (slot.short(True, True), response)
                                  for slot, response in zip(slots, response_list))),
                       product)
        log_data["slots"] = slot_log
        return response_list

    def _invalid_multiple_slots_placements(self, current_slot_orders, slot, product, execmode):
        log.warning("Found more then one order for slot: %s", slot.slot_type)
        log_dict = slot.log_dict()
        log_dict["quantity"] = 0.
        removed_internal_ids = []
        for curr_double_order in current_slot_orders:
            # Remove all orders that have an order_id (we cannot remove unconfirmed entry orders)
            if getattr(curr_double_order, "order_id", None) is not None:
                self.warn_log("Because of double orders for slot: {}, order with id: {} was removed".format(
                    slot.slot_type, curr_double_order.order_id
                ), product)
                modified_order = curr_double_order.modify(quantity=0., price=curr_double_order.price)
                removed_internal_ids.append(modified_order.internal_id)
                self.autotrader.modify_orders([modified_order], execmode)
        return log_dict, SlotResponse(succeeded=False,
                                      action=COMMON.SlotResponseAction.delete,
                                      reason=COMMON.SlotResponseReason.duplicate_orders,
                                      internal_id=",".join(removed_internal_ids))

    def _place_slot_for_existing_order(self, current_slot_orders, slot, stats, product, timestamp,
                                       limit_maximum_purchase_price, limit_minimum_sales_price, execmode):
        """
        Modify existing orders for this slotname

        If there is already an order with the given slotname for this product & area in the own orderbook,
        we modify it.

        :param current_slot_orders: A list of existing orders to modify.
                                    Usually, this list should have a length of 1
                                    Bugs of autoTRADER or the exchange could cause this to have length 2 or more,
                                    in which case we recover from this bad condition by deleting all of them
                                    from the exchange.
        :type current_slot_orders: list
        :param slot: The slot to place
        :type slot: PositionSlot
        :param stats: Some debugging info to be attached to the slot
        :type stats: list(string)
        :param product: The product to place for
        :type product: APITR.Product
        :param timestamp: unused timestamp
        :type timestamp: float
        :type limit_maximum_purchase_price: float or None
        :type limit_minimum_sales_price: float or None
        :param execmode: The internal execution mode of the Orders to be placed. This affects how the order is handled
                         in the internal market, and can be set to any value specified in COMMON.InternalExecutionMode.
                         (Note: COMMON.InternalExecutionMode.skip is not intended for production code,
                         as it can lead to cross trades.)
        :type execmode: int
        :return: Some debug info
        """

        # we only have one order for this slot, so we proceed as normal
        order = current_slot_orders[0]
        order.tags["stats"] = " ".join(stats)
        if getattr(order, "order_id", None) is None:
            # If orders do not have an order_id, it may have been sent,
            # but no answer may have been received which would have assigned an order id
            self.debug_log("'unconfirmed order' blocks order execution slot_type: {}, order info: {}, {}, {}".format(
                slot.slot_type, order.internal_id, order.quantity, order.price), product)
            response = SlotResponse(succeeded=False,
                                    action=COMMON.SlotResponseAction.ignore,
                                    reason=COMMON.SlotResponseReason.unconfirmed_order)
            return None, response
        log_dict, response = self.modify_existing_order(order, slot, product, limit_maximum_purchase_price,
                                                        limit_minimum_sales_price, execmode)
        return log_dict, response

    @staticmethod
    def cleanup_tolerance(tolerance_lo, tolerance_hi, value):
        range_hi = tolerance_hi
        range_lo = tolerance_lo
        if tolerance_lo > tolerance_hi:
            range_lo = tolerance_hi
            range_hi = tolerance_lo
        range_lo = min(value, range_lo)
        range_hi = max(value, range_hi)
        return range_lo, range_hi

    def modify_existing_order(
            self,
            order,  # type: APITR.OwnOrder
            slot,  # type: PositionSlot
            product,  # type: APITR.Product
            limit_maximum_purchase_price=None,  # type: typing.Optional[float]
            limit_minimum_sales_price=None,  # type:  typing.Optional[float]
            execmode=COMMON.InternalExecutionMode.default,  # type: int
    ):  # type: (...) -> tuple[dict,SlotResponse]

        log_dict = slot.log_dict()

        # Validate Slot: if it is not valid, the order is removed by setting
        # its quantity to 0
        valid_slot = slot.validate(limit_minimum_sales_price, limit_maximum_purchase_price, self.exchange,
                                   order=order, product=product,
                                   delivery_area_id=order.delivery_area_id)
        # If the slot is invalid or the directions of the order and the slot differ, the strategy removes the order
        if not valid_slot or slot.direction != order.direction:
            if not valid_slot:
                reason = slot.validation_result
            else:
                reason = COMMON.SlotResponseReason.direction_changed
            response = SlotResponse(succeeded=(slot.quantity == 0),
                                    action=COMMON.SlotResponseAction.delete,
                                    reason=reason,
                                    internal_id=order.internal_id)
            log_dict["quantity"] = 0.
            self.autotrader.modify_orders([order.modify(quantity=0., price=order.price)], execmode)
            return log_dict, response

        if order.state == COMMON.OrderState.hibe and not order.reactivate:
            # If the order is hibernated, then we assume that it was hibernated for a good reason,
            # so we do not try to firm it. Updating price or quantity of a hibernated order would cause load on the
            # system without any clear benefit, so we don't do it.
            # In such situations, a manual TRADER should delete (not firm) the hibernated order to allow the strategy
            # to re-place the order.
            response = SlotResponse(succeeded=False,
                                    action=COMMON.SlotResponseAction.ignore,
                                    reason=COMMON.SlotResponseReason.hibernated,
                                    internal_id=order.internal_id)
            return log_dict, response

        adapt_price = True

        if slot.price_range_lo is not None and slot.price_range_hi is not None:
            # make sure that slot.price is always between the tolerance boundaries by moving the boundaries
            range_lo, range_hi = self.cleanup_tolerance(slot.price_range_lo, slot.price_range_hi, slot.price)

            third_tick = slot.tick_size * 0.333

            if range_lo - third_tick <= order.price <= range_hi + third_tick:
                adapt_price = False
        else:
            # order book empty, remove the order
            adapt_price = False

        # make sure that slot.quantity is always between the tolerance boundaries by moving the boundaries
        range_lo, range_hi = self.cleanup_tolerance(slot.quantity_range_lo, slot.quantity_range_hi, slot.quantity)
        adapt_quantity = not (range_lo - 0.004 <= order.quantity <= range_hi + 0.004)

        # If nothing changes, we do nothing
        reason = SlotResponse(succeeded=True,
                              action=COMMON.SlotResponseAction.ignore,
                              reason=COMMON.SlotResponseReason.unchanged,
                              internal_id=order.internal_id)
        if adapt_quantity or adapt_price:
            log_dict["ORDER"] = "MODIFY"
            modified_order = order.modify(quantity=slot.quantity, price=slot.price,
                                          trading_account=slot.trading_account,
                                          internal_market_price=slot.internal_market_price)
            if modified_order:
                found_limit_violations = self.autotrader.modify_orders([modified_order], execmode)
                if found_limit_violations:
                    reason.action = COMMON.SlotResponseAction.delete
                    reason.reason = ", ".join(found_limit_violations)
                    reason.ok = False
                else:
                    reason.action = COMMON.SlotResponseAction.modify
                    reason.reason = COMMON.SlotResponseReason.ok
        return log_dict, reason

    def place_order(
            self,  # type: Strategy
            slot,  # type: PositionSlot
            product,  # type: APITR.Product
            stats,  # type: list[unicode]
            limit_maximum_purchase_price=None,  # type: typing.Optional[float]
            limit_minimum_sales_price=None,  # type: typing.Optional[float]
            execmode=COMMON.InternalExecutionMode.default,  # type: int
            delivery_area_id=None,  # type: typing.Optional[unicode]
    ):  # type: (...) -> tuple[dict, SlotResponse]
        log_dict = slot.log_dict()

        # Validate Slot: if it is not valid, do nothing
        valid_slot = slot.validate(limit_minimum_sales_price, limit_maximum_purchase_price, self.exchange,
                                   product=product, delivery_area_id=delivery_area_id)
        if not valid_slot:
            return log_dict, SlotResponse(succeeded=False, action=COMMON.SlotResponseAction.ignore,
                                          reason=slot.validation_result)

        log_dict["ORDER"] = "PLACE"
        if slot.execution_restriction in [COMMON.ExecutionRestriction.fok,
                                          COMMON.ExecutionRestriction.ioc]:
            validity_restriction = COMMON.ValidityRestriction.non
        else:
            validity_restriction = COMMON.ValidityRestriction.gfs
        new_order = APITR.OwnOrder(
            portfolio_key=self.strategy_id,
            execution_restriction=slot.execution_restriction,
            validity_restriction=validity_restriction,
            validity_date=None,
            initial_order_id=None,
            direction=slot.direction,
            product=product,
            delivery_area_id=delivery_area_id if delivery_area_id is not None else self.delivery_area_id,
            quantity=slot.quantity,
            price=slot.price,
            exchange=self.exchange_1,
            order_type=slot.order_type,
            visible_quantity=slot.clip_quantity,
            clip_quantity=slot.clip_quantity,
            internal_market_price=slot.internal_market_price,
            tags={
                "strategy_slot": slot.slot_type,
                "stats": " ".join(stats)
            },
            broker_id=slot.broker_id,
            derivative_indicator=slot.derivative_indicator,
            liquidity_provision=slot.liquidity_provision,
            decision_maker=slot.decision_maker,
            execution_maker=slot.execution_maker,
            dea=slot.dea,
            dea_client_id=slot.dea_client_id,
            trading_capacity=slot.trading_capacity,
            trading_account=slot.trading_account,
            terms=slot.terms,
        )

        found_limit_violations = self.autotrader.modify_orders([new_order], execmode)
        if found_limit_violations:
            return log_dict, SlotResponse(succeeded=False,
                                          action=COMMON.SlotResponseAction.ignore,
                                          reason=", ".join(found_limit_violations))

        return log_dict, SlotResponse(succeeded=True,
                                      action=COMMON.SlotResponseAction.create,
                                      reason=COMMON.SlotResponseReason.ok,
                                      internal_id=new_order.internal_id)

    def _receive_new_limits(self, limit_dictionary, overwrite_limits=False):
        """
        Called when the strategy received new limits from the REST-API.

        WARNING: This must not be used by strategy code!

        :param limit_dictionary: The update to the limits
        :type limit_dictionary: dict
        :param overwrite_limits: flag telling if limits need to be overwritten
        :type overwrite_limits: bool
        :returns: dict with `update_timestamp`
        :rtype: dict[str, float]
        """
        update_timestamp = time.time()
        updating_user = limit_dictionary["user_login"]
        per_sequence_limits = limit_dictionary.get("limits_per_sequence", {})
        per_product_id_limits = limit_dictionary.get("limits_per_sequence_item", {})
        limit_logger.compliance_log(LOGTEMP.AutoTraderLimiter.limits_received,
                                    login_name=updating_user,
                                    strategy_id=self.strategy_id,
                                    limits_per_sequence_id=per_sequence_limits,
                                    limits_per_sequence_item_id=per_product_id_limits,
                                    update_timestamp=update_timestamp,
                                    overwrite_limits=overwrite_limits,
                                    )
        if overwrite_limits:
            self._per_product_limits.reset_limits()

        for limit_name, limit_dict in per_sequence_limits.items():
            for sequence_id, limit_value in limit_dict.items():
                self._per_product_limits._set_for_sequence(limit_name, sequence_id, limit_value,
                                                           updating_user, update_timestamp)
        for limit_name, limit_dict in per_product_id_limits.items():
            for product_id, limit_value in limit_dict.items():
                self._per_product_limits._set_for_product(limit_name, product_id, limit_value,
                                                          updating_user, update_timestamp)

        if self.exchange.internal_id == COMMON.Exchange.trayport and self.exchange.init_files_ready():
            self._per_product_limits._expire_old_limits(self.exchange)

        self._per_product_limits.update_db(update_timestamp)
        return {"update_timestamp": update_timestamp}

    def on_order_book_update(self, orders, timestamp):
        return self.custom_on_order_book_update(orders, timestamp)

    def on_trade_update(self, trades, timestamp):
        return self.custom_on_trade_update(trades, timestamp)

    def on_public_trade_update(self, trades, timestamp):
        return self.custom_on_public_trade_update(trades, timestamp)

    def on_products_queue(self, products, timestamp):
        return self.custom_on_products_queue(products, timestamp)

    def on_products_update(self, products, timestamp):
        return self.custom_on_products_update(products, timestamp)

    def on_timer(self, timestamp):
        return self.custom_on_timer(timestamp)

    def on_error(self, errors, timestamp):
        # type: (dict[str, any], float) -> None
        return self.custom_on_error(errors, timestamp)

    def on_internal_order_reject(self, rejected_order_infos, timestamp):
        """
        Only used by the synthetic order strategy base to handle the synthetic order status.

        Should not be overridden by custom strategies.
        :param rejected_order_infos: A list of dicts containing the order internal id
                                     and the reason why the modification was rejected
        :type rejected_order_infos: list[dict]
        :param timestamp: The parent processe's timestamp at the time it rejected the modification.
                          Note that this is not time.time, but rather the timestamp of the message
                          which caused the rejection.
        :type timestamp: int or float
        """
        pass

    def custom_on_order_book_update(self, orders, timestamp):
        pass

    def custom_on_trade_update(self, trades, timestamp):
        pass

    def custom_on_public_trade_update(self, trades, timestamp):
        pass

    def custom_on_products_update(self, products, timestamp):
        pass

    def custom_on_products_queue(self, products, timestamp):
        pass

    def custom_on_timer(self, timestamp):
        pass

    def remove_orders_of_product(self):
        """
        Remove all strategy orders

        Note: This function is used for autoTRADER halts and by-passes some validations.
              Strategies should preferably place slots with quantity 0 instead of using this function
        """

        # We check if exchange is defined (i.e. it is not None), otherwise a warning is displayed in the log
        if not self.exchange:
            self.warn_log("Not active: strategy exchange is None")
        else:
            caught_exc = False
            # select products with delivery_start greater or equal to the current_timestamp
            products = self.exchange.products.get_by_timerange(
                self.autotrader.current_timestamp)
            for product in products:
                # modify all orders to quantity 0.
                try:
                    self.remove_my_orders_from_product(product)
                except Exception:
                    caught_exc = True
                    self.exception_log("Exception while removing orders", product)
            if caught_exc:
                self.warn_log("Not active, but exception while removing orders occur")
            else:
                self.debug_log("Not active, all orders removed")

    def custom_on_error(self, errors, timestamp):
        pass

    def api_export_timeseries(self, timeseries_packets):
        """Save timeseries in Mongo as "TimeSeries" object

        :param timeseries_packets: timeseries packet to be written to mongo
                { timeseries_name -> (caption, unit, unit_caption, resolution (seconds), { ts_from -> value } }
        :type timeseries_packets: dict[str, (str, str, str, int, dict[int, float])]
        :rtype: None
        """
        if PERSIST.MongoDBConnector().is_initialized:
            PERSIST.MongoDBConnector().update_db_timeseries(
                "trading_portfolio", self.strategy_id, self.caption, timeseries_packets,
                self.autotrader.current_timestamp)

    def api_export_log_error(self, text, data_object):
        if PERSIST.MongoDBConnector().is_initialized:
            json_dump = json.dumps((text, data_object))
            if self.last_db_global_log_error != json_dump:
                PERSIST.MongoDBConnector().update_db_global_log(
                    True,
                    "trading_portfolio",
                    self.strategy_id,
                    self.caption,
                    text,
                    data_object,
                    self.autotrader.current_timestamp
                )
                self.last_db_global_log_error = json_dump

    def api_export_log_info(self, text, data_object):
        if PERSIST.MongoDBConnector().is_initialized:
            json_dump = json.dumps((text, data_object))
            if self.last_db_global_log_info != json_dump:
                PERSIST.MongoDBConnector().update_db_global_log(
                    False,
                    "trading_portfolio",
                    self.strategy_id,
                    self.caption,
                    text,
                    data_object,
                    self.autotrader.current_timestamp
                )
                self.last_db_global_log_info = json_dump

    def api_export_log_state(self, text, data_object):
        if PERSIST.MongoDBConnector().is_initialized:
            if self.last_db_global_log_state != json.dumps((text, data_object)):
                PERSIST.MongoDBConnector().update_db_global_log_state(
                    "trading_portfolio",
                    self.strategy_id,
                    self.caption,
                    text,
                    data_object,
                    self.autotrader.current_timestamp
                )
                self.last_db_global_log_state = json.dumps((text, data_object))

    def set_compliance_logger(self, logger):
        assert isinstance(logger, FLOG.Logger)
        self._compliance_logger = logger

    def compliance_log(self, log_entry, **kwargs):
        """
        Major compliance logging function for Strategies.

        The following fields will be filled automatically:
        - strategy_id
        - strategy_caption
        - strategy_zip_version
        - strategy_type

        One should not use these keys as keyword args in kwargs.

        :param log_entry: compliance log template from autotrader_lib.compliance_log_templates
        :type log_entry: tuple
        """
        params = dict(strategy_id=self.strategy_id,
                      strategy_caption=self.caption,
                      strategy_zip_version=self.strategy_package_name,
                      strategy_type=self.strategy_type)
        if kwargs:
            params.update(kwargs)
        self._compliance_logger.compliance_log(log_entry=log_entry, **params)

    def update_active_flag(self, username):
        """
        Updates "active" state of a Strategy.
        If halt_reason is not None, it's a strategy specific halt and we don't want
        to set the strategy to active according to the halted state.
        Strategy must be set to active=False if it is halted. Then the
        rest of autotrader will stop the strategy.
        :param username: username who triggered changing the state
        :type username: str
        """
        new_state = self._pt_active and not self.halted and not self.autotrader.halted and not self.exchange.halted
        if self.active != new_state:
            self.compliance_log(log_entry=LOGTEMP.StrategyBasicLogs.strategy_activated if new_state else
                                LOGTEMP.StrategyBasicLogs.strategy_deactivated, username=username)
        self.active = new_state


class GasStrategy(Strategy):

    def __init__(self, *args, **kwargs):
        super(GasStrategy, self).__init__(*args, **kwargs)
        self.broker_id = None  # broker ID has to be defined

    def area_qty_to_mwh(self, quantity_raw, area, duration, treat_area_mwh_as_mw=True):
        """Convert the quantity in trayport area specific unit to mwh

        :type quantity_raw: float
        :type area: str
        :type duration: int
        :type treat_area_mwh_as_mw: bool
        :param treat_area_mwh_as_mw: consider the unit "MWh" of a trayport area as MWH/H = MW
        :rtype: float
        """
        if quantity_raw is None:
            return None
        area_property = self.autotrader.trayport.trayport_areas[area]
        unit = getattr(area_property, 'unit', "").upper()
        if treat_area_mwh_as_mw and unit == "MWH":
            unit = "MW"
        return UU.convert_units(quantity_raw, unit, COMMON.Units.MWH, duration / COMMON.HOUR)

    def area_qty_to_mw(self, quantity_raw, area, duration, treat_area_mwh_as_mw=True):
        """Convert the quantity in trayport area specific unit to mw

        :type quantity_raw: float
        :type area: str
        :type duration: int
        :type treat_area_mwh_as_mw: bool
        :param treat_area_mwh_as_mw: consider the unit "MWh" of a trayport area as MWH/H = MW
        :rtype: float
        """
        if quantity_raw is None:
            return None
        area_property = self.autotrader.trayport.trayport_areas[area]
        unit = getattr(area_property, 'unit', "").upper()
        if treat_area_mwh_as_mw and unit == "MWH":
            unit = "MW"
        return UU.convert_units(quantity_raw, unit, COMMON.Units.MW, duration / COMMON.HOUR)

    def mw_to_area_qty(self, quantity_mw, area, duration, treat_area_mwh_as_mw=True):
        """Convert mw into the quantity in trayport area specific unit

        :type quantity_mw: float
        :type area: str
        :param duration: duration in seconds
        :type duration: int
        :type treat_area_mwh_as_mw: bool
        :param treat_area_mwh_as_mw: consider the unit "MWh" of a trayport area as MWH/H = MW
        :rtype: float
        """
        if quantity_mw is None:
            return None
        area_property = self.autotrader.trayport.trayport_areas[area]
        unit = getattr(area_property, 'unit', "").upper()
        if treat_area_mwh_as_mw and unit == "MWH":
            unit = "MW"
        return UU.convert_units(quantity_mw, COMMON.Units.MW, unit, duration / COMMON.HOUR)

    def mwh_to_area_qty(self, quantity_mwh, area, duration, treat_area_mwh_as_mw=True):
        """Convert mwh into the quantity in trayport area specific unit

        :type quantity_mwh: float
        :type area: str
        :type duration: int
        :type treat_area_mwh_as_mw: bool
        :param treat_area_mwh_as_mw: consider the unit "MWh" of a trayport area as MWH/H = MW
        :rtype: float
        """
        if quantity_mwh is None:
            return None
        area_property = self.autotrader.trayport.trayport_areas[area]
        unit = getattr(area_property, 'unit', "").upper()
        if treat_area_mwh_as_mw and unit == "MWH":
            unit = "MW"
        return UU.convert_units(quantity_mwh, COMMON.Units.MWH, unit, duration / COMMON.HOUR)

    def get_trayport_properties(self, product_id, instrument_id=None, broker_id=None):
        """find the trayport properties for the specified product

        :param product_id: ID of specified product
        :type product_id: str
        :param instrument_id: ID of delivery area for the product
        :type instrument_id: str
        :param broker_id: ID of broker for the product
        :type broker_id: str
        :rtype: Property
        """
        if instrument_id is None:
            instrument_id = self.delivery_area_id
        if broker_id is None:
            broker_id = self.broker_id
        return self.autotrader.trayport.get_properties(broker_id=broker_id,
                                                       delivery_area_id=instrument_id,
                                                       product_id=product_id)

    @staticmethod
    def filter_products(products_list, allowed_product_types=("WD", "DA", "W/END")):
        """

        :param allowed_product_types: tuple of allowed product types for this strategy
        :type allowed_product_types: tuple[str]
        :type products_list: iterable[autotrader_core.exchange_trading.Product]
        :rtype: list[autotrader_core.exchange_trading.Product]
        """
        # only WD, DA, W/End product
        return [product for product in products_list if product.product_type in allowed_product_types]

    @staticmethod
    def is_cegh_area(curr_area):
        """
        DEPRECATED: Since October 2022, CEGH within day is no longer traded on a different instrument id. Thus this
        function is no longer needed and will be removed in the future.

        Helper function to recognize when we are in a CEGH delivery area
        """
        return curr_area == COMMON.Area.cegh

    def is_mwh_per_day_area(self, curr_area):
        """Helper function to recognize when we are in a PEG delivery area"""
        area_property = self.autotrader.trayport.trayport_areas[curr_area]
        return area_property.unit.upper() == "MEGAWATT HOURS PER DAY"

    @classmethod
    def areas_setup(cls, area):
        """
        DEPRECATED!

        When CEGH still had a separate instrument id for WD (until Oct 2022) this provided special logic for cegh """
        return [area]


class PositionBlockBuildingMode(object):
    average = "average"
    minimum = "minimum"


class Position(object):
    """Handles Position in 15 minutes timeslices"""

    def __init__(self):
        self.positions_long = collections.defaultdict(float)  # unix_timestamp -> quantity
        self.positions_short = collections.defaultdict(float)  # unix_timestamp -> quantity

    @staticmethod
    def block_min(values):
        m = next(values)
        for value in values:
            if m >= 0:
                if value <= 0:
                    return 0.
                m = min(m, value)
            elif m <= 0:
                if value >= 0:
                    return 0.
                m = max(m, value)
        return m

    def rasterized_position_data(self, start, end):
        """get hourly and quarterly aggregated position data

        prepare and quarterly raster first, then hourly

        :param start: int
        :param end: int
        :return: get 2 dicts about the net positions, at beginning of hour and beginning of quarter
        :rtype: dict[int, list[float, float]], dict[int, list[float, float]]
        """
        start = int(start // 3600 * 3600)
        end = int((end // 3600 + 1) * 3600)
        quarter_ranges_dict = dict(
            (r, [round(self.positions_long[r], 1), round(self.positions_short[r], 1)]) for r in range(start, end, 900)
        )
        hourly_ranges_dict = dict((r, [0., 0.]) for r in range(start, end, 3600))
        for hour_start in hourly_ranges_dict:
            # get min
            avg_pos_long = round(min(quarter_ranges_dict[r][0] for r in range(hour_start, hour_start + 3600, 900)), 1)
            avg_pos_short = round(min(quarter_ranges_dict[r][1] for r in range(hour_start, hour_start + 3600, 900)), 1)
            hourly_ranges_dict[hour_start] = [avg_pos_long, avg_pos_short]
            for q_start in range(hour_start, hour_start + 3600, 900):
                try:
                    quarter_ranges_dict[q_start][0] -= avg_pos_long
                    quarter_ranges_dict[q_start][1] -= avg_pos_short
                except KeyError:
                    continue
        return hourly_ranges_dict, quarter_ranges_dict

    def update_from_json(self, long_struct, short_struct):
        """update long/short position based on json timeseries data

        :type long_struct: list[dict[str, int or float]]
        :type short_struct: list[dict[str, int or float]]
        :rtype: NoneType
        """
        for j in long_struct:
            self.positions_long[j["begin"]] = round(j["value"] or 0., 1)
        for j in short_struct:
            self.positions_short[j["begin"]] = round(j["value"] or 0., 1)

    def update_from_tuples(self, long_positions, short_positions):
        """update long/short position based on tuples data

        :type long_positions: list[tuple[int, int or float]]
        :type short_positions: list[tuple[int, int or float]]
        :rtype: NoneType
        """
        for ts, position in long_positions:
            self.positions_long[ts] = position
        for ts, position in short_positions:
            self.positions_short[ts] = position


class PositionSlot(object):
    """Defines an order position target, defined by a strategy.

    Position Slot Instances are passed on from a custom strategy from the
    get_slots function. A Slot defines a specific order wish that the
    strategy wants to communicate. It does not define a direct order placement.
    Slots are directly created with the constructor.
    """
    back = "B"
    middle = "M"
    front = "F"
    exposed = "E"
    out = "O"
    snipe = "S"
    dump = "D"

    def __init__(self, slot_type, direction, quantity=None, price=None,
                 price_range_lo=None, price_range_hi=None,
                 execution_restriction=COMMON.ExecutionRestriction.non,
                 order_type=COMMON.OrderType.order, clip_quantity=None,
                 price_delta=0.0, tick_size=0.01, quantity_range_lo=None,
                 quantity_range_hi=None, broker_id=None, derivative_indicator=None,
                 liquidity_provision=None, decision_maker=None, execution_maker=None,
                 dea=None, dea_client_id=None, trading_capacity=None,
                 trading_account="", terms=None, info=""):
        """Creates a slot.

        :param slot_type: Type of the slot, any string that strictly defines the purpose of the order
        :param direction: Buy (bid) or sell (ask) order, member of :class:`COMMON.Direction`
        :param quantity: quantity of order wish in MW
        :param price: price of order wish in Euro per MWh
        :param price_range_lo: optional. Defines the lower placement tolerance in Euro per MWh
        :param price_range_hi: optional. Defines the upper placement tolerance in Euro per MWh
        :type slot_type: str
        :type direction: str, :class:`COMMON.Direction`
        :type quantity: float
        :type price: float
        :type price_range_lo: float
        :type price_range_hi: float
        :param quantity_range_lo: lower end of placement quantity, at which virtual iceberg refills quantity_range_hi
        :type quantity_range_lo: float
        :param quantity_range_hi: upper limit of placed quantity, to which placement of virtual iceberg will refill
        :type quantity_range_hi: float
        :param broker_id: string of the broker id. Some examples for reuse are in :class:`COMMON.Broker`
        :type broker_id: str
        :param execution_restriction: execution restriction, for example "FOK", "IOC"
        :type execution_restriction: :class:`COMMON.ExecutionRestriction`
        :param order_type: Type of the order, for example regular ("O"), iceberg ("I")
        :type order_type: :class:`COMMON.OrderType`
        :param clip_quantity: Clip quantity of an iceberg orders (applies only to order type "I")
        :type clip_quantity: float
        :param price_delta: price delta determines absolute deviation to
                                  the price of the slot setting up its internal market price,
                                  such that the internal market trading is more favorable
                                  for the resultant order.
        :type price_delta: float
        :param tick_size: minimal price step for an order
        :type tick_size: float
        :param derivative_indicator: Where market regulations require this, this flag can be set to a boolean.
                                     It indicates whether the order objectively reduces risk according to
                                     some MIFID II criteria.
                                     It is currently only forwarded if the exchange is Trayport.
                                     WARNING: Following the python convention, the string "false" is evaluated as True
        :type derivative_indicator: None or bool
        :param liquidity_provision: MIFID field, can be true or false - will be true if market making
        :type liquidity_provision: None or bool
        :param decision_maker: MIFID field, person providing the logic for the algo decisions
        :type decision_maker: None or str
        :param execution_maker: MIFID field, algo ID which is executing the trades
                                Will be automatically set to the Spread Maker,
                                Market Making Live when using the Traport Algo tools
        :type execution_maker: None or str
        :param dea: MIFID field, can be true or false - will be true if market making
        :type dea: None or bool
        :param dea_client_id: DEA Client Id
        :type dea_client_id: None or str
        :param trading_capacity: MIFID field, one of (TradingCapacityType: "DEAL", "MTCH", "AOTC")
        :type trading_capacity: None or str
        :param trading_account: The trading account to send to the exchange.
                                Use an empty string if no trading account should be used
        :type trading_account: str
        :param terms: list of term objects to send to Trayport exchange
        :type terms: None or list
        :param info: additional information to be saved with the slot.
                     Will be added to stats list. stats list in joined by " " character.
                     This info will be seen in the comment or text field of the order and the trade, if executed

                     .. note::

                        The characters "**:**" and "**|**" should not be used in the info field.
                        "**:**" will be replaced with "**?**"

                     .. warning::

                        The parameter ``info`` is not audit safe on Trayport.
                        As on Trayport, the text field of trades can change afterwards if a partially traded
                        order's text field is modified after the trade was made.

        :type info: str

        .. code-block:: python

            # Define a strategy's wish to place a sell named "ord_sell" with a quantity
            # calculated as the remaining open position and a fixed price at the
            # 0 MW price of the sell order book
            PositionSlot("ord_sell", COMMON.Direction.sell,
                max(position_long-traded_sell, 0.),
                indicators[1][0])
        """
        assert slot_type is not None
        self.slot_type = slot_type
        self.direction = direction
        self.price = None
        self.quantity = None
        self.price_range_lo = None
        self.price_range_hi = None
        self.info = info
        self.tick_size = tick_size
        if not PY2LIB.is_none(quantity):
            self.set_quantity(quantity, quantity_range_lo, quantity_range_hi)
        if not PY2LIB.is_none(price):
            self.set_prices(price, price_range_lo, price_range_hi)
        self.execution_restriction = execution_restriction
        self.clip_quantity = clip_quantity
        self.order_type = order_type
        self.broker_id = broker_id
        self._price_delta = price_delta
        self._internal_market_price = None

        # MiFID fields:
        self.derivative_indicator = derivative_indicator
        self.liquidity_provision = liquidity_provision
        self.decision_maker = decision_maker
        self.execution_maker = execution_maker
        self.dea = dea
        self.dea_client_id = dea_client_id
        self.trading_capacity = trading_capacity

        # Other fields needed for some venues
        self.trading_account = trading_account

        # Terms:
        self.terms = terms

        # The following will be set in the .validate function
        self.validation_result = ""

    def short(self, with_slot_type=True, with_info=False):
        """Give short string representation of the slot"""
        if self.quantity is not None:
            self.quantity += 0.0
        if self.price is not None:
            self.price += 0.0
        return ((self.direction[0].upper() if self.direction else "NODIR") + "_"
                + ("%.1f" % self.quantity if self.quantity is not None else "None") + "@"
                + ("%.2f" % self.price if self.price is not None else "None")
                + (" [t=" + self.slot_type + "]" if with_slot_type and self.slot_type is not None else "")
                + (" [i=" + self.info + "]" if with_info and self.info is not None else "")
                )

    def set_prices(self, price, price_range_lo=None, price_range_hi=None):
        if price is None:
            self.quantity = None
            return

        # round according to direction

        def d_round(value):
            # rounding with floating point error fix
            if value in [float("-inf"), float("inf")] or math.isnan(value):
                return float("nan")
            if self.direction == COMMON.Direction.buy:
                return math.ceil((value - 0.0001) / self.tick_size) * self.tick_size
            else:
                return math.floor((value + 0.0001) / self.tick_size) * self.tick_size

        self.price = d_round(price)

        if price_range_lo is None or price_range_hi is None:
            self.price_range_lo = self.price_range_hi = self.price
        elif price_range_lo > price_range_hi:
            self.price_range_lo = d_round(price_range_hi)
            self.price_range_hi = d_round(price_range_lo)
        else:
            self.price_range_lo = d_round(price_range_lo)
            self.price_range_hi = d_round(price_range_hi)

    def set_quantity(self, quantity, quantity_range_lo=None, quantity_range_hi=None):
        self.quantity = round(quantity, 1)
        self.quantity_range_lo = round(quantity if quantity_range_lo is None else quantity_range_lo, 1)
        self.quantity_range_hi = round(quantity if quantity_range_hi is None else quantity_range_hi, 1)

    @property
    def internal_market_price(self):
        # Here we imply a positive price shift for buy orders and
        # negative one for sell orders.
        if self._internal_market_price is None:
            if self.price is None:
                return self._internal_market_price
            sign = 1 if self.direction == COMMON.Direction.buy else -1
            self._internal_market_price = round(self.price + sign * abs(self._price_delta), 2)
        return self._internal_market_price

    def log_dict(self):
        return {"direction": self.direction,
                "price": self.price,
                "quantity": self.quantity,
                "clip_quantity": self.clip_quantity,
                "exec_restriction": self.execution_restriction,
                "order_type": self.order_type,
                "type": self.slot_type}

    def __repr__(self):
        return str(self)

    def __str__(self):
        return ("Slot type: {}; {}; price: {}; price_lo: {}, price_hi: {}, internal_price: {}, "
                "qty: {}; vis_qty: {}; order_type: {}; exec restr: {}, {}").format(
            self.slot_type, self.direction, self.price, self.price_range_lo,
            self.price_range_hi, self.internal_market_price, self.quantity, self.clip_quantity,
            self.order_type, self.execution_restriction, self.info)

    def __eq__(self, other):
        def x(y):
            if y is None:
                return None
            return round(y, 2)

        return (isinstance(other, PositionSlot)
                and self.slot_type == other.slot_type
                and self.direction == other.direction
                and x(self.price) == x(other.price)
                and x(self.price_range_lo) == x(other.price_range_lo)
                and x(self.price_range_hi) == x(other.price_range_hi)
                and x(self.quantity) == x(other.quantity)
                and self.execution_restriction == other.execution_restriction
                and self.broker_id == other.broker_id)

    def validate(self, lim_min_sales_price=None, lim_max_purc_price=None,
                 exchange=None, order=None, product=None, delivery_area_id=None):
        """Validates the created slot for prices, quantities, limits, tick sizes, change of broker

        :param float lim_min_sales_price: minumum sales price
        :param float lim_max_purc_price: maximum purchage price
        :param exchange:
        :type exchange: :class:`autotrader_core.exchanges.Exchange`
        :param order: OwnOrder
        :type order: :class:`APITR.OwnOrder`
        :param product: product
        :type product: `APITR.Product`
        :param delivery_area_id: delivery area of the slot to be placed
        :type delivery_area_id: str
        :return: True if the slot is valid, False otherwise
        :rtype: bool
        """
        # Reset the validation result from previous validations.
        self.validation_result = ""
        checks = [self._validate_price_quantity(lim_min_sales_price, lim_max_purc_price),
                  self._validate_iceberg_slot(),
                  self._validate_block_slot(),
                  self._validate_mifid_fields(),
                  self._validate_terms(),
                  self._validate_execution_restriction(order)]

        if exchange and exchange.internal_id == COMMON.Exchange.trayport:
            product_id = getattr(product, "product_id", None)
            checks.extend([self._validate_for_broker(exchange, order, delivery_area_id),
                           self._validate_trayport_property(exchange, product_id, delivery_area_id),
                           self._validate_intended_tradeorder(product, delivery_area_id)])
        return all(checks)

    def _log_if_nonempty(self, message, *args):
        """
        Write this debugging message, if this slot has non-zero quantity.
        :param message, args: Will be forwarded to Logger.debug
        """
        if self.quantity:
            log.debug(message, *args)

    @staticmethod
    def is_finite(number):
        if number is None or math.isinf(number) or math.isnan(number):
            return False
        return True

    def _validate_price_quantity(self, lim_min_sales_price, lim_max_purc_price):
        """Helper function to validate prices and quantities of the slots

        :param float lim_min_sales_price: minimum sales price
        :param float lim_max_purc_price: maximum purchase price
        :return: True if the slot is valid, False otherwise
        :rtype: bool
        """

        validation = True
        if self.direction is None:
            self._log_if_nonempty("PositionSlot is invalid: direction is None, slot: %s", self)
            self.validation_result = COMMON.SlotResponseReason.missing_direction
            validation = False

        if not self.is_finite(self.quantity):
            log.debug("PositionSlot is invalid: quantity %s is not a finite number, slot: %s",
                      self.quantity, self)
            self.validation_result = COMMON.SlotResponseReason.nonfinite_quantity
            validation = False

        if not self.is_finite(self.price):
            self._log_if_nonempty("PositionSlot is invalid: price %s is not a finite number, slot: %s",
                                  self.price, self)
            self.validation_result = COMMON.SlotResponseReason.nonfinite_price
            validation = False

        # Validate limits only if the validation above is successful
        if not validation:
            return validation

        if self.direction == COMMON.Direction.sell and lim_min_sales_price is not None:
            if lim_min_sales_price > 9999.:
                self._log_if_nonempty("PositionSlot cannot be placed as the minimum sale price"
                                      " limit is larger than 9999.")
                validation = False
                self.validation_result = COMMON.SlotResponseReason.invalid_limit_sale_price
            elif round(lim_min_sales_price - self.price, 8) > 0:  # avoid MACHINE_ERROR at 8th digit to change result
                self._log_if_nonempty("PositionSlot is invalid: slot price is smaller than the"
                                      " minimum sale price limit: %s, slot: %s", lim_min_sales_price, self)
                validation = False
                self.validation_result = COMMON.SlotResponseReason.limit_sale_price

        if self.direction == COMMON.Direction.buy and lim_max_purc_price is not None:
            if lim_max_purc_price < -9999.:
                self._log_if_nonempty(("PositionSlot cannot be placed as the maximum "
                                       "purchase price limit is smaller than -9999."))
                validation = False
                self.validation_result = COMMON.SlotResponseReason.invalid_limit_buy_price
            elif round(lim_max_purc_price - self.price, 8) < 0:
                self._log_if_nonempty(("PositionSlot is invalid: slot price is larger "
                                       "than the maximum purchase price limit: %s, slot: %s"),
                                      lim_max_purc_price, self)
                validation = False
                self.validation_result = COMMON.SlotResponseReason.limit_buy_price

        return validation

    def _validate_iceberg_slot(self):
        """Helper function to validate slots with iceberg order type

        :return: True if the slot is valid, False otherwise
        :rtype: bool
        """

        if self.order_type == COMMON.OrderType.iceberg:
            clip_quantity_min = 5.

            if not self.clip_quantity:
                self.clip_quantity = clip_quantity_min

            if self.quantity < self.clip_quantity:
                log.debug(("PositionSlot is invalid for iceberg order: clip quantity cannot "
                           "be larger than the total quantity, slot: %s"), self)
                self.validation_result = COMMON.SlotResponseReason.iceberg_large_clip
                return False

            if self.clip_quantity < clip_quantity_min or self.clip_quantity > 999.:
                log.debug(("PositionSlot is invalid for iceberg order: "
                           "clip quantity should "
                           "be larger than 5 MW and smaller than 999 MW, slot: %s"),
                          self)
                self.validation_result = COMMON.SlotResponseReason.iceberg_invalid_clip_qty
                return False

        return True

    def _validate_block_slot(self):
        """Helper function to validate slots with block order type

        :return: True if the slot is valid, False otherwise
        :rtype: bool
        """

        if self.order_type == COMMON.OrderType.block and \
                self.execution_restriction in [COMMON.ExecutionRestriction.non, COMMON.ExecutionRestriction.ioc]:
            log.debug("PositionSlot is invalid for block order: execution restriction must be AON or FOK; slot: %s",
                      self)
            self.validation_result = COMMON.SlotResponseReason.invalid_block_exec_restriction
            return False

        return True

    def _validate_mifid_fields(self):
        # to avoid silent errors, such as "false" to be evaluated as True, make sure correct types are inserted
        if self.derivative_indicator is not None and not isinstance(self.derivative_indicator, bool):
            self.validation_result = COMMON.SlotResponseReason.derivative_indicator_not_bool
            return False
        if self.liquidity_provision is not None and not isinstance(self.liquidity_provision, bool):
            self.validation_result = COMMON.SlotResponseReason.liquidity_provision_not_bool
            return False
        if self.decision_maker is not None and not isinstance(self.decision_maker, six.string_types):
            self.validation_result = COMMON.SlotResponseReason.decision_maker_not_string
            return False
        if self.execution_maker is not None and not isinstance(self.execution_maker, six.string_types):
            self.validation_result = COMMON.SlotResponseReason.execution_maker_not_string
            return False
        if self.dea is not None and not isinstance(self.dea, bool):
            self.validation_result = COMMON.SlotResponseReason.dea_not_bool
            return False
        if self.dea_client_id is not None and not isinstance(self.dea_client_id, six.string_types):
            self.validation_result = COMMON.SlotResponseReason.dea_client_id_not_string
            return False
        if (
                self.trading_capacity is not None
                and self.trading_capacity not in COMMON.TradingCapacityType.__slots_container_py2__
        ):
            self.validation_result = COMMON.SlotResponseReason.wrong_trading_capacity
            return False
        return True

    def _validate_terms(self):
        if self.terms is not None and not isinstance(self.terms, list):
            self.validation_result = COMMON.SlotResponseReason.terms_not_list_type
            return False
        return True

    def _validate_intended_tradeorder(self, product, delivery_area_id):  # type: (APITR.Product, str) -> bool
        """Validate that aggressing execution_types that would generate a TradeOrder would match a public order"""
        if self.execution_restriction not in COMMON.ExecutionRestriction.trayport_trade_orders or product is None:
            return True

        min_qty = 0 if self.execution_restriction == COMMON.ExecutionRestriction.ioc else None
        can_trade = product.orders.can_create_trade(self.direction, delivery_area_id, self.price, self.quantity,
                                                    min_qty)

        if not can_trade:
            self.validation_result = COMMON.SlotResponseReason.no_matching_order.format(self.execution_restriction)
            return False

        return True

    def _validate_execution_restriction(self, order):
        """
        Validate the execution restriction of the slot.

        :param order: If given, the existing order for this slot
        :type order: APITR.OwnOrder or None
        :return: True if the slot is valid
        :rtype: bool
        """
        if self.execution_restriction not in COMMON.ExecutionRestriction.available_execution_restrictions:
            self.validation_result = COMMON.SlotResponseReason.wrong_exec_restriction
            return False
        if order and self.execution_restriction != order.execution_restriction:
            self.validation_result = COMMON.SlotResponseReason.exec_restriction_changed
            return False
        return True

    def _validate_for_broker(self, exchange, order, delivery_area_id):
        """Helper function checking the broker_id of the slot

        :param exchange:
        :type exchange: :class:`autotrader_core.exchanges.Exchange`
        :param order: the corresponding own order, which exists on the exchange
        :type order: :class:`APITR.OwnOrder`
        :param delivery_area_id: delivery area of the slot to be placed
        :type delivery_area_id: str
        :return: True if the slot is valid, False otherwise
        :rtype: bool
        """

        if not self.broker_id:
            log.warning("PositionSlot is invalid: slot broker_id for the strategy is not set")
            self.validation_result = COMMON.SlotResponseReason.tp_broker_unset
            return False
        elif not isinstance(self.broker_id, six.string_types):
            log.error("PositionSlot field broker_id must be a string, but was: %s. " %
                      (type(self.broker_id),))
            self.validation_result = COMMON.SlotResponseReason.tp_broker_must_be_string
            return False

        validation = True
        # Validate if strategy changes broker id of an existing order
        if order and self.broker_id != order.broker_id:
            log.warning(("PositionSlot is invalid: slot broker_id (%s) is different from that of "
                         "the corresponding order on the exchange (%s)"),
                        self.broker_id, order.broker_id)
            self.validation_result = COMMON.SlotResponseReason.tp_broker_unchangeable
            validation = False

        # Validate if the broker_id of the slot is allowed for the delivery area
        if delivery_area_id:
            area = exchange.trayport_areas[delivery_area_id]
            if self.broker_id not in area.brokers:
                log.warning("PositionSlot is invalid: slot broker_id %s is not allowed for the delivery area %s",
                            self.broker_id, delivery_area_id)
                self.validation_result = COMMON.SlotResponseReason.tp_invalid_broker_area_combination
                validation = False

        return validation

    @staticmethod
    def get_trayport_tick_sizes(broker_id, exchange, product_id, delivery_area_id):
        """ Helper function to get tick sizes from Trayport properties """
        key = "{}_{}_{}".format(broker_id, delivery_area_id, product_id)

        if key in exchange.trayport_properties:
            properties = exchange.trayport_properties[key]
            min_qty = properties.min_quantity
            price_tick = properties.price_tick
            qty_tick = properties.qty_tick
            return min_qty, price_tick, qty_tick

    def _validate_trayport_property(self, exchange, product_id, delivery_area_id):
        """Helper function checking the slot price and quantity are in accord with the corresponding instrument
        properties

        :param exchange: Trayport exchange object
        :type exchange: :class:`APIEXCH.Exchange`
        :param str product_id: product id
        :param str delivery_area_id: delivery area of the slot to be placed
        :return: True if the slot is valid, False otherwise
        :rtype: book
        """

        if not product_id:
            return True

        validation = True

        tick_sizes = self.get_trayport_tick_sizes(self.broker_id, exchange, product_id, delivery_area_id)
        if tick_sizes:
            min_qty, price_tick, qty_tick = tick_sizes

            if self.price is not None and not is_integer_multiple(self.price, price_tick):
                log.warning("PositionSlot is invalid: slot price (%s) does not match the allowed tick size (%s)",
                            self.price, price_tick)
                self.validation_result = COMMON.SlotResponseReason.tp_price_tick_size_violation

                validation = False
            if self.quantity is not None and not is_integer_multiple(self.quantity, qty_tick):
                log.warning("PositionSlot is invalid: slot quantity (%s) does not match the allowed tick size (%s)",
                            self.quantity, qty_tick)
                self.validation_result = COMMON.SlotResponseReason.tp_quantity_tick_size_violation

                validation = False
            if self.quantity and self.quantity < min_qty:
                log.warning(("PositionSlot is invalid: slot quantity (%s) is less than the allowed "
                             "minimum quantity (%s)"), self.quantity, min_qty)
                validation = False
                self.validation_result = COMMON.SlotResponseReason.tp_min_quantity_violation

        return validation


class ProductsFilterMixin(StrategyBase):
    """Functionality to filter products by timeseries values

    If added to a strategy as parent, this will read the strategy_products_filter timeseries when on_strategy_update
    is called, and will allow to filter the products by :py:meth:`~ProductsFilterMixin.get_allowed_products`

    The Mixin should always be added after the Strategy parent class:

    .. code-block:: python

        class PositionClosingBase(strategy.Strategy, strategy.ProductsFilterMixin)

    """
    _4h_block_areas = (COMMON.Area.uk, COMMON.Area.rte, COMMON.Area.gb2_np, COMMON.Area.rte_np)

    # factor to multiple periotheus/timeseries entries with to turn them into unique integers
    # this is done to avoid bad comparisons dues to floating point errors, e.g. 1 == 1.00000000000001 => False
    _PRODUCT_FILTER_MULTIPLE_FACTOR = 60

    # internal number of the products filter userdefined timeseries
    _PRODUCTS_FILTER_TS = COMMON.StrategyJsonKey.UDFTS.prod_filter

    # the integer form of the product filter.
    # in periotheus timeseries 0.25 is entered for 15min products.
    # After multiplication with the factor, this turns into an integer
    _DEFAULT_FILTER = 0
    _15_MIN_FILTER = 15
    _30_MIN_FILTER = 30
    _1_HOUR_FILTER = 60
    _2_HOUR_FILTER = 120
    _4_HOUR_FILTER = 240

    INPUT_TICK = 0.25
    ALLOWED_VALUES_INPUT = (None, 0., 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.25, 3.5,
                            3.75, 4., 4.25, 4.5, 4.75, 5.0, 5.25, 5.5, 5.75, 6.0, 6.25, 6.5, 6.75, 7.0, 7.25, 7.5, 7.75)
    ALLOWED_VALUES_INTERNAL = (None, 0, 15, 30, 45, 60, 75, 90, 105, 120, 135, 150, 165, 180, 195, 210, 225, 240, 255,
                               270, 285, 300, 315, 330, 345, 360, 375, 390, 405, 420, 435, 450, 465)

    def __init__(self, *args, **kwargs):
        super(ProductsFilterMixin, self).__init__()
        self.strategy_products_filter = {}  # type: dict[tuple[int, int], float]
        self.max_block_size = COMMON.HOUR
        self.filter2allowed = {}
        self.init_allowed_products()

    def init_allowed_products(self):
        """Calculate the allowed product types and durations once for all allowed filter values

        This method calculates all possible and valid combinations of product types and durations once,
        and caches them in a dictionary.
        """
        # we go through all possible combinations of the product durations in minutes
        # precalculate all filter values
        for filter_val in self.ALLOWED_VALUES_INTERNAL:
            self.filter2allowed[filter_val] = self._get_allowed_product_types_and_durations_by_filter(filter_val)

    def on_strategy_update(self, strategy_json):
        super(ProductsFilterMixin, self).on_strategy_update(strategy_json)
        try:
            self.strategy_products_filter = mk_strategy_tr_dict(
                strategy_json[COMMON.StrategyJsonKey.user_defined_timeseries][self._PRODUCTS_FILTER_TS],
                COMMON.AggregatorRule.min_nonone
            )
        except KeyError:
            self.debug_log("No products filter update set in strategy update")

        # check if uk is one of the defined areas.
        if any(strategy_json[k] in self._4h_block_areas for k in strategy_json.keys() if k.startswith("market_area")):
            self.max_block_size = COMMON.HOUR * 4
            self.debug_log("Strategy set to use up to 4-hour time blocks")
        else:
            self.max_block_size = COMMON.HOUR
            self.debug_log("Strategy set to use up to 1-hour time blocks")

    def products_to_intervals(self, products):
        """Get non-overlapping intervals such that each product's delivery span falls into exactly one interval.

        This is important e.g. for flex strategies which need to bundle products together with the product of
        the longest duration.

        :param products: products to be grouped in blocks

                                .. note::

                                    this list of products should already be prefiltered.
                                    Only products allowed to be traded should be entered here, to avoid issues.

        :type products: iterable[autotrader_core.exchange_trading.Product]
        :return: time intervals for overlapping blocks of products to be traded
        :rtype: list[tuple[float]]

        .. code-block:: python

            # call for a list of allowed products
            trading_intervals = self.products_to_intervals(all_products)

        """
        intervals = set()
        is_max_4h = self.max_block_size == COMMON.HOUR * 4
        for product in products:
            start_ts = product.delivery_start
            end_ts = product.delivery_end
            duration = end_ts - start_ts
            if duration > self.max_block_size:
                self.warn_log("Product duration {} is longer than allowed block duration {}. "
                              "Will not include {}-{} in tradable interval.".format(
                                  duration, self.max_block_size,
                                  ALCU.utc_ts2cet_str(start_ts, add_timezone_info=True),
                                  ALCU.utc_ts2cet_str(end_ts, add_timezone_info=True)),
                              product=product)
                continue

            # get value from product filter timeseries, multiplied by 60 and transformed into integer,
            # to ensure safe comparisons internally
            p_filter = self.get_products_filter(start_ts, end_ts)

            if p_filter is None:
                p_filter = COMMON.ProductDurations.ID.DEFAULT

            allow_4h_blocks = (
                p_filter >= ProductsFilterMixin._2_HOUR_FILTER or p_filter == ProductsFilterMixin._DEFAULT_FILTER
            )
            intervals.add(self.get_block_interval(start_ts, block_hours=4 if is_max_4h and allow_4h_blocks else 1))

        # merge overlapping intervals
        return SU.merge_overlapping(list(intervals))

    @staticmethod
    def get_block_interval(start_ts, block_hours=1):
        """return 1h block or 4h block interval for the given start and end time

        :type start_ts: int
        :type block_hours: int
        :rtype: tuple[int, int]
        """
        # only allow blocks of 1 hour or 4 hour duration
        assert block_hours in (1, 4)

        start_cet_dt = ALCU.utc_ts2cet_dt(start_ts)
        starting_hour = int(start_cet_dt.hour // block_hours * block_hours)
        start_cet_dt = datetime.datetime.combine(start_cet_dt.date(), datetime.time(starting_hour))
        start_block = ALCU.cet_dt2int_ts(start_cet_dt)

        closing_hour = int(start_cet_dt.hour // block_hours * block_hours + block_hours)
        shift_day = int(closing_hour // 24)
        shift_hours = closing_hour % 24
        end_cet_dt = datetime.datetime.combine(start_cet_dt.date() + datetime.timedelta(days=shift_day),
                                               datetime.time(shift_hours))
        end_block = ALCU.cet_dt2int_ts(end_cet_dt)

        return start_block, end_block

    def get_products_filter(self, ts_from, ts_until):
        """get products filter and transform into integer

        the rounding and cast to integer is to avoid machine error issues when comparing floats later

        :type ts_from: int
        :type ts_until: int
        :rtype: int
        """
        # Set product filter, for hour, half and quarter products
        product_filter = self.strategy_products_filter.get((ts_from, ts_until))
        if product_filter is None:
            return self._DEFAULT_FILTER

        val = int(
            round(round(product_filter / self.INPUT_TICK, 2) * self.INPUT_TICK * self._PRODUCT_FILTER_MULTIPLE_FACTOR)
        )
        if val not in self.ALLOWED_VALUES_INTERNAL:
            raise ValueError("Passed product filter to strategy with value: {}. "
                             "Allowed product filters to pass must be within: 0 - 7.75. "
                             "And must be None or a sum of a combination of (at most one of each): "
                             "[0, 0.25, 0.5, 1, 2, 4]. Possible Values: {}."
                             "E.g. use 4.5 for 4 hour and 30min products."
                             .format(product_filter, self.ALLOWED_VALUES_INPUT))

        return val

    def get_allowed_products(self, all_range_products, timestamp=None, active_on_area=None):
        """filter products based on passed criteria

        :param all_range_products: all products to be filtered
        :type all_range_products: list[autotrader_core.exchange_trading.Product]
        :param timestamp: timestamp, at which the strategy is checked to be active for a certain area
        :type timestamp: float or None
        :param active_on_area: area on which the strategy should be active, if requested
        :type active_on_area: str or None
        :return: list of products which are allowed according to the criteria and the product filter settings
        :rtype: list[autotrader_core.exchange_trading.Product]
        """

        products = []
        if active_on_area:
            assert timestamp is not None, "timestamp needs to be set, when checking if a product is active on an area"

        all_tradable_durations = set()
        for product in all_range_products:
            if active_on_area is not None and timestamp is not None and \
                    not product.is_tradable(timestamp, active_on_area):
                continue

            tradable_types, tradable_durations = self.get_allowed_product_types_and_durations(
                product.delivery_start, product.delivery_end
            )

            if (
                (product.product_type in tradable_types)
                and (int(product.delivery_end - product.delivery_start) in tradable_durations)
            ):
                products.append(product)

            all_tradable_durations.update(tradable_durations)

        self.debug_log("Filtered Allowed Products (OK-dur: {}): {}".format(
            all_tradable_durations, ",".join(["{} ({})".format(p.name, p.product_id)
                                              for p in products])))
        return products

    def get_allowed_product_types_and_durations(self, ts_from, ts_until):
        """get allowed product types and durations based on area and product filter.

        This function allows 30min products for uk and france and keeps
        backwards compatibility with for all other areas

        Examples of area, product filter and allowed products:
        product filter user input   0                  0.25   0.5      1     1.5       1.75        2     3      4    6
        product filter internal int 0                  15     30       60     90        105       120   180    240  360
        allowed durations           4H 2H 1H 30M 15M   15M    30M      1H   1H 30M    1H 30M 15M   2H   2H 1H  4H  4H 2H

        :param ts_from: beginning of time window, which is used to check for the product filter value
        :type ts_from: int
        :param ts_until: end of time window, which is used to check for the product filter value
        :type ts_until: int
        :return: set of acceptable product types and set of durations in seconds
        :rtype: tuple[tuple[str], tuple[int]]
        """
        product_filter = self.get_products_filter(ts_from, ts_until)
        try:
            return self.filter2allowed[product_filter]
        except KeyError:
            prod_types, prod_durs = self._get_allowed_product_types_and_durations_by_filter(product_filter)
            self.filter2allowed[product_filter] = (prod_types, prod_durs)
            self.warn_log("Products Filter value [ts: {}-{} ({}-{})]: {}."
                          "This is not a standard value. "
                          "Input will allow following durations: {} "
                          "Please use one of the standard values: {}."
                          .format(ALCU.utc_ts2cet_str(ts_from),
                                  ALCU.utc_ts2cet_str(ts_until, add_timezone_info=True),
                                  ts_from, ts_until, self.strategy_products_filter.get((ts_from, ts_until)),
                                  prod_durs, self.ALLOWED_VALUES_INPUT))
            return prod_types, prod_durs

    @staticmethod
    def _get_allowed_product_types_and_durations_by_filter(product_filter):
        """Get allowed Product types and durations for defined product filter. Empty Products for bad value.

        :param product_filter: beginning of time window, which is used to check for the product filter value
        :type product_filter: int
        :return: set of acceptable product types and set of durations in seconds
        :rtype: tuple[tuple[str], tuple[int]]
        """
        # all products if products filter is 0 or empty:
        if product_filter == 0 or product_filter is None:
            return COMMON.ProductType.ID.ALL, COMMON.ProductDurations.ID.ALL
        # else, should be multiples of 15 and between 0 and 465
        if product_filter not in ProductsFilterMixin.ALLOWED_VALUES_INTERNAL:
            return (), ()

        available_products_filter = ()
        acceptable_durations = ()

        # if at least 4 hours
        if product_filter >= ProductsFilterMixin._4_HOUR_FILTER:
            product_filter -= ProductsFilterMixin._4_HOUR_FILTER
            available_products_filter += COMMON.ProductType.ID.ALL_4_HOUR
            acceptable_durations += (COMMON.ProductDurations.ID.BLOCK_4_HOUR, )
        # if at least 2 hours
        if product_filter >= ProductsFilterMixin._2_HOUR_FILTER:
            product_filter -= ProductsFilterMixin._2_HOUR_FILTER
            available_products_filter += COMMON.ProductType.ID.ALL_2_HOUR
            acceptable_durations += (COMMON.ProductDurations.ID.BLOCK_2_HOUR, )
        # if at least 1 hour
        if product_filter >= ProductsFilterMixin._1_HOUR_FILTER:
            product_filter -= ProductsFilterMixin._1_HOUR_FILTER
            available_products_filter += COMMON.ProductType.ID.ALL_HOUR
            acceptable_durations += (COMMON.ProductDurations.ID.HOUR, )
        # if at least 30min
        if product_filter >= ProductsFilterMixin._30_MIN_FILTER:
            product_filter -= ProductsFilterMixin._30_MIN_FILTER
            available_products_filter += COMMON.ProductType.ID.ALL_HALF
            acceptable_durations += (COMMON.ProductDurations.ID.HALF, )
        # if at least 15min
        if product_filter >= ProductsFilterMixin._15_MIN_FILTER:
            product_filter -= ProductsFilterMixin._15_MIN_FILTER
            available_products_filter += COMMON.ProductType.ID.ALL_QUARTERS
            acceptable_durations += (COMMON.ProductDurations.ID.QUARTER, )

        return available_products_filter, acceptable_durations
