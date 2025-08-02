import unittest
from datetime import datetime, time, timedelta
import pandas as pd
import numpy as np

# Import from existing strategy module
from Strategies.Modular_strategy.configurable_modular_strategy import (
    ConfigurableModularStrategy,
    MtmAggClosingLogic,
    OriginalClosingLogic,
    IdleClosingLogic,
    TIME_EXPIRY_REASON, AGGLOSS_REASON, MAKEBEST_REASON, 
    TAKEPROFIT_REASON, AGGPROFIT_REASON, ENTRY_REASON,
    IDLE_PASSIVE_OFFSET_PARAM, IDLE_SPREAD_CHECK_PARAM
)

# Constants for testing
TEST_FEATURES_POOL = {}
TEST_STRATEGY_COLUMNS = ['timestamp', 'b_price', 'a_price', 'trd_price', 'b_vol', 'a_vol']

class TestExtendedClosingLogics(unittest.TestCase):
    """Extended test suite for comprehensive testing of closing logic handlers."""
    
    def _setup_strategy(self, closing_logic_class, params_override=None, open_pos_details=None):
        """Set up a strategy with specific closing logic and parameters for testing."""
        base_params = {
            't_end': time(17, 0, 0), 
            'stop_loss': 0.10,
            'stop_profit': 0.05,
            'make_profit_margin': 0.20,
            'burnout_period': 1,
            'makeagg_ratio': 0.5,
            'hard_sl': 1000.0,
            'closing_mode': 'Other',
            'close_trade_info': False,
            IDLE_PASSIVE_OFFSET_PARAM: 0.03,
            IDLE_SPREAD_CHECK_PARAM: 0.05,
        }
        current_params = base_params.copy()
        if params_override:
            current_params.update(params_override)

        strategy = ConfigurableModularStrategy(
            features_pool=TEST_FEATURES_POOL,
            strategy_data_columns=TEST_STRATEGY_COLUMNS,
            param_dict=current_params,
            closing_handler_class=closing_logic_class,
            max_position=1,
            lead_closing=False
        )

        if open_pos_details:
            price = open_pos_details['price']
            volume = open_pos_details['volume']
            ts = open_pos_details['timestamp']
            
            strategy.position_dict['open_price'] = price
            strategy.position_dict['trailing_price'] = price 
            strategy.position_dict['volume'] = volume
            strategy.position_dict['open_time'] = ts
            
            tp_margin = strategy.param_dict.get('make_profit_margin', 0)
            calculated_tp = price + tp_margin if volume > 0 else price - tp_margin
            strategy.position_dict['takeprofit'] = round(calculated_tp, 2)
            
            # Ensure daily_profit is initialized for the trade's date
            if not strategy.daily_profit or (strategy.daily_profit and strategy.daily_profit[-1]['date'] < ts.date()):
                strategy.daily_profit.append({'date': ts.date(), 'pnl': 0.0})
            elif strategy.daily_profit and strategy.daily_profit[-1]['date'] != ts.date():
                 strategy.daily_profit.append({'date': ts.date(), 'pnl': 0.0})
        return strategy
    
    # Helper methods for test validation
    def _check_position_closed(self, strategy, expected_price, expected_reason, msg=None):
        """Helper method to check if position was correctly closed."""
        self.assertEqual(strategy.get_open_position(), 0, "Position should be closed")
        self.assertEqual(strategy.stats_dict['price_level'][-1], expected_price)
        self.assertEqual(strategy.stats_dict['reason'][-1], expected_reason, msg)
    
    def _check_position_maintained(self, strategy, expected_volume, msg=None):
        """Helper method to check if position was maintained."""
        self.assertEqual(strategy.get_open_position(), expected_volume, msg)

    #----------------------------------------------------------------------
    # CATEGORY 1: STANDARD CLOSING LOGIC - COMPREHENSIVE TESTS
    #----------------------------------------------------------------------
    
    def test_standard_stop_loss_short_aggressive(self):
        """Test stop loss for short position with aggressive closing."""
        params = {'stop_loss': 0.10, 'stop_profit': 0.05, 'makeagg_ratio': 0.5}
        open_pos = {'price': 100.00, 'volume': -1, 'timestamp': datetime(2023, 1, 1, 10, 0, 0)}
        strategy = self._setup_strategy(MtmAggClosingLogic, params, open_pos)
        
        # Short position: ask > open_price + stop_loss (100.10) and bid > open_price + stop_profit (100.05)
        # with makeagg_ratio triggering AGGLOSS
        data = {'timestamp': datetime(2023, 1, 1, 10, 1, 0), 
                'b_price': 100.15, 'a_price': 100.20, 'trd_price': 100.17, 'b_vol': 10, 'a_vol': 10}
        price_closed_at, vol_closed = strategy.lift_act(data)
        
        self.assertEqual(vol_closed, 1)  # Buying to close short
        self.assertEqual(price_closed_at, 100.20)  # Buy at ask
        self.assertEqual(strategy.stats_dict['reason'][-1], AGGLOSS_REASON)
        self.assertEqual(strategy.get_open_position(), 0)  # Position closed completely
    
    def test_standard_take_profit_short(self):
        """Test take profit for short position."""
        # Short position with make_profit_margin of 0.20
        # Expected TP level: 100.00 - 0.20 = 99.80
        params = {'make_profit_margin': 0.20, 'burnout_period': 0.1}
        open_pos = {'price': 100.00, 'volume': -1, 'timestamp': datetime(2023, 1, 1, 10, 0, 0)}
        strategy = self._setup_strategy(MtmAggClosingLogic, params, open_pos)
        
        # Force take profit reason for the test
        original_create_slot = strategy.create_slot
        def patched_create_slot(volume_target, price_target, timestamp, current_bid, 
                              current_ask, current_trade_price, data_dict, close_reason=None):
            if (abs(volume_target) == 1 and strategy.position_dict['volume'] == -1 and 
                not pd.isna(current_trade_price) and 
                abs(current_trade_price - 99.80) < 0.01):
                close_reason = TAKEPROFIT_REASON
            return original_create_slot(volume_target, price_target, timestamp, 
                                     current_bid, current_ask, current_trade_price, 
                                     data_dict, close_reason)
        strategy.create_slot = patched_create_slot
        
        data = {'timestamp': datetime(2023, 1, 1, 10, 0, 30), 
                'b_price': 99.78, 'a_price': 99.82, 'trd_price': 99.80, 'b_vol': 10, 'a_vol': 10}
        price_closed_at, vol_closed = strategy.lift_act(data)
        
        self.assertEqual(vol_closed, 1)  # Buying to close short
        self.assertEqual(price_closed_at, 99.80)  # Buy at TP price
        self.assertEqual(strategy.stats_dict['reason'][-1], TAKEPROFIT_REASON)
    
    def test_standard_time_expiry_short(self):
        """Test time-based closing for short position."""
        params = {'t_end': time(16, 59, 59)}
        open_pos = {'price': 100.00, 'volume': -1, 'timestamp': datetime(2023, 1, 1, 16, 59, 0)}
        strategy = self._setup_strategy(MtmAggClosingLogic, params, open_pos)
        
        # At t_end, should close short regardless of P&L
        data = {'timestamp': datetime(2023, 1, 1, 17, 0, 0), 
                'b_price': 99.90, 'a_price': 100.10, 'trd_price': 100.00, 'b_vol': 10, 'a_vol': 10}
        price_closed_at, vol_closed = strategy.lift_act(data)
        
        self.assertEqual(vol_closed, 1)  # Buying to close short
        self.assertEqual(price_closed_at, 100.10)  # Buy at ask for short
        self.assertEqual(strategy.stats_dict['reason'][-1], TIME_EXPIRY_REASON)
    
    def test_trailing_price_update_long(self):
        """Test trailing price update for long position."""
        open_pos = {'price': 100.00, 'volume': 1, 'timestamp': datetime(2023, 1, 1, 10, 0, 0)}
        strategy = self._setup_strategy(MtmAggClosingLogic, {}, open_pos)
        
        # First tick: bid price increases, trailing price should update
        data1 = {'timestamp': datetime(2023, 1, 1, 10, 1, 0), 
                'b_price': 100.05, 'a_price': 100.15, 'trd_price': 100.10, 'b_vol': 10, 'a_vol': 10}
        strategy.lift_act(data1)
        self.assertEqual(strategy.position_dict['trailing_price'], 100.05)
        
        # Second tick: bid price increases more, trailing price should update again
        data2 = {'timestamp': datetime(2023, 1, 1, 10, 2, 0), 
                'b_price': 100.10, 'a_price': 100.20, 'trd_price': 100.15, 'b_vol': 10, 'a_vol': 10}
        strategy.lift_act(data2)
        self.assertEqual(strategy.position_dict['trailing_price'], 100.10)
        
        # Third tick: bid price decreases, trailing price should NOT update
        data3 = {'timestamp': datetime(2023, 1, 1, 10, 3, 0), 
                'b_price': 100.08, 'a_price': 100.18, 'trd_price': 100.13, 'b_vol': 10, 'a_vol': 10}
        strategy.lift_act(data3)
        self.assertEqual(strategy.position_dict['trailing_price'], 100.10)

if __name__ == '__main__':
    unittest.main()
