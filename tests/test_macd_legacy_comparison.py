#!/usr/bin/env python3
"""
Test to verify MACD implementation mismatch with legacy algorithm.

This test should FAIL initially, confirming that the current GPU MACD 
implementation does NOT match the legacy real-time algorithm.
"""

import pytest
import pandas as pd
import numpy as np
import sys
import os
from pathlib import Path

# Add source paths
sys.path.append(str(Path(__file__).parent.parent / "src"))
sys.path.append(str(Path(__file__).parent.parent / "source_repos" / "EnergyTrading" / "Python"))

def test_macd_legacy_match():
    """Test that new MACD implementation matches legacy algorithm >99%"""
    
    # Create minimal test data
    test_data = pd.DataFrame({
        'datetime': pd.date_range('2024-01-01', periods=100, freq='1h'),
        'price': np.random.uniform(50, 150, 100),
        'nanotime': range(100),
        'tradeid': range(100)
    })
    
    historical_candles = pd.DataFrame({
        'datetime': pd.date_range('2023-12-01', '2023-12-31', freq='1h'),
        'open': np.random.uniform(50, 150, len(pd.date_range('2023-12-01', '2023-12-31', freq='1h'))),
        'high': np.random.uniform(50, 150, len(pd.date_range('2023-12-01', '2023-12-31', freq='1h'))),
        'low': np.random.uniform(50, 150, len(pd.date_range('2023-12-01', '2023-12-31', freq='1h'))),
        'close': np.random.uniform(50, 150, len(pd.date_range('2023-12-01', '2023-12-31', freq='1h')))
    })
    
    try:
        # Test current MACD implementation
        from feature_engineering.macd_calculator import MACDCalculator
        from feature_engineering.array_backend import ArrayBackend
        
        backend = ArrayBackend()
        macd_calc = MACDCalculator(backend)
        
        # New implementation expects full DataFrame input
        current_result = macd_calc.compute_macd(
            test_data,
            historical_candles,
            se=12, le=26, signal_period=9
        )
        
        print(f"Current MACD implementation returned {len(current_result)} rows")
        print("Current implementation columns:", list(current_result.columns))
        
    except Exception as e:
        print(f"Current MACD implementation failed: {e}")
        current_result = None
    
    try:
        # Test legacy MACD implementation
        from Utilities.predictors_tools import compute_realtime_macd
        
        legacy_result = compute_realtime_macd(
            trades_df=test_data,
            historical_candles=historical_candles,
            se=12, le=26, signal_period=9,
            price_col='price',
            datetime_col='datetime',
            candle_granularity='1h'
        )
        
        print(f"Legacy MACD implementation returned {len(legacy_result)} rows")
        print("Legacy implementation columns:", list(legacy_result.columns))
        
    except Exception as e:
        print(f"Legacy MACD implementation failed: {e}")
        legacy_result = None
    
    # Compare results if both succeeded
    if current_result is not None and legacy_result is not None:
        # Simple comparison - expect mismatch
        if 'macd' in current_result.columns and 'macd' in legacy_result.columns:
            current_macd = current_result['macd'].values
            legacy_macd = legacy_result['macd'].values
            
            # Calculate match rate
            min_len = min(len(current_macd), len(legacy_macd))
            if min_len > 0:
                match_rate = np.mean(np.isclose(current_macd[:min_len], legacy_macd[:min_len], rtol=1e-6))
                print(f"MACD Match Rate: {match_rate:.2%}")
                
                # This test expects >99% MATCH - should pass if implementations are aligned
                assert match_rate > 0.99, f"Expected >99% match but got {match_rate:.2%} match rate"
                print("✅ SUCCESS: New and legacy MACD implementations match as expected")
            else:
                pytest.fail("No data to compare")
        else:
            pytest.fail("Missing MACD columns in results")
    else:
        pytest.fail("Could not run both implementations for comparison")

if __name__ == "__main__":
    test_macd_legacy_match()