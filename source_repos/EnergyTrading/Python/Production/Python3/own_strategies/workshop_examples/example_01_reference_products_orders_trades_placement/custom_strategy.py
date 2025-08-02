#!/usr/bin/python3
# -*- coding: utf-8 -*-

import logging

import autotrader_lib.common as COMMON
import autotrader_core.exchange_trading as APITR
import autotrader_core.strategy as STRAT
from autotrader_synthetic.local_view import LocalView

log = logging.getLogger('autotrader.example_01_reference_products_orders_trades_placement')

DEBUG = False


class CustomStrategy(STRAT.Strategy):
    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)

    def custom_act(self, log_data, timestamp, products=None):
        """when act is called, mostly reacting to changes in products

        :type log_data: dict
        :type timestamp: float
        :type products: list[APITR.Product]
        :return:
        """
        for product in products:
            # calling act_for_product is a good way to automatically make sure that:
            # - orders are removed and product is not traded if product duration is outside of validity range
            # - do not trade if product is not active on the area
            # - do not trade if we are already closer to the delivery start,
            #   than the a parameter allows (trading end before market closure)
            self.act_for_product(product, timestamp)

    def custom_act_for_product(self, log_data, product, timestamp, *args, **kwargs):
        """Act for single product

        :param log_data: additional log data to be used
        :type log_data: dict
        :param product: single product passed on this call
        :type product: APITR.Product
        :param timestamp: current timestamp
        :type timestamp: float
        :return: None
        """
        self.debug_log(text="Acting for single product", product=product)

        ##############
        # Indicators #
        ##############
        indicators = product.orders.indicators(
            delivery_area_id=self.delivery_areas[0]
        )  # type: APITR.OrderBookIndicators

        if indicators:
            # get current front buy price
            current_indicator = indicators[0]  # type: APITR.OrderBookIndicator
            buy_price_levels = current_indicator.mw_prices[0]
            front_buy_price = buy_price_levels[0]

            # get current front sell price
            front_sell_price = indicators[0].mw_prices[1][0]

            # get "10s ago" - front buy price
            if len(indicators) >= 2:
                indicator_10s_ago = indicators[1]
                buy_price_levels = indicator_10s_ago.mw_prices[0]
                buy_price_10s_ago = buy_price_levels[0]

            # > V1.106
            # last front sell orders
            last_front_sell_orders = indicators.last_front_sell_orders
            if DEBUG:
                print(("sells", [(o.creation_timestamp, o.price) for orders in last_front_sell_orders for o in orders]))
            # last front buy orders
            last_front_buy_orders = indicators.last_front_buy_orders
            if DEBUG:
                print(("buys", [(o.creation_timestamp, o.price) for orders in last_front_buy_orders for o in orders]))

        ######################
        # Orderbook Accessor #
        ######################

        # <V1.106
        own_buy_order_volume = product.orders.get_volume(
            delivery_area_id=self.delivery_areas[0],
            order_filter=COMMON.OrderFilter.own_buy,
            internal_id_filter=None,
            portfolio_key=self.strategy_id,
        )
        # get public orders
        public_orders = product.orders.get(
            delivery_area_id=self.delivery_areas[0],
            order_filter=COMMON.OrderFilter.public,
            portfolio_key=None,  # only if own orders
            broker_id=None,  # not used on EPEX
        )

        # >V1.106
        sell_price_at_13MW = product.orders.get_public_sell_price_at_min_volume(
            volume=13,
            delivery_area_id=self.delivery_areas[0]
        )

        buy_price_at_13MW = product.orders.get_public_buy_price_at_min_volume(
            volume=13,
            delivery_area_id=self.delivery_areas[0]
        )

        buy_depth = product.orders.get_public_order_depth(
            direction=COMMON.Direction.buy,
            delivery_area_id=self.delivery_areas[0]
        )

        sell_depth = product.orders.get_public_order_depth(
            direction=COMMON.Direction.sell,
            delivery_area_id=self.delivery_areas[0]
        )

        # get public orders
        public_orders = product.orders.get(
            delivery_area_id=self.delivery_areas[0],
            order_filter=COMMON.OrderFilter.public,
            portfolio_key=None,  # only if own orders
            broker_id=None,  # not used on EPEX
            only_tradable=False  # not used on EPEX
        )

        own_buy_order_volume = product.orders.get_volume(
            delivery_area_id=self.delivery_areas[0],
            order_filter=COMMON.OrderFilter.own_buy,
            internal_id_filter=None,
            portfolio_key=self.strategy_id,
            broker_id=None,  # for trayport products
            only_tradable=False  # for trayport products
        )

        ###################
        # Trades Accessor #
        ###################

        own_trades = product.trades.get(
            buy_delivery_area=None,  # only used if looking for direction
            sell_delivery_area=None,  # only used if looking for direction
            delivery_area=self.delivery_areas[0],
            portfolio_key=self.strategy_id,
            trade_filter=COMMON.TradeFilter.own,
            timerange=None  # not used now
        )

        total_volume = product.trades.get_volume(
            delivery_area_id=self.delivery_areas[0],
            trade_filter=COMMON.TradeFilter.own,
            portfolio_key=self.strategy_id,
        )

        net_volume = product.trades.get_balance(
            delivery_area_id=self.delivery_areas[0],
            portfolio_key=self.strategy_id,
        )

        ##########################
        # check localview values #
        ##########################

        # available for version > V1.106
        self.broker_id = COMMON.Broker.eexs  # example broker

        localview = LocalView(product, self.delivery_area_id, self.strategy_id)
        current_front_buy_price = localview.current_front_buy_price(self.broker_id)
        current_front_sell_price = localview.current_front_sell_price(self.broker_id)

        traded_volume_buy = localview.traded_volume_buy("buy")
        traded_volume_sell = localview.traded_volume_sell("sell")
        exposed_order_volume_sell = localview.exposed_order_volume("buy")
        exposed_order_volume_buy = localview.exposed_order_volume("sell")
        current_front_price_spread = localview.current_front_price_spread(self.broker_id)
        current_public_order_price_10MW_buy = localview.current_order_price(
            COMMON.Direction.buy, at_volume=10, broker_id=self.broker_id)
        current_public_order_price_10MW_sell = localview.current_order_price(
            COMMON.Direction.sell, at_volume=10, broker_id=self.broker_id)

        localview.get_trade_statistics(broker_id=self.broker_id)
        trade_statistics = localview._trade_statistics

        msg = (
            "current_front_buy_price:{}, current_front_sell_price:{}, traded_volume_buy:{}, traded_volume_sell:{}, "
            "exposed_order_volume:{}, exposed_order_volume:{}, current_front_price_spread:{}, "
            "current_public_order_price_10MW_buy:{}, current_public_order_price_10MW_sell:{}, _trade_statistics: {}"
            .format(
                current_front_buy_price, current_front_sell_price, traded_volume_buy, traded_volume_sell,
                exposed_order_volume_sell, exposed_order_volume_buy, current_front_price_spread,
                current_public_order_price_10MW_buy, current_public_order_price_10MW_sell, trade_statistics
            )
        )
        self.debug_log(text="LocalView: {}".format(msg), product=product)

        #####################
        # Products Accessor #
        #####################

        xbid_product_same_timerange = self.exchange.products.get_by_timerange(
            start=product.delivery_start,
            end=product.delivery_end,
            product_type="XBID_Hour_Power"
        )

        all_products_with_overlap = self.exchange.products.get_overlapping_with_timerange(
            start=product.delivery_start,
            end=product.delivery_end
        )

        # find all by delivery span
        all_produts_same_delivery_span = self.exchange.products.get_all_by_delivery_span(
            start=product.delivery_start,
            end=product.delivery_end
        )

        # return the first result
        product_with_same_delivery_span = self.exchange.products.get_by_delivery_span(
            start=product.delivery_start,
            end=product.delivery_end,
            product_type=None
        )

        # get active products
        active_products = self.exchange.products.get_active_products(
            delivery_area_id=self.delivery_areas[0]
        )

        total_traded_volume = self.exchange.products.get_total_traded_volume(
            all_products_with_overlap,
            delivery_area_id=self.delivery_areas[0],
            trade_filter=COMMON.TradeFilter.own,
            portfolio_key=self.strategy_id,
            balance=False
        )

        total_traded_net_volume = self.exchange.products.get_total_traded_volume(
            all_products_with_overlap,
            delivery_area_id=self.delivery_areas[0],
            trade_filter=COMMON.TradeFilter.own,
            portfolio_key=self.strategy_id,
            balance=True
        )

        ###################
        # Product methods #
        ###################

        # check if product is tradable at a given time for a delivery area
        is_tradable = product.is_tradable(
            timestamp=timestamp,
            delivery_area_id=self.delivery_area_id
        )

        # check if product is locked, e.g. for by order which has been sent
        # to the exchange but not been confirmed yet => orderlock
        product.is_product_locked(timestamp=timestamp)

        # access via product
        orderbook_obj = product.orders
        tradelist_obj = product.trades
        exchange_obj = product.exchange

        ########################
        # Place Slots Examples #
        ########################
        self.place_slot_normal_limit_order(log_data, product, timestamp)
        self.place_slot_no_internal_market(log_data, product, timestamp)
        self.place_slot_with_price_tolerance(log_data, product, timestamp)
        self.place_slot_with_quantity_tolerance(log_data, product, timestamp)

    def place_slot_normal_limit_order(self, log_data, product, timestamp):
        """place slots, normal limit order"""
        #########################
        # parameters to use #
        #########################
        price = 1.0
        quantity = 1.0
        limit_buy_price = 100
        limit_sales_price = 100
        area = self.delivery_areas[0]
        direction = COMMON.Direction.sell

        #########################
        # create slot with info #
        #########################
        slot = STRAT.PositionSlot(
            "slot_name", direction, quantity, price,
            execution_restriction=COMMON.ExecutionRestriction.non,
            info="normal_placement_{}_qty_{}_prc_{}".format(direction, quantity, price)
        )

        ###############
        # place slots #
        ###############

        place_slot_result = self.place_slots(
            log_data, product, timestamp, area, [slot], [],
            limit_sales_price, limit_buy_price, execmode=COMMON.InternalExecutionMode.exchange_base_price
        )

        self.debug_log(
            text="Placed Slot: {} {}@{} ({})=> {}".format(
                slot.direction, slot.quantity, slot.price, slot.info, place_slot_result
            ),
            product=product
        )

    def place_slot_no_internal_market(self, log_data, product, timestamp):
        """place slots, normal limit order"""
        #########################
        # parameters to use #
        #########################
        price = 1.0
        quantity = 1.0
        limit_buy_price = 100
        limit_sales_price = 100
        area = self.delivery_areas[0]
        direction = COMMON.Direction.sell

        #########################
        # create slot with info #
        #########################
        slot = STRAT.PositionSlot(
            "slot_name", direction, quantity, price,
            execution_restriction=COMMON.ExecutionRestriction.non,
            info="normal_placement_{}_qty_{}_prc_{}".format(direction, quantity, price)
        )

        ###############
        # place slots #
        ###############

        # place slot without internal trades, but resolve the order conflicts
        # so we still have cross trade protection
        self.place_slots(
            log_data, product, timestamp, area, [slot], [],
            limit_sales_price, limit_buy_price, execmode=COMMON.InternalExecutionMode.no
        )

        # place slot without internal trades
        # and also no conflict resolving
        # this can potentially lead to cross trades
        self.place_slots(
            log_data, product, timestamp, area, [slot], [],
            limit_sales_price, limit_buy_price, execmode=COMMON.InternalExecutionMode.skip
        )

    def place_slot_with_price_tolerance(self, log_data, product, timestamp):
        """place slots with price tolerance, e.g. for bot race protection"""
        #########################
        # parameters to use #
        #########################
        price = 1.0
        price_tolerance = 10
        quantity = 1.0
        limit_buy_price = 100
        limit_sales_price = 100
        area = self.delivery_areas[0]
        direction = COMMON.Direction.sell

        #########################
        # create slot with info #
        #########################
        slot = STRAT.PositionSlot(
            "slot_name", direction, quantity, price,
            price_range_lo=price - price_tolerance, price_range_hi=price + price_tolerance,
            info="normal_placement_{}_qty_{}_prc_{}".format(direction, quantity, price)
        )

        ###############
        # place slots #
        ###############

        place_slot_result = self.place_slots(
            log_data, product, timestamp, area, [slot], [],
            limit_sales_price, limit_buy_price, execmode=COMMON.InternalExecutionMode.exchange_base_price
        )

        self.debug_log(
            text="Placed Slot: {} {}@{} (prc_range:{}//{}) ({})=> {}".format(
                slot.direction, slot.quantity, slot.price, slot.price_range_lo, slot.price_range_hi,
                slot.info, place_slot_result
            ),
            product=product
        )

    def place_slot_with_quantity_tolerance(self, log_data, product, timestamp):
        """place slots with quantity tolerance, like iceberg orders"""
        #####################
        # parameters to use #
        #####################
        price = 1.0
        quantity = 1.0
        max_quantity = 5
        min_quantity = 0.2
        limit_buy_price = 100
        limit_sales_price = 100
        area = self.delivery_areas[0]
        direction = COMMON.Direction.sell

        #########################
        # create slot with info #
        #########################
        slot = STRAT.PositionSlot(
            "slot_name", direction, quantity, price,
            quantity_range_hi=max_quantity, quantity_range_lo=min_quantity,
            info="normal_placement_{}_qty_{}_prc_{}".format(direction, quantity, price)
        )

        ###############
        # place slots #
        ###############

        place_slot_result = self.place_slots(
            log_data, product, timestamp, area, [slot], [],
            limit_sales_price, limit_buy_price, execmode=COMMON.InternalExecutionMode.exchange_base_price
        )

        self.debug_log(
            text="Placed Slot: {} {}@{} (prc_range:{}//{}) ({})=> {}".format(
                slot.direction, slot.quantity, slot.quantity_range_lo, slot.quantity_range_hi,
                slot.price, slot.info, place_slot_result
            ),
            product=product
        )

    def on_strategy_update(self, strategy_json):
        """The json is sent from Periotheus or from REST API (strategy steering call)

        strategy json comes unchanged -> can call anything
        api/strategy_steering

        :type strategy_json: dict
        :rtype: None
        """
        super(CustomStrategy, self).on_strategy_update(strategy_json)
        self.delivery_area_id = self.delivery_areas[0]

    def custom_on_order_book_update(self, orders, timestamp):
        """On Order Book

        :type orders: list[APITR.Order]
        :type timestamp: float
        :rtype: None
        """
        for order in orders:
            unused_price = order.price
            unused_quantity = order.quantity
            product = order.product
            unused_product_name = product.name
            orderbook = product.orders
            unused_own_orderbook = orderbook._own_order_book
            unused_public_orderbook = orderbook._public_order_book

        self.act(timestamp, list(set(o.product for o in orders)))

    def custom_on_trade_update(self, trades, timestamp):
        """On Own Trades only

        :type trades: list[APITR.Trade]
        :type timestamp: float
        :rtype: None
        """
        self.act(timestamp, list(set(t.product for t in trades)))

    def custom_on_public_trade_update(self, trades, timestamp):
        """On Public Trades only

        :type trades: list[APITR.Trade]
        :type timestamp: float
        :rtype: None
        """
        self.act(timestamp, list(set(t.product for t in trades)))

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

        # call self.act and not self.custom_act!
        # self.act makes some additional checks, e.g. avoid to run the strategy if the strategy is not active
        self.act(timestamp, products)

    def custom_on_timer(self, timestamp):
        pass  # products queue is enough
