import logging
import time

import autotrader_lib.common as COMMON
import autotrader_synthetic.config_util as SYNCONF
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB
from .strategy_stats import StrategyStats, current_front_price_brk
from .own_tools.misc import round_to_tick, max_with_none_check, min_with_none_check


log = logging.getLogger("sparsity_bmark.lift_order")


class LiftOrder(SYB.SyntheticOrderBase):
    broker_list = SYNCONF.ConfigOptionDescriptor(
        "broker_list", list,
        "List of brokers",
        required=True
    )
    lead_instrument_id = SYNCONF.ConfigOptionDescriptor(
        "lead_instrument_id", str,
        "Name of the lead instrument additional view, as used in the strategy template",
        required=True
    )

    lead_slot_name = SYNCONF.ConfigOptionDescriptor(
        "lead_slot_name", str,
        "Name of the other leading slot",
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
        caption="strategy_stats_dict",
        expected_type=dict,
        description="Object for strategy statistics"
    )

    reset_bool = SYNCONF.SyntheticOrderConfigField(
        caption="autoTrader_reset",
        expected_type=bool,
        description="autoTrader reset boolean",
    )

    make_profit_margin = SYNCONF.SyntheticOrderConfigField(
        caption="make_profit_margin",
        expected_type=float,
        description="Margin for making profit",
    )

    loss_making_thold = SYNCONF.SyntheticOrderConfigField(
        caption="loss_making_thold",
        expected_type=float,
        description="Value <open_price - current_front_price> to start making and close the position"
    )

    stop_loss_margin = SYNCONF.SyntheticOrderConfigField(
        caption="stop_loss_margin",
        expected_type=float,
        description="Stop loss margin that is used for calculation action (make|agg)",
    )

    makeagg_ratio_thold = SYNCONF.SyntheticOrderConfigField(
        caption="makeagg_ratio_thold",
        expected_type=float,
        description="Ratio of loss by making and loss by aggress.",
    )

    burnout_period = SYNCONF.SyntheticOrderConfigField(
        caption="burnout_period",
        expected_type=float,
        description="Time period for making current front price instead of make profit margin.",
    )

    max_position = SYNCONF.SyntheticOrderConfigField(
        caption="max_position",
        expected_type=float,
        description="What is the maximum slot_size",
    )

    def get_open_position(self):
        try:
            strategy_stats = StrategyStats.from_dict(self.strategy_stats_dict)
            buy = strategy_stats.trade_spread_dict['buy']['quantity']
            sell = strategy_stats.trade_spread_dict['sell']['quantity']

            return round(buy - sell)

        except Exception as e:
            log.error(f"{e}, line number: {e.__traceback__.tb_lineno}")
            return 0

    def act_close(self, data_dict, direction, close_behavior, open_price):
        tp = self.strategy_stats_dict['position_dict']['takeprofit']
        b_price, a_price = data_dict['b_price'], data_dict['a_price']
        open_position = self.get_open_position()

        if close_behavior == "AGGLOSS":
            price = b_price if direction == 'long' else a_price
        elif close_behavior == "MAKEBEST":
            price = a_price if direction == 'long' else b_price
            price = min(price, tp) if direction == 'long' else max(price, tp)
        elif close_behavior == "TAKEPROFIT":
            if direction == 'long':
                if a_price > tp:
                    price = tp
                elif a_price > round(tp - 0.05, 2):
                    price = round(a_price - 0.01, 2)
                else:
                    price = tp
            else:
                if b_price < tp:
                    price = tp
                elif b_price < round(tp + 0.05, 2):
                    price = round(b_price + 0.01, 2)
                else:
                    price = tp
        else:
            raise ValueError("close_behavior has invalid value:", close_behavior)

        action = COMMON.Direction.sell if direction == 'long' \
            else COMMON.Direction.buy
        return self.create_slot_info(-open_position, round(price, 2))

    def prepare_data_dict(self, localview, strategy_stats):
        try:
            local_buy = localview.current_front_price(COMMON.Direction.buy)
            local_sell = localview.current_front_price(COMMON.Direction.sell)
            spread = round(local_sell - local_buy, 2)

            data_dict = {
                'b_price': local_buy,
                'a_price': local_sell,
                'ba_spread': spread,
            }
            return data_dict
        except Exception as e:
            log.error(f"[PREPARE data_dict] - exception: {e}, lineno{e.__traceback__.tb_lineno}")
            return None

    def act(self, localview, additional_views, timestamp):
        # check what the lead has been doing
        try:
            self.broker_id = self.broker_list[0]
            local_buy = localview.current_front_price(COMMON.Direction.buy)
            local_sell = localview.current_front_price(COMMON.Direction.sell)
            if not local_buy or not local_sell:
                return self.remove_slot_info('None orders')
            # RESET BOOL
            if self.reset_bool:
                return self.remove_slot_info('RESET BOOL is TRUE')
            # ===================================================
            strategy_stats = StrategyStats.from_dict(self.strategy_stats_dict)



            open_position = self.get_open_position()
            open_price = strategy_stats.position_dict['open_price']
            open_time = strategy_stats.position_dict['open_time']

            # lead persistance
            if round(open_position) == 0 and strategy_stats.lead_pers_dict['flag'] and ((timestamp - strategy_stats.lead_pers_dict['timestamp'] < 1.0)):
                log.info(f"LEAD PERSISTANCE lift action dict:{str(strategy_stats.lead_pers_dict)}, b_price{local_buy}, a_price{local_sell}")
                return self.create_slot_info(strategy_stats.lead_pers_dict['volume'], strategy_stats.lead_pers_dict['price'], localview)

            log.info(f"open position: {open_position} ,position_dict id: {id(strategy_stats.position_dict)}")

            data_dict = self.prepare_data_dict(localview, strategy_stats)
            if not data_dict:
                return self.remove_slot_info('prepare data error')

            if round(open_position) == 0:
                self.strategy_stats_dict['param_dict']['bid_price'] = data_dict['b_price']
                self.strategy_stats_dict['param_dict']['ask_price'] = data_dict['a_price']
                self.strategy_stats_dict['param_dict']['makeagg_ratio'] = None
                self.strategy_stats_dict['param_dict']['branch_flag'] = 0
                strategy_stats.mtm = 0.0
                return self.remove_slot_info("No open position")

            strategy_stats.update_open_price(data_dict)
            self.set_mtm(local_buy, local_sell, open_price)

            steering_closing = strategy_stats.aux_dict['steering_closing']

            burnout = time.time()-open_time > self.burnout_period*60
            # burnout = False # For testing purposes
            log.info(f"Burnout perdiod diff: {time.time()-open_time}")

            branch_flag = 0

            # Close params steering
            if strategy_stats.aux_dict['open_price'] != None:
                open_cand = strategy_stats.aux_dict['open_price']
                if isinstance(open_cand, float) and abs(open_cand-open_position) < .5:
                    log.info(f"[Steering adjustment]: open price changed from {open_price} to {open_cand}")
                    open_price = open_cand
                    self.strategy_stats_dict['position_dict']['open_price'] = open_price
                else:
                    log.error(f"[STEERING open_price]: open_price{open_price}, open_cand{open_cand}, type{type(open_cand)}")

            # SET monitoring variables ====================
            strategy_stats.param_dict['bid_price'] = local_buy
            strategy_stats.param_dict['ask_price'] = local_sell
            strategy_stats.param_dict['burnout_period'] = time.time()-open_time
            # ==============================================

            #TEST SCENARIO 4, 7, 11, 13
            # burnout = False

            # ============================================================
            # CHECK whether we have steered make_profit_margin to some different value
            if strategy_stats.aux_dict['make_profit_margin'] != None:
                mmargin = strategy_stats.aux_dict['make_profit_margin']
                if isinstance(mmargin, float) and mmargin > 0:
                    self.make_profit_margin = strategy_stats.aux_dict['make_profit_margin']
                else:
                    log.error(f"[STEERING make_profit_margin]: original margin{self.make_profit_margin}, make_profit_margin_cand{mmargin}, type{type(mmargin)}")

            # =============================================================

            close_behavior, direction = ["UNDEFINED"]*2
            log.info(f"[ACT VARIABLES] "
                     f"open_position{open_position},"
                     f"open_price{open_price},"
                     f"bid_price{local_buy},"
                     f"ask_price{local_sell},"
                     f"burnout{burnout},"
                     f"self.makeagg_ratio_thold{self.makeagg_ratio_thold},"
                     f"self.loss_making_thold{self.loss_making_thold},"
                     f"self.stop_loss_margin{self.stop_loss_margin},"
                     f"steering_closing{steering_closing},")

            close_behavior, direction, branch_flag = self.calculate_close_behavior(data_dict['b_price'],
                                                                         data_dict['a_price'],
                                                                         open_position,
                                                                         open_price,
                                                                         burnout)

            log.info(f'[LIFT sparsity act] -> calculated closing behavior: {close_behavior}, branch_flag: {branch_flag}')

            # STEERED CLOSE BEHAVIOR
            if steering_closing != 'auto':
                steer_close_map = {
                    'makebest': 'MAKEBEST',
                    'aggress': 'AGGLOSS'
                }
                if steering_closing == 'wait':
                    log.debug('[STEERING CLOSING] - wait action')
                    return self.remove_slot_info()
                else:
                    close_behavior = steer_close_map[steering_closing]
                    log.debug(f'[LIFT sparsity act] -> steered closing behavior: {close_behavior}')
            # ====================================================================
            log.debug(f'[LIFT sparsity act] -> direction: {direction}')
            self.strategy_stats_dict['param_dict']['branch_flag'] = branch_flag
            return self.act_close(data_dict,
                           direction, close_behavior, open_price)
        except Exception as e:
            log.error(f'[LIFT] {e}, line number: {e.__traceback__.tb_lineno}')
            # print("EXCEPTION catched", e, e.__traceback__.tb_lineno)
            return self.remove_slot_info('exception in lift act')

    def set_mtm(self, local_buy, local_sell, open_price):
        strategy_stats = StrategyStats.from_dict(self.strategy_stats_dict)
        position = self.get_open_position()
        result = 0
        mid = 0.5 * (local_buy + local_sell)
        if position > 0:
            result = mid - open_price
        else:
            result = open_price - mid
        strategy_stats.mtm = result

    def calculate_close_behavior(self, bid_price, ask_price, open_position, open_price, burnout):
        diff = lambda x, y: round(y - x, 2)
        TAKEPROFIT = 'TAKEPROFIT'
        MAKEBEST = 'MAKEBEST'
        AGGLOSS = 'AGGLOSS'

        if open_position > 0:
            direction = 'long'
            if bid_price < open_price - self.stop_loss_margin:
                if ask_price < open_price - self.loss_making_thold:
                    # active close
                    make_agg_ratio = diff(ask_price, open_price) / diff(bid_price, open_price)
                    if make_agg_ratio > self.makeagg_ratio_thold:
                        branch_flag = 1
                        close_behavior = AGGLOSS
                    else:
                        branch_flag = 2
                        close_behavior = MAKEBEST
                else:
                    if burnout:
                        branch_flag = 3
                        close_behavior = MAKEBEST
                    else:
                        branch_flag = 4
                        close_behavior = TAKEPROFIT
            else:
                # profit
                if ask_price < open_price - self.loss_making_thold:
                    branch_flag = 5
                    close_behavior = MAKEBEST
                else:
                    if burnout:
                        branch_flag = 6
                        close_behavior = MAKEBEST
                    else:
                        branch_flag = 7
                        close_behavior = TAKEPROFIT
        else:
            # short
            direction = 'short'
            if ask_price > open_price + self.stop_loss_margin:
                if bid_price > open_price + self.loss_making_thold:
                    # active close
                    make_agg_ratio = diff(bid_price, open_price) / diff(ask_price, open_price)
                    if make_agg_ratio > self.makeagg_ratio_thold:
                        branch_flag = 8
                        close_behavior = AGGLOSS
                    else:
                        branch_flag = 9
                        close_behavior = MAKEBEST
                else:
                    if burnout:
                        branch_flag = 10
                        close_behavior = MAKEBEST
                    else:
                        branch_flag = 11
                        close_behavior = TAKEPROFIT
            else:
                # profit
                if bid_price > open_price + self.loss_making_thold:
                    branch_flag = 12
                    close_behavior = MAKEBEST
                else:
                    if burnout:
                        branch_flag = 13
                        close_behavior = MAKEBEST
                    else:
                        branch_flag = 14
                        close_behavior = TAKEPROFIT

        return close_behavior, direction, branch_flag


    def create_slot_info(self, volume, price):
        price = round(price, 2)
        direction = COMMON.Direction.buy if volume > 0 else COMMON.Direction.sell
        log.info(
            f"[{self.strategy_id}] LIFT-SO-ACT-CREATE-SLOT, direction-{direction}, price-{price}, volume-{abs(volume)}, broker-{self.broker_id}"
        )
        # match broker to aggress
        # _, self.broker_id = current_front_price_brk(localview,
        #                                             COMMON.Direction().invert(COMMON.Direction.get(direction)),
        #                                             self.broker_list, True)
        return self.create_slot(direction, quantity=abs(volume), price=price, info="lift_"+direction.capitalize())

    def remove_slot_info(self, reason=None):
        strategy_stats = StrategyStats.from_dict(self.strategy_stats_dict)
        log.info(
            "[{}] {} LIFT-SO-ACT-REMOVE-SLOT: , ql: {}]".format(
                self.strategy_id, self.identifier , strategy_stats.aux_dict['ql'] )
        )
        return self.remove(reason)