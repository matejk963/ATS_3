import logging

import autotrader_core.common as COMMON
import autotrader_core.strategy as STRATEGY

import autotrader_core.exchange_trading  # only for typing in this examples

log = logging.getLogger('autotrader.example_01_multiple_areas')
# hard coded delivery area always added
DELIVERY_AREAS = [COMMON.Area.amp]

DEBUG = False


class CustomStrategy(STRATEGY.Strategy):
    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        # pass strategy logger to base, to show distinct handle
        self.log = log

    def custom_act(self, log_data, timestamp, products=None):
        if not products:
            return
        for p in products:
            print("Act for Product: ", p.name)

    def on_strategy_update(self, strategy_json):
        super(CustomStrategy, self).on_strategy_update(strategy_json)
        # Take the delivery areas configured in Periotheus and add additional delivery areas
        self.delivery_areas = self.delivery_areas + DELIVERY_AREAS

    def on_strategy_configuration_update(self, strategy_json):
        super(CustomStrategy, self).on_strategy_configuration_update(strategy_json)
        # Take the delivery areas configured via REST-API and add additional delivery areas
        self.delivery_areas = self.delivery_areas + DELIVERY_AREAS

    def on_order_book_update(self, orders, timestamp):
        # type: (list[autotrader_core.exchange_trading.PublicOrder], float)-> None
        if DEBUG:
            for o in orders:
                print("OrderUpdate: %20s, %12s, %20s, %4s, %6d cent, %6d kWh" %
                      (o.delivery_area_id, o.product.product_id, o.product.name, o.direction,
                       int(o.price * 100), int(o.quantity * 1000)))
                # to reduce the amount of printouts, break after the first one
                break
        # add this line, if strategy should react to the products affected by these updates
        # self.act(timestamp, set(o.product for o in orders))

    def on_products_queue(self, products, timestamp):
        self.act(timestamp, products)
