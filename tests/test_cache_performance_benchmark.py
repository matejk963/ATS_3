"""
Performance benchmark tests for contract data manager caching.

Tests cache performance, memory usage, and scalability.
"""

import pytest
import pandas as pd
import tempfile
import time
import psutil
import os
from pathlib import Path
from src.gpu_parallel_processing.contract_data_manager import ContractDataManager


@pytest.fixture
def large_contract_data():
    """Create large contract data for performance testing."""
    size = 10000  # 10K rows for more realistic testing
    return pd.DataFrame({
        'open': [100.0 + i * 0.01 for i in range(size)],
        'high': [105.0 + i * 0.01 for i in range(size)],
        'low': [95.0 + i * 0.01 for i in range(size)],
        'close': [103.0 + i * 0.01 for i in range(size)],
        'volume': [1000 + i for i in range(size)]
    })


@pytest.fixture
def performance_contracts_setup(temp_data_dir, large_contract_data):
    """Create multiple large test contract files for performance testing."""
    contract_names = [f"perf_contract_{i:02d}" for i in range(10)]
    
    for name in contract_names:
        contract_file = temp_data_dir / f"{name}_tr_ba_data.parquet"
        large_contract_data.to_parquet(contract_file)
    
    return contract_names


@pytest.fixture
def temp_data_dir():
    """Create temporary data directory for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


class TestCachePerformance:
    """Test cache performance characteristics."""
    
    def test_cache_hit_performance(self, temp_data_dir, performance_contracts_setup):
        """Test cache hit performance vs miss performance."""
        manager = ContractDataManager(str(temp_data_dir), max_cached_contracts=5)
        
        contract_name = performance_contracts_setup[0]
        
        # Measure cache miss time
        miss_times = []
        for _ in range(3):
            manager.clear_cache(contract_name)
            
            start_time = time.time()
            manager.load_contract_data(contract_name)
            miss_time = time.time() - start_time
            miss_times.append(miss_time)
        
        avg_miss_time = sum(miss_times) / len(miss_times)
        
        # Measure cache hit time
        hit_times = []
        for _ in range(10):
            start_time = time.time()
            manager.load_contract_data(contract_name)
            hit_time = time.time() - start_time
            hit_times.append(hit_time)
        
        avg_hit_time = sum(hit_times) / len(hit_times)
        
        # Cache hits should be significantly faster
        speedup_factor = avg_miss_time / avg_hit_time
        
        print(f"Average miss time: {avg_miss_time:.4f}s")
        print(f"Average hit time: {avg_hit_time:.4f}s")
        print(f"Speedup factor: {speedup_factor:.1f}x")
        
        assert speedup_factor > 5  # At least 5x faster
        assert avg_hit_time < 0.1  # Cache hits should be very fast
    
    def test_concurrent_access_performance(self, temp_data_dir, performance_contracts_setup):
        """Test performance with multiple contracts being accessed."""
        manager = ContractDataManager(str(temp_data_dir), max_cached_contracts=5)
        
        # Load multiple contracts
        contracts_to_test = performance_contracts_setup[:5]
        
        start_time = time.time()
        
        # Load all contracts (cache misses)
        for contract in contracts_to_test:
            manager.load_contract_data(contract)
        
        initial_load_time = time.time() - start_time
        
        # Access all contracts multiple times (cache hits)
        start_time = time.time()
        
        for _ in range(10):
            for contract in contracts_to_test:
                manager.load_contract_data(contract)
        
        cached_access_time = time.time() - start_time
        
        # Cached access should be much faster per operation
        avg_initial_time_per_contract = initial_load_time / len(contracts_to_test)
        avg_cached_time_per_contract = cached_access_time / (10 * len(contracts_to_test))
        
        speedup = avg_initial_time_per_contract / avg_cached_time_per_contract
        
        print(f"Initial load time per contract: {avg_initial_time_per_contract:.4f}s")
        print(f"Cached access time per contract: {avg_cached_time_per_contract:.4f}s")
        print(f"Speedup: {speedup:.1f}x")
        
        assert speedup > 3  # At least 3x faster


class TestMemoryPerformance:
    """Test memory usage and efficiency."""
    
    def test_memory_usage_tracking_accuracy(self, temp_data_dir, large_contract_data):
        """Test accuracy of memory usage tracking."""
        manager = ContractDataManager(str(temp_data_dir))
        
        # Create test contract
        contract_file = temp_data_dir / "memory_test_tr_ba_data.parquet"
        large_contract_data.to_parquet(contract_file)
        
        # Get process memory before loading
        process = psutil.Process(os.getpid())
        memory_before = process.memory_info().rss / (1024 * 1024)  # MB
        
        # Load contract
        data = manager.load_contract_data("memory_test")
        
        # Get process memory after loading
        memory_after = process.memory_info().rss / (1024 * 1024)  # MB
        
        # Calculate actual memory increase
        actual_memory_increase = memory_after - memory_before
        
        # Get reported memory usage
        reported_memory = manager.current_cache_memory_mb
        
        # Calculate expected memory usage from DataFrame
        expected_memory = data.memory_usage(deep=True).sum() / (1024 * 1024)
        
        print(f"Actual memory increase: {actual_memory_increase:.1f} MB")
        print(f"Reported cache memory: {reported_memory:.1f} MB")
        print(f"Expected DataFrame memory: {expected_memory:.1f} MB")
        
        # Reported memory should be close to expected DataFrame memory
        assert abs(reported_memory - expected_memory) < 1.0  # Within 1MB
    
    def test_memory_efficiency_with_multiple_loads(self, temp_data_dir, performance_contracts_setup):
        """Test memory efficiency when loading same contract multiple times."""
        manager = ContractDataManager(str(temp_data_dir))
        
        contract_name = performance_contracts_setup[0]
        
        # Load contract multiple times
        for _ in range(10):
            manager.load_contract_data(contract_name)
        
        # Should only use memory for one copy
        assert len(manager.data_cache) == 1
        
        # Memory usage should be stable
        cache_stats = manager.get_cache_stats()
        assert cache_stats['memory_efficiency_mb'] > 0  # Should show memory savings
    
    def test_memory_management_with_eviction(self, temp_data_dir, performance_contracts_setup):
        """Test memory management during cache eviction."""
        manager = ContractDataManager(str(temp_data_dir), max_cached_contracts=3)
        
        # Load more contracts than cache can hold
        contracts_to_load = performance_contracts_setup[:5]
        
        memory_usage_history = []
        
        for contract in contracts_to_load:
            manager.load_contract_data(contract)
            memory_usage_history.append(manager.current_cache_memory_mb)
        
        # Memory usage should stabilize after cache limit is reached
        final_memory = memory_usage_history[-1]
        penultimate_memory = memory_usage_history[-2]
        
        # Memory should not grow indefinitely
        assert abs(final_memory - penultimate_memory) < final_memory * 0.1  # Within 10%
        
        # Should have evicted some contracts
        assert manager.cache_evictions > 0


class TestScalabilityPerformance:
    """Test performance scalability with increasing load."""
    
    def test_cache_performance_scaling(self, temp_data_dir, performance_contracts_setup):
        """Test that cache performance scales well with more contracts."""
        manager = ContractDataManager(str(temp_data_dir), max_cached_contracts=8)
        
        # Test with increasing number of contracts
        contract_counts = [1, 3, 5, 8]
        access_times = []
        
        for count in contract_counts:
            contracts_subset = performance_contracts_setup[:count]
            
            # Load all contracts
            for contract in contracts_subset:
                manager.load_contract_data(contract)
            
            # Time accessing all contracts
            start_time = time.time()
            
            for _ in range(5):  # 5 iterations
                for contract in contracts_subset:
                    manager.load_contract_data(contract)
            
            total_time = time.time() - start_time
            avg_time_per_access = total_time / (5 * count)
            access_times.append(avg_time_per_access)
        
        print(f"Access times per contract: {access_times}")
        
        # Access time per contract should remain roughly constant
        # (allowing for some variation due to system factors)
        time_variation = max(access_times) / min(access_times)
        assert time_variation < 3  # No more than 3x variation
    
    def test_hit_rate_stability(self, temp_data_dir, performance_contracts_setup):
        """Test that hit rate remains stable under load."""
        manager = ContractDataManager(str(temp_data_dir), max_cached_contracts=5)
        
        contracts_to_use = performance_contracts_setup[:5]
        
        # Initial loading phase
        for contract in contracts_to_use:
            manager.load_contract_data(contract)
        
        # Heavy usage phase
        for iteration in range(20):
            for contract in contracts_to_use:
                manager.load_contract_data(contract)
            
            # Check hit rate periodically
            if iteration % 5 == 0:
                stats = manager.get_cache_stats()
                hit_rate = stats['hit_rate_percent']
                
                # Hit rate should be high and stable
                if iteration > 0:  # Skip first check
                    assert hit_rate > 80  # At least 80% hit rate


class TestLargeDatasetPerformance:
    """Test performance with larger datasets."""
    
    @pytest.mark.slow
    def test_very_large_dataset_performance(self, temp_data_dir):
        """Test performance with very large datasets."""
        # Create very large dataset
        size = 100000  # 100K rows
        large_data = pd.DataFrame({
            'open': [100.0 + i * 0.001 for i in range(size)],
            'high': [105.0 + i * 0.001 for i in range(size)],
            'low': [95.0 + i * 0.001 for i in range(size)],
            'close': [103.0 + i * 0.001 for i in range(size)],
            'volume': [1000 + i for i in range(size)]
        })
        
        contract_file = temp_data_dir / "large_dataset_tr_ba_data.parquet"
        large_data.to_parquet(contract_file)
        
        manager = ContractDataManager(str(temp_data_dir))
        
        # Time initial load
        start_time = time.time()
        data = manager.load_contract_data("large_dataset")
        load_time = time.time() - start_time
        
        # Time cached access
        start_time = time.time()
        cached_data = manager.load_contract_data("large_dataset")
        cache_time = time.time() - start_time
        
        print(f"Large dataset ({size:,} rows):")
        print(f"Initial load time: {load_time:.3f}s")
        print(f"Cached access time: {cache_time:.3f}s")
        print(f"Speedup: {load_time/cache_time:.1f}x")
        
        # Should be much faster from cache
        assert cache_time < load_time * 0.1  # At least 10x faster
        assert len(data) == size
        pd.testing.assert_frame_equal(data, cached_data)


class TestCacheOptimizationPerformance:
    """Test cache optimization performance."""
    
    def test_optimization_performance(self, temp_data_dir, performance_contracts_setup):
        """Test that cache optimization doesn't significantly impact performance."""
        manager = ContractDataManager(str(temp_data_dir), max_cached_contracts=8)
        
        # Load contracts
        for contract in performance_contracts_setup[:8]:
            manager.load_contract_data(contract)
        
        # Time normal operations
        start_time = time.time()
        for _ in range(10):
            for contract in performance_contracts_setup[:5]:
                manager.load_contract_data(contract)
        normal_time = time.time() - start_time
        
        # Time operations with optimization
        start_time = time.time()
        for i in range(10):
            for contract in performance_contracts_setup[:5]:
                manager.load_contract_data(contract)
            
            # Run optimization every few iterations
            if i % 3 == 0:
                manager.optimize_cache()
        
        optimized_time = time.time() - start_time
        
        # Optimization should not significantly slow down operations
        overhead = (optimized_time - normal_time) / normal_time * 100
        print(f"Optimization overhead: {overhead:.1f}%")
        
        assert overhead < 20  # Less than 20% overhead


