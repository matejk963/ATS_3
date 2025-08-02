import autotrader_synthetic.synthetic_orders.synthetic_order_base as SOB
import autotrader_lib.package_config_fields as PCF
import autotrader_synthetic.config_util as CONF
import autotrader_core.common as COMMON


class LiftOrder(SOB.SyntheticOrderBase):
    lead_instrument_id = CONF.SyntheticOrderConfigField(caption="lift_instrument_id",
                                                        description="Name of the new additional view",
                                                        expected_type=PCF.InstrumentIdType,
                                                        mandatory=True)
    lead_slot_name = CONF.SyntheticOrderConfigField(caption="lead_slot_name",
                                                    description="lead slot_name",
                                                    expected_type=str,
                                                    mandatory=True)
    strategy_id = CONF.SyntheticOrderConfigField(caption="strategy_id",
                                                 description="strategy_id",
                                                 expected_type=str,
                                                 mandatory=True)

    def get_open_position(self, localview, lead_view):
        net_traded_lift = (localview.traded_volume_buy(self.slot_name) - localview.traded_volume_buy(self.slot_name))
        net_traded_lead = (lead_view.traded_volume_buy(self.lead_slot_name) - lead_view.traded_volume_buy(self.lead_slot_name))

        net_open_position = -(net_traded_lead + net_traded_lift)

        if net_open_position > 0:
            direction = COMMON.Direction.buy
            price = localview.current_front_price(COMMON.Direction.sell)
        else:
            direction = COMMON.Direction.sell
            price = localview.current_front_price(COMMON.Direction.buy)
        return abs(net_open_position), direction, price

    def act(self, localview, additional_view, timestamp):
        lead_view = additional_view.get_view_for_instrument(self.lead_instrument_id, localview.product_id)

        open_position, direction, price = self.get_open_position(localview, lead_view)

        if open_position > 0:
            return self.create_slot(direction, open_position, price)
        else:
            return self.remove()
