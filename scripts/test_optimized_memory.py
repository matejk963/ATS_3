#!/usr/bin/env python3
"""
Test Optimized GPU Memory Usage
"""

import sys
import os
import time
import numpy as np
import pandas as pd

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from technical_indicators.unified_pipeline import UnifiedTechnicalIndicatorsPipeline


def test_memory_utilization():
    """Test GPU memory utilization with optimized settings"""
    print("🚀 TESTING OPTIMIZED GPU MEMORY UTILIZATION")
    print("=" * 60)
    
    try:
        import cupy as cp
        
        # Get initial memory state
        free_mem, total_mem = cp.cuda.runtime.memGetInfo()
        print(f"GPU Total Memory: {total_mem / 1e9:.2f} GB")
        print(f"GPU Free Memory: {free_mem / 1e9:.2f} GB")
        
        # Test with progressively larger datasets
        test_sizes = [100_000, 500_000, 1_000_000, 2_000_000]
        
        for size in test_sizes:
            print(f"\n--- Testing {size:,} data points ---")
            
            # Create test data
            data = pd.DataFrame({
                'open': np.random.randn(size).cumsum() + 100,
                'high': np.random.randn(size).cumsum() + 105,
                'low': np.random.randn(size).cumsum() + 95,
                'close': np.random.randn(size).cumsum() + 100
            })
            
            print(f"Data size: {data.memory_usage(deep=True).sum() / 1e6:.1f} MB")
            
            # Test with optimized settings
            pipeline = UnifiedTechnicalIndicatorsPipeline(
                backend='cupy',
                enable_gpu_memory_management=True,
                chunk_size=200000,  # Optimized chunk size
                memory_threshold=0.85  # Optimized threshold
            )
            
            # Measure memory before computation
            free_before, _ = cp.cuda.runtime.memGetInfo()
            
            try:
                start_time = time.perf_counter()
                
                # Compute all indicators
                result = pipeline.compute_indicators(
                    data, 
                    ['macd', 'atr', 'swing_points'],
                    macd_params={'fast': 12, 'slow': 26, 'signal': 9},
                    atr_period=14,
                    swing_lookback=20
                )
                
                end_time = time.perf_counter()
                
                # Measure memory after computation
                free_after, _ = cp.cuda.runtime.memGetInfo()
                
                memory_used = (free_before - free_after) / 1e9  # GB
                computation_time = end_time - start_time
                throughput = size / computation_time
                memory_efficiency = memory_used / (total_mem / 1e9) * 100
                
                print(f"✅ Success!")
                print(f"  Time: {computation_time:.2f}s")
                print(f"  Throughput: {throughput:,.0f} points/sec")
                print(f"  Peak GPU memory: {memory_used:.2f} GB")
                print(f"  Memory efficiency: {memory_efficiency:.1f}% of total GPU")
                print(f"  Result shape: {result.shape}")
                
                # Check if chunking was used
                if hasattr(pipeline, 'memory_manager') and pipeline.memory_manager:
                    was_chunked = pipeline.memory_manager.should_use_chunking(data)
                    print(f"  Chunking used: {'Yes' if was_chunked else 'No'}")
                
                # Show memory utilization improvement
                if memory_efficiency > 10:  # More than 10% utilization
                    print(f"  🎯 Good memory utilization!")
                else:
                    print(f"  ⚠️ Low memory utilization")
                
            except Exception as e:
                print(f"❌ Failed: {e}")
            
            # Clear memory between tests
            cp.get_default_memory_pool().free_all_blocks()
            print()
        
        return True
        
    except ImportError:
        print("❌ CuPy not available")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


