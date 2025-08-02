#!/usr/bin/env python
# -*- coding: utf-8 -*-

import autotrader_core.simple_epex_strategy as SIMEPEXSTR
import autotrader_core.strategy as STRATEGY
import autotrader_core.common as COMMON

import logging
import random

log = logging.getLogger('autotrader')


class CustomStrategy(SIMEPEXSTR.SimpleEpexStrategy):

    @staticmethod
    def update_deltas_for_product(product):
        """The function updates com_price_deltas for a given product
        """
        delta_buy = 1.45
        delta_sell = 2.33

        for delivery_area, state in product.delivery_area_states.items():
            if state == COMMON.DeliveryAreaState.active:
                product.update_com_price_deltas(delivery_area, delta_buy, delta_sell)

    def get_slots(self, log_data, product, timestamp, position_long, position_short,
                  traded_sell, traded_buy, average_price,
                  product_interval, seconds_traded, seconds_left, indicators,
                  limit_maximum_sales_volume, limit_maximum_purchase_volume, limit_maximum_purchase_price,
                  limit_minimum_sales_price, purchase_immediate_vesting_price, sales_immediate_vesting_price,
                  price_purchase, price_sales,
                  price_minimum_spread_buyback, maximum_imbalance_on_market_closure,
                  maximum_order_book, trading_end_before_market_closure, otr):

        if any([limit_minimum_sales_price is None,
                limit_maximum_purchase_price is None]):
            return [], COMMON.InternalExecutionMode.exchange_base_price

        skip = random.choice(range(50))

        if skip:
            return [], COMMON.InternalExecutionMode.average_price

        slots = []

        if product.delivery_end - product.delivery_start == 900:
            # handle only 15 minute products
            # Update price deltas for the product
            self.update_deltas_for_product(product)
            # Create position slots
            price_sell = random.choice([limit_minimum_sales_price + i for i in range(10)])
            price_sell = limit_minimum_sales_price + 10. * random.random()
            qty_sell = (position_long - traded_sell) * random.random()

            ord_sell = STRATEGY.PositionSlot(
                "ord_sell", COMMON.Direction.sell, qty_sell, price_sell,
                execution_restriction=COMMON.ExecutionRestriction.non)

            ord_sell_next = STRATEGY.PositionSlot(
                "ord_sell_next", COMMON.Direction.sell, qty_sell, 1.1 * price_sell,
                execution_restriction=COMMON.ExecutionRestriction.non)

            price_buy = limit_maximum_purchase_price - 5. * random.random()
            qty_buy = (position_short - traded_buy) * random.random()

            ord_buy = STRATEGY.PositionSlot(
                "ord_buy", COMMON.Direction.buy, qty_buy, price_buy,
                execution_restriction=COMMON.ExecutionRestriction.non)

            ord_buy_next = STRATEGY.PositionSlot(
                "ord_buy_next", COMMON.Direction.buy, qty_buy, 0.9 * price_buy,
                execution_restriction=COMMON.ExecutionRestriction.non)

            slots.extend([ord_sell, ord_buy, ord_sell_next, ord_buy_next])
        slotlog = " / ".join(
            [
                "{} {} {}@{} ({}-{})".format(
                    s.slot_type, s.direction, s.quantity, s.price, s.price_range_lo, s.price_range_hi
                ) for s in slots
            ]
        )
        log.debug("{} {}, ts: {} tb: {}, {}".format(timestamp, product.name, traded_sell, traded_buy, slotlog))
        return slots, COMMON.InternalExecutionMode.exchange_base_price
