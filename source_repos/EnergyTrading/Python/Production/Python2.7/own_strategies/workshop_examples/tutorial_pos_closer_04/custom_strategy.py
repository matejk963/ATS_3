#!/usr/bin/env python
# -*- coding: utf-8 -*-
import autotrader_core.common as COMMON
import autotrader_core.strategy as STRAT
import logging


log = logging.getLogger('autotrader.new_position_closer')


class CustomStrategy(STRAT.Strategy):
    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        # pass strategy logger to base, to show distinct handle
        self.log = log

        # and we need to define their update ourselves
        self.strategy_position_tradable_position_long = STRAT.StrategyTimeSeries(COMMON.QUARTER)
        self.strategy_position_tradable_position_short = STRAT.StrategyTimeSeries(COMMON.QUARTER)

        self.strategy_price_purchase = STRAT.StrategyTimeSeries(COMMON.QUARTER)
        self.strategy_price_sales = STRAT.StrategyTimeSeries(COMMON.QUARTER)

    def custom_act(self, log_data, timestamp, products=None):
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

        for product in sorted(products, key=lambda p: p.delivery_start):
            self.act_for_product(product=product, timestamp=timestamp)

    def custom_act_for_product(self, log_data, product, timestamp, *args, **kwargs):
        self.debug_log(text="Act for product", product=product)

        # get positions set in periotheus (or by REST API)
        product_interval = (product.delivery_start, product.delivery_end)
        long_target = self.strategy_position_tradable_position_long.get(product_interval, 0.) or 0.
        short_target = self.strategy_position_tradable_position_short.get(product_interval, 0.) or 0.
        open_position = short_target - long_target

        ##############################################################
        # create slots with price and quantity rounded to tick sizes #
        ##############################################################

        slot = STRAT.PositionSlot("front", COMMON.Direction.buy, quantity=0, price=0)

        if open_position > 0:
            slot.direction = COMMON.Direction.buy
            slot.quantity = open_position

        elif open_position < 0:
            slot.direction = COMMON.Direction.sell
            slot.quantity = - open_position

        # info to be saved with the order/trade
        slot.info = "place front"

        # place slots and save response
        slot_responses = self.place_slots({}, product, timestamp, self.delivery_area_id, [slot])
        self.debug_log(text="Slot Placement Results: {}".format(slot_responses), product=product)

    def on_strategy_update(self, strategy_json):
        super(CustomStrategy, self).on_strategy_update(strategy_json)
        # on strategy update sets the self.delivery_areas from the passed json

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
        self.act(timestamp, set(o.product for o in orders))

    def custom_on_products_update(self, products, timestamp):
        self.act(timestamp, products)

    def custom_on_products_queue(self, products, timestamp):
        self.act(timestamp, products)
