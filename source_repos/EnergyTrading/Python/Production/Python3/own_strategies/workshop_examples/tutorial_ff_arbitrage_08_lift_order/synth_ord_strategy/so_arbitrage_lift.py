

import logging

import autotrader_lib.common as COMMON
import autotrader_lib.package_config_fields as PKG_CONF
import autotrader_synthetic.config_util as SYNCONF
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB

log = logging.getLogger("arbitrage.lift_order")


class LiftOrder(SYB.SyntheticOrderBase):
    lead_instrument_id = SYNCONF.SyntheticOrderConfigField(
        caption="lead_instrument_id",
        description="ID of the primary view, where initiating (lead) order is placed",
        expected_type=PKG_CONF.InstrumentIdType,
        mandatory=True
    )

    lead_slot_name = SYNCONF.SyntheticOrderConfigField(
        caption="lead_slot_name",
        description="Name of the initiating (lead) order slot",
        expected_type=str,
        mandatory=True
    )

    strategy_id = SYNCONF.SyntheticOrderConfigField(
        caption="strategy_id",
        description="ID of strategy for the SO registration",
        expected_type=str,
        mandatory=True
    )

    def get_open_position(self, localview, lead_view):
        # if net traded >0, we net bought
        net_traded_own = (localview.traded_volume_buy(self.slot_name)
                          - localview.traded_volume_sell(self.slot_name))
        net_traded_lead = (lead_view.traded_volume_buy(self.lead_slot_name)
                           - lead_view.traded_volume_sell(self.lead_slot_name))

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
        # please note the difference to additional_views.get_configured_view
        lead_view = additional_views.get_view_for_instrument(
            self.lead_instrument_id,
            localview.product_id
        )

        open_position, direction, price = self.get_open_position(localview, lead_view)

        print(("LIFT-SO-ACT [OpenPos]:  {}: {}_{}@{}".format(
            self.market_area, direction, open_position, price
        )))

        if open_position > 0:
            return self.create_slot(direction, open_position, price, info="lift")
        else:
            return self.remove()
