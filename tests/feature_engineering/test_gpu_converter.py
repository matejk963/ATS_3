"""Tests for GPUArrayConverter - TDD approach"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import Mock

from src.feature_engineering.gpu_converter import GPUArrayConverter
from src.feature_engineering.metadata import DataFrameMetadata


class TestGPUArrayConverter:
    """Test GPUArrayConverter functionality"""
    
    def setup_method(self):
        """Setup test data"""
        dates = pd.date_range('2023-01-01', periods=50, freq='D')
        self.test_df = pd.DataFrame({
            'open': np.random.uniform(100, 200, 50).astype(np.float64),
            'high': np.random.uniform(150, 250, 50).astype(np.float64),
            'low': np.random.uniform(50, 150, 50).astype(np.float64),
            'close': np.random.uniform(80, 220, 50).astype(np.float64),
            'volume': np.random.randint(1000, 10000, 50).astype(np.int64)
        }, index=dates)
    
    def test_to_arrays_converts_dataframe_to_arrays(self):
        """Test DataFrame to arrays conversion"""
        arrays, metadata = GPUArrayConverter.to_arrays(self.test_df)
        
        # Check arrays were created for each column
        assert set(arrays.keys()) == set(self.test_df.columns)
        
        # Check array values match DataFrame
        for col in self.test_df.columns:
            np.testing.assert_array_equal(arrays[col], self.test_df[col].values.astype('float32'))
        
        # Check metadata is returned
        assert isinstance(metadata, DataFrameMetadata)
    
    def test_to_arrays_respects_dtype_parameter(self):
        """Test to_arrays respects dtype parameter"""
        arrays, metadata = GPUArrayConverter.to_arrays(self.test_df, dtype='float64')
        
        for col in self.test_df.columns:
            assert arrays[col].dtype == np.float64
    
    def test_to_arrays_creates_contiguous_arrays_by_default(self):
        """Test to_arrays creates C-contiguous arrays by default"""
        arrays, metadata = GPUArrayConverter.to_arrays(self.test_df)
        
        for col in self.test_df.columns:
            assert arrays[col].flags.c_contiguous
    
    def test_to_arrays_can_disable_contiguous(self):
        """Test to_arrays can disable contiguous requirement"""
        # Create non-contiguous array
        non_contig_df = self.test_df.iloc[::2].copy()  # Skip every other row
        
        arrays, metadata = GPUArrayConverter.to_arrays(non_contig_df, contiguous=False)
        
        # Should still work, but may not be contiguous
        assert set(arrays.keys()) == set(non_contig_df.columns)
    
    def test_from_arrays_reconstructs_dataframe(self):
        """Test arrays to DataFrame reconstruction"""
        arrays, metadata = GPUArrayConverter.to_arrays(self.test_df)
        reconstructed = GPUArrayConverter.from_arrays(arrays, metadata)
        
        # Should reconstruct original DataFrame structure
        assert list(reconstructed.columns) == list(self.test_df.columns)
        pd.testing.assert_index_equal(reconstructed.index, self.test_df.index)
        
        # Data should match (accounting for dtype conversion)
        for col in self.test_df.columns:
            np.testing.assert_allclose(
                reconstructed[col].values, 
                self.test_df[col].values, 
                rtol=1e-6
            )
    
    def test_from_arrays_handles_cupy_arrays(self):
        """Test from_arrays handles mock CuPy arrays"""
        arrays, metadata = GPUArrayConverter.to_arrays(self.test_df)
        
        # Mock CuPy arrays with get() method
        cupy_arrays = {}
        for col, arr in arrays.items():
            mock_cupy = Mock()
            mock_cupy.get.return_value = arr
            cupy_arrays[col] = mock_cupy
        
        reconstructed = GPUArrayConverter.from_arrays(cupy_arrays, metadata)
        
        # Should call get() on each array
        for mock_cupy in cupy_arrays.values():
            mock_cupy.get.assert_called_once()
        
        # Should reconstruct correctly
        assert list(reconstructed.columns) == list(self.test_df.columns)
    
    def test_optimize_for_gpu_ensures_contiguous(self):
        """Test optimize_for_gpu ensures C-contiguous layout"""
        # Create non-contiguous arrays
        arrays = {}
        for col in self.test_df.columns:
            arr = self.test_df[col].values[::2]  # Non-contiguous
            arrays[col] = arr
        
        optimized = GPUArrayConverter.optimize_for_gpu(arrays)
        
        for col, arr in optimized.items():
            assert arr.flags.c_contiguous
    
    def test_optimize_for_gpu_converts_to_float32(self):
        """Test optimize_for_gpu converts arrays to float32"""
        arrays = {col: self.test_df[col].values.astype('float64') 
                 for col in self.test_df.columns}
        
        optimized = GPUArrayConverter.optimize_for_gpu(arrays)
        
        for col, arr in optimized.items():
            assert arr.dtype == np.float32
    
    def test_optimize_for_gpu_preserves_float32_arrays(self):
        """Test optimize_for_gpu preserves already optimized arrays"""
        arrays = {col: self.test_df[col].values.astype('float32') 
                 for col in self.test_df.columns}
        
        # Make them contiguous
        for col in arrays:
            arrays[col] = np.ascontiguousarray(arrays[col])
        
        optimized = GPUArrayConverter.optimize_for_gpu(arrays)
        
        # Should be unchanged (same object reference would be ideal but not required)
        for col, arr in optimized.items():
            assert arr.dtype == np.float32
            assert arr.flags.c_contiguous
    
    def test_round_trip_conversion_preserves_data(self):
        """Test full round-trip conversion preserves data integrity"""
        # DataFrame -> Arrays -> GPU-optimized -> DataFrame
        arrays, metadata = GPUArrayConverter.to_arrays(self.test_df)
        optimized_arrays = GPUArrayConverter.optimize_for_gpu(arrays)
        reconstructed = GPUArrayConverter.from_arrays(optimized_arrays, metadata)
        
        # Should preserve original structure
        assert list(reconstructed.columns) == list(self.test_df.columns)
        pd.testing.assert_index_equal(reconstructed.index, self.test_df.index)
        
        # Data should be very close (accounting for precision loss)
        for col in self.test_df.columns:
            np.testing.assert_allclose(
                reconstructed[col].values, 
                self.test_df[col].values, 
                rtol=1e-6
            )
    
    def test_empty_dataframe_handling(self):
        """Test handling of empty DataFrame"""
        empty_df = pd.DataFrame()
        arrays, metadata = GPUArrayConverter.to_arrays(empty_df)
        
        assert arrays == {}
        reconstructed = GPUArrayConverter.from_arrays(arrays, metadata)
        pd.testing.assert_frame_equal(reconstructed, empty_df)
    
    def test_single_column_dataframe(self):
        """Test handling of single column DataFrame"""
        single_col_df = pd.DataFrame({'price': [1.0, 2.0, 3.0]})
        arrays, metadata = GPUArrayConverter.to_arrays(single_col_df)
        
        assert 'price' in arrays
        assert len(arrays) == 1
        
        reconstructed = GPUArrayConverter.from_arrays(arrays, metadata)
        pd.testing.assert_frame_equal(reconstructed.astype(single_col_df.dtypes), single_col_df)