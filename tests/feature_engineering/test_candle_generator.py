"""Tests for CandleGenerator - TDD Implementation"""

import pytest
import numpy as np
from datetime import datetime, timedelta
from src.feature_engineering.array_backend import ArrayBackend
from src.feature_engineering.candle_generator import CandleGenerator


class TestCandleGenerator:
    
    @pytest.fixture
    def backend(self):
        return ArrayBackend('numpy')
    
    @pytest.fixture
    def generator(self, backend):
        return CandleGenerator(backend)
    
    @pytest.fixture
    def tick_data(self):
        """Generate sample tick data"""
        n_ticks = 1000
        base_time = datetime(2024, 1, 1)
        
        # Create timestamps every 10 seconds
        timestamps = np.array([
            (base_time + timedelta(seconds=i*10)).timestamp() 
            for i in range(n_ticks)
        ])
        
        # Generate realistic price movements
        np.random.seed(42)
        prices = 100 + np.cumsum(np.random.randn(n_ticks) * 0.1)
        
        return prices, timestamps
    
    def test_generator_init(self, backend):
        """Test CandleGenerator initialization"""
        generator = CandleGenerator(backend)
        assert generator.backend == backend
        assert generator.xp == backend.xp
    
    def test_generate_ohlc_1min(self, generator, tick_data):
        """Test OHLC generation for 1-minute candles"""
        prices, timestamps = tick_data
        
        result = generator.generate_ohlc(prices, timestamps, '1min')
        
        # Should return dict with OHLC arrays
        assert isinstance(result, dict)
        assert 'open' in result
        assert 'high' in result  
        assert 'low' in result
        assert 'close' in result
        
        # All arrays should have same length
        lengths = [len(result[key]) for key in result.keys()]
        assert len(set(lengths)) == 1
        
        # OHLC relationships should hold
        for i in range(len(result['open'])):
            o, h, l, c = result['open'][i], result['high'][i], result['low'][i], result['close'][i]
            assert l <= o, f"Low {l} should be <= Open {o} at index {i}"
            assert l <= h, f"Low {l} should be <= High {h} at index {i}" 
            assert l <= c, f"Low {l} should be <= Close {c} at index {i}"
            assert h >= o, f"High {h} should be >= Open {o} at index {i}"
            assert h >= c, f"High {h} should be >= Close {c} at index {i}"
    
    def test_generate_ohlc_5min(self, generator, tick_data):
        """Test OHLC generation for 5-minute candles"""
        prices, timestamps = tick_data
        
        result = generator.generate_ohlc(prices, timestamps, '5min')
        
        # 5min candles should have fewer bars than 1min
        result_1min = generator.generate_ohlc(prices, timestamps, '1min')
        assert len(result['open']) <= len(result_1min['open'])
    
    def test_empty_input(self, generator):
        """Test behavior with empty input arrays"""
        empty_prices = np.array([])
        empty_timestamps = np.array([])
        
        result = generator.generate_ohlc(empty_prices, empty_timestamps, '1min')
        
        # Should return empty arrays in dict
        for key in ['open', 'high', 'low', 'close']:
            assert len(result[key]) == 0
    
    def test_single_tick(self, generator):
        """Test behavior with single tick"""
        prices = np.array([100.0])
        timestamps = np.array([datetime.now().timestamp()])
        
        result = generator.generate_ohlc(prices, timestamps, '1min')
        
        # Single tick should create one candle with O=H=L=C
        assert len(result['open']) == 1
        assert result['open'][0] == result['high'][0] == result['low'][0] == result['close'][0]
        assert result['open'][0] == 100.0
    
    def test_backend_compatibility(self, tick_data):
        """Test NumPy and CuPy backend compatibility"""
        prices, timestamps = tick_data
        
        # Test NumPy backend
        numpy_backend = ArrayBackend('numpy')
        numpy_generator = CandleGenerator(numpy_backend)
        numpy_result = numpy_generator.generate_ohlc(prices, timestamps, '1min')
        
        # Test CuPy backend (if available)
        try:
            cupy_backend = ArrayBackend('cupy')
            cupy_generator = CandleGenerator(cupy_backend)
            cupy_result = cupy_generator.generate_ohlc(prices, timestamps, '1min')
            
            # Results should be numerically equivalent
            for key in ['open', 'high', 'low', 'close']:
                np.testing.assert_allclose(
                    numpy_result[key], 
                    list(cupy_backend.to_cpu(cupy_result[key])),
                    rtol=1e-10
                )
        except ImportError:
            pytest.skip("CuPy not available")
    
    def test_granularity_parsing(self, generator, tick_data):
        """Test different granularity formats"""
        prices, timestamps = tick_data
        
        # Test various formats
        valid_granularities = ['1min', '5min', '15min', '1H', '4H', '1D']
        
        for granularity in valid_granularities:
            try:
                result = generator.generate_ohlc(prices, timestamps, granularity)
                assert isinstance(result, dict)
                assert all(key in result for key in ['open', 'high', 'low', 'close'])
            except NotImplementedError:
                # Some granularities might not be implemented yet
                pass
    
    def test_invalid_granularity(self, generator, tick_data):
        """Test invalid granularity handling"""
        prices, timestamps = tick_data
        
        with pytest.raises((ValueError, NotImplementedError)):
            generator.generate_ohlc(prices, timestamps, 'invalid')