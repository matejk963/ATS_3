"""
Test suite for AdvancedGPUMemoryPool - Phase 1.2.1 Implementation
Following TDD: Write failing tests first, then implement to pass.
"""

import pytest
import numpy as np
import time
import threading
from unittest.mock import Mock, patch

# This will fail initially - implementing TDD approach
try:
    import cupy as cp
    from src.gpu_parallel_processing.advanced_memory_manager import (
        AdvancedGPUMemoryPool, 
        MemoryBlock, 
        MemoryStats
    )
    HAS_GPU = True
except ImportError:
    HAS_GPU = False
    cp = None


class TestAdvancedGPUMemoryPool:
    """Test AdvancedGPUMemoryPool core functionality."""
    
    @pytest.fixture
    def memory_pool(self):
        """Create memory pool for testing."""
        if not HAS_GPU:
            pytest.skip("GPU/CuPy not available")
        return AdvancedGPUMemoryPool(max_pool_size_gb=1.0, fragmentation_threshold=0.25)
    
    def test_memory_pool_initialization(self, memory_pool):
        """Test memory pool initializes correctly."""
        assert memory_pool.max_pool_size == int(1.0 * 1024**3)
        assert memory_pool.fragmentation_threshold == 0.25
        assert len(memory_pool.free_blocks) == 0
        assert len(memory_pool.allocated_blocks) == 0
        assert memory_pool.maintenance_active is True
    
    def test_get_array_allocation(self, memory_pool):
        """Test array allocation from pool."""
        shape = (1000, 5)
        dtype = 'float32'
        
        # This should fail initially - no implementation yet
        arr = memory_pool.get_array(shape, dtype)
        
        assert arr.shape == shape
        assert arr.dtype == np.dtype(dtype)
        assert isinstance(arr, cp.ndarray)
        
        # Array should be tracked as allocated
        assert len(memory_pool.allocated_blocks) == 1
        assert id(arr) in memory_pool.allocated_blocks
    
    def test_array_return_and_reuse(self, memory_pool):
        """Test array return to pool and reuse."""
        shape = (1000, 5)
        dtype = 'float32'
        
        # Allocate array
        arr1 = memory_pool.get_array(shape, dtype)
        array_id = id(arr1)
        
        # Return to pool
        memory_pool.return_array(arr1)
        
        # Should be in free blocks now
        array_key = f"{shape}_{dtype}"
        assert array_key in memory_pool.free_blocks
        assert len(memory_pool.free_blocks[array_key]) == 1
        assert len(memory_pool.allocated_blocks) == 0
        
        # Get another array of same size - should reuse
        arr2 = memory_pool.get_array(shape, dtype)
        
        # Should have reused the block
        stats = memory_pool.get_memory_stats()
        assert stats['successful_reuses'] == 1
        assert len(memory_pool.free_blocks[array_key]) == 0
    
    def test_memory_cleanup_on_pressure(self, memory_pool):
        """Test memory cleanup when pool is under pressure."""
        # Fill pool with multiple arrays
        arrays = []
        shape = (500000, 5)  # Large arrays to fill memory
        
        for i in range(5):
            try:
                arr = memory_pool.get_array(shape, 'float32')
                arrays.append(arr)
            except RuntimeError:
                break
        
        # Return some arrays
        for arr in arrays[:3]:
            memory_pool.return_array(arr)
        
        # Try to allocate a large array - should trigger cleanup
        large_arr = memory_pool.get_array((1000000, 5), 'float32')
        assert large_arr is not None
    
    def test_fragmentation_detection(self, memory_pool):
        """Test memory fragmentation detection and handling."""
        # Create fragmented memory by allocating and returning different sizes
        shapes = [(1000, 5), (2000, 5), (500, 5), (3000, 5)]
        
        arrays = []
        for shape in shapes:
            arr = memory_pool.get_array(shape, 'float32')
            arrays.append(arr)
        
        # Return every other array to create fragmentation
        for i in range(0, len(arrays), 2):
            memory_pool.return_array(arrays[i])
        
        # Check fragmentation stats
        stats = memory_pool.get_memory_stats()
        assert 'fragmentation_ratio' in stats
        assert stats['fragmentation_ratio'] >= 0.0
    
    def test_background_maintenance(self, memory_pool):
        """Test background maintenance thread functionality."""
        # Background thread should be running
        assert memory_pool.maintenance_thread.is_alive()
        
        # Create some old blocks
        arr = memory_pool.get_array((1000, 5), 'float32')
        memory_pool.return_array(arr)
        
        # Manually update last access time to make it old
        array_key = f"{(1000, 5)}_float32"
        if array_key in memory_pool.free_blocks:
            memory_pool.free_blocks[array_key][0].last_access_time = time.time() - 400
        
        # Wait for maintenance to potentially run
        time.sleep(1)
        
        # Maintenance should be active
        assert memory_pool.maintenance_active
    
    def test_memory_stats_reporting(self, memory_pool):
        """Test comprehensive memory statistics reporting."""
        # Allocate some arrays
        arr1 = memory_pool.get_array((1000, 5), 'float32')
        arr2 = memory_pool.get_array((2000, 3), 'float32')
        
        # Return one
        memory_pool.return_array(arr1)
        
        stats = memory_pool.get_memory_stats()
        
        # Check required stats fields
        required_fields = [
            'current_usage_gb', 'peak_usage_gb', 'max_pool_size_gb',
            'utilization_percent', 'fragmentation_ratio', 'total_allocations',
            'total_deallocations', 'allocation_failures', 'successful_reuses',
            'free_blocks_count', 'allocated_blocks_count', 'reuse_efficiency_percent'
        ]
        
        for field in required_fields:
            assert field in stats
            assert isinstance(stats[field], (int, float))
    
    def test_emergency_cleanup(self, memory_pool):
        """Test emergency cleanup functionality."""
        # Fill pool with arrays
        arrays = []
        try:
            for i in range(10):
                arr = memory_pool.get_array((100000, 5), 'float32')
                arrays.append(arr)
        except RuntimeError:
            pass  # Expected when pool is full
        
        # Return all arrays
        for arr in arrays:
            memory_pool.return_array(arr)
        
        # Emergency cleanup should work
        memory_pool._emergency_cleanup()
        
        # Pool should be clean
        assert len(memory_pool.free_blocks) == 0
        stats = memory_pool.get_memory_stats()
        assert stats['current_usage_gb'] == stats['current_usage_gb']  # Should not crash
    
    def test_thread_safety(self, memory_pool):
        """Test thread safety of memory pool operations."""
        results = []
        errors = []
        
        def worker_function():
            try:
                for i in range(10):
                    arr = memory_pool.get_array((100, 5), 'float32')
                    time.sleep(0.001)  # Small delay
                    memory_pool.return_array(arr)
                results.append("success")
            except Exception as e:
                errors.append(str(e))
        
        # Start multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=worker_function)
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Should have no errors and all successes
        assert len(errors) == 0
        assert len(results) == 5
    
    def test_cleanup_resources(self, memory_pool):
        """Test proper cleanup of memory pool resources."""
        # Allocate some arrays
        arr1 = memory_pool.get_array((1000, 5), 'float32')
        arr2 = memory_pool.get_array((2000, 3), 'float32')
        memory_pool.return_array(arr1)
        
        # Cleanup should work without errors
        memory_pool.cleanup()
        
        # Maintenance thread should be stopped
        assert memory_pool.maintenance_active is False
        
        # All blocks should be cleared
        assert len(memory_pool.free_blocks) == 0
        assert len(memory_pool.allocated_blocks) == 0