def compare_before_after():
    """Compare old vs new memory configuration"""
    print("📊 COMPARING OLD VS NEW MEMORY CONFIGURATION")
    print("=" * 60)
    
    try:
        import cupy as cp
        
        # Test data
        size = 1_000_000
        data = pd.DataFrame({
            'open': np.random.randn(size).cumsum() + 100,
            'high': np.random.randn(size).cumsum() + 105,
            'low': np.random.randn(size).cumsum() + 95,
            'close': np.random.randn(size).cumsum() + 100
        })
        
        configs = [
            ("Conservative (old)", 50000, 0.7),
            ("Optimized (new)", 200000, 0.85),
        ]
        
        results = []
        
        for name, chunk_size, threshold in configs:
            print(f"\n--- {name} ---")
            print(f"Chunk size: {chunk_size:,}, Threshold: {threshold}")
            
            try:
                pipeline = UnifiedTechnicalIndicatorsPipeline(
                    backend='cupy',
                    enable_gpu_memory_management=True,
                    chunk_size=chunk_size,
                    memory_threshold=threshold
                )
                
                # Clear memory before test
                cp.get_default_memory_pool().free_all_blocks()
                free_before, total_mem = cp.cuda.runtime.memGetInfo()
                
                start_time = time.perf_counter()
                
                result = pipeline.compute_indicators(
                    data, 
                    ['macd', 'atr'],
                    macd_params={'fast': 12, 'slow': 26, 'signal': 9},
                    atr_period=14
                )
                
                end_time = time.perf_counter()
                free_after, _ = cp.cuda.runtime.memGetInfo()
                
                memory_used = (free_before - free_after) / 1e9
                computation_time = end_time - start_time
                throughput = size / computation_time
                memory_efficiency = memory_used / (total_mem / 1e9) * 100
                
                print(f"✅ Time: {computation_time:.2f}s")
                print(f"✅ Throughput: {throughput:,.0f} points/sec")
                print(f"✅ Memory used: {memory_used:.2f} GB ({memory_efficiency:.1f}%)")
                
                results.append({
                    'config': name,
                    'time': computation_time,
                    'throughput': throughput,
                    'memory_gb': memory_used,
                    'memory_efficiency': memory_efficiency
                })
                
            except Exception as e:
                print(f"❌ Failed: {e}")
        
        # Compare results
        if len(results) == 2:
            old, new = results
            
            print(f"\n🎯 PERFORMANCE IMPROVEMENT:")
            time_improvement = (old['time'] - new['time']) / old['time'] * 100
            throughput_improvement = (new['throughput'] - old['throughput']) / old['throughput'] * 100
            memory_improvement = (new['memory_efficiency'] - old['memory_efficiency'])
            
            print(f"  Time improvement: {time_improvement:+.1f}%")
            print(f"  Throughput improvement: {throughput_improvement:+.1f}%")
            print(f"  Memory utilization: {old['memory_efficiency']:.1f}% → {new['memory_efficiency']:.1f}% ({memory_improvement:+.1f}%)")
            
            if throughput_improvement > 0:
                print(f"  🚀 Optimized configuration is faster!")
            if memory_improvement > 5:
                print(f"  💾 Optimized configuration uses memory more efficiently!")
        
        return results
        
    except Exception as e:
        print(f"❌ Comparison failed: {e}")
        return []


def main():
    """Main test function"""
    print("⚡ OPTIMIZED GPU MEMORY USAGE TEST")
    print("=" * 80)
    
    # Test optimized memory utilization
    success = test_memory_utilization()
    
    if success:
        # Compare old vs new configuration
        compare_before_after()
        
        print(f"\n✅ OPTIMIZATION SUMMARY:")
        print(f"1. Increased default chunk size: 50K → 200K points")
        print(f"2. Increased memory threshold: 70% → 85%")
        print(f"3. Increased memory pool limit: 80% → 90%")
        print(f"4. Reduced safety margins for better utilization")
        print(f"5. Larger chunk size bounds: 100K → 500K max")
        
        print(f"\n💡 EXPECTED BENEFITS:")
        print(f"- Higher GPU memory utilization (target: >10% of total)")
        print(f"- Better throughput with larger chunks")
        print(f"- Reduced chunking overhead")
        print(f"- More efficient GPU resource usage")
    
    else:
        print("❌ GPU not available for optimization testing")


if __name__ == "__main__":
    main()