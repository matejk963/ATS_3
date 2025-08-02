#!/usr/bin/python3
# -*- coding: utf-8 -*-

from __future__ import absolute_import
import types as T
import six

import autotrader_lib.common as COMMON
import autotrader_lib.compliance_log_templates as LOGTEMP
import autotrader_core.exchange_trading as APITR
import autotrader_core.exchanges as APIEXCH
import autotrader_core.strategy
if six.PY2:
    import autotrader_lib.fast_logging_py2 as FLOG
else:
    import autotrader_lib.fast_logging_py3 as FLOG
from six.moves import map
from six.moves import zip


log = FLOG.getLogger('limit_management')


def check_order(strategy, order, exchange, current_timestamp):
    # type: (autotrader_core.strategy.Strategy, APITR.OwnOrder, APIEXCH.ExchangeBase, float) -> T.ListType[str]
    """Checks a new/updated order produced by a strategy

    :param strategy: strategy instance, member of :class:`autotrader_core.strategy.Strategy`
    :param order: new or updated order (member of :class:`APITR.Order`) belonging to that strategy
    :param exchange: exchange instance (member of :class:`APIEXCH.ExchangeBase`)
                     to which the order belongs
    :param float current_timestamp: current timestamp
    :return: list of found limit/behavioral violations
    :rtype: list[str]
    """
    return check_limits(strategy, order, exchange) + check_flapping_behaviour(strategy, order, current_timestamp)


def check_actions_in_rolling_time(exchange, broker_id, current_timestamp, order_to_send_count=None):
    # type: (APIEXCH.ExchangeBase, str, float, dict) -> T.ListType[str]
    """Checks if the limit of allowed actions (price updates) is violated for a given broker

    :param exchange: exchange instance (member of :class:`APIEXCH.ExchangeBase`)
                     to which the order belongs
    :type exchange: APIEXCH.ExchangeBase
    :param broker_id: broker id as str
    :type broker_id: str
    :param current_timestamp: current timestamp in seconds
    :type current_timestamp: float
    :param order_to_send_count: count of how many orders will be sent to the exchange for the given broker
    :type: dict
    :return: [] if no limit violation, else a [str] with the error is returned
    :rtype: list
    """
    try:
        action_limit = exchange.products.settings_per_broker[broker_id][COMMON.ActionLimits.limit]
        action_interval = exchange.products.settings_per_broker[broker_id][COMMON.ActionLimits.interval]
        order_count = order_to_send_count[exchange.internal_id].get(broker_id, 0)
        order_actions = exchange.products.actions_in_rolling_time(broker_id, current_timestamp)
    except KeyError:
        # no action limit
        return []
    if (order_count + order_actions) < action_limit:
        order_to_send_count[exchange.internal_id][broker_id] = order_count + 1
        # everthing ok
        return []
    else:
        return [
            "Action limit reached, too many order actions (max {} per {} seconds) for exchange {} with broker_id {}"
            "".format(action_limit, action_interval, exchange.internal_id, broker_id)]


def check_flapping_behaviour(strategy, order, current_timestamp):
    # type: (autotrader_core.strategy.Strategy, APITR.Order, float) -> T.ListType[str]
    """Checks flapping behavior of a new/updated order produced by a strategy

    :param strategy: strategy instance, member of :class:`autotrader_core.strategy.Strategy`
    :param order: new or updated order (member of :class:`APITR.Order`) belonging to that strategy
    :param current_timestamp: current timestamp
    :return: list with a message if flapping behavior was found
    :rtype: list[str]
    """
    # check trades in the neg_buyback_period
    trades = order.product.trades.get(trade_filter=COMMON.TradeFilter.own,
                                      portfolio_key=strategy.strategy_id,
                                      timerange=(current_timestamp - strategy.neg_buyback_period, current_timestamp))
    # no trades, no problem
    if len(trades) < strategy.maximum_neg_buyback + 1:
        # too few trades in neg_buyback_period for flapping behaviour
        return []
    sells = [t for t in trades if t.direction == COMMON.Direction.sell]
    buys = [t for t in trades if t.direction == COMMON.Direction.buy]
    sell_qty = sum(t.quantity for t in sells)
    buy_qty = sum(t.quantity for t in buys)
    if not sell_qty or not buy_qty:
        return []
    # first check: do we sell for worse prices than we buy
    sell_price = sum(t.price * t.quantity for t in sells) / sell_qty
    buy_price = sum(t.price * t.quantity for t in buys) / buy_qty
    if sell_price >= buy_price:
        # everything ok
        return []
    # second check: do we have suspicious switches between sell and buy
    trades.sort(key=lambda x: x.execution_time)
    num_switches = len([a for a, b in zip(trades[:-1], trades[1:]) if a.direction != b.direction])
    if num_switches < strategy.maximum_neg_buyback:
        # everything ok
        return []
    return ["flapping strategy behaviour at {}: sold {}@{}, bought {}@{} with the"
            " trades {}".format(current_timestamp, sell_qty, sell_price, buy_qty, buy_price,
                                ",".join(trade.trade_id for trade in trades))]


