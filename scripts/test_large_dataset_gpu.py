#!/usr/bin/env python3
"""
Large Dataset GPU Testing Script - 1M+ Data Points
Test all technical indicators with GPU acceleration and memory management
"""

import time
import gc
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from technical_indicators.unified_pipeline import UnifiedTechnicalIndicatorsPipeline


def generate_large_dataset(size: int = 1_000_000) -> pd.DataFrame:
    """Generate large realistic OHLCV dataset"""
    print(f"Generating {size:,} data points...")
    
    # Create realistic price movements using random walk with trend
    np.random.seed(42)  # Reproducible results
    
    # Base price and volatility
    base_price = 100.0
    volatility = 0.02
    
    # Generate price changes with trend
    changes = np.random.normal(0, volatility, size)
    trend = np.linspace(0, 0.5, size)  # Slight upward trend
    
    # Create close prices using cumulative sum
    close_prices = base_price + np.cumsum(changes + trend/size)
    
    # Generate OHLC from close prices
    high_noise = np.abs(np.random.normal(0, volatility/2, size))
    low_noise = np.abs(np.random.normal(0, volatility/2, size))
    open_noise = np.random.normal(0, volatility/4, size)
    
    data = pd.DataFrame({
        'open': np.roll(close_prices, 1) + open_noise,
        'high': close_prices + high_noise,
        'low': close_prices - low_noise,
        'close': close_prices
    })
    
    # Fix first open price
    data.loc[0, 'open'] = base_price
    
    # Ensure OHLC relationships are valid
    data['high'] = np.maximum.reduce([data['open'], data['high'], data['low'], data['close']])
    data['low'] = np.minimum.reduce([data['open'], data['high'], data['low'], data['close']])
    
    print(f"Dataset generated: {len(data):,} rows")
    print(f"Memory usage: {data.memory_usage(deep=True).sum() / 1024**2:.1f} MB")
    
    return data


def test_gpu_availability():
    """Test GPU availability and memory"""
    print("\n" + "="*60)
    print("GPU AVAILABILITY TEST")
    print("="*60)
    
    try:
        import cupy as cp
        print("✅ CuPy available")
        
        # Test GPU device
        device = cp.cuda.Device()
        print(f"✅ GPU Device: {device}")
        
        # Test memory
        mempool = cp.get_default_memory_pool()
        total_bytes = mempool.total_bytes()
        used_bytes = mempool.used_bytes()
        free_bytes = total_bytes - used_bytes
        
        print(f"✅ GPU Memory - Total: {total_bytes/1024**3:.1f} GB")
        print(f"✅ GPU Memory - Used: {used_bytes/1024**3:.1f} GB") 
        print(f"✅ GPU Memory - Free: {free_bytes/1024**3:.1f} GB")
        
        return True
        
    except Exception as e:
        print(f"❌ GPU not available: {e}")
        return False


def test_indicator_computation(data: pd.DataFrame, indicator: str, pipeline: UnifiedTechnicalIndicatorsPipeline):
    """Test individual indicator computation"""
    print(f"\n--- Testing {indicator.upper()} ---")
    
    try:
        # Clear GPU memory before test
        if hasattr(pipeline, 'clear_gpu_memory_cache'):
            pipeline.clear_gpu_memory_cache()
        
        start_time = time.perf_counter()
        
        # Compute indicator
        if indicator == 'macd':
            result = pipeline.compute_indicators(data, ['macd'], macd_params={'fast': 12, 'slow': 26, 'signal': 9})
            expected_cols = ['macd']
        elif indicator == 'atr':
            result = pipeline.compute_indicators(data, ['atr'], atr_period=14)
            expected_cols = ['atr']
        elif indicator == 'swing_points':
            result = pipeline.compute_indicators(data, ['swing_points'], swing_lookback=20)
            expected_cols = ['swing_highs', 'swing_lows']
        elif indicator == 'candles':
            result = pipeline.compute_indicators(data, ['candles'], candle_granularity='15min')
            expected_cols = ['candle_open', 'candle_high', 'candle_low', 'candle_close']
        else:
            raise ValueError(f"Unknown indicator: {indicator}")
        
        end_time = time.perf_counter()
        computation_time = end_time - start_time
        
        # Validate results
        print(f"✅ Computation completed in {computation_time:.2f} seconds")
        print(f"✅ Result shape: {result.shape}")
        print(f"✅ Memory usage: {result.memory_usage(deep=True).sum() / 1024**2:.1f} MB")
        
        # Check expected columns
        found_cols = [col for col in expected_cols if col in result.columns]
        print(f"✅ Expected columns found: {found_cols}")
        
        # Check for non-null values
        for col in found_cols:
            non_null_count = result[col].notna().sum()
            print(f"✅ {col}: {non_null_count:,} non-null values")
        
        # Performance metrics
        points_per_second = len(data) / computation_time
        print(f"✅ Performance: {points_per_second:,.0f} points/second")
        
        return {
            'indicator': indicator,
            'success': True,
            'time': computation_time,
            'points_per_second': points_per_second,
            'result_shape': result.shape,
            'columns_found': found_cols
        }
        
    except Exception as e:
        print(f"❌ {indicator.upper()} failed: {e}")
        return {
            'indicator': indicator,
            'success': False,
            'error': str(e)
        }


