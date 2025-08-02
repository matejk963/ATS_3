import autotrader_lib.common as COMMON
import autotrader_synthetic.synthetic_order_strategies.synthetic_order_strategy_base as SYSTRAT

import logging

import simple_so

# Identifier and slot name must be the same
DEFAULT_IDENTIFIER = "simple_so_1"
log = logging.getLogger('autotrader.simple_synthetic_strategy')


class CustomStrategy(SYSTRAT.SyntheticOrderStrategyBase):

    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        # pass the logger, so all strategy related logs will have this logger handle
        self.log = log

    def on_strategy_configuration_update(self, strategy_json):
        super(CustomStrategy, self).on_strategy_configuration_update(strategy_json)
        # custom configuration for this strategy
        self.debug_log("Received Registering SO products" + str(self.strategy_settings["so_products"]))

        # handle registering the synthetic order for the transferred products
        if not self.strategy_settings["so_products"]:
            return

        payload = {"identifier": DEFAULT_IDENTIFIER,
                   "message_type": COMMON.SyntheticMessageType.order,
                   "synthetic_order_type": "SimpleSO",
                   "configuration": {
                       "market_area": self.delivery_area_id,
                       "broker_id": COMMON.Broker.eexs}
                   }

        for desired_product in self.strategy_settings["so_products"]:
            try:
                self.on_synthetic_order_register(desired_product, payload)
            except SYSTRAT.ERR.ConfigurationError as err:
                if "already exists" not in err.message:
                    raise
                self.on_synthetic_order_modify(desired_product, payload)

    @classmethod
    def get_available_synthetic_order_types(cls):
        return {"SimpleSO": simple_so.SimpleSO}
