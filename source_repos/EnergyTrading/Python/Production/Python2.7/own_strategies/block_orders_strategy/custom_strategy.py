#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This strategy aims to place block orders at the exchange
It will create a user defined product
"""

import autotrader_core.simple_epex_strategy as SIMEPEXSTR
import autotrader_core.strategy as STRATEGY
import autotrader_core.common as COMMON
import autotrader_core.api as API
import autotrader_lib.util as ALU
import datetime

import logging

HOUR = 60 * 60
log = logging.getLogger("autotrader.simple_epex_strategy")


class CustomStrategy(SIMEPEXSTR.SimpleEpexStrategy):

    def __init__(self, *args, **kwargs):

        super(SIMEPEXSTR.SimpleEpexStrategy, self).__init__(*args, **kwargs)
        self.delivery_area_id = COMMON.Area.rwe
        self.delivery_areas = [self.delivery_area_id]
        self.strategy_settings["trading_end_before_market_closure"] = None
        self.tradable_long = 1.
        self.tradable_short = 1.
        self.limit_maximum_purchase_price = 29.
        self.limit_minimum_sales_price = 30.

    def get_slots(self, log_data, product, timestamp, position_long,
                  position_short, traded_sell, traded_buy,
                  limit_maximum_purchase_price, limit_minimum_sales_price):

        if any([limit_minimum_sales_price is None,
                limit_maximum_purchase_price is None]):
            return [], COMMON.InternalExecutionMode.exchange_base_price

        slots = []

        price_sell = limit_minimum_sales_price
        qty_sell = (position_long - traded_sell)

        ord_sell = STRATEGY.PositionSlot(
            "ord_sell", COMMON.Direction.sell, qty_sell, price_sell,
            order_type=COMMON.OrderType.block,
            execution_restriction=COMMON.ExecutionRestriction.aon)

        price_buy = limit_maximum_purchase_price
        qty_buy = (position_short - traded_buy)

        ord_buy = STRATEGY.PositionSlot(
            "ord_buy", COMMON.Direction.buy, qty_buy, price_buy,
            order_type=COMMON.OrderType.block,
            execution_restriction=COMMON.ExecutionRestriction.aon)

        slots.extend([ord_sell, ord_buy])
        slotlog = " / ".join(
            [
                "{} {} {}@{} ({}-{})".format(
                    s.slot_type, s.direction, s.quantity, s.price, s.price_range_lo, s.price_range_hi
                ) for s in slots
            ]
        )
        log.debug("{} {}, ts: {} tb: {}, {}".format(timestamp, product.name, traded_sell, traded_buy, slotlog))
        return slots, COMMON.InternalExecutionMode.exchange_base_price

    def get_traded(self, product):
        own_trades = product.trades.get(delivery_area=self.delivery_area_id,
                                        trade_filter=API.TradeFilter.own,
                                        portfolio_key=self.strategy_id)
        traded_sell = sum(t.quantity for t in own_trades
                          if t.direction == COMMON.Direction.sell)
        traded_buy = sum(t.quantity for t in own_trades
                         if t.direction == COMMON.Direction.buy)
        if own_trades:
            average_price = sum(t.quantity * t.price for t in own_trades) / (traded_sell + traded_buy)
        else:
            average_price = None
        return traded_sell, traded_buy, average_price

    def get_and_place_slots(self, log_data, product, timestamp, position_long,
                            position_short, traded_sell, traded_buy,
                            limit_maximum_purchase_price, limit_minimum_sales_price):
        stats = ["{:0.1f}_{:0.1f}_{:0.1f}_{:0.1f}".format(
                 position_long, position_short, traded_sell, traded_buy)]

        slots, execmode = self.get_slots(log_data, product, timestamp,
                                         position_long, position_short,
                                         traded_sell, traded_buy,
                                         limit_maximum_purchase_price,
                                         limit_minimum_sales_price)

        self.place_slots(log_data, product, timestamp, self.delivery_area_id, slots, stats, limit_minimum_sales_price,
                         limit_maximum_purchase_price, execmode)

    def place_slots_for_block_product(self, product, timestamp, traded_sell, traded_buy):
        position_long = self.tradable_long
        position_short = self.tradable_short
        limit_minimum_sales_price = self.limit_minimum_sales_price
        limit_maximum_purchase_price = self.limit_maximum_purchase_price

        if product is None:
            now = datetime.datetime.now()
            delivery_start = datetime.datetime.combine(now, datetime.time(now.hour + 2, 0))
            delivery_end = datetime.datetime.combine(now, datetime.time(now.hour + 4, 0))
            product = self.autotrader.epex.products.get_by_delivery_span(
                ALU.convert_dt_to_timestamp(delivery_start),
                ALU.convert_dt_to_timestamp(delivery_end),
                "Intraday_Hour_Power")
            if product:
                if product.product_id:
                    log.debug("waiting for the existing block product to be queued")
                    return

            product = self.autotrader.epex.products.add_block_product(
                ALU.convert_dt_to_timestamp(delivery_start),
                ALU.convert_dt_to_timestamp(delivery_end))
            if product is None:
                return
            traded_sell, traded_buy, unused_average_price = self.get_traded(product)
        log_data = {"product_caption": product.name}

        self.get_and_place_slots(log_data, product, timestamp, position_long,
                                 position_short, traded_sell, traded_buy,
                                 limit_maximum_purchase_price, limit_minimum_sales_price)

    def custom_act(self, log_data, timestamp, products=None):
        if products:
            for product in products:
                if not (
                        product.product_type == "Intraday_Hour_Power"
                        and (product.delivery_end - product.delivery_start).total_seconds() > 3600
                ):
                    continue
                traded_sell, traded_buy, average_price = self.get_traded(product)
                if product.product_id:
                    logs = self.act_for_product(product, timestamp, self.tradable_long,
                                                self.tradable_short, traded_sell,
                                                traded_buy, average_price)
                    return log_data.append(logs)
                else:
                    self.place_slots_for_block_product(product, timestamp,
                                                       traded_sell, traded_buy)
        else:
            self.place_slots_for_block_product(None, timestamp, 0., 0.)

    def custom_act_for_product(self, log_data, product, timestamp,
                               position_long, position_short,
                               traded_sell, traded_buy,
                               average_price):
        position_long = self.tradable_long
        position_short = self.tradable_short
        limit_minimum_sales_price = self.limit_minimum_sales_price
        limit_maximum_purchase_price = self.limit_maximum_purchase_price
        log_data.update({"tradeable_position": position_long - position_short,
                         "traded_position": traded_sell - traded_buy,
                         "slots": []})

        trading_start, trading_end, unused_trading_state = product.trading_phase(self.delivery_area_id)

        if not (trading_start <= timestamp <= trading_end):
            return

        self.get_and_place_slots(log_data, product, timestamp, position_long,
                                 position_short, traded_sell, traded_buy,
                                 limit_maximum_purchase_price, limit_minimum_sales_price)