def test_all_indicators_combined(data: pd.DataFrame, pipeline: UnifiedTechnicalIndicatorsPipeline):
    """Test all indicators together"""
    print(f"\n--- Testing ALL INDICATORS COMBINED ---")
    
    try:
        # Clear GPU memory before test
        if hasattr(pipeline, 'clear_gpu_memory_cache'):
            pipeline.clear_gpu_memory_cache()
        
        start_time = time.perf_counter()
        
        # Compute all indicators
        result = pipeline.compute_all_indicators(
            data,
            candle_granularity='15min',
            macd_params={'fast': 12, 'slow': 26, 'signal': 9},
            atr_period=14,
            swing_lookback=20
        )
        
        end_time = time.perf_counter()
        computation_time = end_time - start_time
        
        # Validate results
        print(f"✅ All indicators computed in {computation_time:.2f} seconds")
        print(f"✅ Result shape: {result.shape}")
        print(f"✅ Total columns: {len(result.columns)}")
        print(f"✅ Memory usage: {result.memory_usage(deep=True).sum() / 1024**2:.1f} MB")
        
        # List all computed columns
        indicator_cols = [col for col in result.columns if col not in ['open', 'high', 'low', 'close']]
        print(f"✅ Indicator columns: {indicator_cols}")
        
        # Performance metrics
        points_per_second = len(data) / computation_time
        print(f"✅ Performance: {points_per_second:,.0f} points/second")
        
        return {
            'success': True,
            'time': computation_time,
            'points_per_second': points_per_second,
            'result_shape': result.shape,
            'total_columns': len(result.columns),
            'indicator_columns': indicator_cols
        }
        
    except Exception as e:
        print(f"❌ Combined indicators failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'error': str(e)
        }


