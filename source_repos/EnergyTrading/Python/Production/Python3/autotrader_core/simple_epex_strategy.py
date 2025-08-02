#!/usr/bin/python3
# -*- coding: utf-8 -*-

from __future__ import absolute_import
import autotrader_lib.common as COMMON
import autotrader_core.strategy as strategy
import logging

log = logging.getLogger("autotrader.simple_epex_strategy")


class SimpleEpexStrategy(strategy.Strategy):
    """Is the base class for the simple strategy definition.

    Simple strategies define their behaviour only by the get_slots function
    which determines the strategies order wishes in every strategy execution.
    The get_slots() function is to be overwritten in descendants of SimpleEpexStrategy.
    """

    def __init__(self, *args, **kwargs):
        super(SimpleEpexStrategy, self).__init__(*args, **kwargs)
        self.position = strategy.Position()

        self.strategy_position_tradable_position_long = None  # timeseries
        self.strategy_position_tradable_position_short = None  # timeseries
        self.strategy_price_purchase_immediate_vesting = None  # timeseries
        self.strategy_price_sales_immediate_vesting = None  # timeseries
        self.strategy_limit_maximum_sales_volume = None  # timeseries
        self.strategy_limit_maximum_purchase_volume = None  # timeseries
        self.strategy_limit_maximum_purchase_price = None  # timeseries
        self.strategy_limit_minimum_sales_price = None  # timeseries
        self.strategy_price_minimum_spread_buyback = None  # timeseties
        self.strategy_price_purchase = None
        self.strategy_price_sales = None

    def get_slots(self, log_data, product, timestamp, position_long, position_short,
                  traded_sell, traded_buy, average_price,
                  product_interval, seconds_traded, seconds_left, indicators,
                  limit_maximum_sales_volume, limit_maximum_purchase_volume, limit_maximum_purchase_price,
                  limit_minimum_sales_price, purchase_immediate_vesting_price, sales_immediate_vesting_price,
                  price_purchase, price_sales,
                  price_minimum_spread_buyback, maximum_imbalance_on_market_closure,
                  maximum_order_book, trading_end_before_market_closure, **kwargs):
        """
        :param product: Product of the actual call
        :param timestamp: Current timestamp as unix timestamp
        :param position_long: Definition of the long position from Periotheus
        :param position_short: Definition of the short position from Periotheus
        :param traded_sell: Already traded volume for strategy
        :param traded_buy: Already traded volume for strategy
        :param average_price: Average price of all own trades so far
        :param product_interval: Delivery duration in seconds
        :param seconds_traded: Number of seconds, this product can be traded already
        :param seconds_left: Number of seconds, this product can still be traded until closing of trading
        :param indicators: :class:`api.OrderBookIndicator` object for current product
        :param limit_maximum_sales_volume: Maximum volume from Periotheus
        :param limit_maximum_purchase_volume: Maximum volume from Periotheus
        :param limit_maximum_purchase_price: Maximum purchase price from Periotheus
        :param limit_minimum_sales_price: Minimum sales price from Periotheus
        :param purchase_immediate_vesting_price: Immediate vesting price for purchase
        :param sales_immediate_vesting_price: Immediate vesting price for sales
        :param price_purchase: Starting price for purchase
        :param price_sales: Starting price for sales
        :param price_minimum_spread_buyback: Minimum buyback spread setting from Periotheus
        :param maximum_imbalance_on_market_closure: same setting from Periotheus
        :param maximum_order_book: Maximum exposure in order book ('Iceberg')
        :param trading_end_before_market_closure: Setting from Periotheus in minutes
        :returns: A list of :class:`strategy.PositionSlot` and the internal execution mode of these slots
        """

        return [], COMMON.InternalExecutionMode.default

    def custom_act_for_product(self, log_data, product, timestamp,
                               position_long, position_short,
                               traded_sell, traded_buy,
                               average_price):

        duration = product.duration
        if duration not in (900, 3600) and product.exchange in (COMMON.Exchange.epex, COMMON.Exchange.nordpool):
            return

        stats = []
        stats.append("{:0.1f}_{:0.1f}_{:0.1f}_{:0.1f}".format(position_long, position_short, traded_sell, traded_buy))

        log_data.update({"tradeable_position": position_long - position_short,
                         "traded_position": traded_sell - traded_buy,
                         "slots": []})

        product_interval = (product.delivery_start, product.delivery_end)

        trading_start, trading_end, unused_trading_state = product.trading_phase(self.delivery_area_id)
        # in case the trading_end is in any of the market halt intervals,
        # shift the trading_end to the begin of the corresponding
        # market halt interval

        trading_end_in_halt = self.check_epex_timestamp_halt(trading_end)
        if trading_end_in_halt:
            trading_end = trading_end_in_halt[0]

        # TODO: sollte hier nicht auf den Produktstatus geschaut werden (active/hibernated ..) ?
        if not (trading_start <= timestamp <= trading_end):
            return

        seconds_left = trading_end - timestamp
        seconds_traded = timestamp - trading_start

        if seconds_left <= 0:
            return

        if seconds_traded <= 0:
            return

        indicators = product.orders.indicators(self.delivery_area_id)

        if not indicators:
            return

        indicators = indicators[0].mw_prices

        limit_maximum_sales_volume, limit_maximum_purchase_volume, limit_maximum_purchase_price, \
            limit_minimum_sales_price, purchase_immediate_vesting_price, sales_immediate_vesting_price, \
            price_purchase, price_sales, price_minimum_spread_buyback = self.get_strategy_timerow_settings([
                (COMMON.StrategyJsonKey.TS.limit_sell_vol, 0.),
                (COMMON.StrategyJsonKey.TS.limit_buy_vol, 0.),
                (COMMON.StrategyJsonKey.TS.limit_buy_price, None),
                (COMMON.StrategyJsonKey.TS.limit_sell_price, None),
                (COMMON.StrategyJsonKey.TS.price_imm_buy, None),
                (COMMON.StrategyJsonKey.TS.price_imm_sell, None),
                (COMMON.StrategyJsonKey.TS.price_buy, None),
                (COMMON.StrategyJsonKey.TS.price_sell, None),
                (COMMON.StrategyJsonKey.TS.price_min_spread_buyback, None)], product_interval)

        maximum_imbalance_on_market_closure = self.strategy_settings["maximum_imbalance_on_market_closure"] or 0.
        maximum_order_book = abs(self.strategy_settings["maximum_order_book"] or 1000.)

        trading_end_before_market_closure = int(self.strategy_settings["trading_end_before_market_closure"] or 0)

        slots, execmode = self.get_slots(
            log_data, product, timestamp, position_long, position_short, traded_sell, traded_buy, average_price,
            product_interval, seconds_traded, seconds_left, indicators, limit_maximum_sales_volume,
            limit_maximum_purchase_volume, limit_maximum_purchase_price, limit_minimum_sales_price,
            purchase_immediate_vesting_price, sales_immediate_vesting_price, price_purchase, price_sales,
            price_minimum_spread_buyback, maximum_imbalance_on_market_closure, maximum_order_book,
            trading_end_before_market_closure
        )

        self.place_slots(
            log_data, product, timestamp, self.delivery_area_id, slots, stats, limit_minimum_sales_price,
            limit_maximum_purchase_price, execmode
        )

    def custom_act(self, log_data, timestamp, products=None):
        # get positions for every product
        if products is None:
            products = self.exchange.products.get_active_products(self.delivery_area_id)

        if not products:
            return

        for product in products:
            # products for collecting traded amounts
            traded_products = [
                p for p in self.exchange.products.get_all()
                if p.delivery_start == product.delivery_start and p.delivery_end == product.delivery_end
            ]
            product_interval = (product.delivery_start, product.delivery_end)
            own_trades = []
            for traded_product in traded_products:
                own_trades.extend(traded_product.trades.get(
                    delivery_area=self.delivery_area_id, trade_filter=COMMON.TradeFilter.own,
                    portfolio_key=self.strategy_id))
            traded_sell = sum(t.quantity for t in own_trades if t.direction == COMMON.Direction.sell)
            traded_buy = sum(t.quantity for t in own_trades if t.direction == COMMON.Direction.buy)
            if own_trades:
                average_price = sum(t.quantity * t.price for t in own_trades) / (traded_sell + traded_buy)
            else:
                average_price = None

            log_data.append(
                self.act_for_product(
                    product, timestamp,
                    self.strategy_position_tradable_position_long.get(product_interval, 0.) or 0.,
                    self.strategy_position_tradable_position_short.get(product_interval, 0.) or 0., traded_sell,
                    traded_buy, average_price
                )
            )

    def on_strategy_update(self, strategy_json):
        super(SimpleEpexStrategy, self).on_strategy_update(strategy_json)
        assert len(self.delivery_areas) == 1
        self.delivery_area_id = self.delivery_areas[0]
        self.strategy_position_tradable_position_long = strategy.mk_strategy_tr_dict(
            strategy_json[COMMON.StrategyJsonKey.TS.pos_sell], "min"
        )
        self.strategy_position_tradable_position_short = strategy.mk_strategy_tr_dict(
            strategy_json[COMMON.StrategyJsonKey.TS.pos_buy], "min"
        )
        self.strategy_price_purchase_immediate_vesting = strategy.mk_strategy_tr_dict(
            strategy_json[COMMON.StrategyJsonKey.TS.price_imm_buy], "min"
        )
        self.strategy_price_sales_immediate_vesting = strategy.mk_strategy_tr_dict(
            strategy_json[COMMON.StrategyJsonKey.TS.price_imm_sell], "max"
        )
        self.strategy_price_purchase = strategy.mk_strategy_tr_dict(
            strategy_json[COMMON.StrategyJsonKey.TS.price_buy], "min"
        )
        self.strategy_price_sales = strategy.mk_strategy_tr_dict(
            strategy_json[COMMON.StrategyJsonKey.TS.price_sell], "max"
        )
        self.strategy_price_minimum_spread_buyback = \
            strategy.mk_strategy_tr_dict(
                strategy_json[COMMON.StrategyJsonKey.TS.price_min_spread_buyback],
                "min_nonone")

    def is_market_halt(self, timestamp):
        timestamp_in_halt = self.check_epex_timestamp_halt(timestamp)
        if timestamp_in_halt:
            log.warning("markethalt set for strategy {}".format(self.strategy_id))
            return True
        else:
            return False

    def custom_on_order_book_update(self, orders, timestamp):
        if self.is_market_halt(timestamp):
            return
        products = set(o.product for o in orders)
        self.act(timestamp, products)

    def custom_on_trade_update(self, trades, timestamp):
        if self.is_market_halt(timestamp):
            return
        products = set(o.product for o in trades)
        self.act(timestamp, products)

    def custom_on_public_trade_update(self, trades, timestamp):
        pass

    def custom_on_products_queue(self, products, timestamp):
        if self.is_market_halt(timestamp):
            return
        self.act(timestamp, products)

    def custom_on_products_update(self, products, timestamp):
        pass

    def custom_on_timer(self, timestamp):
        # epex halt set -> stop
        if self.is_market_halt(timestamp):
            return
        self.act(timestamp)

    def custom_on_error(self, errors, timestamp):
        super(SimpleEpexStrategy, self).custom_on_error(errors, timestamp)
