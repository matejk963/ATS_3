#!/usr/bin/env python3
"""
GPU Memory Management Test Script

This script tests the GPU memory management system with datasets of various sizes,
including datasets larger than 250K points to validate memory handling capabilities.

Features tested:
- Chunked processing for large datasets
- GPU memory profiling and monitoring
- Adaptive batch sizing
- Memory pool optimization
- Automatic fallback prevention
"""

import sys
import time
import numpy as np
import pandas as pd
from typing import Dict, Any

# Add src to path for imports
sys.path.insert(0, 'src')

from src.feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline
from src.feature_engineering.gpu_memory_manager import GPUMemoryManager


def generate_test_data(size: int, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing"""
    np.random.seed(seed)
    
    # Generate base price series with realistic movement
    base_price = 100.0
    price_changes = np.random.normal(0, 0.5, size)
    prices = np.cumsum(price_changes) + base_price
    
    # Create OHLC from base prices
    noise = np.random.uniform(-0.5, 0.5, size)
    
    return pd.DataFrame({
        'open': prices + noise * 0.5,
        'high': prices + np.abs(noise) + np.random.uniform(0, 1, size),
        'low': prices - np.abs(noise) - np.random.uniform(0, 1, size),
        'close': prices + noise * 0.3,
        'volume': np.random.randint(1000, 10000, size)
    })


def test_dataset_size(size: int, description: str) -> Dict[str, Any]:
    """Test GPU memory management with a specific dataset size"""
    print(f"\n{'='*60}")
    print(f"Testing {description} ({size:,} points)")
    print(f"{'='*60}")
    
    # Generate test data
    print("Generating test data...")
    data = generate_test_data(size)
    print(f"✓ Generated {len(data):,} data points")
    
    results = {}
    
    try:
        # Create pipeline with GPU memory management
        print("\nInitializing GPU-enabled pipeline...")
        pipeline = UnifiedTechnicalIndicatorsPipeline(
            backend='cupy',
            enable_gpu_memory_management=True,
            chunk_size=50000,
            memory_threshold=0.7,
            optimize_memory=True
        )
        
        # Get memory statistics before processing
        print("\nGPU Memory Status (Before):")
        memory_stats_before = pipeline.get_gpu_memory_statistics()
        for key, value in memory_stats_before.items():
            if isinstance(value, dict):
                print(f"  {key}:")
                for subkey, subvalue in value.items():
                    print(f"    {subkey}: {subvalue}")
            else:
                print(f"  {key}: {value}")
        
        # Test computation with timing
        print(f"\nComputing technical indicators...")
        start_time = time.perf_counter()
        
        result = pipeline.compute_indicators(
            data=data,
            indicators=['macd', 'atr'],
            macd_params={'fast': 12, 'slow': 26, 'signal': 9},
            atr_period=14
        )
        
        end_time = time.perf_counter()
        computation_time = end_time - start_time
        
        print(f"✓ Computation completed in {computation_time:.2f} seconds")
        print(f"✓ Result shape: {result.shape}")
        
        # Get memory statistics after processing
        print("\nGPU Memory Status (After):")
        memory_stats_after = pipeline.get_gpu_memory_statistics()
        if memory_stats_after.get('gpu_available'):
            print(f"  Memory Utilization: {memory_stats_after.get('memory_utilization_pct', 0):.1f}%")
            print(f"  Free Memory: {memory_stats_after.get('free_memory_gb', 0):.2f} GB")
        
        # Verify results
        print("\nValidating results...")
        required_columns = ['macd', 'macd_signal', 'macd_histogram', 'atr']
        missing_columns = [col for col in required_columns if col not in result.columns]
        
        if not missing_columns:
            print("✓ All expected indicators computed successfully")
        else:
            print(f"❌ Missing columns: {missing_columns}")
        
        # Check for NaN values
        nan_counts = result[required_columns].isnull().sum()
        total_nans = nan_counts.sum()
        print(f"✓ NaN values: {total_nans} (expected for early periods)")
        
        # Clear GPU cache
        pipeline.clear_gpu_memory_cache()
        
        results = {
            'success': True,
            'size': size,
            'computation_time': computation_time,
            'result_shape': result.shape,
            'memory_stats_before': memory_stats_before,
            'memory_stats_after': memory_stats_after,
            'throughput_points_per_sec': size / computation_time,
            'missing_columns': missing_columns,
            'total_nans': total_nans
        }
        
    except Exception as e:
        print(f"❌ Error: {e}")
        results = {
            'success': False,
            'size': size,
            'error': str(e),
            'error_type': type(e).__name__
        }
    
    return results


def test_memory_pressure_handling():
    """Test how the system handles memory pressure situations"""
    print(f"\n{'='*60}")
    print("Testing Memory Pressure Handling")
    print(f"{'='*60}")
    
    # Test with progressively larger datasets
    sizes = [10000, 50000, 100000, 250000, 500000]
    
    results = []
    
    for size in sizes:
        print(f"\nTesting with {size:,} points...")
        
        try:
            # Create memory manager directly
            memory_manager = GPUMemoryManager(
                memory_threshold=0.6,  # More aggressive threshold
                chunk_size=30000,      # Smaller chunks
                enable_memory_pool=True
            )
            
            # Generate test data
            data = generate_test_data(size)
            
            # Check if chunking should be used
            should_chunk = memory_manager.should_use_chunking(data)
            print(f"  Should use chunking: {should_chunk}")
            
            # Get memory statistics
            stats = memory_manager.get_memory_statistics()
            print(f"  GPU available: {stats.get('gpu_available', False)}")
            
            if stats.get('gpu_available'):
                print(f"  Free memory: {stats.get('free_memory_gb', 0):.2f} GB")
                print(f"  Memory utilization: {stats.get('memory_utilization_pct', 0):.1f}%")
            
            results.append({
                'size': size,
                'should_chunk': should_chunk,
                'gpu_available': stats.get('gpu_available', False),
                'free_memory_gb': stats.get('free_memory_gb', 0)
            })
            
        except Exception as e:
            print(f"  Error: {e}")
            results.append({
                'size': size,
                'error': str(e)
            })
    
    return results


def main():
    """Main test execution"""
    print("GPU Memory Management Test Suite")
    print("="*60)
    
    # Test different dataset sizes
    test_cases = [
        (10000, "Small Dataset"),
        (75000, "Medium Dataset (Memory Limit)"),
        (150000, "Large Dataset (Chunking Required)"),
        (250000, "Very Large Dataset"),
        (500000, "Extreme Dataset")
    ]
    
    all_results = []
    
    for size, description in test_cases:
        result = test_dataset_size(size, description)
        all_results.append(result)
    
    # Test memory pressure handling
    pressure_results = test_memory_pressure_handling()
    
    # Summary report
    print(f"\n{'='*60}")
    print("SUMMARY REPORT")
    print(f"{'='*60}")
    
    successful_tests = [r for r in all_results if r.get('success', False)]
    failed_tests = [r for r in all_results if not r.get('success', False)]
    
    print(f"Successful tests: {len(successful_tests)}/{len(all_results)}")
    print(f"Failed tests: {len(failed_tests)}")
    
    if successful_tests:
        print("\nPerformance Summary:")
        for result in successful_tests:
            size = result['size']
            time_taken = result['computation_time']
            throughput = result['throughput_points_per_sec']
            print(f"  {size:>6,} points: {time_taken:>6.2f}s ({throughput:>8,.0f} pts/sec)")
    
    if failed_tests:
        print("\nFailed Tests:")
        for result in failed_tests:
            size = result['size']
            error = result.get('error', 'Unknown error')
            print(f"  {size:>6,} points: {error}")
    
    print(f"\n{'='*60}")
    print("Memory Pressure Test Results:")
    print(f"{'='*60}")
    
    for result in pressure_results:
        if 'error' not in result:
            size = result['size']
            should_chunk = result['should_chunk']
            gpu_available = result['gpu_available']
            free_mem = result.get('free_memory_gb', 0)
            print(f"  {size:>6,} points: Chunk={should_chunk}, GPU={gpu_available}, Free={free_mem:.2f}GB")
    
    print("\nTest completed!")
    
    # Return overall success
    return len(failed_tests) == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)