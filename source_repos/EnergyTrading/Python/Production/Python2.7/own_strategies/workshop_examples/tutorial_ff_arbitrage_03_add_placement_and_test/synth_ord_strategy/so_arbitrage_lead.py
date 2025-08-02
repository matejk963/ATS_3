import numbers
import logging

import autotrader_synthetic.config_util as SYNCONF
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB

log = logging.getLogger("arbitrage.arbitrage_order")

QUANTITY_TICK_SIZE = 1


class ArbitrageOrder(SYB.SyntheticOrderBase):
    direction = SYNCONF.EnumerateConfigOptionDescriptor("direction", basestring,
                                                        "The side of the order_book: buy or sell",
                                                        allowed_values=["buy", "sell"], required=True)

    quantity = SYNCONF.ConfigOptionDescriptor("quantity", numbers.Number,
                                              "The maximum quantity that is allowed to be traded",
                                              required=True)

    def act(self, localview, additional_views, timestamp):

        if self.direction == "buy":
            net_traded = localview.traded_volume_buy(self.slot_name)
        else:
            net_traded = localview.traded_volume_sell(self.slot_name)

        qty = max(0., net_traded)
        price = localview.current_front_price(self.direction, self.broker_id)

        return self.create_slot(self.direction, qty, price)