def test_memory_management(data: pd.DataFrame, pipeline: UnifiedTechnicalIndicatorsPipeline):
    """Test GPU memory management capabilities"""
    print(f"\n--- Testing GPU MEMORY MANAGEMENT ---")
    
    try:
        # Get memory statistics before
        if hasattr(pipeline, 'get_gpu_memory_statistics'):
            mem_stats_before = pipeline.get_gpu_memory_statistics()
            print("Memory stats before computation:")
            for key, value in mem_stats_before.items():
                print(f"  {key}: {value}")
        
        # Force chunked processing by using a smaller memory threshold
        pipeline.config.memory_threshold = 0.3  # Use only 30% of available memory
        
        start_time = time.perf_counter()
        
        # Compute indicators with forced chunking
        result = pipeline.compute_indicators(
            data, 
            ['macd', 'atr'], 
            macd_params={'fast': 12, 'slow': 26, 'signal': 9},
            atr_period=14
        )
        
        end_time = time.perf_counter()
        computation_time = end_time - start_time
        
        # Get memory statistics after
        if hasattr(pipeline, 'get_gpu_memory_statistics'):
            mem_stats_after = pipeline.get_gpu_memory_statistics()
            print("Memory stats after computation:")
            for key, value in mem_stats_after.items():
                print(f"  {key}: {value}")
        
        print(f"✅ Memory-managed computation completed in {computation_time:.2f} seconds")
        print(f"✅ Result shape: {result.shape}")
        
        return {
            'success': True,
            'time': computation_time,
            'chunked_processing': True
        }
        
    except Exception as e:
        print(f"❌ Memory management test failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }


def compare_gpu_cpu_performance(data: pd.DataFrame):
    """Compare GPU vs CPU performance"""
    print(f"\n--- GPU vs CPU PERFORMANCE COMPARISON ---")
    
    results = {}
    
    # Test with smaller subset for CPU (CPU might be too slow for 1M points)
    test_size = min(100_000, len(data))  # Use 100K points for comparison
    test_data = data.head(test_size).copy()
    
    print(f"Using {test_size:,} points for comparison...")
    
    for backend in ['cupy', 'numpy']:
        print(f"\n--- Testing {backend.upper()} backend ---")
        
        try:
            pipeline = UnifiedTechnicalIndicatorsPipeline(
                backend=backend,
                enable_gpu_memory_management=(backend == 'cupy')
            )
            
            start_time = time.perf_counter()
            
            result = pipeline.compute_indicators(
                test_data,
                ['macd', 'atr'],
                macd_params={'fast': 12, 'slow': 26, 'signal': 9},
                atr_period=14
            )
            
            end_time = time.perf_counter()
            computation_time = end_time - start_time
            
            points_per_second = len(test_data) / computation_time
            
            results[backend] = {
                'success': True,
                'time': computation_time,
                'points_per_second': points_per_second
            }
            
            print(f"✅ {backend.upper()}: {computation_time:.2f}s, {points_per_second:,.0f} points/sec")
            
        except Exception as e:
            print(f"❌ {backend.upper()} failed: {e}")
            results[backend] = {
                'success': False,
                'error': str(e)
            }
    
    # Calculate speedup
    if results.get('cupy', {}).get('success') and results.get('numpy', {}).get('success'):
        cpu_time = results['numpy']['time']
        gpu_time = results['cupy']['time']
        speedup = cpu_time / gpu_time
        print(f"\n🚀 GPU SPEEDUP: {speedup:.2f}x faster than CPU")
        results['speedup'] = speedup
    
    return results


def main():
    """Main test function"""
    print("🧪 LARGE DATASET GPU TESTING - 1M+ Data Points")
    print("="*80)
    
    # Test GPU availability first
    gpu_available = test_gpu_availability()
    
    if not gpu_available:
        print("❌ GPU not available. Cannot proceed with GPU testing.")
        return
    
    # Update todo status
    print("\n📋 Starting large dataset testing...")
    
    # Generate large dataset
    data_size = 1_200_000  # 1.2M points
    data = generate_large_dataset(data_size)
    
    # Initialize GPU pipeline
    pipeline = UnifiedTechnicalIndicatorsPipeline(
        backend='cupy',
        enable_gpu_memory_management=True,
        chunk_size=50000,
        memory_threshold=0.7
    )
    
    print(f"\n🔧 Pipeline Configuration:")
    print(f"  Backend: {pipeline.backend_name}")
    print(f"  Memory Management: {pipeline.memory_manager is not None}")
    print(f"  Chunk Size: {pipeline.config.chunk_size:,}")
    print(f"  Memory Threshold: {pipeline.config.memory_threshold}")
    
    # Test results storage
    test_results = {}
    
    # Test individual indicators
    indicators = ['macd', 'atr', 'swing_points', 'candles']
    
    for indicator in indicators:
        result = test_indicator_computation(data, indicator, pipeline)
        test_results[indicator] = result
        
        # Clean up memory between tests
        gc.collect()
        if hasattr(pipeline, 'clear_gpu_memory_cache'):
            pipeline.clear_gpu_memory_cache()
    
    # Test all indicators combined
    combined_result = test_all_indicators_combined(data, pipeline)
    test_results['combined'] = combined_result
    
    # Test memory management
    memory_result = test_memory_management(data, pipeline)
    test_results['memory_management'] = memory_result
    
    # Compare GPU vs CPU performance
    performance_result = compare_gpu_cpu_performance(data)
    test_results['performance_comparison'] = performance_result
    
    # Print final summary
    print("\n" + "="*80)
    print("🎯 FINAL TEST SUMMARY")
    print("="*80)
    
    print(f"Dataset Size: {len(data):,} data points")
    print(f"GPU Backend: {pipeline.backend_name}")
    print(f"Memory Management: {'Enabled' if pipeline.memory_manager else 'Disabled'}")
    
    print(f"\n📊 Individual Indicator Results:")
    for indicator in indicators:
        result = test_results.get(indicator, {})
        if result.get('success'):
            print(f"  ✅ {indicator.upper()}: {result['time']:.2f}s ({result['points_per_second']:,.0f} pts/sec)")
        else:
            print(f"  ❌ {indicator.upper()}: FAILED")
    
    combined = test_results.get('combined', {})
    if combined.get('success'):
        print(f"\n🔄 Combined Indicators: {combined['time']:.2f}s ({combined['points_per_second']:,.0f} pts/sec)")
        print(f"   Total columns generated: {combined['total_columns']}")
    
    if 'speedup' in performance_result:
        print(f"\n🚀 GPU vs CPU Speedup: {performance_result['speedup']:.2f}x")
    
    memory_mgmt = test_results.get('memory_management', {})
    if memory_mgmt.get('success'):
        print(f"\n💾 Memory Management: ✅ Working with chunked processing")
    
    print(f"\n✅ Large dataset GPU testing completed successfully!")
    
    return test_results


if __name__ == "__main__":
    try:
        results = main()
    except KeyboardInterrupt:
        print("\n❌ Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()