class LimitViolationInfo(object):
    violation_type_missing = "missing limit"
    violation_type_violation = "limit violation"

    def __init__(self, limit_name, source, limit_value, observed_value):
        """
        Store information about limit violations for logging.

        :param limit_name: Name of the limit that was violated.
        :type limit_name: str
        :param source: Where the limit was set. Should be one of "no limit set", "from timeseries",
                       "from master data", "from sequence/ sequence item"
        :type source: str
        :param limit_value: The value of the limit
        :type limit_value: float | None
        :param observed_value: The observed value (e.g. price or volume)
        :type observed_value: float | None
        """
        self._limit_name = limit_name
        self._source = source
        self._limit_value = limit_value
        self._observed_value = observed_value
        # Cache the string representation to avoid 1 call to .format, as we need it twice per violation.
        self._str = None

    def to_dict(self):
        """
        Return information about this limit violation in a structured way that can be used with compliance logging.

        :rtype: dict
        """
        return {"text": str(self), "limit_name": self._limit_name, "limit_source": self._source,
                "limit_value": self._limit_value, "observed_value": self._observed_value,
                "violation_type": self.violation_type}

    @property
    def violation_type(self):
        """
        The type of limit violation.

        :return: Either "missing limit" or "limit violation"
        :rtype: str
        """
        if self._limit_value is None:
            return self.violation_type_missing
        else:
            return self.violation_type_violation

    def __str__(self):
        if self._str is None:
            if self.violation_type == self.violation_type_missing:
                self._str = "No limit set for {}.".format(self._limit_name)
            else:
                op = ">" if self._limit_name.startswith("max") else "<"
                self._str = "{} ({}): {} {} {}".format(self._limit_name, self._source,
                                                       self._observed_value, op, self._limit_value)
        return self._str


