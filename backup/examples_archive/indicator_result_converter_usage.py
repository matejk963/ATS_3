"""
IndicatorResultConverter Usage Examples

This script demonstrates how to use the IndicatorResultConverter to seamlessly
convert technical indicator array outputs back to pandas DataFrames.

Covers all indicator types:
- MACD (multi-component results)
- ATR (single array results) 
- Candles (OHLC dictionary results)
- Swings (boolean array results)
- Generic arrays (any dictionary of arrays)
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# Import Phase 1 and Phase 2 components
from src.feature_engineering.array_backend import ArrayBackend
from src.feature_engineering.gpu_converter import GPUArrayConverter, DataFrameMetadata
from src.feature_engineering.indicator_result_converter import IndicatorResultConverter

# Import calculators
from src.feature_engineering.macd_calculator import MACDCalculator
from src.feature_engineering.atr_calculator import ATRCalculator
from src.feature_engineering.candle_generator import CandleGenerator
from src.feature_engineering.swing_point_detector import SwingPointDetector


def create_sample_data(n_points: int = 1000) -> pd.DataFrame:
    """Create sample price data for demonstration"""
    np.random.seed(42)
    
    # Generate timestamps
    start_time = datetime(2024, 1, 1, 9, 0)
    timestamps = [start_time + timedelta(minutes=i) for i in range(n_points)]
    
    # Generate realistic price walk
    returns = np.random.normal(0, 0.001, n_points)
    prices = 100 * np.exp(np.cumsum(returns))
    
    # Create mid prices (simulating data fetcher output)
    df = pd.DataFrame({
        '0': prices,  # Mid prices (column '0' from data fetcher)
        'b_price': prices - 0.01,  # Bid prices
        'a_price': prices + 0.01,  # Ask prices
        'volume': np.random.randint(100, 1000, n_points)
    }, index=pd.DatetimeIndex(timestamps, name='datetime'))
    
    return df


def example_1_basic_macd_conversion():
    """Example 1: Basic MACD array-to-DataFrame conversion"""
    print("=" * 60)
    print("Example 1: Basic MACD Conversion")
    print("=" * 60)
    
    # 1. Create sample data
    df = create_sample_data(500)
    print(f"Sample data shape: {df.shape}")
    print(f"Sample data columns: {list(df.columns)}")
    
    # 2. Calculate MACD using Phase 2 calculator
    backend = ArrayBackend('numpy')
    macd_calc = MACDCalculator(backend)
    
    prices = df['0'].values  # Mid prices
    macd_result = macd_calc.compute_macd(prices, fast=12, slow=26, signal=9)
    
    print(f"\nMACD result keys: {list(macd_result.keys())}")
    print(f"MACD array shape: {macd_result['macd'].shape}")
    
    # 3. Convert to DataFrame using IndicatorResultConverter
    converter = IndicatorResultConverter()
    
    # Create metadata from original DataFrame
    arrays, metadata = GPUArrayConverter.to_arrays(df)
    
    # Convert MACD arrays to DataFrame
    macd_df = converter.macd_to_dataframe(macd_result, metadata)
    
    print(f"\nMACD DataFrame shape: {macd_df.shape}")
    print(f"MACD DataFrame columns: {list(macd_df.columns)}")
    print(f"MACD DataFrame index type: {type(macd_df.index)}")
    print("\nFirst 5 rows:")
    print(macd_df.head())
    
    return macd_df


def example_2_prefixed_indicators():
    """Example 2: Multiple timeframes with prefixed columns"""
    print("\n" + "=" * 60)
    print("Example 2: Multiple Timeframes with Prefixes")
    print("=" * 60)
    
    # Create sample data
    df = create_sample_data(1000)
    backend = ArrayBackend('numpy')
    converter = IndicatorResultConverter()
    
    # Get metadata once
    arrays, metadata = GPUArrayConverter.to_arrays(df)
    prices = df['0'].values
    
    # Calculate MACD for different timeframes (simulated)
    macd_calc = MACDCalculator(backend)
    
    # Fast MACD (5, 13, 3)
    fast_macd = macd_calc.compute_macd(prices, fast=5, slow=13, signal=3)
    fast_macd_df = converter.macd_to_dataframe(fast_macd, metadata, prefix='fast_')
    
    # Standard MACD (12, 26, 9)
    std_macd = macd_calc.compute_macd(prices, fast=12, slow=26, signal=9)
    std_macd_df = converter.macd_to_dataframe(std_macd, metadata, prefix='std_')
    
    # Slow MACD (26, 50, 20)
    slow_macd = macd_calc.compute_macd(prices, fast=26, slow=50, signal=20)
    slow_macd_df = converter.macd_to_dataframe(slow_macd, metadata, prefix='slow_')
    
    # Combine all MACD indicators
    combined_df = pd.concat([fast_macd_df, std_macd_df, slow_macd_df], axis=1)
    
    print(f"Combined DataFrame shape: {combined_df.shape}")
    print(f"Combined DataFrame columns: {list(combined_df.columns)}")
    print("\nFirst 5 rows of combined indicators:")
    print(combined_df.head())
    
    return combined_df


def example_3_atr_conversion():
    """Example 3: ATR single array conversion"""
    print("\n" + "=" * 60)
    print("Example 3: ATR Array Conversion")
    print("=" * 60)
    
    # Create OHLC data for ATR
    df = create_sample_data(500)
    backend = ArrayBackend('numpy')
    converter = IndicatorResultConverter()
    
    # Generate OHLC candles from tick data
    candle_gen = CandleGenerator(backend)
    prices = df['0'].values
    timestamps = df.index.astype('int64') // 10**9
    
    ohlc = candle_gen.generate_ohlc(prices, timestamps, '5min')
    print(f"Generated {len(ohlc['open'])} candles from {len(prices)} ticks")
    
    # Calculate ATR
    atr_calc = ATRCalculator(backend)
    atr_result = atr_calc.compute_atr(ohlc['high'], ohlc['low'], ohlc['close'], period=14)
    
    print(f"ATR result shape: {atr_result.shape}")
    print(f"ATR values range: {np.nanmin(atr_result):.4f} to {np.nanmax(atr_result):.4f}")
    
    # Create metadata for candle timeframe
    candle_timestamps = df.index[:len(atr_result)]
    candle_metadata = DataFrameMetadata(
        index=candle_timestamps,
        columns=['atr'],
        dtypes={'atr': 'float64'}
    )
    
    # Convert to DataFrame
    atr_df = converter.atr_to_dataframe(atr_result, candle_metadata)
    
    print(f"\nATR DataFrame shape: {atr_df.shape}")
    print("First 10 rows (with NaN values shown):")
    print(atr_df.head(10))
    
    # Multiple ATR periods with prefixes
    atr_7d = atr_calc.compute_atr(ohlc['high'], ohlc['low'], ohlc['close'], period=7)
    atr_21d = atr_calc.compute_atr(ohlc['high'], ohlc['low'], ohlc['close'], period=21)
    
    atr_7d_df = converter.atr_to_dataframe(atr_7d, candle_metadata, prefix='7d_')
    atr_21d_df = converter.atr_to_dataframe(atr_21d, candle_metadata, prefix='21d_')
    
    multi_atr_df = pd.concat([atr_df, atr_7d_df, atr_21d_df], axis=1)
    print(f"\nMulti-period ATR columns: {list(multi_atr_df.columns)}")
    
    return atr_df, multi_atr_df


def example_4_candle_and_swing_conversion():
    """Example 4: Candle OHLC and swing points conversion"""
    print("\n" + "=" * 60)
    print("Example 4: Candles and Swing Points Conversion")
    print("=" * 60)
    
    df = create_sample_data(800)
    backend = ArrayBackend('numpy')
    converter = IndicatorResultConverter()
    
    # Generate candles
    candle_gen = CandleGenerator(backend)
    prices = df['0'].values
    timestamps = df.index.astype('int64') // 10**9
    
    ohlc = candle_gen.generate_ohlc(prices, timestamps, '15min')
    n_candles = len(ohlc['open'])
    
    print(f"Generated {n_candles} 15-minute candles")
    
    # Create metadata for candles
    candle_timestamps = df.index[:n_candles]
    candle_metadata = DataFrameMetadata(
        index=candle_timestamps,
        columns=['open', 'high', 'low', 'close'],
        dtypes={col: 'float64' for col in ['open', 'high', 'low', 'close']}
    )
    
    # Convert candles to DataFrame
    candles_df = converter.candles_to_dataframe(ohlc, candle_metadata)
    
    print(f"Candles DataFrame shape: {candles_df.shape}")
    print("Sample candles:")
    print(candles_df.head())
    
    # Detect swing points
    swing_detector = SwingPointDetector(backend)
    swings = swing_detector.detect_swings(ohlc['high'], ohlc['low'], lookback=10)
    
    swing_count = np.sum(swings['swing_highs']) + np.sum(swings['swing_lows'])
    print(f"\nDetected {swing_count} swing points:")
    print(f"  Swing highs: {np.sum(swings['swing_highs'])}")
    print(f"  Swing lows: {np.sum(swings['swing_lows'])}")
    
    # Convert swings to DataFrame
    swings_df = converter.swings_to_dataframe(swings, candle_metadata)
    
    print(f"Swings DataFrame shape: {swings_df.shape}")
    print("Swing points (showing only True values):")
    swing_points = swings_df[swings_df.any(axis=1)]
    print(swing_points)
    
    # Combine candles and swings
    candles_with_swings = pd.concat([candles_df, swings_df], axis=1)
    print(f"\nCombined candles+swings columns: {list(candles_with_swings.columns)}")
    
    return candles_df, swings_df, candles_with_swings


def example_5_generic_array_conversion():
    """Example 5: Generic array conversion for custom indicators"""
    print("\n" + "=" * 60)
    print("Example 5: Generic Array Conversion")
    print("=" * 60)
    
    df = create_sample_data(300)
    converter = IndicatorResultConverter()
    
    # Get metadata
    arrays, metadata = GPUArrayConverter.to_arrays(df)
    prices = df['0'].values
    
    # Create custom indicator arrays (example: multiple moving averages)
    ma_5 = pd.Series(prices).rolling(5).mean().values
    ma_20 = pd.Series(prices).rolling(20).mean().values
    ma_50 = pd.Series(prices).rolling(50).mean().values
    
    # Custom momentum indicators
    roc_10 = (prices / np.roll(prices, 10) - 1) * 100  # Rate of Change
    momentum = prices - np.roll(prices, 14)  # Simple momentum
    
    # Combine into generic arrays dictionary
    custom_indicators = {
        'ma_5': ma_5,
        'ma_20': ma_20,
        'ma_50': ma_50,
        'roc_10': roc_10,
        'momentum': momentum
    }
    
    # Convert using generic method
    indicators_df = converter.arrays_to_dataframe(custom_indicators, metadata)
    
    print(f"Custom indicators DataFrame shape: {indicators_df.shape}")
    print(f"Custom indicators columns: {list(indicators_df.columns)}")
    print("\nFirst 10 rows (showing NaN from rolling calculations):")
    print(indicators_df.head(10))
    
    # With prefix for namespacing
    prefixed_df = converter.arrays_to_dataframe(
        custom_indicators, metadata, prefix='custom_'
    )
    print(f"\nWith prefix columns: {list(prefixed_df.columns)}")
    
    return indicators_df, prefixed_df


def example_6_complete_pipeline():
    """Example 6: Complete data processing pipeline"""
    print("\n" + "=" * 60)
    print("Example 6: Complete Processing Pipeline")
    print("=" * 60)
    
    # 1. Simulate data fetcher output
    df = create_sample_data(1000)
    print(f"1. Raw data: {df.shape}, columns: {list(df.columns)}")
    
    # 2. Initialize components
    backend = ArrayBackend('numpy')
    converter = IndicatorResultConverter()
    
    # 3. Extract price data
    prices = df['0'].values
    timestamps = df.index.astype('int64') // 10**9
    arrays, metadata = GPUArrayConverter.to_arrays(df)
    
    # 4. Generate OHLC candles
    candle_gen = CandleGenerator(backend)
    ohlc = candle_gen.generate_ohlc(prices, timestamps, '5min')
    n_candles = len(ohlc['open'])
    
    # 5. Calculate all indicators
    # MACD on tick data
    macd_calc = MACDCalculator(backend)
    macd_result = macd_calc.compute_macd(prices, fast=12, slow=26, signal=9)
    
    # ATR on candle data
    atr_calc = ATRCalculator(backend)
    atr_result = atr_calc.compute_atr(ohlc['high'], ohlc['low'], ohlc['close'], period=14)
    
    # Swing points on candle data
    swing_detector = SwingPointDetector(backend)
    swings = swing_detector.detect_swings(ohlc['high'], ohlc['low'], lookback=15)
    
    # 6. Convert all results to DataFrames
    # MACD (tick-level data)
    macd_df = converter.macd_to_dataframe(macd_result, metadata, prefix='tick_')
    
    # Create candle metadata
    candle_metadata = DataFrameMetadata(
        index=df.index[:n_candles],
        columns=['open', 'high', 'low', 'close'],
        dtypes={col: 'float64' for col in ['open', 'high', 'low', 'close']}
    )
    
    # Candles, ATR, and Swings (candle-level data)
    candles_df = converter.candles_to_dataframe(ohlc, candle_metadata, prefix='5min_')
    atr_df = converter.atr_to_dataframe(atr_result, candle_metadata, prefix='5min_')
    swings_df = converter.swings_to_dataframe(swings, candle_metadata, prefix='5min_')
    
    # 7. Display results summary
    print(f"2. Generated {n_candles} candles from {len(prices)} ticks")
    print(f"3. MACD DataFrame: {macd_df.shape}")
    print(f"4. Candles DataFrame: {candles_df.shape}")
    print(f"5. ATR DataFrame: {atr_df.shape}")
    print(f"6. Swings DataFrame: {swings_df.shape}")
    
    # 8. Combine candle-level indicators
    candle_indicators = pd.concat([candles_df, atr_df, swings_df], axis=1)
    
    print(f"\n7. Combined candle indicators: {candle_indicators.shape}")
    print(f"   Columns: {list(candle_indicators.columns)}")
    
    print("\n8. Sample of final candle indicators:")
    print(candle_indicators.head())
    
    print(f"\n9. MACD tick indicators columns: {list(macd_df.columns)}")
    print("   Sample MACD values:")
    print(macd_df.head())
    
    return {
        'raw_data': df,
        'macd_tick': macd_df,
        'candle_indicators': candle_indicators,
        'metadata': {'tick_level': metadata, 'candle_level': candle_metadata}
    }


def main():
    """Run all examples"""
    print("IndicatorResultConverter Usage Examples")
    print("=" * 60)
    print("Demonstrating seamless array-to-DataFrame conversion")
    print("for all technical indicator types.\n")
    
    try:
        # Run examples
        example_1_basic_macd_conversion()
        example_2_prefixed_indicators()
        example_3_atr_conversion()
        example_4_candle_and_swing_conversion()
        example_5_generic_array_conversion()
        final_results = example_6_complete_pipeline()
        
        print("\n" + "=" * 60)
        print("SUCCESS: All examples completed successfully!")
        print("=" * 60)
        print("Key Benefits Demonstrated:")
        print("✅ Seamless array → DataFrame conversion")
        print("✅ Automatic CPU/GPU array handling")
        print("✅ Proper metadata preservation")
        print("✅ Column naming with prefixes")
        print("✅ Integration with existing GPUArrayConverter")
        print("✅ Complete data processing pipeline")
        
        return final_results
        
    except Exception as e:
        print(f"\n❌ Error in examples: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    results = main()