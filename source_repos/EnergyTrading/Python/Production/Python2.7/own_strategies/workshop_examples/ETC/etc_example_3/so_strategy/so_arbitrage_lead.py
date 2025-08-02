import logging

import autotrader_lib.package_config_fields as PCF
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SOB
import autotrader_synthetic.config_util as CONF


log = logging.getLogger('example_2')

class ArbitrageOrder(SOB.SyntheticOrderBase):
    direction = CONF.SyntheticOrderConfigField(caption="direction",
                                               description="The side of the orderbook: buy or sell",
                                               expected_type=PCF.Enum(allowed_values=['buy', 'sell']),
                                               mandatory=True)
    quantity = CONF.SyntheticOrderConfigField(caption="quantity",
                                              description="The maximum quantity that is allowed to be traded",
                                              expected_type=float,
                                              mandatory=True)

    def act(self, localview, additional_views, timestamp):
        if self.direction == 'buy':
            traded = localview.traded_volume_buy(self.slot_name)
        else:
            traded = localview.traded_volume_sell(self.slot_name)

        traded_qty = max(0., traded)
        price = localview.current_front_price(self.direction, self.broker_id)
        return self.create_slot(self.direction, self.quantity - traded_qty, price, info="info")