def check_limits(strategy, order, exchange):
    # type: (autotrader_core.strategy.Strategy, APITR.OwnOrder, APIEXCH.ExchangeBase) -> T.ListType[str]

    """Checks price and volume limit violations for a new/updated order produced by a strategy

    :param strategy: strategy instance, member of :class:`autotrader_core.strategy.Strategy`
    :param order: new or updated order (member of :class:`APITR.OwnOrder`) belonging to that strategy
    :param exchange: exchange instance (member of :class:`APIEXCH.ExchangeBase`)
                     to which the order belongs
    :return: list with messages describing found limit violations, str of LimitViolationInfo
    :rtype: list[str]
    """
    found_limit_violations = []

    product_interval = (int(order.product.delivery_start), int(order.product.delivery_end))
    if order.direction == COMMON.Direction.bid:
        max_buy_volume_ts = strategy.strategy_limit_maximum_purchase_volume.get(product_interval)
        max_buy_volume_product = strategy.per_product_limits.get_limit("maximum_purchase_volume", order.product)

        max_buy_price_ts = strategy.strategy_limit_maximum_purchase_price.get(product_interval)
        max_buy_price_product = strategy.per_product_limits.get_limit("maximum_purchase_price", order.product)

        if max_buy_price_product is None and max_buy_price_ts is None:
            info = LimitViolationInfo("maximum_purchase_price", "no limit set", None, order.price)
            found_limit_violations.append(info)
        else:
            if max_buy_price_ts is not None:
                if order.price > max_buy_price_ts + 0.005:
                    info = LimitViolationInfo("maximum_purchase_price", "from timeseries",
                                              max_buy_price_ts + 0.005, order.price)
                    found_limit_violations.append(info)
            if max_buy_price_product is not None:
                if order.price > max_buy_price_product + 0.000001:  # Tiny tolerance for float inaccurracies
                    info = LimitViolationInfo("maximum_purchase_price", "from sequence/ sequence item",
                                              max_buy_price_product, order.price)
                    found_limit_violations.append(info)
        found_limit_violations.extend(check_volume_limits(order, exchange, strategy.maximum_bid, max_buy_volume_product,
                                                          max_buy_volume_ts))

    elif order.direction == COMMON.Direction.ask:
        max_sell_volume_ts = strategy.strategy_limit_maximum_sales_volume.get(product_interval)
        max_sell_volume_product = strategy.per_product_limits.get_limit("maximum_sales_volume", order.product)

        min_sell_price_ts = strategy.strategy_limit_minimum_sales_price.get(product_interval)
        min_sell_price_product = strategy.per_product_limits.get_limit("minimum_sales_price", order.product)

        if min_sell_price_product is None and min_sell_price_ts is None:
            info = LimitViolationInfo("minimum_sales_price", "no limit set", None, order.price)
            found_limit_violations.append(info)
        else:
            if min_sell_price_ts is not None:
                if order.price < min_sell_price_ts - 0.005:
                    info = LimitViolationInfo("minimum_sales_price", "from timeseries",
                                              min_sell_price_ts - 0.005, order.price)
                    found_limit_violations.append(info)
            if min_sell_price_product is not None:
                if order.price < min_sell_price_product - 0.000001:  # Tiny tolerance for float inaccuracies
                    info = LimitViolationInfo("minimum_sales_price", "from sequence/ sequence item",
                                              min_sell_price_product, order.price)
                    found_limit_violations.append(info)
        found_limit_violations.extend(check_volume_limits(order, exchange, strategy.maximum_ask,
                                                          max_sell_volume_product, max_sell_volume_ts))
    if found_limit_violations:
        log.compliance_log(LOGTEMP.AutoTraderLimiter.found_limit_violations,
                           strategy_id=strategy.strategy_id,
                           order=LOGTEMP.get_own_order_keys(order),
                           limit_violations=[info_.to_dict() for info_ in found_limit_violations])

    return list(map(str, found_limit_violations))


def check_volume_limits(order, exchange, max_order_volume, max_volume_product, max_volume_ts):
    """
    Check all volume related limits of an order.

    :param order: The order to check
    :type order: APITR.OwnOrder
    :param exchange: The exchange Object
    :type exchange: APIEXCH.ExchangeBase
    :param max_order_volume: The maximal volume of a single order
    :type max_order_volume: float | None
    :param max_volume_product: The maximal volume of all orders/ trades for this strategy on this product.
                               (This is set via the REST-API, and mostly used for forwards and futures)
    :type max_volume_product: float | None
    :param max_volume_ts: The maximal volume of all orders/ trades for this strategy on all products
                          overlapping the delivery interval of this order. (This comes from periotheus timeseries)
    :type max_volume_ts: float | None
    :return: A list of limit violations. Empty list if no violations were found
    :rtype: list
    """

    # Some terminology for the violation messages
    limit_names = {("max_order_volume", COMMON.Direction.buy): "maximum_bid",
                   ("max_order_volume", COMMON.Direction.ask): "maximum_ask",
                   ("max_volume", COMMON.Direction.buy): "maximum_purchase_volume",
                   ("max_volume", COMMON.Direction.sell): "maximum_sales_volume"
                   }
    product_interval = (order.product.delivery_start, order.product.delivery_end)
    found_limit_violations = []
    # we have to take units into regard here.
    # max order volume may be in MW, as all values on Periotheus, however on PEG we have PEG_MWH_DAY
    if isinstance(exchange, APIEXCH.Trayport):
        area_property = exchange.trayport_areas[order.delivery_area_id]
        if area_property.unit.upper() == "MEGAWATT HOURS PER DAY":
            if max_order_volume is not None:
                max_order_volume *= 24
            if max_volume_product is not None:
                max_volume_product *= 24

    if max_order_volume is not None and order.quantity > max_order_volume:
        info = LimitViolationInfo(limit_names[("max_order_volume", order.direction)], "from master data",
                                  max_order_volume, order.quantity)
        found_limit_violations.append(info)
    if max_volume_ts is None and max_volume_product is None:
        # At least one limit has to be set, either via timeseries or via product/ sequence id.
        info = LimitViolationInfo(limit_names[("max_volume", order.direction)], "no limit set",
                                  None, order.quantity)
        found_limit_violations.append(info)
    else:
        # If at least one limit (per sequence_id or via timeseries) is set,
        # then we check the limits independently
        if max_volume_ts is not None:
            total_volume = get_max_total_volume(product_interval, order, exchange)
            try:
                if total_volume > max_volume_ts + 0.005:
                    info = LimitViolationInfo(limit_names[("max_volume", order.direction)], "from timeseries",
                                              max_volume_ts, total_volume)
                    found_limit_violations.append(info)
            except TypeError:  # To handle Python3 TypeError for MagicMock comparison with float
                pass
        if max_volume_product is not None:
            product_volume = get_single_product_total_volume(order)
            if product_volume > max_volume_product + 0.000001:  # Tiny tolerance for float inaccuracies
                info = LimitViolationInfo(limit_names[("max_volume", order.direction)], "from sequence/ sequence item",
                                          max_volume_product, product_volume)
                found_limit_violations.append(info)
    return found_limit_violations


