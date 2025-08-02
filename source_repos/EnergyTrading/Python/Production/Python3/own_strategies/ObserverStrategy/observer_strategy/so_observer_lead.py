import logging
import numpy as np
import autotrader_lib.common as COMMON
import autotrader_synthetic.config_util as SYNCONF
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB
from .strategy_stats import StrategyStats, current_front_price_brk, aon_check
from .predictors import predictor_sparsity
from .OB_attributes import OB_attributes

log = logging.getLogger("observer_strategy.lead_order")
tol = 1e-3

class ObserverLeadOrder(SYB.SyntheticOrderBase):
    broker_list = SYNCONF.ConfigOptionDescriptor(
        "broker_list", list,
        "List of brokers",
        required=True
    )

    own_product_id = SYNCONF.ConfigOptionDescriptor(
        "own_product_id", str,
        "Own Product ID",
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

    def condition_data_check(self, data_dict):
        conditions = {}
        conditions['ba_spread_valid'] = data_dict.get('ba_spread', 0) > 0
        conditions['trade_price_valid'] = data_dict.get('trd_price', 0) > 0
        conditions['sparsity_data_valid'] = (
            data_dict.get('b_price_sparsity', 0) > 0 and 
            data_dict.get('a_price_sparsity', 0) > 0
        )
        
        all_valid = all(conditions.values())
        log.info(f"[OBSERVER_DATA_CHECK]: {conditions} -> {all_valid}")
        
        # TEMPORARY DEBUG: Allow processing even if conditions fail, to test basic mechanism
        if not all_valid:
            log.info(f"[OBSERVER_DATA_CHECK]: Conditions failed but proceeding anyway for debugging")
            return True
        
        return all_valid

    def condition_long(self, data_dict):
        """Check LONG entry conditions like SparsityStrategy_bmark"""
        x = {}
        x['trd_gap'] = data_dict['trd_price'] > round(data_dict['a_price'] + 0.10, 2)  # Using 0.10 as default trd_gap
        x['ba_spread'] = data_dict['ba_spread'] < 1.0  # Using 1.0 as default bid_ask
        x['misstrade_limit'] = data_dict['trd_price'] < round(data_dict['a_price'] + 0.5, 2)
        x['sparsity'] = data_dict['a_price_sparsity'] > 0.20 and data_dict['b_price_sparsity'] < 0.70  # Default thresholds
        
        all_met = all(x.values())
        log.info(f"[CONDITION LONG]: {x} -> LONG_POSSIBLE: {all_met}")
        return all_met

    def condition_short(self, data_dict):
        """Check SHORT entry conditions like SparsityStrategy_bmark"""
        x = {}
        x['trd_gap'] = data_dict['trd_price'] < round(data_dict['b_price'] - 0.10, 2)  # Using 0.10 as default trd_gap
        x['ba_spread'] = data_dict['ba_spread'] < 1.0  # Using 1.0 as default bid_ask
        x['misstrade_limit'] = data_dict['trd_price'] > round(data_dict['b_price'] - 0.5, 2)
        x['sparsity'] = data_dict['b_price_sparsity'] > 0.20 and data_dict['a_price_sparsity'] < 0.70  # Default thresholds
        
        all_met = all(x.values())
        log.info(f"[CONDITION SHORT]: {x} -> SHORT_POSSIBLE: {all_met}")
        return all_met

    def prepare_data_dict(self, localview, strategy_stats):
        try:
            obAttr = OB_attributes(localview, self.market_area)
            
            # Basic order book metrics
            data_dict = {
                'b_price': obAttr.bid_price(),
                'a_price': obAttr.ask_price(),
                'ba_spread': obAttr.ba_spread(),
                'mid_price': obAttr.mid_price(),
                'trd_price': strategy_stats.aux_dict['last_traded_price'] or 0,
                'trd_object': strategy_stats.aux_dict['trd_object'],
                'bid_volume': obAttr.bid_volume(),
                'ask_volume': obAttr.ask_volume(),
                'bid_broker': obAttr.bid_broker(),
                'ask_broker': obAttr.ask_broker(),
                
                # Order book depth metrics
                'n_bids': len(obAttr.bids),
                'n_asks': len(obAttr.asks),
                
                # Volume ratios at different depths
                'vol_ratio_0_1': obAttr.vol_ratio(0.1),
                'vol_ratio_0_5': obAttr.vol_ratio(0.5),
                'vol_ratio_1_0': obAttr.vol_ratio(1.0),
                
                # Weighted mid prices at different depths (like ba_volrat pattern)
                'mid_priceW_00': obAttr.mid_priceW(0.0),
                'mid_priceW_05': obAttr.mid_priceW(0.05),
                'mid_priceW_08': obAttr.mid_priceW(0.08),
                'mid_priceW_10': obAttr.mid_priceW(0.10),
                'mid_priceW_15': obAttr.mid_priceW(0.15),
                'mid_priceW_20': obAttr.mid_priceW(0.20),
                'mid_priceW_25': obAttr.mid_priceW(0.25),
                
                # BA volume ratios at different depths
                'ba_volrat_00': obAttr.vol_ratio(0.0),
                'ba_volrat_05': obAttr.vol_ratio(0.05),
                'ba_volrat_08': obAttr.vol_ratio(0.08),
                'ba_volrat_10': obAttr.vol_ratio(0.10),
                'ba_volrat_15': obAttr.vol_ratio(0.15),
                'ba_volrat_20': obAttr.vol_ratio(0.20),
                'ba_volrat_25': obAttr.vol_ratio(0.25),
            }
            
            # Sparsity metrics
            sparsity = predictor_sparsity(obAttr)
            data_dict = {**data_dict, **sparsity}
            
            return data_dict
        except Exception as e:
            log.error(f"[OBSERVER_PREPARE data_dict] - exception: {e}, lineno{e.__traceback__.tb_lineno}")
            return None

    def check_all_conditions(self, strategy_stats, localview, timestamp, data_dict):
        """
        Check all observation conditions and trading conditions
        """
        conditions = {}
        
        # Basic checks
        conditions['has_trade_data'] = bool(strategy_stats.aux_dict['trade_id'])
        
        # Trade age check
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
            # Calculate trading conditions for analysis (but don't trade)
            conditions['long_conditions'] = self.condition_long(data_dict) if conditions['data_valid'] else False
            conditions['short_conditions'] = self.condition_short(data_dict) if conditions['data_valid'] else False
        else:
            conditions['data_valid'] = False
            conditions['long_conditions'] = False
            conditions['short_conditions'] = False
        
        # Observer can observe all trades (no actual trading conditions)
        conditions['can_observe'] = (
            conditions['has_trade_data'] and 
            conditions['trade_age_valid'] and 
            conditions['trade_not_processed'] and 
            conditions['data_valid']
        )
        
        log.info(f"[OBSERVER_CONDITIONS]: {conditions}")
        return conditions

    def _get_observation_reason(self, conditions):
        """Get reason for observation result"""
        if not conditions['has_trade_data']:
            return 'no_trade_data'
        if not conditions['trade_age_valid']:
            return 'trade_too_old'
        if not conditions['trade_not_processed']:
            return 'trade_already_processed'
        if not conditions['data_valid']:
            return 'invalid_market_data'
        return 'observed'

    def act(self, localview, additional_views, timestamp):
        try:
            log.info(f"[DEBUG][OBSERVER_LEAD] *** ACT METHOD CALLED *** timestamp: {timestamp}")
            # Work directly with the shared strategy_stats_dict like in working implementation
            log.info(f"[DEBUG][OBSERVER_LEAD] Act called - trade_id: {self.strategy_stats_dict['aux_dict'].get('trade_id')}, timestamp: {timestamp}")
            log.info(f"[DEBUG][OBSERVER_LEAD] strategy_stats_dict keys: {list(self.strategy_stats_dict.keys())}")
            log.info(f"[DEBUG][OBSERVER_LEAD] aux_dict contents: {self.strategy_stats_dict['aux_dict']}")
            
            # Initialize processed_trades set if not exists
            if not hasattr(self, 'processed_trades'):
                self.processed_trades = set()
                log.info("[DEBUG][OBSERVER_LEAD] Initialized processed_trades set")
            
            # Check that market_data_dict and predictor_dict exist in shared dict (should be initialized by StrategyStats)
            market_data_count = len(self.strategy_stats_dict.get('market_data_dict', {}))
            predictor_data_count = len(self.strategy_stats_dict.get('predictor_dict', {}))
            log.info(f"[DEBUG][OBSERVER_LEAD] market_data_dict has {market_data_count} entries, predictor_dict has {predictor_data_count} entries")

            # Check basic market data availability
            local_buy = localview.current_front_price(COMMON.Direction.buy)
            local_sell = localview.current_front_price(COMMON.Direction.sell)
            log.info(f"[DEBUG][OBSERVER_LEAD] Market prices - bid: {local_buy}, ask: {local_sell}")
            
            
            if not local_buy or not local_sell:
                log.info(f"[DEBUG][OBSERVER_LEAD] Missing market prices, returning")
                return self.remove_slot_info('No orders available')
            
            # ONLY collect data when we have actual trade data (not just order book updates)
            has_trade_data = bool(self.strategy_stats_dict['aux_dict'].get('trade_id'))
            trade_price = self.strategy_stats_dict['aux_dict'].get('last_traded_price')
            current_trade_id = self.strategy_stats_dict['aux_dict'].get('trade_id')
            
            if not has_trade_data:
                log.info(f"[DEBUG][OBSERVER_LEAD] No trade data in aux_dict, skipping data collection (order book update)")
                return self.remove_slot_info('No trade data')
            
            if trade_price is None:
                log.info(f"[DEBUG][OBSERVER_LEAD] Trade price is None, skipping data collection")
                return self.remove_slot_info('No trade price')
            
            # Check if we already processed this trade (avoid duplicates)
            if current_trade_id in self.processed_trades:
                log.info(f"[DEBUG][OBSERVER_LEAD] Trade {current_trade_id} already processed, skipping duplicate")
                return self.remove_slot_info('Trade already processed')
            
            # Mark trade as processed
            self.processed_trades.add(current_trade_id)
            log.info(f"[DEBUG][OBSERVER_LEAD] Processing NEW trade {current_trade_id} (total processed: {len(self.processed_trades)})")
            
            # Create StrategyStats object for operations like SparsityStrategy pattern
            log.info(f"[DEBUG][OBSERVER_LEAD] Creating StrategyStats from dict")
            strategy_stats = StrategyStats.from_dict(self.strategy_stats_dict)
            
            # Update market data using StrategyStats object (ONLY for actual trades)
            log.info(f"[DEBUG][OBSERVER_LEAD] Adding market data for trade {strategy_stats.aux_dict['trade_id']}")
            strategy_stats.market_data_dict['timestamp'].append(strategy_stats.aux_dict['timestamp'])
            strategy_stats.market_data_dict['trade_id'].append(strategy_stats.aux_dict['trade_id'])
            strategy_stats.market_data_dict['trd_price'].append(trade_price)
            strategy_stats.market_data_dict['b_price'].append(local_buy)
            strategy_stats.market_data_dict['a_price'].append(local_sell)
            
            new_market_data_count = len(strategy_stats.market_data_dict['timestamp'])
            log.info(f"[DEBUG][OBSERVER_LEAD] Market data updated via StrategyStats object - entries: {new_market_data_count}")
            
            # Log the actual market data that was added
            log.info(f"[DEBUG][OBSERVER_LEAD] Added market data entry:")
            log.info(f"  timestamp: {timestamp}")
            log.info(f"  trade_id: {strategy_stats.aux_dict['trade_id']}")
            log.info(f"  trd_price: {trade_price}")
            log.info(f"  b_price: {local_buy}")
            log.info(f"  a_price: {local_sell}")
            
            # Prepare data dictionary for observation
            log.info(f"[DEBUG][OBSERVER_LEAD] Preparing data dict for observation")
            data_dict = self.prepare_data_dict(localview, strategy_stats)
            
            # Check all observation conditions
            log.info(f"[DEBUG][OBSERVER_LEAD] Checking observation conditions")
            conditions = self.check_all_conditions(strategy_stats, localview, timestamp, data_dict)
            log.info(f"[DEBUG][OBSERVER_LEAD] Observation conditions: {conditions}")
    
            
            # Update processed trade tracking
            if conditions['has_trade_data'] and conditions['trade_not_processed']:
                self.processed_trade_id = strategy_stats.aux_dict['trade_id']
                self.processed_trade_ts = strategy_stats.aux_dict['timestamp']
            
            # Observer collects predictor data for ALL trades (not conditional on observation)
            trade_id = strategy_stats.aux_dict['trade_id']
            log.info(f"[DEBUG][OBSERVER_LEAD] COLLECTING PREDICTORS - Processing trade {trade_id}")

            if data_dict:
                log.info(f"[DEBUG][OBSERVER_LEAD] Adding predictor data via StrategyStats object")
                strategy_stats.predictor_dict['timestamp'].append(timestamp)
                strategy_stats.predictor_dict['trade_id'].append(trade_id)
                strategy_stats.predictor_dict['predictors'].append(data_dict)
                
                new_predictor_count = len(strategy_stats.predictor_dict['timestamp'])
                log.info(f"[DEBUG][OBSERVER_LEAD] Predictor data updated via StrategyStats object - entries: {new_predictor_count}")
                
                # Log comprehensive analysis
                log.info(f"[OBSERVER_COMPREHENSIVE] Trade {trade_id}:")
                log.info(f"  Trade Price: {data_dict.get('trd_price', 'N/A')}")
                log.info(f"  Bid/Ask: {data_dict.get('b_price', 'N/A')}/{data_dict.get('a_price', 'N/A')} (spread: {data_dict.get('ba_spread', 'N/A')})")
                if 'b_price_sparsity' in data_dict and 'a_price_sparsity' in data_dict:
                    log.info(f"  Sparsity: Bid={data_dict['b_price_sparsity']}, Ask={data_dict['a_price_sparsity']}")
                if conditions:
                    log.info(f"  Conditions: LONG={conditions.get('long_conditions', False)}, SHORT={conditions.get('short_conditions', False)}")
            else:
                log.error(f"[DEBUG][OBSERVER_LEAD] data_dict is None - prepare_data_dict failed!")
            
            # Still do observation analysis for completeness (but predictor collection is independent)
            if conditions and conditions['can_observe']:
                log.info(f"[DEBUG][OBSERVER_LEAD] CAN OBSERVE - Trade {trade_id} meets observation conditions")
            else:
                log.info(f"[DEBUG][OBSERVER_LEAD] CANNOT OBSERVE - Trade {trade_id} doesn't meet observation conditions")
            

            # Return empty - observer doesn't create trading slots
            return {}
            
        except Exception as e:
            log.error(f"[DEBUG][OBSERVER_LEAD] Exception in act: {e}, line: {e.__traceback__.tb_lineno}")
            import traceback
            traceback.print_exc()
            return {}

    def remove_slot_info(self, reason):
        """Observer doesn't create slots, so just log and return empty"""
        log.info(f"[OBSERVER_LEAD] {reason}")
        return {}