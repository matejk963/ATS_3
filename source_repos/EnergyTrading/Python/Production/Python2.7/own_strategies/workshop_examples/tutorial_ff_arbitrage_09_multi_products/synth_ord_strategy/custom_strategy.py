import logging

import autotrader_core.common as COMMON
import autotrader_synthetic.synthetic_order_strategies.synthetic_order_strategy_base as SYSTRAT
import so_arbitrage_lead
import so_arbitrage_lift
from constants import TTF_ICE, ITALY_BASELOAD

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
        print("DEBUG on_synthetic_order: ", payload)
        error = super(CustomStrategy, self).on_synthetic_order(payload)
        print(error)
        self._update_lift_orders()
        # import to still return the error, to make sure a rest call can get the response to this request
        return error

    def custom_on_order_book_update(self, orders, timestamp):
        for o in orders:
            print("DEBUG ORDER UPDATE: ", o.product.product_id, o.delivery_area_id, o.price, o.quantity, o.direction)
        # just call act, to trigger all product synthetic orders
        products = self.exchange.products.get_active_products()
        res = self.act(timestamp, products)
        self._update_lift_orders()
        return res

    def on_trade_update(self, trades, timestamp):
        res = super(CustomStrategy, self).on_trade_update(trades, timestamp)
        self._update_lift_orders()
        return res

    def create_lift_synthetic_order_payload_register(self, so):
        return {
            "operation": COMMON.SyntheticOrderOperations.register,
            "product_id": so.lift_product_id,
            "message_type": "synthetic_order",
            "synthetic_order_type": "LiftOrder",
            "identifier": "LIFT_" + so.slot_name,
            "configuration": {
                "slot_name": "LIFT_" + so.slot_name,
                "market_area": so.lift_instrument_id,
                "broker_id": so.lift_broker_id,
                "lead_instrument_id": so.market_area,
                "lead_slot_name": so.slot_name,
                "lead_product_id": so.own_product_id,
                "strategy_id": self.strategy_id

            }
        }

    def _update_lift_orders(self):
        for prod, sos in self.product_synthetic_order_mapping.items():
            for identifier, so in sos.items():
                if isinstance(so, so_arbitrage_lift.LiftOrder):
                    if any([(lead_so.slot_name.startswith("ArbitrageLead")
                             and lead_so.market_area == so.lead_instrument_id)
                            for lead_so in self.product_synthetic_order_mapping[so.lead_product_id].values()]):
                        # if we already have a LIFT for this, then do nothing
                        self.debug_log("Found LEAD for LIFT SO {} [{}]".format(so.identifier, prod))
                    else:
                        self.debug_log("Removing LIFT SO {} [{}]".format(so.identifier, prod))
                        payload = {"identifier": so.identifier, "synthetic_order_type": "LiftOrder"}
                        self.on_synthetic_order_delete(prod, payload)

                elif isinstance(so, so_arbitrage_lead.ArbitrageOrder):
                    if any([(lift_so.slot_name == "LIFT_" + so.slot_name
                             and lift_so.market_area == so.lift_instrument_id)
                            for lift_so in self.product_synthetic_order_mapping[so.lift_product_id].values()]):
                        # if we already have a LIFT for this, then do nothing
                        pass
                    else:
                        self.debug_log("Creating LIFT SO {} [{}]".format(so.identifier, prod))
                        payload = self.create_lift_synthetic_order_payload_register(so)
                        self.on_synthetic_order_register(so.lift_product_id, payload)

    @classmethod
    def get_available_synthetic_order_types(cls):
        return {
            "ArbitrageOrder": so_arbitrage_lead.ArbitrageOrder,
            "LiftOrder": so_arbitrage_lift.LiftOrder
        }
