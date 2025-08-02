import logging

import autotrader_core.common as COMMON
import autotrader_synthetic.config_util as SYNCONF
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB

log = logging.getLogger("arbitrage.arbitrage_order")

QUANTITY_TICK_SIZE = 10


class ArbitrageOrder(SYB.SyntheticOrderBase):
    lift_instrument_id = SYNCONF.ConfigOptionDescriptor(
        "lift_instrument_id", str,
        "Name of the other additional view, as used in the strategy template",
        required=True
    )

    def act(self, localview, additional_views, timestamp):
        lift_view = additional_views.get_view_for_instrument(self.lift_instrument_id, localview.product_id)

        local_buy = localview.current_front_price(COMMON.Direction.buy, self.broker_id)
        local_sell = localview.current_front_price(COMMON.Direction.sell, self.broker_id)
        lift_buy = lift_view.current_front_price(COMMON.Direction.buy, self.broker_id)
        lift_sell = lift_view.current_front_price(COMMON.Direction.sell, self.broker_id)
        print("LEAD-SO-ACT [Public BUY/SELL]: A: {}: {}//{} --- B: {}: {}//{}".format(
            self.market_area, local_buy, local_sell, self.lift_instrument_id, lift_buy, lift_sell)
        )
        # default to 0, needs to be unequal 0 to do something.
        spread_buy = 0
        spread_sell = 0
        if lift_sell is not None and local_buy is not None:
            # local buy: 20
            # other sell: 60
            # spread buy: 40
            # if we sell in local, and buy in other, we lose 40
            spread_buy = lift_sell - local_buy
        if lift_buy is not None and local_sell is not None:
            # local sell: 20
            # other buy: 60
            # spread sell: 40
            # if we buy in local, and sell in other, we profit 40
            spread_sell = lift_buy - local_sell

        if spread_buy < 0:
            return self.create_slot(COMMON.Direction.sell, QUANTITY_TICK_SIZE, local_buy, info="lead",
                                    price_range_lo=local_buy - 10, price_range_hi=local_buy + 10)
        elif spread_sell > 0:
            return self.create_slot(COMMON.Direction.buy, QUANTITY_TICK_SIZE, local_sell, info="lead",
                                    price_range_lo=local_sell - 10, price_range_hi=local_sell + 10)
        else:
            return self.remove()
