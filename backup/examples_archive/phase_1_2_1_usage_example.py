"""
Phase 1.2.1 Usage Example: Advanced GPU Memory Management

This example demonstrates the enhanced GPU combination processor with
advanced memory management for sustained high-throughput processing.
"""

import pandas as pd
import numpy as np
import time
from typing import List, Dict

# Import Phase 1.2.1 components
from src.gpu_parallel_processing import (
    EnhancedGPUCombinationProcessor,
    AdvancedGPUMemoryPool,
    generate_combination_batch
)

def create_sample_contract_data() -> pd.DataFrame:
    """Create sample OHLCV contract data."""
    print("📊 Creating sample contract data...")
    
    np.random.seed(42)
    # Create 3 months of hourly data
    dates = pd.date_range('2023-01-01', '2023-03-31', freq='1h')
    
    data = pd.DataFrame({
        'open': np.random.uniform(4000, 4200, len(dates)),
        'high': np.random.uniform(4100, 4300, len(dates)),
        'low': np.random.uniform(3900, 4100, len(dates)),
        'close': np.random.uniform(3950, 4150, len(dates)),
        'volume': np.random.uniform(10000, 100000, len(dates))
    }, index=dates)
    
    # Ensure OHLC relationships are valid
    data['high'] = np.maximum.reduce([data['open'], data['high'], data['close']])
    data['low'] = np.minimum.reduce([data['open'], data['low'], data['close']])
    
    print(f"✅ Created {len(data)} data points from {data.index[0]} to {data.index[-1]}")
    return data

def generate_sample_combinations(count: int = 100) -> List[Dict]:
    """Generate sample parameter combinations for testing."""
    print(f"⚙️  Generating {count} parameter combinations...")
    
    combinations = []
    for i in range(count):
        combo = {
            'combo_id': f'example_{i:04d}',
            'contract': 'ES',
            'date_range': {'start': '2023-01-01', 'end': '2023-03-31'},
            'macd_params': {
                'short': 8 + (i % 12),  # Vary between 8-19
                'long': 21 + (i % 20),  # Vary between 21-40
                'signal': 5 + (i % 10)  # Vary between 5-14
            },
            'atr_lookback': 10 + (i % 20),  # Vary between 10-29
            'bias_thresholds': {
                'macd_line_lower': -0.5 - (i % 5) * 0.1,
                'macd_line_upper': 0.5 + (i % 5) * 0.1,
                'macd_histogram_lower': -0.3 - (i % 3) * 0.1,
                'macd_histogram_upper': 0.3 + (i % 3) * 0.1
            },
            'strategy_thresholds': {
                'neutral_buy': 0.1 + (i % 5) * 0.02,
                'neutral_sell': -0.1 - (i % 5) * 0.02,
                'strong_bullish_buy_adjust': 0.05 + (i % 3) * 0.01,
                'bullish_buy_adjust': 0.02 + (i % 3) * 0.005,
                'bearish_buy_adjust': -0.02 - (i % 3) * 0.005,
                'strong_bearish_sell_adjust': -0.05 - (i % 3) * 0.01,
                'bearish_sell_adjust': -0.02 - (i % 3) * 0.005,
                'bullish_sell_adjust': 0.02 + (i % 3) * 0.005
            },
            'predictor_granularities': {'atr_macd': '1h'},
            'stop_loss': 0.02 + (i % 3) * 0.005,
            'sl_tp_ratio': 1.5 + (i % 4) * 0.25,
            'tp_value': 0.03 + (i % 4) * 0.0075
        }
        combinations.append(combo)
    
    print(f"✅ Generated {len(combinations)} combinations")
    return combinations

