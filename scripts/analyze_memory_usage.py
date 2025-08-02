#!/usr/bin/env python3
"""
GPU Memory Usage Analysis and Optimization
"""

import sys
import os
import numpy as np
import pandas as pd

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from technical_indicators.unified_pipeline import UnifiedTechnicalIndicatorsPipeline


def analyze_current_memory_usage():
    """Analyze current GPU memory usage patterns"""
    print("🔍 ANALYZING CURRENT GPU MEMORY USAGE")
    print("=" * 50)
    
    try:
        import cupy as cp
        
        # Get GPU info
        device = cp.cuda.Device()
        free_mem, total_mem = cp.cuda.runtime.memGetInfo()
        
        print(f"GPU Total Memory: {total_mem / 1e9:.2f} GB")
        print(f"GPU Free Memory: {free_mem / 1e9:.2f} GB")
        print(f"GPU Used Memory: {(total_mem - free_mem) / 1e9:.2f} GB")
        print(f"Memory Utilization: {((total_mem - free_mem) / total_mem * 100):.1f}%")
        
        # Test with different data sizes
        test_sizes = [10_000, 50_000, 100_000, 200_000, 500_000, 1_000_000]
        
        print(f"\n📊 MEMORY USAGE BY DATA SIZE:")
        print("-" * 60)
        
        for size in test_sizes:
            print(f"\nTesting {size:,} data points...")
            
            # Create test data
            data = pd.DataFrame({
                'open': np.random.randn(size).cumsum() + 100,
                'high': np.random.randn(size).cumsum() + 105,
                'low': np.random.randn(size).cumsum() + 95,
                'close': np.random.randn(size).cumsum() + 100
            })
            
            # Measure memory before
            free_before, _ = cp.cuda.runtime.memGetInfo()
            
            # Create pipeline and compute
            pipeline = UnifiedTechnicalIndicatorsPipeline(
                backend='cupy',
                enable_gpu_memory_management=True
            )
            
            try:
                result = pipeline.compute_indicators(data, ['macd'])
                
                # Measure memory after
                free_after, _ = cp.cuda.runtime.memGetInfo()
                memory_used = (free_before - free_after) / 1e6  # MB
                
                print(f"  Memory used: {memory_used:.1f} MB")
                print(f"  Memory per point: {memory_used / size * 1000:.2f} KB/point")
                
                # Check if chunking was used
                if pipeline.memory_manager:
                    should_chunk = pipeline.memory_manager.should_use_chunking(data)
                    print(f"  Chunking used: {should_chunk}")
                
            except Exception as e:
                print(f"  ❌ Failed: {e}")
            
            # Clear memory
            cp.get_default_memory_pool().free_all_blocks()
        
        return True
        
    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        return False


def test_optimized_chunk_sizes():
    """Test different chunk size configurations"""
    print(f"\n🔧 TESTING OPTIMIZED CHUNK SIZES")
    print("=" * 50)
    
    try:
        import cupy as cp
        
        # Get total memory
        free_mem, total_mem = cp.cuda.runtime.memGetInfo()
        print(f"Available GPU Memory: {free_mem / 1e9:.2f} GB")
        
        # Create large test dataset
        size = 1_000_000
        data = pd.DataFrame({
            'open': np.random.randn(size).cumsum() + 100,
            'high': np.random.randn(size).cumsum() + 105,
            'low': np.random.randn(size).cumsum() + 95,
            'close': np.random.randn(size).cumsum() + 100
        })
        
        print(f"Test data size: {size:,} points ({data.memory_usage(deep=True).sum() / 1e6:.1f} MB)")
        
        # Test different chunk sizes and memory thresholds
        test_configs = [
            (50_000, 0.7, "Conservative (current)"),
            (100_000, 0.8, "Moderate"),
            (200_000, 0.85, "Aggressive"),
            (500_000, 0.9, "Very Aggressive"),
        ]
        
        results = []
        
        for chunk_size, mem_threshold, description in test_configs:
            print(f"\n--- Testing {description} ---")
            print(f"Chunk size: {chunk_size:,}, Memory threshold: {mem_threshold}")
            
            try:
                pipeline = UnifiedTechnicalIndicatorsPipeline(
                    backend='cupy',
                    enable_gpu_memory_management=True,
                    chunk_size=chunk_size,
                    memory_threshold=mem_threshold
                )
                
                # Measure memory before
                free_before, _ = cp.cuda.runtime.memGetInfo()
                
                import time
                start_time = time.perf_counter()
                
                # Compute indicators
                result = pipeline.compute_indicators(data, ['macd', 'atr'])
                
                end_time = time.perf_counter()
                
                # Measure memory after
                free_after, _ = cp.cuda.runtime.memGetInfo()
                
                memory_used = (free_before - free_after) / 1e9  # GB
                computation_time = end_time - start_time
                throughput = size / computation_time
                
                print(f"✅ Success!")
                print(f"  Time: {computation_time:.2f}s")
                print(f"  Throughput: {throughput:,.0f} points/sec")
                print(f"  Peak memory: {memory_used:.2f} GB")
                print(f"  Memory efficiency: {memory_used / (free_mem / 1e9) * 100:.1f}% of available")
                
                results.append({
                    'config': description,
                    'chunk_size': chunk_size,
                    'threshold': mem_threshold,
                    'time': computation_time,
                    'throughput': throughput,
                    'memory_gb': memory_used,
                    'memory_efficiency': memory_used / (free_mem / 1e9) * 100
                })
                
            except Exception as e:
                print(f"❌ Failed: {e}")
                
            # Clear memory between tests
            cp.get_default_memory_pool().free_all_blocks()
        
        # Print comparison
        if results:
            print(f"\n📈 PERFORMANCE COMPARISON:")
            print("-" * 80)
            print(f"{'Config':<20} {'Time(s)':<8} {'Throughput':<12} {'Memory(GB)':<12} {'Efficiency%':<12}")
            print("-" * 80)
            
            for r in results:
                print(f"{r['config']:<20} {r['time']:<8.2f} {r['throughput']:<12,.0f} "
                      f"{r['memory_gb']:<12.2f} {r['memory_efficiency']:<12.1f}")
            
            # Find best configuration
            best_throughput = max(results, key=lambda x: x['throughput'])
            best_memory = max(results, key=lambda x: x['memory_efficiency'])
            
            print(f"\n🏆 RECOMMENDATIONS:")
            print(f"Best Throughput: {best_throughput['config']} ({best_throughput['throughput']:,.0f} pts/sec)")
            print(f"Best Memory Use: {best_memory['config']} ({best_memory['memory_efficiency']:.1f}% efficiency)")
        
        return results
        
    except Exception as e:
        print(f"❌ Optimization test failed: {e}")
        return []


