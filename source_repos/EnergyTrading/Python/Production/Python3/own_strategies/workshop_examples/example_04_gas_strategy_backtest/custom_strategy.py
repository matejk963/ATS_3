#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""Simple Gas strategy to Demo Unit Tests"""
import collections

import autotrader_lib.cet_util as CETUTIL
import autotrader_lib.common as COMMON
import autotrader_core.strategy as STRAT
import autotrader_core.strategy_utils as SU
import autotrader_core.exchange_trading as APITR

import logging
from six.moves import range

# # available from version V1.106
# from autotrader_synthetic.local_view import LocalView

log = logging.getLogger('autotrader.example_04_gas_strategy_backtest')

SELL_SLOTNAME = "sell_slot"
BUY_SLOTNAME = "buy_slot"
TRAYPORT_BROKER_ID = COMMON.Broker.eexs
Property = collections.namedtuple("property", ["min_quantity", "price_tick", "qty_tick", "unit", "name"])


class CustomStrategy(STRAT.GasStrategy):
    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        # used for aggregations
        self.smallest_timestep = COMMON.HOUR

        # pass strategy logger to base, to show distinct handle
        self.log = log
        # keep info about delivery area
        self.delivery_area_id = None

        # trayport broker has to be defined
        self.broker_id = TRAYPORT_BROKER_ID

        # and we need to define their update ourselves
        self.strategy_position_tradable_position_long = STRAT.StrategyTimeSeries()
        self.strategy_position_tradable_position_short = STRAT.StrategyTimeSeries()

        self.strategy_price_purchase = STRAT.StrategyTimeSeries()
        self.strategy_price_sales = STRAT.StrategyTimeSeries()

        # dictionary to keep track of traded amounts
        self.traded = {}

    def _get_traded_amount(self, start_ts, end_ts):
        """get traded amount per timestep

        :type start_ts: int
        :type end_ts: int
        :return: dict[int, float]
        """
        # overlapping products
        products = self.exchange.products.get_overlapping_with_timerange(start_ts, end_ts)
        net_traded = collections.defaultdict(float)
        for p in products:
            own_trades = p.trades.get(
                delivery_area=self.delivery_area_id,
                trade_filter=COMMON.TradeFilter.own,
                portfolio_key=self.strategy_id
            )
            traded_sell = sum(t.quantity for t in own_trades if t.direction == COMMON.Direction.sell)
            traded_buy = sum(t.quantity for t in own_trades if t.direction == COMMON.Direction.buy)
            net_val = round(traded_buy - traded_sell, SU.PREC_DIGITS)
            for ts in range(p.delivery_start, p.delivery_end, self.smallest_timestep):
                net_traded[ts] += net_val
        return net_traded

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
        key = "{}_{}_{}".format(broker_id, instrument_id, product_id)
        area_property = self.autotrader.trayport.trayport_areas[instrument_id]
        try:
            properties = self.autotrader.trayport.trayport_properties[key]
            min_quantity = properties.min_quantity
            price_tick = properties.price_tick
            qty_tick = properties.qty_tick
        except KeyError:
            self.error_log("Could not find trayport properties for key: {}".format(key))
            raise
        return Property(min_quantity=min_quantity, price_tick=price_tick, qty_tick=qty_tick,
                        unit=getattr(area_property, 'unit'), name=getattr(area_property, 'inst_name', None))

    def custom_act(self, log_data, timestamp, products=None):  # type: (dict, float, list[APITR.Product]) -> None
        """when act is called, mostly reacting to changes in products

        :type log_data: dict
        :type timestamp: float
        :type products: list[APITR.Product]
        :return:
        """

        self.debug_log(text="Running")

        #############################
        # Act on product one by one #
        #############################
        if not products:
            return

        min_start_ts = min(p.delivery_start for p in products)
        max_end_ts = max(p.delivery_end for p in products)
        self.traded = self._get_traded_amount(min_start_ts, max_end_ts)

        for product in sorted(products, key=lambda p: p.delivery_start):
            self.act_for_product(product=product, timestamp=timestamp)

        # export values to MongoDB
        self.api_export_timeseries({
            "traded": ("Net-Traded", "MW", "MW", COMMON.HOUR,
                       {ts: self.traded[ts] for ts in
                        range(min_start_ts, max_end_ts, COMMON.HOUR)})
        })

        self.api_export_timeseries({
            "pos_long": ("pos_long", "MW", "MW", COMMON.HOUR,
                         {ts: self.strategy_position_tradable_position_long[(ts, ts + COMMON.HOUR)] for ts in
                          range(min_start_ts, max_end_ts, COMMON.HOUR)})
        })

        self.api_export_timeseries({
            "pos_short": ("pos_short", "MW", "MW", COMMON.HOUR,
                          {ts: self.strategy_position_tradable_position_long[(ts, ts + COMMON.HOUR)] for ts in
                           range(min_start_ts, max_end_ts, COMMON.HOUR)})
        })

    def custom_act_for_product(self, log_data, product, timestamp, *args, **kwargs):
        """Get open position for product and place orders for that open position"""
        self.debug_log(text="Act for product", product=product)

        #################################
        # Filter only tradable products #
        #################################
        if not product.is_tradable(timestamp, self.delivery_area_id):
            start_ts, end_ts, state = product.trading_phase(self.delivery_area_id)
            self.debug_log(text="skip untradable product. state: {}, interval: {}-{}, now:{}".format(
                state,
                CETUTIL.utc_ts2cet_str(start_ts, True, True),
                CETUTIL.utc_ts2cet_str(end_ts, True, True),
                CETUTIL.utc_ts2cet_str(timestamp, True, True),
            ),
                product=product
            )

        ###################################################
        # get trayport properties for instrument and area #
        ###################################################
        properties = self.get_trayport_properties(product_id=product.product_id)
        tick_size = properties.price_tick
        qty_tick = properties.qty_tick
        min_quantity = properties.min_quantity
        unit = properties.unit
        name = properties.name
        self.debug_log(
            text="Act for product (instrument: {} ({}), tick_size:{}, qty_tick:{}, min_quantity:{}, unit:{})".format(
                name, self.delivery_area_id, tick_size, qty_tick, min_quantity, unit),
            product=product
        )

        #####################################
        # find left over positions to trade #
        #####################################

        # get traded amount
        traded_vals = [self.traded[ts] for ts in range(product.delivery_start, product.delivery_end, COMMON.QUARTER)]
        most_bought = max(0, max(traded_vals))
        most_sold = min(0, min(traded_vals))
        common_traded = most_bought + most_sold
        common_traded = round(common_traded, 2)

        # get positions set in periotheus (or by REST API)
        product_interval = (product.delivery_start, product.delivery_end)
        long_target = self.strategy_position_tradable_position_long.get(product_interval, 0.) or 0.
        short_target = self.strategy_position_tradable_position_short.get(product_interval, 0.) or 0.
        open_position = short_target - long_target

        # calculate left over
        rest = round(open_position - common_traded, SU.PREC_DIGITS)

        ##############################################################
        # create slots with price and quantity rounded to tick sizes #
        ##############################################################

        # in contrast to power intraday, we have to set the broker_id in this case, to use the correct broker for
        # order placement
        buy_slot = STRAT.PositionSlot(BUY_SLOTNAME, COMMON.Direction.buy, quantity=0, price=0, broker_id=self.broker_id)
        sell_slot = STRAT.PositionSlot(
            SELL_SLOTNAME, COMMON.Direction.sell, quantity=0, price=0, broker_id=self.broker_id
        )

        # check min quantity for this exchange:

        if abs(rest) < properties.min_quantity:
            self.debug_log(text="Rest is: {}, but minimum quantity is: {}".format(rest, properties.min_quantity))
        else:
            if rest > 0:
                buy_slot.quantity = SU.load_rounder(rest, properties.min_quantity, properties.qty_tick)
                buy_slot.price = self.strategy_price_purchase.get(product_interval)

                if buy_slot.price is not None:
                    buy_slot.price = SU.stepsize_rounder(buy_slot.price, properties.price_tick)

            elif rest < 0:
                sell_slot.quantity = SU.load_rounder(-rest, properties.min_quantity, properties.qty_tick)
                sell_slot.price = self.strategy_price_sales.get(product_interval)
                if sell_slot.price is not None:
                    sell_slot.price = SU.stepsize_rounder(sell_slot.price, properties.price_tick)

        #############################################
        # found best public orders for this product #
        #############################################

        best_public_buy_price = None
        best_public_sell_price = None
        indicators = product.orders.indicators(self.delivery_area_id)
        if indicators:
            best_public_buy_price = indicators[0].mw_prices[0][0]
            best_public_sell_price = indicators[0].mw_prices[1][0]

        ##########################
        # check localview values #
        ##########################

        # # available for version > V1.106
        # localview = LocalView(product, self.delivery_area_id, self.strategy_id)
        # current_front_buy_price = localview.current_front_buy_price(self.broker_id)
        # current_front_sell_price = localview.current_front_sell_price(self.broker_id)
        #
        # traded_volume_buy = localview.traded_volume_buy(BUY_SLOTNAME)
        # traded_volume_sell = localview.traded_volume_sell(SELL_SLOTNAME)
        # exposed_order_volume_sell = localview.exposed_order_volume(SELL_SLOTNAME)
        # exposed_order_volume_buy = localview.exposed_order_volume(BUY_SLOTNAME)
        # otr = localview.otr()
        # current_front_price_spread = localview.current_front_price_spread(self.broker_id)
        # current_public_order_price_10MW_buy = localview.current_order_price(
        #     COMMON.Direction.buy, at_volume=10, broker_id=self.broker_id)
        # current_public_order_price_10MW_sell = localview.current_order_price(
        #     COMMON.Direction.sell, at_volume=10, broker_id=self.broker_id)
        #
        # localview.build_trade_statistics(broker_id=self.broker_id)
        # _trade_statistics = localview._trade_statistics
        #
        # msg = ("current_front_buy_price:{}, current_front_sell_price:{}, traded_volume_buy:{}, "
        #        "traded_volume_sell:{}, exposed_order_volume:{}, exposed_order_volume:{}, otr:{}, "
        #        "current_front_price_spread:{}, current_public_order_price_10MW_buy:{}, "
        #        "current_public_order_price_10MW_sell:{}, _trade_statistics: {}"
        #        .format(
        #            current_front_buy_price, current_front_sell_price,
        #            traded_volume_buy, traded_volume_sell,
        #            exposed_order_volume_sell, exposed_order_volume_buy, otr,
        #            current_front_price_spread, current_public_order_price_10MW_buy,
        #            current_public_order_price_10MW_sell,
        #            _trade_statistics
        #        )
        #       )
        # self.debug_log(text="LocalView: {}".format(msg), product=product)

        ##############################################
        # place slots with info #
        ##############################################

        # place buy slot
        buy_slot.info = (
            "buy_state:normal||trd:{:.1f}||net_target_pos:{}||rest:{}||{}".format(
                common_traded, open_position, rest, po_slot_info(best_public_buy_price, best_public_sell_price)
            )
        )

        slot_responses = self.place_slots({}, product, timestamp, self.delivery_area_id,
                                          [buy_slot], [],
                                          limit_minimum_sales_price=-9999,
                                          limit_maximum_purchase_price=9999,
                                          execmode=COMMON.InternalExecutionMode.exchange_base_price)

        self.debug_log(text="Buy Slot Placement Results: {}".format(slot_responses), product=product)

        sell_slot.info = (
            "sell_state:normal||trd:{:.1f}||net_target_pos:{}||rest:{}||{}".format(
                common_traded, open_position, rest, po_slot_info(best_public_buy_price, best_public_sell_price)
            )
        )

        slot_responses = self.place_slots({}, product, timestamp, self.delivery_area_id,
                                          [sell_slot], [],
                                          limit_minimum_sales_price=-9999,
                                          limit_maximum_purchase_price=9999,
                                          execmode=COMMON.InternalExecutionMode.exchange_base_price)

        self.debug_log(text="Sell Slot Placement Results: {}".format(slot_responses), product=product)

    def on_strategy_update(self, strategy_json):
        """The json is sent from Periotheus or from REST API (strategy steering call)

        strategy json comes unchanged -> can call anything
        api/strategy_steering

        :type strategy_json: dict
        :rtype: None
        """

        super(CustomStrategy, self).on_strategy_update(strategy_json)
        # on strategy update sets the self.delivery_areas from the passed json
        self.delivery_area_id = self.delivery_areas[0]

        self.strategy_position_tradable_position_long = STRAT.mk_strategy_tr_dict(
            strategy_json[COMMON.StrategyJsonKey.TS.pos_sell], "min"
        )
        self.strategy_position_tradable_position_short = STRAT.mk_strategy_tr_dict(
            strategy_json[COMMON.StrategyJsonKey.TS.pos_buy], "min"
        )

        self.strategy_price_purchase = STRAT.mk_strategy_tr_dict(
            strategy_json[COMMON.StrategyJsonKey.TS.price_buy], "min"
        )
        self.strategy_price_sales = STRAT.mk_strategy_tr_dict(
            strategy_json[COMMON.StrategyJsonKey.TS.price_sell], "max"
        )

    def custom_on_order_book_update(self, orders, timestamp):
        """On Order Book

        :type orders: list[APITR.Order]
        :type timestamp: float
        :rtype: None
        """
        self.act(timestamp, set(o.product for o in orders))

    def custom_on_trade_update(self, trades, timestamp):
        """On Own Trades only

        :type trades: list[APITR.Trade]
        :type timestamp: float
        :rtype: None
        """
        pass

    def custom_on_public_trade_update(self, trades, timestamp):
        """On Public Trades only

        :type trades: list[APITR.Trade]
        :type timestamp: float
        :rtype: None
        """
        pass

    def custom_on_products_update(self, products, timestamp):
        """Only when exchange sends a messages about a product changing

        E.g. change from active to inactive, trading interval, ...

        :type products: list[APITR.Product]
        :type timestamp: float
        :rtype: None
        """
        self.act(timestamp, products)

    def custom_on_products_queue(self, products, timestamp):
        """Replacement for timer

        Products get queued by urgency via ProductsPriorityQueue

        This is the best entrypoint to call code periodically

        e.g. with
        self.act(timestamp, products)

        :type products: list[APITR.Product]
        :type timestamp: float
        :rtype: None
        """
        pass

    def custom_on_timer(self, timestamp):
        pass  # products queue is enough


def po_slot_info(best_public_buy_price, best_public_sell_price):
    """Helper to print slot information

    :type best_public_buy_price: float or None
    :type best_public_sell_price: float or None
    :return: str
    """
    return "".join([
        "fronts:",
        "{:.1f}".format(best_public_buy_price or 0.) if best_public_buy_price is not None else "None",
        "//",
        "{:.1f}".format(best_public_sell_price or 0.) if best_public_sell_price is not None else "None",
    ])
