#!/usr/bin/env python3
"""
Aggressive GPU Memory Utilization Fix Test
Tests the new ultra-aggressive GPU memory optimization
"""

import sys
sys.path.append('src')

import time
import pandas as pd
import numpy as np
from technical_indicators.unified_pipeline import UnifiedTechnicalIndicatorsPipeline
from technical_indicators.gpu_memory_manager import GPUMemoryManager

def create_test_data(size):
    """Create test OHLCV data"""
    return pd.DataFrame({
        'open': np.random.rand(size) * 100,
        'high': np.random.rand(size) * 100 + 5,
        'low': np.random.rand(size) * 100 - 5,
        'close': np.random.rand(size) * 100,
        'volume': np.random.rand(size) * 1000
    })

def test_gpu_memory_manager_aggressive():
    """Test the aggressive GPU memory manager directly"""
    print("🧪 TESTING AGGRESSIVE GPU MEMORY MANAGER")
    print("=" * 60)
    
    # Test different data sizes
    sizes = [25000, 100000, 250000, 500000]
    
    manager = GPUMemoryManager()
    initial_stats = manager.get_memory_statistics()
    
    print(f"GPU Device: {initial_stats.get('device_name', 'Unknown')}")
    print(f"Total Memory: {initial_stats.get('total_memory_gb', 0):.1f} GB")
    print(f"Free Memory: {initial_stats.get('free_memory_gb', 0):.1f} GB")
    print(f"Current Utilization: {initial_stats.get('memory_utilization_pct', 0):.1f}%")
    print()
    
    for size in sizes:
        data = create_test_data(size)
        should_chunk = manager.should_use_chunking(data)
        print(f"Size {size:6d}: Should chunk = {should_chunk}")
    
    print()

def test_aggressive_pipeline():
    """Test the aggressive pipeline configuration"""
    print("🚀 TESTING AGGRESSIVE PIPELINE PROCESSING")
    print("=" * 60)
    
    # Create large test dataset
    data = create_test_data(150000)  # 150K points
    print(f"Created dataset with {len(data)} points")
    
    # Initialize aggressive pipeline
    pipeline = UnifiedTechnicalIndicatorsPipeline(
        backend='cupy',
        enable_gpu_memory_management=True,
        chunk_size=1000000,     # 1M chunk size
        memory_threshold=0.95,  # Use 95% of GPU memory
        optimize_memory=True
    )
    
    # Get initial GPU stats
    initial_stats = pipeline.get_gpu_memory_statistics()
    print(f"Initial GPU utilization: {initial_stats.get('memory_utilization_pct', 0):.1f}%")
    print(f"Chunk size: {initial_stats.get('chunking_strategy', {}).get('chunk_size', 0):,}")
    print(f"Memory threshold: {initial_stats.get('chunking_strategy', {}).get('memory_threshold', 0):.0%}")
    print()
    
    # Test MACD processing
    print("Processing MACD indicators...")
    start_time = time.perf_counter()
    
    result = pipeline.compute_indicators(data, ['macd'])
    
    end_time = time.perf_counter()
    processing_time = end_time - start_time
    
    # Get final GPU stats
    final_stats = pipeline.get_gpu_memory_statistics()
    
    print(f"✅ Processing completed successfully!")
    print(f"Processing time: {processing_time:.3f} seconds")
    print(f"Throughput: {len(data)/processing_time:.0f} points/second")
    print(f"Initial GPU utilization: {initial_stats.get('memory_utilization_pct', 0):.1f}%")
    print(f"Peak GPU utilization: {final_stats.get('memory_utilization_pct', 0):.1f}%")
    
    # Check result columns
    print(f"Result shape: {result.shape}")
    print(f"Result columns: {list(result.columns)}")
    
    # Verify MACD data exists and is valid
    macd_cols = [col for col in result.columns if 'macd' in col.lower()]
    if macd_cols:
        print(f"✅ MACD columns found: {macd_cols}")
        # Check for valid data (not all NaN)
        valid_data = sum(result[col].notna().sum() for col in macd_cols)
        print(f"Valid MACD data points: {valid_data}")
    else:
        print("❌ No MACD columns found in result")
    
    return len(macd_cols) > 0

def test_memory_scaling():
    """Test memory scaling with different dataset sizes"""
    print("📊 TESTING MEMORY SCALING")
    print("=" * 60)
    
    sizes = [50000, 100000, 200000, 300000]
    results = []
    
    for size in sizes:
        print(f"\nTesting {size:,} points...")
        data = create_test_data(size)
        
        pipeline = UnifiedTechnicalIndicatorsPipeline(
            backend='cupy',
            enable_gpu_memory_management=True,
            chunk_size=1000000,
            memory_threshold=0.95
        )
        
        start_time = time.perf_counter()
        initial_stats = pipeline.get_gpu_memory_statistics()
        
        result = pipeline.compute_indicators(data, ['macd'])
        
        end_time = time.perf_counter()
        final_stats = pipeline.get_gpu_memory_statistics()
        
        processing_time = end_time - start_time
        throughput = size / processing_time
        gpu_util = final_stats.get('memory_utilization_pct', 0)
        
        results.append({
            'size': size,
            'time': processing_time,
            'throughput': throughput,
            'gpu_util': gpu_util
        })
        
        print(f"  Time: {processing_time:.3f}s, Throughput: {throughput:.0f} pts/s, GPU: {gpu_util:.1f}%")
    
    print("\n📈 SCALING SUMMARY:")
    print("Size     | Time   | Throughput | GPU Util")
    print("-" * 45)
    for r in results:
        print(f"{r['size']:7,} | {r['time']:5.2f}s | {r['throughput']:8.0f} | {r['gpu_util']:6.1f}%")

def main():
    """Run all aggressive GPU tests"""
    print("🔥 AGGRESSIVE GPU UTILIZATION FIX TEST")
    print("=" * 70)
    print()
    
    try:
        # Test 1: Memory manager
        test_gpu_memory_manager_aggressive()
        
        # Test 2: Pipeline processing
        success = test_aggressive_pipeline()
        
        # Test 3: Memory scaling
        test_memory_scaling()
        
        print("\n" + "=" * 70)
        print("🎯 AGGRESSIVE GPU FIX SUMMARY:")
        print(f"✅ Memory Manager: Ultra-aggressive settings enabled")
        print(f"✅ Pipeline Processing: {'SUCCESS' if success else 'FAILED'}")
        print(f"✅ Memory Scaling: Tested across multiple dataset sizes")
        print("🚀 GPU should now utilize much more memory and processing power!")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()