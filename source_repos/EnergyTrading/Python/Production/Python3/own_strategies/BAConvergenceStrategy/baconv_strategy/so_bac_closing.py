import logging
import time

import autotrader_lib.common as COMMON
import autotrader_synthetic.config_util as SYNCONF
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB
from .strategy_stats import StrategyStats
from .own_tools.misc import round_to_tick, max_with_none_check, min_with_none_check
import math


log = logging.getLogger("baconv.BAC_Closing_order")

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

    aggloss_thres = SYNCONF.SyntheticOrderConfigField(
        caption="Aggloss threshold",
        expected_type=float,
        description="Bidask threshold for AGGLOSSing instead of MAKEBESTing",
    )

    burnout_period = SYNCONF.SyntheticOrderConfigField(
        caption="burnout_period",
        expected_type=float,
        description="burnout_period",
    )

    stop_profit = SYNCONF.SyntheticOrderConfigField(
        caption="stop_profit",
        expected_type=float,
        description="stop_profit",
    )

    makeagg_ratio = SYNCONF.SyntheticOrderConfigField(
        caption="makeagg_ratio",
        expected_type=float,
        description="makeagg_ratio",
    )

    trail_stop = SYNCONF.SyntheticOrderConfigField(
        caption="trail_stop",
        expected_type=float,
        description="trail_stop",
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

    reset_bool = SYNCONF.SyntheticOrderConfigField(
        caption="autoTrader_reset",
        expected_type=bool,
        description="autoTrader reset boolean",
    )

    ba_max = SYNCONF.SyntheticOrderConfigField(
        caption="ba_max",
        expected_type=float,
        description="Bid-Ask spread maximum"
    )

    def get_open_position(self, localview):
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
            last_time_init = strategy_stats.slot_dict[self.init_slot_name]['last_execution_time']
            # last_delivery_end_init = strategy_stats.slot_dict[self.init_slot_name]['last_delivery_end']
        else:
            net_traded_init=0
            last_price_init=None
            last_time_init=None
            # last_delivery_end_init=None

        if not last_price_init:
            last_price_init=0.

        if not last_time_init:
            last_time_init=0.
        # if net open position >0, we need to place a buy, else we place sell
        # example
        # init sold 10 => -10
        # closing bought 5 => 5
        # net open: 5 = -(-10+5)
        net_open_position = - (net_traded_init + net_traded_own)
        price_mm_bid = localview.current_front_price(COMMON.Direction.buy)
        price_mm_ask = localview.current_front_price(COMMON.Direction.sell)


        if net_open_position > 0:
            direction = COMMON.Direction.buy

            price_tp= last_price_init-self.take_profit
            price_sl= last_price_init-self.stop_loss

            log.debug(
                "[{}] [{}] price_mm_bid: {}, price_mm_ask: {}, price_tp: {}, price_sl: {}, last_price_init: {}, last_time_init: {}".format(
                    self.strategy_id, self.slot_name, price_mm_bid, price_mm_ask, price_tp, price_sl, last_price_init, last_time_init)
            )

        else:
            direction = COMMON.Direction.sell

            price_tp = last_price_init + self.take_profit
            price_sl = last_price_init + self.stop_loss

            log.debug(
                "[{}] [{}] price_mm_bid: {}, price_mm_ask: {}, price_tp: {}, price_sl: {}, last_price_init: {}, last_time_init: {} ".format(
                    self.strategy_id, self.slot_name, price_mm_bid, price_mm_ask, price_tp, price_sl, last_price_init, last_time_init)
            )


        log.debug("[{}] closing-SO-ACT,  TRADED_OWN {}[{}]: {}, TRADED_init {} [{}]: {}".format(
            self.strategy_id, self.market_area, localview.product_id, net_traded_own,
            self.init_instrument_id, self.init_product_id, net_traded_init)
        )

        return round(net_open_position, 6), abs(round(net_open_position, 6)), direction, price_mm_bid, price_mm_ask, price_tp, price_sl, last_price_init, last_time_init
    def calculate_close_behavior(self, bid_price, ask_price, net_open_position, open_price, burnout):
        diff = lambda x, y: round(y - x, 2)
        TAKEPROFIT = 'TAKEPROFIT'
        MAKEBEST = 'MAKEBEST'
        AGGLOSS = 'AGGLOSS'

        self.trail_stop_adjustment = int(self.strategy_stats.bool_dict['trail_stop_flag']) * self.max_mtm

        if net_open_position < 0:
            direction = 'long'
            open_price_adj = open_price + self.trail_stop_adjustment
            if bid_price < open_price_adj + self.stop_loss:
                if ask_price < open_price_adj - self.stop_profit:
                    # active close
                    make_agg_ratio = diff(ask_price, open_price_adj) / diff(bid_price, open_price_adj)
                    if make_agg_ratio > self.makeagg_ratio and self.ba_spread<=self.ba_max:
                        branch_flag = 1
                        close_behavior = AGGLOSS
                    else:
                        branch_flag = 2
                        close_behavior = MAKEBEST
                        if ask_price-bid_price<=self.aggloss_thres:
                            close_behavior = AGGLOSS
                else:
                    if burnout:
                        branch_flag = 3
                        close_behavior = MAKEBEST
                        if ask_price-bid_price<=self.aggloss_thres:
                            close_behavior = AGGLOSS
                    else:
                        branch_flag = 4
                        close_behavior = TAKEPROFIT
            else:
                # profit
                if ask_price < open_price_adj - self.stop_profit:
                    branch_flag = 5
                    close_behavior = MAKEBEST
                    if ask_price - bid_price <= self.aggloss_thres:
                        close_behavior = AGGLOSS
                else:
                    if burnout:
                        branch_flag = 6
                        close_behavior = MAKEBEST
                        if ask_price-bid_price<=self.aggloss_thres:
                            close_behavior = AGGLOSS
                    else:
                        branch_flag = 7
                        close_behavior = TAKEPROFIT
        else:
            # short
            direction = 'short'
            open_price_adj = open_price - self.trail_stop_adjustment
            if ask_price > open_price_adj - self.stop_loss:
                if bid_price > open_price_adj + self.stop_profit:
                    # active close
                    make_agg_ratio = diff(bid_price, open_price_adj) / diff(ask_price, open_price_adj)
                    if make_agg_ratio > self.makeagg_ratio and self.ba_spread<=self.ba_max:
                        branch_flag = 8
                        close_behavior = AGGLOSS
                    else:
                        branch_flag = 9
                        close_behavior = MAKEBEST
                        if ask_price-bid_price<=self.aggloss_thres:
                            close_behavior = AGGLOSS
                else:
                    if burnout:
                        branch_flag = 10
                        close_behavior = MAKEBEST
                        if ask_price-bid_price<=self.aggloss_thres:
                            close_behavior = AGGLOSS

                    else:
                        branch_flag = 11
                        close_behavior = TAKEPROFIT
            else:
                # profit
                if bid_price > open_price_adj + self.stop_profit:
                    branch_flag = 12
                    close_behavior = MAKEBEST
                    if ask_price - bid_price <= self.aggloss_thres:
                        close_behavior = AGGLOSS
                else:
                    if burnout:
                        branch_flag = 13
                        close_behavior = MAKEBEST
                        if ask_price-bid_price<=self.aggloss_thres:
                            close_behavior = AGGLOSS
                    else:
                        branch_flag = 14
                        close_behavior = TAKEPROFIT

        return close_behavior, direction, branch_flag

    def act_close(self, bid_price, ask_price, direction, close_behavior, open_price):
        long_tp = open_price + self.take_profit
        short_tp = open_price - self.take_profit
        b_price, a_price = bid_price, ask_price

        if close_behavior == "AGGLOSS":
            price = b_price if direction == 'long' else a_price
        elif close_behavior == "MAKEBEST":
            price = a_price if direction == 'long' else b_price
            price = min(price, long_tp) if direction == 'long' else max(price, short_tp)
        elif close_behavior == "TAKEPROFIT":
            if direction == 'long':
                if a_price > long_tp:
                    price = long_tp
                elif a_price > round(long_tp - 0.05, 2):
                    price = round(a_price - 0.01, 2)
                else:
                    price = long_tp
            else:
                if b_price < short_tp:
                    price = short_tp
                elif b_price < round(short_tp + 0.05, 2):
                    price = round(b_price + 0.01, 2)
                else:
                    price = short_tp
        else:
            raise ValueError("close_behavior has invalid value:", close_behavior)

        return round(price, 2)

    def act(self, localview, additional_views, timestamp):
        # check what the init has been doing
        net_open_position, open_position, direction, bid_price, ask_price, price_tp, price_sl, last_price_init, last_time_init= self.get_open_position(
            localview
        )

        self.strategy_stats = StrategyStats.from_dict(self.strategy_stats_dict)
        burnout = time.time() - last_time_init > self.burnout_period * 60
        time_in_position = round((time.time() - last_time_init)/60.0 , 2)

        self.inst_key=self.market_area + "_" + self.init_product_id

        if ask_price and bid_price:
            self.ba_spread=ask_price-bid_price
        else:
            self.ba_spread = None
            return self.remove()

        if not hasattr(self, 'max_mtm'):
            self.max_mtm = 0
            self.strategy_stats.aux_dict['max_mtm']=0

        if open_position > 0 and last_price_init!=0. and not self.reset_bool and not self.strategy_stats.bool_dict['hard_stop_loss']:
            # and (bid_not_balancing or ask_not_balancing)

            self.strategy_stats.aux_dict['op_tip'] = str(last_price_init)+'_'+str(time_in_position)

            if net_open_position < 0 and (bid_price+ask_price)/2 -last_price_init >=self.trail_stop:
                self.strategy_stats.bool_dict['trail_stop_flag'] = True
                if math.floor(((bid_price+ask_price)/2 -last_price_init) * 10) / 10 >self.max_mtm:
                    self.max_mtm=math.floor(((bid_price+ask_price)/2 -last_price_init) * 10)/10
                    self.strategy_stats.aux_dict['max_mtm']=self.max_mtm

            if net_open_position > 0 and last_price_init-(bid_price+ask_price)/2  >=self.trail_stop:
                self.strategy_stats.bool_dict['trail_stop_flag'] = True
                if math.floor((last_price_init-(bid_price+ask_price)/2) * 10) / 10 >self.max_mtm:
                    self.max_mtm=math.floor((last_price_init-(bid_price+ask_price)/2) * 10)/10
                    self.strategy_stats.aux_dict['max_mtm']=self.max_mtm


            close_behavior, direction_str, branch_flag = self.calculate_close_behavior(bid_price, ask_price,
                                                                                       net_open_position,
                                                                                       last_price_init, burnout)

            price = self.act_close(bid_price, ask_price, direction_str, close_behavior, last_price_init)

            #logging the details
            log.debug("[{}] [{}] CLOSING-SO-ACT-CREATE-SLOT [OpenPos]:  {}--{}: {}_{}@{}, close_behavior: {}, branch_flag: {}, trail_stop_adjustment {}".format(
                self.strategy_id, self.identifier, self.market_area, self.init_instrument_id, direction, open_position,
                price, close_behavior, branch_flag, self.trail_stop_adjustment
            ))
            volume=min(open_position, self.max_quantity)

            return self.create_slot(direction, volume, price, info="closing")

        else:
            self.max_mtm=0
            self.strategy_stats.aux_dict['max_mtm']=0
            self.strategy_stats.bool_dict['trail_stop_flag'] = False
            self.strategy_stats.aux_dict['op_tip']=None
            # logging the details
            log.debug("[{}] [{}] [{}] CLOSING-SO-ACT-REMOVE-SLOT: [OpenPosition: {}], [LastPriceInit: {}], [ResetBool: {}], [HardStopLoss: {}]".format(
                self.strategy_id, self.identifier, self.market_area, open_position, last_price_init, self.reset_bool, self.strategy_stats.bool_dict['hard_stop_loss']
            ))
            return self.remove()
