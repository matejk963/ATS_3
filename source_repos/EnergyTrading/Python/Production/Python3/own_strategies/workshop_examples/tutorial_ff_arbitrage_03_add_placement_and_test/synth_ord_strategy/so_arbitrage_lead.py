import logging

import autotrader_lib.package_config_fields as PKG_CONF

import autotrader_synthetic.config_util as SYNCONF
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB

log = logging.getLogger("arbitrage.arbitrage_order")

QUANTITY_TICK_SIZE = 1


class ArbitrageOrder(SYB.SyntheticOrderBase):
    direction = SYNCONF.SyntheticOrderConfigField(caption="direction",
                                                  description="The side of the order_book: buy or sell",
                                                  expected_type=PKG_CONF.Enum(allowed_values=["buy", "sell"]),
                                                  mandatory=True)

    quantity = SYNCONF.SyntheticOrderConfigField(caption="quantity",
                                                 description="The maximum quantity that is allowed to be traded",
                                                 expected_type=float,
                                                 mandatory=True)

    def act(self, localview, additional_views, timestamp):

        if self.direction == "buy":
            net_traded = localview.traded_volume_buy(self.slot_name)
        else:
            net_traded = localview.traded_volume_sell(self.slot_name)

        traded_qty = max(0., net_traded)
        price = localview.current_front_price(self.direction, self.broker_id)

        return self.create_slot(self.direction, self.quantity - traded_qty, price)
