# coding=utf-8
from __future__ import absolute_import
import collections
import datetime
import time

import autotrader_lib.common as COMMON
import autotrader_lib.util as UTIL


class EmptyMarketAreas(Exception):
    pass


class CommingledView(object):
    """
    A CommingledView is a thin wrapper as a preview into a product for specified market areas and
    strategy id combination. Provides a collection of indicators that can be queried by synthetic orders.

    IMPORTANT: As long as these views are created and destroyed on each loop
    we do not need to think about cache invalidation as they are short lived
    """

    _order_filter_mapping = {
        (COMMON.Direction.buy, True, True): COMMON.OrderFilter.com_public_buy,
        (COMMON.Direction.buy, True, False): COMMON.OrderFilter.public_buy,
        (COMMON.Direction.buy, False, True): COMMON.OrderFilter.com_buy,
        (COMMON.Direction.buy, False, False): COMMON.OrderFilter.only_buy,

        (COMMON.Direction.sell, True, True): COMMON.OrderFilter.com_public_sell,
        (COMMON.Direction.sell, True, False): COMMON.OrderFilter.public_sell,
        (COMMON.Direction.sell, False, True): COMMON.OrderFilter.com_sell,
        (COMMON.Direction.sell, False, False): COMMON.OrderFilter.only_sell,
    }

    def __init__(self, product, market_areas, strategy_id):
        """
        :param product: The product object for which we would like to create the commingled view
        :type product: autotrader_core.exchange_trading.Product
        :param market_areas: The list of market areas for which this view should be created
        :type market_areas: list[str]
        :param strategy_id: The id of the strategy within which this local view is created
        :type strategy_id: str
        """
        if not market_areas:
            raise EmptyMarketAreas

        self._product = product
        # for now we ignore duplicated market areas
        self._market_areas = list(set(market_areas))

        # as views are always created within a strategy
        # they can already be initialized with the strategy_id
        self._strategy_id = strategy_id

        self._public_trades = list()
        self._public_trade_last_update_ts = 0

        self._public_trade_filter = collections.namedtuple("public_trade_filter", ["from_ts", "to_ts", "broker_id"])

        # new filters will be set the first time, when build statistics is called
        self._public_trade_new_filters = self._public_trade_filter(from_ts=0, to_ts=0, broker_id=None)
        self._public_trade_applied_filters = self._public_trade_filter(from_ts=0, to_ts=0, broker_id=None)

        self._trade_statistics = TradeStatistics()

        self._statistics_methods = {
            COMMON.TradeStatisticsMetric.vwap: self._public_trade_vwap,
            COMMON.TradeStatisticsMetric.low_price: self._public_trade_low_price,
            COMMON.TradeStatisticsMetric.high_price: self._public_trade_high_price,
            COMMON.TradeStatisticsMetric.first_price: self._public_trade_first_price,
            COMMON.TradeStatisticsMetric.last_price: self._public_trade_last_price,
            COMMON.TradeStatisticsMetric.last_change: self._public_trade_last_change,
            COMMON.TradeStatisticsMetric.volume_buy: self._public_trade_volume_buy,
            COMMON.TradeStatisticsMetric.volume_sell: self._public_trade_volume_sell,
        }

    def __repr__(self):
        return "CommingledView(product='{}(id:{})', market_areas={}, strategy_id={})\nStatistics: {}".format(
            self._product.name, self._product.product_id, self._market_areas, self._strategy_id, self._trade_statistics)

    def current_front_volume(self, direction, broker_id=None, only_tradable=True, include_public=True,
                             include_own_manual=False):
        """ Indicator returning the front VOLUME of the orders, on the defined direction

        :param direction: BUY or SELL
        :type direction: str
        :param broker_id: optional filter on the broker ids in the OrderBook
        :type broker_id: str
        :param only_tradable: optional - if True, only those orders are counted where order.is_tradable == True
        :type only_tradable: bool
        :param include_public: optional - if True, the public orders are included within the calculation, otherwise
                               the public orders are not included
        :type include_public: bool
        :param include_own_manual: optional - if True, the manual orders but not autoTRADER orders are included within
                                   the calculation, otherwise the manual orders are not included
        :type include_own_manual: bool
        :return: The VOLUME of the front order in the side of the OrderBook specified by direction
        :rtype: float
        """
        price_quantities = self._summarize_price_level(direction, broker_id, only_tradable=only_tradable,
                                                       include_public=include_public,
                                                       include_own_manual=include_own_manual)
        if price_quantities:
            return price_quantities[0][1]
        return None

    def current_front_price(self, direction, broker_id=None, only_tradable=True, include_public=True,
                            include_own_manual=False):
        """ Indicator returning the front PRICE of the orders, on the defined direction

        :param direction: BUY or SELL
        :type direction: str
        :param broker_id: optional filter on the broker ids in the OrderBook
        :type broker_id: str
        :param only_tradable: optional - if True, only those orders are counted where order.is_tradable == True.
        :type only_tradable: bool
        :param include_public: optional - if True, the public orders are included within the calculation, otherwise
            the public orders are not included
        :type include_public: bool
        :param include_own_manual: optional - if True, the manual orders but not autoTRADER orders are included within
            the calculation, otherwise the manual orders are not included
            Note: Most (but not all) OwnOrders are untradable, so you might want to set only_tradable to False when
            using this filter
        :type include_own_manual: bool
        :return: The PRICE of the front order in the side of the OrderBook specified by direction
        :rtype: float
        """
        return self.current_order_price(direction, at_volume=0, broker_id=broker_id,
                                        only_tradable=only_tradable, include_public=include_public,
                                        include_own_manual=include_own_manual)

    def _summarize_price_level(self, side, broker_id, only_tradable=True, include_public=True,
                               include_own_manual=False):
        """
        Helper function that will return a price ladder for an orderbook

        :param side: The side for which we wish to calculate the price level
        :type side: str
        :param broker_id: The broker id used to identify correct orders
        :type broker_id: str
        :param only_tradable: optional - if True, only those orders are counted where order.is_tradable == True
        :type only_tradable: bool
        :param include_public: optional - if True, the public orders are included within the calculation, otherwise
        the public orders are not included
        :type include_public: bool
        :param include_own_manual: optional - if True, the manual orders but not autoTRADER orders are included within
        the calculation, otherwise the manual orders are not included
        :type include_own_manual: bool
        :return: Price ladder for an orderbook
        :rtype: List[Tuple[float, float]]
        """
        if side == COMMON.Direction.buy:
            reverse = True
        else:
            reverse = False

        filter_orders = self.create_order_filter(side, include_public, include_own_manual)
        orders = list()
        for market_area in self._market_areas:
            orders.extend(self._product.orders.get(market_area, filter_orders, broker_id=broker_id,
                                                   only_tradable=only_tradable, only_active=True))
        summarized_price_levels = _summarize_price_level(orders=orders)
        summarized_price_levels.sort(key=lambda e: e[0], reverse=reverse)
        return summarized_price_levels

    def _public_trade_filter_changed(self):
        """
        Helper function telling if public trade filter was changed
        :return: True if public trade filter was changed or False otherwise
        :rtype: bool
        """
        return any((self._public_trade_new_filters.from_ts != self._public_trade_applied_filters.from_ts,
                    self._public_trade_new_filters.to_ts != self._public_trade_applied_filters.to_ts,
                    self._public_trade_new_filters.broker_id != self._public_trade_applied_filters.broker_id))

    def _public_trades_changed(self):
        """
        Helper function telling if public trades in any of defined market areas were changed
        :return: True if trades in any of defined market areas were changed or False otherwise
        :rtype: bool
        """
        for market_area in self._market_areas:
            key = (self._product.product_id, market_area)
            if self._product.trades.last_trade_update_ts[key] > self._public_trade_last_update_ts:
                return True
        return False

    def _set_public_trade_filters(self, from_ts=None, to_ts=None, broker_id=None):
        """
        Helper function setting public trade filters
        :param from_ts: timestamp from
        :type from_ts: int
        :param to_ts:  timestamp to
        :type to_ts: int
        :param broker_id: optional filter for broker
        :type broker_id: str
        :return: None
        """
        # if a filter value is None, we define it so that it lets through every trade
        self._public_trade_new_filters = self._public_trade_filter(from_ts=0 if from_ts is None else from_ts,
                                                                   to_ts=time.time() if to_ts is None else to_ts,
                                                                   broker_id=broker_id)

    @property
    def public_trades(self):
        """
        Property, which stores list of public trades, and is updated only when it's used for calculations.

        If not set (==None) or one of the filters has changed, or it was not filled more than 1 minute ago,
        it fills itself from loaded public trade data (public trades are available in DB for the last 72 hours).
        The 1 minute timeout is needed, because it can happen that a new public trade appears in autoTRADER later
        with such an execution time, which was already included in the actual time filter.
        By default the public trades are sorted by execution time, because many metrics utilize this ordering.
        """
        if not self._public_trades or self._public_trade_filter_changed() or self._public_trades_changed():
            filtered_public_trades = list()
            for market_area in self._market_areas:
                filtered_public_trades.extend(self._product.trades.get(trade_filter=COMMON.TradeFilter.public,
                                                                       delivery_area=market_area,
                                                                       timerange=(
                                                                           self._public_trade_new_filters.from_ts,
                                                                           self._public_trade_new_filters.to_ts)))
            # broker_id filtering isn't implemented in TradeList object, so it's filtered below with list comprehension
            broker_id = self._public_trade_new_filters.broker_id
            if broker_id is not None:
                filtered_public_trades = [pub_trade for pub_trade in filtered_public_trades if
                                          pub_trade.initiator_broker_id == broker_id
                                          or pub_trade.aggressor_broker_id == broker_id]
            self._public_trades = sorted(filtered_public_trades, key=lambda t: t.execution_time)

            # storing timestamp of the last update to handle timeouts
            product_trade_updates = [self._product.trades.last_trade_update_ts[(self._product.product_id, market_area)]
                                     for market_area in self._market_areas]
            self._public_trade_last_update_ts = max(product_trade_updates)
            # update the applied filters tuple, not to load the same list later again
            self._public_trade_applied_filters = self._public_trade_new_filters
        return self._public_trades

    def _public_trade_vwap(self):
        """ Metric function that calculates the Volume Weighted Average Price of active public trades """
        weighted_price_sum = 0.0
        quantity_sum = 0.0
        for pt in self.public_trades:
            weighted_price_sum += pt.quantity * pt.price
            quantity_sum += pt.quantity
        return UTIL.round_float(weighted_price_sum / quantity_sum) if quantity_sum > 0 else None

    def _public_trade_low_price(self):
        """ Metric function that selects the lowest price of active public trades """
        low_trade = min(self.public_trades, key=lambda t: t.price) if self.public_trades else None
        return low_trade.price if low_trade else None

    def _public_trade_high_price(self):
        """ Metric function that selects the highest price of active public trades """
        high_trade = max(self.public_trades, key=lambda t: t.price) if self.public_trades else None
        return high_trade.price if high_trade else None

    def _public_trade_first_price(self):
        """ Metric function that returns with the price of the earliest public trade in the list """
        return self.public_trades[0].price if self.public_trades else None

    def _public_trade_last_price(self):
        """ Metric function that returns with the price of the latest public trade in the list """
        return self.public_trades[-1].price if self.public_trades else None

    def _public_trade_last_change(self):
        """
        Metric function that returns with the difference of the last two public trade in the list.
        If there is only one trade, it returns 0.
        """
        len_trades = len(self.public_trades)
        if len_trades == 0:
            return None
        elif len_trades == 1:
            return 0.0
        else:
            last_2_trades = self.public_trades[-2:]
            return UTIL.round_float(last_2_trades[1].price - last_2_trades[0].price)

    def _public_trade_volume_buy(self):
        """ Metric function that summarizes the quantities of public trades that have a buy delivery area defined. """
        buy_volumes = sum(pt.quantity for pt in self.public_trades if pt.buy_delivery_area in self._market_areas)
        return buy_volumes if buy_volumes else None

    def _public_trade_volume_sell(self):
        """ Metric function that summarizes the quantities of public trades that have a sell delivery area defined. """
        sell_volumes = sum(pt.quantity for pt in self.public_trades if pt.sell_delivery_area in self._market_areas)
        return sell_volumes if sell_volumes else None

    def get_trade_statistics(self, metrics=None, from_dt=None, to_dt=None, broker_id=None):
        """
        Initiates calculation or recalculation of the required trade metrics. These metrics are given as a parameter
        list of strings. The results are stored in _trade_statistics object as attributes until build is called again.

        :param metrics: list of metric names that denote required metrics to be stored.
                        If None then we calculate all the metrics listed in _trade_statistics.all_metrics.
        :type metrics: None or List[str]
        :param from_dt: lower boundary of the timeframe which filters the public trades used for calculation.
                        If None then we don't specify a lower boundary (minus infinite).
        :type from_dt: None or datetime.datetime
        :param to_dt: upper boundary of the timeframe which filters the public trades used for calculation
                      If None then we don't specify an upper boundary (minus infinite).
        :type to_dt: None datetime.datetime
        :param broker_id: a specific broker which we require to be participant in the public trade.
                          If None then we don't filter on brokers.
        :type broker_id: None or str
        :return TradeStatistics: Returns the updated trade statistics object
        """

        # we want to have a snapshot in time, but if to_dt would be None, current time would change between metrics:
        to_dt = datetime.datetime.utcnow() if to_dt is None else to_dt
        # if metrics is not given, we calculate all of them by default
        if metrics is None:
            metrics = self._trade_statistics.all_metrics

        from_ts = None if from_dt is None else UTIL.convert_dt_to_timestamp(from_dt)
        to_ts = None if to_dt is None else UTIL.convert_dt_to_timestamp(to_dt)
        self._set_public_trade_filters(from_ts, to_ts, broker_id)

        for metric_name in self._trade_statistics.all_metrics:
            if metric_name in metrics:
                result = self._statistics_methods[metric_name]()
                setattr(self._trade_statistics, metric_name, result)
            elif hasattr(self._trade_statistics, metric_name):
                delattr(self._trade_statistics, metric_name)
        return self._trade_statistics

    def current_order_price(self, direction, at_volume, broker_id=None, only_tradable=True, include_public=True,
                            include_own_manual=False):
        """
        Retrieves the best current price from the orders for a given direction and volume amount.

        :param direction: direction of the orders under check
        :type direction: str, member of :class:`COMMON.Direction`
        :param at_volume: the requested quantity
        :type at_volume: float
        :param broker_id: optional filter on the broker ids of the orders
        :type broker_id: str
        :param only_tradable: optional - if True, only those orders are counted where order.is_tradable == True
        :type only_tradable: bool
        :param include_public: optional - if True, the public orders are included within the calculation, otherwise
                               the public orders are not included
        :type include_public: bool
        :param include_own_manual: optional - if True, the manual orders but not autoTRADER orders are included within
                                   the calculation, otherwise the manual orders are not included
        :type include_own_manual: bool
        :return: price
        :rtype: float or None
        """
        if at_volume is None:
            return None

        filter_orders = self.create_order_filter(direction, include_public, include_own_manual)
        return self._product.orders.get_price_at_min_volume(at_volume, filter_orders,
                                                            delivery_area_id=self._market_areas,
                                                            broker_id=broker_id, only_tradable=only_tradable)[0]

    def current_orders_depth(self, direction, broker_id=None, only_tradable=True, include_public=True,
                             include_own_manual=False):
        """
        Returns the aggregated volume of orders of the specified direction

        :param direction: direction of the orders under check
        :type direction: str, member of :class:`COMMON.Direction`
        :param broker_id: optional filter on the broker ids of the orders
        :type broker_id: str
        :param only_tradable: optional - if True, only those orders are counted where order.is_tradable == True
        :type only_tradable: bool
        :param include_public: optional - if True, the public orders are included within the calculation, otherwise
                               the public orders are not included
        :type include_public: bool
        :param include_own_manual: optional - if True, the manual orders but not autoTRADER orders are included within
                                   the calculation, otherwise the manual orders are not included
        :type include_own_manual: bool
        :return: The aggregated volume of orders of the specified direction
        :rtype: float
        """
        order_depth = 0.0
        filter_order = self.create_order_filter(direction, include_public, include_own_manual)
        for market_area in self._market_areas:
            order_depth += self._product.orders.get_volume(market_area, filter_order,
                                                           broker_id=broker_id,
                                                           only_tradable=only_tradable,
                                                           only_active=True,
                                                           )
        return order_depth

    def current_front_price_spread(self, broker_id=None, only_tradable=True, include_public=True,
                                   include_own_manual=False):
        """
        Returns the difference of the sell and buy front prices

        :param broker_id: optional filter on the broker ids of the orders
        :type broker_id: str
        :param only_tradable: optional - if True, only those orders are counted where order.is_tradable == True
        :type only_tradable: bool
        :param include_public: optional - if True, the public orders are included within the calculation, otherwise
                               the public orders are not included
        :type include_public: bool
        :param include_own_manual: optional - if True, the manual orders but not autoTRADER orders are included within
                                   the calculation, otherwise the manual orders are not included
        :type include_own_manual: bool
        :return: The difference of the sell and buy front prices
        :rtype: float or None
        """
        sell_front_price = self.current_front_price(COMMON.Direction.sell, broker_id=broker_id,
                                                    only_tradable=only_tradable, include_public=include_public,
                                                    include_own_manual=include_own_manual)
        buy_front_price = self.current_front_price(COMMON.Direction.buy, broker_id=broker_id,
                                                   only_tradable=only_tradable, include_public=include_public,
                                                   include_own_manual=include_own_manual)
        if sell_front_price is None or buy_front_price is None:
            return None
        else:
            return UTIL.round_float(sell_front_price - buy_front_price)

    def _front_price_by_index(self, delivery_area_id, direction, index=-1, broker_id=None):
        """
        Returns the "index-th" maximal buy, or the minimal sell price of public orders, based on direction.
        Normally index is a negative number. By default it's -1 meaning the last (current) front value.
        It means the order number in the ascending list in time, which contains the actual extreme values at that time.

        # WARNING: we can not always guarantee the correct history in special edge cases,
        e.g. when public order turns out to be an own order and the public gets removed,
        but actually there was a better public order in that time which we did not save

        :param direction: direction of the orders under check
        :type direction: str, member of :class:`COMMON.Direction`
        :param index: which max-min value do we need back in time from "last_front_..._orders" buffer
        :type index: int
        :param broker_id: optional filter on the broker ids of the orders
        :type broker_id: str
        :return: current front price
        :rtype: float or None
        """
        try:
            indicator = self._product.orders.indicators(delivery_area_id)
            if not broker_id:
                if direction == COMMON.Direction.buy:
                    ret_val = tuple(indicator.last_front_buy_orders[index])[-1].price
                else:
                    ret_val = tuple(indicator.last_front_sell_orders[index])[-1].price
            else:
                if direction == COMMON.Direction.buy:
                    ret_val = tuple(indicator.last_front_buy_orders_by_broker_id[broker_id][index])[-1].price
                else:
                    ret_val = tuple(indicator.last_front_sell_orders_by_broker_id[broker_id][index])[-1].price
            return ret_val
        except Exception:
            return None

    def current_front_buy_price(self, broker_id=None):
        """Returns the maximal price of buy orders, only includes tradable

        :param broker_id: optional filter on the broker ids of the orders
        :type broker_id: str or None
        :rtype: float or None
        """
        prices = list()
        for market_area in self._market_areas:
            tmp_price = self._front_price_by_index(market_area, COMMON.Direction.buy, -1, broker_id=broker_id)
            if tmp_price is not None:
                prices.append(tmp_price)
        return max(prices) if prices else None

    def current_front_sell_price(self, broker_id=None):
        """Returns the minimal price of sell orders, only includes tradable

        :param broker_id: optional filter on the broker ids of the orders
        :type broker_id: str
        :rtype: float or None
        """
        prices = list()
        for market_area in self._market_areas:
            tmp_price = self._front_price_by_index(market_area, COMMON.Direction.sell, -1, broker_id=broker_id)
            if tmp_price is not None:
                prices.append(tmp_price)
        return min(prices) if prices else None

    @property
    def strategy_id(self):
        return self._strategy_id

    @staticmethod
    def create_order_filter(direction, include_public, include_own_manual):
        """
        Function for creating the order filter according to specified parameters

        :param direction: direction of the orders under check
        :type direction: str, member of :class:`COMMON.Direction`
        :param include_public: optional - if True, the public orders are included within the calculation, otherwise
                               the public orders are not included
        :type include_public: bool
        :param include_own_manual: optional - if True, the manual orders but not autoTRADER orders are included within
                                   the calculation, otherwise the manual orders are not included
        :type include_own_manual: bool
        :return: the order filter expression for the OrderBook.get(...) method
        :rtype: string
        """
        return CommingledView._order_filter_mapping[(direction, include_public, include_own_manual)]

    def get_current_public_order_ids(self, direction):
        """Retrieve all ids of current public orders on the views area and for the given direction

        :param direction: public order direction
        :return: list[str]
        """
        ids = []
        for area in self._market_areas:
            ids.extend(self._product.orders.get_public_order_ids(area, direction))
        return ids


