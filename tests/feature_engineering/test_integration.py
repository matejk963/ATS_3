"""Integration tests for Technical Indicators GPU-Ready Infrastructure"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import Mock, patch

from src.feature_engineering import (
    DataFrameMetadata, ArrayBackend, GPUArrayConverter, 
    ArrayLike, is_gpu_array, ensure_cpu_array, validate_array_compatibility
)


class TestIntegration:
    """Test integration between all components"""
    
    def setup_method(self):
        """Setup test data"""
        dates = pd.date_range('2023-01-01', periods=100, freq='D')
        self.test_df = pd.DataFrame({
            'open': np.random.uniform(100, 200, 100).astype(np.float64),
            'high': np.random.uniform(150, 250, 100).astype(np.float64),
            'low': np.random.uniform(50, 150, 100).astype(np.float64),
            'close': np.random.uniform(80, 220, 100).astype(np.float64),
            'volume': np.random.randint(1000, 10000, 100).astype(np.int64)
        }, index=dates)
    
    def test_complete_workflow_numpy_backend(self):
        """Test complete workflow with NumPy backend"""
        # Initialize backend
        backend = ArrayBackend('numpy')
        
        # Convert DataFrame to arrays
        arrays, metadata = GPUArrayConverter.to_arrays(self.test_df, dtype='float32', contiguous=True)
        
        # Transfer to backend
        backend_arrays = {key: backend.asarray(arr) for key, arr in arrays.items()}
        
        # Verify all arrays are on correct backend
        for arr in backend_arrays.values():
            assert not is_gpu_array(arr)
            assert isinstance(arr, np.ndarray)
        
        # Verify arrays are compatible
        array_list = list(backend_arrays.values())
        for i in range(len(array_list) - 1):
            # Should have same shape[0] (number of rows)
            assert array_list[i].shape[0] == array_list[i+1].shape[0]
        
        # Reconstruct DataFrame
        result_df = GPUArrayConverter.from_arrays(backend_arrays, metadata)
        
        # Verify structure preservation
        assert list(result_df.columns) == list(self.test_df.columns)
        pd.testing.assert_index_equal(result_df.index, self.test_df.index)
        
        # Verify data integrity (with float32 precision)
        for col in self.test_df.columns:
            np.testing.assert_allclose(
                result_df[col].values, 
                self.test_df[col].values, 
                rtol=1e-6
            )
    
    def test_complete_workflow_cupy_backend_available(self):
        """Test complete workflow with CuPy backend when available"""
        # Test CuPy backend without complex mocking (test the fallback behavior)
        backend = ArrayBackend('cupy')  # Will fallback to NumPy without CuPy
        
        # Convert DataFrame to arrays
        arrays, metadata = GPUArrayConverter.to_arrays(self.test_df, dtype='float32')
        
        # Transfer to backend
        backend_arrays = {key: backend.asarray(arr) for key, arr in arrays.items()}
        
        # Verify backend initialization
        assert backend.backend == 'cupy'  # backend name
        assert backend.xp == np  # but actual module is numpy (fallback)
        
        # Reconstruct DataFrame
        result_df = GPUArrayConverter.from_arrays(backend_arrays, metadata)
        
        # Should still preserve structure
        assert list(result_df.columns) == list(self.test_df.columns)
        pd.testing.assert_index_equal(result_df.index, self.test_df.index)
    
    def test_memory_optimization_workflow(self):
        """Test memory optimization workflow"""
        # Start with various dtypes and layouts
        mixed_df = pd.DataFrame({
            'price_f64': np.random.random(50).astype(np.float64),
            'volume_i32': np.random.randint(1000, 5000, 50).astype(np.int32),
            'indicator_f32': np.random.random(50).astype(np.float32)
        })
        
        # Convert to arrays
        arrays, metadata = GPUArrayConverter.to_arrays(mixed_df, dtype='float64')
        
        # Optimize for GPU
        optimized = GPUArrayConverter.optimize_for_gpu(arrays)
        
        # Verify optimization
        for arr in optimized.values():
            assert arr.dtype == np.float32
            assert arr.flags.c_contiguous
        
        # Reconstruct should still work
        result_df = GPUArrayConverter.from_arrays(optimized, metadata)
        
        # Structure should be preserved
        assert list(result_df.columns) == list(mixed_df.columns)
        pd.testing.assert_index_equal(result_df.index, mixed_df.index)
    
    def test_backend_switching(self):
        """Test switching between backends maintains compatibility"""
        # Start with NumPy backend
        numpy_backend = ArrayBackend('numpy')
        arrays, metadata = GPUArrayConverter.to_arrays(self.test_df)
        
        numpy_arrays = {key: numpy_backend.asarray(arr) for key, arr in arrays.items()}
        
        # Switch to CuPy backend (will fallback to NumPy without CuPy)
        with patch('builtins.print'):  # Suppress fallback message
            cupy_backend = ArrayBackend('cupy')
        
        # Should still work with same arrays
        converted_arrays = {key: cupy_backend.to_cpu(arr) for key, arr in numpy_arrays.items()}
        
        # Reconstruct should work
        result_df = GPUArrayConverter.from_arrays(converted_arrays, metadata)
        
        # Should match original
        assert list(result_df.columns) == list(self.test_df.columns)
    
    def test_type_validation_workflow(self):
        """Test type validation in complete workflow"""
        backend = ArrayBackend('numpy')
        arrays, metadata = GPUArrayConverter.to_arrays(self.test_df)
        
        backend_arrays = {key: backend.asarray(arr) for key, arr in arrays.items()}
        
        # Test array compatibility
        array_list = list(backend_arrays.values())
        if len(array_list) >= 2:
            # Same length arrays should be compatible
            arr1 = backend.zeros((100,), dtype='float32')
            arr2 = backend.ones((100,), dtype='float32')
            assert validate_array_compatibility(arr1, arr2)
            
            # Different length arrays should not be compatible
            arr3 = backend.zeros((50,), dtype='float32')
            assert not validate_array_compatibility(arr1, arr3)
    
    def test_error_handling_integration(self):
        """Test error handling across components"""
        # Test with modified arrays that match truncated index
        arrays, metadata = GPUArrayConverter.to_arrays(self.test_df)
        
        # Modify arrays to have incompatible shapes
        bad_arrays = {key: arr[:50] for key, arr in arrays.items()}  # Truncate arrays
        
        # Create truncated metadata to match
        truncated_df = self.test_df.iloc[:50]
        _, truncated_metadata = GPUArrayConverter.to_arrays(truncated_df)
        
        # Should reconstruct with matching metadata
        result_df = GPUArrayConverter.from_arrays(bad_arrays, truncated_metadata)
        
        # Should have truncated length and preserve structure
        assert len(result_df) == 50
        assert list(result_df.columns) == list(self.test_df.columns)
        
        # Test that mismatched arrays and metadata raise appropriate error
        with pytest.raises(ValueError, match="Length of values"):
            GPUArrayConverter.from_arrays(bad_arrays, metadata)  # Original metadata has 100 rows
    
    def test_performance_characteristics(self):
        """Test that performance characteristics meet requirements"""
        import time
        
        # Large dataset for performance testing
        large_df = pd.DataFrame({
            'data': np.random.random(10000).astype(np.float64)
        })
        
        # Time the conversion
        start_time = time.time()
        arrays, metadata = GPUArrayConverter.to_arrays(large_df)
        optimized = GPUArrayConverter.optimize_for_gpu(arrays)
        result_df = GPUArrayConverter.from_arrays(optimized, metadata)
        end_time = time.time()
        
        # Should complete reasonably quickly (less than 1 second for 10K rows)
        conversion_time = end_time - start_time
        assert conversion_time < 1.0
        
        # Should preserve data
        np.testing.assert_allclose(
            result_df['data'].values, 
            large_df['data'].values, 
            rtol=1e-6
        )
    
    def test_edge_cases_integration(self):
        """Test edge cases in integrated workflow"""
        # Empty DataFrame
        empty_df = pd.DataFrame()
        arrays, metadata = GPUArrayConverter.to_arrays(empty_df)
        result_df = GPUArrayConverter.from_arrays(arrays, metadata)
        pd.testing.assert_frame_equal(result_df, empty_df)
        
        # Single row DataFrame
        single_row_df = pd.DataFrame({'value': [42.0]})
        arrays, metadata = GPUArrayConverter.to_arrays(single_row_df)
        backend = ArrayBackend('numpy')
        backend_arrays = {key: backend.asarray(arr) for key, arr in arrays.items()}
        result_df = GPUArrayConverter.from_arrays(backend_arrays, metadata)
        
        assert len(result_df) == 1
        assert result_df['value'].iloc[0] == pytest.approx(42.0, rel=1e-6)