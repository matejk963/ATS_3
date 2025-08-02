import logging

import autotrader_core.common as COMMON
import autotrader_synthetic.synthetic_order_strategies.synthetic_order_strategy_base as SYSTRAT
import so_arbitrage_lead
from constants import TTF_BROKER_ID, TTF_ICE, THE_ICE, GAS_PRODUCT_ID
from own_strategies.workshop_examples.tutorial_ff_arbitrage_08_lift_order.synth_ord_strategy import so_arbitrage_lift

log = logging.getLogger("autotrader.tutorial_synthetic_order_08_lift_order")


class CustomStrategy(SYSTRAT.SyntheticOrderStrategyBase):
    # with the default payload, we define fields valid for all synthetic orders used with this strategy
    default_payload = {}

    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        self.delivery_areas_additional = [
            TTF_ICE,
            THE_ICE
        ]
        # pass the logger, so all strategy related logs will have this logger handle
        self.log = log

    def on_strategy_configuration_update(self, strategy_json):
        super(CustomStrategy, self).on_strategy_configuration_update(strategy_json)

    def on_synthetic_order(self, payload):
        super(CustomStrategy, self).on_synthetic_order(payload)
        self._update_lift_orders()

    def custom_on_order_book_update(self, orders, timestamp):
        super(CustomStrategy, self).custom_on_order_book_update(orders, timestamp)
        self._update_lift_orders()

    def on_trade_update(self, trades, timestamp):
        super(CustomStrategy, self).on_trade_update(trades, timestamp)
        self._update_lift_orders()

    def create_lift_synthetic_order_payload_register(self, so):
        return {
            "operation": COMMON.SyntheticOrderOperations.register,
            "product_id": GAS_PRODUCT_ID,
            "message_type": "synthetic_order",
            "synthetic_order_type": "LiftOrder",
            "identifier": "LIFT",
            "configuration": {
                "slot_name": "LIFT",
                "market_area": so.lift_instrument_id,
                "broker_id": TTF_BROKER_ID,
                "lead_instrument_id": so.market_area,
                "lead_slot_name": so.slot_name,
                "strategy_id": self.strategy_id
            }
        }

    def _update_lift_orders(self):
        for prod, sos in self.product_synthetic_order_mapping.items():
            for identifier, so in sos.items():
                if isinstance(so, so_arbitrage_lift.LiftOrder):
                    if any([(other_so.slot_name == "LEAD" and other_so.market_area == so.lead_instrument_id)
                            for other_so in self.product_synthetic_order_mapping[prod].values()]):
                        # if we already have a LIFT for this, then do nothing
                        pass
                    else:
                        self.debug_log("Removing LIFT SO {} [{}]".format(so.identifier, prod))
                        payload = {"identifier": so.identifier, "synthetic_order_type": "LiftOrder"}
                        self.on_synthetic_order_delete(prod, payload)

                if isinstance(so, so_arbitrage_lead.ArbitrageOrder):
                    if any([(other_so.slot_name == "LIFT" and other_so.market_area == so.lift_instrument_id)
                            for other_so in self.product_synthetic_order_mapping[prod].values()]):
                        # if we already have a LIFT for this, then do nothing
                        pass
                    else:
                        self.debug_log("Creating LIFT SO {} [{}]".format(so.identifier, prod))
                        payload = self.create_lift_synthetic_order_payload_register(so)
                        self.on_synthetic_order_register(prod, payload)

    @classmethod
    def get_available_synthetic_order_types(cls):
        return {
            "ArbitrageOrder": so_arbitrage_lead.ArbitrageOrder,
            "LiftOrder": so_arbitrage_lift.LiftOrder
        }
