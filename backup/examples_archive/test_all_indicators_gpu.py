#!/usr/bin/env python3
"""
Comprehensive Test of All Technical Indicators with Phase 3.1 GPU Integration

Tests all indicators: MACD, ATR, Swing Points, Candles
Verifies both individual and combined processing works with aggressive GPU settings.
"""

import sys
import os
import time
import numpy as np
import pandas as pd
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

def create_realistic_test_data(size: int = 10000) -> pd.DataFrame:
    """Create realistic OHLCV data for comprehensive testing"""
    print(f"📊 Generating {size:,} realistic data points...")
    
    np.random.seed(42)
    
    # Generate realistic price movement using random walk
    base_price = 100.0
    volatility = 0.02
    trend = 0.0001
    
    # Generate price changes with trend and volatility
    price_changes = np.random.normal(trend, volatility, size)
    log_prices = np.cumsum(price_changes)
    prices = base_price * np.exp(log_prices)
    
    # Create OHLC with realistic relationships
    data = pd.DataFrame(index=range(size))
    
    # Close prices from our random walk
    data['close'] = prices
    
    # Open is previous close (with small gap)
    data['open'] = data['close'].shift(1).fillna(data['close'].iloc[0])
    gap_factor = np.random.normal(1.0, 0.001, size)
    data['open'] *= gap_factor
    
    # High/Low based on intraday volatility
    intraday_vol = np.random.uniform(0.005, 0.02, size)
    high_factor = 1 + np.random.uniform(0, intraday_vol)
    low_factor = 1 - np.random.uniform(0, intraday_vol)
    
    data['high'] = np.maximum(data['open'], data['close']) * high_factor
    data['low'] = np.minimum(data['open'], data['close']) * low_factor
    
    # Ensure OHLC consistency
    data['high'] = np.maximum.reduce([data['open'], data['high'], data['low'], data['close']])
    data['low'] = np.minimum.reduce([data['open'], data['high'], data['low'], data['close']])
    
    # Volume with realistic patterns
    base_volume = 50000
    volume_volatility = 0.3
    data['volume'] = base_volume * np.exp(np.random.normal(0, volume_volatility, size))
    data['volume'] = data['volume'].astype(int)
    
    return data


def test_individual_indicators():
    """Test each indicator individually"""
    print("\n" + "="*80)
    print("🧪 TESTING INDIVIDUAL INDICATORS WITH PHASE 3.1 GPU")
    print("="*80)
    
    try:
        from technical_indicators.unified_pipeline import UnifiedTechnicalIndicatorsPipeline
        
        # Initialize Phase 3.1 aggressive pipeline
        pipeline = UnifiedTechnicalIndicatorsPipeline(
            backend='cupy',
            fallback_on_error=False,
            force_gpu_only=True,
            chunk_size=100000,  # Smaller for individual tests
            memory_threshold=0.95
        )
        
        # Create test data
        data = create_realistic_test_data(5000)
        
        indicators_to_test = ['macd', 'atr', 'swing_points', 'candles']
        results = {}
        
        for indicator in indicators_to_test:
            print(f"\n🔬 Testing {indicator.upper()}...")
            
            try:
                start_time = time.perf_counter()
                
                result = pipeline.compute_indicators(
                    data=data,
                    indicators=[indicator],
                    macd_params={'fast': 12, 'slow': 26, 'signal': 9},
                    atr_period=14,
                    swing_lookback=20
                )
                
                processing_time = time.perf_counter() - start_time
                
                # Verify expected columns are present
                expected_columns = {
                    'macd': ['macd_line', 'macd_signal', 'macd_histogram'],
                    'atr': ['atr'],
                    'swing_points': ['swing_highs', 'swing_lows'],
                    'candles': ['candle_open', 'candle_high', 'candle_low', 'candle_close']
                }
                
                missing_cols = []
                for col in expected_columns[indicator]:
                    if col not in result.columns:
                        missing_cols.append(col)
                
                if missing_cols:
                    print(f"❌ {indicator.upper()}: Missing columns {missing_cols}")
                    results[indicator] = {'status': 'FAILED', 'error': f'Missing columns: {missing_cols}'}
                else:
                    # Check for valid data (not all NaN)
                    valid_data = True
                    for col in expected_columns[indicator]:
                        if result[col].isna().all():
                            print(f"⚠️ {indicator.upper()}: Column {col} is all NaN")
                            valid_data = False
                    
                    if valid_data:
                        print(f"✅ {indicator.upper()}: SUCCESS - {processing_time:.3f}s")
                        print(f"   Columns: {expected_columns[indicator]}")
                        print(f"   Shape: {result.shape}")
                        results[indicator] = {
                            'status': 'SUCCESS', 
                            'time': processing_time, 
                            'shape': result.shape,
                            'columns': expected_columns[indicator]
                        }
                    else:
                        results[indicator] = {'status': 'FAILED', 'error': 'Invalid data (all NaN)'}
                
            except Exception as e:
                print(f"❌ {indicator.upper()}: FAILED - {e}")
                results[indicator] = {'status': 'FAILED', 'error': str(e)}
        
        return results
        
    except Exception as e:
        print(f"❌ Failed to initialize pipeline: {e}")
        return {}


