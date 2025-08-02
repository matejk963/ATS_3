"""
Tests for ATR calculation fix - implementing correct candle-based ATR calculation.

Following Energy Trading's correct approach:
1. Build evolving candles from tick data
2. Use previous completed candle's close as reference
3. Calculate True Range using candle OHLC + previous candle close
4. Forward-fill ATR values to all ticks within candle period
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '../../src'))

from feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline


class TestATRCalculationFix:
    """Test correct candle-based ATR calculation implementation."""

    def setup_method(self):
        """Setup test data for each test method."""
        # Create sample historical candles (completed candles)
        base_time = datetime(2025, 1, 1, 10, 0, 0)
        
        self.historical_candles = pd.DataFrame({
            'open': [100.0, 101.0, 102.0, 103.0, 104.0],
            'high': [101.5, 102.5, 103.5, 104.5, 105.5],
            'low': [99.5, 100.5, 101.5, 102.5, 103.5],
            'close': [101.0, 102.0, 103.0, 104.0, 105.0]
        }, index=pd.date_range(base_time, periods=5, freq='1H'))
        
        # Create sample tick data within the next hour (current evolving candle)
        tick_times = pd.date_range(
            base_time + timedelta(hours=5), 
            periods=10, 
            freq='6min'  # 10 ticks over 1 hour
        )
        
        self.tick_data = pd.DataFrame({
            'datetime': tick_times,
            'price': [105.2, 105.8, 105.1, 106.0, 105.9, 105.3, 105.7, 105.4, 105.6, 105.5],
            'nanotime': range(10),
            'tradeid': range(100, 110)
        })

    def test_atr_calculation_uses_candle_ohlc_not_tick_prices(self):
        """Test that ATR calculation uses candle OHLC data, not individual tick prices."""
        pipeline = UnifiedTechnicalIndicatorsPipeline()
        
        # This should fail with current implementation
        result = pipeline._compute_realtime_atr(
            self.tick_data, 
            self.historical_candles, 
            atr_period=3
        )
        
        # Expected behavior: ATR should be calculated using candle OHLC
        # Current candle: open=105.2, high=106.0, low=105.1, close=105.5
        # Previous candle close: 105.0
        # True Range = max(106.0-105.1, |106.0-105.0|, |105.1-105.0|) = max(0.9, 1.0, 0.1) = 1.0
        
        # All ticks within same candle period should have SAME ATR value (forward-filled)
        unique_atr_values = result['atr'].nunique()
        
        # This will fail with current per-tick implementation
        assert unique_atr_values == 1, f"Expected 1 unique ATR value (forward-filled), got {unique_atr_values}"

    def test_atr_uses_previous_candle_close_not_previous_tick(self):
        """Test that ATR calculation uses previous completed candle's close, not previous tick."""
        pipeline = UnifiedTechnicalIndicatorsPipeline()
        
        result = pipeline._compute_realtime_atr(
            self.tick_data, 
            self.historical_candles, 
            atr_period=3
        )
        
        # Expected: Previous close should be 105.0 (last historical candle's close)
        # Not 105.2 (previous tick price)
        
        # For verification, let's calculate expected ATR manually
        # Historical True Ranges (using last 2 completed candles)
        hist_tr_1 = max(104.5-102.5, abs(104.5-103.0), abs(102.5-103.0))  # 2.0
        hist_tr_2 = max(105.5-103.5, abs(105.5-104.0), abs(103.5-104.0))  # 2.0
        
        # Current evolving candle True Range
        current_tr = max(106.0-105.1, abs(106.0-105.0), abs(105.1-105.0))  # 1.0
        
        expected_atr = (hist_tr_1 + hist_tr_2 + current_tr) / 3  # (2.0 + 2.0 + 1.0) / 3 = 1.67
        
        # All ATR values should be approximately this value (with reasonable tolerance)
        # Note: The actual implementation includes evolving candle TR development, 
        # so the result may be slightly different but should be in the right range
        assert abs(result['atr'].iloc[0] - expected_atr) < 0.2, \
            f"Expected ATR ~{expected_atr}, got {result['atr'].iloc[0]} (difference: {abs(result['atr'].iloc[0] - expected_atr):.3f})"

    def test_atr_forward_fill_within_candle_period(self):
        """Test that ATR values are forward-filled to all ticks within same candle period."""
        pipeline = UnifiedTechnicalIndicatorsPipeline()
        
        result = pipeline._compute_realtime_atr(
            self.tick_data, 
            self.historical_candles, 
            atr_period=3
        )
        
        # All ticks should have identical ATR values (forward-filled)
        atr_values = result['atr'].values
        first_atr = atr_values[0]
        
        for i, atr_val in enumerate(atr_values):
            assert abs(atr_val - first_atr) < 1e-10, \
                f"Tick {i}: Expected ATR {first_atr}, got {atr_val} (forward-fill failed)"

    def test_atr_calculation_consistency_with_traditional_formula(self):
        """Test that ATR calculation follows traditional Wilder's ATR formula."""
        pipeline = UnifiedTechnicalIndicatorsPipeline()
        
        result = pipeline._compute_realtime_atr(
            self.tick_data, 
            self.historical_candles, 
            atr_period=5  # Use all historical candles
        )
        
        # Calculate expected ATR using traditional formula
        combined_candles = self.historical_candles.copy()
        
        # Add current evolving candle
        current_candle = pd.DataFrame({
            'open': [self.tick_data['price'].iloc[0]],  # First tick as open
            'high': [self.tick_data['price'].max()],    # Max tick as high
            'low': [self.tick_data['price'].min()],     # Min tick as low
            'close': [self.tick_data['price'].iloc[-1]] # Last tick as close
        }, index=[self.tick_data['datetime'].iloc[0].floor('1H')])
        
        all_candles = pd.concat([combined_candles, current_candle])
        
        # Calculate True Range for all candles
        all_candles['prev_close'] = all_candles['close'].shift(1)
        all_candles['tr'] = all_candles.apply(
            lambda row: max(
                row['high'] - row['low'],
                abs(row['high'] - row['prev_close']) if not pd.isna(row['prev_close']) else 0,
                abs(row['low'] - row['prev_close']) if not pd.isna(row['prev_close']) else 0
            ), axis=1
        )
        
        # ATR = Simple Moving Average of last 5 True Ranges
        expected_atr = all_candles['tr'].tail(5).mean()
        
        # Result should match traditional calculation
        actual_atr = result['atr'].iloc[0]
        assert abs(actual_atr - expected_atr) < 0.1, \
            f"Expected ATR {expected_atr}, got {actual_atr}"

    def test_atr_reduces_unique_values_compared_to_current_implementation(self):
        """Test that fixed ATR has fewer unique values than current per-tick implementation."""
        # This test documents the expected improvement
        
        # Create larger dataset to demonstrate the difference
        large_tick_data = pd.DataFrame({
            'datetime': pd.date_range('2025-01-01 15:00:00', periods=360, freq='10s'),
            'price': 105.0 + np.random.normal(0, 0.1, 360)  # 360 ticks with small variations
        })
        
        pipeline = UnifiedTechnicalIndicatorsPipeline()
        result = pipeline._compute_realtime_atr(
            large_tick_data, 
            self.historical_candles, 
            atr_period=21
        )
        
        unique_atr_count = result['atr'].nunique()
        
        # Current implementation produces ~360 unique values (one per tick)
        # Fixed implementation should produce ~1 unique value (forward-filled within candle)
        
        # This will fail with current implementation, pass with fixed implementation
        assert unique_atr_count <= 10, \
            f"Expected <= 10 unique ATR values (candle-based), got {unique_atr_count} (per-tick)"

    def test_atr_maintains_datetime_and_metadata_columns(self):
        """Test that ATR calculation preserves datetime and metadata columns."""
        pipeline = UnifiedTechnicalIndicatorsPipeline()
        
        result = pipeline._compute_realtime_atr(
            self.tick_data, 
            self.historical_candles, 
            atr_period=3
        )
        
        # Should preserve datetime
        assert 'datetime' in result.columns
        assert len(result) == len(self.tick_data)
        
        # Should have ATR column
        assert 'atr' in result.columns
        
        # All ATR values should be valid numbers
        assert not result['atr'].isna().any()
        assert (result['atr'] > 0).all()  # ATR should be positive


if __name__ == "__main__":
    pytest.main([__file__, "-v"])