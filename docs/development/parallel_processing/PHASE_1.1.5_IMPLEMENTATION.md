# Phase 1.1.5: Cache Implementation

## Overview
**Dependencies**: Phase 1.1.4 completed  
**Track**: Data Management (Track B)

This micro-phase adds LRU caching, memory management, and performance optimization to the contract data manager foundation, completing the data management system.

## Objectives
1. Implement LRU cache mechanism with configurable size
2. Add cache hit/miss tracking and performance metrics
3. Implement memory-efficient data loading with caching
4. Write comprehensive cache performance tests

## Implementation Steps

### Step 1: Extend Contract Data Manager with Caching

Add to `src/gpu_parallel_processing/contract_data_manager.py`:

```python
# Add these imports at the top
import time
from collections import OrderedDict
import gc

# Modify the ContractDataManager class to include caching
class ContractDataManager:
    """
    Contract data manager with LRU caching for efficient loading and validation.
    
    Manages contract data files with automatic path resolution, comprehensive 
    data validation, LRU caching, and performance optimization.
    
    Phase 1.1.4: Foundation implementation with file management and validation.
    Phase 1.1.5: LRU caching and memory management implementation.
    """
    
    def __init__(self, data_directory: str = "data", max_cached_contracts: int = 3):
        """
        Initialize contract data manager with caching.
        
        Args:
            data_directory: Base directory for contract data files
            max_cached_contracts: Maximum number of contracts to cache simultaneously
        """
        self.data_directory = Path(data_directory)
        self.max_cached_contracts = max_cached_contracts
        
        # LRU Cache implementation using OrderedDict
        self.data_cache: OrderedDict[str, pd.DataFrame] = OrderedDict()
        self.cache_metadata: Dict[str, Dict] = {}
        
        # Cache performance tracking
        self.cache_hits = 0
        self.cache_misses = 0
        self.cache_evictions = 0
        self.total_memory_saved_mb = 0.0
        
        # File operation statistics
        self.files_loaded = 0
        self.validation_failures = 0
        self.file_not_found_errors = 0
        
        # Memory management
        self.current_cache_memory_mb = 0.0
        self.max_cache_memory_mb = None  # Will be set based on available memory
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        
        # Validate data directory
        if not self._validate_data_directory():
            raise ValueError(f"Invalid data directory: {self.data_directory}")
        
        # Initialize memory limits
        self._set_memory_limits()
    
    def load_contract_data(self, contract_code: str) -> pd.DataFrame:
        """
        Load contract data with LRU caching.
        
        Args:
            contract_code: Contract identifier (e.g., 'dem07_25')
            
        Returns:
            DataFrame with contract OHLCV data
            
        Raises:
            FileNotFoundError: If contract file doesn't exist
            ValueError: If data validation fails
            Exception: For other loading errors
        """
        start_time = time.time()
        
        try:
            # Check cache first
            if contract_code in self.data_cache:
                self._update_cache_access(contract_code)
                self.cache_hits += 1
                
                load_time = time.time() - start_time
                self.logger.info(f"📋 Cache HIT: {contract_code} (loaded in {load_time:.3f}s)")
                self._log_cache_stats()
                
                return self.data_cache[contract_code]
            
            # Cache miss - load from file
            self.cache_misses += 1
            self.logger.info(f"📂 Cache MISS: Loading {contract_code} from file...")
            
            # Load and validate data
            contract_path = self._resolve_contract_path(contract_code)
            data = pd.read_parquet(contract_path)
            
            validation_result = self._validate_contract_data(data, contract_code)
            if not validation_result.is_valid:
                self.validation_failures += 1
                raise ValueError(f"Data validation failed for {contract_code}: {validation_result.error_message}")
            
            # Calculate memory usage
            memory_usage_mb = data.memory_usage(deep=True).sum() / (1024 * 1024)
            
            # Cache management - check memory limits and evict if necessary
            self._ensure_cache_capacity(memory_usage_mb)
            
            # Cache the data
            self._add_to_cache(contract_code, data, memory_usage_mb, validation_result)
            
            self.files_loaded += 1
            load_time = time.time() - start_time
            
            self.logger.info(f"✅ Loaded {len(data):,} candles from {contract_code} in {load_time:.3f}s")
            self.logger.info(f"💾 Memory usage: {memory_usage_mb:.1f} MB")
            self._log_cache_stats()
            
            return data
            
        except FileNotFoundError as e:
            self.file_not_found_errors += 1
            self.logger.error(f"Contract file not found: {contract_code}")
            raise
        except Exception as e:
            self.logger.error(f"Error loading contract {contract_code}: {e}")
            raise
    
    def get_cached_data(self, contract_code: str) -> Optional[pd.DataFrame]:
        """
        Get cached data without loading from file.
        
        Args:
            contract_code: Contract identifier
            
        Returns:
            DataFrame if cached, None otherwise
        """
        if contract_code in self.data_cache:
            self._update_cache_access(contract_code)
            return self.data_cache[contract_code]
        return None
    
    def is_cached(self, contract_code: str) -> bool:
        """
        Check if contract is currently cached.
        
        Args:
            contract_code: Contract identifier
            
        Returns:
            True if cached, False otherwise
        """
        return contract_code in self.data_cache
    
    def preload_contracts(self, contract_codes: List[str]) -> Dict[str, bool]:
        """
        Preload multiple contracts into cache.
        
        Args:
            contract_codes: List of contract identifiers to preload
            
        Returns:
            Dictionary mapping contract codes to success status
        """
        results = {}
        
        self.logger.info(f"🔄 Preloading {len(contract_codes)} contracts...")
        
        for i, contract_code in enumerate(contract_codes):
            try:
                self.load_contract_data(contract_code)
                results[contract_code] = True
                self.logger.info(f"✅ Preloaded {contract_code} ({i+1}/{len(contract_codes)})")
            except Exception as e:
                results[contract_code] = False
                self.logger.error(f"❌ Failed to preload {contract_code}: {e}")
        
        successful_loads = sum(results.values())
        self.logger.info(f"🎯 Preloading complete: {successful_loads}/{len(contract_codes)} successful")
        
        return results
    
    def clear_cache(self, contract_code: Optional[str] = None):
        """
        Clear cache for specific contract or all contracts.
        
        Args:
            contract_code: Specific contract to remove, or None for all
        """
        if contract_code is None:
            # Clear entire cache
            cleared_count = len(self.data_cache)
            self.data_cache.clear()
            self.cache_metadata.clear()
            self.current_cache_memory_mb = 0.0
            
            self.logger.info(f"🗑️  Cleared entire cache: {cleared_count} contracts removed")
        else:
            # Clear specific contract
            if contract_code in self.data_cache:
                memory_freed = self.cache_metadata[contract_code]['memory_mb']
                del self.data_cache[contract_code]
                del self.cache_metadata[contract_code]
                self.current_cache_memory_mb -= memory_freed
                
                self.logger.info(f"🗑️  Cleared {contract_code} from cache: {memory_freed:.1f} MB freed")
        
        # Force garbage collection after cache clearing
        gc.collect()
    
    def _add_to_cache(self, contract_code: str, data: pd.DataFrame, 
                     memory_mb: float, validation_result: ValidationResult):
        """
        Add contract data to cache with metadata.
        
        Args:
            contract_code: Contract identifier
            data: Contract DataFrame
            memory_mb: Memory usage in MB
            validation_result: Validation result with details
        """
        # Store data and metadata
        self.data_cache[contract_code] = data
        self.cache_metadata[contract_code] = {
            'memory_mb': memory_mb,
            'cached_at': time.time(),
            'access_count': 1,
            'last_accessed': time.time(),
            'validation_warnings': len(validation_result.warnings),
            'row_count': len(data),
            'columns': list(data.columns)
        }
        
        self.current_cache_memory_mb += memory_mb
        
        self.logger.debug(f"📦 Added {contract_code} to cache: {memory_mb:.1f} MB")
    
    def _update_cache_access(self, contract_code: str):
        """
        Update cache access information for LRU tracking.
        
        Args:
            contract_code: Contract identifier
        """
        # Move to end in OrderedDict (most recently used)
        self.data_cache.move_to_end(contract_code)
        
        # Update metadata
        if contract_code in self.cache_metadata:
            self.cache_metadata[contract_code]['last_accessed'] = time.time()
            self.cache_metadata[contract_code]['access_count'] += 1
    
    def _ensure_cache_capacity(self, new_item_memory_mb: float):
        """
        Ensure cache has capacity for new item by evicting LRU items if necessary.
        
        Args:
            new_item_memory_mb: Memory required for new item
        """
        # Check count-based limit
        while len(self.data_cache) >= self.max_cached_contracts:
            self._evict_lru_item()
        
        # Check memory-based limit (if set)
        if self.max_cache_memory_mb is not None:
            while (self.current_cache_memory_mb + new_item_memory_mb > self.max_cache_memory_mb 
                   and len(self.data_cache) > 0):
                self._evict_lru_item()
    
    def _evict_lru_item(self):
        """
        Evict least recently used item from cache.
        """
        if not self.data_cache:
            return
        
        # OrderedDict maintains insertion order, first item is LRU
        lru_contract = next(iter(self.data_cache))
        
        # Get memory info before eviction
        memory_freed = self.cache_metadata[lru_contract]['memory_mb']
        
        # Remove from cache
        del self.data_cache[lru_contract]
        del self.cache_metadata[lru_contract]
        
        self.current_cache_memory_mb -= memory_freed
        self.cache_evictions += 1
        
        self.logger.info(f"🗑️  Evicted LRU contract: {lru_contract} ({memory_freed:.1f} MB freed)")
    
    def _set_memory_limits(self):
        """
        Set memory limits based on available system memory.
        """
        try:
            import psutil
            available_memory_gb = psutil.virtual_memory().available / (1024**3)
            
            # Use up to 25% of available memory for cache
            self.max_cache_memory_mb = (available_memory_gb * 0.25) * 1024
            
            self.logger.info(f"💾 Cache memory limit set to: {self.max_cache_memory_mb:.1f} MB")
            
        except ImportError:
            self.logger.warning("psutil not available - memory limits disabled")
            self.max_cache_memory_mb = None
        except Exception as e:
            self.logger.warning(f"Could not determine memory limits: {e}")
            self.max_cache_memory_mb = None
    
    def _log_cache_stats(self):
        """
        Log current cache statistics.
        """
        total_requests = self.cache_hits + self.cache_misses
        hit_rate = (self.cache_hits / total_requests * 100) if total_requests > 0 else 0
        
        self.logger.debug(
            f"📊 Cache: {len(self.data_cache)}/{self.max_cached_contracts} items, "
            f"{self.current_cache_memory_mb:.1f} MB, "
            f"hit rate: {hit_rate:.1f}% ({self.cache_hits}/{total_requests})"
        )
    
    def get_cache_stats(self) -> Dict:
        """
        Get comprehensive cache performance statistics.
        
        Returns:
            Dictionary with cache performance metrics
        """
        total_requests = self.cache_hits + self.cache_misses
        hit_rate = (self.cache_hits / total_requests * 100) if total_requests > 0 else 0
        
        # Calculate memory efficiency
        if self.cache_misses > 0:
            avg_memory_per_load = self.current_cache_memory_mb / len(self.data_cache) if self.data_cache else 0
            estimated_memory_without_cache = avg_memory_per_load * total_requests
            memory_saved = max(0, estimated_memory_without_cache - self.current_cache_memory_mb)
        else:
            memory_saved = 0
        
        return {
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'cache_evictions': self.cache_evictions,
            'hit_rate_percent': round(hit_rate, 1),
            'cached_contracts': len(self.data_cache),
            'max_cached_contracts': self.max_cached_contracts,
            'current_memory_mb': round(self.current_cache_memory_mb, 1),
            'max_memory_mb': round(self.max_cache_memory_mb, 1) if self.max_cache_memory_mb else None,
            'memory_efficiency_mb': round(memory_saved, 1),
            'avg_memory_per_contract_mb': round(
                self.current_cache_memory_mb / len(self.data_cache), 1
            ) if self.data_cache else 0
        }
    
    def get_cache_details(self) -> Dict[str, Dict]:
        """
        Get detailed information about cached contracts.
        
        Returns:
            Dictionary mapping contract codes to cache metadata
        """
        details = {}
        
        for contract_code, metadata in self.cache_metadata.items():
            details[contract_code] = {
                'memory_mb': round(metadata['memory_mb'], 1),
                'cached_duration_seconds': round(time.time() - metadata['cached_at'], 1),
                'access_count': metadata['access_count'],
                'last_accessed_seconds_ago': round(time.time() - metadata['last_accessed'], 1),
                'validation_warnings': metadata['validation_warnings'],
                'row_count': metadata['row_count'],
                'columns': metadata['columns']
            }
        
        return details
    
    def optimize_cache(self) -> Dict[str, int]:
        """
        Optimize cache by removing contracts with low access frequency.
        
        Returns:
            Dictionary with optimization statistics
        """
        if len(self.data_cache) <= 1:
            return {'contracts_analyzed': 0, 'contracts_removed': 0}
        
        contracts_analyzed = len(self.data_cache)
        contracts_to_remove = []
        
        # Calculate access frequency for each contract
        current_time = time.time()
        
        for contract_code, metadata in self.cache_metadata.items():
            cached_duration = current_time - metadata['cached_at']
            access_frequency = metadata['access_count'] / max(cached_duration, 1)  # accesses per second
            
            # Remove contracts with very low access frequency (less than 0.01 accesses per second)
            # and haven't been accessed in the last 60 seconds
            time_since_last_access = current_time - metadata['last_accessed']
            
            if access_frequency < 0.01 and time_since_last_access > 60:
                contracts_to_remove.append(contract_code)
        
        # Remove low-frequency contracts
        for contract_code in contracts_to_remove:
            self.clear_cache(contract_code)
        
        contracts_removed = len(contracts_to_remove)
        
        if contracts_removed > 0:
            self.logger.info(f"🔧 Cache optimization: removed {contracts_removed} low-frequency contracts")
        
        return {
            'contracts_analyzed': contracts_analyzed,
            'contracts_removed': contracts_removed
        }


# Update the get_manager_statistics method to include cache stats
def get_manager_statistics(self) -> Dict:
    """
    Get comprehensive statistics about the data manager's operations.
    
    Returns:
        Dictionary with operation and cache statistics
    """
    cache_stats = self.get_cache_stats()
    
    return {
        'files_loaded': self.files_loaded,
        'validation_failures': self.validation_failures,
        'file_not_found_errors': self.file_not_found_errors,
        'data_directory': str(self.data_directory),
        'available_contracts': len(self.list_available_contracts()),
        'cache_performance': cache_stats,
        'cache_enabled': True,
        'max_cached_contracts': self.max_cached_contracts
    }

# Replace the method in the class
ContractDataManager.get_manager_statistics = get_manager_statistics


if __name__ == "__main__":
    # Test caching functionality
    print("🧪 Testing Contract Data Manager with Caching...")
    
    try:
        # Initialize manager with caching
        manager = ContractDataManager("data", max_cached_contracts=2)
        print(f"✅ Manager initialized with caching: max {manager.max_cached_contracts} contracts")
        
        # Test cache stats
        stats = manager.get_cache_stats()
        print(f"📊 Initial cache stats: {stats}")
        
        # List available contracts
        contracts = manager.list_available_contracts()
        print(f"📋 Available contracts: {contracts}")
        
        if contracts:
            # Test loading and caching
            test_contract = contracts[0]
            
            print(f"\n🔄 Testing cache with contract: {test_contract}")
            
            # First load (cache miss)
            data1 = manager.load_contract_data(test_contract)
            print(f"📂 First load: {len(data1)} rows")
            
            # Second load (cache hit)
            data2 = manager.load_contract_data(test_contract)
            print(f"📋 Second load: {len(data2)} rows")
            
            # Check cache stats
            cache_stats = manager.get_cache_stats()
            print(f"📊 Cache stats after loading: {cache_stats}")
            
            # Test cache details
            cache_details = manager.get_cache_details()
            print(f"🔍 Cache details: {cache_details}")
            
            # Test cache optimization
            optimization_stats = manager.optimize_cache()
            print(f"🔧 Cache optimization: {optimization_stats}")
            
        else:
            print("⚠️  No contracts found for testing")
        
        print("✅ Contract Data Manager with caching ready!")
        
    except Exception as e:
        print(f"❌ Error testing manager: {e}")
```

