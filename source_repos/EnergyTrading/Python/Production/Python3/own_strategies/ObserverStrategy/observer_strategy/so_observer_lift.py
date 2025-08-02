import logging
import autotrader_lib.common as COMMON
import autotrader_synthetic.config_util as SYNCONF
import autotrader_synthetic.synthetic_orders.synthetic_order_base as SYB
from .strategy_stats import StrategyStats

log = logging.getLogger("observer_strategy.lift_order")
tol = 1e-3

class ObserverLiftOrder(SYB.SyntheticOrderBase):
    broker_list = SYNCONF.ConfigOptionDescriptor(
        "broker_list", list,
        "List of brokers",
        required=True
    )

    lead_instrument_id = SYNCONF.ConfigOptionDescriptor(
        "lead_instrument_id", str,
        "Lead instrument ID",
        required=True
    )

    lead_slot_name = SYNCONF.ConfigOptionDescriptor(
        "lead_slot_name", str,
        "Lead slot name",
        required=True
    )

    lead_product_id = SYNCONF.ConfigOptionDescriptor(
        "lead_product_id", str,
        "Lead product ID",
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


    def check_lift_conditions(self, strategy_stats, localview, timestamp):
        """
        Check conditions for lift order observation
        """
        conditions = {}
        
        # Basic position check
        open_position = strategy_stats.position_dict.get('volume', 0)
        conditions['has_position'] = abs(open_position) > 0.1
        
        # Market data availability
        local_buy = localview.current_front_price(COMMON.Direction.buy)
        local_sell = localview.current_front_price(COMMON.Direction.sell)
        conditions['market_data_available'] = local_buy is not None and local_sell is not None
        
        # Observer lift can observe all position states
        conditions['can_observe_lift'] = True  # Always observe for metrics
        
        log.info(f"[OBSERVER_LIFT_CONDITIONS]: {conditions}")
        return conditions

    def act(self, localview, additional_views, timestamp):
        try:
            # Strategy stats object
            strategy_stats = StrategyStats.from_dict(self.strategy_stats_dict)
            
            # Check lift observation conditions
            conditions = self.check_lift_conditions(strategy_stats, localview, timestamp)
            
            # Log lift observation
            decision_data = {
                'lift_conditions': conditions,
                'position_volume': strategy_stats.position_dict.get('volume', 0),
                'observation_decision': 'lift_observed' if conditions['can_observe_lift'] else 'lift_not_observed',
                'lift_reason': 'observing_position_state'
            }
            
            if conditions['can_observe_lift']:
                log.info(f"[OBSERVER_LIFT] Observing position state: volume={strategy_stats.position_dict.get('volume', 0)}")
                
                # Update position tracking for metrics
                if conditions['market_data_available']:
                    bid_price = localview.current_front_price(COMMON.Direction.buy)
                    ask_price = localview.current_front_price(COMMON.Direction.sell)
                    
                    strategy_stats.param_dict['bid_price'] = bid_price
                    strategy_stats.param_dict['ask_price'] = ask_price
                
                # Return empty - no slot creation
                return {}
            else:
                log.info("[OBSERVER_LIFT] No position to observe")
                return {}
            
        except Exception as e:
            log.error(f"[OBSERVER_LIFT] Exception in act: {e}, line: {e.__traceback__.tb_lineno}")
            return {}

    def remove_slot_info(self, reason):
        """Observer doesn't create slots, so just log and return empty"""
        log.info(f"[OBSERVER_LIFT] {reason}")
        return {}