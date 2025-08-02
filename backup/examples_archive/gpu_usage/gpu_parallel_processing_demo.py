"""
GPU Parallel Processing Demonstration
Shows how to use the GPU parallel processing system for high-performance data processing
"""

import sys
import numpy as np
import time
import matplotlib.pyplot as plt
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent.parent / "src"))

from gpu_usage.gpu_hardware_detector import GPUHardwareDetector
from gpu_usage.gpu_parallel_processor import (
    GPUParallelProcessor, ProcessingConfig, ProcessingMode, DataType
)
from gpu_usage.gpu_performance_comparator import GPUPerformanceComparator

def demonstrate_gpu_detection():
    """Demonstrate GPU hardware detection"""
    print("=" * 60)
    print("GPU HARDWARE DETECTION DEMONSTRATION")
    print("=" * 60)
    
    # Initialize detector
    detector = GPUHardwareDetector()
    
    # Detect GPU hardware
    gpu_info = detector.detect_gpu_hardware()
    detector.print_gpu_info()
    
    # Run benchmarks if GPU is available
    if gpu_info.gpu_available:
        print("\nRunning GPU benchmark suite...")
        benchmark_results = detector.run_gpu_benchmark(data_size=500000)
        detector.print_gpu_info()  # Print updated info with benchmark results
        
        # Validate GPU processing
        is_valid = detector.validate_gpu_processing_capability()
        print(f"\nGPU Processing Validation: {'✅ PASSED' if is_valid else '❌ FAILED'}")
    
    return gpu_info

def demonstrate_basic_processing():
    """Demonstrate basic GPU parallel processing"""
    print("\n" + "=" * 60)
    print("BASIC GPU PARALLEL PROCESSING DEMONSTRATION")
    print("=" * 60)
    
    # Generate sample data
    print("Generating sample data...")
    np.random.seed(42)
    data_sizes = [10000, 100000, 1000000]
    
    # Initialize processor
    config = ProcessingConfig(
        mode=ProcessingMode.AUTO,
        chunk_size=100000,
        max_memory_usage=75.0,
        use_streams=True,
        stream_count=4
    )
    
    processor = GPUParallelProcessor(config)
    
    # Print GPU info
    gpu_info = processor.get_gpu_info()
    print(f"GPU Available: {gpu_info['gpu_available']}")
    if gpu_info['gpu_available']:
        print(f"Capability Level: {gpu_info['capability_level']}")
        print(f"Recommended Chunk Size: {gpu_info['recommended_chunk_size']:,}")
    
    # Test different operations
    operations = ['sort', 'sum', 'mean', 'std', 'rolling_mean']
    
    print(f"\nTesting operations: {', '.join(operations)}")
    print("-" * 40)
    
    for size in data_sizes:
        print(f"\nData Size: {size:,} points")
        test_data = np.random.random(size).astype(np.float32)
        
        for operation in operations:
            try:
                start_time = time.perf_counter()
                
                if operation == 'rolling_mean':
                    result = processor.process_array(test_data, operation, window=20)
                else:
                    result = processor.process_array(test_data, operation)
                
                elapsed_time = time.perf_counter() - start_time
                
                # Get latest stats
                stats = processor.get_latest_stats()
                mode_str = stats.processing_mode.value if stats else "unknown"
                speedup_str = f"{stats.speedup_factor:.2f}x" if stats and stats.speedup_factor > 0 else "N/A"
                
                print(f"  {operation:12} | {elapsed_time:.4f}s | {mode_str:8} | {speedup_str:>6}")
                
            except Exception as e:
                print(f"  {operation:12} | ERROR: {str(e)}")
    
    return processor

def demonstrate_performance_comparison():
    """Demonstrate GPU vs CPU performance comparison"""
    print("\n" + "=" * 60)
    print("GPU vs CPU PERFORMANCE COMPARISON DEMONSTRATION")
    print("=" * 60)
    
    # Initialize comparator
    comparator = GPUPerformanceComparator("demo_benchmark_results")
    
    # Override for faster demo
    comparator.warmup_iterations = 2
    comparator.benchmark_iterations = 3
    comparator.default_data_sizes = [10000, 50000, 100000, 500000]
    
    print("Running quick benchmark...")
    
    # Run quick benchmark
    operations = ['sort', 'sum', 'mean', 'std']
    suite = comparator.quick_benchmark(operations, [10000, 100000, 500000])
    
    # Display results
    print(f"\n📊 BENCHMARK RESULTS")
    print("-" * 40)
    print(f"GPU Available: {suite.gpu_available}")
    print(f"Total Tests: {int(suite.summary_stats['total_tests'])}")
    print(f"Success Rate: {suite.summary_stats['success_rate']:.1f}%")
    print(f"Average Speedup: {suite.summary_stats['avg_speedup']:.2f}x")
    print(f"Maximum Speedup: {suite.summary_stats['max_speedup']:.2f}x")
    
    # Show detailed results
    print(f"\n📋 DETAILED RESULTS")
    print("-" * 60)
    print(f"{'Operation':<12} {'Size':<8} {'CPU Time':<10} {'GPU Time':<10} {'Speedup':<8}")
    print("-" * 60)
    
    for result in suite.results:
        if result.validation_passed:
            cpu_time_str = f"{result.cpu_time:.4f}s"
            gpu_time_str = f"{result.gpu_time:.4f}s" if result.gpu_time else "N/A"
            speedup_str = f"{result.speedup:.2f}x" if result.gpu_time else "N/A"
            
            print(f"{result.operation:<12} {result.data_size:<8,} {cpu_time_str:<10} "
                  f"{gpu_time_str:<10} {speedup_str:<8}")
    
    # Show recommendations
    print(f"\n💡 RECOMMENDATIONS")
    print("-" * 40)
    for i, rec in enumerate(suite.recommendations, 1):
        print(f"{i}. {rec}")
    
    # Generate performance plot
    try:
        print(f"\n📈 Generating performance plot...")
        comparator.plot_performance_comparison(suite)
        print("Performance plot saved to demo_benchmark_results/")
    except Exception as e:
        print(f"Could not generate plot: {e}")
    
    return suite

