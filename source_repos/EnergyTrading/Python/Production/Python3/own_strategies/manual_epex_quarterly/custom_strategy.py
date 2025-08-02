#!/usr/bin/python3
# -*- coding: utf-8 -*-

import autotrader_core.simple_epex_strategy as simple_epex_strategy
import autotrader_lib.common as COMMON
import autotrader_core.strategy as ATSTRAT
import logging

log = logging.getLogger('autotrader.manual_epex_quarterly_strategy')


class CustomStrategy(simple_epex_strategy.SimpleEpexStrategy):

    def get_slots(self, log_data, product, timestamp, position_long, position_short,
                  traded_sell, traded_buy, average_price,
                  product_interval, seconds_traded, seconds_left, indicators,
                  limit_maximum_sales_volume, limit_maximum_purchase_volume, limit_maximum_purchase_price,
                  limit_minimum_sales_price, purchase_immediate_vesting_price, sales_immediate_vesting_price,
                  price_purchase, price_sales,
                  price_minimum_spread_buyback, maximum_imbalance_on_market_closure,
                  maximum_order_book, trading_end_before_market_closure):

        if any([limit_minimum_sales_price is None, limit_maximum_purchase_price is None]):
            return [], COMMON.InternalExecutionMode.exchange_base_price

        slots = []

        if product.delivery_end - product.delivery_start == 900:
            # handle only 15 minute products
            ord_sell = ATSTRAT.PositionSlot("ord_sell",
                                            COMMON.Direction.sell,
                                            max(position_long - traded_sell, 0.),
                                            limit_minimum_sales_price)

            ord_buy = ATSTRAT.PositionSlot("ord_buy",
                                           COMMON.Direction.buy,
                                           max(position_short - traded_buy, 0.),
                                           limit_maximum_purchase_price)

            slots.extend([ord_sell, ord_buy])

        return slots, COMMON.InternalExecutionMode.exchange_base_price
