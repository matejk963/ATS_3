import logging
import numpy as np
from copy import deepcopy

import autotrader_lib.common as COMMON
import autotrader_synthetic.config_util as SYNCONF
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB
from .strategy_stats import StrategyStats, get_avg_market_price_depth, current_front_price_brk
from .action_result import ActionResult
from .own_tools.instrument_key import InstrumentKey
tol = 1e-5

log = logging.getLogger("market_making.strategy_order")


class MarketMakingOrderLift(SYB.SyntheticOrderBase):
    broker_list = SYNCONF.ConfigOptionDescriptor(
        "broker_list", list,
        "List of brokers",
        required=True
    )

    product_id = SYNCONF.ConfigOptionDescriptor(
        "product_id", str,
        "Name of so's product id",
        required=True
    )

    other_instrument_id = SYNCONF.ConfigOptionDescriptor(
        "other_instrument_id", str,
        "Name of the lead instrument additional view, as used in the strategy template",
        required=True
    )

    other_product_id = SYNCONF.ConfigOptionDescriptor(
        "other_product_id", str,
        "Name of the other leading so's product id",
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

    bo_max = SYNCONF.SyntheticOrderConfigField(
        caption="bo_max",
        expected_type=float,
        description="Max bid ask spread for action",
    )

    strategy_stats_dict = SYNCONF.SyntheticOrderConfigField(
        caption="strategy_stats_dict",
        expected_type=dict,
        description="Object for strategy statistics"
    )

    strategy_id = SYNCONF.ConfigOptionDescriptor(
        "strategy_id", str,
        "strategy_id for logging",
        required=True
    )

    @property
    def instrument_key(self):
        return InstrumentKey(self.market_area, self.product_id)

    def _get_trade_params_old(self, localview, other_view):
        instrument_key_other = InstrumentKey(other_view.market_area, other_view.product_id)
        strategy_stats = StrategyStats.from_dict(self.strategy_stats_dict)
        net_position_other = strategy_stats.net_position[instrument_key_other.key]
        if net_position_other > 0:
            direction = COMMON.Direction.sell
            price = localview.current_front_price(COMMON.Direction.buy)
        else:
            direction = COMMON.Direction.buy
            price = localview.current_front_price(COMMON.Direction.sell)
        return abs(round(net_position_other, 6)), direction, price

    def _reduce_leg_position_action(self, thisview, strategy_stats):
        instrument_key = InstrumentKey(thisview.market_area, thisview.product_id)
        net_clip_pos = strategy_stats.net_clip_position[instrument_key.key]
        if net_clip_pos > 0:
            direction = COMMON.Direction.sell
        elif net_clip_pos < 0:
            direction = COMMON.Direction.buy
        else:
            return ActionResult(-np.inf, COMMON.Direction.buy, 0)
        if instrument_key == InstrumentKey().from_instrument_key(strategy_stats.leg1_instkey):
            c_our = strategy_stats.price_coeff[0]
        else:
            c_our = strategy_stats.price_coeff[1]
        # Calculate mtm of open leg position
        quantity = round(min(abs(net_clip_pos), self.num_clips) * strategy_stats.leg_clip_dict[instrument_key.key], 0)
        opn_price = strategy_stats.trade_leg_dict[instrument_key.key][COMMON.Direction().invert(direction)]['price']
        mkt_price = get_avg_market_price_depth(COMMON.Direction().invert(direction), thisview, quantity,
                                               self.broker_list)
        return ActionResult.reduce_leg_action(direction, quantity, mkt_price, opn_price) * c_our

    def _add_spread_position_action(self, thisview, strategy_stats):
        instrument_key = InstrumentKey(thisview.market_area, thisview.product_id)
        if instrument_key == InstrumentKey().from_instrument_key(strategy_stats.leg1_instkey):
            sign = 1.
            instrument_key_other = InstrumentKey().from_instrument_key(strategy_stats.leg2_instkey)
            c_our, c_oth = strategy_stats.price_coeff
        else:
            sign = -1.
            instrument_key_other = InstrumentKey().from_instrument_key(strategy_stats.leg1_instkey)
            c_oth, c_our = strategy_stats.price_coeff
        # Calculate open position for adding spread
        net_clip_this = strategy_stats.net_clip_position[instrument_key.key]
        net_clip_other = strategy_stats.net_clip_position[instrument_key_other.key]
        if np.sign(net_clip_this) * np.sign(net_clip_other) > 0:
            # Problem
            log.debug("[{}] WARNING ADD SPREAD Position the same direction:  {}//{}".format(
                self.strategy_id, net_clip_this, net_clip_other
            ))
            return ActionResult(-np.inf, COMMON.Direction.buy, 0)
        elif abs(net_clip_this) > tol:
            log.debug("[{}] ADD SPREAD Position Partial clip position:  {}//{}".format(
                self.strategy_id, net_clip_this, net_clip_other
            ))
            bool_partial = True
            net_clip_pos = net_clip_other + net_clip_this
        else:
            log.debug("[{}] ADD SPREAD Position Full clip position:  {}//{}".format(
                self.strategy_id, net_clip_this, net_clip_other
            ))
            bool_partial = False
            net_clip_pos = net_clip_other
        # Sign of position
        if net_clip_other > 0:
            direction = COMMON.Direction.sell
        else:
            direction = COMMON.Direction.buy
        opp_direction = COMMON.Direction().invert(direction)
        # Sign of spread
        if sign > 0:
            spread_direction = direction
        else:
            spread_direction = opp_direction
        quantity = round(min(abs(net_clip_pos), self.num_clips) * strategy_stats.leg_clip_dict[instrument_key.key], 0)
        # Calculate expected price of spread opening
        mkt_price = get_avg_market_price_depth(opp_direction, thisview, quantity,
                                               self.broker_list)
        opn_price_other = strategy_stats.trade_leg_dict[instrument_key_other.key][opp_direction]['price']
        if bool_partial:
            opn_price_this = strategy_stats.trade_leg_dict[instrument_key.key][direction]['price']
            price_this = (mkt_price * quantity + abs(net_clip_this) * opn_price_this) / (quantity + abs(net_clip_this))
        else:
            price_this = mkt_price
        if mkt_price is None:
            exp_price_spread = None
        else:
            exp_price_spread = sign * (c_our * price_this - c_oth * opn_price_other)
        return ActionResult.add_spread_action(direction, quantity, strategy_stats, spread_direction, exp_price_spread)

    def _add_spread_position_action_both(self, thisview, other_view, strategy_stats):
        instrument_key = InstrumentKey(thisview.market_area, thisview.product_id)
        if instrument_key == InstrumentKey().from_instrument_key(strategy_stats.leg1_instkey):
            sign = 1.
            instrument_key_other = InstrumentKey().from_instrument_key(strategy_stats.leg2_instkey)
            c_our, c_oth = strategy_stats.price_coeff
        else:
            sign = -1.
            instrument_key_other = InstrumentKey().from_instrument_key(strategy_stats.leg1_instkey)
            c_oth, c_our = strategy_stats.price_coeff
        # Calculate open position for adding spread
        net_clip_pos = strategy_stats.net_clip_position[instrument_key_other.key]
        # Sign of position
        if net_clip_pos > 0:
            direction = COMMON.Direction.sell
        else:
            direction = COMMON.Direction.buy
        opp_direction = COMMON.Direction().invert(direction)
        # Sign of spread
        if sign > 0:
            spread_direction = direction
        else:
            spread_direction = opp_direction
        remain_clip_other = self.num_clips - abs(net_clip_pos)
        quantity = round(self.num_clips * strategy_stats.leg_clip_dict[instrument_key.key], 0)
        quantity_other = round(remain_clip_other * strategy_stats.leg_clip_dict[instrument_key_other.key], 0)
        # Calculate expected price of spread opening
        mkt_price = get_avg_market_price_depth(opp_direction, thisview, quantity,
                                               self.broker_list)
        mkt_price_other = get_avg_market_price_depth(direction, other_view, quantity_other,
                                                     self.broker_list)
        opn_price_other = strategy_stats.trade_leg_dict[instrument_key_other.key][opp_direction]['price']
        if mkt_price_other is None:
            price_other = None
        else:
            price_other = (opn_price_other * abs(net_clip_pos) + mkt_price_other + remain_clip_other) / self.num_clips
        if (mkt_price is None) or (price_other is None):
            exp_price_spread = None
        else:
            exp_price_spread = sign * (c_our * mkt_price - c_oth * price_other)
        return ActionResult.add_spread_action(direction, quantity, strategy_stats, spread_direction, exp_price_spread)

    def _hold_position_action(self, thisview, strategy_stats):
        instrument_key = InstrumentKey(thisview.market_area, thisview.product_id)
        if instrument_key == InstrumentKey().from_instrument_key(strategy_stats.leg1_instkey):
            c_our = strategy_stats.price_coeff[0]
        else:
            c_our = strategy_stats.price_coeff[1]
        net_clip_pos = strategy_stats.net_clip_position[instrument_key.key]
        if abs(net_clip_pos) < 1:
            if net_clip_pos > 0:
                direction = COMMON.Direction.sell
                sign = 1.
            else:
                direction = COMMON.Direction.buy
                sign = -1.
            opp_direction = COMMON.Direction().invert(direction)
            quantity = round(min(abs(net_clip_pos), self.num_clips) * strategy_stats.leg_clip_dict[instrument_key.key],
                             0)
            opn_price = strategy_stats.trade_leg_dict[instrument_key.key][opp_direction]['price']
            mkt_price = strategy_stats.get_instrument_model_price(instrument_key.key)
            action_value = sign * c_our * (mkt_price - opn_price)
        else:
            action_value = -np.inf
            direction = COMMON.Direction.buy
            quantity = 0
        return ActionResult(action_value, direction, quantity)

    def _get_trade_params(self, localview, other_view, strategy_stats):
        if strategy_stats.manage_pos:
            no_action_bool = True
            log.debug("[{}] LIFT-NO-ACT Position being managed:  {}[{}]".format(
                self.strategy_id, self.market_area, self.product_id
            ))
        else:
            no_action_bool = False

        instrument_key_local = InstrumentKey(localview.market_area, localview.product_id)
        instrument_key_other = InstrumentKey(other_view.market_area, other_view.product_id)

        hold_bool = False
        hld_instkey = instrument_key_local.key

        net_clip_local = strategy_stats.net_clip_position[instrument_key_local.key]
        net_clip_other = strategy_stats.net_clip_position[instrument_key_other.key]
        if abs(net_clip_local) > abs(net_clip_other):
            # Reduce clip on local leg or get into spread
            red_action = self._reduce_leg_position_action(localview, strategy_stats)
            hld_action = self._hold_position_action(localview, strategy_stats)
            if (abs(net_clip_other) > 0) and (abs(net_clip_other) < 1):
                # Get into spread Partial - hold no action
                add_action = self._add_spread_position_action(other_view, strategy_stats)
                hld_action.quantity = 0
            elif abs(net_clip_local) < 1:
                # Get both legs into spread
                add_action = self._add_spread_position_action_both(other_view, localview, strategy_stats)
            else:
                # Get into spread NO partial
                add_action = self._add_spread_position_action(other_view, strategy_stats)
            add_action.quantity = 0
        elif abs(net_clip_local) < abs(net_clip_other):
            # Reduce clip on other leg or get into spread
            red_action = self._reduce_leg_position_action(other_view, strategy_stats)
            hld_action = self._hold_position_action(other_view, strategy_stats)
            red_action.quantity = 0
            hld_instkey = instrument_key_other.key
            if (abs(net_clip_local) > 0) and (abs(net_clip_local) < 1):
                # Get into spread Partial - hold action
                add_action = self._add_spread_position_action(localview, strategy_stats)
            elif abs(net_clip_other) < 1:
                # Get both legs into spread
                add_action = self._add_spread_position_action_both(localview, other_view, strategy_stats)
                hld_action.quantity = 0
            else:
                add_action = self._add_spread_position_action(localview, strategy_stats)
                hld_action.quantity = 0
        else:
            # Clip amounts equals no balancing needed
            no_action_bool = True
            red_action = ActionResult(0, COMMON.Direction.buy, 0)
            add_action = ActionResult(0, COMMON.Direction.buy, 0)
            hld_action = ActionResult(0, COMMON.Direction.buy, 0)
        # Print actions
        log.debug("[{}] LIFT Actions Reduce//AddSpread//Hold:  {}[{}]: {}//{}//{}".format(
            self.strategy_id, self.market_area, self.product_id,
            red_action.value, add_action.value, hld_action.value
        ))
        # Evaluate actions
        if no_action_bool or (red_action.is_none and add_action.is_none):
            # Do nothing
            act_position = 0
            direction = COMMON.Direction.buy
            log.debug("[{}] LIFT-NO-ACT due to balance/None both [OpenPos vs Other OpenPos]:  {}[{}]: {} vs {}".format(
                self.strategy_id, self.market_area, self.product_id, net_clip_local, net_clip_other
            ))
        elif red_action.is_none:
            if add_action < -self.stop_loss:
                # Do nothing
                act_position = 0
                direction = COMMON.Direction.buy
                log.debug("[{}] LIFT-NO-ACT due to stop loss [OpenPos vs Other OpenPos]:  {}[{}]: {} vs {}".format(
                    self.strategy_id, self.market_area, self.product_id, net_clip_local, net_clip_other
                ))
            else:
                # Add spread action activated
                act_position = add_action.quantity
                direction = add_action.side
                log.debug("[{}] LIFT-ADD-POS-ACT [OpenPos vs Value]:  {}[{}]: {} vs {}, ".format(
                    self.strategy_id, self.market_area, self.product_id, net_clip_local, add_action.value
                ))
        elif add_action.is_none:
            # Reduce leg action activated
            act_position = red_action.quantity
            direction = red_action.side
            log.debug("[{}] LIFT-RED-POS-ACT [OpenPos vs Value]:  {}[{}]: {} vs {}, ".format(
                self.strategy_id, self.market_area, self.product_id, net_clip_local, red_action.value
            ))
        else:
            if max(red_action, add_action) < 0 and hld_action > max(red_action, add_action):
                # Hold action activated
                act_position = hld_action.quantity
                direction = hld_action.side
                log.debug("[{}] LIFT-HOLD-POS-ACT [OpenPos vs Value]:  {}[{}]: {} vs {}, ".format(
                    self.strategy_id, self.market_area, self.product_id, net_clip_local, hld_action.value
                ))
                hold_bool = True
            elif red_action > add_action + (self.margin / 2):
                # Reduce leg action activated
                act_position = red_action.quantity
                direction = red_action.side
                log.debug("[{}] LIFT-RED-POS-ACT [OpenPos vs Value]:  {}[{}]: {} vs {}, ".format(
                    self.strategy_id, self.market_area, self.product_id, net_clip_local, red_action.value
                ))
            else:
                # Add spread action activated
                act_position = add_action.quantity
                direction = add_action.side
                log.debug("[{}] LIFT-ADD-POS-ACT [OpenPos vs Value]:  {}[{}]: {} vs {}, ".format(
                    self.strategy_id, self.market_area, self.product_id, net_clip_local, add_action.value
                ))
        if hold_bool:
            # price = localview.current_front_price(direction)
            price, self.broker_id = current_front_price_brk(localview, direction, self.broker_list, True)
        else:
            # price = localview.current_front_price(COMMON.Direction().invert(direction))
            price, self.broker_id = current_front_price_brk(localview, COMMON.Direction().invert(direction),
                                                            self.broker_list, True)
        StrategyStats.from_dict(self.strategy_stats_dict).hold_dict[hld_instkey] = hold_bool
        return act_position, direction, price

    def _stop_loss_trigger(self, localview, other_view, strategy_stats):
        instrument_key_local = InstrumentKey(localview.market_area, localview.product_id)
        instrument_key_other = InstrumentKey(other_view.market_area, other_view.product_id)
        if strategy_stats.manage_pos:
            no_action_bool = True
            log.debug("[{}] LIFT-STOP-LOSS-NO-ACT Position being managed:  {}[{}]".format(
                self.strategy_id, self.market_area, self.product_id
            ))
        else:
            no_action_bool = False
        # Calculate bo spread of legs
        bo_local = strategy_stats.bo_legs_dict[instrument_key_local.key]
        bo_other = strategy_stats.bo_legs_dict[instrument_key_other.key]
        # Evaluate actions
        # Check for imbalance
        net_clip_pos = strategy_stats.total_net_position
        if no_action_bool:
            # Do nothing
            quantity = 0
            direction = COMMON.Direction.buy
            log.debug("[{}] LIFT-NO-ACT [OpenPos]:  {}[{}]: {}".format(
                self.strategy_id, self.market_area, self.product_id, net_clip_pos
            ))
        else:
            if abs(net_clip_pos) > 0:
                # Reduce imbalance position
                quantity, direction = self._reduce_imbalance_pos(strategy_stats, instrument_key_local,
                                                                 instrument_key_other, bo_local - self.bo_max)
            else:
                # Reduce spread position
                quantity, direction = self._reduce_spread_pos(strategy_stats, instrument_key_local,
                                                              max(bo_local, bo_other) - self.bo_max)
        opp_direction = COMMON.Direction().invert(direction)
        # Calculate price
        price_clip = get_avg_market_price_depth(opp_direction, localview, quantity, self.broker_list)
        # price = localview.current_front_price(opp_direction, self.broker_id)
        price, self.broker_id = current_front_price_brk(localview, opp_direction, self.broker_list, True)
        if price_clip is None:
            act_position = 0
        else:
            act_position = quantity
        return act_position, direction, price

    def _reduce_spread_pos(self, strategy_stats, instrument_key, bo_exceed):
        # Calculate open position of spread
        net_spread_pos = strategy_stats.net_spread_position
        if instrument_key == InstrumentKey.from_instrument_key(strategy_stats.leg1_instkey):
            sign = 1
        elif instrument_key == InstrumentKey.from_instrument_key(strategy_stats.leg2_instkey):
            sign = -1
        else:
            raise ValueError("Lift so Unknown instrument key: %s." % instrument_key.key)
        if sign * np.sign(net_spread_pos) > 0:
            direction = COMMON.Direction.sell
        else:
            direction = COMMON.Direction.buy
        if bo_exceed > 0:
            quantity = 0
        else:
            quantity = round(min(abs(net_spread_pos), self.num_clips) * strategy_stats.leg_clip_dict[instrument_key.key],
                             0)
        return quantity, direction

    def _reduce_imbalance_pos(self, strategy_stats, instrument_key_local, instrument_key_other, bo_exceed):
        # Calculate open position of individual legs
        net_clip_local = strategy_stats.net_clip_position[instrument_key_local.key]
        net_clip_other = strategy_stats.net_clip_position[instrument_key_other.key]
        if abs(net_clip_local) > abs(net_clip_other):
            # Reduce position on local leg
            if net_clip_local > 0:
                direction = COMMON.Direction.sell
            else:
                direction = COMMON.Direction.buy
            if bo_exceed > 0:
                quantity = 0
            else:
                quantity = round(min(abs(net_clip_local), self.num_clips) *
                                 strategy_stats.leg_clip_dict[instrument_key_local.key], 0)
        else:
            direction = COMMON.Direction.buy
            quantity = 0
        return quantity, direction

    def stop_loss_check(self, strategy_stats):
        # Return whether trigger stop loss or not
        if strategy_stats.manage_pos:
            return False
        net_clip_pos = strategy_stats.total_net_position
        net_spread_pos = strategy_stats.net_spread_position
        if abs(net_clip_pos) > 0:
            return strategy_stats.stop_loss
        elif abs(net_spread_pos) < tol:
            return False
        else:
            # Calculate mtm of open spread position
            trade_spread_dict = strategy_stats.price_vol_trade_spread_dict
            if net_spread_pos > 0:
                direction = COMMON.Direction.buy
            else:
                direction = COMMON.Direction.sell
            mtm_spread = strategy_stats.mtm_spread(direction, trade_spread_dict[direction].price)
            if mtm_spread <= -self.stop_loss:
                return True
            else:
                return False

    def act(self, localview, additional_views, timestamp):
        self.broker_id = self.broker_list[0]
        other_view = additional_views.get_view_for_instrument(
            self.other_instrument_id,
            self.other_product_id,
        )
        other_inst_key = InstrumentKey(self.other_instrument_id, self.other_product_id)

        strategy_stats_freeze = StrategyStats.from_dict(deepcopy(self.strategy_stats_dict))
        act_position, direction, price = self._get_trade_params(localview, other_view, strategy_stats_freeze)
        # if self.stop_loss_check(strategy_stats_freeze):
        #     stop_loss_bool = True
        #     act_position, direction, price = self._stop_loss_trigger(localview, other_view, strategy_stats_freeze)
        # else:
        #     stop_loss_bool = False
        #     act_position, direction, price = self._get_trade_params(localview, other_view, strategy_stats_freeze)

        log.debug("[{}] LIFT-SO-ACT [OpenPos]:  {}[{}]: {}_{}@{}".format(
            self.strategy_id, self.market_area, self.product_id, direction, act_position, price
        ))
        strategy_stats = StrategyStats.from_dict(self.strategy_stats_dict)
        if act_position > 0 and strategy_stats_freeze.lift_bool(other_inst_key.key):
            strategy_stats.balancing = True
            strategy_stats.lock_lift_instkey(self.instrument_key.key)
            # if stop_loss_bool:
            #     strategy_stats.stop_loss = True
            # else:
            #     strategy_stats.lock_lift_instkey(self.instrument_key.key)
            return self.create_slot(direction, act_position, price, info="MarketMakingLift")
        else:
            return self.remove()
