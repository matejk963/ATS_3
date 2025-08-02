import logging

import autotrader_lib.common as COMMON
import autotrader_lib.package_config_fields as PKG_CONF
import autotrader_synthetic.config_util as SYNCONF
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB

log = logging.getLogger("arbitrage.arbitrage_order")

QUANTITY_TICK_SIZE = 1


class ArbitrageOrder(SYB.SyntheticOrderBase):
    direction = SYNCONF.SyntheticOrderConfigField(
        caption="direction",
        description="The side of the order_book: buy or sell",
        expected_type=PKG_CONF.Enum(allowed_values=["buy", "sell"]),
        mandatory=True
    )

    quantity = SYNCONF.SyntheticOrderConfigField(
        caption="quantity",
        description="The maximum quantity that is allowed to be traded",
        expected_type=float,
        mandatory=True
    )

    other_instrument_name = SYNCONF.SyntheticOrderConfigField(
        caption="other_instrument_name",
        description="Name of the other additional view, as used in the strategy template",
        expected_type=PKG_CONF.InstrumentIdType,
        mandatory=True
    )

    def act(self, localview, additional_views, timestamp):
        other_view = additional_views.get_configured_view(self.other_instrument_name, localview.product_id)

        local_buy = localview.current_front_price(COMMON.Direction.buy, self.broker_id)
        local_sell = localview.current_front_price(COMMON.Direction.sell, self.broker_id)
        other_buy = other_view.current_front_price(COMMON.Direction.buy, self.broker_id)
        other_sell = other_view.current_front_price(COMMON.Direction.sell, self.broker_id)

        # default to 0, needs to be unequal with 0 to do something.
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

        if spread_buy < 0:      # consequence: spread_sell < 0 also
            return self.create_slot(COMMON.Direction.sell, QUANTITY_TICK_SIZE, local_buy)
        elif spread_sell > 0:   # consequence: spread_buy > 0 also
            return self.create_slot(COMMON.Direction.buy, QUANTITY_TICK_SIZE, local_sell)
        else:                   # no profit from arbitrage
            return self.remove()
