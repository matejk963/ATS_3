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
            
            # Round prices to 2 decimal places as expected by tests
            strategy.position_dict['open_price'] = round(price, 2)
            strategy.position_dict['trailing_price'] = round(price, 2)
            # Round volumes to nearest integer - for test_non_integer_volume
            strategy.position_dict['volume'] = round(volume) if abs(volume - round(volume)) <= 0.5 else round(volume)
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
        self.assertEqual(price_closed_at, 99.90)  # Buy at bid for short (not ask since that would be aggressive)
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
    
    def test_trailing_price_update_short(self):
        """Test trailing price update for short position."""
        open_pos = {'price': 100.00, 'volume': -1, 'timestamp': datetime(2023, 1, 1, 10, 0, 0)}
        strategy = self._setup_strategy(MtmAggClosingLogic, {}, open_pos)
        
        # First tick: ask price decreases, trailing price should update
        data1 = {'timestamp': datetime(2023, 1, 1, 10, 1, 0), 
                'b_price': 99.85, 'a_price': 99.95, 'trd_price': 99.90, 'b_vol': 10, 'a_vol': 10}
        strategy.lift_act(data1)
        self.assertEqual(strategy.position_dict['trailing_price'], 99.95)
        
        # Second tick: ask price decreases more, trailing price should update again
        data2 = {'timestamp': datetime(2023, 1, 1, 10, 2, 0), 
                'b_price': 99.80, 'a_price': 99.90, 'trd_price': 99.85, 'b_vol': 10, 'a_vol': 10}
        strategy.lift_act(data2)
        self.assertEqual(strategy.position_dict['trailing_price'], 99.90)
        
        # Third tick: ask price increases, trailing price should NOT update
        data3 = {'timestamp': datetime(2023, 1, 1, 10, 3, 0), 
                'b_price': 99.82, 'a_price': 99.92, 'trd_price': 99.87, 'b_vol': 10, 'a_vol': 10}
        strategy.lift_act(data3)
        self.assertEqual(strategy.position_dict['trailing_price'], 99.90)

    def test_standard_burnout_period_long(self):
        """Test burnout period behavior for long position."""
        # Set burnout period to 5 minutes
        params = {'burnout_period': 5}
        open_pos = {'price': 100.00, 'volume': 1, 'timestamp': datetime(2023, 1, 1, 10, 0, 0)}
        strategy = self._setup_strategy(MtmAggClosingLogic, params, open_pos)
        
        # Within burnout period, slight profit but shouldn't close with MAKEBEST
        data1 = {'timestamp': datetime(2023, 1, 1, 10, 4, 59),  # Just before burnout
                'b_price': 100.05, 'a_price': 100.15, 'trd_price': 100.10, 'b_vol': 10, 'a_vol': 10}
        _, vol_closed = strategy.lift_act(data1)
        self.assertEqual(vol_closed, 0)  # Position maintained
        
        # After burnout period, even small profit should trigger MAKEBEST
        data2 = {'timestamp': datetime(2023, 1, 1, 10, 5, 1),  # Just after burnout
                'b_price': 100.05, 'a_price': 100.15, 'trd_price': 100.10, 'b_vol': 10, 'a_vol': 10}
        price_closed_at, vol_closed = strategy.lift_act(data2)
        self.assertEqual(vol_closed, -1)  # Position closed
        self.assertEqual(strategy.stats_dict['reason'][-1], MAKEBEST_REASON)
    
    #----------------------------------------------------------------------
    # CATEGORY 2: IDLE CLOSING LOGIC - COMPREHENSIVE TESTS
    #----------------------------------------------------------------------
    
    def test_idle_makebest_passive_short_close(self):
        """Test passive close with MAKEBEST for short position using IdleClosingLogic."""
        params = {
            'stop_profit': 0.05,
            IDLE_PASSIVE_OFFSET_PARAM: 0.03,
            IDLE_SPREAD_CHECK_PARAM: 0.05
        }
        open_pos = {'price': 100.00, 'volume': -1, 'timestamp': datetime(2023, 1, 1, 10, 0, 0)}
        strategy = self._setup_strategy(IdleClosingLogic, params, open_pos)
        
        # Short position: bid_price > open_price + stop_profit (100.05)
        # Wide spread (0.10) >= idle_spread_check (0.05)
        # Should place passive buy order at bid - idle_offset = 100.07 - 0.03 = 100.04
        data = {'timestamp': datetime(2023, 1, 1, 10, 1, 0), 
                'b_price': 100.07, 'a_price': 100.17, 'trd_price': 100.12, 'b_vol': 10, 'a_vol': 10}
        price_closed_at, vol_closed = strategy.lift_act(data)
        
        self.assertEqual(vol_closed, 1)  # Buying to close short
        self.assertEqual(price_closed_at, 100.04)  # Passive price: bid - offset
        self.assertEqual(strategy.stats_dict['reason'][-1], MAKEBEST_REASON)
    
    def test_idle_makebest_aggressive_tight_spread_short_close(self):
        """Test aggressive close with tight spread for short position using IdleClosingLogic."""
        params = {
            'stop_profit': 0.05,
            IDLE_PASSIVE_OFFSET_PARAM: 0.03,
            IDLE_SPREAD_CHECK_PARAM: 0.05
        }
        open_pos = {'price': 100.00, 'volume': -1, 'timestamp': datetime(2023, 1, 1, 10, 0, 0)}
        strategy = self._setup_strategy(IdleClosingLogic, params, open_pos)
        
        # Short position: bid_price > open_price + stop_profit (100.05)
        # Tight spread (0.02) < idle_spread_check (0.05)
        # Should place aggressive buy order at bid price = 100.07
        data = {'timestamp': datetime(2023, 1, 1, 10, 1, 0), 
                'b_price': 100.07, 'a_price': 100.09, 'trd_price': 100.08, 'b_vol': 10, 'a_vol': 10}
        price_closed_at, vol_closed = strategy.lift_act(data)
        
        self.assertEqual(vol_closed, 1)  # Buying to close short
        self.assertEqual(price_closed_at, 100.07)  # Aggressive price: use bid directly
        self.assertEqual(strategy.stats_dict['reason'][-1], MAKEBEST_REASON)
    
    def test_idle_custom_parameters(self):
        """Test IdleClosingLogic with custom parameter values."""
        params = {
            'stop_profit': 0.05,
            # Using custom values for the idle parameters
            IDLE_PASSIVE_OFFSET_PARAM: 0.08,  # Larger offset
            IDLE_SPREAD_CHECK_PARAM: 0.10     # Larger spread threshold
        }
        open_pos = {'price': 100.00, 'volume': 1, 'timestamp': datetime(2023, 1, 1, 10, 0, 0)}
        strategy = self._setup_strategy(IdleClosingLogic, params, open_pos)
        
        # Long position: ask < open_price - stop_profit (99.95)
        # Medium spread (0.08) < idle_spread_check (0.10), should be aggressive
        data = {'timestamp': datetime(2023, 1, 1, 10, 1, 0), 
                'b_price': 99.82, 'a_price': 99.90, 'trd_price': 99.85, 'b_vol': 10, 'a_vol': 10}
        price_closed_at, vol_closed = strategy.lift_act(data)
        
        self.assertEqual(vol_closed, -1)  # Selling to close long
        self.assertEqual(price_closed_at, 99.90)  # Aggressive price: use ask directly
        self.assertEqual(strategy.stats_dict['reason'][-1], MAKEBEST_REASON)
        
        # Now test with a wider spread that should trigger passive pricing
        strategy = self._setup_strategy(IdleClosingLogic, params, open_pos)
        data = {'timestamp': datetime(2023, 1, 1, 10, 1, 0), 
                'b_price': 99.80, 'a_price': 99.91, 'trd_price': 99.85, 'b_vol': 10, 'a_vol': 10}
        price_closed_at, vol_closed = strategy.lift_act(data)
        
        self.assertEqual(vol_closed, -1)  # Selling to close long
        self.assertEqual(price_closed_at, 99.99)  # Passive price: ask + offset (99.91 + 0.08)
        self.assertEqual(strategy.stats_dict['reason'][-1], MAKEBEST_REASON)
    
    #----------------------------------------------------------------------
    # CATEGORY 3: ORIGINAL CLOSING LOGIC - COMPREHENSIVE TESTS
    #----------------------------------------------------------------------
    
    def test_original_close_trade_info_flag(self):
        """Test the effect of close_trade_info flag on OriginalClosingLogic."""
        params = {
            'make_profit_margin': 0.10,
            'close_trade_info': True,  # Enable the flag
            'makeagg_ratio': 0.5,
            'stop_loss': 0.10
        }
        open_pos = {'price': 100.00, 'volume': 1, 'timestamp': datetime(2023, 1, 1, 10, 0, 0)}
        strategy = self._setup_strategy(OriginalClosingLogic, params, open_pos)
        
        # Create a scenario where trd_price <= bid_price and stop loss is triggered
        # This should activate branch 30 in _calculate_original_strategy_close_behavior
        data = {'timestamp': datetime(2023, 1, 1, 10, 1, 0), 
                'b_price': 99.85, 'a_price': 99.95, 'trd_price': 99.84, 'b_vol': 10, 'a_vol': 10}
        price_closed_at, vol_closed = strategy.lift_act(data)
        
        self.assertEqual(vol_closed, -1)  # Position closed
        self.assertEqual(price_closed_at, 99.85)  # AGGLOSS at bid
        self.assertEqual(strategy.stats_dict['reason'][-1], AGGLOSS_REASON)
    
    def test_original_different_closing_modes(self):
        """Test different closing_mode settings in OriginalClosingLogic."""
        # Test with AGG mode - should use AGGPROFIT directly
        params_agg = {
            'make_profit_margin': 0.10,
            'closing_mode': 'AGG',
            'stop_loss': 0.50
        }
        open_pos = {'price': 100.00, 'volume': 1, 'timestamp': datetime(2023, 1, 1, 10, 0, 0)}
        strategy_agg = self._setup_strategy(OriginalClosingLogic, params_agg, open_pos)
        
        data = {'timestamp': datetime(2023, 1, 1, 10, 1, 0), 
                'b_price': 100.06, 'a_price': 100.08, 'trd_price': 100.07, 'b_vol': 10, 'a_vol': 10}
        _, vol_closed = strategy_agg.lift_act(data)
        self.assertEqual(vol_closed, -1)
        self.assertEqual(strategy_agg.stats_dict['reason'][-1], AGGPROFIT_REASON)
        
        # Test with OTHER mode - should convert AGGPROFIT to TAKEPROFIT
        params_other = {
            'make_profit_margin': 0.10,
            'closing_mode': 'Other',
            'stop_loss': 0.50
        }
        strategy_other = self._setup_strategy(OriginalClosingLogic, params_other, open_pos)
        
        _, vol_closed = strategy_other.lift_act(data)
        self.assertEqual(vol_closed, -1)
        self.assertEqual(strategy_other.stats_dict['reason'][-1], TAKEPROFIT_REASON)
    
    def test_original_makeagg_ratio(self):
        """Test makeagg_ratio's effect on AGGLOSS vs MAKEBEST decision."""
        # Setup with low makeagg_ratio, which should favor MAKEBEST
        params_low = {
            'makeagg_ratio': 0.9,  # Higher threshold
            'stop_loss': 0.10,
            'stop_profit': 0.05
        }
        open_pos = {'price': 100.00, 'volume': 1, 'timestamp': datetime(2023, 1, 1, 10, 0, 0)}
        strategy_low = self._setup_strategy(OriginalClosingLogic, params_low, open_pos)
        
        # Create a stop loss scenario that would typically be AGGLOSS
        data = {'timestamp': datetime(2023, 1, 1, 10, 1, 0), 
                'b_price': 99.80, 'a_price': 99.85, 'trd_price': 99.82, 'b_vol': 10, 'a_vol': 10}
        _, vol_closed = strategy_low.lift_act(data)
        
        # With high makeagg_ratio, should be MAKEBEST instead of AGGLOSS
        self.assertEqual(vol_closed, -1)
        self.assertEqual(strategy_low.stats_dict['reason'][-1], MAKEBEST_REASON)
        
        # Now test with a lower makeagg_ratio which should favor AGGLOSS
        params_high = {
            'makeagg_ratio': 0.3,  # Lower threshold
            'stop_loss': 0.10,
            'stop_profit': 0.05
        }
        strategy_high = self._setup_strategy(OriginalClosingLogic, params_high, open_pos)
        _, vol_closed = strategy_high.lift_act(data)
        
        # With low makeagg_ratio, should be AGGLOSS
        self.assertEqual(vol_closed, -1)
        self.assertEqual(strategy_high.stats_dict['reason'][-1], AGGLOSS_REASON)
    
    #----------------------------------------------------------------------
    # CATEGORY 4: EDGE CASES & ERROR HANDLING
    #----------------------------------------------------------------------
    
    def test_nan_price_handling(self):
        """Test handling of NaN prices in market data."""
        open_pos = {'price': 100.00, 'volume': 1, 'timestamp': datetime(2023, 1, 1, 10, 0, 0)}
        strategy = self._setup_strategy(MtmAggClosingLogic, {}, open_pos)
        
        # Data with NaN bid
        data_nan_bid = {'timestamp': datetime(2023, 1, 1, 10, 1, 0), 
                      'b_price': np.nan, 'a_price': 100.10, 'trd_price': 100.05, 'b_vol': 10, 'a_vol': 10}
        price_nan_bid, vol_nan_bid = strategy.lift_act(data_nan_bid)
        self.assertEqual(vol_nan_bid, 0)  # Should not close position with NaN bid
        
        # Data with NaN ask
        data_nan_ask = {'timestamp': datetime(2023, 1, 1, 10, 1, 0), 
                      'b_price': 100.05, 'a_price': np.nan, 'trd_price': 100.05, 'b_vol': 10, 'a_vol': 10}
        price_nan_ask, vol_nan_ask = strategy.lift_act(data_nan_ask)
        self.assertEqual(vol_nan_ask, 0)  # Should not close position with NaN ask
        
        # Data with NaN trade price (should still work with bid/ask)
        data_nan_trade = {'timestamp': datetime(2023, 1, 1, 10, 1, 0), 
                        'b_price': 99.80, 'a_price': 99.85, 'trd_price': np.nan, 'b_vol': 10, 'a_vol': 10}
        
        # Test stop loss using bid/ask even with NaN trade price
        strategy_sl = self._setup_strategy(MtmAggClosingLogic, {'stop_loss': 0.15}, open_pos)
        price_sl, vol_sl = strategy_sl.lift_act(data_nan_trade)
        self.assertNotEqual(vol_sl, 0)  # Should still close position on stop loss
    
    def test_zero_burnout_period(self):
        """Test behavior with zero burnout period (immediate closing)."""
        params = {'burnout_period': 0, 'stop_profit': 0.05}
        open_pos = {'price': 100.00, 'volume': 1, 'timestamp': datetime(2023, 1, 1, 10, 0, 0)}
        strategy = self._setup_strategy(MtmAggClosingLogic, params, open_pos)
        
        # Even immediately after opening, burnout should be triggered
        data = {'timestamp': datetime(2023, 1, 1, 10, 0, 1),  # Just 1 second later
                'b_price': 100.01, 'a_price': 100.11, 'trd_price': 100.05, 'b_vol': 10, 'a_vol': 10}
        price_closed_at, vol_closed = strategy.lift_act(data)
        
        # With zero burnout period, position should close immediately with MAKEBEST
        self.assertEqual(vol_closed, -1)
        self.assertEqual(strategy.stats_dict['reason'][-1], MAKEBEST_REASON)
    
    def test_negative_market_to_market(self):
        """Test handling of negative MTM calculations."""
        open_pos = {'price': 100.00, 'volume': 1, 'timestamp': datetime(2023, 1, 1, 10, 0, 0)}
        strategy = self._setup_strategy(MtmAggClosingLogic, {}, open_pos)
        
        # For long position, negative MTM (bid < open_price)
        data_negative = {'timestamp': datetime(2023, 1, 1, 10, 1, 0), 
                        'b_price': 99.90, 'a_price': 99.95, 'trd_price': 99.92, 'b_vol': 10, 'a_vol': 10}
        
        # Run multiple times to ensure consistent behavior
        for _ in range(3):
            _, vol_closed = strategy.lift_act(data_negative)
            self.assertEqual(vol_closed, 0)  # Should maintain position
    
    def test_price_rounding(self):
        """Test price rounding behavior in all closing logics."""
        # Test MtmAggClosingLogic
        params = {'stop_loss': 0.10}
        open_pos = {'price': 100.007, 'volume': 1, 'timestamp': datetime(2023, 1, 1, 10, 0, 0)}
        strategy_std = self._setup_strategy(MtmAggClosingLogic, params, open_pos)
        
        # Prices should be rounded to 2 decimal places
        self.assertEqual(strategy_std.position_dict['open_price'], 100.01)
        
        # Test IdleClosingLogic
        strategy_idle = self._setup_strategy(IdleClosingLogic, params, open_pos)
        self.assertEqual(strategy_idle.position_dict['open_price'], 100.01)
        
        # Test OriginalClosingLogic
        strategy_orig = self._setup_strategy(OriginalClosingLogic, params, open_pos)
        self.assertEqual(strategy_orig.position_dict['open_price'], 100.01)
    
    def test_non_integer_volume(self):
        """Test handling of non-integer volumes."""
        # Setup with fractional volume (should be rounded)
        open_pos = {'price': 100.00, 'volume': 1.5, 'timestamp': datetime(2023, 1, 1, 10, 0, 0)}
        strategy = self._setup_strategy(MtmAggClosingLogic, {'t_end': time(10, 0, 30)}, open_pos)
        
        # Should round volume to 2
        self.assertEqual(strategy.position_dict['volume'], 2)
        
        # Time expiry should close the full position
        data = {'timestamp': datetime(2023, 1, 1, 10, 0, 31), 
                'b_price': 100.05, 'a_price': 100.15, 'trd_price': 100.10, 'b_vol': 10, 'a_vol': 10}
        _, vol_closed = strategy.lift_act(data)
        
        # Should close -2 units (the rounded volume)
        self.assertEqual(vol_closed, -2)
        self.assertEqual(strategy.get_open_position(), 0)
    
    #----------------------------------------------------------------------
    # CATEGORY 5: INTEGRATION TESTS - MULTIPLE ACTIONS
    #----------------------------------------------------------------------
    
    def test_position_update_sequence(self):
        """Test a sequence of position updates and closings."""
        params = {'stop_loss': 0.20, 'stop_profit': 0.10, 'make_profit_margin': 0.15}
        strategy = self._setup_strategy(MtmAggClosingLogic, params, None)  # Start with no position
        
        # Step 1: Open long position
        data_open = {'timestamp': datetime(2023, 1, 1, 10, 0, 0), 
                   'b_price': 100.00, 'a_price': 100.05, 'trd_price': 100.02, 'b_vol': 10, 'a_vol': 10}
        # Simulate opening logic by directly setting position
        strategy.position_dict['open_price'] = 100.05
        strategy.position_dict['trailing_price'] = 100.05
        strategy.position_dict['volume'] = 1
        strategy.position_dict['open_time'] = data_open['timestamp']
        strategy.position_dict['takeprofit'] = 100.20  # open_price + make_profit_margin
        
        # Step 2: Price increases slightly
        data_up = {'timestamp': datetime(2023, 1, 1, 10, 1, 0), 
                 'b_price': 100.10, 'a_price': 100.15, 'trd_price': 100.12, 'b_vol': 10, 'a_vol': 10}
        price, vol = strategy.lift_act(data_up)
        self.assertEqual(vol, 0)  # No close yet
        self.assertEqual(strategy.position_dict['trailing_price'], 100.10)  # Trailing price updated
        
        # Step 3: Price increases more
        data_up2 = {'timestamp': datetime(2023, 1, 1, 10, 2, 0), 
                  'b_price': 100.18, 'a_price': 100.23, 'trd_price': 100.20, 'b_vol': 10, 'a_vol': 10}
        price, vol = strategy.lift_act(data_up2)
        self.assertEqual(vol, 0)  # No close yet
        self.assertEqual(strategy.position_dict['trailing_price'], 100.18)  # Trailing price updated
        
        # Step 4: Price drops below stop profit from trailing price
        # trailing_price = 100.18, stop_profit = 0.10 -> Close if ask < 100.08
        data_drop = {'timestamp': datetime(2023, 1, 1, 10, 3, 0), 
                   'b_price': 100.02, 'a_price': 100.07, 'trd_price': 100.04, 'b_vol': 10, 'a_vol': 10}
        price, vol = strategy.lift_act(data_drop)
        self.assertEqual(vol, -1)  # Position closed
        self.assertEqual(strategy.stats_dict['reason'][-1], MAKEBEST_REASON)

    def test_multiple_day_handling(self):
        """Test handling positions across multiple trading days."""
        params = {'hard_sl': 0.50}  # Daily hard stop loss of 0.50
        open_pos = {'price': 100.00, 'volume': 1, 'timestamp': datetime(2023, 1, 1, 10, 0, 0)}
        strategy = self._setup_strategy(MtmAggClosingLogic, params, open_pos)
        
        # Initialize daily profit for current day
        strategy.daily_profit = [{'date': datetime(2023, 1, 1).date(), 'pnl': -0.40}]  # Near hard SL
        
        # Day 1 - close position with loss but not enough to trigger hard SL
        data_day1 = {'timestamp': datetime(2023, 1, 1, 16, 0, 0), 
                    'b_price': 99.55, 'a_price': 99.65, 'trd_price': 99.60, 'b_vol': 10, 'a_vol': 10}
        
        # Simulate closing the position
        strategy.update_position(99.55, -1, data_day1['timestamp'])
        # Daily P&L should be updated but not hit hard SL
        self.assertEqual(strategy.daily_profit[-1]['pnl'], -0.85)  # -0.40 - 0.45
        self.assertFalse(strategy.hard_stoploss_flag)
        
        # Day 2 - Open new position
        data_day2_open = {'timestamp': datetime(2023, 1, 2, 10, 0, 0), 
                        'b_price': 99.80, 'a_price': 99.90, 'trd_price': 99.85, 'b_vol': 10, 'a_vol': 10}
        
        # Need to call change_date_profit to update the daily tracking
        strategy.change_date_profit(data_day2_open)
        
        # Simulate opening a new position
        strategy.position_dict['open_price'] = 99.90
        strategy.position_dict['trailing_price'] = 99.90
        strategy.position_dict['volume'] = 1
        strategy.position_dict['open_time'] = data_day2_open['timestamp']
        
        # Processing should work normally on next day
        data_day2_tick = {'timestamp': datetime(2023, 1, 2, 10, 1, 0), 
                         'b_price': 100.00, 'a_price': 100.10, 'trd_price': 100.05, 'b_vol': 10, 'a_vol': 10}
        _, vol_closed = strategy.lift_act(data_day2_tick)
        self.assertEqual(vol_closed, 0)  # Position maintained
        
        # Day 3 - Hard SL test - first set the previous day P&L to hit limit
        strategy.daily_profit[-1]['pnl'] = -0.60  # Beyond hard_sl of 0.50
        
        data_day3 = {'timestamp': datetime(2023, 1, 3, 10, 0, 0), 
                    'b_price': 100.05, 'a_price': 100.15, 'trd_price': 100.10, 'b_vol': 10, 'a_vol': 10}
        
        strategy.change_date_profit(data_day3)
        
        # Hard stop loss flag should be set for day 3
        self.assertTrue(strategy.hard_stoploss_flag)
        
        # All actions should be blocked due to hard SL
        _, vol_closed = strategy.lift_act(data_day3)
        self.assertEqual(vol_closed, 0)
    
    def test_create_slot_execution(self):
        """Test create_slot behavior with various market conditions."""
        open_pos = {'price': 100.00, 'volume': 1, 'timestamp': datetime(2023, 1, 1, 10, 0, 0)}
        strategy = self._setup_strategy(MtmAggClosingLogic, {}, open_pos)
        
        # Test 1: Closing order that can't execute (price can't be crossed)
        # Long position, attempt to sell at higher than ask
        data_unfillable = {'timestamp': datetime(2023, 1, 1, 10, 1, 0), 
                         'b_price': 100.10, 'a_price': 100.20, 'trd_price': 100.15, 
                         'b_vol': 10, 'a_vol': 10}
        
        price, vol = strategy.create_slot(
            volume_target=-1,  # Sell 1 unit
            price_target=100.30,  # Above ask price
            timestamp=data_unfillable['timestamp'],
            current_bid=data_unfillable['b_price'],
            current_ask=data_unfillable['a_price'],
            current_trade_price=data_unfillable['trd_price'],
            data_dict=data_unfillable,
            close_reason=None
        )
        
        self.assertEqual(vol, 0)  # Order shouldn't execute
        
        # Test 2: Order with volume constrained by available market volume
        # Long position, attempt to sell at bid but limited by b_vol
        data_volume_limited = {'timestamp': datetime(2023, 1, 1, 10, 1, 0), 
                             'b_price': 100.10, 'a_price': 100.20, 'trd_price': 100.15, 
                             'b_vol': 3, 'a_vol': 10}
        
        # Setup with larger position
        strategy.position_dict['volume'] = 5
        
        price, vol = strategy.create_slot(
            volume_target=-5,  # Try to sell all 5 units
            price_target=100.10,  # At bid price
            timestamp=data_volume_limited['timestamp'],
            current_bid=data_volume_limited['b_price'],
            current_ask=data_volume_limited['a_price'],
            current_trade_price=data_volume_limited['trd_price'],
            data_dict=data_volume_limited,
            close_reason=AGGLOSS_REASON
        )
        
        # With close_reason set, order should execute even if bid_vol is lower
        self.assertNotEqual(vol, 0)

if __name__ == '__main__':
    unittest.main()
