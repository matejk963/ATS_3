"""
Performance tests for complete parameter generation system.

Tests loading, memory usage, and generation speed.
"""

import time
import psutil
import os
from src.gpu_parallel_processing.parameter_combinations import (
    generate_combination_batch,
    get_combination_sample,
    get_combination_counts,
    export_combinations_to_file
)


def test_generation_performance():
    """Test parameter generation performance metrics."""
    print("🚀 Parameter Generation Performance Test")
    print("=" * 50)
    
    # Get system info
    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss / 1024 / 1024  # MB
    
    print(f"💾 Initial memory usage: {initial_memory:.1f} MB")
    
    # Test different batch sizes
    batch_sizes = [10, 50, 100, 500]
    
    for batch_size in batch_sizes:
        print(f"\n📊 Testing batch size: {batch_size}")
        
        start_time = time.time()
        start_memory = process.memory_info().rss / 1024 / 1024
        
        # Generate batch
        batch = generate_combination_batch(0, batch_size)
        
        end_time = time.time()
        end_memory = process.memory_info().rss / 1024 / 1024
        
        generation_time = end_time - start_time
        memory_used = end_memory - start_memory
        rate = len(batch) / generation_time if generation_time > 0 else 0
        
        print(f"   ⏱️  Time: {generation_time:.3f} seconds")
        print(f"   💾 Memory: +{memory_used:.1f} MB")
        print(f"   📈 Rate: {rate:.1f} combinations/second")
        print(f"   ✅ Generated: {len(batch)} combinations")
    
    # Test large scale estimation
    counts = get_combination_counts()
    total_combinations = counts['total_combinations_estimate']
    
    print(f"\n🎯 Total combinations estimated: {total_combinations:,}")
    
    # Estimate full generation time based on small batch performance
    small_batch_start = time.time()
    small_batch = generate_combination_batch(0, 100)
    small_batch_time = time.time() - small_batch_start
    
    if small_batch_time > 0:
        estimated_full_time_minutes = (small_batch_time * total_combinations / len(small_batch)) / 60
        print(f"⏳ Estimated full generation time: {estimated_full_time_minutes:.1f} minutes")
    
    # Memory projection
    final_memory = process.memory_info().rss / 1024 / 1024
    total_memory_used = final_memory - initial_memory
    
    if len(small_batch) > 0:
        memory_per_combo = total_memory_used / len(small_batch)
        estimated_full_memory_gb = (memory_per_combo * total_combinations) / 1024
        print(f"💾 Estimated full generation memory: {estimated_full_memory_gb:.1f} GB")
    
    print(f"\n🏁 Performance test complete!")
    print(f"📋 Final memory usage: {final_memory:.1f} MB")


def test_export_performance():
    """Test export performance for different file sizes."""
    print("\n💾 Export Performance Test")
    print("=" * 30)
    
    export_sizes = [10, 50, 100]
    
    for size in export_sizes:
        print(f"\n📁 Testing export of {size} combinations...")
        
        # Generate combinations
        combinations = generate_combination_batch(0, size)
        
        # Test export performance
        start_time = time.time()
        
        output_file = f"test_export_{size}.json"
        success = export_combinations_to_file(combinations, output_file)
        
        export_time = time.time() - start_time
        
        if success:
            # Get file size
            import os
            file_size_kb = os.path.getsize(output_file) / 1024
            
            print(f"   ⏱️  Export time: {export_time:.3f} seconds")
            print(f"   📏 File size: {file_size_kb:.1f} KB")
            print(f"   📈 Rate: {size / export_time:.1f} combinations/second")
            
            # Clean up
            os.remove(output_file)
        else:
            print(f"   ❌ Export failed")


if __name__ == "__main__":
    print("🧪 Running Parameter Generation Performance Tests")
    print("=" * 60)
    
    test_generation_performance()
    test_export_performance()
    
    print("\n✅ All performance tests complete!")