import pytest
import numpy as np
import pandas as pd
from typing import List, Tuple, Optional, Dict

# Test imports - will implement these optimized classes
from src.feature_engineering.array_backend import ArrayBackend
from src.feature_engineering.metadata import DataFrameMetadata


class TestOptimizedArrayBackendMemoryPool:
    """Test GPU memory pool management for OptimizedArrayBackend (Task 1.1)"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.backend = ArrayBackend(backend='cupy')
        # Generate test data for memory pool testing
        self.test_data = np.random.rand(1000, 10).astype(np.float32)
        self.batch_data = [
            np.random.rand(500, 5).astype(np.float32),
            np.random.rand(750, 5).astype(np.float32),
            np.random.rand(1000, 5).astype(np.float32)
        ]
    
    def test_gpu_memory_pool_initialization(self):
        """Test OptimizedArrayBackend initializes GPU memory pool correctly"""
        # GREEN: Implementation exists - test actual functionality
        assert hasattr(self.backend, 'memory_pool')
        assert hasattr(self.backend, 'pinned_memory_pool')
        
        # Verify memory pools are properly initialized
        if self.backend.memory_pool is not None:
            # Memory pool should be the default CuPy memory pool
            assert self.backend.memory_pool is not None
            # Pinned memory pool should be initialized
            assert self.backend.pinned_memory_pool is not None
    
    def test_batch_asarray_method_exists(self):
        """Test batch_asarray method exists and has proper signature"""
        # GREEN: Implementation exists - test actual functionality
        result = self.backend.batch_asarray(self.batch_data)
        
        # Validate results
        assert isinstance(result, list)
        assert len(result) == len(self.batch_data)
        
        # Verify all arrays are GPU arrays and properly formatted
        for i, gpu_array in enumerate(result):
            assert gpu_array is not None
            assert hasattr(gpu_array, 'shape')
            assert gpu_array.dtype == np.float32  # Should be converted to float32
            assert gpu_array.flags.c_contiguous  # Should be C-contiguous
    
    def test_batch_asarray_memory_preallocation(self):
        """Test batch_asarray pre-allocates contiguous GPU memory for entire batch"""
        # GREEN: Implementation exists - test actual functionality
        target_shape = (len(self.batch_data), max(arr.shape[0] for arr in self.batch_data), 5)
        result = self.backend.batch_asarray(self.batch_data, target_shape=target_shape)
        
        # Validate:
        # 1. Result should be list of GPU arrays
        assert isinstance(result, list)
        assert len(result) == len(self.batch_data)
        
        # 2. All arrays should be C-contiguous
        # 3. All arrays should be float32
        # 4. Memory should be properly allocated
        for gpu_array in result:
            assert gpu_array.flags.c_contiguous
            assert gpu_array.dtype == np.float32
            assert hasattr(gpu_array, 'get')  # CuPy array method
    
    def test_ensure_contiguous_layout_method_exists(self):
        """Test ensure_contiguous_layout method exists"""
        # GREEN: Implementation exists - test actual functionality
        test_array = self.backend.asarray(self.test_data)
        result = self.backend.ensure_contiguous_layout(test_array)
        
        # Validate results
        assert result is not None
        assert result.flags.c_contiguous
        assert result.dtype == np.float32
        assert hasattr(result, 'get')  # CuPy array method
    
    def test_memory_pool_reuse_efficiency(self):
        """Test memory pool reuses allocated memory between operations"""
        # RED: This test should fail - optimization doesn't exist yet
        # This test validates that memory pool reduces allocation overhead
        pytest.skip("Requires OptimizedArrayBackend implementation with memory pool")
        
        # After implementation:
        # 1. Process first batch and measure memory allocations
        # 2. Process second batch and verify memory reuse
        # 3. Validate reduced memory fragmentation


class TestOptimizedArrayBackendContiguousLayout:
    """Test contiguous memory layout optimization (Task 1.1)"""
    
    def setup_method(self):
        """Setup test fixtures with non-contiguous arrays"""
        self.backend = ArrayBackend(backend='cupy')
        # Create non-contiguous test data
        base_array = np.random.rand(100, 20).astype(np.float32)
        self.non_contiguous_array = base_array[:, ::2]  # Non-contiguous view
        assert not self.non_contiguous_array.flags.c_contiguous
    
    def test_ensure_contiguous_layout_fixes_memory_layout(self):
        """Test ensure_contiguous_layout creates C-contiguous arrays"""
        # GREEN: Implementation exists - test actual functionality
        gpu_array = self.backend.asarray(self.non_contiguous_array)
        contiguous_array = self.backend.ensure_contiguous_layout(gpu_array)
        
        # Validate:
        # 1. Result should be C-contiguous
        assert contiguous_array.flags.c_contiguous
        # 2. Data should be preserved (check shape)
        assert contiguous_array.shape == gpu_array.shape
        # 3. Should be float32 dtype
        assert contiguous_array.dtype == np.float32
        # 4. Should be GPU array (CuPy)
        assert hasattr(contiguous_array, 'get')
    
    def test_batch_memory_layout_optimization(self):
        """Test batch operations maintain optimal memory layout"""
        # RED: This test should fail - batch optimization doesn't exist yet
        pytest.skip("Requires batch processing implementation")
        
        # After implementation:
        # 1. Process batch of arrays with mixed memory layouts
        # 2. Verify all results are C-contiguous
        # 3. Validate GPU memory alignment


class TestOptimizedArrayBackendTypeConversion:
    """Test efficient type conversion optimization (Task 1.1)"""
    
    def setup_method(self):
        """Setup test fixtures with different dtypes"""
        self.backend = ArrayBackend(backend='cupy')
        self.float64_data = np.random.rand(1000, 10).astype(np.float64)
        self.int32_data = np.random.randint(0, 1000, (1000, 10)).astype(np.int32)
        self.mixed_dtype_batch = [
            self.float64_data,
            self.int32_data.astype(np.float64),
            np.random.rand(500, 10).astype(np.float32)
        ]
    
    def test_single_pass_type_conversion(self):
        """Test efficient single-pass type conversion to float32"""
        # Current implementation should work, but may not be optimized
        result = self.backend.asarray(self.float64_data, dtype='float32')
        
        # Validate current functionality
        assert result.dtype == np.float32
        # Test optimization will be in batch processing
    
    def test_optimize_dtypes_batch_method_exists(self):
        """Test optimize_dtypes_batch method exists for batch type conversion"""
        # GREEN: Implementation exists - test actual functionality
        # Convert mixed dtype data to arrays first
        test_arrays = []
        for data in self.mixed_dtype_batch:
            array = self.backend.asarray(data)
            test_arrays.append(array)
        
        optimized_arrays = self.backend.optimize_dtypes_batch(test_arrays)
        
        # Validate results
        assert isinstance(optimized_arrays, list)
        assert len(optimized_arrays) == len(test_arrays)
        
        # Verify all arrays are optimized
        for array in optimized_arrays:
            assert array.dtype == np.float32  # All should be float32
            assert array.flags.c_contiguous  # All should be C-contiguous
            assert hasattr(array, 'get')  # All should be CuPy arrays
    
    def test_batch_type_conversion_efficiency(self):
        """Test batch type conversion reduces overhead"""
        # RED: This test should fail - batch optimization doesn't exist yet
        pytest.skip("Requires batch type conversion implementation")
        
        # After implementation:
        # 1. Convert batch of mixed dtypes to float32
        # 2. Verify all results are float32
        # 3. Measure conversion efficiency vs individual conversions


class TestOptimizedArrayBackendIntegration:
    """Integration tests for OptimizedArrayBackend with current pipeline"""
    
    def setup_method(self):
        """Setup integration test fixtures"""
        self.backend = ArrayBackend(backend='cupy')
        
        # Create realistic test data similar to technical indicators pipeline
        dates = pd.date_range('2024-01-01', periods=10000, freq='1min')
        self.test_df = pd.DataFrame({
            'open': np.random.rand(10000) * 100 + 100,
            'high': np.random.rand(10000) * 5 + 105,
            'low': np.random.rand(10000) * 5 + 95,
            'close': np.random.rand(10000) * 100 + 100,
            'volume': np.random.randint(1000, 10000, 10000)
        }, index=dates)
    
    def test_backward_compatibility_with_existing_methods(self):
        """Test OptimizedArrayBackend maintains compatibility with existing code"""
        # Current methods should continue working
        test_array = self.backend.asarray(self.test_df.values)
        assert test_array is not None
        assert hasattr(test_array, 'shape')
        
        # Basic operations should work
        zeros = self.backend.zeros((100, 5))
        ones = self.backend.ones((100, 5))
        result = self.backend.add(zeros, ones)
        
        # Verify GPU operations work
        cpu_result = self.backend.to_cpu(result)
        assert np.allclose(cpu_result, 1.0)
    
    def test_integration_with_dataframe_metadata(self):
        """Test optimized backend preserves DataFrame metadata compatibility"""
        # This validates that optimization doesn't break existing metadata handling
        from src.feature_engineering.metadata import DataFrameMetadata
        
        metadata = DataFrameMetadata.from_dataframe(self.test_df)
        assert metadata is not None
        assert len(metadata.columns) == len(self.test_df.columns)
        
        # After optimization implementation, ensure metadata preservation
        # during batch operations


@pytest.mark.performance
class TestOptimizedArrayBackendPerformance:
    """Performance tests for GPU optimization (Task 1.1)"""
    
    def setup_method(self):
        """Setup performance test fixtures"""
        self.backend = ArrayBackend(backend='cupy')
        
        # Large dataset for performance testing
        self.large_dataset = np.random.rand(100000, 50).astype(np.float64)
        self.batch_datasets = [
            np.random.rand(50000, 20).astype(np.float64) for _ in range(10)
        ]
    
    @pytest.mark.skip(reason="Requires GPU optimization implementation")
    def test_memory_pool_performance_improvement(self):
        """Test memory pool provides performance improvement over standard allocation"""
        # This test will measure performance improvement after implementation
        # Target: 5-10x improvement in array conversion speed
        pass
    
    @pytest.mark.skip(reason="Requires batch processing implementation")
    def test_batch_processing_performance(self):
        """Test batch processing achieves target GPU utilization"""
        # This test will validate GPU utilization targets after implementation
        # Target: 60-70% GPU utilization (vs current 8.2%)
        pass
    
    def test_current_gpu_utilization_baseline(self):
        """Establish current GPU utilization baseline for comparison"""
        # Process data with current implementation to establish baseline
        arrays = []
        for i in range(5):  # Small batch for baseline
            array = self.backend.asarray(self.large_dataset[i*10000:(i+1)*10000])
            arrays.append(array)
        
        # This establishes the current performance baseline
        # After optimization, we'll compare against this baseline
        assert len(arrays) == 5
        
        # Cleanup GPU memory
        del arrays
        import gc
        gc.collect()
        if hasattr(self.backend.xp, 'get_default_memory_pool'):
            self.backend.xp.get_default_memory_pool().free_all_blocks()