### Step 2: Create Cache Performance Tests (`tests/test_contract_data_manager_cache.py`)

```python
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
```

### Step 3: Create Cache Performance Benchmark (`tests/test_cache_performance_benchmark.py`)

```python
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
```

### Step 4: Create Validation Script (`validate_phase_1_1_5.py`)

```python
"""
Validation script for Phase 1.1.5 completion.

Run this script to verify that Phase 1.1.5 is properly implemented.
"""

import sys
import tempfile
import pandas as pd
import time
from pathlib import Path

def validate_phase_1_1_5():
    """Validate Phase 1.1.5 implementation."""
    print("🔍 Validating Phase 1.1.5: Cache Implementation...")
    
    success = True
    
    # Check dependencies (Phase 1.1.4)
    try:
        from src.gpu_parallel_processing.contract_data_manager import ContractDataManager
        print("✅ Phase 1.1.4 dependencies available")
    except ImportError as e:
        print(f"❌ Dependency missing: {e}")
        success = False
        return False
    
    # Test cache initialization
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ContractDataManager(temp_dir, max_cached_contracts=2)
            
            # Check cache attributes
            if not hasattr(manager, 'data_cache'):
                print("❌ Missing data_cache attribute")
                success = False
            
            if not hasattr(manager, 'cache_hits'):
                print("❌ Missing cache_hits attribute")
                success = False
            
            if not hasattr(manager, 'cache_misses'):
                print("❌ Missing cache_misses attribute")
                success = False
            
            if manager.max_cached_contracts != 2:
                print(f"❌ Incorrect max_cached_contracts: expected 2, got {manager.max_cached_contracts}")
                success = False
            
            if success:
                print("✅ Cache initialization successful")
        
    except Exception as e:
        print(f"❌ Cache initialization failed: {e}")
        success = False
    
    # Test basic caching functionality
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ContractDataManager(temp_dir, max_cached_contracts=2)
            
            # Create test contract
            test_data = pd.DataFrame({
                'open': [100.0, 101.0, 102.0],
                'high': [105.0, 106.0, 107.0],
                'low': [95.0, 96.0, 97.0],
                'close': [103.0, 104.0, 105.0],
                'volume': [1000, 1100, 1200]
            })
            
            contract_file = Path(temp_dir) / "cache_test_tr_ba_data.parquet"
            test_data.to_parquet(contract_file)
            
            # First load (cache miss)
            data1 = manager.load_contract_data("cache_test")
            
            if manager.cache_misses != 1:
                print(f"❌ Expected 1 cache miss, got {manager.cache_misses}")
                success = False
            
            if manager.cache_hits != 0:
                print(f"❌ Expected 0 cache hits, got {manager.cache_hits}")
                success = False
            
            # Second load (cache hit)
            data2 = manager.load_contract_data("cache_test")
            
            if manager.cache_misses != 1:
                print(f"❌ Cache misses changed unexpectedly: {manager.cache_misses}")
                success = False
            
            if manager.cache_hits != 1:
                print(f"❌ Expected 1 cache hit, got {manager.cache_hits}")
                success = False
            
            # Data should be identical
            if not data1.equals(data2):
                print("❌ Cached data differs from original")
                success = False
            
            if success:
                print("✅ Basic caching functionality working")
        
    except Exception as e:
        print(f"❌ Basic caching test failed: {e}")
        success = False
    
    # Test cache methods
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ContractDataManager(temp_dir)
            
            # Create test contract
            test_data = pd.DataFrame({
                'open': [100.0, 101.0],
                'high': [105.0, 106.0],
                'low': [95.0, 96.0],
                'close': [103.0, 104.0],
                'volume': [1000, 1100]
            })
            
            contract_file = Path(temp_dir) / "methods_test_tr_ba_data.parquet"
            test_data.to_parquet(contract_file)
            
            # Test is_cached method
            if manager.is_cached("methods_test"):
                print("❌ is_cached returned True for non-cached contract")
                success = False
            
            # Load contract
            manager.load_contract_data("methods_test")
            
            if not manager.is_cached("methods_test"):
                print("❌ is_cached returned False for cached contract")
                success = False
            
            # Test get_cached_data method
            cached_data = manager.get_cached_data("methods_test")
            if cached_data is None:
                print("❌ get_cached_data returned None for cached contract")
                success = False
            
            # Test cache stats
            stats = manager.get_cache_stats()
            required_stats_keys = ['cache_hits', 'cache_misses', 'hit_rate_percent', 'cached_contracts']
            
            for key in required_stats_keys:
                if key not in stats:
                    print(f"❌ Missing cache stats key: {key}")
                    success = False
            
            # Test cache details
            details = manager.get_cache_details()
            if "methods_test" not in details:
                print("❌ Contract not found in cache details")
                success = False
            
            if success:
                print("✅ Cache methods working")
        
    except Exception as e:
        print(f"❌ Cache methods test failed: {e}")
        success = False
    
    # Test LRU eviction
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ContractDataManager(temp_dir, max_cached_contracts=2)
            
            # Create test contracts
            test_data = pd.DataFrame({
                'open': [100.0, 101.0],
                'high': [105.0, 106.0],
                'low': [95.0, 96.0],
                'close': [103.0, 104.0],
                'volume': [1000, 1100]
            })
            
            contracts = ["lru_a", "lru_b", "lru_c"]
            for contract in contracts:
                contract_file = Path(temp_dir) / f"{contract}_tr_ba_data.parquet"
                test_data.to_parquet(contract_file)
            
            # Load first two contracts
            manager.load_contract_data("lru_a")
            manager.load_contract_data("lru_b")
            
            if len(manager.data_cache) != 2:
                print(f"❌ Expected 2 cached contracts, got {len(manager.data_cache)}")
                success = False
            
            # Load third contract (should trigger eviction)
            manager.load_contract_data("lru_c")
            
            if len(manager.data_cache) != 2:
                print(f"❌ Cache size incorrect after eviction: {len(manager.data_cache)}")
                success = False
            
            if manager.cache_evictions == 0:
                print("❌ No evictions recorded")
                success = False
            
            # First contract should be evicted (LRU)
            if manager.is_cached("lru_a"):
                print("❌ LRU contract was not evicted")
                success = False
            
            if success:
                print("✅ LRU eviction working")
        
    except Exception as e:
        print(f"❌ LRU eviction test failed: {e}")
        success = False
    
    # Test memory tracking
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ContractDataManager(temp_dir)
            
            # Create larger test contract
            test_data = pd.DataFrame({
                'open': [100.0 + i * 0.1 for i in range(1000)],
                'high': [105.0 + i * 0.1 for i in range(1000)],
                'low': [95.0 + i * 0.1 for i in range(1000)],
                'close': [103.0 + i * 0.1 for i in range(1000)],
                'volume': [1000 + i for i in range(1000)]
            })
            
            contract_file = Path(temp_dir) / "memory_test_tr_ba_data.parquet"
            test_data.to_parquet(contract_file)
            
            # Check initial memory
            if manager.current_cache_memory_mb != 0.0:
                print(f"❌ Initial cache memory should be 0, got {manager.current_cache_memory_mb}")
                success = False
            
            # Load contract
            data = manager.load_contract_data("memory_test")
            
            # Check memory tracking
            if manager.current_cache_memory_mb <= 0:
                print("❌ Cache memory not tracked after loading")
                success = False
            
            # Memory should be reasonable
            expected_memory = data.memory_usage(deep=True).sum() / (1024 * 1024)
            if abs(manager.current_cache_memory_mb - expected_memory) > 1.0:
                print(f"❌ Memory tracking inaccurate: expected ~{expected_memory:.1f} MB, got {manager.current_cache_memory_mb:.1f} MB")
                success = False
            
            if success:
                print("✅ Memory tracking working")
        
    except Exception as e:
        print(f"❌ Memory tracking test failed: {e}")
        success = False
    
    # Test cache operations
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ContractDataManager(temp_dir)
            
            # Create test contract
            test_data = pd.DataFrame({
                'open': [100.0], 'high': [105.0], 'low': [95.0], 
                'close': [103.0], 'volume': [1000]
            })
            
            contract_file = Path(temp_dir) / "ops_test_tr_ba_data.parquet"
            test_data.to_parquet(contract_file)
            
            # Load and cache
            manager.load_contract_data("ops_test")
            
            # Test clear specific contract
            manager.clear_cache("ops_test")
            
            if manager.is_cached("ops_test"):
                print("❌ Contract still cached after clear")
                success = False
            
            if manager.current_cache_memory_mb != 0.0:
                print("❌ Memory not freed after cache clear")
                success = False
            
            # Test preload
            result = manager.preload_contracts(["ops_test"])
            
            if not result.get("ops_test"):
                print("❌ Preload failed")
                success = False
            
            if not manager.is_cached("ops_test"):
                print("❌ Contract not cached after preload")
                success = False
            
            if success:
                print("✅ Cache operations working")
        
    except Exception as e:
        print(f"❌ Cache operations test failed: {e}")
        success = False
    
    # Test performance improvement
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ContractDataManager(temp_dir)
            
            # Create test contract
            test_data = pd.DataFrame({
                'open': [100.0 + i * 0.01 for i in range(5000)],
                'high': [105.0 + i * 0.01 for i in range(5000)],
                'low': [95.0 + i * 0.01 for i in range(5000)],
                'close': [103.0 + i * 0.01 for i in range(5000)],
                'volume': [1000 + i for i in range(5000)]
            })
            
            contract_file = Path(temp_dir) / "perf_test_tr_ba_data.parquet"
            test_data.to_parquet(contract_file)
            
            # Time cache miss
            start_time = time.time()
            manager.load_contract_data("perf_test")
            miss_time = time.time() - start_time
            
            # Time cache hit
            start_time = time.time()
            manager.load_contract_data("perf_test")
            hit_time = time.time() - start_time
            
            # Cache hit should be faster
            if hit_time >= miss_time:
                print(f"❌ Cache hit not faster: miss={miss_time:.4f}s, hit={hit_time:.4f}s")
                success = False
            else:
                speedup = miss_time / hit_time
                print(f"✅ Performance improvement: {speedup:.1f}x speedup")
        
    except Exception as e:
        print(f"❌ Performance test failed: {e}")
        success = False
    
    # Check test files exist
    test_files = [
        Path("tests/test_contract_data_manager_cache.py"),
        Path("tests/test_cache_performance_benchmark.py")
    ]
    
    for test_file in test_files:
        if test_file.exists():
            print(f"✅ Test file exists: {test_file}")
        else:
            print(f"❌ Missing test file: {test_file}")
            success = False
    
    # Run cache tests
    try:
        print("\n🧪 Running cache tests...")
        import subprocess
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "tests/test_contract_data_manager_cache.py", 
            "-v", "--tb=short"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ All cache tests passed")
        else:
            print(f"❌ Cache tests failed:\n{result.stdout}\n{result.stderr}")
            success = False
    except Exception as e:
        print(f"❌ Error running cache tests: {e}")
        success = False
    
    if success:
        print("\n🎉 Phase 1.1.5 validation PASSED!")
        print("✅ Cache implementation is ready")
        print("💾 LRU caching, memory management, and performance optimization complete")
        print("🚀 Ready to proceed to Phase 1.1.6: Integration and Polish")
        return True
    else:
        print("\n❌ Phase 1.1.5 validation FAILED!")
        print("Please fix the issues before proceeding.")
        return False

if __name__ == "__main__":
    validate_phase_1_1_5()
```

