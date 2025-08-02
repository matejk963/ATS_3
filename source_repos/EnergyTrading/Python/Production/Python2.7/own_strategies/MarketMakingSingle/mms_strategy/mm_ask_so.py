import logging

import autotrader_core.common as COMMON
import autotrader_synthetic.config_util as SYNCONF
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB
from own_tools.instrument_key import InstrumentKey
from action_result import ActionResult
from strategy_stats import StrategyStats, get_avg_market_price_depth

log = logging.getLogger("market_making_single.strategy_order")


class MarketMakingOrderAsk(SYB.SyntheticOrderBase):
    product_id = SYNCONF.ConfigOptionDescriptor(
        "product_id", str,
        "product_id for logging",
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

    strategy_stats_dict = SYNCONF.SyntheticOrderConfigField(
        caption="strategy_stats_dict",
        expected_type=StrategyStats,
        description="Object for strategy statistics"
    )

    @property
    def instrument_key(self):
        return InstrumentKey(self.market_area, self.product_id)

    def _price_check(self, our_price, exist_price, local_buy, local_sell):
        price = None
        if our_price is None:
            log.debug("[{}] MarketMakeAsk, proposed price is None".format(self.strategy_id))
        else:
            if (local_sell is not None) and (our_price - local_sell > 1 * self.margin):
                # Depth of orderbook check
                log.debug(
                    "[{}] MarketMakeAsk, proposed price too far from market ASK {} -- {}".format(
                        self.strategy_id, our_price, local_sell)
                )
            elif (local_buy is not None) and our_price <= local_buy:
                # Inverse bid ask spread check
                log.debug(
                    "[{}] MarketMakeAsk, proposed price create inverse bo spread ASK {} -- {}//{}".format(
                        self.strategy_id, our_price, local_buy, local_sell)
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
        strategy_stats = StrategyStats.from_dict(self.strategy_stats_dict)
        direction = COMMON.Direction.sell
        local_clip = strategy_stats.leg_clip

        local_buy = localview.current_front_price(COMMON.Direction.buy, self.broker_id)
        local_sell = localview.current_front_price(COMMON.Direction.sell, self.broker_id)

        log.debug(
            "[{}] MarketMakeAsk, BROKER:{},  [Public BUY/SELL]: Local: {}[{}]: {}//{}".format(
                self.strategy_id, self.broker_id, self.market_area, self.product_id, local_buy, local_sell)
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
            "[{}] MarketMakeAsk, MARGIN:{}, SPREAD MODEL PRICE:{}".format(
                self.strategy_id, margin, spread_model_price)
        )

        local_quantity = round(self.num_clips * local_clip, 0)
    
        our_price = None
        if (spread_model_price is not None) and (margin is not None):
            our_price = spread_model_price + margin
            # Price check
            exist_price = self.get_own_order_price(localview)
            our_price = self._price_check(our_price, exist_price, local_buy, local_sell)

        log.debug(
            "[{}] MarketMakeAsk order placement: our_price: {} / quoting: {}".format(
                self.strategy_id, our_price, strategy_stats.quote_bool)
        )

        if (our_price is not None) and strategy_stats.quote_bool:
            return self.create_slot(direction, local_quantity, our_price, info="MarketMakingLimitAsk")
        else:
            return self.remove()
