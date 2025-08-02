import logging

import autotrader_core.common as COMMON
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

    new_additional_view = CONF.SyntheticOrderConfigField(caption="new additional view",
                                                         description="Name of the new additional view",
                                                         expected_type=PCF.InstrumentIdType,
                                                         mandatory=True)

    def act_old(self, localview, additional_views, timestamp):

        #additional_views.get_configured_view("new_additional_view", "10000302_1")
        #additional_view = additional_views.get_view_for_instrument("10100480", "10000302_1")

        if self.direction == 'buy':
            traded = localview.traded_volume_buy(self.slot_name)
        else:
            traded = localview.traded_volume_sell(self.slot_name)

        traded_qty = max(0., traded)
        price = localview.current_front_price(self.direction, self.broker_id)
        return self.create_slot(self.direction, self.quantity - traded_qty, price, info="info")

    def act(self, localview, additional_views, timestamp):
        other_view = additional_views.get_configured_view(self.new_additional_view, localview.product_id)

        local_buy = localview.current_front_price(COMMON.Direction.buy, self.broker_id)
        local_sell = localview.current_front_price(COMMON.Direction.sell, self.broker_id)

        other_buy = other_view.current_front_price(COMMON.Direction.buy, self.broker_id)
        other_sell = other_view.current_front_price(COMMON.Direction.sell, self.broker_id)

        spread_buy = 0
        spread_sell = 0
        if other_sell is not None and local_buy is not None:
            spread_buy = other_sell - local_buy
        if other_buy is not None and local_sell is not None:
            spread_sell = other_buy - local_sell

        if spread_sell > 0:
            return self.create_slot(COMMON.Direction.buy, 10, local_sell)
        elif spread_buy < 0:
            return self.create_slot(COMMON.Direction.sell, 10, local_buy)
        else:
            return self.remove()
