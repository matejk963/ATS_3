"""Tests for ATRCalculator - TDD Implementation"""

import pytest
import numpy as np
from src.feature_engineering.array_backend import ArrayBackend
from src.feature_engineering.atr_calculator import ATRCalculator


class TestATRCalculator:
    
    @pytest.fixture
    def backend(self):
        return ArrayBackend('numpy')
    
    @pytest.fixture
    def calculator(self, backend):
        return ATRCalculator(backend)
    
    @pytest.fixture
    def ohlc_data(self):
        """Generate sample OHLC data"""
        np.random.seed(42)
        n_periods = 500
        
        # Generate realistic OHLC data
        close = 100 + np.cumsum(np.random.randn(n_periods) * 0.5)
        
        # High/Low should be around close with some spread
        spread = np.abs(np.random.randn(n_periods) * 0.3) + 0.1
        high = close + spread * np.random.uniform(0.3, 1.0, n_periods)
        low = close - spread * np.random.uniform(0.3, 1.0, n_periods)
        
        # Ensure OHLC relationships hold
        high = np.maximum(high, close)
        low = np.minimum(low, close)
        
        return high, low, close
    
    def test_calculator_init(self, backend):
        """Test ATRCalculator initialization"""
        calculator = ATRCalculator(backend)
        assert calculator.backend == backend
        assert calculator.xp == backend.xp
    
    def test_compute_atr_basic(self, calculator, ohlc_data):
        """Test basic ATR computation"""
        high, low, close = ohlc_data
        
        result = calculator.compute_atr(high, low, close, period=14)
        
        # Should return same length as input
        assert len(result) == len(high)
        
        # ATR should be positive (excluding NaN values)
        valid_result = result[~np.isnan(result)]
        assert np.all(valid_result >= 0)
        
        # First few values might be NaN due to insufficient data
        valid_atr = result[~np.isnan(result)]
        assert len(valid_atr) > 0
        assert np.all(valid_atr > 0)
    
    def test_compute_atr_default_period(self, calculator, ohlc_data):
        """Test ATR with default period (14)"""
        high, low, close = ohlc_data
        
        result = calculator.compute_atr(high, low, close)
        
        assert len(result) == len(high)
        assert np.all(result[~np.isnan(result)] >= 0)
    
    def test_compute_atr_custom_period(self, calculator, ohlc_data):
        """Test ATR with custom periods"""
        high, low, close = ohlc_data
        
        periods = [5, 10, 20, 50]
        
        for period in periods:
            result = calculator.compute_atr(high, low, close, period=period)
            
            assert len(result) == len(high)
            assert np.all(result[~np.isnan(result)] >= 0)
            
            # Longer periods should generally give smoother (less volatile) ATR
            valid_count = np.sum(~np.isnan(result))
            assert valid_count > 0
    
    def test_true_range_calculation(self, calculator, ohlc_data):
        """Test True Range calculation component"""
        high, low, close = ohlc_data
        
        tr = calculator._compute_true_range(high, low, close)
        
        # True Range should be positive
        assert np.all(tr >= 0)
        
        # True Range should be at least High - Low
        hl_range = high - low
        np.testing.assert_array_less(-1e-10, tr - hl_range)  # TR >= H-L
    
    def test_true_range_components(self, calculator):
        """Test True Range with known values"""
        # Simple test case where we know the expected True Range
        high = np.array([105.0, 108.0, 107.0])
        low = np.array([102.0, 104.0, 103.0])
        close = np.array([104.0, 106.0, 105.0])
        
        tr = calculator._compute_true_range(high, low, close)
        
        # First TR is just H-L (no previous close)
        assert tr[0] == 105.0 - 102.0  # 3.0
        
        # Second TR should be max of:
        # - H-L: 108-104 = 4
        # - H-prev_close: 108-104 = 4
        # - prev_close-L: 104-104 = 0
        # So TR[1] should be 4.0
        assert tr[1] == 4.0
        
        # Third TR should be max of:
        # - H-L: 107-103 = 4
        # - H-prev_close: 107-106 = 1
        # - prev_close-L: 106-103 = 3
        # So TR[2] should be 4.0
        assert tr[2] == 4.0
    
    def test_empty_input(self, calculator):
        """Test behavior with empty input"""
        empty = np.array([])
        
        result = calculator.compute_atr(empty, empty, empty)
        
        assert len(result) == 0
    
    def test_single_period_input(self, calculator):
        """Test behavior with single period"""
        high = np.array([105.0])
        low = np.array([102.0])
        close = np.array([104.0])
        
        result = calculator.compute_atr(high, low, close, period=14)
        
        # Single period should return the high-low range or NaN
        assert len(result) == 1
        # With period=14 and only 1 data point, result should be NaN
        assert np.isnan(result[0])
    
    def test_insufficient_data(self, calculator):
        """Test behavior with insufficient data for period"""
        # Only 5 periods but asking for period=14
        high = np.array([105.0, 108.0, 107.0, 109.0, 106.0])
        low = np.array([102.0, 104.0, 103.0, 105.0, 103.0])
        close = np.array([104.0, 106.0, 105.0, 107.0, 105.0])
        
        result = calculator.compute_atr(high, low, close, period=14)
        
        # Should still return array of same length
        assert len(result) == 5
        
        # Early values should be NaN due to insufficient data
        assert np.all(np.isnan(result[:13]))  # First 13 should be NaN
        
        # Last values might have some calculated ATR
        if not np.isnan(result[-1]):
            assert result[-1] > 0
    
    def test_backend_compatibility(self, ohlc_data):
        """Test NumPy and CuPy backend compatibility"""
        high, low, close = ohlc_data
        
        # Test NumPy backend
        numpy_backend = ArrayBackend('numpy')
        numpy_calc = ATRCalculator(numpy_backend)
        numpy_result = numpy_calc.compute_atr(high, low, close, period=14)
        
        # Test CuPy backend (if available)
        try:
            cupy_backend = ArrayBackend('cupy')
            cupy_calc = ATRCalculator(cupy_backend)
            cupy_result = cupy_calc.compute_atr(high, low, close, period=14)
            
            # Results should be numerically equivalent
            np.testing.assert_allclose(
                numpy_result,
                cupy_backend.to_cpu(cupy_result),
                rtol=1e-6, atol=1e-6,
                equal_nan=True  # NaN values should match
            )
        except ImportError:
            pytest.skip("CuPy not available")
    
    def test_atr_smoothing_behavior(self, calculator):
        """Test that ATR provides smoothing over time"""
        # Create data with known volatility pattern
        n = 100
        high = np.ones(n) * 105
        low = np.ones(n) * 95
        close = np.ones(n) * 100
        
        # Add some volatility spikes
        high[50:55] = 120  # Big spike
        low[50:55] = 80
        
        atr = calculator.compute_atr(high, low, close, period=14)
        
        # ATR should be relatively stable except around the spike
        # The spike should cause ATR to increase but then smooth out
        valid_atr = atr[~np.isnan(atr)]
        
        if len(valid_atr) > 20:  # Ensure we have enough data
            # ATR before spike should be lower than during/after spike
            pre_spike = np.mean(valid_atr[:30]) if len(valid_atr) > 30 else valid_atr[0]
            post_spike = np.mean(valid_atr[-10:]) if len(valid_atr) > 10 else valid_atr[-1]
            
            # After the spike, ATR should still be elevated due to smoothing
            assert post_spike >= pre_spike
    
    def test_parameter_validation(self, calculator, ohlc_data):
        """Test parameter validation"""
        high, low, close = ohlc_data
        
        # Period should be positive
        with pytest.raises((ValueError, AssertionError)):
            calculator.compute_atr(high, low, close, period=0)
        
        with pytest.raises((ValueError, AssertionError)):
            calculator.compute_atr(high, low, close, period=-5)
    
    def test_input_array_lengths(self, calculator):
        """Test that input arrays must have same length"""
        high = np.array([105.0, 108.0])
        low = np.array([102.0, 104.0, 103.0])  # Different length
        close = np.array([104.0, 106.0])
        
        with pytest.raises((ValueError, AssertionError)):
            calculator.compute_atr(high, low, close)
    
    def test_atr_values_reasonable(self, calculator):
        """Test that ATR values are reasonable given input data"""
        # Create data with known ranges
        high = np.array([110, 115, 112, 118, 116])
        low = np.array([100, 105, 102, 108, 106])
        close = np.array([105, 110, 107, 113, 111])
        
        atr = calculator.compute_atr(high, low, close, period=3)
        
        # ATR should be related to the typical ranges
        typical_range = np.mean(high - low)  # Simple H-L average
        
        valid_atr = atr[~np.isnan(atr)]
        if len(valid_atr) > 0:
            # ATR should be in the same ballpark as typical H-L range
            assert np.all(valid_atr > 0)
            assert np.all(valid_atr < typical_range * 3)  # Shouldn't be wildly different