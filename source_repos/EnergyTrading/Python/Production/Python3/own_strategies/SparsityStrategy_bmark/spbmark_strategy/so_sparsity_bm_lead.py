import logging

import autotrader_lib.common as COMMON
import autotrader_synthetic.config_util as SYNCONF
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB
from .strategy_stats import StrategyStats, current_front_price_brk, aon_check
from .predictors import predictor_sparsity
from .OB_attributes import OB_attributes

log = logging.getLogger("sparsity_bmark.lead_order")
tol = 1e-3

#QUANTITY_TICK_SIZE = 10


class SpBMarkOrder(SYB.SyntheticOrderBase):
    broker_list = SYNCONF.ConfigOptionDescriptor(
        "broker_list", list,
        "List of brokers",
        required=True
    )

    own_product_id = SYNCONF.ConfigOptionDescriptor(
        "own_product_id", str,
        "Own Product ID, which is passed to the 2nd arbitrage leg synthetic order as 'other'",
        required=True
    )

    lift_slot_name = SYNCONF.ConfigOptionDescriptor(
        "lift_slot_name", str,
        "Name of the lifting slot",
        required=True
    )

    lift_instrument_id = SYNCONF.ConfigOptionDescriptor(
        "lift_instrument_id", str,
        "Name of the lift instrument additional view, as used in the strategy template",
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

    max_position = SYNCONF.SyntheticOrderConfigField(
        caption="max position",
        expected_type=float,
        description="What is the maximum slot_size",
    )

    ql_max = SYNCONF.SyntheticOrderConfigField(
        caption="maximal_allowed_queue_lag",
        expected_type=float,
        description="Maximal allowed queue lag for strategy",
    )

    reset_bool = SYNCONF.SyntheticOrderConfigField(
        caption="autoTrader_reset",
        expected_type=bool,
        description="autoTrader reset boolean",
    )

    trd_gap = SYNCONF.SyntheticOrderConfigField(
        caption="trade_gap",
        expected_type=float,
        description="Gap between best order and trade needed for a lead action",
    )

    bid_ask = SYNCONF.SyntheticOrderConfigField(
        caption="bid_ask_spread",
        expected_type=float,
        description="Gap between best orders",
    )
    thold_dense = SYNCONF.SyntheticOrderConfigField(
        caption="thold_dense",
        expected_type=float,
        description="thold dense",
    )

    thold_sparse = SYNCONF.SyntheticOrderConfigField(
        caption="thold_sparse",
        expected_type=float,
        description="thold sparse",
    )

    lead_closing = SYNCONF.SyntheticOrderConfigField(
        caption="lead closing",
        expected_type=bool,
        description="lead closing bool",
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


    def condition_data_check(self, data):
        self.data_columns = ['trd_price', 'b_price', 'a_price', 'ba_spread', 'a_price_sparsity', 'b_price_sparsity']
        return all([x in self.data_columns for x in data.keys()])

    def condition_long(self, data):
        x = {}
        x['trd_gap'] = data['trd_price'] > round(data['a_price'] + self.trd_gap, 2)
        x['ba_spread'] = data['ba_spread'] < self.bid_ask
        x['misstrade_limit'] = data['trd_price'] < round(data['a_price'] + 0.5, 2)
        x['sparsity'] = data['a_price_sparsity'] > self.thold_sparse and data['b_price_sparsity'] < self.thold_dense
        log.info(f"[CONDITION LONG]: {x}")
        return all(x.values())

    def condition_short(self, data):
        x = {}
        x['trd_gap'] = data['trd_price'] < round(data['b_price'] - self.trd_gap, 2)
        x['ba_spread'] = data['ba_spread'] < self.bid_ask
        x['misstrade_limit'] = data['trd_price'] > round(data['b_price'] - 0.5, 2)
        x['sparsity'] = data['b_price_sparsity'] > self.thold_sparse and data['a_price_sparsity'] < self.thold_dense
        log.info(f"[CONDITION SHORT]: {x}")
        return all(x.values())

    def check_all_conditions(self, strategy_stats, localview, timestamp, data_dict):
        """
        Check all entry conditions in one place and return comprehensive results
        """
        conditions = {}
        
        # Basic checks
        conditions['hard_stoploss'] = not strategy_stats.hard_sl
        conditions['lead_closing'] = self.lead_closing or round(self.get_open_position()) == 0
        conditions['reset_bool'] = not self.reset_bool
        conditions['has_trade_data'] = bool(strategy_stats.aux_dict['trade_id'])
        
        # Last trade age check (moved from act method)
        conditions['trade_age_valid'] = True
        if isinstance(strategy_stats.aux_dict['timestamp'], int):
            conditions['trade_age_valid'] = strategy_stats.aux_dict['timestamp'] + 1 >= timestamp
        
        # Trade duplicate check
        conditions['trade_not_processed'] = True
        if hasattr(self, 'processed_trade_id'):
            conditions['trade_not_processed'] = (
                self.processed_trade_id != strategy_stats.aux_dict['trade_id'] and 
                self.processed_trade_ts <= strategy_stats.aux_dict['timestamp']
            )
        
        # Market data conditions
        if data_dict:
            conditions['data_valid'] = self.condition_data_check(data_dict)
            conditions['long_conditions'] = self.condition_long(data_dict) if conditions['data_valid'] else False
            conditions['short_conditions'] = self.condition_short(data_dict) if conditions['data_valid'] else False
        else:
            conditions['data_valid'] = False
            conditions['long_conditions'] = False
            conditions['short_conditions'] = False
        
        # Overall entry decision
        conditions['can_enter'] = all([
            conditions['hard_stoploss'],
            conditions['lead_closing'], 
            conditions['reset_bool'],
            conditions['has_trade_data'],
            conditions['trade_age_valid'],
            conditions['trade_not_processed'],
            conditions['data_valid'],
            (conditions['long_conditions'] or conditions['short_conditions'])
        ])
        
        return conditions

    def prepare_data_dict(self, localview, strategy_stats):
        try:
            obAttr = OB_attributes(localview, self.market_area)
            local_buy = localview.current_front_price(COMMON.Direction.buy)
            local_sell = localview.current_front_price(COMMON.Direction.sell)
            spread = round(local_sell - local_buy, 2)
            trade_price = strategy_stats.aux_dict['last_traded_price']
            sparsity = predictor_sparsity(obAttr)
            data_dict = {
                'b_price': local_buy,
                'a_price': local_sell,
                'ba_spread': spread,
                'trd_price': trade_price,
            }
            data_dict = {**data_dict, **sparsity}
            return data_dict
        except Exception as e:
            log.error(f"[PREPARE data_dict] - exception: {e}, lineno{e.__traceback__.tb_lineno}")
            return None

    def act(self, localview, additional_views, timestamp):
        try:
            # Set broker_id to primary (EEX)
            self.broker_id = self.broker_list[0]
            # Strategy stats object
            strategy_stats = StrategyStats.from_dict(self.strategy_stats_dict)
            
            # Check basic market data availability
            local_buy = localview.current_front_price(COMMON.Direction.buy)
            local_sell = localview.current_front_price(COMMON.Direction.sell)
            if not local_buy or not local_sell:
                return self.remove_slot_info('None orders')
            
            # Prepare data dictionary for condition checking
            data_dict = self.prepare_data_dict(localview, strategy_stats)
            
            # Check all conditions in one place
            conditions = self.check_all_conditions(strategy_stats, localview, timestamp, data_dict)
            
            # Log trade decision for tracking
            decision_data = {
                'conditions': conditions,
                'market_data': data_dict,
                'open_position': self.get_open_position(),
                'entry_decision': 'enter' if conditions['can_enter'] else 'no_enter',
                'reason': self._get_rejection_reason(conditions) if not conditions['can_enter'] else 'conditions_met'
            }
            
            strategy_stats.log_trade_decision(
                strategy_stats.aux_dict['trade_id'], 
                timestamp, 
                decision_data
            )
            
            # Update processed trade tracking
            if conditions['has_trade_data'] and conditions['trade_not_processed']:
                self.processed_trade_id = strategy_stats.aux_dict['trade_id']
                self.processed_trade_ts = strategy_stats.aux_dict['timestamp']
            
            # Early returns for failed conditions
            if not conditions['can_enter']:
                return self.remove_slot_info(decision_data['reason'])
            
            # Update sparsity in strategy stats
            if data_dict:
                self.strategy_stats_dict['param_dict']['b_price_sparsity'] = data_dict.get('b_price_sparsity', 0.0)
                self.strategy_stats_dict['param_dict']['a_price_sparsity'] = data_dict.get('a_price_sparsity', 0.0)
            
            # Calculate action
            open_position = self.get_open_position()
            price, volume = self.calculate_action(data_dict, conditions['long_conditions'], conditions['short_conditions'], open_position)

            if round(volume) != 0:
                strategy_stats.set_lead_persistance(True, timestamp, price, volume)
                return self.create_slot_info(volume, price, localview)
            else:
                return self.remove_slot_info("LEAD condition was not met")

        except Exception as e:
            log.error(f'[LEAD] {e}, line number: {e.__traceback__.tb_lineno}')
            return self.remove_slot_info(str(e))
    
    def _get_rejection_reason(self, conditions):
        """Get human readable reason for trade rejection"""
        if not conditions['hard_stoploss']:
            return '[HARD STOPLOSS] - pnl has reached stoploss'
        elif not conditions['lead_closing']:
            return f'[LEAD CLOSING] - lead_closing={self.lead_closing}, position={self.get_open_position()}'
        elif not conditions['reset_bool']:
            return '[RESET BOOL] - reset flag is TRUE'
        elif not conditions['has_trade_data']:
            return '[NO TRADE] - no trade data for this product'
        elif not conditions['trade_age_valid']:
            return '[OLD TRADE] - trade data too old'
        elif not conditions['trade_not_processed']:
            return '[DUPLICATE TRADE] - already processed this trade'
        elif not conditions['data_valid']:
            return '[DATA ERROR] - market data preparation failed'
        elif not (conditions['long_conditions'] or conditions['short_conditions']):
            return '[CONDITIONS NOT MET] - neither long nor short conditions satisfied'
        else:
            return '[UNKNOWN] - unspecified rejection reason'

    def calculate_action(self, data_dict, long, short, open_position):
        a_price, b_price = data_dict['a_price'], data_dict['b_price']
        volume = 0
        if long and short:
            if open_position >= 0:
                volume = round(self.max_position - open_position)
            else:
                volume = -round(self.max_position + open_position)
        elif long:
            if open_position < 0:
                volume = abs(open_position)
            else:
                volume = round(self.max_position - open_position)
        elif short:
            if open_position > 0:
                volume = -open_position
            else:
                volume = -round(self.max_position + open_position)

        price = a_price if volume > 0 else b_price
        return price, volume

    def create_slot_info(self, volume, price, localview):
        price = round(price, 2)
        direction = COMMON.Direction.buy if volume > 0 else COMMON.Direction.sell
        inverted_direction = COMMON.Direction().invert(COMMON.Direction.get(direction))
        log.info(
            f"[{self.strategy_id}] LEAD-SO-ACT-CREATE-SLOT, direction-{direction}, price-{price}, volume-{abs(volume)}, broker-{self.broker_id}"
        )
        # match broker to aggress
        _, self.broker_id = current_front_price_brk(localview,
                                                    inverted_direction,
                                                    self.broker_list, True)
        log.info(f"[{self.strategy_id}] broker_id chosen: {self.broker_id}, broker_list[0]: {self.broker_list[0]}")
        if self.broker_id == self.broker_list[0]:
            return self.remove_slot_info("Best order is EEX, no action")
        aon = aon_check(localview, inverted_direction, price, abs(volume), self.broker_id, self.market_area)
        log.info(f"[{self.strategy_id}] AON check result: {aon}, direction: {inverted_direction}, price: {price}, volume: {abs(volume)}, broker: {self.broker_id}")
        if not aon:
            return self.remove_slot_info("AON check False")
        else:
            return self.create_slot(direction, quantity=abs(volume), price=price, info="lead_"+direction.capitalize())

    def remove_slot_info(self, reason):
        strategy_stats = StrategyStats.from_dict(self.strategy_stats_dict)
        log.info(
            "[{}] {} LEAD-SO-ACT-REMOVE-SLOT: , ql: {}, reason: {}]".format(
                self.strategy_id, self.identifier, strategy_stats.aux_dict['ql'], reason)
        )
        return self.remove(reason)


