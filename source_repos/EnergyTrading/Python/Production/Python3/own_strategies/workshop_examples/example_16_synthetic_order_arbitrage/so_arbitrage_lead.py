
import logging

import autotrader_lib.common as COMMON
import autotrader_synthetic.config_util as SYNCONF
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB

log = logging.getLogger("arbitrage.arbitrage_order_08")

QUANTITY_TICK_SIZE = 10


class ArbitrageOrder(SYB.SyntheticOrderBase):

    own_product_id = SYNCONF.ConfigOptionDescriptor(
        "own_product_id", str,
        "Own Product ID, which is passed to the 2nd arbitrage leg synthetic order as 'other'",
        required=True
    )

    lift_product_id = SYNCONF.ConfigOptionDescriptor(
        "lift_product_id", str,
        "Product ID of the Gas product to be used as lift order, which closes this orders 2nd leg",
        required=True
    )

    lift_instrument_id = SYNCONF.ConfigOptionDescriptor(
        "lift_instrument_id", str,
        "Name of the lift instrument additional view, as used in the strategy template",
        required=True
    )

    lift_broker_id = SYNCONF.ConfigOptionDescriptor(
        "lift_broker_id", str,
        "Broker ID trading on the Gas product",
        required=True
    )

    strategy_id = SYNCONF.ConfigOptionDescriptor(
        "strategy_id", str,
        "strategy_id for logging",
        required=True
    )

    def act(self, localview, additional_views, timestamp):
        other_view = additional_views.get_view_for_instrument(
            self.lift_instrument_id,
            self.lift_product_id
        )
        local_buy = localview.current_front_price(COMMON.Direction.buy, self.broker_id)
        local_sell = localview.current_front_price(COMMON.Direction.sell, self.broker_id)
        other_buy = other_view.current_front_price(COMMON.Direction.buy, self.broker_id)
        other_sell = other_view.current_front_price(COMMON.Direction.sell, self.broker_id)

        log.debug("[{}] LEAD-SO-ACT, BROKER:{},  [Public BUY/SELL]: A: {}[{}]: {}//{} --- B: {}[{}]: {}//{}".format(
            self.strategy_id, self.broker_id, self.market_area, self.own_product_id, local_buy, local_sell,
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
