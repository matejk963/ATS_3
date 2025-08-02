"""Tests for ArrayBackend abstraction - TDD approach"""

import pytest
import numpy as np
from unittest.mock import Mock, patch, MagicMock

from src.feature_engineering.array_backend import ArrayBackend


class TestArrayBackend:
    """Test ArrayBackend functionality"""
    
    def test_numpy_backend_initialization(self):
        """Test ArrayBackend initializes with NumPy"""
        backend = ArrayBackend('numpy')
        assert backend.backend == 'numpy'
        assert backend.xp == np
    
    def test_default_backend_is_numpy(self):
        """Test default backend is NumPy"""
        backend = ArrayBackend()
        assert backend.backend == 'numpy'
        assert backend.xp == np
    
    def test_asarray_creates_numpy_array(self):
        """Test asarray creates NumPy array with correct dtype"""
        backend = ArrayBackend('numpy')
        data = [1.0, 2.0, 3.0]
        result = backend.asarray(data, dtype='float32')
        
        assert isinstance(result, np.ndarray)
        assert result.dtype == np.float32
        np.testing.assert_array_equal(result, [1.0, 2.0, 3.0])
    
    def test_to_cpu_with_numpy_array(self):
        """Test to_cpu with NumPy array returns same array"""
        backend = ArrayBackend('numpy')
        arr = np.array([1.0, 2.0, 3.0])
        result = backend.to_cpu(arr)
        
        assert isinstance(result, np.ndarray)
        np.testing.assert_array_equal(result, arr)
    
    def test_zeros_creates_correct_array(self):
        """Test zeros creates array with correct shape and dtype"""
        backend = ArrayBackend('numpy')
        result = backend.zeros((3, 4), dtype='float32')
        
        assert result.shape == (3, 4)
        assert result.dtype == np.float32
        assert np.all(result == 0)
    
    def test_ones_creates_correct_array(self):
        """Test ones creates array with correct shape and dtype"""
        backend = ArrayBackend('numpy')
        result = backend.ones((2, 3), dtype='float32')
        
        assert result.shape == (2, 3)
        assert result.dtype == np.float32
        assert np.all(result == 1)
    
    def test_empty_creates_correct_shape(self):
        """Test empty creates array with correct shape and dtype"""
        backend = ArrayBackend('numpy')
        result = backend.empty((5, 2), dtype='float32')
        
        assert result.shape == (5, 2)
        assert result.dtype == np.float32
    
    @patch('builtins.__import__')
    def test_cupy_backend_with_cupy_available(self, mock_import):
        """Test CuPy backend when CuPy is available"""
        # Mock CuPy module
        mock_cupy = Mock()
        mock_cupy.asarray = Mock(return_value=Mock())
        mock_cupy.zeros = Mock(return_value=Mock())
        mock_cupy.ones = Mock(return_value=Mock())
        mock_cupy.empty = Mock(return_value=Mock())
        
        def mock_import_func(name, *args, **kwargs):
            if name == 'cupy':
                return mock_cupy
            # Call real import for other modules
            return __import__(name, *args, **kwargs)
        
        mock_import.side_effect = mock_import_func
        
        backend = ArrayBackend('cupy')
        assert backend.backend == 'cupy'
        assert backend.xp == mock_cupy
    
    @patch('builtins.__import__')
    def test_cupy_backend_fallback_to_numpy(self, mock_import):
        """Test CuPy backend falls back to NumPy when CuPy unavailable"""
        def mock_import_func(name, *args, **kwargs):
            if name == 'cupy':
                raise ImportError("CuPy not available")
            return __import__(name, *args, **kwargs)
        
        mock_import.side_effect = mock_import_func
        
        with patch('builtins.print') as mock_print:
            backend = ArrayBackend('cupy')
            mock_print.assert_called_with("CuPy not available, falling back to NumPy")
        
        assert backend.backend == 'cupy'  # backend name stays 'cupy'
        assert backend.xp == np  # but actual module is numpy
    
    def test_to_cpu_with_mock_cupy_array(self):
        """Test to_cpu with mock CuPy array calls get() method"""
        backend = ArrayBackend('numpy')
        
        # Mock CuPy array with get() method
        mock_cupy_array = Mock()
        expected_result = np.array([1.0, 2.0, 3.0])
        mock_cupy_array.get.return_value = expected_result
        
        result = backend.to_cpu(mock_cupy_array)
        
        mock_cupy_array.get.assert_called_once()
        np.testing.assert_array_equal(result, expected_result)
    
    def test_different_dtype_handling(self):
        """Test backend handles different dtypes correctly"""
        backend = ArrayBackend('numpy')
        
        # Test float64
        result_f64 = backend.asarray([1, 2, 3], dtype='float64')
        assert result_f64.dtype == np.float64
        
        # Test int32
        result_i32 = backend.asarray([1, 2, 3], dtype='int32')
        assert result_i32.dtype == np.int32
    
    def test_backend_consistency(self):
        """Test backend operations are consistent"""
        backend = ArrayBackend('numpy')
        
        # Create arrays using different methods
        zeros = backend.zeros((3,), dtype='float32')
        ones = backend.ones((3,), dtype='float32')
        data = backend.asarray([1.0, 2.0, 3.0], dtype='float32')
        
        # All should have same dtype and be from same backend
        assert zeros.dtype == ones.dtype == data.dtype
        assert type(zeros) == type(ones) == type(data)