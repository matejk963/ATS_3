import logging

import autotrader_lib.common as COMMON
import autotrader_synthetic.config_util as SYNCONF
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB
from .strategy_stats import StrategyStats
from .own_tools.misc import round_to_tick, max_with_none_check, min_with_none_check
from .own_tools.instrument_key import InstrumentKey


log = logging.getLogger("arbitrage.lift_order")


class LiftOrder(SYB.SyntheticOrderBase):
    product_id = SYNCONF.ConfigOptionDescriptor(
        "product_id", str,
        "Name of the so's product id",
        required=True
    )

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

    lead_broker_id = SYNCONF.ConfigOptionDescriptor(
        "lead_broker_id", str,
        "Broker ID trading on the Gas product",
        required=True
    )

    lift_broker_ids = SYNCONF.ConfigOptionDescriptor(
        "lift_broker_ids", list,
        "Broker ID trading on the Gas product",
        required=True
    )

    strategy_id = SYNCONF.ConfigOptionDescriptor(
        "strategy_id", str,
        "strategy_id for logging",
        required=True
    )

    strategy_stats_dict = SYNCONF.SyntheticOrderConfigField(
        caption="strategy_stats_dict",
        expected_type=dict,
        description="Object for strategy statistics"
    )
    margin = SYNCONF.SyntheticOrderConfigField(
        caption="margin",
        expected_type=float,
        description="How far from spread mid price to be",
    )

    margin_for_closing = SYNCONF.SyntheticOrderConfigField(
        caption="margin_for_closing",
        expected_type=float,
        description="Margin in EUR for closing mishit trades",
    )

    closing_in_profit_flag = SYNCONF.SyntheticOrderConfigField(
        caption="closing_in_profit_flag",
        expected_type=float,
        description="Closing mishit position in profit allowed?",
    )

    max_quantity = SYNCONF.SyntheticOrderConfigField(
        caption="max_quantity",
        expected_type=float,
        description="What is the maximum slot_size",
    )

    idle_threshold = SYNCONF.SyntheticOrderConfigField(
        caption="idle_threshold",
        expected_type=float,
        description="Min price movement threshold for quoting orders",
    )

    verbose = SYNCONF.SyntheticOrderConfigField(
        caption="verbose",
        expected_type=bool,
        description="logging bool",
    )

    reset_bool = SYNCONF.SyntheticOrderConfigField(
        caption="reset_bool",
        expected_type=bool,
        description="autoTrader reset boolean",
    )

    def get_open_position(self, localview, other_view):
        # if net traded >0, we net bought
        # net_traded_own = (localview.traded_volume_buy(self.slot_name)
        #                   - localview.traded_volume_sell(self.slot_name))
        # net_traded_lead = (other_view.traded_volume_buy(self.lead_slot_name)
        #                    - other_view.traded_volume_sell(self.lead_slot_name))

        strategy_stats = StrategyStats.from_dict(self.strategy_stats_dict)


        if self.slot_name in strategy_stats.slot_dict:
            net_traded_own=strategy_stats.slot_dict[self.slot_name]['net_volume']
            last_price_own=strategy_stats.slot_dict[self.slot_name]['last_price']
            # last_delivery_end_own=strategy_stats.slot_dict[self.slot_name]['last_delivery_end']
            last_order_price_own=strategy_stats.slot_dict[self.slot_name]['last_order_price']

        else:
            net_traded_own=0
            last_price_own=None
            # last_delivery_end_own=None
            last_order_price_own=None


        if self.lead_slot_name in strategy_stats.slot_dict:
            net_traded_lead=strategy_stats.slot_dict[self.lead_slot_name]['net_volume']
            last_price_lead = strategy_stats.slot_dict[self.lead_slot_name]['last_price']
            # last_delivery_end_lead = strategy_stats.slot_dict[self.lead_slot_name]['last_delivery_end']
        else:
            net_traded_lead=0
            last_price_lead=None
            # last_delivery_end_lead=None

        # if net open position >0, we need to place a buy, else we place sell
        # example
        # lead sold 10 => -10
        # lift bought 5 => 5
        # net open: 5 = -(-10+5)
        net_open_position = - (net_traded_lead + net_traded_own)


        if net_open_position > 0:
            direction = COMMON.Direction.buy
            price_own_dict = {broker:localview.current_front_price(COMMON.Direction.sell,broker) for broker in
                              [self.lead_broker_id]+self.lift_broker_ids}
            best_broker, best_price = min_with_none_check(price_own_dict)

            price_own, broker_own = best_price, best_broker


            price_mm = localview.current_front_price(COMMON.Direction.buy)

            if self.verbose:
                log.debug(
                    "[{}] [{}] price_own_dict: {}, best_price: {}, best_broker: {}, last_price_lead: {}".format(
                        self.strategy_id, self.slot_name, price_own_dict, best_price,best_broker, last_price_lead)
                )

            if 'ASK' in self.slot_name:
                price_last=last_price_lead
            else:
                price_last=last_price_own

            if self.closing_in_profit_flag == 0.0 and price_last and price_mm:
                price_mm=max(price_last-self.tick_size, price_mm)

            if price_own and price_own<=round_to_tick(price_last+self.margin_for_closing,self.tick_size):
                price=price_own
                broker_id=broker_own
            elif price_mm:
                if last_order_price_own and round_to_tick(abs(price_mm-last_order_price_own),self.tick_size)<=self.idle_threshold:
                    price=last_order_price_own
                else:
                    price=round_to_tick(price_mm,self.tick_size)
                broker_id = self.lead_broker_id
            else:
                price=-1
                broker_id = self.lead_broker_id

        else:
            direction = COMMON.Direction.sell
            price_own_dict = {broker:localview.current_front_price(COMMON.Direction.buy,broker) for broker in
                              [self.lead_broker_id]+self.lift_broker_ids}

            best_broker, best_price = max_with_none_check(price_own_dict)

            price_own, broker_own = best_price, best_broker
            price_mm = localview.current_front_price(COMMON.Direction.sell)

            if self.verbose:
                log.debug(
                    "[{}] [{}] price_own_dict: {}, best_price: {}, best_broker: {}, last_price_lead: {}".format(
                        self.strategy_id, self.slot_name, price_own_dict, best_price,best_broker,last_price_lead)
                )

            if 'BID' in self.slot_name:
                price_last=last_price_lead
            else:
                price_last=last_price_own

            if self.closing_in_profit_flag == 0.0 and price_last and price_mm:
                price_mm=min(price_last+self.tick_size, price_mm)

            if price_own and price_last and round_to_tick(price_own+self.margin_for_closing,self.tick_size)>=price_last:
                price=price_own
                broker_id=broker_own

            elif price_mm:
                if last_order_price_own and round_to_tick(abs(price_mm-last_order_price_own),self.tick_size)<=self.idle_threshold:
                    price=last_order_price_own
                else:
                    price=round_to_tick(price_mm,self.tick_size)
                broker_id = self.lead_broker_id
            else:
                price=-1
                broker_id = self.lead_broker_id

        if self.verbose:
            log.debug("[{}] LIFT-SO-ACT, BROKER:{},  TRADED_OWN {}[{}]: {}, TRADED_LEAD {} [{}]: {}".format(
                self.strategy_id, self.broker_id, self.market_area, localview.product_id, net_traded_own,
                self.lead_instrument_id, self.lead_product_id, net_traded_lead)
            )
        # # OR find price from trades
        # lead_trades = other_view._product.trades.get(
        #     buy_delivery_area=None,
        #     sell_delivery_area=None,
        #     delivery_area=other_view.market_area,
        #     portfolio_key=other_view.strategy_id,
        #     trade_filter=COMMON.TradeFilter.own,
        #     timerange=None
        # )
        # if len(lead_trades) > 0:
        #     print(len(lead_trades))

        return abs(round(net_open_position, 6)), direction, price, broker_id

    def act(self, localview, additional_views, timestamp):
        # check what the lead has been doing
        own_instkey = InstrumentKey(self.market_area, self.product_id)
        other_instkey = InstrumentKey(self.lead_instrument_id, self.lead_product_id)
        if own_instkey == other_instkey:
            lead_view = localview
        else:
            lead_view = additional_views.get_view_for_instrument(
                self.lead_instrument_id,
                self.lead_product_id,
            )

        open_position, direction, price, broker_id = self.get_open_position(
            localview, lead_view
        )

        self.inst_key=self.market_area + "_" + self.lead_product_id

        strategy_stats = StrategyStats.from_dict(self.strategy_stats_dict)
        ask_not_balancing = ('ASK' in self.identifier and not strategy_stats.balancing_dict[self.inst_key]['ASK'])
        bid_not_balancing = ('BID' in self.identifier and not strategy_stats.balancing_dict[self.inst_key]['BID'])
        cross_not_balancing = not strategy_stats.balancing_dict[self.inst_key]['CROSS']

        # Do not need to check for negative prices

        if open_position > 0  and not self.reset_bool and not strategy_stats.bool_dict['hard_stop_loss']: # and (bid_not_balancing or ask_not_balancing)
            #logging the details
            log.debug("[{}] [{}] LIFT-SO-ACT-CREATE-SLOT [OpenPos]:  {}--{}: {}_{}@{} BROKER_ID: {}".format(
                self.strategy_id, self.identifier, self.market_area, self.lead_instrument_id, direction, open_position,
                price, broker_id
            ))
            self.broker_id=broker_id
            volume=min(open_position, self.max_quantity)
            return self.create_slot(direction, volume, price, info="lift")
        else:
            # logging the details
            log.debug("[{}] [{}] [{}] LIFT-SO-ACT-REMOVE-SLOT: [OP: {},  BNB: {}, ANB: {}, CNB: {}, RB: {}, HSL: {}]".format(
                self.strategy_id, self.identifier, self.market_area, open_position,bid_not_balancing, ask_not_balancing,
                cross_not_balancing, self.reset_bool, strategy_stats.bool_dict['hard_stop_loss']
            ))
            return self.remove()
