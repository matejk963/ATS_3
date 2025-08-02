import logging
import autotrader_synthetic.synthetic_order_strategies.synthetic_order_strategy_base as SYSB
import autotrader_core.common as COMMON
import so_arbitrage_lead
import so_arbitrage_lift


GAS_YEARS = "10000301"
BROKER_ID = "37"
GAS_YR22_ITEM_ID = "21"
GAS_PRODUCT_ID = GAS_YEARS + "_" + GAS_YR22_ITEM_ID

log = logging.getLogger("example_1")


class CustomStrategy(SYSB.SyntheticOrderStrategyBase):
    default_payload = {}

    def __init__(self, *args, **kwargs):
        super(CustomStrategy, self).__init__(*args, **kwargs)
        self.log = log

    def on_strategy_configuration_update(self, strategy_json):
        super(CustomStrategy, self).on_strategy_configuration_update(strategy_json)

    def on_synthetic_order(self, payload):
        super(CustomStrategy, self).on_synthetic_order(payload)
        self.update_lift_order()

    def custom_on_order_book_update(self, orders, timestamp):
        super(CustomStrategy, self).custom_on_order_book_update(orders, timestamp)
        self.update_lift_order()

    def custom_on_trade_update(self, trades, timestamp):
        super(CustomStrategy, self).custom_on_trade_update(trades, timestamp)
        self.update_lift_order()

    def update_lift_order(self):
        for product, sos in self.product_synthetic_order_mapping.items():
            for identifier, so in sos.items():
                if isinstance(so, so_arbitrage_lift.LiftOrder):
                    if any([(other_so.slot_name == "LEAD" and other_so.market_area == so.lead_instrument_id)
                        for other_so in self.product_synthetic_order_mapping[product].values()]):
                            pass
                    else:
                        payload = {"identifier": so.identifier, "syntetic_order_type": "LiftOrder"}
                        self.on_synthetic_order_delete(product, payload)
                if isinstance(so, so_arbitrage_lead.ArbitrageOrder):
                    if any([(other_so.slot_name == "LIFT" and other_so.market_area == so.lift_instrument_id)
                            for other_so in self.product_synthetic_order_mapping[product].values()]):
                        pass
                    else:
                        payload = {
                            "operation": COMMON.SyntheticOrderOperations.register,
                            "product_id": GAS_PRODUCT_ID,
                            "message_type": "synthetic_order",
                            "synthetic_order_type": "LiftOrder",
                            "identifier": "LIFT",
                            "configuration": {
                                "slot_name": "LIFT",
                                "market_area": so.lift_instrument_id,
                                "broker_id": BROKER_ID,
                                "lead_instrument_id": so.market_area,
                                "lead_slot_name": so.slot_name,
                                "strategy_id": self.strategy_id
            }
        }
                        self.on_synthetic_order_register(product, payload)

    @classmethod
    def get_available_synthetic_order_types(cls):
        return {"ArbitrageOrder": so_arbitrage_lead.ArbitrageOrder,
                "LiftOrder": so_arbitrage_lift.LiftOrder}