class TestMemoryBlock:
    """Test MemoryBlock dataclass functionality."""
    
    def test_memory_block_creation(self):
        """Test MemoryBlock creation and attributes."""
        # This will fail initially - no implementation yet
        block = MemoryBlock(
            size_bytes=1000,
            shape=(100, 10),
            dtype='float32',
            is_free=True,
            allocation_time=time.time(),
            last_access_time=time.time()
        )
        
        assert block.size_bytes == 1000
        assert block.shape == (100, 10)
        assert block.dtype == 'float32'
        assert block.is_free is True
        assert block.usage_count == 0


class TestMemoryStats:
    """Test MemoryStats dataclass functionality."""
    
    def test_memory_stats_creation(self):
        """Test MemoryStats creation and default values."""
        # This will fail initially - no implementation yet
        stats = MemoryStats()
        
        assert stats.total_allocations == 0
        assert stats.total_deallocations == 0
        assert stats.peak_usage_bytes == 0
        assert stats.current_usage_bytes == 0
        assert stats.fragmentation_ratio == 0.0
        assert stats.allocation_failures == 0
        assert stats.successful_reuses == 0
        assert stats.defragmentation_count == 0


if __name__ == "__main__":
    # Run tests to see failures (TDD approach)
    pytest.main([__file__, "-v"])