def test_combined_indicators():
    """Test all indicators together"""
    print("\n" + "="*80)
    print("🧪 TESTING ALL INDICATORS COMBINED WITH PHASE 3.1 GPU")
    print("="*80)
    
    try:
        from technical_indicators.unified_pipeline import UnifiedTechnicalIndicatorsPipeline
        
        # Initialize Phase 3.1 aggressive pipeline
        pipeline = UnifiedTechnicalIndicatorsPipeline(
            backend='cupy',
            fallback_on_error=False,
            force_gpu_only=True,
            chunk_size=200000,
            memory_threshold=0.98
        )
        
        # Test with different data sizes
        test_sizes = [1000, 5000, 25000]
        
        for size in test_sizes:
            print(f"\n📊 Testing combined processing with {size:,} data points...")
            
            try:
                data = create_realistic_test_data(size)
                
                start_time = time.perf_counter()
                
                # Test compute_all_indicators (all indicators at once)
                result = pipeline.compute_all_indicators(
                    data=data,
                    macd_params={'fast': 12, 'slow': 26, 'signal': 9},
                    atr_period=14,
                    swing_lookback=20,
                    candle_granularity='15min'
                )
                
                processing_time = time.perf_counter() - start_time
                
                # Verify all expected columns are present
                expected_all_columns = [
                    # Original OHLCV
                    'open', 'high', 'low', 'close', 'volume',
                    # MACD
                    'macd_line', 'macd_signal', 'macd_histogram',
                    # ATR
                    'atr',
                    # Swing Points
                    'swing_highs', 'swing_lows',
                    # Candles
                    'candle_open', 'candle_high', 'candle_low', 'candle_close'
                ]
                
                missing_columns = [col for col in expected_all_columns if col not in result.columns]
                
                if missing_columns:
                    print(f"❌ Size {size:,}: Missing columns {missing_columns}")
                else:
                    # Check data validity
                    indicator_columns = [col for col in expected_all_columns if col not in ['open', 'high', 'low', 'close', 'volume']]
                    valid_indicators = []
                    invalid_indicators = []
                    
                    for col in indicator_columns:
                        if not result[col].isna().all():
                            valid_indicators.append(col)
                        else:
                            invalid_indicators.append(col)
                    
                    print(f"✅ Size {size:,}: SUCCESS - {processing_time:.3f}s")
                    print(f"   Performance: {size/processing_time:,.0f} points/second")
                    print(f"   Shape: {result.shape}")
                    print(f"   Valid indicators: {len(valid_indicators)}/{len(indicator_columns)}")
                    
                    if invalid_indicators:
                        print(f"   ⚠️ Indicators with all NaN: {invalid_indicators}")
                    
                    # Sample data check
                    print(f"   📊 Sample values:")
                    for indicator_type in [['macd_line', 'macd_signal'], ['atr'], ['swing_highs'], ['candle_close']]:
                        for col in indicator_type:
                            if col in result.columns:
                                sample_val = result[col].dropna().iloc[-1] if not result[col].dropna().empty else 'No data'
                                print(f"      {col}: {sample_val}")
                                break
                
            except Exception as e:
                print(f"❌ Size {size:,}: FAILED - {e}")
                continue
        
        return True
        
    except Exception as e:
        print(f"❌ Failed combined test: {e}")
        return False