def _summarize_price_level(orders):
    """ Helper function for special calculations, add quantities together which have the same price

    additionally, remove the quantities of own orders on the same price levels,
    to avoid own orders influencing the price finding

    Sometimes, own orders in the public orderbook can only be identified by the price.

    :type orders: List[autotrader_core.exchange_trading.PublicOrder
                       or autotrader_core.exchange_trading.OwnOrder
                       or autotrader_core.exchange_trading.ComTraderOrder]
    :rtype: List[Tuple[float, float]]
    """
    # fill orders
    price_levels = collections.defaultdict(float)
    for o in orders:
        price_levels[UTIL.round_float(o.price)] += o.quantity
    return list(price_levels.items())


class TradeStatistics(object):
    """ Container class for a particular view facilitating the access to public trade metrics. """

    def __init__(self, vwap=None, low_price=None, high_price=None, first_price=None,
                 last_price=None, last_change=None, volume_buy=None, volume_sell=None):
        self.vwap = vwap
        self.low_price = low_price
        self.high_price = high_price
        self.first_price = first_price
        self.last_price = last_price
        self.last_change = last_change
        self.volume_buy = volume_buy
        self.volume_sell = volume_sell

        self.all_metrics = COMMON.TradeStatisticsMetric.__slots_container_py2__

    def __repr__(self):
        return "TradeStatistics({})".format(
            ", ".join(["{}={}".format(m, getattr(self, m)) for m in sorted(self.all_metrics)])
        )


if __name__ == "__main__":
    raise RuntimeError("This module should not be directly executed")  # pragma: no cover
