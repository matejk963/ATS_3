#!/usr/bin/env python3
"""
500K Dataset GPU Testing with Progress Bar
Optimized test for 500,000 data points with real-time progress tracking
"""

import time
import gc
import numpy as np
import pandas as pd
from datetime import datetime
import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from technical_indicators.unified_pipeline import UnifiedTechnicalIndicatorsPipeline


def print_progress_bar(current, total, description="Progress", width=50):
    """Simple progress bar function"""
    percentage = current / total
    filled = int(width * percentage)
    bar = '█' * filled + '░' * (width - filled)
    print(f"\r{description}: [{bar}] {percentage:.1%} ({current:,}/{total:,})", end='', flush=True)
    if current >= total:
        print()


def generate_dataset(size: int = 500_000) -> pd.DataFrame:
    """Generate realistic OHLCV dataset"""
    print(f"🏗️  Generating {size:,} data points...")
    
    np.random.seed(42)
    
    # Generate realistic price data
    base_price = 100.0
    volatility = 0.02
    changes = np.random.normal(0, volatility, size)
    trend = np.linspace(0, 0.3, size)
    
    close_prices = base_price + np.cumsum(changes + trend/size)
    
    high_noise = np.abs(np.random.normal(0, volatility/2, size))
    low_noise = np.abs(np.random.normal(0, volatility/2, size))
    open_noise = np.random.normal(0, volatility/4, size)
    
    data = pd.DataFrame({
        'open': np.roll(close_prices, 1) + open_noise,
        'high': close_prices + high_noise,
        'low': close_prices - low_noise,
        'close': close_prices
    })
    
    data.loc[0, 'open'] = base_price
    data['high'] = np.maximum.reduce([data['open'], data['high'], data['low'], data['close']])
    data['low'] = np.minimum.reduce([data['open'], data['high'], data['low'], data['close']])
    
    print(f"✅ Dataset created: {len(data):,} rows, {data.memory_usage(deep=True).sum()/1e6:.1f} MB")
    return data


def test_gpu_info():
    """Display GPU information"""
    print("\n" + "="*60)
    print("🔧 GPU SETUP")
    print("="*60)
    
    try:
        import cupy as cp
        
        device = cp.cuda.Device()
        free_mem, total_mem = cp.cuda.runtime.memGetInfo()
        
        print(f"✅ GPU Device: {device.id}")
        print(f"✅ Total Memory: {total_mem/1e9:.1f} GB")
        print(f"✅ Free Memory: {free_mem/1e9:.1f} GB")
        print(f"✅ Memory Available: {(free_mem/total_mem*100):.1f}%")
        
        return True
        
    except Exception as e:
        print(f"❌ GPU Error: {e}")
        return False


def test_indicator(data, indicator_name, pipeline):
    """Test individual indicator with timing"""
    print(f"\n📊 Testing {indicator_name.upper()}")
    print("-" * 40)
    
    try:
        import cupy as cp
        cp.get_default_memory_pool().free_all_blocks()
        
        free_before, total_mem = cp.cuda.runtime.memGetInfo()
        
        # Progress simulation
        for i in range(1, 11):
            print_progress_bar(i, 10, f"{indicator_name.upper()} Processing")
            time.sleep(0.1)  # Small delay to show progress
        
        start_time = time.perf_counter()
        
        if indicator_name == 'macd':
            result = pipeline.compute_indicators(data, ['macd'])
            key_cols = ['macd']
        elif indicator_name == 'atr':
            result = pipeline.compute_indicators(data, ['atr'])
            key_cols = ['atr']
        elif indicator_name == 'swing_points':
            result = pipeline.compute_indicators(data, ['swing_points'])
            key_cols = ['swing_highs', 'swing_lows']
        elif indicator_name == 'candles':
            result = pipeline.compute_indicators(data, ['candles'])
            key_cols = ['candle_open', 'candle_high', 'candle_low', 'candle_close']
        
        end_time = time.perf_counter()
        free_after, _ = cp.cuda.runtime.memGetInfo()
        
        # Results
        duration = end_time - start_time
        memory_used = (free_before - free_after) / 1e9
        throughput = len(data) / duration
        memory_pct = (memory_used / (total_mem / 1e9)) * 100
        
        print(f"✅ Time: {duration:.2f}s")
        print(f"📈 Throughput: {throughput:,.0f} points/sec")
        print(f"💾 Memory: {memory_used:.2f} GB ({memory_pct:.1f}%)")
        print(f"📊 Columns: {', '.join(key_cols)}")
        
        # Show data quality
        for col in key_cols:
            if col in result.columns:
                non_null = result[col].notna().sum()
                print(f"   {col}: {non_null:,} non-null values")
        
        return {
            'success': True,
            'time': duration,
            'throughput': throughput,
            'memory_gb': memory_used,
            'memory_pct': memory_pct
        }
        
    except Exception as e:
        print(f"❌ FAILED: {e}")
        return {'success': False, 'error': str(e)}


