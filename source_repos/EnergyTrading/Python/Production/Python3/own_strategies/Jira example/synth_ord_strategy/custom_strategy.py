

import logging

import autotrader_lib.common as COMMON
import autotrader_synthetic.commingled_view as CV
import autotrader_synthetic.synthetic_order_strategies.synthetic_order_strategy_base as SYSTRAT
from . import so_arbitrage_lead
from . import so_arbitrage_lift
from .constants import TTF_ICE, ITALY_BASELOAD

log = logging.getLogger("autotrader.tutorial_ff_arbitrage_09_multi_products")


class CustomStrategy(SYSTRAT.SyntheticOrderStrategyBase):
    # with the default payload, we define fields valid for all synthetic orders used with this strategy
    default_payload = {}

    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        self.delivery_areas_additional = [
            TTF_ICE,
            ITALY_BASELOAD
        ]
        # pass the logger, so all strategy related logs will have this logger handle
        self.log = log

    def on_strategy_configuration_update(self, strategy_json):
        super(CustomStrategy, self).on_strategy_configuration_update(strategy_json)

    def on_synthetic_order(self, payload):
        print(("DEBUG on_synthetic_order: ", payload))
        error = super(CustomStrategy, self).on_synthetic_order(payload)
        print(error)
        # import to still return the error, to make sure a rest call can get the response to this request
        return error

    def custom_on_order_book_update(self, orders, timestamp):
        for o in orders:
            print(("DEBUG ORDER UPDATE: ", o.product.product_id, o.delivery_area_id, o.price, o.quantity, o.direction))
        # just call act, to trigger all product synthetic orders
        products = self.exchange.products.get_active_products()
        test_commingled_view = CV.CommingledView(product=[p for p in products if p.product_id == "10000106_20"][0],
                                                 market_areas=["10100480"],
                                                 strategy_id=self.strategy_id)
        summarized_price_levels = test_commingled_view._summarize_price_level("buy", "37", only_tradable=True)
        print("Summarized price level: {}".format(summarized_price_levels))
        res = self.act(timestamp, products)
        return res

    def on_trade_update(self, trades, timestamp):
        res = super(CustomStrategy, self).on_trade_update(trades, timestamp)
        return res

    @classmethod
    def get_available_synthetic_order_types(cls):
        return {
            "ArbitrageOrder": so_arbitrage_lead.ArbitrageOrder,
            "LiftOrder": so_arbitrage_lift.LiftOrder
        }