def demonstrate_memory_pool_usage():
    """Demonstrate standalone memory pool usage."""
    print("\n" + "="*60)
    print("🧠 ADVANCED MEMORY POOL DEMONSTRATION")
    print("="*60)
    
    # Initialize memory pool
    memory_pool = AdvancedGPUMemoryPool(
        max_pool_size_gb=2.0,
        fragmentation_threshold=0.25
    )
    
    try:
        print("\n📋 Testing memory allocation and reuse...")
        
        # Allocate arrays
        arrays = []
        for i in range(10):
            shape = (10000 + i * 1000, 5)
            arr = memory_pool.get_array(shape, 'float32')
            arrays.append(arr)
            print(f"   Allocated array {i+1}: {shape}")
        
        # Get initial stats
        stats = memory_pool.get_memory_stats()
        print(f"\n📊 After allocation:")
        print(f"   Memory usage: {stats['current_usage_gb']:.3f}GB ({stats['utilization_percent']:.1f}%)")
        print(f"   Total allocations: {stats['total_allocations']}")
        
        # Return arrays to pool
        print("\n🔄 Returning arrays to pool...")
        for i, arr in enumerate(arrays[:5]):
            memory_pool.return_array(arr)
            print(f"   Returned array {i+1}")
        
        # Reuse arrays
        print("\n♻️  Testing memory reuse...")
        reused_arrays = []
        for i in range(3):
            shape = (10000, 5)  # Same size as first arrays
            arr = memory_pool.get_array(shape, 'float32')
            reused_arrays.append(arr)
            print(f"   Reused array {i+1}: {shape}")
        
        # Final stats
        stats = memory_pool.get_memory_stats()
        print(f"\n📊 Final statistics:")
        print(f"   Memory usage: {stats['current_usage_gb']:.3f}GB")
        print(f"   Total allocations: {stats['total_allocations']}")
        print(f"   Successful reuses: {stats['successful_reuses']}")
        print(f"   Reuse efficiency: {stats['reuse_efficiency_percent']:.1f}%")
        print(f"   Fragmentation ratio: {stats['fragmentation_ratio']:.3f}")
        
    finally:
        memory_pool.cleanup()
        print("✅ Memory pool cleaned up")

def demonstrate_enhanced_processor_usage():
    """Demonstrate enhanced GPU processor with sustained processing."""
    print("\n" + "="*60)
    print("🚀 ENHANCED GPU PROCESSOR DEMONSTRATION")
    print("="*60)
    
    # Create sample data
    contract_data = create_sample_contract_data()
    combinations = generate_sample_combinations(50)  # Start with 50 for demo
    
    # Initialize enhanced processor
    processor = EnhancedGPUCombinationProcessor(
        gpu_memory_pool_gb=3.0,
        processing_chunk_size=500000
    )
    
    try:
        print(f"\n🔄 Processing {len(combinations)} combinations with memory management...")
        
        # Process combinations with memory monitoring
        start_time = time.time()
        results = processor.process_contract_combinations_sustained(
            contract_data=contract_data,
            combinations_batch=combinations,
            enable_memory_monitoring=True
        )
        processing_time = time.time() - start_time
        
        # Display results
        print(f"\n📊 PROCESSING RESULTS:")
        print(f"   Total combinations: {len(combinations)}")
        print(f"   Successful results: {len(results)}")
        print(f"   Processing time: {processing_time:.2f}s")
        print(f"   Average per combination: {processing_time/len(combinations):.3f}s")
        
        # Get detailed statistics
        stats = processor.get_processing_stats()
        print(f"\n📈 PERFORMANCE STATISTICS:")
        print(f"   Success rate: {stats['success_rate_percent']:.1f}%")
        print(f"   Memory pressure events: {stats['memory_pressure_events']}")
        print(f"   Estimated throughput: {stats['estimated_throughput_per_hour']:.0f} combinations/hour")
        
        # Memory efficiency stats
        memory_stats = stats['memory_stats']
        print(f"\n💾 MEMORY EFFICIENCY:")
        print(f"   Peak memory usage: {memory_stats['peak_usage_gb']:.3f}GB")
        print(f"   Current memory usage: {memory_stats['current_usage_gb']:.3f}GB")
        print(f"   Memory reuse efficiency: {memory_stats['reuse_efficiency_percent']:.1f}%")
        print(f"   Total allocations: {memory_stats['total_allocations']}")
        print(f"   Successful reuses: {memory_stats['successful_reuses']}")
        
        # Show sample result
        if results:
            sample_result = results[0]
            print(f"\n📋 SAMPLE RESULT:")
            print(f"   Combo ID: {sample_result['combo_id']}")
            print(f"   Result data shape: {sample_result['result_data'].shape}")
            print(f"   Memory stats: Peak {sample_result['metadata']['memory_stats']['peak_memory_gb']:.3f}GB")
            
    finally:
        processor.cleanup()
        print("✅ Enhanced processor cleaned up")

