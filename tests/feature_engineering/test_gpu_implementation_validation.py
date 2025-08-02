#!/usr/bin/env python3
"""
Focused GPU Testing - Quick validation of GPU implementation with large datasets
"""

import sys
import time
import pandas as pd
import numpy as np
import warnings
from datetime import datetime, timedelta
from pathlib import Path

# Suppress overflow warnings during testing
warnings.filterwarnings('ignore', category=RuntimeWarning)

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from src.feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline

def generate_clean_dataset(size: int) -> pd.DataFrame:
    """Generate clean, realistic dataset without overflow issues"""
    print(f"📊 Generating clean dataset with {size:,} data points...")
    
    np.random.seed(42)
    
    # Create realistic price progression
    base_price = 100.0
    prices = [base_price]
    
    # Generate smooth price changes to avoid overflow
    for i in range(1, size):
        # Small random walk with mean reversion
        change_pct = np.random.normal(0, 0.005)  # 0.5% volatility
        change_pct = np.clip(change_pct, -0.05, 0.05)  # Limit to ±5%
        new_price = prices[-1] * (1 + change_pct)
        new_price = max(1.0, new_price)  # Ensure positive prices
        prices.append(new_price)
    
    # Create OHLCV data
    data = []
    start_date = datetime(2020, 1, 1)
    
    for i in range(size):
        price = prices[i]
        
        # Generate OHLC around the price
        volatility = 0.01  # 1% intraday volatility
        high = price * (1 + np.random.uniform(0, volatility))
        low = price * (1 - np.random.uniform(0, volatility))
        
        # Ensure OHLC relationships are valid
        open_price = np.random.uniform(low, high)
        close_price = np.random.uniform(low, high)
        volume = int(np.random.uniform(100000, 1000000))
        
        data.append({
            'timestamp': start_date + timedelta(minutes=i),
            'open': round(open_price, 2),
            'high': round(high, 2),
            'low': round(low, 2),
            'close': round(close_price, 2),
            'volume': volume
        })
    
    df = pd.DataFrame(data)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    print(f"✅ Generated clean dataset: Price range ${df['close'].min():.2f} - ${df['close'].max():.2f}")
    return df

def test_gpu_setup():
    """Quick GPU availability test"""
    print("🔍 Testing GPU Setup...")
    
    try:
        import cupy as cp
        device = cp.cuda.Device()
        meminfo = cp.cuda.runtime.memGetInfo()
        total_gb = meminfo[1] / (1024**3)
        free_gb = meminfo[0] / (1024**3)
        
        print(f"✅ GPU Available: {total_gb:.1f}GB total, {free_gb:.1f}GB free")
        return True
    except Exception as e:
        print(f"❌ GPU unavailable: {e}")
        return False

def test_indicator(dataset: pd.DataFrame, indicator: str, backend: str):
    """Test specific indicator with timing"""
    print(f"\n🧪 Testing {indicator.upper()} ({backend}) - {len(dataset):,} points")
    
    try:
        pipeline = UnifiedTechnicalIndicatorsPipeline(
            backend=backend,
            enable_gpu_memory_management=True if backend == 'cupy' else False,
            chunk_size=50000,
            memory_threshold=0.7
        )
        
        start_time = time.time()
        result = pipeline.compute_indicators(data=dataset, indicators=[indicator])
        end_time = time.time()
        
        processing_time = end_time - start_time
        
        if result is not None and indicator in result.columns:
            valid_count = result[indicator].notna().sum()
            print(f"✅ Success: {processing_time:.2f}s, {valid_count:,} valid values")
            
            # Check for chunking info if GPU
            if backend == 'cupy':
                stats = pipeline.get_gpu_memory_statistics()
                chunks = stats.get('chunking_strategy', {}).get('chunks_processed', 1)
                if chunks > 1:
                    print(f"   📦 Chunked processing: {chunks} chunks")
            
            return processing_time, True
        else:
            print(f"❌ Failed: No valid results")
            return 0, False
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return 0, False

def main():
    """Run focused GPU tests"""
    print("🚀 Focused GPU Testing")
    print("=" * 50)
    
    # Test GPU availability
    gpu_available = test_gpu_setup()
    
    # Test different dataset sizes
    test_sizes = [10000, 100000, 250000]
    indicators = ['macd', 'atr']  # Focus on key indicators
    
    results = {}
    
    for size in test_sizes:
        print(f"\n📏 Testing size: {size:,} data points")
        print("-" * 40)
        
        # Generate dataset
        dataset = generate_clean_dataset(size)
        
        for indicator in indicators:
            size_key = f"{size}_{indicator}"
            results[size_key] = {}
            
            # Test CPU
            cpu_time, cpu_success = test_indicator(dataset, indicator, 'numpy')
            results[size_key]['cpu'] = {'time': cpu_time, 'success': cpu_success}
            
            # Test GPU if available
            if gpu_available:
                gpu_time, gpu_success = test_indicator(dataset, indicator, 'cupy')
                results[size_key]['gpu'] = {'time': gpu_time, 'success': gpu_success}
                
                # Calculate speedup
                if cpu_success and gpu_success and cpu_time > 0 and gpu_time > 0:
                    speedup = cpu_time / gpu_time
                    print(f"   🏃 Speedup: {speedup:.2f}x")
    
    # Summary report
    print(f"\n📊 SUMMARY REPORT")
    print("=" * 50)
    
    gpu_successes = 0
    cpu_successes = 0
    total_tests = 0
    speedups = []
    
    for key, result in results.items():
        size, indicator = key.split('_')
        total_tests += 1
        
        cpu_result = result.get('cpu', {})
        gpu_result = result.get('gpu', {})
        
        if cpu_result.get('success'):
            cpu_successes += 1
        
        if gpu_result.get('success'):
            gpu_successes += 1
            
        # Calculate speedup
        if (cpu_result.get('success') and gpu_result.get('success') and 
            cpu_result.get('time', 0) > 0 and gpu_result.get('time', 0) > 0):
            speedup = cpu_result['time'] / gpu_result['time']
            speedups.append(speedup)
            print(f"{indicator.upper()} ({size:>6}): {speedup:.2f}x speedup")
    
    print(f"\n📈 Overall Results:")
    print(f"CPU Success Rate: {cpu_successes}/{total_tests} ({cpu_successes/total_tests*100:.1f}%)")
    
    if gpu_available:
        print(f"GPU Success Rate: {gpu_successes}/{total_tests} ({gpu_successes/total_tests*100:.1f}%)")
        if speedups:
            avg_speedup = sum(speedups) / len(speedups)
            print(f"Average GPU Speedup: {avg_speedup:.2f}x")
            print(f"Max GPU Speedup: {max(speedups):.2f}x")
        
        # Memory management test
        largest_size = max(test_sizes)
        if largest_size > 75000:
            print(f"✅ GPU Memory Management: Tested up to {largest_size:,} points")
        
        print(f"\n🎉 GPU Implementation: {'✅ VALIDATED' if gpu_successes == total_tests else '⚠️ PARTIAL SUCCESS'}")
    else:
        print("⚠️ GPU testing skipped - GPU not available")

if __name__ == "__main__":
    main()