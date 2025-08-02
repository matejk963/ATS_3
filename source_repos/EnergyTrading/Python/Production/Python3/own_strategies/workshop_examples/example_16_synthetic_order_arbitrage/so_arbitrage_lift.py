
import logging

import autotrader_lib.common as COMMON
import autotrader_synthetic.config_util as SYNCONF
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB

log = logging.getLogger("arbitrage.lift_order")


class LiftOrder(SYB.SyntheticOrderBase):
    lead_instrument_id = SYNCONF.ConfigOptionDescriptor(
        "lead_instrument_id", str,
        "Name of the lead instrument additional view, as used in the strategy template",
        required=True
    )

    lead_slot_name = SYNCONF.ConfigOptionDescriptor(
        "lead_slot_name", str,
        "Name of the other leading slot",
        required=True
    )

    lead_product_id = SYNCONF.ConfigOptionDescriptor(
        "lead_product_id", str,
        "Name of the other leading so's product id",
        required=True
    )

    strategy_id = SYNCONF.ConfigOptionDescriptor(
        "strategy_id", str,
        "strategy_id for logging",
        required=True
    )

    def get_open_position(self, localview, other_view):
        # if net traded >0, we net bought
        net_traded_own = localview.traded_volume_buy(self.slot_name) - localview.traded_volume_sell(self.slot_name)
        net_traded_lead = (other_view.traded_volume_buy(self.lead_slot_name)
                           - other_view.traded_volume_sell(self.lead_slot_name))

        log.debug("[{}] LIFT-SO-ACT, BROKER:{},  TRADED_OWN {}[{}]: {}, TRADED_LEAD {} [{}]: {}".format(
            self.strategy_id, self.broker_id, self.market_area, localview.product_id, net_traded_own,
            self.lead_instrument_id, self.lead_product_id, net_traded_lead)
        )

        # if net open position >0, we need to place a buy, else we place sell
        # example
        # lead sold 10 => -10
        # lift bought 5 => 5
        # net open: 5 = -(-10+5)
        net_open_position = - (net_traded_lead + net_traded_own)

        if net_open_position > 0:
            direction = COMMON.Direction.buy
            price = localview.current_front_price(COMMON.Direction.sell)
        else:
            direction = COMMON.Direction.sell
            price = localview.current_front_price(COMMON.Direction.buy)

        return abs(round(net_open_position, 6)), direction, price

    def act(self, localview, additional_views, timestamp):
        lead_view = additional_views.get_view_for_instrument(
            self.lead_instrument_id,
            self.lead_product_id,
        )

        open_position, direction, price = self.get_open_position(localview, lead_view)

        log.debug("[{}] LIFT-SO-ACT [OpenPos]:  {}: {}_{}@{}".format(
            self.strategy_id, self.market_area, direction, open_position, price
        ))

        if open_position > 0:
            return self.create_slot(direction, open_position, price, info="lift")
        else:
            return self.remove()
