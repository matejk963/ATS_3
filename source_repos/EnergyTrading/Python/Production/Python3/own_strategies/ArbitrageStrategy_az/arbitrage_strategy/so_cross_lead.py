import logging

import autotrader_lib.common as COMMON
import autotrader_synthetic.config_util as SYNCONF
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB
from .own_tools.instrument_key import InstrumentKey
from .strategy_stats import StrategyStats, get_price_diff_depth, aon_check
from .own_tools.misc import round_to_tick, max_with_none_check, min_with_none_check


log = logging.getLogger("arbitrage.arbitrage_cross_order")
tol = 1e-3


class ArbitrageOrder(SYB.SyntheticOrderBase):
    abs_net_open_position = None
    best_buy = None
    best_sell = None
    timestamp = None

    product_id = SYNCONF.ConfigOptionDescriptor(
        "product_id", str,
        "product_id for logging",
        required=True
    )

    lift_broker_id = SYNCONF.ConfigOptionDescriptor(
        "lift_broker_id", str,
        "Broker ID trading on the Gas product",
        required=True
    )

    broker_list = SYNCONF.ConfigOptionDescriptor(
        "broker_list", list,
        "List of brokers",
        required=True
    )

    strategy_id = SYNCONF.ConfigOptionDescriptor(
        "strategy_id", str,
        "strategy_id for logging",
        required=True
    )

    lift_slot_name = SYNCONF.ConfigOptionDescriptor(
        "lift_slot_name", str,
        "Name of the lifting slot",
        required=True
    )

    cross_arb_margin_min = SYNCONF.SyntheticOrderConfigField(
        caption="cross_arb_margin_min",
        expected_type=float,
        description="Minimum margin for activating cross arbitrage",
    )

    cross_arb_margin_max = SYNCONF.SyntheticOrderConfigField(
        caption="cross_arb_margin_max",
        expected_type=float,
        description="Maximum margin for activating cross arbitrage",
    )

    min_time_cross = SYNCONF.SyntheticOrderConfigField(
        caption="min_time_cross",
        expected_type=float,
        description="Minimum time difference for activating cross arbitrage",
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

    def _get_trade_params(self, localview, best_price_buy, best_venue_buy, best_volume_buy,
                          best_price_sell, best_venue_sell, best_volume_sell, strategy_stats):
        try:
            cross_margin = round_to_tick(best_price_buy - best_price_sell, self.tick_size)
        except TypeError:
            cross_margin = None
        if cross_margin is None or (cross_margin < self.cross_arb_margin_min) or (
                cross_margin > self.cross_arb_margin_max):
            # No action
            act_position = 0
            direction = COMMON.Direction.buy
            our_venue = best_venue_buy
            our_price = best_price_buy
            strategy_stats.set_no_cross()
            if self.verbose:
                log.debug("[{}] CROSS_ARB-NO-ACT out of range [CrossMargin // (BID//ASK)]:  {}[{}]: {} vs ({}//{})".format(
                    self.strategy_id, self.market_area, self.product_id, cross_margin, best_price_buy, best_price_sell
                ))
        else:
            # Create preference list of brokers, lift borker is last
            broker_list = [b for b in self.broker_list if b != self.lift_broker_id]
            broker_list.append(self.lift_broker_id)
            # Take broker based on preference of broker list
            id_buy, id_sell = [broker_list.index(ven) for ven in [best_venue_buy, best_venue_sell]]
            if id_buy < id_sell:
                # BID is preferred
                direction = COMMON.Direction.sell
                our_volume = min(best_volume_buy, self.max_quantity)
                our_venue = best_venue_buy
                our_price = best_price_buy
                direction_opp = COMMON.Direction.buy
                opp_volume = min(best_volume_sell, self.max_quantity)
                opp_venue = best_venue_sell
                opp_price = best_price_sell
                buy_bool = False
            else:
                # ASK is preferred
                direction = COMMON.Direction.buy
                our_volume = min(best_volume_sell, self.max_quantity)
                our_venue = best_venue_sell
                our_price = best_price_sell
                direction_opp = COMMON.Direction.sell
                opp_volume = min(best_volume_buy, self.max_quantity)
                opp_venue = best_venue_buy
                opp_price = best_price_buy
                buy_bool = True
            closeable_flag = aon_check(self.strategy_id, direction, localview, our_price,
                                       our_volume, our_venue, self.market_area)
            if opp_venue == self.lift_broker_id:
                closeable_flag_opp = True
            else:
                closeable_flag_opp = aon_check(self.strategy_id, direction_opp, localview, opp_price,
                                               opp_volume, opp_venue, self.market_area)
            market_volume_check = True
            if self.market_volume_check_flag == 1:
                price_depth = get_price_diff_depth(self.strategy_id, direction, localview, our_price,
                                                   our_volume, None)
                if buy_bool:
                    price_thres = round_to_tick(our_price - abs(self.cross_arb_margin_max), self.tick_size)
                    if price_depth and round_to_tick(price_depth, self.tick_size) > price_thres:
                        pass
                    else:
                        market_volume_check = False
                else:
                    price_thres = round_to_tick(our_price + abs(self.cross_arb_margin_max), self.tick_size)
                    if price_depth and round_to_tick(price_depth, self.tick_size) < price_thres:
                        pass
                    else:
                        market_volume_check = False
            if closeable_flag and closeable_flag_opp and market_volume_check:
                act_position = min(abs(round(our_volume)), self.max_quantity)
                strategy_stats.set_cross(buy_bool)
            else:
                act_position = 0
        return act_position, direction, our_price, our_venue

    def act(self, localview, additional_views, timestamp):
        strategy_stats = StrategyStats.from_dict(self.strategy_stats_dict)
        if self.timestamp is None:
            time_diff = self.min_time_cross + 10 * tol
        else:
            time_diff = timestamp - self.timestamp

        if self.slot_name in strategy_stats.slot_dict:
            net_traded_own = strategy_stats.slot_dict[self.slot_name]['net_volume']
        else:
            net_traded_own = 0

        if self.lift_slot_name in strategy_stats.slot_dict:
            net_traded_lift = strategy_stats.slot_dict[self.lift_slot_name]['net_volume']
        else:
            net_traded_lift = 0

        self.abs_net_open_position = abs(net_traded_own + net_traded_lift)

        # Calculate best broker price and volume for buying among the available brokers
        other_buy_price_dict = {broker: localview.current_front_price(COMMON.Direction.buy, broker) for broker in
                                self.broker_list}
        other_buy_volume_dict = {broker: localview.current_front_volume(COMMON.Direction.buy, broker) for broker in
                                 self.broker_list}

        best_venue_buy, best_price_buy = max_with_none_check(other_buy_price_dict)
        best_volume_buy = other_buy_volume_dict.get(best_venue_buy)

        # Calculate best broker price and volume for selling among the lift brokers
        other_sell_price_dict = {broker: localview.current_front_price(COMMON.Direction.sell, broker) for broker in
                                 self.broker_list}
        other_sell_volume_dict = {broker: localview.current_front_volume(COMMON.Direction.sell, broker) for broker in
                                  self.broker_list}

        best_venue_sell, best_price_sell = min_with_none_check(other_sell_price_dict)
        best_volume_sell = other_sell_volume_dict.get(best_venue_sell)

        self.best_buy, self.best_sell = best_price_buy, best_price_sell

        if self.verbose:
            log.debug(
                "[{}] [{}] other_buy_price_dict: {}  other_sell_price_dict: {}".format(
                    self.strategy_id, self.slot_name, other_buy_price_dict, other_sell_price_dict)
            )

        act_position, direction, price, venue = self._get_trade_params(localview, best_price_buy, best_venue_buy,
                                                                       best_volume_buy, best_price_sell,
                                                                       best_venue_sell, best_volume_sell,
                                                                       strategy_stats)
        if self.check_place_order(act_position, price, time_diff, strategy_stats):
            # Execute order
            self.broker_id = venue
            self.timestamp = timestamp
            return self.create_slot_info(direction, price, act_position)
        else:
            return self.remove_slot_info()

    def remove_slot_info(self):
        strategy_stats = StrategyStats.from_dict(self.strategy_stats_dict)
        inst_key = InstrumentKey(self.market_area, self.product_id).key
        log.debug(
            "[{}] CROSS_LEAD-SO-ACT-REMOVE-SLOT-CROSS: [balancing_{}: abs_net_open_position: {}]".format(
                self.strategy_id, strategy_stats.balancing_dict[inst_key]['CROSS'], self.abs_net_open_position)
        )
        return self.remove()

    def create_slot_info(self, direction, price, volume):
        log.debug(
            "[{}] CROSS_LEAD-SO-ACT-CREATE-SLOT-{}, {}@{}, BROKER:{},  [Public BUY/SELL]: BEST_PRICES: {}[{}]: {}//{}".format(
                self.strategy_id, direction, price, volume, self.broker_id, self.market_area,
                self.product_id, self.best_buy if self.best_buy else -1.0,
                self.best_sell if self.best_sell else -1.0)
        )
        return self.create_slot(direction, volume, price, info="cross" + direction.capitalize())

    def check_place_order(self, act_position, price, time_diff, strategy_stats):
        inst_key = InstrumentKey(self.market_area, self.product_id).key
        balance_bool = all([not b for b in strategy_stats.balancing_dict[inst_key].values()])
        return ((act_position > tol) and ((time_diff - self.min_time_cross) > tol) and price is not None and
                balance_bool and strategy_stats.aux_dict['ql'] <= self.ql_max and not self.reset_bool and
                not strategy_stats.bool_dict['hard_stop_loss'])
