import autotrader_core.common as COMMON
import autotrader_synthetic.synthetic_order_strategies.synthetic_order_strategy_base as SYSTRAT

import logging

import simple_so

BROKER_ID = COMMON.Broker.eexs
# Identifier and slot name must be the same
DEFAULT_IDENTIFIER = "simple_so_1"

log = logging.getLogger('autotrader.tutorial_synthetic_order_03_add_synthetic_order_and_initiate_via_rest')


class CustomStrategy(SYSTRAT.SyntheticOrderStrategyBase):
    # with the default payload, we define fields valid for all synthetic orders used with this strategy
    default_payload = {"identifier": DEFAULT_IDENTIFIER,
                       "message_type": COMMON.SyntheticMessageType.order,
                       "synthetic_order_type": "SimpleSO",
                       "configuration": {"slot_name": DEFAULT_IDENTIFIER}}

    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        # pass the logger, so all strategy related logs will have this logger handle
        self.log = log
        self.broker_id = BROKER_ID

    def handle_so_for_product(self, product_id):
        planned_payload = self.default_payload.copy()
        planned_payload["configuration"]["market_area"] = self.delivery_area_id
        planned_payload["configuration"]["broker_id"] = self.broker_id

        try:
            self.on_synthetic_order_register(product_id, planned_payload)
        except SYSTRAT.ERR.ConfigurationError as err:
            if "already exists" not in err.message:
                raise
            self.on_synthetic_order_modify(product_id, planned_payload)

    def on_strategy_configuration_update(self, strategy_json):
        super(CustomStrategy, self).on_strategy_configuration_update(strategy_json)
        # custom configuration for this strategy
        self.debug_log("Received Registering SO products" + str(self.strategy_settings["so_products"]))

        # handle registering the synthetic order for the transferred products
        if not self.strategy_settings["so_products"]:
            return

        for desired_product in self.strategy_settings["so_products"]:
            self.handle_so_for_product(desired_product)

    @classmethod
    def get_available_synthetic_order_types(cls):
        return {"SimpleSO": simple_so.SimpleSO}
