"""Tests for ArrayLike types and utilities - TDD approach"""

import pytest
import numpy as np
from unittest.mock import Mock

from src.feature_engineering.types import (
    ArrayLike, ArrayProtocol, is_gpu_array, ensure_cpu_array, validate_array_compatibility
)


class TestArrayLikeTypes:
    """Test ArrayLike types and utilities"""
    
    def test_is_gpu_array_with_numpy_array(self):
        """Test is_gpu_array returns False for NumPy arrays"""
        arr = np.array([1.0, 2.0, 3.0])
        assert is_gpu_array(arr) == False
    
    def test_is_gpu_array_with_mock_cupy_array(self):
        """Test is_gpu_array returns True for CuPy arrays"""
        mock_cupy = Mock()
        mock_cupy.get = Mock(return_value=np.array([1.0, 2.0, 3.0]))
        
        assert is_gpu_array(mock_cupy) == True
    
    def test_is_gpu_array_with_object_without_get(self):
        """Test is_gpu_array returns False for objects without get method"""
        regular_object = Mock()
        # Explicitly don't add get method
        del regular_object.get  # Remove if mock added it
        
        assert is_gpu_array(regular_object) == False
    
    def test_ensure_cpu_array_with_numpy_array(self):
        """Test ensure_cpu_array with NumPy array returns same array"""
        arr = np.array([1.0, 2.0, 3.0])
        result = ensure_cpu_array(arr)
        
        assert isinstance(result, np.ndarray)
        np.testing.assert_array_equal(result, arr)
    
    def test_ensure_cpu_array_with_mock_cupy_array(self):
        """Test ensure_cpu_array with CuPy array calls get()"""
        expected = np.array([1.0, 2.0, 3.0])
        mock_cupy = Mock()
        mock_cupy.get.return_value = expected
        
        result = ensure_cpu_array(mock_cupy)
        
        mock_cupy.get.assert_called_once()
        np.testing.assert_array_equal(result, expected)
    
    def test_ensure_cpu_array_with_list(self):
        """Test ensure_cpu_array converts list to NumPy array"""
        data = [1.0, 2.0, 3.0]
        result = ensure_cpu_array(data)
        
        assert isinstance(result, np.ndarray)
        np.testing.assert_array_equal(result, data)
    
    def test_validate_array_compatibility_same_arrays(self):
        """Test validate_array_compatibility with identical arrays"""
        arr1 = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        arr2 = np.array([4.0, 5.0, 6.0], dtype=np.float32)
        
        assert validate_array_compatibility(arr1, arr2) == True
    
    def test_validate_array_compatibility_different_shapes(self):
        """Test validate_array_compatibility with different shapes"""
        arr1 = np.array([1.0, 2.0, 3.0])
        arr2 = np.array([[1.0, 2.0], [3.0, 4.0]])
        
        assert validate_array_compatibility(arr1, arr2) == False
    
    def test_validate_array_compatibility_different_dtypes(self):
        """Test validate_array_compatibility with different dtypes"""
        arr1 = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        arr2 = np.array([1.0, 2.0, 3.0], dtype=np.float64)
        
        assert validate_array_compatibility(arr1, arr2) == False
    
    def test_validate_array_compatibility_different_backends(self):
        """Test validate_array_compatibility with different backends"""
        arr1 = np.array([1.0, 2.0, 3.0])
        mock_cupy = Mock()
        mock_cupy.shape = (3,)
        mock_cupy.dtype = np.float64
        
        # Different types (NumPy vs Mock/CuPy)
        assert validate_array_compatibility(arr1, mock_cupy) == False
    
    def test_validate_array_compatibility_both_cupy_arrays(self):
        """Test validate_array_compatibility with both CuPy arrays"""
        # Create a mock CuPy class to ensure both objects have same type
        class MockCuPyArray:
            def __init__(self, shape, dtype):
                self.shape = shape
                self.dtype = dtype
                self.get = Mock()
        
        mock_cupy1 = MockCuPyArray((3,), np.float32)
        mock_cupy2 = MockCuPyArray((3,), np.float32)
        
        assert validate_array_compatibility(mock_cupy1, mock_cupy2) == True
    
    def test_array_protocol_runtime_checkable(self):
        """Test ArrayProtocol is runtime checkable"""
        # Create a class that implements the protocol
        class MockArray:
            def __init__(self):
                self.shape = (3,)
                self.dtype = np.float32
            
            def __array__(self):
                return np.array([1.0, 2.0, 3.0])
            
            def astype(self, dtype):
                return MockArray()
        
        mock_arr = MockArray()
        assert isinstance(mock_arr, ArrayProtocol)
    
    def test_array_protocol_with_numpy_array(self):
        """Test NumPy array implements ArrayProtocol"""
        arr = np.array([1.0, 2.0, 3.0])
        assert isinstance(arr, ArrayProtocol)
    
    def test_array_protocol_missing_methods(self):
        """Test object without required methods doesn't implement ArrayProtocol"""
        class IncompleteArray:
            def __init__(self):
                self.shape = (3,)
                self.dtype = np.float32
            # Missing __array__ and astype methods
        
        incomplete = IncompleteArray()
        assert not isinstance(incomplete, ArrayProtocol)
    
    def test_edge_case_empty_arrays(self):
        """Test utilities work with empty arrays"""
        empty_arr = np.array([])
        
        assert is_gpu_array(empty_arr) == False
        result = ensure_cpu_array(empty_arr)
        np.testing.assert_array_equal(result, empty_arr)
    
    def test_edge_case_zero_dimensional_arrays(self):
        """Test utilities work with scalar arrays"""
        scalar_arr = np.array(5.0)
        
        assert is_gpu_array(scalar_arr) == False
        result = ensure_cpu_array(scalar_arr)
        np.testing.assert_array_equal(result, scalar_arr)