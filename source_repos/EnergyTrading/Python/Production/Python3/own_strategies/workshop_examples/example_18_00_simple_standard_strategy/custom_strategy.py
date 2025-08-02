#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""Simple Gas strategy to Demo Unit Tests"""
import autotrader_lib.common as COMMON
import autotrader_core.strategy as STRAT
import autotrader_core.exchange_trading as APITR

import logging

log = logging.getLogger('autotrader.simple_standard_strategy')


class CustomStrategy(STRAT.GasStrategy):
    """ Very simple example standard strategy that promptly trades the front buy and front sell public orders """

    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)

        # pass strategy logger to base, to show distinct handle
        self.log = log

        # trayport broker has to be defined
        self.broker_id = COMMON.Broker.eexs

    def custom_on_order_book_update(self, orders, timestamp):
        products = set(o.product for o in orders)
        if not products:
            return
        for product in sorted(products, key=lambda p: p.delivery_start):
            self.act_for_product(product=product, timestamp=timestamp)

    def custom_act_for_product(self, log_data, product, timestamp, *args, **kwargs):
        self.debug_log(text="Act for product", product=product)

        properties = self.get_trayport_properties(product_id=product.product_id)
        tick_size = properties.price_tick

        best_public_buy_price = None
        best_public_sell_price = None
        best_public_buy_quantity = None
        best_public_sell_quantity = None
        indicators = product.orders.indicators(self.delivery_area_id)
        if indicators:
            best_public_buy_price = indicators[0].mw_prices[0][0]
            best_public_sell_price = indicators[0].mw_prices[1][0]
            best_public_buy_quantity = indicators[0].eur_quantities[0][0]
            best_public_sell_quantity = indicators[0].eur_quantities[1][0]

        if best_public_buy_price and best_public_buy_quantity:
            # round the price to tick size
            trade_price = (best_public_buy_price / tick_size - 1) * tick_size

            sell_slot = STRAT.PositionSlot(
                "sell_slot",
                COMMON.Direction.sell,
                quantity=best_public_buy_quantity,
                price=trade_price - 10,
                broker_id=self.broker_id,
                info="slot_name_{}||order:{}@{}".format("sell_slot", best_public_buy_quantity, trade_price)
            )
            slot_responses = self.place_slots({}, product, timestamp, self.delivery_area_id, [sell_slot], [],
                                              limit_minimum_sales_price=-9999, limit_maximum_purchase_price=9999,
                                              execmode=COMMON.InternalExecutionMode.exchange_base_price)
            self.debug_log(text="Sell Slot Placement Results: {}".format(slot_responses), product=product)

        if best_public_sell_price and best_public_sell_quantity:
            # round the price to tick size
            trade_price = (best_public_sell_price / tick_size + 1) * tick_size

            buy_slot = STRAT.PositionSlot(
                "buy_slot",
                COMMON.Direction.buy,
                quantity=best_public_sell_quantity,
                price=trade_price + 10,
                broker_id=self.broker_id,
                info="slot_name_{}||order:{}@{}".format("buy_slot", best_public_sell_quantity, trade_price)
            )
            slot_responses = self.place_slots({}, product, timestamp, self.delivery_area_id, [buy_slot], [],
                                              limit_minimum_sales_price=-9999, limit_maximum_purchase_price=9999,
                                              execmode=COMMON.InternalExecutionMode.exchange_base_price)
            self.debug_log(text="Buy Slot Placement Results: {}".format(slot_responses), product=product)
