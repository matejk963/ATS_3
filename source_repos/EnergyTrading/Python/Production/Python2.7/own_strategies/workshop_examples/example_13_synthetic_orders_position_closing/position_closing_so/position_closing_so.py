import numbers

import autotrader_core.common as COMMON

import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYBASE
import autotrader_synthetic.config_util as CONF


class PositionClosingBehavior(SYBASE.SyntheticOrderBase):
    """ We will be registering this synthetic order on various products via the synthetic strategy """

    slot_size = CONF.SyntheticOrderConfigField(caption="slot_size",
                                               description="What slot size it can place maximum on the market",
                                               expected_type=int)

    position = CONF.SyntheticOrderConfigField(caption="position",
                                              expected_type=int,
                                              description="Total position that is desired to be traded")

    spread = CONF.SyntheticOrderConfigField(caption="spread",
                                            expected_type=float,
                                            description="How far from best price to be")

    def act(self, localview, additional_views, timestamp):

        traded_volume_buy = localview.traded_volume_buy(self.slot_name)
        traded_volume_sell = localview.traded_volume_sell(self.slot_name)

        total_traded_volume = traded_volume_buy - traded_volume_sell

        remaining_volume = self.position - total_traded_volume

        if remaining_volume == 0:
            return None

        # we need to buy more
        elif remaining_volume > 0:

            front_sell_price = localview.current_front_price(COMMON.Direction.sell)
            final_quantity = min([remaining_volume, self.slot_size])
            if front_sell_price:
                return self.create_slot(direction=COMMON.Direction.buy,
                                        quantity=final_quantity,
                                        price=front_sell_price + self.spread)

        # we need to sell more:
        elif remaining_volume < 0:

            front_buy_price = localview.current_front_price(COMMON.Direction.buy)

            final_quantity = min([abs(remaining_volume), self.slot_size])

            if front_buy_price:
                return self.create_slot(direction=COMMON.Direction.sell,
                                        quantity=final_quantity,
                                        price=front_buy_price - self.spread)
