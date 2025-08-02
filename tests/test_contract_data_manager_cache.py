"""
Tests for contract data manager caching functionality (Phase 1.1.5).

Tests LRU cache, memory management, and performance optimization.
"""

import pytest
import pandas as pd
import tempfile
import time
from pathlib import Path
from src.gpu_parallel_processing.contract_data_manager import ContractDataManager


@pytest.fixture
def temp_data_dir():
    """Create temporary data directory for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def sample_contract_data():
    """Create sample contract data with known memory footprint."""
    # Create larger dataset for better memory testing
    size = 1000
    return pd.DataFrame({
        'open': [100.0 + i * 0.1 for i in range(size)],
        'high': [105.0 + i * 0.1 for i in range(size)],
        'low': [95.0 + i * 0.1 for i in range(size)],
        'close': [103.0 + i * 0.1 for i in range(size)],
        'volume': [1000 + i * 10 for i in range(size)]
    })


@pytest.fixture
def contracts_setup(temp_data_dir, sample_contract_data):
    """Create multiple test contract files."""
    contract_names = ["contract_a", "contract_b", "contract_c"]
    
    for name in contract_names:
        contract_file = temp_data_dir / f"{name}_tr_ba_data.parquet"
        sample_contract_data.to_parquet(contract_file)
    
    return contract_names


class TestCacheInitialization:
    """Test cache initialization and configuration."""
    
    def test_cache_initialization(self, temp_data_dir):
        """Test cache initialization with different configurations."""
        # Default configuration
        manager1 = ContractDataManager(str(temp_data_dir))
        assert manager1.max_cached_contracts == 3
        assert len(manager1.data_cache) == 0
        assert manager1.cache_hits == 0
        assert manager1.cache_misses == 0
        
        # Custom configuration
        manager2 = ContractDataManager(str(temp_data_dir), max_cached_contracts=5)
        assert manager2.max_cached_contracts == 5
    
    def test_initial_cache_stats(self, temp_data_dir):
        """Test initial cache statistics."""
        manager = ContractDataManager(str(temp_data_dir))
        
        stats = manager.get_cache_stats()
        
        assert stats['cache_hits'] == 0
        assert stats['cache_misses'] == 0
        assert stats['cache_evictions'] == 0
        assert stats['hit_rate_percent'] == 0
        assert stats['cached_contracts'] == 0
        assert stats['current_memory_mb'] == 0


class TestBasicCaching:
    """Test basic caching functionality."""
    
    def test_cache_miss_and_hit(self, temp_data_dir, contracts_setup):
        """Test cache miss followed by cache hit."""
        manager = ContractDataManager(str(temp_data_dir), max_cached_contracts=2)
        
        contract_name = contracts_setup[0]
        
        # First load should be cache miss
        data1 = manager.load_contract_data(contract_name)
        assert manager.cache_misses == 1
        assert manager.cache_hits == 0
        assert manager.is_cached(contract_name) == True
        
        # Second load should be cache hit
        data2 = manager.load_contract_data(contract_name)
        assert manager.cache_misses == 1
        assert manager.cache_hits == 1
        
        # Data should be identical
        pd.testing.assert_frame_equal(data1, data2)
    
    def test_get_cached_data(self, temp_data_dir, contracts_setup):
        """Test getting cached data without triggering load."""
        manager = ContractDataManager(str(temp_data_dir))
        
        contract_name = contracts_setup[0]
        
        # Initially not cached
        assert manager.get_cached_data(contract_name) is None
        
        # Load data
        original_data = manager.load_contract_data(contract_name)
        
        # Now should be cached
        cached_data = manager.get_cached_data(contract_name)
        assert cached_data is not None
        pd.testing.assert_frame_equal(original_data, cached_data)
    
    def test_is_cached_method(self, temp_data_dir, contracts_setup):
        """Test is_cached method."""
        manager = ContractDataManager(str(temp_data_dir))
        
        contract_name = contracts_setup[0]
        
        # Initially not cached
        assert manager.is_cached(contract_name) == False
        
        # Load data
        manager.load_contract_data(contract_name)
        
        # Now should be cached
        assert manager.is_cached(contract_name) == True


class TestLRUEviction:
    """Test LRU cache eviction mechanism."""
    
    def test_lru_eviction_by_count(self, temp_data_dir, contracts_setup):
        """Test LRU eviction when count limit is reached."""
        manager = ContractDataManager(str(temp_data_dir), max_cached_contracts=2)
        
        contract_a, contract_b, contract_c = contracts_setup
        
        # Load first two contracts
        manager.load_contract_data(contract_a)
        manager.load_contract_data(contract_b)
        
        assert len(manager.data_cache) == 2
        assert manager.is_cached(contract_a) == True
        assert manager.is_cached(contract_b) == True
        
        # Load third contract - should evict first (LRU)
        manager.load_contract_data(contract_c)
        
        assert len(manager.data_cache) == 2
        assert manager.is_cached(contract_a) == False  # Evicted
        assert manager.is_cached(contract_b) == True
        assert manager.is_cached(contract_c) == True
        assert manager.cache_evictions == 1
    
    def test_lru_access_order_update(self, temp_data_dir, contracts_setup):
        """Test that accessing cached data updates LRU order."""
        manager = ContractDataManager(str(temp_data_dir), max_cached_contracts=2)
        
        contract_a, contract_b, contract_c = contracts_setup
        
        # Load contracts A and B
        manager.load_contract_data(contract_a)
        manager.load_contract_data(contract_b)
        
        # Access contract A (should move it to end of LRU)
        manager.load_contract_data(contract_a)  # Cache hit
        
        # Load contract C - should evict B (now LRU), not A
        manager.load_contract_data(contract_c)
        
        assert manager.is_cached(contract_a) == True   # Should still be cached
        assert manager.is_cached(contract_b) == False  # Should be evicted
        assert manager.is_cached(contract_c) == True


class TestCacheMemoryManagement:
    """Test cache memory management and tracking."""
    
    def test_memory_tracking(self, temp_data_dir, contracts_setup):
        """Test memory usage tracking."""
        manager = ContractDataManager(str(temp_data_dir))
        
        contract_name = contracts_setup[0]
        
        # Initial memory should be zero
        assert manager.current_cache_memory_mb == 0.0
        
        # Load contract
        data = manager.load_contract_data(contract_name)
        expected_memory = data.memory_usage(deep=True).sum() / (1024 * 1024)
        
        # Memory should be tracked
        assert manager.current_cache_memory_mb > 0
        assert abs(manager.current_cache_memory_mb - expected_memory) < 0.1  # Allow small differences
    
    def test_memory_tracking_with_eviction(self, temp_data_dir, contracts_setup):
        """Test memory tracking with cache eviction."""
        manager = ContractDataManager(str(temp_data_dir), max_cached_contracts=2)
        
        contract_a, contract_b, contract_c = contracts_setup
        
        # Load two contracts
        manager.load_contract_data(contract_a)
        memory_after_a = manager.current_cache_memory_mb
        
        manager.load_contract_data(contract_b)
        memory_after_b = manager.current_cache_memory_mb
        
        # Memory should increase
        assert memory_after_b > memory_after_a
        
        # Load third contract (triggers eviction)
        manager.load_contract_data(contract_c)
        memory_after_c = manager.current_cache_memory_mb
        
        # Memory should be approximately the same as after loading B
        # (one contract evicted, one added)
        assert abs(memory_after_c - memory_after_b) < memory_after_a * 0.1


class TestCacheStatistics:
    """Test cache statistics and performance metrics."""
    
    def test_hit_rate_calculation(self, temp_data_dir, contracts_setup):
        """Test hit rate calculation."""
        manager = ContractDataManager(str(temp_data_dir))
        
        contract_name = contracts_setup[0]
        
        # Load contract multiple times
        for _ in range(3):
            manager.load_contract_data(contract_name)
        
        stats = manager.get_cache_stats()
        
        # Should have 1 miss and 2 hits = 66.7% hit rate
        assert stats['cache_misses'] == 1
        assert stats['cache_hits'] == 2
        assert abs(stats['hit_rate_percent'] - 66.7) < 0.1
    
    def test_cache_details(self, temp_data_dir, contracts_setup):
        """Test detailed cache information."""
        manager = ContractDataManager(str(temp_data_dir))
        
        contract_name = contracts_setup[0]
        
        # Load contract
        data = manager.load_contract_data(contract_name)
        
        # Access it again to increase access count
        manager.load_contract_data(contract_name)
        
        details = manager.get_cache_details()
        
        assert contract_name in details
        contract_details = details[contract_name]
        
        assert contract_details['access_count'] == 2
        assert contract_details['row_count'] == len(data)
        assert contract_details['memory_mb'] > 0
        assert contract_details['cached_duration_seconds'] >= 0
        assert contract_details['last_accessed_seconds_ago'] >= 0


class TestCacheOperations:
    """Test cache operation methods."""
    
    def test_clear_specific_contract(self, temp_data_dir, contracts_setup):
        """Test clearing specific contract from cache."""
        manager = ContractDataManager(str(temp_data_dir))
        
        contract_a, contract_b = contracts_setup[:2]
        
        # Load both contracts
        manager.load_contract_data(contract_a)
        manager.load_contract_data(contract_b)
        
        assert len(manager.data_cache) == 2
        
        # Clear specific contract
        manager.clear_cache(contract_a)
        
        assert len(manager.data_cache) == 1
        assert manager.is_cached(contract_a) == False
        assert manager.is_cached(contract_b) == True
    
    def test_clear_entire_cache(self, temp_data_dir, contracts_setup):
        """Test clearing entire cache."""
        manager = ContractDataManager(str(temp_data_dir))
        
        # Load multiple contracts
        for contract in contracts_setup:
            manager.load_contract_data(contract)
        
        assert len(manager.data_cache) == len(contracts_setup)
        
        # Clear entire cache
        manager.clear_cache()
        
        assert len(manager.data_cache) == 0
        assert manager.current_cache_memory_mb == 0.0
        
        for contract in contracts_setup:
            assert manager.is_cached(contract) == False
    
    def test_preload_contracts(self, temp_data_dir, contracts_setup):
        """Test preloading multiple contracts."""
        manager = ContractDataManager(str(temp_data_dir))
        
        # Preload contracts
        results = manager.preload_contracts(contracts_setup)
        
        # All should be successful
        assert all(results.values())
        assert len(results) == len(contracts_setup)
        
        # All should be cached
        for contract in contracts_setup:
            assert manager.is_cached(contract) == True
    
    def test_preload_with_failures(self, temp_data_dir, contracts_setup):
        """Test preloading with some failures."""
        manager = ContractDataManager(str(temp_data_dir))
        
        # Include non-existent contract
        contracts_to_preload = contracts_setup + ["nonexistent_contract"]
        
        results = manager.preload_contracts(contracts_to_preload)
        
        # Existing contracts should succeed, non-existent should fail
        for contract in contracts_setup:
            assert results[contract] == True
        
        assert results["nonexistent_contract"] == False


class TestCacheOptimization:
    """Test cache optimization functionality."""
    
    def test_cache_optimization_basic(self, temp_data_dir, contracts_setup):
        """Test basic cache optimization."""
        manager = ContractDataManager(str(temp_data_dir))
        
        # Load contracts
        for contract in contracts_setup:
            manager.load_contract_data(contract)
        
        # Run optimization immediately (should not remove anything)
        stats = manager.optimize_cache()
        
        assert stats['contracts_analyzed'] == len(contracts_setup)
        assert stats['contracts_removed'] == 0  # Too recent to remove
    
    def test_cache_optimization_with_time_delay(self, temp_data_dir, contracts_setup):
        """Test cache optimization with simulated time delay."""
        manager = ContractDataManager(str(temp_data_dir))
        
        # Load contracts
        for contract in contracts_setup:
            manager.load_contract_data(contract)
        
        # Manually adjust last access time to simulate old data
        for contract_code in manager.cache_metadata:
            manager.cache_metadata[contract_code]['last_accessed'] = time.time() - 120  # 2 minutes ago
            manager.cache_metadata[contract_code]['cached_at'] = time.time() - 300     # 5 minutes ago
            manager.cache_metadata[contract_code]['access_count'] = 1  # Low access count
        
        # Run optimization
        stats = manager.optimize_cache()
        
        # Should remove low-frequency contracts
        assert stats['contracts_removed'] > 0


class TestPerformanceMetrics:
    """Test performance-related metrics and timing."""
    
    def test_load_timing(self, temp_data_dir, contracts_setup):
        """Test that cache hits are faster than cache misses."""
        manager = ContractDataManager(str(temp_data_dir))
        
        contract_name = contracts_setup[0]
        
        # Time cache miss
        start_time = time.time()
        manager.load_contract_data(contract_name)
        miss_time = time.time() - start_time
        
        # Time cache hit
        start_time = time.time()
        manager.load_contract_data(contract_name)
        hit_time = time.time() - start_time
        
        # Cache hit should be significantly faster
        assert hit_time < miss_time * 0.5  # At least 50% faster
    
    def test_memory_efficiency_calculation(self, temp_data_dir, contracts_setup):
        """Test memory efficiency metrics."""
        manager = ContractDataManager(str(temp_data_dir))
        
        # Load contract multiple times
        contract_name = contracts_setup[0]
        
        for _ in range(5):
            manager.load_contract_data(contract_name)
        
        stats = manager.get_cache_stats()
        
        # Should show memory efficiency gains
        assert stats['memory_efficiency_mb'] >= 0
        assert stats['avg_memory_per_contract_mb'] > 0


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_cache_with_zero_max_contracts(self, temp_data_dir):
        """Test cache behavior with zero max contracts."""
        # This should still work but never cache anything
        manager = ContractDataManager(str(temp_data_dir), max_cached_contracts=0)
        
        # Create test contract
        sample_data = pd.DataFrame({
            'open': [100.0], 'high': [105.0], 'low': [95.0], 
            'close': [103.0], 'volume': [1000]
        })
        
        contract_file = Path(temp_data_dir) / "test_tr_ba_data.parquet"
        sample_data.to_parquet(contract_file)
        
        # Load contract
        data = manager.load_contract_data("test")
        
        # Should not be cached
        assert len(manager.data_cache) == 0
        assert manager.is_cached("test") == False
    
    def test_clear_nonexistent_contract(self, temp_data_dir):
        """Test clearing non-existent contract from cache."""
        manager = ContractDataManager(str(temp_data_dir))
        
        # Should not raise error
        manager.clear_cache("nonexistent")
        
        assert len(manager.data_cache) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])