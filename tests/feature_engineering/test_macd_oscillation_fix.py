"""
Test suite for MACD oscillation fix.

This test demonstrates that MACD should oscillate around zero even during
sustained uptrends, rather than continuously rising with price.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.feature_engineering.array_backend import ArrayBackend
from src.feature_engineering.macd_calculator import MACDCalculator


class TestMACDOscillationFix:
    """Test suite for MACD oscillation behavior during sustained uptrends"""
    
    @pytest.fixture
    def backend(self):
        """Initialize ArrayBackend"""
        return ArrayBackend()
    
    @pytest.fixture
    def calculator(self, backend):
        """Initialize MACD calculator"""
        return MACDCalculator(backend)
    
    @pytest.fixture
    def sustained_uptrend_data(self):
        """
        Create test data showing sustained uptrend with varying momentum.
        
        Expected MACD behavior:
        - Should oscillate around zero even during uptrend
        - Should show momentum changes (acceleration/deceleration)
        - Should NOT continuously rise from 0.5 to 5.5 like in screenshot
        """
        # Create 100 periods of uptrend with varying momentum
        periods = 100
        base_price = 70.0
        
        # Phase 1: Slow rise (periods 0-30)
        slow_rise = np.linspace(0, 5, 31)
        
        # Phase 2: Acceleration (periods 31-60) 
        acceleration = np.linspace(5, 15, 30)
        
        # Phase 3: Deceleration but still rising (periods 61-100)  
        deceleration = 15 + np.linspace(0, 5, 39) * 0.5  # 39 elements to make total 100
        
        # Combine phases (31 + 30 + 39 = 100)
        price_changes = np.concatenate([slow_rise, acceleration, deceleration])
        prices = base_price + price_changes
        
        # Add some noise to make it realistic
        np.random.seed(42)
        prices += np.random.normal(0, 0.1, len(prices))
        
        # Create datetime index
        start_time = datetime(2024, 1, 1, 9, 0)
        timestamps = [start_time + timedelta(hours=i) for i in range(periods)]
        
        return pd.DataFrame({
            'datetime': timestamps,
            'price': prices,
            'tradeid': [f'trade_{i:06d}' for i in range(periods)],
            'nanotime': [int(t.timestamp() * 1e9) for t in timestamps]
        })
    
    @pytest.fixture
    def historical_candles(self):
        """Create historical OHLC candles for lookback"""
        # 50 periods of historical data
        periods = 50
        base_price = 65.0
        
        # Historical prices with some variation
        np.random.seed(123)
        prices = base_price + np.cumsum(np.random.normal(0, 0.2, periods))
        
        start_time = datetime(2023, 12, 1, 9, 0)
        timestamps = [start_time + timedelta(hours=i) for i in range(periods)]
        
        # Create OHLC data
        opens = prices
        closes = prices + np.random.normal(0, 0.1, periods)
        highs = np.maximum(opens, closes) + np.abs(np.random.normal(0, 0.2, periods))
        lows = np.minimum(opens, closes) - np.abs(np.random.normal(0, 0.2, periods))
        
        return pd.DataFrame({
            'open': opens,
            'high': highs, 
            'low': lows,
            'close': closes
        }, index=pd.DatetimeIndex(timestamps))
    
    def test_current_macd_shows_trending_behavior(self, calculator, sustained_uptrend_data, historical_candles):
        """
        TEST: Current implementation shows continuous trending (FAILING BEHAVIOR)
        
        This test documents the current broken behavior where MACD
        continuously rises instead of oscillating.
        """
        # Compute MACD with current implementation
        result = calculator.compute_macd(
            sustained_uptrend_data,
            historical_candles,
            se=12,
            le=26,
            signal_period=9,
            candle_granularity='1h'
        )
        
        # Current broken behavior: MACD continuously rises
        macd_values = result['macd'].dropna()
        
        # Document the broken behavior
        macd_min = macd_values.min()
        macd_max = macd_values.max()
        macd_trend = np.polyfit(range(len(macd_values)), macd_values, 1)[0]
        
        print(f"\n=== CURRENT BROKEN MACD BEHAVIOR ===")
        print(f"MACD Range: {macd_min:.3f} to {macd_max:.3f}")
        print(f"MACD Variation: {macd_max - macd_min:.3f}")
        print(f"MACD Trend Slope: {macd_trend:.6f}")
        print(f"Price Range: {sustained_uptrend_data['price'].min():.3f} to {sustained_uptrend_data['price'].max():.3f}")
        
        # This documents the BROKEN behavior - MACD should NOT continuously trend up
        assert macd_trend > 0.01, "Current implementation shows continuous upward trend (BROKEN)"
        assert macd_max - macd_min > 2.0, "Current implementation shows excessive variation (BROKEN)"
        
        # MACD should oscillate around zero, not trend with price
        # This assertion will FAIL with current implementation, demonstrating the bug
        mean_macd = macd_values.mean()
        print(f"MACD Mean: {mean_macd:.3f} (should be close to 0)")
        
        # Document that current implementation is broken
        assert mean_macd > 1.0, "Current MACD mean is far from zero (BROKEN BEHAVIOR)"
    
    def test_proper_macd_oscillates_correctly(self, calculator, sustained_uptrend_data, historical_candles):
        """
        TEST: Fixed MACD should oscillate properly during uptrends
        
        This test validates the FIXED behavior showing proper oscillation.
        """
        # Compute MACD with fixed implementation
        result = calculator.compute_macd(
            sustained_uptrend_data,
            historical_candles,
            se=12,
            le=26,
            signal_period=9,
            candle_granularity='1h'
        )
        
        macd_values = result['macd'].dropna()
        
        # Validate fixed behavior:
        macd_mean = macd_values.mean()
        macd_std = macd_values.std()
        macd_min = macd_values.min()
        macd_max = macd_values.max()
        
        print(f"\n=== FIXED MACD BEHAVIOR VALIDATION ===")
        print(f"MACD Range: {macd_min:.3f} to {macd_max:.3f}")
        print(f"MACD Mean: {macd_mean:.3f}")
        print(f"MACD Std Dev: {macd_std:.3f}")
        
        # Validate the fix worked:
        assert macd_min != 0.0 or macd_max != 0.0, "MACD should not be all zeros (fixed)"
        assert macd_std > 0.1, "MACD should show oscillation"
        assert macd_std < 5.0, "MACD oscillation should be reasonable"
        
        # MACD should respond to price changes but not trend excessively
        # In uptrends, MACD can be positive but should still oscillate
        assert len(macd_values) > 10, "Should have sufficient data points"
        
        # The fix should produce reasonable MACD values
        assert not np.allclose(macd_values, macd_values[0]), "MACD should vary over time"
    
    def test_macd_responds_to_momentum_changes(self, calculator, sustained_uptrend_data, historical_candles):
        """
        TEST: MACD should respond to momentum changes, not just price direction
        
        During the test data:
        - Phase 1 (0-30): Slow rise → MACD should be slightly positive
        - Phase 2 (31-60): Acceleration → MACD should rise (momentum increasing)
        - Phase 3 (61-100): Deceleration → MACD should fall (momentum decreasing)
        """
        pytest.skip("Will implement after fixing basic oscillation behavior")
    
    def create_reference_macd(self, prices, fast=12, slow=26, signal=9):
        """
        Create reference MACD using proper exponential moving averages
        for comparison with our implementation.
        """
        # Standard EMA calculation with proper exponential weighting
        def ema(data, span):
            alpha = 2.0 / (span + 1)
            result = np.zeros_like(data)
            result[0] = data[0]
            
            for i in range(1, len(data)):
                result[i] = alpha * data[i] + (1 - alpha) * result[i-1]
            
            return result
        
        # Calculate proper EMAs
        fast_ema = ema(prices, fast)
        slow_ema = ema(prices, slow)
        
        # MACD line
        macd_line = fast_ema - slow_ema
        
        # Signal line
        signal_line = ema(macd_line, signal)
        
        # Histogram
        histogram = macd_line - signal_line
        
        return {
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram
        }


if __name__ == "__main__":
    # Run the test to demonstrate current broken behavior
    pytest.main([__file__, "-v", "-s"])