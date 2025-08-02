
import logging

import autotrader_lib.common as COMMON
import autotrader_lib.package_config_fields as PKG_CONF
import autotrader_synthetic.config_util as SYNCONF
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB

log = logging.getLogger("arbitrage.arbitrage_order")

QUANTITY_TICK_SIZE = 10


class ArbitrageOrder(SYB.SyntheticOrderBase):
    controllable_via_rest_api = True

    lift_product_id = SYNCONF.SyntheticOrderConfigField(
        caption="lift_product_id",
        description="Product ID of the Gas product to be used as lift order, which closes this orders 2nd leg",
        expected_type=PKG_CONF.CombinedSequenceItemIdType,
        mandatory=True
    )

    lift_instrument_id = SYNCONF.SyntheticOrderConfigField(
        caption="lift_instrument_id",
        description="ID of the lift instrument additional view, as used in the strategy template",
        expected_type=PKG_CONF.InstrumentIdType,
        mandatory=True
    )

    lift_broker_id = SYNCONF.SyntheticOrderConfigField(
        caption="lift_broker_id",
        description="Broker ID trading on the Gas product",
        expected_type=PKG_CONF.BrokerIdType,
        mandatory=True
    )

    strategy_id = SYNCONF.SyntheticOrderConfigField(
        caption="strategy_id",
        description="ID of strategy for the SO registration",
        expected_type=str,
        mandatory=True
    )

    @property
    def so_siblings(self):
        return [{
            "product_id": self.lift_product_id,
            "message_type": "synthetic_order",
            "synthetic_order_type": "LiftOrder",
            "identifier": "LIFT_" + self.slot_name,
            "configuration": {
                "slot_name": "LIFT_" + self.slot_name,
                "market_area": self.lift_instrument_id,
                "broker_id": self.lift_broker_id,
                "lead_instrument_id": self.market_area,
                "lead_slot_name": self.slot_name,
                "lead_product_id": self.product_id,
                "strategy_id": self.strategy_id
            }
        }]

    def act(self, localview, additional_views, timestamp):
        other_view = additional_views.get_view_for_instrument(
            self.lift_instrument_id,
            self.lift_product_id
        )

        local_buy = localview.current_front_price(COMMON.Direction.buy, self.broker_id)
        local_sell = localview.current_front_price(COMMON.Direction.sell, self.broker_id)
        other_buy = other_view.current_front_price(COMMON.Direction.buy, self.lift_broker_id)
        other_sell = other_view.current_front_price(COMMON.Direction.sell, self.lift_broker_id)

        log.debug("[{}] LEAD-SO-ACT, BROKER:{},  [Public BUY/SELL]: A: {}[{}]: {}//{} --- B: {}[{}]: {}//{}".format(
            self.strategy_id, self.broker_id, self.market_area, self.product_id, local_buy, local_sell,
            self.lift_instrument_id, self.lift_product_id, other_buy, other_sell)
        )
        # default to 0, needs to be unequal 0 to do something.
        spread_buy = 0
        spread_sell = 0
        if other_sell is not None and local_buy is not None:
            # local buy: 20
            # other sell: 60
            # spread buy: 40
            # if we sell in local, and buy in other, we lose 40
            spread_buy = other_sell - local_buy
        if other_buy is not None and local_sell is not None:
            # local sell: 20
            # other buy: 60
            # spread sell: 40
            # if we buy in local, and sell in other, we profit 40
            spread_sell = other_buy - local_sell

        if spread_buy < 0:
            return self.create_slot(COMMON.Direction.sell, QUANTITY_TICK_SIZE, local_buy, info="lead")
        elif spread_sell > 0:
            return self.create_slot(COMMON.Direction.buy, QUANTITY_TICK_SIZE, local_sell, info="lead")
        else:
            return self.remove()
