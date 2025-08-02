#!/usr/bin/env python3
"""Quick GPU Memory Optimization Test"""

import sys
import os
import time
import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from technical_indicators.unified_pipeline import UnifiedTechnicalIndicatorsPipeline

def quick_test():
    print("⚡ QUICK GPU MEMORY OPTIMIZATION TEST")
    print("=" * 50)
    
    try:
        import cupy as cp
        
        # Check GPU memory
        free_mem, total_mem = cp.cuda.runtime.memGetInfo()
        print(f"GPU Memory: {total_mem/1e9:.1f} GB total, {free_mem/1e9:.1f} GB free")
        
        # Create 1M point dataset
        size = 1_000_000
        print(f"\nCreating {size:,} data points...")
        
        data = pd.DataFrame({
            'open': np.random.randn(size).cumsum() + 100,
            'high': np.random.randn(size).cumsum() + 105,
            'low': np.random.randn(size).cumsum() + 95,
            'close': np.random.randn(size).cumsum() + 100
        })
        
        print(f"Data created: {data.memory_usage(deep=True).sum()/1e6:.1f} MB")
        
        # Test optimized pipeline
        print("\nTesting optimized GPU pipeline...")
        pipeline = UnifiedTechnicalIndicatorsPipeline(backend='cupy')
        
        # Measure memory usage
        free_before, _ = cp.cuda.runtime.memGetInfo()
        start_time = time.perf_counter()
        
        result = pipeline.compute_indicators(data, ['macd'])
        
        end_time = time.perf_counter()
        free_after, _ = cp.cuda.runtime.memGetInfo()
        
        # Results
        memory_used = (free_before - free_after) / 1e9
        duration = end_time - start_time
        throughput = size / duration
        memory_efficiency = memory_used / (total_mem / 1e9) * 100
        
        print(f"\n✅ SUCCESS!")
        print(f"Time: {duration:.2f}s")
        print(f"Throughput: {throughput:,.0f} points/sec")
        print(f"GPU Memory Used: {memory_used:.2f} GB")
        print(f"Memory Efficiency: {memory_efficiency:.1f}% of total GPU")
        print(f"Result Shape: {result.shape}")
        
        if memory_efficiency > 5:
            print(f"🎯 Good memory utilization!")
        else:
            print(f"⚠️ Memory could be better utilized")
            
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    quick_test()