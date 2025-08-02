import logging

import autotrader_lib.common as COMMON
import autotrader_synthetic.config_util as SYNCONF
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB
from .strategy_stats import StrategyStats, get_price_diff_depth, get_price_time_depth, aon_check
from .own_tools.misc import round_to_tick, floor_div_to_tick, max_with_none_check, min_with_none_check
from .own_tools.instrument_key import InstrumentKey


log = logging.getLogger("arbitrage.arbitrage_order")
tol = 1e-3

# QUANTITY_TICK_SIZE = 10


class ArbitrageOrder(SYB.SyntheticOrderBase):

    own_product_id = SYNCONF.ConfigOptionDescriptor(
        "own_product_id", str,
        "Own Product ID, which is passed to the 2nd arbitrage leg synthetic order as 'other'",
        required=True
    )

    lead_broker_id = SYNCONF.ConfigOptionDescriptor(
        "lead_broker_id", str,
        "Broker ID trading on the Gas product",
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
        description="How far optimally from spread mid price to be",
    )

    max_margin = SYNCONF.SyntheticOrderConfigField(
        caption="max_margin",
        expected_type=float,
        description="How far max from spread mid price to be",
    )

    min_margin_dict = SYNCONF.SyntheticOrderConfigField(
        caption="min_margin_dict",
        expected_type=dict,
        description="How far min from spread mid price to be based on broker ID",
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

    cross_arb_bool = SYNCONF.SyntheticOrderConfigField(
        caption="cross_arb_bool",
        expected_type=bool,
        description="autoTrader reset boolean",
    )

    reset_bool = SYNCONF.SyntheticOrderConfigField(
        caption="reset_bool",
        expected_type=bool,
        description="autoTrader reset boolean",
    )

    advanced_making = SYNCONF.SyntheticOrderConfigField(
        caption="advanced_making",
        expected_type=bool,
        description="advanced making boolean",
    )

    flex_margin = SYNCONF.SyntheticOrderConfigField(
        caption="flex_margin",
        expected_type=bool,
        description="flexible margin boolean",
    )

    broker_making = SYNCONF.SyntheticOrderConfigField(
        caption="broker_making",
        expected_type=bool,
        description="broker making boolean",
    )

    cons_margin = SYNCONF.SyntheticOrderConfigField(
        caption="cons_margin",
        expected_type=float,
        description="Level for activating conservetive making",
    )

    cons_min_level = SYNCONF.SyntheticOrderConfigField(
        caption="cons_min_level",
        expected_type=float,
        description="Minimum level for conservative making",
    )

    cons_making_dict = SYNCONF.SyntheticOrderConfigField(
        caption="cons_making_dict",
        expected_type=dict,
        description="conservative making boolean dictionary with broker ID keys",
    )

    verbose = SYNCONF.SyntheticOrderConfigField(
        caption="verbose",
        expected_type=bool,
        description="logging bool",
    )

    local_buy = None
    local_sell = None
    other_buy = None
    other_sell = None
    other_buy_volume = None
    other_sell_volume = None
    other_buy_broker = None
    other_sell_broker = None
    abs_net_open_position = None
    inst_key = None
    aon_cross = False

    @property
    def is_cross_arb(self):
        is_cross_arb = False
        nan_bool = all([x is not None for x in [self.local_buy,
                       self.other_buy, self.local_sell, self.other_sell]])
        if self.cross_arb_bool and nan_bool:
            best_price_buy = max(self.local_buy, self.other_buy)
            best_price_sell = min(self.local_sell, self.other_sell)
            cross_margin = round_to_tick(
                best_price_buy - best_price_sell, self.tick_size)
            if (cross_margin < self.cross_arb_margin_min) or (cross_margin > self.cross_arb_margin_max):
                pass
            else:
                if self.aon_cross:
                    is_cross_arb = True
        return is_cross_arb

    def calc_margin(self, market_margin, own_margin, broker_id):
        min_margin = self.min_margin_dict[broker_id]
        opt_margin = self.margin if self.margin >= min_margin else min_margin
        if self.flex_margin:
            if own_margin is None:
                factor = 1.
            elif abs(own_margin - market_margin) < tol:
                factor = 0.
            else:
                factor = 1.
            market_margin = max(market_margin, min_margin)
            if market_margin - opt_margin < tol:
                margin = max(market_margin - factor *
                             self.tick_size, min_margin)
            elif market_margin - 2 * opt_margin < -tol:
                margin = opt_margin
            elif market_margin - 2 * self.max_margin < -tol:
                margin = min(floor_div_to_tick(market_margin, 2,
                             self.tick_size) + self.tick_size, self.max_margin)
            else:
                margin = self.max_margin
        else:
            margin = opt_margin
        if self.verbose:
            log.debug("calc_margin: margin {}".format(margin))
        return abs(margin)

    def act(self, localview, additional_views, timestamp):
        self.broker_id = self.lead_broker_id
        self.aon_cross = False

        own_instkey = InstrumentKey(self.market_area, self.own_product_id)
        other_instkey = InstrumentKey(
            self.lift_instrument_id, self.lift_product_id)
        if own_instkey == other_instkey:
            other_view = localview
        else:
            other_view = additional_views.get_view_for_instrument(
                self.lift_instrument_id,
                self.lift_product_id
            )

        strategy_stats = StrategyStats.from_dict(self.strategy_stats_dict)

        self.local_buy = localview.current_front_price(
            COMMON.Direction.buy, self.broker_id)
        self.local_sell = localview.current_front_price(
            COMMON.Direction.sell, self.broker_id)

        # Calculate best broker price and volume for buying among the lift brokers
        other_buy_price_dict = {broker: other_view.current_front_price(COMMON.Direction.buy, broker) for broker in
                                self.lift_broker_ids}
        other_buy_volume_dict = {broker: other_view.current_front_volume(COMMON.Direction.buy, broker) for broker in
                                 self.lift_broker_ids}

        best_buy_broker, best_buy_price = max_with_none_check(
            other_buy_price_dict)
        best_buy_volume = other_buy_volume_dict.get(best_buy_broker)

        # Calculate best broker price and volume for selling among the lift brokers
        other_sell_price_dict = {broker: other_view.current_front_price(COMMON.Direction.sell, broker) for broker in
                                 self.lift_broker_ids}
        other_sell_volume_dict = {broker: other_view.current_front_volume(COMMON.Direction.sell, broker) for broker in
                                  self.lift_broker_ids}

        best_sell_broker, best_sell_price = min_with_none_check(
            other_sell_price_dict)
        best_sell_volume = other_sell_volume_dict.get(best_sell_broker)

        if self.verbose:
            log.debug(
                "[{}] [{}] other_buy_price_dict: {}  other_sell_price_dict: {}".format(
                    self.strategy_id, self.slot_name, other_buy_price_dict, other_sell_price_dict)
            )

        self.other_buy = best_buy_price
        self.other_sell = best_sell_price

        self.other_buy_volume = best_buy_volume
        self.other_sell_volume = best_sell_volume

        self.other_buy_broker = best_buy_broker
        self.other_sell_broker = best_sell_broker

        if self.slot_name in strategy_stats.slot_dict:
            net_traded_own = strategy_stats.slot_dict[self.slot_name]['net_volume']
        else:
            net_traded_own = 0

        if self.lift_slot_name in strategy_stats.slot_dict:
            net_traded_lift = strategy_stats.slot_dict[self.lift_slot_name]['net_volume']
        else:
            net_traded_lift = 0

        abs_net_open_position = abs(net_traded_own + net_traded_lift)
        self.abs_net_open_position = abs_net_open_position

        self.inst_key = self.market_area + "_" + self.own_product_id
        # Set default margin
        margin = abs(self.margin)

        # For cross arb
        if 'BID' in self.identifier and self.other_sell and self.cross_arb_bool:
            self.aon_cross = aon_check(self.strategy_id, COMMON.Direction.sell, other_view, self.other_sell, 1,
                                       self.other_sell_broker, self.lift_instrument_id, self.verbose)
        elif 'ASK' in self.identifier and self.other_buy and self.cross_arb_bool:
            self.aon_cross = aon_check(self.strategy_id, COMMON.Direction.buy, other_view, self.other_buy, 1,
                                       self.other_buy_broker, self.lift_instrument_id, self.verbose)

        if self.check_place_order_bid(abs_net_open_position, strategy_stats):
            own_price, own_brk = self.get_own_order_price(
                localview, COMMON.Direction.buy)
            try:
                market_margin = round_to_tick(
                    self.other_buy - self.local_buy, self.tick_size)
                own_margin = self.our_margin_calc(
                    COMMON.Direction.buy, own_price, self.other_buy)
                margin = self.calc_margin(
                    market_margin, own_margin, self.other_buy_broker)
            except TypeError:
                market_margin = margin + 2 * tol
            if self.market_volume_check_flag == 0.0:
                if not self.local_buy or (market_margin - margin >= -tol):
                    our_price = round_to_tick(
                        self.other_buy - margin, self.tick_size)
                    our_volume = min(self.other_buy_volume, self.max_quantity)
                    # checking if LEAD can be safely closed e.g. AON orders
                    closeable_flag = aon_check(self.strategy_id, COMMON.Direction.buy, other_view, self.other_buy,
                                               our_volume, self.other_buy_broker, self.lift_instrument_id, self.verbose)

                    if closeable_flag:
                        if market_margin > margin:
                            return self.create_slot_info(COMMON.Direction.buy, our_price, our_volume)
                        else:
                            brk_margin_bool = self.calc_brk_margin_bool_bid(
                                other_buy_price_dict, own_brk, margin)
                            # Check if exists our order on proposed level
                            if self.check_proposed_price_slot(own_price, our_price) and brk_margin_bool:
                                # This means we have an order already placed at proposed level don't change
                                self.broker_id = own_brk
                                return self.create_slot_info(COMMON.Direction.buy, our_price, our_volume)
                            else:
                                # Post other brokers if possible
                                prop_brk = self.advanced_broker_making_bid(
                                    our_price, other_buy_price_dict)
                                if prop_brk is None:
                                    return self.remove_slot_info("BID")
                                else:
                                    self.broker_id = prop_brk
                                    return self.create_slot_info(COMMON.Direction.buy, our_price, our_volume)
                    else:
                        return self.remove_slot_info("BID")
                else:
                    return self.remove_slot_info("BID")

            elif self.market_volume_check_flag == 1.0:
                if not self.local_buy or (market_margin - margin >= -tol):
                    our_price = round_to_tick(
                        self.other_buy - margin, self.tick_size)
                    our_volume = min(self.other_buy_volume, self.max_quantity)
                    market_volume_check = get_price_diff_depth(self.strategy_id, COMMON.Direction.buy, localview,
                                                               our_price, our_volume, None, self.verbose)
                    closeable_flag = aon_check(self.strategy_id, COMMON.Direction.buy, other_view, self.other_buy,
                                               our_volume, self.other_buy_broker, self.lift_instrument_id, self.verbose)
                    # Conservative bidding check
                    if self.cons_making_dict[self.other_buy_broker] and market_volume_check:
                        price_level = our_price - self.cons_margin
                        # We do not want to take the price level worse than the minimum price level
                        min_price_level = round_to_tick(
                            self.other_buy - self.cons_min_level, self.tick_size)
                        market_cons_price = get_price_time_depth(self.strategy_id, COMMON.Direction.buy, localview,
                                                                 price_level, our_volume, self.lead_broker_id, min_price_level,
                                                                 self.verbose)
                    else:
                        market_cons_price = self.other_buy
                    if self.verbose:
                        log.debug(
                            "[{}] BID: market_volume_check: {}, market_cons_price: {}, our_price: {}, margin: {}".format(
                                self.strategy_id, market_volume_check, market_cons_price, our_price, margin)
                        )
                    if market_volume_check and round_to_tick(market_volume_check, self.tick_size) > round_to_tick(
                            our_price - margin, self.tick_size) and market_cons_price and closeable_flag:
                        if market_margin > margin:
                            return self.create_slot_info(COMMON.Direction.buy, our_price, our_volume)
                        else:
                            brk_margin_bool = self.calc_brk_margin_bool_bid(
                                other_buy_price_dict, own_brk, margin)
                            # Check if exists our order on proposed level
                            if self.check_proposed_price_slot(own_price, our_price) and brk_margin_bool:
                                # This means we have an order already placed at proposed level don't change
                                self.broker_id = own_brk
                                return self.create_slot_info(COMMON.Direction.buy, our_price, our_volume)
                            else:
                                # Post other brokers if possible
                                prop_brk = self.advanced_broker_making_bid(
                                    our_price, other_buy_price_dict)
                                if prop_brk is None:
                                    return self.remove_slot_info("BID")
                                else:
                                    self.broker_id = prop_brk
                                    return self.create_slot_info(COMMON.Direction.buy, our_price, our_volume)
                    else:
                        return self.remove_slot_info("BID")
                else:
                    return self.remove_slot_info("BID")
            else:
                return self.remove_slot_info("BID")

        elif self.check_place_order_ask(abs_net_open_position, strategy_stats):
            own_price, own_brk = self.get_own_order_price(
                localview, COMMON.Direction.sell)
            try:
                market_margin = round_to_tick(
                    self.local_sell - self.other_sell, self.tick_size)
                own_margin = self.our_margin_calc(
                    COMMON.Direction.sell, own_price, self.other_sell)
                margin = self.calc_margin(
                    market_margin, own_margin, self.other_sell_broker)
            except TypeError:
                market_margin = margin + 2 * tol
            if self.market_volume_check_flag == 0.0:

                if not self.local_sell or (market_margin - margin >= -tol):
                    our_price = round_to_tick(
                        self.other_sell + margin, self.tick_size)
                    our_volume = min(self.other_sell_volume, self.max_quantity)
                    # checking if LEAD can be safely closed e.g. AON orders
                    closeable_flag = aon_check(self.strategy_id, COMMON.Direction.sell, other_view, self.other_sell,
                                               our_volume, self.other_sell_broker, self.lift_instrument_id, self.verbose)

                    if closeable_flag:
                        if market_margin > margin:
                            return self.create_slot_info(COMMON.Direction.sell, our_price, our_volume)
                        else:
                            brk_margin_bool = self.calc_brk_margin_bool_ask(
                                other_sell_price_dict, own_brk, margin)
                            # Check if exists our order on proposed level
                            if self.check_proposed_price_slot(own_price, our_price) and brk_margin_bool:
                                # This means we have an order already placed at proposed level don't change
                                self.broker_id = own_brk
                                return self.create_slot_info(COMMON.Direction.sell, our_price, our_volume)
                            else:
                                # Post other brokers if possible
                                prop_brk = self.advanced_broker_making_ask(
                                    our_price, other_sell_price_dict)
                                if prop_brk is None:
                                    return self.remove_slot_info("ASK")
                                else:
                                    self.broker_id = prop_brk
                                    return self.create_slot_info(COMMON.Direction.sell, our_price, our_volume)
                    else:
                        return self.remove_slot_info("ASK")
                else:
                    return self.remove_slot_info("ASK")

            elif self.market_volume_check_flag == 1.0:
                if not self.local_sell or (market_margin - margin >= -tol):
                    our_price = round_to_tick(
                        self.other_sell + margin, self.tick_size)
                    our_volume = min(self.other_sell_volume, self.max_quantity)

                    market_volume_check = get_price_diff_depth(self.strategy_id, COMMON.Direction.sell, localview,
                                                               our_price, our_volume, None, self.verbose)

                    closeable_flag = aon_check(self.strategy_id, COMMON.Direction.sell, other_view, self.other_sell,
                                               our_volume, self.other_sell_broker, self.lift_instrument_id, self.verbose)
                    # Conservative bidding check
                    if self.cons_making_dict[self.other_sell_broker] and market_volume_check:
                        price_level = our_price + self.cons_margin
                        # We do not want to take the price level worse than the minimum price level
                        min_price_level = round_to_tick(
                            self.other_sell + self.cons_min_level, self.tick_size)
                        market_cons_price = get_price_time_depth(self.strategy_id, COMMON.Direction.sell, localview,
                                                                 price_level, our_volume, self.lead_broker_id, min_price_level,
                                                                 self.verbose)
                    else:
                        market_cons_price = self.other_sell
                    if self.verbose:
                        log.debug(
                            "[{}] ASK: market_volume_check: {}, market_cons_price: {}, our_price: {}, margin: {}".format(
                                self.strategy_id, market_volume_check, market_cons_price, our_price, margin)
                        )
                    if market_volume_check and round_to_tick(market_volume_check, self.tick_size) < round_to_tick(
                            our_price + margin, self.tick_size) and market_cons_price and closeable_flag:
                        if market_margin > margin:
                            return self.create_slot_info(COMMON.Direction.sell, our_price, our_volume)
                        else:
                            brk_margin_bool = self.calc_brk_margin_bool_ask(
                                other_sell_price_dict, own_brk, margin)
                            # Check if exists our order on proposed level
                            if self.check_proposed_price_slot(own_price, our_price) and brk_margin_bool:
                                # This means we have an order already placed at proposed level don't change
                                self.broker_id = own_brk
                                return self.create_slot_info(COMMON.Direction.sell, our_price, our_volume)
                            else:
                                # Post other brokers if possible
                                prop_brk = self.advanced_broker_making_ask(
                                    our_price, other_sell_price_dict)
                                if prop_brk is None:
                                    return self.remove_slot_info("ASK")
                                else:
                                    self.broker_id = prop_brk
                                    return self.create_slot_info(COMMON.Direction.sell, our_price, our_volume)
                    else:
                        return self.remove_slot_info("ASK")
                else:
                    return self.remove_slot_info("ASK")
            else:
                return self.remove_slot_info("ASK")

        return self.remove_slot_info()

    def create_slot_info(self, direction, our_price, our_volume):
        log.debug(
            "[{}] LEAD-SO-ACT-CREATE-SLOT-{}, {}@{}, BROKER:{},  [Public BUY/SELL]: LEAD_BEST_PRICES: {}[{}]: {}//{} --- LIFT_BEST_PRICES: {}[{}]: {}//{}".format(
                self.strategy_id, direction, our_price, our_volume, self.broker_id, self.market_area,
                self.own_product_id, self.local_buy if self.local_buy else -1.0,
                self.local_sell if self.local_sell else -1.0,
                self.lift_instrument_id, self.lift_product_id, self.other_buy if self.other_buy else -1.0,
                self.other_sell if self.other_sell else -1.0)
        )
        return self.create_slot(direction, our_volume, our_price, info="lead"+direction.capitalize())

    def remove_slot_info(self, direction=None):
        strategy_stats = StrategyStats.from_dict(self.strategy_stats_dict)
        if direction == "BID":
            log.debug(
                "[{}] LEAD-SO-ACT-REMOVE-SLOT-{}: [other_{}: {}, balancing_{}: {}, abs_net_open_position: {}]".format(
                    self.strategy_id, direction, direction, self.other_buy, direction,
                    strategy_stats.balancing_dict[self.inst_key]['BID'], self.abs_net_open_position)
            )
        elif direction == "ASK":
            log.debug(
                "[{}] LEAD-SO-ACT-REMOVE-SLOT-{}: [other_{}: {}, balancing_{}: {}, abs_net_open_position: {}]".format(
                    self.strategy_id, direction, direction, self.other_buy, direction,
                    strategy_stats.balancing_dict[self.inst_key]['ASK'], self.abs_net_open_position)
            )
        else:
            log.debug(
                "[{}] {} LEAD-SO-ACT-REMOVE-SLOT: [self.other_buy: {}, self.other_sell: {}, balancing_bid: {}, balancing_ask: {}, abs_net_open_position: {}, ql: {}, hard_stop_loss: {}]".format(
                    self.strategy_id, self.identifier, self.other_buy, self.other_sell,
                    strategy_stats.balancing_dict[self.inst_key]['BID'],
                    strategy_stats.balancing_dict[self.inst_key]['ASK'], self.abs_net_open_position,
                    strategy_stats.aux_dict['ql'], strategy_stats.bool_dict['hard_stop_loss'])
            )
        return self.remove()

    def get_own_order_price(self, localview, direction):
        own_price = None
        own_brk = None
        strategy_orders = localview._product.orders.get(localview.market_area, COMMON.OrderFilter.own,
                                                        portfolio_key=self.strategy_id)
        for curr_order in strategy_orders:
            if curr_order.tags.get("strategy_slot") == self.slot_name and curr_order.direction == direction:
                own_price = curr_order.price
                own_brk = curr_order.broker_id
                break
        return own_price, own_brk

    def check_proposed_price_slot(self, own_price, prop_price):
        if not self.advanced_making:
            return False
        if own_price is None:
            return False
        else:
            return abs(own_price - prop_price) < tol

    def calc_brk_margin_bool_bid(self, brk_price_dict, own_brk, margin):
        if not self.broker_making:
            return True
        try:
            if brk_price_dict[own_brk] is None:
                return True
            market_margin = round_to_tick(
                self.other_buy - brk_price_dict[own_brk], self.tick_size)
            if market_margin - margin < -tol:
                return False
            else:
                return True
        except KeyError:
            return True

    def calc_brk_margin_bool_ask(self, brk_price_dict, own_brk, margin):
        if not self.broker_making:
            return True
        try:
            if brk_price_dict[own_brk] is None:
                return True
            market_margin = round_to_tick(
                brk_price_dict[own_brk] - self.other_sell, self.tick_size)
            if market_margin - margin < -tol:
                return False
            else:
                return True
        except KeyError:
            return True

    def our_margin_calc(self, direction, own_price, best_price):
        if own_price is None:
            return None
        else:
            if direction == COMMON.Direction.buy:
                return round_to_tick(best_price - own_price, self.tick_size)
            elif direction == COMMON.Direction.sell:
                return round_to_tick(own_price - best_price, self.tick_size)
            else:
                return None

    def advanced_broker_making_bid(self, prop_price, brk_price_dict):
        if not self.broker_making:
            return None
        if prop_price < self.local_buy:
            return None
        aux_price_dict = {brk: p for brk, p in brk_price_dict.items(
        ) if p is not None and (p < prop_price)}
        if not aux_price_dict:
            return None
        else:
            return next(iter(aux_price_dict))

    def advanced_broker_making_ask(self, prop_price, brk_price_dict):
        if not self.broker_making:
            return None
        if prop_price > self.local_sell:
            return None
        aux_price_dict = {brk: p for brk, p in brk_price_dict.items(
        ) if p is not None and (p > prop_price)}
        if not aux_price_dict:
            return None
        else:
            return next(iter(aux_price_dict))

    def check_place_order_ask(self, opn_position, strategy_stats):
        return ('ASK' in self.identifier and self.other_sell and
                not strategy_stats.balancing_dict[self.inst_key]['ASK'] and
                not strategy_stats.balancing_dict[self.inst_key]['CROSS'] and
                opn_position == 0 and strategy_stats.aux_dict['ql'] <= self.ql_max and
                not strategy_stats.bool_dict['hard_stop_loss'] and strategy_stats.cross_check and
                not self.reset_bool and not self.is_cross_arb)

    def check_place_order_bid(self, opn_position, strategy_stats):
        return ('BID' in self.identifier and self.other_buy and
                not strategy_stats.balancing_dict[self.inst_key]['BID'] and
                not strategy_stats.balancing_dict[self.inst_key]['CROSS'] and
                opn_position == 0 and strategy_stats.aux_dict['ql'] <= self.ql_max and
                not strategy_stats.bool_dict['hard_stop_loss'] and strategy_stats.cross_check and
                not self.reset_bool and not self.is_cross_arb)
