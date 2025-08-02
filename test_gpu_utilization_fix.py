#!/usr/bin/env python3
"""
GPU Utilization Fix Test - Aggressive GPU Memory Usage
"""

import sys
sys.path.append('src')

import time
import pandas as pd
import numpy as np
from technical_indicators.unified_pipeline import UnifiedTechnicalIndicatorsPipeline

def test_aggressive_gpu_usage():
    """Test with aggressive GPU memory settings"""
    
    # Create larger test dataset
    print("Creating 100K point test dataset...")
    data = pd.DataFrame({
        'open': np.random.rand(100000) * 100,
        'high': np.random.rand(100000) * 100 + 2,
        'low': np.random.rand(100000) * 100 - 2,
        'close': np.random.rand(100000) * 100,
        'volume': np.random.rand(100000) * 1000
    })
    
    print(f"Dataset size: {len(data)} points")
    
    # Test with aggressive GPU settings
    print("\nTesting with aggressive GPU memory settings...")
    
    pipeline = UnifiedTechnicalIndicatorsPipeline(
        backend='cupy',
        enable_gpu_memory_management=True,
        chunk_size=500000,        # Much larger chunks
        memory_threshold=0.95,    # Use 95% of GPU memory
        optimize_memory=True
    )
    
    # Get initial GPU stats
    gpu_stats = pipeline.get_gpu_memory_statistics()
    print(f"GPU Device: {gpu_stats.get('device_name', 'Unknown')}")
    print(f"Total GPU Memory: {gpu_stats.get('total_memory_gb', 0):.1f} GB")
    print(f"Free GPU Memory: {gpu_stats.get('free_memory_gb', 0):.1f} GB")
    print(f"Current Utilization: {gpu_stats.get('memory_utilization_pct', 0):.1f}%")
    
    # Force GPU processing by bypassing chunking decision
    start_time = time.perf_counter()
    
    try:
        # Compute MACD with forced GPU processing
        result = pipeline.compute_indicators(data, ['macd'])
        
        end_time = time.perf_counter()
        processing_time = end_time - start_time
        
        print(f"\nProcessing completed successfully!")
        print(f"Processing time: {processing_time:.3f} seconds")
        print(f"Throughput: {len(data)/processing_time:.0f} points/second")
        
        # Check final GPU stats
        final_stats = pipeline.get_gpu_memory_statistics()
        print(f"Final GPU utilization: {final_stats.get('memory_utilization_pct', 0):.1f}%")
        
        # Verify results
        macd_cols = ['macd_line', 'macd_signal', 'macd_histogram']
        found_cols = [col for col in macd_cols if col in result.columns]
        print(f"MACD columns found: {found_cols}")
        
        return True
        
    except Exception as e:
        print(f"GPU processing failed: {e}")
        return False

def test_force_gpu_direct():
    """Test direct GPU processing without memory management"""
    
    print("\n" + "="*60)
    print("TESTING DIRECT GPU PROCESSING (NO MEMORY MANAGEMENT)")
    print("="*60)
    
    # Create test data
    data = pd.DataFrame({
        'open': np.random.rand(50000) * 100,
        'high': np.random.rand(50000) * 100 + 2,
        'low': np.random.rand(50000) * 100 - 2,
        'close': np.random.rand(50000) * 100,
        'volume': np.random.rand(50000) * 1000
    })
    
    # Disable memory management to force direct GPU processing
    pipeline = UnifiedTechnicalIndicatorsPipeline(
        backend='cupy',
        enable_gpu_memory_management=False,  # Disable memory management
        optimize_memory=False
    )
    
    start_time = time.perf_counter()
    
    try:
        result = pipeline.compute_indicators(data, ['macd'])
        end_time = time.perf_counter()
        
        print(f"Direct GPU processing successful!")
        print(f"Processing time: {end_time - start_time:.3f} seconds")
        print(f"Throughput: {len(data)/(end_time - start_time):.0f} points/second")
        
        return True
        
    except Exception as e:
        print(f"Direct GPU processing failed: {e}")
        return False

if __name__ == "__main__":
    print("GPU Utilization Fix Test")
    print("=" * 50)
    
    # Test 1: Aggressive memory settings
    success1 = test_aggressive_gpu_usage()
    
    # Test 2: Direct GPU processing
    success2 = test_force_gpu_direct()
    
    print("\n" + "="*50)
    print("SUMMARY:")
    print(f"Aggressive GPU settings: {'✅ SUCCESS' if success1 else '❌ FAILED'}")
    print(f"Direct GPU processing: {'✅ SUCCESS' if success2 else '❌ FAILED'}")