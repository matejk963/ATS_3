import logging

import autotrader_core.common as COMMON
import autotrader_synthetic.config_util as SYNCONF
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB
from strategy_stats import StrategyStats, get_price_diff_depth, aon_check
from own_tools.misc import round_to_tick, max_with_none_check, min_with_none_check


log = logging.getLogger("leadlag.LL_Initial_order")

#QUANTITY_TICK_SIZE = 10

class InitialOrder(SYB.SyntheticOrderBase):

    strategy_id = SYNCONF.ConfigOptionDescriptor(
        "strategy_id", str,
        "strategy_id for logging",
        required=True
    )

    lead_product_id = SYNCONF.ConfigOptionDescriptor(
        "lead_product_id", basestring,
        "Lead Product ID, which is used to know when to trade",
        required=True
    )

    lag_product_id = SYNCONF.ConfigOptionDescriptor(
        "lag_product_id", basestring,
        "Lag Product ID, this product ID is used for trading",
        required=True
    )

    ######################################################################################################################################################
    # main strategy parameters

    max_secs_between_trades = SYNCONF.SyntheticOrderConfigField(
        caption="max_secs_between_trades",
        expected_type=float,
        description="Maximal allowed queue lag for strategy"
    )

    cluster_trade_num_threshold = SYNCONF.SyntheticOrderConfigField(
        caption="cluster_trade_num_threshold",
        expected_type=float,
        description="Cluster trades number threshold"
    )

    min_price_movement = SYNCONF.SyntheticOrderConfigField(
        caption="min_price_movement",
        expected_type=float,
        description="Minimum price movement"
    )

    ######################################################################################################################################################

    ba_max = SYNCONF.SyntheticOrderConfigField(
        caption="ba_max",
        expected_type=float,
        description="Bid-Ask spread maximum"
    )

    closing_slot_name = SYNCONF.ConfigOptionDescriptor(
        "closing_slot_name", str,
        "Name of the closing slot"
    )

    closing_product_id = SYNCONF.ConfigOptionDescriptor(
        "closing_product_id", str,
        "Product ID of the Gas product to be used as closing order, which closes this orders 2nd leg"
    )

    closing_instrument_id = SYNCONF.ConfigOptionDescriptor(
        "closing_instrument_id", str,
        "Name of the closing instrument additional view, as used in the strategy template"
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

    ql_max = SYNCONF.SyntheticOrderConfigField(
        caption="maximal_allowed_queue_lag",
        expected_type=float,
        description="Maximal allowed queue lag for strategy",
    )

    def act(self, localview, additional_views, timestamp):
        strategy_stats = StrategyStats.from_dict(self.strategy_stats_dict)

        self.local_buy, self.local_buy_volume  = localview.current_front_price(COMMON.Direction.buy), localview.current_front_volume(COMMON.Direction.buy)
        self.local_sell, self.local_sell_volume = localview.current_front_price(COMMON.Direction.sell), localview.current_front_volume(COMMON.Direction.sell)

        self.ba_spread=self.local_sell-self.local_buy

        if self.slot_name in strategy_stats.slot_dict:
            net_traded_own = strategy_stats.slot_dict[self.slot_name]['net_volume']
        else:
            net_traded_own = 0

        if self.closing_slot_name in strategy_stats.slot_dict:
            net_traded_closing = strategy_stats.slot_dict[self.closing_slot_name]['net_volume']
        else:
            net_traded_closing = 0

        abs_net_open_position = abs(net_traded_own + net_traded_closing)
        self.abs_net_open_position=abs_net_open_position

        self.inst_key=self.market_area + "_" + self.lag_product_id

        if abs_net_open_position == 0 and self.ba_spread<=self.ba_max and strategy_stats.ql<=self.ql_max:

            action=strategy_stats.calculate_action(max_secs_between_trades, cluster_trade_num_threshold, min_price_movement)

            if action==1:
                our_price = self.local_sell
                our_volume = min(self.local_sell_volume, self.max_quantity)
                return self.create_slot_info(COMMON.Direction.buy, our_price, our_volume)

            if action==-1:
                our_price = self.local_buy
                our_volume = min(self.local_buy_volume, self.max_quantity)
                return self.create_slot_info(COMMON.Direction.sell, our_price, our_volume)


        return self.remove_slot_info()

    def create_slot_info(self, direction, our_price, our_volume):
        log.debug(
            "[{}] LL-INITIAL-CREATE-SLOT-{}, {}@{},  [Public BUY/SELL]: LEAD_BEST_PRICES: {}[{}]: {}//{}".format(
                self.strategy_id, direction,our_price,our_volume, self.market_area, self.lag_product_id, self.local_buy if self.local_buy else -1.0,
                self.local_sell if self.local_sell else -1.0)
        )
        return self.create_slot(direction, our_volume, our_price, info="LL_INIT_"+direction.capitalize())

    def remove_slot_info(self):
        log.debug(
            "[{}] {} LL-INITIAL-REMOVE-SLOT: [abs_net_open_position: {}, ba_spread: {}, ql: {}]".format(
                self.strategy_id, self.identifier, self.abs_net_open_position,self.ba_spread, strategy_stats.ql)
        )
        return self.remove()