def demonstrate_custom_operations():
    """Demonstrate custom GPU operations"""
    print("\n" + "=" * 60)
    print("CUSTOM GPU OPERATIONS DEMONSTRATION")
    print("=" * 60)
    
    # Initialize processor
    processor = GPUParallelProcessor()
    
    # Generate sample financial data
    np.random.seed(42)
    prices = np.random.uniform(100, 200, 100000).astype(np.float32)
    
    print(f"Sample financial data: {len(prices):,} price points")
    print(f"Price range: ${prices.min():.2f} - ${prices.max():.2f}")
    
    # Define custom technical indicator functions
    def simple_moving_average(data, window=20):
        """Simple moving average calculation"""
        if hasattr(data, '__array_interface__'):
            # GPU data (CuPy array)
            import cupy as cp
            if len(data) < window:
                return cp.full(len(data), cp.nan)
            
            kernel = cp.ones(window) / window
            result = cp.convolve(data, kernel, mode='valid')
            padding = cp.full(window - 1, cp.nan)
            return cp.concatenate([padding, result])
        else:
            # CPU data (NumPy array)
            if len(data) < window:
                return np.full(len(data), np.nan)
            
            result = np.convolve(data, np.ones(window) / window, mode='valid')
            padding = np.full(window - 1, np.nan)
            return np.concatenate([padding, result])
    
    def price_momentum(data, period=10):
        """Price momentum calculation"""
        if hasattr(data, '__array_interface__'):
            # GPU data
            import cupy as cp
            if len(data) < period:
                return cp.zeros_like(data)
            
            shifted_data = cp.roll(data, period)
            shifted_data[:period] = data[0]  # Fill initial values
            return ((data - shifted_data) / shifted_data) * 100
        else:
            # CPU data
            if len(data) < period:
                return np.zeros_like(data)
            
            shifted_data = np.roll(data, period)
            shifted_data[:period] = data[0]  # Fill initial values
            return ((data - shifted_data) / shifted_data) * 100
    
    def bollinger_bands(data, window=20, num_std=2):
        """Bollinger Bands calculation"""
        if hasattr(data, '__array_interface__'):
            # GPU data
            import cupy as cp
            sma = simple_moving_average(data, window)
            
            # Calculate rolling standard deviation
            squared_diff = (data - sma) ** 2
            rolling_var = simple_moving_average(squared_diff, window)
            rolling_std = cp.sqrt(rolling_var)
            
            upper_band = sma + (rolling_std * num_std)
            lower_band = sma - (rolling_std * num_std)
            
            return cp.column_stack([lower_band, sma, upper_band])
        else:
            # CPU data
            sma = simple_moving_average(data, window)
            
            squared_diff = (data - sma) ** 2
            rolling_var = simple_moving_average(squared_diff, window)
            rolling_std = np.sqrt(rolling_var)
            
            upper_band = sma + (rolling_std * num_std)
            lower_band = sma - (rolling_std * num_std)
            
            return np.column_stack([lower_band, sma, upper_band])
    
    # Test custom operations
    custom_operations = [
        ('SMA-20', lambda x: simple_moving_average(x, 20)),
        ('Momentum-10', lambda x: price_momentum(x, 10)),
        ('Bollinger Bands', lambda x: bollinger_bands(x, 20, 2))
    ]
    
    print(f"\n🔧 TESTING CUSTOM TECHNICAL INDICATORS")
    print("-" * 50)
    
    for name, operation in custom_operations:
        print(f"\nTesting {name}...")
        
        try:
            start_time = time.perf_counter()
            result = processor.process_array(prices, operation)
            elapsed_time = time.perf_counter() - start_time
            
            # Get processing stats
            stats = processor.get_latest_stats()
            mode_str = stats.processing_mode.value if stats else "unknown"
            
            print(f"  ✅ Completed in {elapsed_time:.4f}s using {mode_str} mode")
            print(f"  📊 Result shape: {result.shape}")
            
            # Show sample values (avoid NaN)
            valid_mask = ~np.isnan(result.flat) if result.ndim > 1 else ~np.isnan(result)
            if np.any(valid_mask):
                if result.ndim > 1:
                    valid_data = result[valid_mask[:len(result)]][:5]  # First 5 valid rows
                    print(f"  📈 Sample values: {valid_data}")
                else:
                    valid_data = result[valid_mask][:5]  # First 5 valid values
                    print(f"  📈 Sample values: {valid_data}")
            
        except Exception as e:
            print(f"  ❌ Error: {str(e)}")

