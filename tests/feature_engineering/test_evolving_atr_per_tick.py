"""
Test for CORRECT evolving ATR per tick behavior - CRITICAL FIX VALIDATION

This test validates the CORRECT real-time ATR algorithm where each tick gets
its own ATR value based on the evolving candle state at that moment.

Expected behavior (from handoff document):
Tick 1 (13:05, price=103.2): ATR = 1.50   ✅ (based on current evolving candle state)
Tick 2 (13:12, price=103.8): ATR = 1.65   ✅ (ATR evolves as candle develops)  
Tick 3 (13:18, price=104.0): ATR = 1.75   ✅ (ATR continues evolving)
Tick 4 (13:24, price=103.9): ATR = 1.73   ✅ (ATR reflects latest candle state)
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


class TestEvolvingATRPerTick:
    """Test that ATR evolves per tick based on evolving candle state."""

    def setup_method(self):
        """Setup test data matching handoff document example."""
        # Historical candles (completed)
        base_time = datetime(2025, 1, 1, 10, 0, 0)
        
        self.historical_candles = pd.DataFrame({
            'open': [100.0, 101.0, 102.0],
            'high': [101.5, 102.5, 103.5], 
            'low': [99.5, 100.5, 101.5],
            'close': [101.0, 102.0, 103.0]
        }, index=pd.date_range(base_time, periods=3, freq='1H'))
        
        # Current tick data (13:00-14:00 period from handoff document)
        self.tick_data = pd.DataFrame({
            'datetime': [
                datetime(2025, 1, 1, 13, 5, 0),   # Tick 1: 13:05
                datetime(2025, 1, 1, 13, 12, 0),  # Tick 2: 13:12
                datetime(2025, 1, 1, 13, 18, 0),  # Tick 3: 13:18
                datetime(2025, 1, 1, 13, 24, 0),  # Tick 4: 13:24
            ],
            'price': [103.2, 103.8, 104.0, 103.9],  # From handoff document
            'nanotime': [1, 2, 3, 4],
            'tradeid': [100, 101, 102, 103]
        })

    def test_atr_evolves_per_tick_not_constant(self):
        """
        CRITICAL TEST: Each tick should get different ATR values reflecting evolving candle state.
        
        This test SHOULD FAIL with current implementation (all ticks get same ATR).
        This test SHOULD PASS with correct implementation (evolving ATR per tick).
        """
        pipeline = UnifiedTechnicalIndicatorsPipeline()
        
        result = pipeline._compute_realtime_atr(
            self.tick_data, 
            self.historical_candles, 
            atr_period=3
        )
        
        atr_values = result['atr'].tolist()
        
        # Key assertion: ATR should evolve (not all same value)
        unique_atr_count = len(set(atr_values))
        assert unique_atr_count > 1, f"ATR should evolve per tick, got {unique_atr_count} unique values: {atr_values}"
        
        # ATR should generally increase as candle develops (more volatility)
        # Tick 1: Candle OHLC = (103.2, 103.2, 103.2, 103.2) → smaller TR
        # Tick 2: Candle OHLC = (103.2, 103.8, 103.2, 103.8) → larger TR
        # Tick 3: Candle OHLC = (103.2, 104.0, 103.2, 104.0) → even larger TR
        assert atr_values[1] > atr_values[0], f"ATR should increase as candle develops: {atr_values[0]} → {atr_values[1]}"
        assert atr_values[2] > atr_values[1], f"ATR should continue increasing: {atr_values[1]} → {atr_values[2]}"

    def test_each_tick_has_different_true_range_calculation(self):
        """
        Test that each tick calculates its own True Range based on current candle OHLC state.
        
        Expected evolving candle development:
        Tick 1: Candle OHLC = (103.2, 103.2, 103.2, 103.2) → TR = max(0.0, |103.2-103.0|, |103.2-103.0|) = 0.2
        Tick 2: Candle OHLC = (103.2, 103.8, 103.2, 103.8) → TR = max(0.6, |103.8-103.0|, |103.2-103.0|) = 0.8
        Tick 3: Candle OHLC = (103.2, 104.0, 103.2, 104.0) → TR = max(0.8, |104.0-103.0|, |103.2-103.0|) = 1.0
        """
        pipeline = UnifiedTechnicalIndicatorsPipeline()
        
        result = pipeline._compute_realtime_atr(
            self.tick_data, 
            self.historical_candles, 
            atr_period=3
        )
        
        # Each tick should produce different ATR based on its evolving candle TR
        atr_values = result['atr'].tolist()
        
        # Approximate expected ATR values (using historical TR + current evolving TR)
        # Historical TRs: ~2.0, ~2.0 (calculated from historical candles)
        # Expected ATRs with evolving current TR:
        # Tick 1: (2.0 + 2.0 + 0.2) / 3 ≈ 1.4
        # Tick 2: (2.0 + 2.0 + 0.8) / 3 ≈ 1.6  
        # Tick 3: (2.0 + 2.0 + 1.0) / 3 ≈ 1.67
        
        expected_ranges = [(1.2, 1.6), (1.4, 1.8), (1.5, 1.9)]  # Tolerance ranges
        
        for i, (atr_val, (min_exp, max_exp)) in enumerate(zip(atr_values[:3], expected_ranges)):
            assert min_exp <= atr_val <= max_exp, \
                f"Tick {i+1}: Expected ATR in range [{min_exp}, {max_exp}], got {atr_val}"

    def test_atr_reflects_candle_development_pattern(self):
        """
        Test that ATR reflects realistic candle development pattern.
        
        As ticks arrive within a candle period, the candle OHLC evolves:
        - Open stays constant (first tick price)
        - High updates to max of all ticks so far
        - Low updates to min of all ticks so far  
        - Close updates to current tick price
        
        Each tick's ATR should reflect this evolving candle state.
        """
        pipeline = UnifiedTechnicalIndicatorsPipeline()
        
        result = pipeline._compute_realtime_atr(
            self.tick_data, 
            self.historical_candles, 
            atr_period=3
        )
        
        atr_values = result['atr'].tolist()
        
        # Validate that ATR evolution makes sense given price movements
        prices = self.tick_data['price'].tolist()  # [103.2, 103.8, 104.0, 103.9]
        
        # As price range expands, ATR should generally increase
        price_range_tick1 = 0.0  # Only one price point
        price_range_tick2 = max(prices[:2]) - min(prices[:2])  # 103.8 - 103.2 = 0.6
        price_range_tick3 = max(prices[:3]) - min(prices[:3])  # 104.0 - 103.2 = 0.8
        
        # ATR should correlate with expanding price range
        assert atr_values[1] > atr_values[0], "ATR should increase as price range expands"
        assert atr_values[2] >= atr_values[1], "ATR should increase or stay same as range continues expanding"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])