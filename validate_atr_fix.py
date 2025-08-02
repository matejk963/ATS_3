#!/usr/bin/env python3
"""
Validation script for ATR Real-Time Calculation Fix
==================================================

This script validates that the ATR fix produces evolving ATR values per tick
instead of constant forward-filled values.

Expected behavior:
- Each tick should get different ATR values  
- ATR should evolve as candle OHLC develops
- No more constant ATR values across all ticks in same period
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline


def validate_atr_fix():
    """Validate that ATR calculation produces evolving values per tick."""
    
    print("=" * 60)
    print("ATR REAL-TIME CALCULATION FIX VALIDATION")
    print("=" * 60)
    
    # Setup test data matching handoff document example
    base_time = datetime(2025, 1, 1, 10, 0, 0)
    
    # Historical candles (completed)
    historical_candles = pd.DataFrame({
        'open': [100.0, 101.0, 102.0],
        'high': [101.5, 102.5, 103.5], 
        'low': [99.5, 100.5, 101.5],
        'close': [101.0, 102.0, 103.0]
    }, index=pd.date_range(base_time, periods=3, freq='1h'))
    
    # Current tick data (13:00-14:00 period from handoff document)
    tick_data = pd.DataFrame({
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
    
    print(f"Historical candles:\n{historical_candles}")
    print(f"\nTick data:\n{tick_data}")
    
    # Run ATR calculation
    print("\n" + "=" * 40)
    print("RUNNING ATR CALCULATION...")
    print("=" * 40)
    
    pipeline = UnifiedTechnicalIndicatorsPipeline()
    result = pipeline._compute_realtime_atr(
        tick_data, 
        historical_candles, 
        atr_period=3
    )
    
    print(f"\nResult shape: {result.shape}")
    print(f"Result columns: {result.columns.tolist()}")
    
    # Extract ATR values
    atr_values = result['atr'].tolist()
    unique_atr_count = len(set(atr_values))
    
    print("\n" + "=" * 40)
    print("VALIDATION RESULTS")
    print("=" * 40)
    
    print(f"ATR values: {[f'{atr:.3f}' for atr in atr_values]}")
    print(f"Unique ATR values: {unique_atr_count}")
    print(f"ATR range: {min(atr_values):.3f} - {max(atr_values):.3f}")
    
    # Validation checks
    success = True
    
    print("\n" + "-" * 40)
    print("VALIDATION CHECKS")
    print("-" * 40)
    
    # Check 1: ATR should evolve (not all same value)
    if unique_atr_count > 1:
        print("✅ PASS: ATR evolves per tick (not constant)")
    else:
        print("❌ FAIL: ATR is constant across all ticks")
        success = False
    
    # Check 2: ATR should generally increase as candle develops
    if len(atr_values) >= 3:
        if atr_values[1] > atr_values[0] and atr_values[2] >= atr_values[1]:
            print("✅ PASS: ATR increases as candle develops")
        else:
            print("⚠️  WARN: ATR evolution pattern may be unexpected")
    
    # Check 3: All ATR values should be positive and reasonable
    if all(atr > 0 for atr in atr_values) and all(atr < 10 for atr in atr_values):
        print("✅ PASS: ATR values are positive and reasonable")
    else:
        print("❌ FAIL: ATR values are not reasonable")
        success = False
    
    print("\n" + "=" * 40)
    print("EXPECTED vs ACTUAL BEHAVIOR")
    print("=" * 40)
    
    print("Expected behavior (from handoff document):")
    print("Tick 1 (13:05, price=103.2): ATR = 1.50   ✅ (evolving)")  
    print("Tick 2 (13:12, price=103.8): ATR = 1.65   ✅ (evolving)")
    print("Tick 3 (13:18, price=104.0): ATR = 1.75   ✅ (evolving)")
    print("Tick 4 (13:24, price=103.9): ATR = 1.73   ✅ (evolving)")
    
    print("\nActual behavior (current implementation):")
    for i, atr in enumerate(atr_values):
        tick_time = tick_data.iloc[i]['datetime'].strftime('%H:%M')
        tick_price = tick_data.iloc[i]['price']
        print(f"Tick {i+1} ({tick_time}, price={tick_price}): ATR = {atr:.3f}   {'✅' if i == 0 or atr != atr_values[i-1] else '❌'}")
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 ATR FIX VALIDATION: SUCCESS")
        print("The fix correctly produces evolving ATR values per tick!")
    else:
        print("❌ ATR FIX VALIDATION: FAILED")
        print("The fix did not produce expected evolving ATR behavior.")
    print("=" * 60)
    
    return success


if __name__ == "__main__":
    success = validate_atr_fix()
    sys.exit(0 if success else 1)