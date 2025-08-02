"""
Debug the lookback merge issue causing NaN previous close.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from feature_engineering.atr_calculator import ATRCalculator
from feature_engineering.array_backend import ArrayBackend


def debug_lookback_issue():
    """Debug why _pair_trade_with_historical_lookback returns NaN for prev_close."""
    
    # Create the same test data as in the test
    base_time = datetime(2025, 1, 1, 10, 0, 0)
    
    historical_candles = pd.DataFrame({
        'open': [100.0, 101.0, 102.0, 103.0, 104.0],
        'high': [101.5, 102.5, 103.5, 104.5, 105.5],
        'low': [99.5, 100.5, 101.5, 102.5, 103.5],
        'close': [101.0, 102.0, 103.0, 104.0, 105.0]
    }, index=pd.date_range(base_time, periods=5, freq='1h'))
    
    tick_times = pd.date_range(
        base_time + timedelta(hours=5), 
        periods=10, 
        freq='6min'
    )
    
    tick_data = pd.DataFrame({
        'datetime': tick_times,
        'price': [105.2, 105.8, 105.1, 106.0, 105.9, 105.3, 105.7, 105.4, 105.6, 105.5],
        'nanotime': range(10),
        'tradeid': range(100, 110)
    })
    
    print("=== DEBUGGING LOOKBACK ISSUE ===")
    print(f"Historical candles index:\n{historical_candles.index}")
    print(f"Historical candles:\n{historical_candles}")
    print(f"\nTick data:\n{tick_data[['datetime', 'price']].head()}")
    
    # Test the ATR calculator's lookback method
    backend = ArrayBackend()
    atr_calc = ATRCalculator(backend)
    
    # Step 1: Create trades with candles
    print("\n=== STEP 1: Create trades with candles ===")
    trades_with_candles = atr_calc._compute_realtime_candles_per_trade(
        tick_data, 'price', 'datetime', '1h'
    )
    print(f"Trades with candles 'period' column:\n{trades_with_candles['period'].unique()}")
    print(f"Sample trades with candles:\n{trades_with_candles[['datetime', 'price', 'period', 'candle_close']].head()}")
    
    # Step 2: Test lookback merge
    print("\n=== STEP 2: Test lookback merge ===")
    try:
        result = atr_calc._pair_trade_with_historical_lookback(
            trades_with_candles, historical_candles, lookback_periods=1,
            price_col='price', datetime_col='datetime', candle_granularity='1h', candle_col='close'
        )
        print(f"Lookback result shape: {result.shape}")
        print(f"Lookback result columns: {result.columns.tolist()}")
        
        # Check the close_t-1 column
        if 'close_t-1' in result.columns:
            print(f"close_t-1 values: {result['close_t-1'].unique()}")
            print(f"First close_t-1 value: {result['close_t-1'].iloc[0]}")
        else:
            print("❌ close_t-1 column not found!")
            
        print(f"Result sample:\n{result[['datetime', 'price', 'period', 'close_t-1']].head()}")
        
    except Exception as e:
        print(f"❌ Error in lookback merge: {e}")
        import traceback
        traceback.print_exc()
    
    # Step 3: Debug the merge process manually
    print("\n=== STEP 3: Manual merge debug ===")
    df = trades_with_candles.copy()
    df['period'] = pd.to_datetime(df['datetime']).dt.floor('1h')
    
    print(f"Trade periods: {df['period'].unique()}")
    print(f"Historical candle index: {historical_candles.index.tolist()}")
    
    # Check if trade periods align with historical candle index
    trade_period = df['period'].iloc[0]
    print(f"Trade period: {trade_period}")
    print(f"Expected previous candle: {trade_period - pd.Timedelta(hours=1)}")
    
    # Check if the expected previous candle exists in historical data
    expected_prev = trade_period - pd.Timedelta(hours=1)
    if expected_prev in historical_candles.index:
        expected_prev_close = historical_candles.loc[expected_prev, 'close']
        print(f"✓ Found expected previous close: {expected_prev_close}")
    else:
        print(f"❌ Expected previous candle {expected_prev} not found in historical candles")
        print(f"Available historical periods: {historical_candles.index.tolist()}")
    
    # Step 4: Test manual shift and merge
    print("\n=== STEP 4: Manual shift and merge ===")
    candles = historical_candles.copy()
    shifted_close = candles['close'].shift(1)
    print(f"Original close: {candles['close'].tolist()}")
    print(f"Shifted close (t-1): {shifted_close.tolist()}")
    
    # Try the merge manually
    close_histories = pd.DataFrame({'close_t-1': shifted_close})
    print(f"Close histories index: {close_histories.index}")
    print(f"Close histories:\n{close_histories}")
    
    merge_result = pd.merge(
        df[['datetime', 'price', 'period']],
        close_histories,
        left_on='period',
        right_index=True,
        how='left'
    )
    print(f"Manual merge result:\n{merge_result[['datetime', 'price', 'period', 'close_t-1']].head()}")


if __name__ == "__main__":
    debug_lookback_issue()