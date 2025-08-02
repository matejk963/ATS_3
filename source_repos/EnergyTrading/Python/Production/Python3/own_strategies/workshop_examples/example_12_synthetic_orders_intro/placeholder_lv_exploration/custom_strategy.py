""" Helper strategy, not relevant to the workshop example """

import autotrader_lib.common as COMMON

import autotrader_synthetic.synthetic_order_strategies.synthetic_order_strategy_base as SYSTRAT

from . import placeholder_so as PSO

import logging
log = logging.getLogger('autotrader.example_12.placeholder_lv_exploration')


# IMPORTANT: For now lets ignore what this strategy does!
class CustomStrategy(SYSTRAT.SyntheticOrderStrategyBase):
    """ This is just a placeholder strategy """
    default_payload = {"identifier": "example_so",
                       "message_type": COMMON.SyntheticMessageType.order,
                       "synthetic_order_type": "EmptySyntheticOrder",
                       "configuration": {"slot_name": "example_so"}}

    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        # pass the logger, so all strategy related logs will have this logger handle
        self.log = log

    def on_strategy_configuration_update(self, strategy_json):
        super(CustomStrategy, self).on_strategy_configuration_update(strategy_json)

        for desired_product in self.strategy_settings["so_products"]:
            planned_payload = self.default_payload.copy()
            planned_payload["configuration"]["market_area"] = self.delivery_area_id

            try:
                self.on_synthetic_order_register(desired_product, planned_payload)
            except SYSTRAT.ERR.ConfigurationError as err:
                if "already exists" in err.message:
                    self.on_synthetic_order_modify(desired_product, planned_payload)
                else:
                    raise

    @classmethod
    def get_available_synthetic_order_types(cls):
        return {"EmptySyntheticOrder": PSO.EmptySyntheticOrder}
