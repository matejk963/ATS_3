import logging
import numbers

import autotrader_core.common as COMMON
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

    other_instrument_name = SYNCONF.ConfigOptionDescriptor(
        "other_instrument_name", str,
        "Name of the other additional view, as used in the strategy template",
        required=True
    )

    def act(self, localview, additional_views, timestamp):
        other_view = additional_views.get_configured_view(self.other_instrument_name, localview.product_id)

        local_buy = localview.current_front_price(COMMON.Direction.buy, self.broker_id)
        local_sell = localview.current_front_price(COMMON.Direction.sell, self.broker_id)
        other_buy = other_view.current_front_price(COMMON.Direction.buy, self.broker_id)
        other_sell = other_view.current_front_price(COMMON.Direction.sell, self.broker_id)

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
            return self.create_slot(COMMON.Direction.sell, QUANTITY_TICK_SIZE, local_buy)
        elif spread_sell > 0:
            return self.create_slot(COMMON.Direction.buy, QUANTITY_TICK_SIZE, local_sell)
        else:
            return self.remove()