def demonstrate_memory_efficiency():
    """Demonstrate memory-efficient processing of large datasets"""
    print("\n" + "=" * 60)
    print("MEMORY-EFFICIENT LARGE DATA PROCESSING DEMONSTRATION")
    print("=" * 60)
    
    # Configure for memory efficiency
    config = ProcessingConfig(
        mode=ProcessingMode.AUTO,
        chunk_size=250000,  # Process in 250K chunks
        max_memory_usage=60.0,  # Use up to 60% of GPU memory
        use_streams=True,
        stream_count=4,
        enable_overlap=True
    )
    
    processor = GPUParallelProcessor(config)
    
    # Generate large dataset
    print("Generating large dataset...")
    large_size = 5000000  # 5 million points
    np.random.seed(42)
    large_data = np.random.random(large_size).astype(np.float32)
    
    print(f"Dataset size: {large_size:,} points ({large_data.nbytes / 1024**2:.1f} MB)")
    
    # Test memory-intensive operations
    operations = ['sort', 'cumsum', 'rolling_mean']
    
    print(f"\n🔄 PROCESSING LARGE DATASET")
    print("-" * 40)
    
    for operation in operations:
        print(f"\nProcessing {operation}...")
        
        try:
            start_time = time.perf_counter()
            
            if operation == 'rolling_mean':
                result = processor.process_array(large_data, operation, window=50)
            else:
                result = processor.process_array(large_data, operation)
            
            elapsed_time = time.perf_counter() - start_time
            
            # Get processing stats
            stats = processor.get_latest_stats()
            
            print(f"  ✅ Completed in {elapsed_time:.2f}s")
            print(f"  🔧 Mode: {stats.processing_mode.value}")
            print(f"  📦 Chunks: {stats.chunk_count}")
            print(f"  ⚡ Speedup: {stats.speedup_factor:.2f}x")
            print(f"  💾 Result size: {result.nbytes / 1024**2:.1f} MB")
            
        except Exception as e:
            print(f"  ❌ Error: {str(e)}")

def main():
    """Main demonstration function"""
    print("🚀 GPU PARALLEL PROCESSING SYSTEM DEMONSTRATION")
    print("This demo showcases high-performance GPU-accelerated data processing")
    print()
    
    try:
        # 1. GPU Hardware Detection
        gpu_info = demonstrate_gpu_detection()
        
        # 2. Basic Processing
        processor = demonstrate_basic_processing()
        
        # 3. Performance Comparison
        suite = demonstrate_performance_comparison()
        
        # 4. Custom Operations
        demonstrate_custom_operations()
        
        # 5. Memory Efficiency (only if GPU available)
        if gpu_info.gpu_available:
            demonstrate_memory_efficiency()
        else:
            print("\n⚠️  Skipping memory efficiency demo (GPU not available)")
        
        # Final summary
        print("\n" + "=" * 60)
        print("DEMONSTRATION COMPLETE")
        print("=" * 60)
        
        if gpu_info.gpu_available:
            print("✅ GPU processing system is fully functional")
            print(f"📊 GPU Capability Level: {gpu_info.capability_level.value.upper()}")
            if suite.summary_stats['avg_speedup'] > 2:
                print(f"⚡ Excellent performance with {suite.summary_stats['avg_speedup']:.1f}x average speedup")
            else:
                print(f"📈 Moderate performance with {suite.summary_stats['avg_speedup']:.1f}x average speedup")
        else:
            print("ℹ️  GPU not available - CPU processing demonstrated")
            print("💡 Install CUDA and CuPy for GPU acceleration")
        
        print("\n🎯 Key Features Demonstrated:")
        print("   • Automatic GPU hardware detection and validation")
        print("   • Seamless CPU/GPU processing mode selection")
        print("   • Built-in operations (sort, math, statistics)")
        print("   • Custom operation support")
        print("   • Performance benchmarking and comparison")
        print("   • Memory-efficient chunked processing")
        print("   • Comprehensive error handling and fallback")
        
        print(f"\n📁 Results and plots saved to: demo_benchmark_results/")
        
    except Exception as e:
        print(f"\n❌ Demo failed with error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()