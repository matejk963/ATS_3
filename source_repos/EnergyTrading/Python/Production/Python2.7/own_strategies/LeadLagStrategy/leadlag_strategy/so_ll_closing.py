import logging

import autotrader_core.common as COMMON
import autotrader_synthetic.config_util as SYNCONF
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB
from strategy_stats import StrategyStats
from own_tools.misc import round_to_tick, max_with_none_check, min_with_none_check


log = logging.getLogger("leadlag.LL_Closing_order")

class ClosingOrder(SYB.SyntheticOrderBase):
    init_instrument_id = SYNCONF.ConfigOptionDescriptor(
        "init_instrument_id", str,
        "Name of the init instrument additional view, as used in the strategy template",
        required=True
    )

    init_slot_name = SYNCONF.ConfigOptionDescriptor(
        "init_slot_name", str,
        "Name of the other initing slot",
        required=True
    )

    init_product_id = SYNCONF.ConfigOptionDescriptor(
        "init_product_id", str,
        "Name of the other initing so's product id",
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

    take_profit = SYNCONF.SyntheticOrderConfigField(
        caption="Take Profit",
        expected_type=float,
        description="Take profit of the strategy in absolute EUR terms",
    )

    stop_loss = SYNCONF.SyntheticOrderConfigField(
        caption="Stop Loss",
        expected_type=float,
        description="Stop Loss of the strategy in absolute EUR terms",
    )

    trail_tp_bool = SYNCONF.SyntheticOrderConfigField(
        caption="trail_tp_bool",
        expected_type=bool,
        description="Trailing Take Profit switch",
    )

    trailing_tp_tau = SYNCONF.SyntheticOrderConfigField(
        caption="trailing_tp_tau",
        expected_type=float,
        description="Tau parameter for the trailing take profit EMA",
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

    def get_open_position(self, localview, other_view):
        # if net traded >0, we net bought
        # net_traded_own = (localview.traded_volume_buy(self.slot_name)
        #                   - localview.traded_volume_sell(self.slot_name))
        # net_traded_init = (other_view.traded_volume_buy(self.init_slot_name)
        #                    - other_view.traded_volume_sell(self.init_slot_name))

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


        if self.init_slot_name in strategy_stats.slot_dict:
            net_traded_init=strategy_stats.slot_dict[self.init_slot_name]['net_volume']
            last_price_init = strategy_stats.slot_dict[self.init_slot_name]['last_price']
            # last_delivery_end_init = strategy_stats.slot_dict[self.init_slot_name]['last_delivery_end']
        else:
            net_traded_init=0
            last_price_init=None
            # last_delivery_end_init=None

        # if net open position >0, we need to place a buy, else we place sell
        # example
        # init sold 10 => -10
        # closing bought 5 => 5
        # net open: 5 = -(-10+5)
        net_open_position = - (net_traded_init + net_traded_own)


        if net_open_position > 0:
            direction = COMMON.Direction.buy
            price_mm = localview.current_front_price(COMMON.Direction.buy)

            price_tp= last_price_init-take_profit
            price_sl= last_price_init-stop_loss

            log.debug(
                "[{}] [{}] price_mm: {}, price_tp: {}, price_sl: {}, last_price_init: {}".format(
                    self.strategy_id, self.slot_name, price_mm, price_tp, price_sl, last_price_init)
            )

        else:
            direction = COMMON.Direction.sell
            price_mm = localview.current_front_price(COMMON.Direction.sell)

            price_tp = last_price_init + take_profit
            price_sl = last_price_init + stop_loss

            log.debug(
                "[{}] [{}] price_mm: {}, price_tp: {}, price_sl: {}, last_price_init: {}".format(
                    self.strategy_id, self.slot_name, price_mm, price_tp, price_sl, last_price_init)
            )


        log.debug("[{}] closing-SO-ACT,  TRADED_OWN {}[{}]: {}, TRADED_init {} [{}]: {}".format(
            self.strategy_id, self.market_area, localview.product_id, net_traded_own,
            self.init_instrument_id, self.init_product_id, net_traded_init)
        )
        # # OR find price from trades
        # init_trades = other_view._product.trades.get(
        #     buy_delivery_area=None,
        #     sell_delivery_area=None,
        #     delivery_area=other_view.market_area,
        #     portfolio_key=other_view.strategy_id,
        #     trade_filter=COMMON.TradeFilter.own,
        #     timerange=None
        # )
        # if len(init_trades) > 0:
        #     print(len(init_trades))

        return abs(round(net_open_position, 6)), direction, price_mm, price_tp, price_sl, last_price_init

    def act(self, localview, additional_views, timestamp):
        # check what the init has been doing
        init_view = additional_views.get_view_for_instrument(
            self.init_instrument_id,
            self.init_product_id,
        )

        open_position, direction, price_mm, price_tp, price_sl = self.get_open_position(
            localview, init_view
        )

        self.inst_key=self.market_area + "_" + self.init_product_id

        if open_position > 0: # and (bid_not_balancing or ask_not_balancing)

            if direction == COMMON.Direction.buy:
                if abs(price_tp-price_mm)<1.0:
                    price=price_tp
                elif price_sl-price_mm<=0.0:
                    price=price_mm
                else:
                    price=-1

            else:
                if abs(price_tp-price_mm)<1.0:
                    price=price_tp
                elif price_sl-price_mm>=0.0:
                    price=price_mm
                else:
                    price=-1
            #logging the details
            log.debug("[{}] [{}] CLOSING-SO-ACT-CREATE-SLOT [OpenPos]:  {}--{}: {}_{}@{}".format(
                self.strategy_id, self.identifier, self.market_area, self.init_instrument_id, direction, open_position,
                price
            ))
            volume=min(open_position, self.max_quantity)

            if price>0.0:
                return self.create_slot(direction, volume, price, info="closing")
            else:
                # logging the details
                log.debug("[{}] [{}] [{}] CLOSING-SO-ACT-REMOVE-SLOT: [OP: {}]; Price is not within range.".format(
                    self.strategy_id, self.identifier, self.market_area, open_position
                ))
                return self.remove()
        else:
            # logging the details
            log.debug("[{}] [{}] [{}] CLOSING-SO-ACT-REMOVE-SLOT: [OP: {}]".format(
                self.strategy_id, self.identifier, self.market_area, open_position
            ))
            return self.remove()