def get_single_product_total_volume(order):
    """
    Get the total volume of all orders/ trades for the order's strategy on the order's product.

    Includes the volume of the given order
    :param order: The order to check
    :type order: APITR.OwnOrder
    :return: The volume
    :rtype: float
    """
    product = order.product
    is_sell = order.direction == COMMON.Direction.sell
    order_filter = COMMON.OrderFilter.own_sell if is_sell else COMMON.OrderFilter.own_buy

    trade_volume = product.trades.get_balance(order.delivery_area_id, order.portfolio_key) * (-1) ** is_sell
    order_volume = product.orders.get_volume(order.delivery_area_id, order_filter, order.internal_id,
                                             order.portfolio_key)
    return order_volume + trade_volume + order.quantity


def get_max_total_volume(time_interval, order, exchange):
    """Function returns max total volume of orders and trades

    The time interval is split into smaller time intervals determined by delivery
    span of the products, if any of the delivery spans, i.e. delivery_start and delivery_end,
    is within this time interval.
    For each time interval the total volume (order volume at the exchange + traded balanced volume + order volume)
    is evaluated (in MW).
    We, then, take the max of the found volumes.

    :param Tuple[float, float] time_interval: a list determining time interval (i.e. start and end timestamps)
                                              for which the total volume is to be evaluated
    :param order: new or updated order (member of :class:`APITR.Order`) to be checked for limit violations
    :param exchange: exchange instance (member of :class:`APIEXCH.ExchangeBase`)
                     to which the order belongs

    :return: maximal total volume
    :rtype: float
    """
    start, end = time_interval
    products = exchange.products.get_overlapping_with_timerange(start, end)

    product_starts = set([product.delivery_start if product.delivery_start >= start else start for product in products])
    product_ends = set([product.delivery_end if product.delivery_end <= end else end for product in products])

    timepoints = sorted(product_starts.union(product_ends))

    is_sell = order.direction == COMMON.Direction.sell

    order_filter = COMMON.OrderFilter.own_sell if is_sell else COMMON.OrderFilter.own_buy
    volumes = []
    for start, end in zip(timepoints[:-1], timepoints[1:]):
        products_in_interval = [product for product in products
                                if product.delivery_start <= start and product.delivery_end >= end]
        trade_volume_balance = exchange.products.get_total_traded_volume(
            products_in_interval, order.delivery_area_id, COMMON.TradeFilter.own, order.portfolio_key, balance=True)
        order_volume = exchange.products.get_total_order_volume(
            products_in_interval, order.delivery_area_id, order_filter, order.portfolio_key, order.internal_id)
        volumes.append(order_volume + trade_volume_balance * (-1) ** is_sell + order.quantity)

    return max(volumes)
