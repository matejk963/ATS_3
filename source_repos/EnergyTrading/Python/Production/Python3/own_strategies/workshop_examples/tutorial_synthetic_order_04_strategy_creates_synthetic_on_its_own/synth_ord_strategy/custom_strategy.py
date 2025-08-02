""" Strategy which can spawn synthetic orders """

import logging

import autotrader_lib.common as COMMON
import autotrader_synthetic.synthetic_order_strategies.synthetic_order_strategy_base as SYSTRAT
from . import simple_so
from autotrader_synthetic.local_view import LocalView
from autotrader_synthetic.factory_view import ViewFactory
from six.moves import zip

SELL_SLOTNAME = "sell_slot"
BUY_SLOTNAME = "buy_slot"

log = logging.getLogger('autotrader.tutorial_synthetic_order_04_strategy_creates_synthetic_on_its_own')


class CustomStrategy(SYSTRAT.SyntheticOrderStrategyBase):
    def __init__(self, autotrader_instance, strategy_id, caption, strategy_package_name):
        super(CustomStrategy, self).__init__(autotrader_instance, strategy_id, caption, strategy_package_name)

        # DEFINE BROKER ID
        self.broker_id = COMMON.Broker.eexs
        self.positionsByProduct = {}  # positions to be traded by the products
        self.synthetic_orders = {}

    def custom_act(self, log_data, timestamp, products=None):
        """when act is called, mostly reacting to changes in products

        :type log_data: dict
        :type timestamp: float
        :type products: list[APITR.Product]
        :return:
        """
        if not products:
            return

        for product in products:
            if product.product_id in self.positionsByProduct:
                self.act_for_product(product, timestamp)

    def custom_act_for_product(self, log_data, product, timestamp, *args, **kwargs):
        if product.product_id not in self.synthetic_orders:
            props = self.autotrader.trayport.get_properties(broker_id=self.broker_id,
                                                            delivery_area_id=self.delivery_area_id,
                                                            product_id=product.product_id)
            so = simple_so.SimpleSO(tick_size=props.qty_tick,
                                    identifier="so_" + product.product_id,
                                    configuration=dict(market_area=self.delivery_area_id,
                                                       broker_id=self.broker_id,
                                                       slot_name="so_" + product.product_id,
                                                       position=self.positionsByProduct[product.product_id],
                                                       slot_size=props.min_quantity + props.qty_tick * 2,
                                                       spread=props.price_tick * 5)
                                    )
            self.synthetic_orders[product.product_id] = so
        so = self.synthetic_orders[product.product_id]
        self.debug_log(text="Call Synthetic Order Act", product=product)
        slot = so.act(LocalView(product, self.delivery_area_id, self.strategy_id),
                      ViewFactory(self.exchange.products, self.strategy_id),
                      timestamp)
        if slot:
            result = self.place_slots({}, product, timestamp, self.delivery_area_id, [slot])
            self.debug_log(text="Placed {} with result: {}".format(slot.short(), result[0]), product=product)

    def on_strategy_configuration_update(self, strategy_json):
        # call on super also handles active field
        super(CustomStrategy, self).on_strategy_configuration_update(strategy_json)
        # custom configuration for this strategy
        self.debug_log("Received Registering SO products" + str(self.strategy_settings["so_products"]))

        # handle registering the synthetic order for the transferred products
        if "so_products" not in self.strategy_settings or "so_positions" not in self.strategy_settings:
            return

        if not self.strategy_settings["so_products"] or not self.strategy_settings["so_positions"]:
            return

        self.positionsByProduct = dict(zip(self.strategy_settings["so_products"],
                                           self.strategy_settings["so_positions"]))

    def custom_on_products_queue(self, products, timestamp):
        self.act(timestamp, products)
