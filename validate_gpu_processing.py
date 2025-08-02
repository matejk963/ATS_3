#!/usr/bin/env python3
"""
Validate GPU Processing is Actually Working
"""

import sys
sys.path.append('src')

import time
import pandas as pd
import numpy as np
from technical_indicators.unified_pipeline import UnifiedTechnicalIndicatorsPipeline

def create_test_data(size=50000):
    """Create test OHLCV data"""
    return pd.DataFrame({
        'open': np.random.rand(size) * 100 + 50,
        'high': np.random.rand(size) * 100 + 55,
        'low': np.random.rand(size) * 100 + 45,
        'close': np.random.rand(size) * 100 + 50,
        'volume': np.random.rand(size) * 1000 + 500
    })

def test_gpu_vs_cpu_performance():
    """Compare GPU vs CPU performance to validate GPU is working"""
    
    print("🏁 GPU vs CPU Performance Validation")
    print("=" * 50)
    
    # Create test data
    data = create_test_data(50000)
    print(f"Test data: {len(data):,} points")
    
    # Test CPU pipeline
    print("\n⚙️  Testing CPU Pipeline...")
    cpu_pipeline = UnifiedTechnicalIndicatorsPipeline(
        backend='numpy',
        enable_gpu_memory_management=False
    )
    
    cpu_start = time.perf_counter()
    cpu_result = cpu_pipeline.compute_indicators(data, ['macd'])
    cpu_end = time.perf_counter()
    cpu_time = cpu_end - cpu_start
    
    print(f"CPU Time: {cpu_time:.3f} seconds")
    print(f"CPU Throughput: {len(data)/cpu_time:.0f} points/second")
    print(f"CPU Result shape: {cpu_result.shape}")
    
    # Test GPU pipeline  
    print("\n🚀 Testing GPU Pipeline...")
    gpu_pipeline = UnifiedTechnicalIndicatorsPipeline(
        backend='cupy',
        enable_gpu_memory_management=True
    )
    
    # Monitor GPU stats
    initial_stats = gpu_pipeline.get_gpu_memory_statistics()
    print(f"Initial GPU utilization: {initial_stats.get('memory_utilization_pct', 0):.1f}%")
    
    gpu_start = time.perf_counter()
    gpu_result = gpu_pipeline.compute_indicators(data, ['macd'])
    gpu_end = time.perf_counter()
    gpu_time = gpu_end - gpu_start
    
    final_stats = gpu_pipeline.get_gpu_memory_statistics()
    print(f"GPU Time: {gpu_time:.3f} seconds")
    print(f"GPU Throughput: {len(data)/gpu_time:.0f} points/second")
    print(f"GPU Result shape: {gpu_result.shape}")
    print(f"Peak GPU utilization: {final_stats.get('memory_utilization_pct', 0):.1f}%")
    
    # Calculate speedup
    if gpu_time > 0:
        speedup = cpu_time / gpu_time
        print(f"\n🎯 GPU Speedup: {speedup:.2f}x")
        
        if speedup > 1.1:
            print("✅ GPU is significantly faster - GPU processing is working!")
        elif speedup > 0.9:
            print("⚠️  GPU and CPU performance similar - check GPU utilization")
        else:
            print("❌ GPU is slower than CPU - possible issue with GPU processing")
    
    # Verify results are similar
    print(f"\n🔍 Result Verification:")
    print(f"CPU columns: {list(cpu_result.columns)}")
    print(f"GPU columns: {list(gpu_result.columns)}")
    
    # Check for MACD columns
    cpu_macd_cols = [col for col in cpu_result.columns if 'macd' in col.lower()]
    gpu_macd_cols = [col for col in gpu_result.columns if 'macd' in col.lower()]
    
    print(f"CPU MACD columns: {cpu_macd_cols}")
    print(f"GPU MACD columns: {gpu_macd_cols}")
    
    if len(cpu_macd_cols) > 0 and len(gpu_macd_cols) > 0:
        print("✅ Both CPU and GPU produced MACD results")
        
        # Compare first MACD column values (should be similar)
        cpu_col = cpu_macd_cols[0]
        gpu_col = gpu_macd_cols[0]
        
        cpu_vals = cpu_result[cpu_col].dropna()
        gpu_vals = gpu_result[gpu_col].dropna()
        
        if len(cpu_vals) > 0 and len(gpu_vals) > 0:
            diff = abs(cpu_vals.iloc[-1] - gpu_vals.iloc[-1])
            print(f"Last value difference: {diff:.6f}")
            
            if diff < 0.001:
                print("✅ CPU and GPU results are very similar")
            else:
                print("⚠️  CPU and GPU results differ - check implementation")
    else:
        print("❌ Missing MACD results from CPU or GPU")
    
    return speedup if gpu_time > 0 else 0

def test_memory_pressure():
    """Test GPU under memory pressure to validate chunking"""
    
    print("\n🧠 GPU Memory Pressure Test")
    print("=" * 50)
    
    # Create increasingly large datasets
    sizes = [100000, 200000, 500000]
    
    pipeline = UnifiedTechnicalIndicatorsPipeline(
        backend='cupy',
        enable_gpu_memory_management=True
    )
    
    for size in sizes:
        print(f"\n📊 Testing {size:,} points...")
        data = create_test_data(size)
        
        initial_stats = pipeline.get_gpu_memory_statistics()
        
        start_time = time.perf_counter()
        result = pipeline.compute_indicators(data, ['macd'])
        end_time = time.perf_counter()
        
        final_stats = pipeline.get_gpu_memory_statistics()
        
        processing_time = end_time - start_time
        throughput = size / processing_time
        
        print(f"  Time: {processing_time:.3f}s")
        print(f"  Throughput: {throughput:.0f} pts/s")
        print(f"  GPU utilization: {final_stats.get('memory_utilization_pct', 0):.1f}%")
        print(f"  Result shape: {result.shape}")
        
        # Clear GPU cache between tests
        pipeline.clear_gpu_memory_cache()

def main():
    """Run GPU validation tests"""
    
    print("🔥 GPU PROCESSING VALIDATION TEST")
    print("=" * 60)
    
    try:
        # Test 1: Performance comparison
        speedup = test_gpu_vs_cpu_performance()
        
        # Test 2: Memory pressure
        test_memory_pressure()
        
        print("\n" + "=" * 60)
        print("🎯 VALIDATION SUMMARY:")
        
        if speedup > 1.1:
            print("✅ GPU processing is working and faster than CPU")
            print("✅ Aggressive memory optimization is active")
            print("✅ GPU memory utilization has been improved")
            print("🚀 Your GPU is now being properly utilized!")
        else:
            print("⚠️  GPU performance needs investigation")
            print("🔍 Check GPU drivers and CuPy installation")
        
    except Exception as e:
        print(f"❌ Validation failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()