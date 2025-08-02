import logging

import autotrader_core.common as COMMON
import autotrader_synthetic.config_util as SYNCONF
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB
from strategy_stats import StrategyStats, get_price_diff_depth, aon_check
from own_tools.misc import round_to_tick, max_with_none_check, min_with_none_check


log = logging.getLogger("arbitrage.arbitrage_order")

#QUANTITY_TICK_SIZE = 10


class ArbitrageOrder(SYB.SyntheticOrderBase):

    own_product_id = SYNCONF.ConfigOptionDescriptor(
        "own_product_id", basestring,
        "Own Product ID, which is passed to the 2nd arbitrage leg synthetic order as 'other'",
        required=True
    )

    lift_slot_name = SYNCONF.ConfigOptionDescriptor(
        "lift_slot_name", str,
        "Name of the lifting slot",
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

    margin = SYNCONF.SyntheticOrderConfigField(
        caption="margin",
        expected_type=float,
        description="How far from spread mid price to be",
    )

    slot_size = SYNCONF.SyntheticOrderConfigField(
        caption="slot_size",
        description="What slot size it can place maximum on the market",
        expected_type=float,
    )

    strategy_stats_dict = SYNCONF.SyntheticOrderConfigField(
        caption="strategy_stats_dict",
        expected_type=dict,
        description="Object for strategy statistics"
    )

    max_quantity = SYNCONF.SyntheticOrderConfigField(
        caption="max_quantity",
        expected_type=float,
        description="What is the maximum slot_size",
    )

    market_volume_check_flag = SYNCONF.SyntheticOrderConfigField(
        caption="market_volume_check_flag",
        expected_type=float,
        description="Should the strategy check market depth before placing LEAD order?",
    )

    ql_max = SYNCONF.SyntheticOrderConfigField(
        caption="maximal_allowed_queue_lag",
        expected_type=float,
        description="Maximal allowed queue lag for strategy",
    )

    def act(self, localview, additional_views, timestamp):
        other_view = additional_views.get_view_for_instrument(
            self.lift_instrument_id,
            self.lift_product_id
        )

        strategy_stats = StrategyStats.from_dict(self.strategy_stats_dict)

        self.local_buy = localview.current_front_price(COMMON.Direction.buy, self.broker_id)
        self.local_sell = localview.current_front_price(COMMON.Direction.sell, self.broker_id)

        # Calculate best broker price and volume for buying among the lift brokers
        other_buy_price_dict = {broker: other_view.current_front_price(COMMON.Direction.buy, broker) for broker in
                                self.lift_broker_ids}
        other_buy_volume_dict = {broker: other_view.current_front_volume(COMMON.Direction.buy, broker) for broker in
                                 self.lift_broker_ids}

        best_buy_broker, best_buy_price = max_with_none_check(other_buy_price_dict)
        best_buy_volume = other_buy_volume_dict.get(best_buy_broker)

        # Calculate best broker price and volume for selling among the lift brokers
        other_sell_price_dict = {broker: other_view.current_front_price(COMMON.Direction.sell, broker) for broker in
                                 self.lift_broker_ids}
        other_sell_volume_dict = {broker: other_view.current_front_volume(COMMON.Direction.sell, broker) for broker in
                                  self.lift_broker_ids}

        best_sell_broker, best_sell_price = min_with_none_check(other_sell_price_dict)
        best_sell_volume = other_sell_volume_dict.get(best_sell_broker)

        log.debug(
            "[{}] [{}] other_buy_price_dict: {}  other_sell_price_dict: {}".format(
                self.strategy_id, self.slot_name,other_buy_price_dict, other_sell_price_dict)
        )

        self.other_buy = best_buy_price
        self.other_sell = best_sell_price

        self.other_buy_volume = best_buy_volume
        self.other_sell_volume = best_sell_volume

        self.other_buy_broker=best_buy_broker
        self.other_sell_broker=best_sell_broker

        if self.slot_name in strategy_stats.slot_dict:
            net_traded_own = strategy_stats.slot_dict[self.slot_name]['net_volume']
        else:
            net_traded_own = 0

        if self.lift_slot_name in strategy_stats.slot_dict:
            net_traded_lift = strategy_stats.slot_dict[self.lift_slot_name]['net_volume']
        else:
            net_traded_lift = 0

        abs_net_open_position = abs(net_traded_own + net_traded_lift)
        self.abs_net_open_position=abs_net_open_position

        self.inst_key=self.market_area + "_" + self.own_product_id

        if 'BID' in self.identifier and self.other_buy and not strategy_stats.balancing_dict[self.inst_key]['BID'] and abs_net_open_position == 0 and strategy_stats.ql<=self.ql_max:

            if self.market_volume_check_flag == 0.0:

                if not self.local_buy or (round_to_tick(self.other_buy - self.local_buy,self.tick_size) > abs(self.margin)):
                    our_price = round_to_tick(self.other_buy - abs(self.margin),self.tick_size)
                    our_volume = min(self.other_buy_volume, self.max_quantity)
                    # checking if LEAD can be safely closed e.g. AON orders
                    closeable_flag=aon_check(self.strategy_id,COMMON.Direction.buy,other_view, self.other_buy,our_volume,self.other_buy_broker, self.lift_instrument_id)

                    if closeable_flag:
                        return self.create_slot_info(COMMON.Direction.buy, our_price, our_volume)
                    else:
                        return self.remove_slot_info("BID")
                else:
                    return self.remove_slot_info("BID")

            elif self.market_volume_check_flag == 1.0:
                if not self.local_buy or (round_to_tick(self.other_buy - self.local_buy,self.tick_size) > abs(self.margin)):
                    our_price = round_to_tick(self.other_buy - abs(self.margin), self.tick_size)
                    our_volume = min(self.other_buy_volume, self.max_quantity)
                    market_volume_check = get_price_diff_depth(self.strategy_id,COMMON.Direction.buy, localview, our_price,
                                                                          our_volume, None)
                    closeable_flag=aon_check(self.strategy_id,COMMON.Direction.buy,other_view, self.other_buy,our_volume,self.other_buy_broker, self.lift_instrument_id)

                    if market_volume_check and round_to_tick(market_volume_check,self.tick_size) > round_to_tick(our_price - abs(self.margin),self.tick_size) and closeable_flag:
                        return self.create_slot_info(COMMON.Direction.buy, our_price, our_volume)
                    else:
                        return self.remove_slot_info("BID")
                else:
                    return self.remove_slot_info("BID")

        elif 'ASK' in self.identifier and self.other_sell and not strategy_stats.balancing_dict[self.inst_key]['ASK'] and abs_net_open_position == 0 and strategy_stats.ql<=self.ql_max:

            if self.market_volume_check_flag == 0.0:

                if not self.local_sell or (round_to_tick(self.local_sell - self.other_sell,self.tick_size) > abs(self.margin)):
                    our_price = round_to_tick(self.other_sell + abs(self.margin),self.tick_size)
                    our_volume = min(self.other_sell_volume, self.max_quantity)
                    # checking if LEAD can be safely closed e.g. AON orders
                    closeable_flag=aon_check(self.strategy_id,COMMON.Direction.sell,other_view, self.other_sell,our_volume,self.other_sell_broker, self.lift_instrument_id)

                    if closeable_flag:
                        return self.create_slot_info(COMMON.Direction.sell, our_price, our_volume)
                    else:
                        return self.remove_slot_info("ASK")
                else:
                    return self.remove_slot_info("ASK")

            elif self.market_volume_check_flag == 1.0:
                if not self.local_sell or (round_to_tick(self.local_sell - self.other_sell,self.tick_size) > abs(self.margin)):
                    our_price = round_to_tick(self.other_sell + abs(self.margin),self.tick_size)
                    our_volume = min(self.other_sell_volume, self.max_quantity)

                    market_volume_check = get_price_diff_depth(self.strategy_id,COMMON.Direction.sell, localview, our_price,
                                                                          our_volume, None)

                    closeable_flag=aon_check(self.strategy_id,COMMON.Direction.sell,other_view, self.other_sell,our_volume,self.other_sell_broker, self.lift_instrument_id)

                    if market_volume_check and round_to_tick(market_volume_check,self.tick_size) < round_to_tick(our_price + abs(self.margin),self.tick_size) and closeable_flag:
                        return self.create_slot_info(COMMON.Direction.sell, our_price, our_volume)
                    else:
                        return self.remove_slot_info("ASK")
                else:
                    return self.remove_slot_info("ASK")

        return self.remove_slot_info()

    def create_slot_info(self, direction, our_price, our_volume):
        log.debug(
            "[{}] LEAD-SO-ACT-CREATE-SLOT-{}, {}@{}, BROKER:{},  [Public BUY/SELL]: LEAD_BEST_PRICES: {}[{}]: {}//{} --- LIFT_BEST_PRICES: {}[{}]: {}//{}".format(
                self.strategy_id, direction,our_price,our_volume, self.broker_id, self.market_area, self.own_product_id, self.local_buy if self.local_buy else -1.0,
                self.local_sell if self.local_sell else -1.0,
                self.lift_instrument_id, self.lift_product_id, self.other_buy if self.other_buy else -1.0, self.other_sell if self.other_sell else -1.0)
        )
        return self.create_slot(direction, our_volume, our_price, info="lead"+direction.capitalize())

    def remove_slot_info(self, direction=None):
        strategy_stats = StrategyStats.from_dict(self.strategy_stats_dict)
        if direction=="BID":
            log.debug(
                "[{}] LEAD-SO-ACT-REMOVE-SLOT-{}: [other_{}: {}, balancing_{}: {}, abs_net_open_position: {}]".format(
                    self.strategy_id, direction, direction, self.other_buy, direction,
                    strategy_stats.balancing_dict[self.inst_key]['BID'], self.abs_net_open_position)
            )
        elif direction=="ASK":
            log.debug(
                "[{}] LEAD-SO-ACT-REMOVE-SLOT-{}: [other_{}: {}, balancing_{}: {}, abs_net_open_position: {}]".format(
                    self.strategy_id, direction, direction, self.other_buy, direction,
                    strategy_stats.balancing_dict[self.inst_key]['ASK'], self.abs_net_open_position)
            )
        else:
            log.debug(
                "[{}] {} LEAD-SO-ACT-REMOVE-SLOT: [self.other_buy: {}, self.other_sell: {}, balancing_bid: {}, balancing_ask: {}, abs_net_open_position: {}, ql: {}]".format(
                    self.strategy_id, self.identifier, self.other_buy, self.other_sell, strategy_stats.balancing_dict[self.inst_key]['BID'],
                    strategy_stats.balancing_dict[self.inst_key]['ASK'], self.abs_net_open_position, strategy_stats.ql )
            )
        return self.remove()
