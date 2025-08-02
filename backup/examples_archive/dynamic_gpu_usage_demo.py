"""
Dynamic GPU Resource Management Demo
Demonstrates the Phase 3.2 implementation with real-world usage examples.
"""
import numpy as np
import pandas as pd
import time
from src.feature_engineering.dynamic_gpu_processor import (
    DynamicGPUBatchProcessor,
    ContinuousIndicatorProcessor,
    AdaptiveRealTimeProcessor
)
from src.feature_engineering.gpu_performance_monitor import (
    GPUUtilizationMonitor,
    GPUBenchmarkValidator,
    DynamicGPUDiagnostics
)


def create_sample_market_data(num_points: int) -> pd.DataFrame:
    """Create sample market data for testing"""
    np.random.seed(42)  # For reproducible results
    
    # Simulate realistic price movements
    close_prices = 100 + np.cumsum(np.random.randn(num_points) * 0.5)
    high_prices = close_prices + np.abs(np.random.randn(num_points) * 0.3)
    low_prices = close_prices - np.abs(np.random.randn(num_points) * 0.3)
    open_prices = np.roll(close_prices, 1)
    open_prices[0] = close_prices[0]
    volumes = np.random.randint(1000, 50000, num_points)
    
    return pd.DataFrame({
        'open': open_prices,
        'high': high_prices,
        'low': low_prices,
        'close': close_prices,
        'volume': volumes
    })


def demo1_dynamic_batch_processing():
    """Demo 1: Dynamic batch processing with adaptive sizing"""
    print("=" * 60)
    print("DEMO 1: Dynamic GPU Batch Processing")
    print("=" * 60)
    
    # Create test data
    data = create_sample_market_data(50000)
    print(f"Created sample data: {len(data)} data points")
    
    # Initialize dynamic processor
    processor = DynamicGPUBatchProcessor(target_memory_usage=0.85, target_core_usage=0.90)
    print(f"Initialized DynamicGPUBatchProcessor with targets: 85% memory, 90% core")
    
    # Process with dynamic batching
    print("\nStarting dynamic batch processing...")
    start_time = time.time()
    
    results = processor.process_with_dynamic_batching(data)
    
    processing_time = time.time() - start_time
    
    print(f"✅ Processing completed in {processing_time:.2f} seconds")
    print(f"📊 Processing speed: {len(data)/processing_time:.0f} points/second")
    print(f"🎯 Results: {list(results.keys())}")
    print()


def demo2_continuous_streaming():
    """Demo 2: Continuous streaming data processing"""
    print("=" * 60)
    print("DEMO 2: Continuous Streaming Processing")
    print("=" * 60)
    
    # Create streaming data batches
    data_stream = [
        create_sample_market_data(10000) for _ in range(5)
    ]
    print(f"Created streaming data: 5 batches of 10,000 points each")
    
    # Initialize continuous processor
    processor = ContinuousIndicatorProcessor(target_gpu_usage=0.85)
    print("Initialized ContinuousIndicatorProcessor")
    
    # Process streaming data
    print("\nProcessing streaming data...")
    results_count = 0
    
    for result in processor.process_streaming_data(iter(data_stream)):
        results_count += 1
        print(f"  📦 Processed batch {results_count}")
        if results_count >= 5:  # Process all 5 batches
            break
    
    print(f"✅ Completed processing {results_count} streaming batches")
    print()


def demo3_real_time_adaptation():
    """Demo 3: Real-time adaptive processing"""
    print("=" * 60)
    print("DEMO 3: Real-time Adaptive Processing")
    print("=" * 60)
    
    # Create market data feed
    market_feed = [
        create_sample_market_data(7500) for _ in range(4)
    ]
    print(f"Created market data feed: 4 chunks of 7,500 points each")
    
    # Initialize adaptive processor
    processor = AdaptiveRealTimeProcessor(target_memory_usage=0.85, target_core_usage=0.90)
    print("Initialized AdaptiveRealTimeProcessor")
    
    # Process live feed
    print("\nProcessing live market feed...")
    processed_batches = 0
    
    for result in processor.process_live_feed(market_feed):
        processed_batches += 1
        print(f"  ⚡ Processed adaptive batch {processed_batches}")
    
    print(f"✅ Completed processing {processed_batches} adaptive batches")
    print()


def demo4_performance_monitoring():
    """Demo 4: GPU performance monitoring and diagnostics"""
    print("=" * 60)
    print("DEMO 4: GPU Performance Monitoring")
    print("=" * 60)
    
    # Initialize monitoring
    monitor = GPUUtilizationMonitor()
    validator = GPUBenchmarkValidator()
    print("Initialized GPU monitoring and validation tools")
    
    # Get current GPU stats
    stats = monitor.get_real_time_stats()
    print(f"\n📊 Current GPU Statistics:")
    print(f"  🔥 Core Utilization: {stats['core_utilization']:.1f}%")
    print(f"  💾 Memory Utilization: {stats['memory_utilization']:.1f}%")
    print(f"  📦 Memory Used: {stats['memory_used_gb']:.1f} GB")
    print(f"  🆓 Memory Free: {stats['memory_free_gb']:.1f} GB")
    
    # Run a quick benchmark
    print("\n🔍 Running performance benchmark...")
    processor = DynamicGPUBatchProcessor()
    test_data = create_sample_market_data(25000)
    
    # Start monitoring
    monitor.start_monitoring(interval=0.5)
    start_time = time.time()
    
    # Run processing
    results = processor.process_with_dynamic_batching(test_data)
    processing_time = time.time() - start_time
    
    # Stop monitoring and analyze
    time.sleep(1.0)  # Allow final monitoring samples
    monitor.stop_monitoring()
    
    # Get average utilization during processing
    avg_stats = monitor.calculate_average_utilization()
    
    print(f"\n📈 Benchmark Results:")
    print(f"  ⏱️  Processing Time: {processing_time:.2f} seconds")
    print(f"  🚀 Processing Speed: {len(test_data)/processing_time:.0f} points/second")
    if avg_stats:
        print(f"  📊 Average GPU Core: {avg_stats['avg_core_utilization']:.1f}%")
        print(f"  🔝 Peak GPU Core: {avg_stats['peak_core_utilization']:.1f}%")
        print(f"  💾 Average Memory: {avg_stats['avg_memory_utilization']:.1f}%")
    
    print()


def main():
    """Run all demos"""
    print("🚀 Dynamic GPU Resource Management Demo")
    print("Phase 3.2 Implementation - GPU Utilization Analysis & Optimization")
    print()
    
    try:
        demo1_dynamic_batch_processing()
        demo2_continuous_streaming()
        demo3_real_time_adaptation()
        demo4_performance_monitoring()
        
        print("=" * 60)
        print("✅ ALL DEMOS COMPLETED SUCCESSFULLY")
        print("=" * 60)
        print()
        print("🎯 Key Features Demonstrated:")
        print("  ✅ Dynamic GPU batch sizing based on target utilization")
        print("  ✅ Continuous streaming data processing")
        print("  ✅ Real-time adaptive resource management")
        print("  ✅ Comprehensive GPU performance monitoring")
        print("  ✅ Hardware-agnostic dynamic scaling")
        print()
        print("📊 Implementation Status: COMPLETE")
        print("🚀 Ready for Phase 4 enhancement")
        
    except Exception as e:
        print(f"❌ Demo failed with error: {e}")
        print("🔧 Check GPU availability and dependencies")


if __name__ == "__main__":
    main()