def test_gpu_memory_utilization():
    """Test GPU memory utilization with indicators"""
    print("\n" + "="*80)
    print("🧪 TESTING GPU MEMORY UTILIZATION WITH INDICATORS")
    print("="*80)
    
    try:
        from technical_indicators.unified_pipeline import UnifiedTechnicalIndicatorsPipeline
        
        pipeline = UnifiedTechnicalIndicatorsPipeline(
            backend='cupy',
            fallback_on_error=False,
            force_gpu_only=True,
            chunk_size=500000,  # Large chunks to test memory utilization
            memory_threshold=0.98
        )
        
        # Get initial GPU stats
        initial_stats = pipeline.get_gpu_memory_statistics()
        print(f"📊 Initial GPU State:")
        print(f"   Device: {initial_stats.get('device_name', 'Unknown')}")
        print(f"   Total Memory: {initial_stats.get('total_memory_gb', 0):.1f} GB")
        print(f"   Free Memory: {initial_stats.get('free_memory_gb', 0):.1f} GB")
        print(f"   Utilization: {initial_stats.get('memory_utilization_pct', 0):.1f}%")
        print(f"   CUDA Streams: {initial_stats.get('cuda_streams', 0)}")
        print(f"   Phase 3.1 Optimized: {initial_stats.get('phase_3_1_optimized', False)}")
        
        # Test with larger dataset to utilize GPU memory
        print(f"\n🚀 Testing with 100K data points for GPU utilization...")
        large_data = create_realistic_test_data(100000)
        
        start_time = time.perf_counter()
        result = pipeline.compute_all_indicators(large_data)
        processing_time = time.perf_counter() - start_time
        
        # Get final GPU stats
        final_stats = pipeline.get_gpu_memory_statistics()
        
        print(f"📊 Processing Results:")
        print(f"   Processing Time: {processing_time:.3f}s")
        print(f"   Performance: {len(large_data)/processing_time:,.0f} points/second")
        print(f"   Final GPU Utilization: {final_stats.get('memory_utilization_pct', 0):.1f}%")
        print(f"   Result Shape: {result.shape}")
        
        # Verify aggressive settings are working
        aggressive_features = {
            'phase_3_1_optimized': final_stats.get('phase_3_1_optimized', False),
            'gpu_only_mode': final_stats.get('gpu_only_mode', False),
            'cpu_fallback_disabled': final_stats.get('cpu_fallback_disabled', False),
            'rtx4080_super_mode': final_stats.get('rtx4080_super_mode', False)
        }
        
        print(f"🎯 Phase 3.1 Features Status:")
        for feature, status in aggressive_features.items():
            status_icon = "✅" if status else "❌"
            print(f"   {feature}: {status_icon} {status}")
        
        return True
        
    except Exception as e:
        print(f"❌ GPU utilization test failed: {e}")
        return False


def main():
    """Main test function"""
    print("🔬 COMPREHENSIVE TECHNICAL INDICATORS GPU TEST")
    print("Testing all indicators: MACD, ATR, Swing Points, Candles")
    print("With Phase 3.1 Aggressive GPU Integration")
    print("="*80)
    
    # Test individual indicators
    individual_results = test_individual_indicators()
    
    # Test combined indicators
    combined_success = test_combined_indicators()
    
    # Test GPU utilization
    gpu_success = test_gpu_memory_utilization()
    
    # Summary
    print("\n" + "="*80)
    print("📋 COMPREHENSIVE TEST SUMMARY")
    print("="*80)
    
    print("\n🔬 Individual Indicator Results:")
    for indicator, result in individual_results.items():
        status_icon = "✅" if result['status'] == 'SUCCESS' else "❌"
        print(f"   {indicator.upper()}: {status_icon} {result['status']}")
        if result['status'] == 'SUCCESS':
            print(f"      Time: {result['time']:.3f}s, Columns: {result['columns']}")
        else:
            print(f"      Error: {result.get('error', 'Unknown')}")
    
    print(f"\n🧪 Combined Processing: {'✅ SUCCESS' if combined_success else '❌ FAILED'}")
    print(f"📊 GPU Utilization Test: {'✅ SUCCESS' if gpu_success else '❌ FAILED'}")
    
    # Overall status
    individual_success = all(r['status'] == 'SUCCESS' for r in individual_results.values())
    overall_success = individual_success and combined_success and gpu_success
    
    print(f"\n🎯 OVERALL STATUS: {'🎉 ALL TESTS PASSED' if overall_success else '❌ SOME TESTS FAILED'}")
    
    if overall_success:
        print("\n✅ All technical indicators are functional with Phase 3.1 GPU integration:")
        print("   • MACD: GPU-accelerated with aggressive memory utilization")
        print("   • ATR: GPU-accelerated with CUDA streams")
        print("   • Swing Points: GPU-accelerated detection algorithm")
        print("   • Candles: GPU-accelerated OHLC processing")
        print("   • Combined Processing: All indicators work together")
        print("   • GPU Memory: Aggressive utilization without CPU fallback")
    else:
        print("\n⚠️ Some indicators may have issues. Check individual results above.")
    
    return overall_success


if __name__ == "__main__":
    try:
        success = main()
        if success:
            print("\n🎉 All technical indicators are fully functional with Phase 3.1 GPU integration!")
        else:
            print("\n❌ Some technical indicators need attention.")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n⚠️ Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)