def run_performance_benchmark():
    """Run comprehensive performance benchmark."""
    print("🚀 Running Contract Data Manager Cache Performance Benchmark")
    print("=" * 70)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create test data
        print("📊 Creating test data...")
        size = 50000
        test_data = pd.DataFrame({
            'open': [100.0 + i * 0.001 for i in range(size)],
            'high': [105.0 + i * 0.001 for i in range(size)],
            'low': [95.0 + i * 0.001 for i in range(size)],
            'close': [103.0 + i * 0.001 for i in range(size)],
            'volume': [1000 + i for i in range(size)]
        })
        
        contracts = ["benchmark_a", "benchmark_b", "benchmark_c"]
        for contract in contracts:
            contract_file = Path(temp_dir) / f"{contract}_tr_ba_data.parquet"
            test_data.to_parquet(contract_file)
        
        print(f"✅ Created {len(contracts)} contracts with {size:,} rows each")
        
        # Initialize manager
        manager = ContractDataManager(temp_dir, max_cached_contracts=3)
        
        # Benchmark cache miss performance
        print("\n⏱️  Benchmarking cache miss performance...")
        miss_times = []
        
        for contract in contracts:
            start_time = time.time()
            data = manager.load_contract_data(contract)
            miss_time = time.time() - start_time
            miss_times.append(miss_time)
            print(f"   {contract}: {miss_time:.3f}s ({len(data):,} rows)")
        
        avg_miss_time = sum(miss_times) / len(miss_times)
        
        # Benchmark cache hit performance
        print("\n⚡ Benchmarking cache hit performance...")
        hit_times = []
        
        for _ in range(10):
            for contract in contracts:
                start_time = time.time()
                manager.load_contract_data(contract)
                hit_time = time.time() - start_time
                hit_times.append(hit_time)
        
        avg_hit_time = sum(hit_times) / len(hit_times)
        
        # Results
        speedup = avg_miss_time / avg_hit_time
        
        print(f"\n📈 Performance Results:")
        print(f"   Average cache miss time: {avg_miss_time:.4f}s")
        print(f"   Average cache hit time: {avg_hit_time:.4f}s")
        print(f"   Speedup factor: {speedup:.1f}x")
        
        # Memory efficiency
        stats = manager.get_cache_stats()
        print(f"\n💾 Memory Efficiency:")
        print(f"   Cached contracts: {stats['cached_contracts']}")
        print(f"   Cache memory usage: {stats['current_memory_mb']:.1f} MB")
        print(f"   Memory efficiency: {stats['memory_efficiency_mb']:.1f} MB saved")
        print(f"   Hit rate: {stats['hit_rate_percent']:.1f}%")
        
        print("\n✅ Benchmark complete!")


if __name__ == "__main__":
    # Run benchmark if called directly
    run_performance_benchmark()
    
    # Run tests with: pytest tests/test_cache_performance_benchmark.py -v -s
    # Run slow tests with: pytest tests/test_cache_performance_benchmark.py -v -s -m slow