## Success Criteria for Phase 1.1.5

### Functional Requirements:
- ✅ LRU cache implementation with configurable size limits
- ✅ Cache hit/miss tracking and comprehensive performance metrics
- ✅ Memory usage tracking and automatic memory management
- ✅ Cache eviction with proper memory cleanup
- ✅ Cache operations (clear, preload, optimize)

### Performance Requirements:
- ✅ Cache hits 5x+ faster than cache misses
- ✅ Memory-efficient caching with accurate tracking
- ✅ LRU eviction maintains stable memory usage
- ✅ High hit rates (80%+) under normal usage patterns

### Testing Requirements:
- ✅ Comprehensive unit tests for all cache functionality
- ✅ Performance benchmarks and scalability tests
- ✅ Memory usage and efficiency testing
- ✅ LRU eviction and cache operation testing
- ✅ Error handling and edge case coverage

### Quality Requirements:
- ✅ Automatic memory limit detection and management
- ✅ Comprehensive statistics and monitoring
- ✅ Cache optimization for low-frequency data
- ✅ Logging and debugging support
- ✅ Thread-safe cache operations

## Next Steps
Upon successful validation of Phase 1.1.5, **Track B (Data Management)** is complete. Proceed to **Phase 1.1.6: Integration and Polish** which will integrate both Track A (Parameter Logic) and Track B (Data Management) and add final polish.

## TDD Cycle for Phase 1.1.5
1. **RED**: Write failing tests for cache functionality
2. **GREEN**: Implement LRU cache and memory management
3. **REFACTOR**: Optimize cache performance and memory efficiency
4. **VALIDATE**: Run comprehensive cache and performance tests