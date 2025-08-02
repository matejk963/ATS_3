""" Helper strategy, not relevant to the workshop example """
import autotrader_core.common as COMMON

import autotrader_synthetic.synthetic_order_strategies.synthetic_order_strategy_base as SYSTRAT

import so_one as SOO
import so_two as SOT

import logging
log = logging.getLogger('autotrader.example_13.so_config_and_management')


class CustomStrategy(SYSTRAT.SyntheticOrderStrategyBase):
    """ This is just a placeholder strategy """
    default_payload = {"identifier": "example_so",
                       "message_type": COMMON.SyntheticMessageType.order,
                       "synthetic_order_type": "SimpleSyntheticOrder",
                       "configuration": {"slot_name": "example_so",
                                         "broker_id": COMMON.Broker.eexs}}

    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        # pass the logger, so all strategy related logs will have this logger handle
        self.log = log

    def on_strategy_configuration_update(self, strategy_json):
        super(CustomStrategy, self).on_strategy_configuration_update(strategy_json)

        if "product" in self.strategy_settings:
            desired_product = self.strategy_settings["product"]
            planned_payload = self.default_payload.copy()
            planned_payload["synthetic_order_type"] = self.strategy_settings.get("order_type")
            planned_payload["configuration"]["market_area"] = self.delivery_area_id
            planned_payload["configuration"]["position"] = self.strategy_settings.get("position")
            planned_payload["configuration"]["config_option"] = self.strategy_settings.get("config_option")

            # important distinction
            try:
                product_mapping = self.product_synthetic_order_mapping.get(desired_product)
                if not product_mapping or planned_payload["identifier"] not in product_mapping:
                    self.on_synthetic_order_register(desired_product, planned_payload)
                else:
                    self.on_synthetic_order_modify(desired_product, planned_payload)

            except Exception as err:
                print(err)

    @classmethod
    def get_available_synthetic_order_types(cls):
        return {"SimpleSyntheticOrderOne": SOO.SimpleSyntheticOrderOne,
                "SimpleSyntheticOrderTwo": SOT.SimpleSyntheticOrderTwo}