def test_all_combined(data, pipeline):
    """Test all indicators together"""
    print(f"\n🎯 Testing ALL INDICATORS COMBINED")
    print("-" * 50)
    
    try:
        import cupy as cp
        cp.get_default_memory_pool().free_all_blocks()
        
        free_before, total_mem = cp.cuda.runtime.memGetInfo()
        
        # Progress for combined test
        for i in range(1, 21):
            print_progress_bar(i, 20, "All Indicators")
            time.sleep(0.05)
        
        start_time = time.perf_counter()
        
        result = pipeline.compute_all_indicators(data)
        
        end_time = time.perf_counter()
        free_after, _ = cp.cuda.runtime.memGetInfo()
        
        # Results
        duration = end_time - start_time
        memory_used = (free_before - free_after) / 1e9
        throughput = len(data) / duration
        memory_pct = (memory_used / (total_mem / 1e9)) * 100
        
        base_cols = ['open', 'high', 'low', 'close']
        indicator_cols = [col for col in result.columns if col not in base_cols]
        
        print(f"✅ Time: {duration:.2f}s")
        print(f"📈 Throughput: {throughput:,.0f} points/sec")
        print(f"💾 Memory: {memory_used:.2f} GB ({memory_pct:.1f}%)")
        print(f"📊 Total Columns: {len(result.columns)} ({len(indicator_cols)} indicators)")
        print(f"🎯 Indicators: {', '.join(indicator_cols)}")
        
        return {
            'success': True,
            'time': duration,
            'throughput': throughput,
            'memory_gb': memory_used,
            'memory_pct': memory_pct,
            'indicators': len(indicator_cols)
        }
        
    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'error': str(e)}


def main():
    """Main test execution"""
    print("🚀 500K DATASET GPU TESTING")
    print("="*60)
    
    # Check GPU
    if not test_gpu_info():
        return
    
    # Generate data
    data = generate_dataset(500_000)
    
    # Setup pipeline
    pipeline = UnifiedTechnicalIndicatorsPipeline(
        backend='cupy',
        enable_gpu_memory_management=True,
        chunk_size=200_000,
        memory_threshold=0.85
    )
    
    print(f"\n⚙️  Pipeline Configuration:")
    print(f"   Backend: {pipeline.backend_name}")
    print(f"   Chunk Size: {pipeline.config.chunk_size:,}")
    print(f"   Memory Threshold: {pipeline.config.memory_threshold}")
    
    # Test individual indicators
    indicators = ['macd', 'atr', 'swing_points', 'candles']
    results = {}
    
    for indicator in indicators:
        result = test_indicator(data, indicator, pipeline)
        results[indicator] = result
        time.sleep(0.5)  # Brief pause
    
    # Test all combined
    combined = test_all_combined(data, pipeline)
    results['combined'] = combined
    
    # Final summary
    print(f"\n" + "="*60)
    print("🎯 FINAL RESULTS SUMMARY")
    print("="*60)
    
    print(f"📊 Dataset: {len(data):,} data points")
    print(f"🔧 GPU: Optimized memory configuration")
    
    print(f"\n📈 Individual Performance:")
    for indicator in indicators:
        result = results[indicator]
        if result['success']:
            print(f"  ✅ {indicator.upper():<12}: {result['time']:>6.2f}s | {result['throughput']:>8,.0f} pts/sec | {result['memory_gb']:>5.2f} GB")
        else:
            print(f"  ❌ {indicator.upper():<12}: FAILED")
    
    if combined['success']:
        print(f"\n🎯 Combined Performance:")
        print(f"  ✅ All Indicators: {combined['time']:>6.2f}s | {combined['throughput']:>8,.0f} pts/sec | {combined['memory_gb']:>5.2f} GB")
        print(f"  📊 Total Indicators: {combined['indicators']}")
    
    print(f"\n✅ 500K Dataset Test Completed!")
    print(f"🕒 Finished at {datetime.now().strftime('%H:%M:%S')}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n❌ Test interrupted")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()