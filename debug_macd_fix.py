"""
Debug script to understand why MACD calculation is returning all zeros.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from src.feature_engineering.array_backend import ArrayBackend
from src.feature_engineering.macd_calculator import MACDCalculator


def debug_macd_calculation():
    """Debug the MACD calculation step by step"""
    
    # Initialize
    backend = ArrayBackend()
    calculator = MACDCalculator(backend)
    
    # Create simple test data
    periods = 50
    base_price = 70.0
    
    # Create simple rising price series
    prices = base_price + np.linspace(0, 10, periods)
    
    start_time = datetime(2024, 1, 1, 9, 0)
    timestamps = [start_time + timedelta(hours=i) for i in range(periods)]
    
    trades_df = pd.DataFrame({
        'datetime': timestamps,
        'price': prices,
        'tradeid': [f'trade_{i:06d}' for i in range(periods)],
        'nanotime': [int(t.timestamp() * 1e9) for t in timestamps]
    })
    
    # Create historical candles
    hist_periods = 30
    hist_prices = base_price - 5 + np.linspace(0, 5, hist_periods)
    hist_start = datetime(2023, 12, 25, 9, 0)
    hist_timestamps = [hist_start + timedelta(hours=i) for i in range(hist_periods)]
    
    historical_candles = pd.DataFrame({
        'open': hist_prices,
        'high': hist_prices + 0.5,
        'low': hist_prices - 0.5,
        'close': hist_prices + np.random.normal(0, 0.1, hist_periods)
    }, index=pd.DatetimeIndex(hist_timestamps))
    
    print("=== INPUT DATA ===")
    print(f"Trades data shape: {trades_df.shape}")
    print(f"Historical candles shape: {historical_candles.shape}")
    print(f"Price range: {trades_df['price'].min():.3f} to {trades_df['price'].max():.3f}")
    print(f"Historical price range: {historical_candles['close'].min():.3f} to {historical_candles['close'].max():.3f}")
    
    # Step-by-step debugging
    try:
        print("\n=== STEP 1: Real-time candle generation ===")
        trades_with_candles = calculator._compute_realtime_candles_per_trade(
            trades_df, 'price', 'datetime', '1h'
        )
        print(f"Trades with candles shape: {trades_with_candles.shape}")
        print(f"Columns: {list(trades_with_candles.columns)}")
        print(f"Sample OHLC:")
        print(trades_with_candles[['candle_open', 'candle_high', 'candle_low', 'candle_close']].head())
        
        print("\n=== STEP 2: OHLC mean calculation ===")
        trades_with_ohlc = calculator._add_ohlc_mean(trades_with_candles)
        print(f"OHLC mean range: {trades_with_ohlc['ohlc_mean'].min():.3f} to {trades_with_ohlc['ohlc_mean'].max():.3f}")
        print(f"Sample OHLC mean values: {trades_with_ohlc['ohlc_mean'].head().tolist()}")
        
        print("\n=== STEP 3: Historical candles preparation ===")
        hist_candles_view = calculator._prepare_historical_candles(historical_candles)
        print(f"Historical OHLC mean range: {hist_candles_view['ohlc_mean'].min():.3f} to {hist_candles_view['ohlc_mean'].max():.3f}")
        
        print("\n=== STEP 4: Historical lookback for short EMA (12) ===")
        short_ema_data = calculator._pair_trade_with_historical_lookback(
            trades_with_ohlc[['period', 'datetime', 'ohlc_mean']],
            hist_candles_view,
            lookback_periods=12,
            price_col='ohlc_mean',
            datetime_col='datetime',
            candle_granularity='1h',
            candle_col='ohlc_mean'
        )
        print(f"Short EMA data shape: {short_ema_data.shape}")
        print(f"Short EMA columns: {list(short_ema_data.columns)}")
        
        # Check for close_t columns
        close_cols = [col for col in short_ema_data.columns if col.startswith('close_t')]
        print(f"Close_t columns found: {close_cols[:5]}...")  # Show first 5
        
        if close_cols:
            print(f"Sample close_t values:")
            print(short_ema_data[close_cols[:3]].head())
        else:
            print("❌ NO close_t columns found!")
        
        print("\n=== STEP 5: Short EMA calculation ===")
        short_ema = calculator._calculate_simple_ema(short_ema_data)
        print(f"Short EMA range: {short_ema.min():.3f} to {short_ema.max():.3f}")
        print(f"Short EMA sample: {short_ema.head().tolist()}")
        
        print("\n=== STEP 6: Long EMA calculation ===")
        long_ema_data = calculator._pair_trade_with_historical_lookback(
            trades_with_ohlc[['period', 'datetime', 'ohlc_mean']],
            hist_candles_view,
            lookback_periods=26,
            price_col='ohlc_mean',
            datetime_col='datetime',
            candle_granularity='1h',
            candle_col='ohlc_mean'
        )
        long_ema = calculator._calculate_simple_ema(long_ema_data)
        print(f"Long EMA range: {long_ema.min():.3f} to {long_ema.max():.3f}")
        
        print("\n=== STEP 7: MACD calculation ===")
        macd_line = short_ema - long_ema
        print(f"MACD range: {macd_line.min():.3f} to {macd_line.max():.3f}")
        print(f"MACD sample: {macd_line.head().tolist()}")
        
        if macd_line.min() == 0.0 and macd_line.max() == 0.0:
            print("❌ MACD is all zeros! Short EMA == Long EMA")
            print(f"Short EMA == Long EMA? {np.allclose(short_ema, long_ema)}")
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()


def test_proper_ema_calculation():
    """Test what proper EMA should look like"""
    
    print("\n" + "="*50)
    print("=== REFERENCE EMA CALCULATION ===")
    
    # Simple test data
    prices = np.array([70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80])
    
    def calculate_proper_ema(data, span):
        """Calculate proper exponential moving average"""
        alpha = 2.0 / (span + 1)
        result = np.zeros_like(data, dtype=float)
        result[0] = data[0]
        
        for i in range(1, len(data)):
            result[i] = alpha * data[i] + (1 - alpha) * result[i-1]
        
        return result
    
    # Calculate proper EMAs
    fast_ema = calculate_proper_ema(prices, 12)
    slow_ema = calculate_proper_ema(prices, 26)
    proper_macd = fast_ema - slow_ema
    
    print(f"Prices: {prices}")
    print(f"Fast EMA (12): {fast_ema}")
    print(f"Slow EMA (26): {slow_ema}")
    print(f"Proper MACD: {proper_macd}")
    print(f"Proper MACD range: {proper_macd.min():.3f} to {proper_macd.max():.3f}")
    
    # The proper MACD should be positive and increasing (momentum building)
    assert proper_macd[-1] > proper_macd[0], "MACD should respond to trend"
    assert not np.allclose(proper_macd, 0), "MACD should not be all zeros"


if __name__ == "__main__":
    debug_macd_calculation()
    test_proper_ema_calculation()