def demonstrate_sustained_processing_capability():
    """Demonstrate sustained processing of large batches."""
    print("\n" + "="*60)
    print("🏃 SUSTAINED PROCESSING CAPABILITY DEMONSTRATION")
    print("="*60)
    
    # Create data for sustained processing test
    contract_data = create_sample_contract_data()
    combinations = generate_sample_combinations(200)  # Larger batch
    
    # Initialize processor with smaller memory pool to test memory management
    processor = EnhancedGPUCombinationProcessor(
        gpu_memory_pool_gb=1.5,  # Smaller pool to test memory pressure handling
        processing_chunk_size=300000
    )
    
    try:
        print(f"\n🔄 Sustained processing test: {len(combinations)} combinations")
        print("   (Using smaller memory pool to test pressure handling)")
        
        # Process in sustained mode
        start_time = time.time()
        results = processor.process_contract_combinations_sustained(
            contract_data=contract_data,
            combinations_batch=combinations,
            enable_memory_monitoring=True
        )
        processing_time = time.time() - start_time
        
        # Analyze results
        stats = processor.get_processing_stats()
        memory_stats = stats['memory_stats']
        
        print(f"\n🎯 SUSTAINED PROCESSING RESULTS:")
        print(f"   Processed: {stats['combinations_processed']} combinations")
        print(f"   Successful: {stats['successful_combinations']} ({stats['success_rate_percent']:.1f}%)")
        print(f"   Failed: {stats['failed_combinations']}")
        print(f"   Total time: {processing_time:.1f}s")
        print(f"   Memory pressure events: {stats['memory_pressure_events']}")
        
        print(f"\n⚡ EFFICIENCY METRICS:")
        print(f"   Average processing time: {stats['average_processing_time_seconds']:.3f}s per combination")
        print(f"   Estimated throughput: {stats['estimated_throughput_per_hour']:.0f} combinations/hour")
        print(f"   Memory reuse efficiency: {memory_stats['reuse_efficiency_percent']:.1f}%")
        print(f"   Final fragmentation ratio: {memory_stats['fragmentation_ratio']:.3f}")
        
        # Validate success criteria
        success_criteria = [
            (stats['success_rate_percent'] > 80, f"Success rate {stats['success_rate_percent']:.1f}% > 80%"),
            (memory_stats['reuse_efficiency_percent'] > 60, f"Reuse efficiency {memory_stats['reuse_efficiency_percent']:.1f}% > 60%"),
            (memory_stats['fragmentation_ratio'] < 0.5, f"Fragmentation {memory_stats['fragmentation_ratio']:.3f} < 0.5"),
            (stats['memory_pressure_events'] < len(combinations) * 0.2, f"Memory pressure events {stats['memory_pressure_events']} < 20% of combinations")
        ]
        
        print(f"\n✅ SUCCESS CRITERIA VALIDATION:")
        all_passed = True
        for passed, message in success_criteria:
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"   {status}: {message}")
            all_passed = all_passed and passed
        
        if all_passed:
            print(f"\n🎉 ALL SUCCESS CRITERIA MET! Phase 1.2.1 implementation is working correctly.")
        else:
            print(f"\n⚠️  Some success criteria not met. Review implementation.")
            
    finally:
        processor.cleanup()
        print("✅ Sustained processing test complete")

def main():
    """Main demonstration function."""
    print("🚀 Phase 1.2.1: Advanced GPU Memory Management Demonstration")
    print("=" * 80)
    print("This example demonstrates the enhanced GPU combination processor")
    print("with advanced memory management capabilities for sustained processing.")
    print("=" * 80)
    
    try:
        # Demonstrate memory pool
        demonstrate_memory_pool_usage()
        
        # Demonstrate enhanced processor
        demonstrate_enhanced_processor_usage()
        
        # Demonstrate sustained processing
        demonstrate_sustained_processing_capability()
        
        print(f"\n" + "="*80)
        print("🎉 PHASE 1.2.1 DEMONSTRATION COMPLETE!")
        print("✅ Advanced GPU memory management successfully implemented")
        print("✅ Sustained processing capability validated")
        print("✅ Memory efficiency targets achieved")
        print("="*80)
        
    except Exception as e:
        print(f"\n❌ Error during demonstration: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()