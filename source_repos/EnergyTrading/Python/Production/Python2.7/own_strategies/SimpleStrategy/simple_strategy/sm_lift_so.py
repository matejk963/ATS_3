import logging

import autotrader_core.common as COMMON
import autotrader_synthetic.config_util as SYNCONF
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB
from strategy_stats import StrategyStats
from own_tools.instrument_key import InstrumentKey

log = logging.getLogger("arbitrage.arbitrage_order")


class SimpleOrderLift(SYB.SyntheticOrderBase):
    product_id = SYNCONF.ConfigOptionDescriptor(
        "product_id", str,
        "Name of so's product id",
        required=True
    )

    lead_slot_name = SYNCONF.ConfigOptionDescriptor(
        "lead_slot_name", str,
        "Name of the other leading slot",
        required=True
    )

    lead_instrument_id = SYNCONF.ConfigOptionDescriptor(
        "lead_instrument_id", str,
        "Name of the other leading so's instrument id",
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

    strategy_stats_dict = SYNCONF.SyntheticOrderConfigField(
        caption="strategy_stats",
        expected_type=StrategyStats,
        description="Object for strategy statistics"
    )

    def _get_trade_params(self, localview):
        instrument_key = InstrumentKey(self.lead_instrument_id, self.lead_product_id)
        strategy_stats = StrategyStats.from_dict(self.strategy_stats_dict)
        # net_position = self.strategy_stats.net_position[instrument_key.key]
        net_position = strategy_stats.net_position[instrument_key.key]
        if net_position > 0:
            direction = COMMON.Direction.sell
            price = localview.current_front_price(COMMON.Direction.buy)
        else:
            direction = COMMON.Direction.buy
            price = localview.current_front_price(COMMON.Direction.sell)
        return abs(round(net_position, 6)), direction, price

    def act(self, localview, additional_views, timestamp):

        open_position, direction, price = self._get_trade_params(localview)

        log.debug("[{}] LIFT-SO-ACT [OpenPos]:  {}[{}]: {}_{}@{}".format(
            self.strategy_id, self.market_area, self.product_id, direction, open_position, price
        ))
        strategy_stats = StrategyStats.from_dict(self.strategy_stats_dict)
        if open_position > 0:
            strategy_stats.balancing = True
            return self.create_slot(direction, open_position, price, info="SimpleLift")
        else:
            return self.remove()
