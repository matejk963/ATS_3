#!/usr/bin/env python
# -*- coding: utf-8 -*-

import autotrader_core.simple_epex_strategy as simple_epex_strategy
import autotrader_core.common as COMMON
import autotrader_core.strategy as ATSTRAT

import logging

log = logging.getLogger('autotrader.manual_epex_floating_quarterly')


class CustomStrategy(simple_epex_strategy.SimpleEpexStrategy):

    def get_slots(self, log_data, product, timestamp, position_long, position_short,
                  traded_sell, traded_buy, average_price,
                  product_interval, seconds_traded, seconds_left, indicators,
                  limit_maximum_sales_volume, limit_maximum_purchase_volume, limit_maximum_purchase_price,
                  limit_minimum_sales_price, purchase_immediate_vesting_price, sales_immediate_vesting_price,
                  price_purchase, price_sales,
                  price_minimum_spread_buyback, maximum_imbalance_on_market_closure,
                  maximum_order_book, trading_end_before_market_closure, otr):

        if any([limit_minimum_sales_price is None, limit_maximum_purchase_price is None]):
            return []

        if any([indicators[1][0] is None, indicators[0][0] is None]):
            return []

        slots = []

        if otr > 47:
            return slots

        if product.delivery_end - product.delivery_start == 900:
            # handle only 15 minute products
            ord_sell = ATSTRAT.PositionSlot("ord_sell",
                                            COMMON.Direction.sell,
                                            max(position_long - traded_sell, 0.),
                                            indicators[1][0])

            ord_buy = ATSTRAT.PositionSlot("ord_buy",
                                           COMMON.Direction.buy,
                                           max(position_short - traded_buy, 0.),
                                           indicators[0][0])

            slots.extend([ord_sell, ord_buy])

        return slots
