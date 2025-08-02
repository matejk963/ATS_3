import logging

import autotrader_core.common as COMMON
import autotrader_synthetic.config_util as SYNCONF
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB
from strategy_stats import StrategyStats

log = logging.getLogger("arbitrage.arbitrage_order")


class SimpleOrderBid(SYB.SyntheticOrderBase):
    strategy_id = SYNCONF.ConfigOptionDescriptor(
        "strategy_id", str,
        "strategy_id for logging",
        required=True
    )

    product_id = SYNCONF.ConfigOptionDescriptor(
        "product_id", str,
        "product_id for logging",
        required=True
    )

    slot_size = SYNCONF.SyntheticOrderConfigField(
        caption="slot_size",
        description="What slot size it can place maximum on the market",
        expected_type=float,
    )

    margin = SYNCONF.SyntheticOrderConfigField(
        caption="spread",
        expected_type=float,
        description="How far from spread mid price to be",
    )

    strategy_stats_dict = SYNCONF.SyntheticOrderConfigField(
        caption="strategy_stats_dict",
        expected_type=StrategyStats,
        description="Object for strategy statistics"
    )

    def act(self, localview, additional_views, timestamp):
        direction = COMMON.Direction.buy

        local_buy = localview.current_front_price(COMMON.Direction.buy, self.broker_id)
        local_sell = localview.current_front_price(COMMON.Direction.sell, self.broker_id)

        log.debug(
            "[{}] SimpleBid, BROKER:{},  [Public BUY/SELL]: Local: {}[{}]: {}//{}".format(
            self.strategy_id, self.broker_id, self.market_area, self.product_id, local_buy, local_sell)
        )
        strategy_stats = StrategyStats.from_dict(self.strategy_stats_dict)
        if local_buy is not None:
            our_price = local_buy - self.margin
        else:
            our_price = None
        if (our_price is not None) and (not strategy_stats.balancing):
            return self.create_slot(direction, self.slot_size, our_price, info="SimpleLimitAsk")
        else:
            return self.remove()
