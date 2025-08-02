"""
Debug script to understand ATR calculation issues.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline


def debug_atr_calculation():
    """Debug the ATR calculation step by step."""
    
    # Create sample data
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
    
    print("=== DEBUGGING ATR CALCULATION ===")
    print(f"Historical candles:\n{historical_candles}")
    print(f"\nTick data:\n{tick_data}")
    
    # Create pipeline and test individual steps
    pipeline = UnifiedTechnicalIndicatorsPipeline()
    
    # Step 1: Test candle generation
    print("\n=== STEP 1: Real-time candles ===")
    trades_with_candles = pipeline._compute_realtime_candles_per_trade(
        tick_data, price_col='price', datetime_col='datetime', candle_granularity='1h'
    )
    print(f"Trades with candles shape: {trades_with_candles.shape}")
    print(f"Sample candle data:\n{trades_with_candles[['datetime', 'price', 'period', 'candle_open', 'candle_high', 'candle_low', 'candle_close']].head()}")
    print(f"Unique periods: {trades_with_candles['period'].nunique()}")
    print(f"Current candle OHLC: O={trades_with_candles['candle_open'].iloc[0]:.2f}, H={trades_with_candles['candle_high'].max():.2f}, L={trades_with_candles['candle_low'].min():.2f}, C={trades_with_candles['candle_close'].iloc[-1]:.2f}")
    
    # Step 2: Test historical lookback
    print("\n=== STEP 2: Historical lookback ===")
    trades_with_history = pipeline._pair_trades_with_historical_lookback(
        trades_with_candles, historical_candles, lookback_periods=1,
        price_col='price', datetime_col='datetime', candle_granularity='1h', candle_col='close'
    )
    trades_with_history = trades_with_history.rename(columns={'close_t-1': 'prev_close'})
    print(f"Trades with history shape: {trades_with_history.shape}")
    print(f"Previous close values: {trades_with_history['prev_close'].iloc[0]:.2f} (should be 105.0)")
    print(f"Historical candles last close: {historical_candles['close'].iloc[-1]:.2f}")
    
    # Step 3: Test True Range calculation
    print("\n=== STEP 3: True Range calculation ===")
    trades_with_tr = pipeline._calculate_true_range_for_trades(trades_with_history)
    print(f"Sample True Range values: {trades_with_tr['true_range'].head().values}")
    print(f"Expected TR = max(H-L, |H-PrevC|, |L-PrevC|)")
    print(f"Expected TR = max({trades_with_candles['candle_high'].max():.2f}-{trades_with_candles['candle_low'].min():.2f}, |{trades_with_candles['candle_high'].max():.2f}-105.0|, |{trades_with_candles['candle_low'].min():.2f}-105.0|)")
    expected_tr = max(
        trades_with_candles['candle_high'].max() - trades_with_candles['candle_low'].min(),
        abs(trades_with_candles['candle_high'].max() - 105.0),
        abs(trades_with_candles['candle_low'].min() - 105.0)
    )
    print(f"Expected TR = {expected_tr:.2f}")
    
    # Step 4: Test historical candle True Range
    print("\n=== STEP 4: Historical candle True Range ===")
    candles = historical_candles.copy()
    candles['prev_close'] = candles['close'].shift(1)
    candles['true_range'] = candles.apply(
        lambda row: max(
            row['high'] - row['low'],
            abs(row['high'] - row['prev_close']) if not pd.isna(row['prev_close']) else 0,
            abs(row['low'] - row['prev_close']) if not pd.isna(row['prev_close']) else 0
        ),
        axis=1
    )
    print(f"Historical True Ranges:\n{candles[['close', 'prev_close', 'true_range']]}")
    
    # Step 5: Test TR lookback merge
    print("\n=== STEP 5: TR lookback merge ===")
    tr_lookback_data = pipeline._pair_trades_with_historical_lookback(
        trades_df=trades_with_tr[['period', 'datetime', 'true_range']],
        historical_candles=candles[['true_range']],
        lookback_periods=3,
        price_col='true_range',
        datetime_col='datetime',
        candle_granularity='1h',
        candle_col='true_range'
    )
    print(f"TR lookback shape: {tr_lookback_data.shape}")
    print(f"TR lookback columns: {tr_lookback_data.columns.tolist()}")
    print(f"Sample TR lookback data:\n{tr_lookback_data.head()}")
    
    # Step 6: Test final ATR calculation
    print("\n=== STEP 6: Final ATR calculation ===")
    result = pipeline._compute_realtime_atr(tick_data, historical_candles, atr_period=3)
    print(f"Final result shape: {result.shape}")
    print(f"Final ATR values: {result['atr'].values}")
    print(f"Expected ATR (manual calc): {(candles['true_range'].tail(2).mean() + expected_tr) / 3:.2f}")


if __name__ == "__main__":
    debug_atr_calculation()