def create_optimized_memory_manager():
    """Create an optimized memory manager configuration"""
    print(f"\n⚡ CREATING OPTIMIZED MEMORY MANAGER")
    print("=" * 50)
    
    try:
        import cupy as cp
        
        # Get GPU capabilities
        free_mem, total_mem = cp.cuda.runtime.memGetInfo()
        device = cp.cuda.Device()
        
        print(f"GPU Memory: {total_mem / 1e9:.2f} GB")
        print(f"Free Memory: {free_mem / 1e9:.2f} GB")
        
        # Calculate optimized parameters
        # Use up to 90% of available memory instead of 70%
        aggressive_threshold = 0.9
        
        # Calculate optimal chunk size based on available memory
        # Assuming ~12 bytes per data point (4 OHLC values * 4 bytes + overhead)
        bytes_per_point = 12 * 4  # 4x factor for intermediate arrays
        optimal_chunk_size = int((free_mem * aggressive_threshold) / bytes_per_point)
        
        # Clamp to reasonable bounds
        optimal_chunk_size = max(100_000, min(optimal_chunk_size, 2_000_000))
        
        print(f"Calculated optimal chunk size: {optimal_chunk_size:,}")
        print(f"Aggressive memory threshold: {aggressive_threshold}")
        
        # Test the optimized configuration
        print(f"\n🧪 Testing optimized configuration...")
        
        # Create large test dataset
        size = 1_500_000  # 1.5M points
        data = pd.DataFrame({
            'open': np.random.randn(size).cumsum() + 100,
            'high': np.random.randn(size).cumsum() + 105,
            'low': np.random.randn(size).cumsum() + 95,
            'close': np.random.randn(size).cumsum() + 100
        })
        
        pipeline = UnifiedTechnicalIndicatorsPipeline(
            backend='cupy',
            enable_gpu_memory_management=True,
            chunk_size=optimal_chunk_size,
            memory_threshold=aggressive_threshold
        )
        
        # Measure performance
        free_before, _ = cp.cuda.runtime.memGetInfo()
        
        import time
        start_time = time.perf_counter()
        
        result = pipeline.compute_indicators(data, ['macd', 'atr', 'swing_points'])
        
        end_time = time.perf_counter()
        free_after, _ = cp.cuda.runtime.memGetInfo()
        
        memory_used = (free_before - free_after) / 1e9
        computation_time = end_time - start_time
        throughput = size / computation_time
        
        print(f"✅ Optimized test completed!")
        print(f"  Dataset: {size:,} points")
        print(f"  Time: {computation_time:.2f}s")
        print(f"  Throughput: {throughput:,.0f} points/sec")
        print(f"  Peak memory: {memory_used:.2f} GB")
        print(f"  Memory utilization: {memory_used / (total_mem / 1e9) * 100:.1f}% of total GPU memory")
        
        # Save optimal configuration
        optimal_config = {
            'chunk_size': optimal_chunk_size,
            'memory_threshold': aggressive_threshold,
            'throughput': throughput,
            'memory_efficiency': memory_used / (total_mem / 1e9) * 100
        }
        
        return optimal_config
        
    except Exception as e:
        print(f"❌ Optimization failed: {e}")
        return None


def main():
    """Main analysis function"""
    print("🚀 GPU MEMORY USAGE ANALYSIS & OPTIMIZATION")
    print("=" * 80)
    
    # Step 1: Analyze current usage
    analyze_current_memory_usage()
    
    # Step 2: Test different configurations
    test_optimized_chunk_sizes()
    
    # Step 3: Create optimized configuration
    optimal_config = create_optimized_memory_manager()
    
    if optimal_config:
        print(f"\n🎯 OPTIMAL CONFIGURATION FOUND:")
        print(f"  Chunk Size: {optimal_config['chunk_size']:,}")
        print(f"  Memory Threshold: {optimal_config['memory_threshold']}")
        print(f"  Expected Throughput: {optimal_config['throughput']:,.0f} points/sec")
        print(f"  Memory Efficiency: {optimal_config['memory_efficiency']:.1f}%")
        
        print(f"\n💡 RECOMMENDATIONS:")
        print(f"1. Update default chunk_size to {optimal_config['chunk_size']:,}")
        print(f"2. Update default memory_threshold to {optimal_config['memory_threshold']}")
        print(f"3. This should achieve ~{optimal_config['memory_efficiency']:.0f}% GPU memory utilization")
        print(f"4. Expected performance improvement: {optimal_config['throughput']:,.0f} points/sec")


if __name__ == "__main__":
    main()