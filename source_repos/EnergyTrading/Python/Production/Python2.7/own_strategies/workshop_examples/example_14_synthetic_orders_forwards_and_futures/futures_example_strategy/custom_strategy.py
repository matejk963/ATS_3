""" Helper strategy, not relevant to the workshop example """
import autotrader_core.common as COMMON

import autotrader_synthetic.synthetic_order_strategies.synthetic_order_strategy_base as SYSTRAT

import position_closing_so as PCSO


import logging
log = logging.getLogger('autotrader.example_14.futures_example_strategy')


class CustomStrategy(SYSTRAT.SyntheticOrderStrategyBase):
    """ This is just a placeholder strategy """
    default_payload = {"identifier": "closer_so",
                       "message_type": COMMON.SyntheticMessageType.order,
                       "configuration": {"slot_name": "closer_so",
                                         "broker_id": COMMON.Broker.eex}}

    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        # pass the logger, so all strategy related logs will have this logger handle
        self.log = log

    def on_strategy_configuration_update(self, strategy_json):
        super(CustomStrategy, self).on_strategy_configuration_update(strategy_json)

        if "product" in self.strategy_settings:
            product_id = self.strategy_settings["sequence_item_id"]
            planned_payload = self.default_payload.copy()
            planned_payload["synthetic_order_type"] = self.strategy_settings.get("order_type")
            planned_payload["configuration"]["market_area"] = self.delivery_area_id
            planned_payload["configuration"]["position"] = self.strategy_settings.get("position")
            planned_payload["configuration"]["slot_size"] = self.strategy_settings.get("slot_size")
            planned_payload["configuration"]["spread"] = self.strategy_settings.get("spread")

            product = None
            if product_id:
                product = self.autotrader.trayport.products.get_by_id(product_id)

            self.debug_log("Strategy settings: {}".format(planned_payload), product)

            product_mapping = self.product_synthetic_order_mapping.get(product_id)
            if not product_mapping or planned_payload["identifier"] not in product_mapping:
                self.on_synthetic_order_register(product_id, planned_payload)
            else:
                self.on_synthetic_order_modify(product_id, planned_payload)

    def on_synthetic_order_register(self, product_id, payload):
        super(CustomStrategy, self).on_synthetic_order_register(product_id, payload)
        needed_fields = ("market_area", "position", "slot_size", "spread")
        for field in needed_fields:
            if field not in payload["configuration"]:
                self.debug_log("Field {} is not in the configuration payload".format(field))

    @classmethod
    def get_available_synthetic_order_types(cls):
        return {"PositionClosingBehavior": PCSO.PositionClosingBehavior}
