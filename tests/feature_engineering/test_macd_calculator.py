"""Tests for MACDCalculator - TDD Implementation"""

import pytest
import numpy as np
import pandas as pd
from src.feature_engineering.array_backend import ArrayBackend
from src.feature_engineering.macd_calculator import MACDCalculator


class TestMACDCalculator:
    
    @pytest.fixture
    def backend(self):
        return ArrayBackend('numpy')
    
    @pytest.fixture
    def calculator(self, backend):
        return MACDCalculator(backend)
    
    @pytest.fixture
    def price_data(self):
        """Generate sample price data"""
        np.random.seed(42)
        n_points = 1000
        prices = 100 + np.cumsum(np.random.randn(n_points) * 0.1)
        return prices
    
    def test_calculator_init(self, backend):
        """Test MACDCalculator initialization"""
        calculator = MACDCalculator(backend)
        assert calculator.backend == backend
        assert calculator.xp == backend.xp
    
    def test_compute_ema_vectorized_pandas_equivalence(self, calculator):
        """Test vectorized EMA matches pandas exactly"""
        np.random.seed(42)
        prices = 100 + np.cumsum(np.random.randn(1000) * 0.1)
        spans = [12, 26, 9, 14]
        
        for span in spans:
            # Pandas reference
            pandas_ema = pd.Series(prices).ewm(span=span).mean().values
            
            # Our vectorized implementation
            our_ema = calculator._compute_ema_vectorized(prices, span)
            
            # MANDATORY: High precision match (adjusted for float32 precision)
            np.testing.assert_allclose(pandas_ema, our_ema, rtol=1e-6, atol=1e-6,
                                     err_msg=f"EMA span={span} failed pandas equivalence")
    
    def test_compute_macd_basic(self, calculator, price_data):
        """Test basic MACD computation"""
        result = calculator.compute_macd(price_data, fast=12, slow=26, signal=9)
        
        # Should return dict with required keys
        assert isinstance(result, dict)
        assert 'macd' in result
        assert 'signal' in result
        assert 'histogram' in result
        
        # All arrays should have same length as input
        assert len(result['macd']) == len(price_data)
        assert len(result['signal']) == len(price_data)
        assert len(result['histogram']) == len(price_data)
        
        # Histogram should be MACD - Signal
        np.testing.assert_allclose(
            result['histogram'], 
            result['macd'] - result['signal'],
            rtol=1e-10
        )
    
    def test_compute_macd_default_parameters(self, calculator, price_data):
        """Test MACD with default parameters (12, 26, 9)"""
        result = calculator.compute_macd(price_data)
        
        # Should work with defaults
        assert isinstance(result, dict)
        assert all(key in result for key in ['macd', 'signal', 'histogram'])
    
    def test_compute_macd_custom_parameters(self, calculator, price_data):
        """Test MACD with custom parameters"""
        result = calculator.compute_macd(price_data, fast=5, slow=20, signal=7)
        
        assert isinstance(result, dict)
        assert all(key in result for key in ['macd', 'signal', 'histogram'])
    
    def test_ema_batch_processing(self, calculator):
        """Test batch EMA processing for multiple series"""
        np.random.seed(42)
        batch_size = 10
        n_points = 500
        
        # Create batch of price series
        data_batch = np.random.randn(batch_size, n_points).cumsum(axis=1) + 100
        spans = np.array([12, 26, 9, 14, 21, 5, 8, 13, 17, 30])
        
        result = calculator._compute_ema_batch(data_batch, spans)
        
        # Should return same shape
        assert result.shape == data_batch.shape
        
        # Verify each series individually
        for i in range(batch_size):
            individual_ema = calculator._compute_ema_vectorized(data_batch[i], spans[i])
            np.testing.assert_allclose(result[i], individual_ema, rtol=1e-6, atol=1e-6)
    
    def test_empty_input(self, calculator):
        """Test behavior with empty input"""
        empty_data = np.array([])
        
        result = calculator.compute_macd(empty_data)
        
        # Should return empty arrays
        for key in ['macd', 'signal', 'histogram']:
            assert len(result[key]) == 0
    
    def test_single_value_input(self, calculator):
        """Test behavior with single value"""
        single_value = np.array([100.0])
        
        result = calculator.compute_macd(single_value)
        
        # Should handle gracefully (may be NaN for some values)
        assert len(result['macd']) == 1
        assert len(result['signal']) == 1
        assert len(result['histogram']) == 1
    
    def test_backend_compatibility(self, price_data):
        """Test NumPy and CuPy backend compatibility"""
        # Test NumPy backend
        numpy_backend = ArrayBackend('numpy')
        numpy_calc = MACDCalculator(numpy_backend)
        numpy_result = numpy_calc.compute_macd(price_data)
        
        # Test CuPy backend (if available)
        try:
            cupy_backend = ArrayBackend('cupy') 
            cupy_calc = MACDCalculator(cupy_backend)
            cupy_result = cupy_calc.compute_macd(price_data)
            
            # Results should be numerically equivalent
            for key in ['macd', 'signal', 'histogram']:
                np.testing.assert_allclose(
                    numpy_result[key],
                    cupy_backend.to_cpu(cupy_result[key]),
                    rtol=1e-10
                )
        except ImportError:
            pytest.skip("CuPy not available")
    
    def test_ema_convolution_efficiency(self, calculator):
        """Test EMA convolution implementation efficiency"""
        # Large dataset to test GPU efficiency
        np.random.seed(42)
        large_data = np.random.randn(10000).cumsum() + 100
        
        # Should complete without memory issues
        result = calculator._compute_ema_vectorized(large_data, 26)
        
        assert len(result) == len(large_data)
        assert not np.any(np.isnan(result))  # Should not have NaN values
    
    def test_ema_weight_truncation(self, calculator):
        """Test EMA weight truncation for efficiency"""
        np.random.seed(42)
        data = np.random.randn(1000).cumsum() + 100
        
        # Short span - should use full weights
        short_result = calculator._compute_ema_vectorized(data, 12)
        
        # Long span - should truncate weights
        long_result = calculator._compute_ema_vectorized(data, 200)
        
        assert len(short_result) == len(data)
        assert len(long_result) == len(data)
        assert not np.any(np.isnan(short_result))
        assert not np.any(np.isnan(long_result))
    
    def test_macd_signal_relationship(self, calculator, price_data):
        """Test MACD and signal line relationship"""
        result = calculator.compute_macd(price_data, fast=12, slow=26, signal=9)
        
        macd = result['macd']
        signal = result['signal']
        
        # Signal should be EMA of MACD
        expected_signal = calculator._compute_ema_vectorized(macd, 9)
        np.testing.assert_allclose(signal, expected_signal, rtol=1e-10)
    
    def test_parameter_validation(self, calculator, price_data):
        """Test parameter validation"""
        # Fast should be less than slow
        with pytest.raises((ValueError, AssertionError)):
            calculator.compute_macd(price_data, fast=26, slow=12, signal=9)
        
        # Parameters should be positive
        with pytest.raises((ValueError, AssertionError)):
            calculator.compute_macd(price_data, fast=-12, slow=26, signal=9)