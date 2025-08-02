#!/usr/bin/env python3
"""
Debug script to reproduce the ATR 2.0 issue mentioned in the handoff document.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline
from feature_engineering.atr_calculator import ATRCalculator
from feature_engineering.array_backend import ArrayBackend

def create_test_data():
    """Create the exact test data mentioned in the handoff document."""
    # Create historical candles as mentioned in the document
    base_time = datetime(2025, 1, 1, 10, 0, 0)
    
    historical_candles = pd.DataFrame({
        'open': [100.0, 101.0, 102.0],
        'high': [101.5, 102.5, 103.5], 
        'low': [99.5, 100.5, 101.5],
        'close': [101.0, 102.0, 103.0]
    }, index=pd.date_range(base_time, periods=3, freq='1h'))
    
    # Create tick data within the next hour
    tick_times = pd.date_range(
        base_time + timedelta(hours=3), 
        periods=5, 
        freq='6min'
    )
    
    tick_data = pd.DataFrame({
        'datetime': tick_times,
        'price': [103.2, 103.8, 103.1, 104.0, 103.9],
        'nanotime': range(5),
        'tradeid': range(100, 105)
    })
    
    return tick_data, historical_candles

def test_atr_calculation():
    """Test the ATR calculation to see if we get the 2.0 issue."""
    print("=== ATR Issue Debug Test ===")
    
    tick_data, historical_candles = create_test_data()
    
    print(f"Historical candles:\n{historical_candles}")
    print(f"\nTick data:\n{tick_data}")
    
    # Expected calculation based on handoff document:
    # Historical TR: [2.0, 2.0] (from completed candles)
    # Current TR: 1.0 (from evolving candle) 
    # ATR = (2.0 + 2.0 + 1.0) / 3 = 1.67
    
    pipeline = UnifiedTechnicalIndicatorsPipeline()
    backend = ArrayBackend('cupy')  # GPU backend
    atr_calc = ATRCalculator(backend)
    
    # Test the intermediate steps
    print("\n=== DEBUGGING INTERMEDIATE STEPS ===")
    
    # Step 1: Check candle generation
    trades_with_candles = atr_calc._compute_realtime_candles_per_trade(
        tick_data, 'price', 'datetime', '1h'
    )
    print("Generated candles OHLC:")
    candle_cols = ['candle_open', 'candle_high', 'candle_low', 'candle_close']
    for i, row in trades_with_candles[candle_cols].iterrows():
        print(f"  Tick {i}: O={row['candle_open']:.1f} H={row['candle_high']:.1f} L={row['candle_low']:.1f} C={row['candle_close']:.1f}")
    
    # Expected: O=103.2, H=104.0, L=103.1, C=103.9 (last tick)
    print(f"\nExpected current candle: O=103.2, H=104.0, L=103.1, C=103.9")
    actual_last_candle = trades_with_candles[candle_cols].iloc[-1]
    print(f"Actual last candle: O={actual_last_candle['candle_open']:.1f}, H={actual_last_candle['candle_high']:.1f}, L={actual_last_candle['candle_low']:.1f}, C={actual_last_candle['candle_close']:.1f}")
    
    # Manual TR calculation
    expected_tr = max(104.0 - 103.1, abs(104.0 - 103.0), abs(103.1 - 103.0))  # max(0.9, 1.0, 0.1) = 1.0
    print(f"\nExpected TR = max(H-L, |H-PrevClose|, |L-PrevClose|) = max({104.0-103.1:.1f}, {abs(104.0-103.0):.1f}, {abs(103.1-103.0):.1f}) = {expected_tr:.1f}")
    
    result = pipeline._compute_realtime_atr(
        tick_data, 
        historical_candles, 
        atr_period=3
    )
    
    print(f"\nResult ATR values: {result['atr'].unique()}")
    print(f"Expected: ~1.67")
    print(f"Actual: {result['atr'].iloc[0]}")
    
    if abs(result['atr'].iloc[0] - 1.67) > 0.1:
        print(f"❌ ISSUE REPRODUCED: Expected ~1.67, got {result['atr'].iloc[0]}")
        if result['atr'].iloc[0] == 2.0:
            print("🚨 CONFIRMED: Getting the 2.0 fallback value mentioned in handoff!")
    else:
        print(f"✅ Working correctly: ATR = {result['atr'].iloc[0]}")

if __name__ == "__main__":
    test_atr_calculation()