import logging

import autotrader_core.common as COMMON
import autotrader_synthetic.config_util as SYNCONF
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB
from own_tools.instrument_key import InstrumentKey
from action_result import ActionResult
from strategy_stats import StrategyStats, get_avg_market_price_depth

log = logging.getLogger("market_making.strategy_order")


class MarketMakingOrderBid(SYB.SyntheticOrderBase):
    mkt1_instrument_key = SYNCONF.ConfigOptionDescriptor(
        "mkt1_instrument_key", str,
        "Instrument key in string format of market 1",
        required=True
    )

    product_id = SYNCONF.ConfigOptionDescriptor(
        "product_id", str,
        "product_id for logging",
        required=True
    )

    other_product_id = SYNCONF.ConfigOptionDescriptor(
        "other_product_id", str,
        "Product ID of the Gas product to be used as lift order, which closes this orders 2nd leg",
        required=True
    )

    other_instrument_id = SYNCONF.ConfigOptionDescriptor(
        "other_instrument_id", str,
        "Name of the lift instrument additional view, as used in the strategy template",
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

    num_clips = SYNCONF.SyntheticOrderConfigField(
        caption="num_clips",
        description="What slot size it can place maximum on the market",
        expected_type=float,
    )

    margin = SYNCONF.SyntheticOrderConfigField(
        caption="margin",
        expected_type=float,
        description="How far from spread mid price to be",
    )

    size_margin = SYNCONF.SyntheticOrderConfigField(
        caption="margin",
        expected_type=float,
        description="How far from spread mid price to be",
    )

    stop_loss = SYNCONF.SyntheticOrderConfigField(
        caption="stop_loss",
        expected_type=float,
        description="Stop loss for strategy",
    )

    idle_thres = SYNCONF.SyntheticOrderConfigField(
        caption="idle_thres",
        expected_type=float,
        description="Minimal price movement threshold",
    )

    market_depth = SYNCONF.SyntheticOrderConfigField(
        caption="market_depth",
        expected_type=float,
        description="Minimal price movement threshold",
    )

    strategy_stats_dict = SYNCONF.SyntheticOrderConfigField(
        caption="strategy_stats_dict",
        expected_type=StrategyStats,
        description="Object for strategy statistics"
    )


    @property
    def instrument_key(self):
        return InstrumentKey(self.market_area, self.product_id)

    def _price_check(self, direction, our_price, price_other, c_our, c_oth, exist_price, local_buy, local_sell,
                     strategy_stats):
        price = None
        spread_direction = COMMON.Direction.buy
        if our_price is None:
            log.debug("[{}] MarketMakeBid, proposed price is None".format(self.strategy_id))
        else:
            if direction == COMMON.Direction.buy:
                if (local_buy is not None) and (local_buy - our_price > self.market_depth):
                    # Depth of orderbook check
                    log.debug(
                        "[{}] MarketMakeBid, proposed price too far from market BID {} -- {}".format(
                            self.strategy_id, our_price, local_buy)
                    )
                elif (local_sell is not None) and (our_price >= local_sell):
                    # Inverse bid ask spread check
                    log.debug(
                        "[{}] MarketMakeBid, proposed price create inverse bo spread BID {} -- {}//{}".format(
                            self.strategy_id, our_price, local_buy, local_sell)
                    )
                else:
                    exp_spread_price = c_our * our_price - c_oth * price_other
                    add_action = ActionResult.add_spread_action(direction, 1, strategy_stats, spread_direction,
                                                                exp_spread_price)
                    if add_action < -self.stop_loss:
                        log.debug(
                            "[{}] MarketMakeBid, proposed price would end up in stop loss {} -- {}".format(
                                self.strategy_id, our_price, add_action)
                        )
                    else:
                        price = our_price
            else:
                if (local_sell is not None) and (our_price - local_sell > self.market_depth):
                    # Depth of orderbook check
                    log.debug(
                        "[{}] MarketMakeBid, proposed price too far from market ASK {} -- {}".format(
                            self.strategy_id, our_price, local_sell)
                    )
                elif (local_buy is not None) and (our_price <= local_buy):
                    # Inverse bid ask spread check
                    log.debug(
                        "[{}] MarketMakeBid, proposed price create inverse bo spread ASK {} -- {}//{}".format(
                            self.strategy_id, our_price, local_buy, local_sell)
                    )
                else:
                    exp_spread_price = -(c_our * our_price - c_oth * price_other)
                    add_action = ActionResult.add_spread_action(direction, 1, strategy_stats, spread_direction,
                                                                exp_spread_price)
                    if add_action < -self.stop_loss:
                        log.debug(
                            "[{}] MarketMakeBid, proposed price would end up in stop loss {} -- {}".format(
                                self.strategy_id, our_price, add_action)
                        )
                    else:
                        price = our_price
        if (price is None) or (exist_price is None):
            pass
        else:
            if abs(exist_price - price) < self.idle_thres:
                price = exist_price
        return price

    def get_own_order_price(self, localview):
        own_price = None
        strategy_orders = localview._product.orders.get(localview.market_area, COMMON.OrderFilter.own,
                                                        portfolio_key=self.strategy_id)
        for curr_order in strategy_orders:
            if curr_order.tags.get("strategy_slot") == self.slot_name:
                own_price = curr_order.price
        return own_price

    def act(self, localview, additional_views, timestamp):
        local_instrument_key = InstrumentKey(localview.market_area, localview.product_id)
        other_instrument_key = InstrumentKey(self.other_instrument_id, self.other_product_id)
        # Other view definition
        other_view = additional_views.get_view_for_instrument(
            other_instrument_key.instrument_id,
            other_instrument_key.product_id
        )

        strategy_stats = StrategyStats.from_dict(self.strategy_stats_dict)
        if local_instrument_key == InstrumentKey().from_instrument_key(self.mkt1_instrument_key):
            direction = COMMON.Direction.buy
            local_clip = strategy_stats.leg1_clip
            other_clip = strategy_stats.leg2_clip
            c_our, c_oth = strategy_stats.price_coeff
        else:
            direction = COMMON.Direction.sell
            local_clip = strategy_stats.leg2_clip
            other_clip = strategy_stats.leg1_clip
            c_oth, c_our = strategy_stats.price_coeff

        local_buy = localview.current_front_price(COMMON.Direction.buy, self.broker_id)
        local_sell = localview.current_front_price(COMMON.Direction.sell, self.broker_id)
        other_buy = other_view.current_front_price(COMMON.Direction.buy, self.broker_id)
        other_sell = other_view.current_front_price(COMMON.Direction.sell, self.broker_id)

        log.debug(
            "[{}] MarketMakeBid, BROKER:{},  [Public BUY/SELL]: Local: {}[{}]: {}//{} --- Other: {}[{}]: {}//{}".format(
                self.strategy_id, self.broker_id, self.market_area, self.product_id, local_buy, local_sell,
                self.other_instrument_id, self.other_product_id, other_buy, other_sell)
        )

        if strategy_stats.is_spread_price and strategy_stats.is_adjusted_model_price and self.margin is not None:
            try:
                bid_spread, ask_spread = strategy_stats.bid_spread, strategy_stats.ask_spread
                if bid_spread - ask_spread > abs(self.margin) / 2:
                    spread_model_price = None
                    margin = None
                    log.debug(
                        "[{}] MarketMakeBid WARNING: Bid above Ask, Bid/Ask Spread: {}//{}".format(
                            self.strategy_id, bid_spread, ask_spread)
                    )
                else:
                    spread_model_price = strategy_stats.adjusted_model_price
                    log.debug(
                        "[{}] MarketMakeBid, Bid/Ask Spread: {}//{}".format(
                            self.strategy_id, bid_spread, ask_spread)
                    )
                    margin = max(self.margin, .8 * (ask_spread - bid_spread) / 2)
            except Exception as err:
                spread_model_price = None
                margin = None
                log.error("Exception in BID order: %s", err)
        else:
            spread_model_price = None
            margin = None

        log.debug(
            "[{}] MarketMakeBid, MARGIN:{}, SPREAD MODEL PRICE:{}".format(
                self.strategy_id, margin, spread_model_price)
        )

        local_quantity = round(self.num_clips * local_clip, 0)
        other_quantity = round(self.num_clips * other_clip, 0)

        our_price = None
        if (spread_model_price is not None) and (margin is not None):
            if direction == COMMON.Direction.sell:
                avg_clip_other = get_avg_market_price_depth(COMMON.Direction.sell, other_view, other_quantity,
                                                            self.broker_list)
                if avg_clip_other is not None:
                    our_price = (c_oth * avg_clip_other - (spread_model_price - (margin + self.size_margin))) / c_our
            else:
                avg_clip_other = get_avg_market_price_depth(COMMON.Direction.buy, other_view, other_quantity,
                                                            self.broker_list)
                if avg_clip_other is not None:
                    our_price = (c_oth * avg_clip_other + (spread_model_price - (margin + self.size_margin))) / c_our
            # Price check
            exist_price = self.get_own_order_price(localview)
            our_price = self._price_check(direction, our_price, avg_clip_other, c_our, c_oth, exist_price,
                                          local_buy, local_sell, strategy_stats)
    
        log.debug(
            "[{}] MarketMakeBid order placement: our_price: {} / balancing: {}".format(
                self.strategy_id, our_price, strategy_stats.balancing)
        )

        if (our_price is not None) and strategy_stats.quote_bool(local_instrument_key.key, 'bid'):
            return self.create_slot(direction, local_quantity, our_price, info="MarketMakingLimitBid")
        elif (our_price is not None) and strategy_stats.hold_bool(local_instrument_key.key):
            num_clips = abs(strategy_stats.net_clip_position[local_instrument_key.key])
            if num_clips < 1:
                quantity = round(num_clips * local_clip, 0)
            else:
                quantity = 0
            return self.create_slot(direction, quantity, our_price, info="MarketMakingLimitBidHold")
        else:
            return self.remove()
