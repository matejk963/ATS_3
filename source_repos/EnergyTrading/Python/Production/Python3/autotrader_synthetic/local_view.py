# coding=utf-8
from __future__ import absolute_import
import autotrader_lib.common as COMMON
import autotrader_core.exchange_trading as APITR
import autotrader_synthetic.commingled_view as COMMVIEW
import autotrader_lib.util as UTIL
from six.moves import range


class LocalView(COMMVIEW.CommingledView):
    """
    A LocalView is a special case of CommingledView for single market area
    """

    def __init__(self, product, market_area, strategy_id):
        """

        :param product: The product object for which we would like to create the local view
        :type product: autotrader_core.exchange_trading.Product
        :param market_area: The market area for which this local view should be created
        :type market_area: str
        :param strategy_id: The id of the strategy within which this local view is created
        :type strategy_id: str
        """
        super(LocalView, self).__init__(product, [market_area], strategy_id)
        self._market_area = market_area
        # CACHED DATA: The LocalView objects have to be thrown away after each call to strategy_act,
        # to make sure we don't keep a cache with stale data.
        self._exposed_order_volume = {}
        self._traded_volume_buy = {}
        self._traded_volume_sell = {}
        self._otr = None

    def __repr__(self):
        return "LocalView(product='{}({})', market_area={}, strategy_id={})\nStatistics: {}".format(
            self._product.name, self._product.product_id, self._market_area, self._strategy_id, self._trade_statistics)

    def exposed_order_volume(self, slot_name):
        """ Indicator providing the total volume of own orders on the market with the defined slot name

        :param slot_name: the name of the slot for the orders we wish to sum the volume of
        :type slot_name: str
        :return: Returns the total volume of all own orders with the defined slot name
        :rtype: float
        """
        if (self._strategy_id, slot_name) not in self._exposed_order_volume:
            # We can have at most 1 order under normal circumstances.
            orders = self._product.orders.get(delivery_area_id=self._market_area,
                                              order_filter=COMMON.OrderFilter.own,
                                              portfolio_key=self._strategy_id)
            volume = sum(order.quantity for order in orders if order.tags.get("strategy_slot", "") == slot_name)
            self._exposed_order_volume[(self._strategy_id, slot_name)] = volume
        return self._exposed_order_volume[(self._strategy_id, slot_name)]

    def traded_volume_buy(self, slot_name, timerange=None):
        """ Indicator returning the total BUY volume of own trades on the market with the defined slot name

        :param slot_name: the name of the slot for the orders we wish to sum the volume of
        :type slot_name: str
        :param timerange: optional, tuple containing 2 timestamps, filtering by trade execution
        :type timerange: tuple with 2 int elements
        :return: Returns the total volume of all BUY own trades with the defined slot name
        :rtype: float
        """
        if (self._strategy_id, slot_name, timerange) not in self._traded_volume_buy:
            buy_trades = self._product.trades.get(buy_delivery_area=self._market_area,
                                                  trade_filter=COMMON.TradeFilter.own_buy,
                                                  portfolio_key=self._strategy_id,
                                                  timerange=timerange)
            buy_qty = sum(trade.quantity for trade in buy_trades if trade.tags.get("strategy_slot", "") == slot_name)
            self._traded_volume_buy[(self._strategy_id, slot_name, timerange)] = buy_qty
        return self._traded_volume_buy[(self._strategy_id, slot_name, timerange)]

    def traded_volume_sell(self, slot_name, timerange=None):
        """ Indicator returning the total SELL volume of own trades on the market with the defined slot name

        :param slot_name: the name of the slot for the orders we wish to sum the volume of
        :type slot_name: str
        :param timerange: optional, tuple containing 2 timestamps, filtering by trade execution
        :type timerange: tuple with 2 int elements
        :return: Returns the total volume of all SELL own trades with the defined slot name
        :rtype: float
        """
        if (self._strategy_id, slot_name, timerange) not in self._traded_volume_sell:
            sell_trades = self._product.trades.get(sell_delivery_area=self._market_area,
                                                   trade_filter=COMMON.TradeFilter.own_sell,
                                                   portfolio_key=self._strategy_id,
                                                   timerange=timerange)
            sell_qty = sum(trade.quantity for trade in sell_trades if trade.tags.get("strategy_slot", "") == slot_name)
            self._traded_volume_sell[(self._strategy_id, slot_name, timerange)] = sell_qty
        return self._traded_volume_sell[(self._strategy_id, slot_name, timerange)]

    @property
    def _current_indicator(self):
        """The latest indicator object of the Product for self.market_area

        :return: The latest indicator
        :rtype: autotrader_core.exchange_trading.OrderBookIndicator or None
        """
        return self._historic_indicator(0)

    def _historic_indicator(self, steps_in_past):
        indicators = self._product.orders.indicators(self._market_area)
        if indicators and len(indicators) > steps_in_past:
            return indicators[steps_in_past]
        return None

    def _historic_spread(self, steps_in_past):
        """ Indicator returning the spread between BUY and SELL public orders, the defined number of steps in the past

        WARNING: Does not work on exchanges where public orders of the same price are combined (EEX, ICE)

        :param steps_in_past: How many 10 seconds steps in the past we want the spread. 0 means current spread,
                              6 means roughly 60 seconds in the past.
        :type steps_in_past: int
        :return: Returns the difference between (SPREAD) front of BUY and SELL sides at some steps in the past
        :rtype: float
        """
        indicator = self._historic_indicator(steps_in_past)
        if indicator:
            return indicator.mw_prices[1][0] - indicator.mw_prices[0][0]
        else:
            return None

    def _get_aggregated_historic_spread(self, historic_spread_seconds, method=COMMON.HistorySpreadMethod.get_max):
        """ Indicator providing an aggregated historic spread, by defined seconds in the past,
        using a defined aggregation method (calculation is based on public orders)

        WARNING: Does not work on exchanges where public orders of the same price are combined (EEX, ICE)

        # index 0: x seconds  (0)
        # index 1: x seconds  (0, 10)
        # index 2: 10 + x seconds  (10, 20)
        # index 3: 20 + x seconds  (20, 30)

        :param historic_spread_seconds: Number of seconds in the past to create the aggregation window
        :type historic_spread_seconds: int
        :param method: The method by which to aggregate ("max" or "avg" or "min", default: "max")
        :type method: str of :class:`COMMON.HistorySpreadMethod`
        :return: None if no spread history is present, otherwise return max or avg of spread
        :rtype: NoneType or float
        """
        # Historic data is stored in a 10 seconds raster. So go from seconds to 10 seconds
        steps = int(round(historic_spread_seconds / APITR.INDICATOR_HISTORY_TIMESTEP, 0))
        historic_spreads = [self._historic_spread(step) for step in range(1, steps)]
        historic_spreads = [spread for spread in historic_spreads if spread is not None]
        if len(historic_spreads) == 0:
            return None

        if method == COMMON.HistorySpreadMethod.get_avg:
            historic_spread = sum(historic_spreads) / len(historic_spreads)
        elif method == COMMON.HistorySpreadMethod.get_min:
            historic_spread = min(historic_spreads)
        else:
            historic_spread = max(historic_spreads)

        return historic_spread

    def previous_front_buy_price(self, broker_id=None):
        """Returns the price of buy order, which was maximal before the current maximum

        # WARNING: in rare edge cases might give wrong historic data

        :param broker_id: optional filter on the broker ids of the orders
        :type broker_id: str
        :rtype: float or None
        """
        return self._front_price_by_index(self._market_areas[0], COMMON.Direction.buy, -2, broker_id=broker_id)

    def previous_front_sell_price(self, broker_id=None):
        """Returns the price of sell order, which was minimal before the current minimum

        # WARNING: in rare edge cases might give wrong historic data

        :param broker_id: optional filter on the broker ids of the orders
        :type broker_id: str
        :rtype: float or None
        """
        return self._front_price_by_index(self._market_areas[0], COMMON.Direction.sell, -2, broker_id=broker_id)

    def current_front_order_price_change(self, direction, broker_id=None):
        """Returns the difference between the current and previous front price of public orders filtered on direction

        # WARNING: in rare edge cases might give wrong result due to faulty history data from exchange

        :param broker_id: optional filter on the broker ids of the orders
        :type broker_id: str
        :param direction: direction of the public orders under check
        :type direction: str, member of :class:`COMMON.Direction`
        :return: current front price
        :rtype: float or None
        """
        current_front_price = self._front_price_by_index(self._market_areas[0], direction, -1, broker_id=broker_id)
        previous_front_price = self._front_price_by_index(self._market_areas[0], direction, -2, broker_id=broker_id)
        if current_front_price is None or previous_front_price is None:
            return None
        else:
            return UTIL.round_float(current_front_price - previous_front_price)

    @property
    def market_area(self):
        """Property that stores the Instrument ID on Trayport

        :return: Instrument ID on Trayport
        :rtype: str
        """
        return self._market_area

    @property
    def product_id(self):
        """Property that stores the ID of the product

        :return: Product ID for the local view
        :rtype: str
        """
        return self._product.product_id


if __name__ == "__main__":
    raise RuntimeError("This module should not be directly executed")  # pragma: no cover
