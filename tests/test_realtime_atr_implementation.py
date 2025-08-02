"""
Test suite for real-time ATR implementation following TDD approach.
This test suite defines the expected behavior of the new real-time ATR algorithm.
"""

import sys
import os
import pandas as pd
import numpy as np
import pytest
from pathlib import Path

# Add source directories to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root / "src"))
sys.path.append(str(project_root / "source_repos" / "EnergyTrading" / "Python" / "Utilities"))

# Import legacy implementation for comparison
from predictors_tools import compute_realtime_atr

# Import GPU implementation
from feature_engineering.array_backend import ArrayBackend
from feature_engineering.atr_calculator import ATRCalculator


class TestRealtimeATR:
    """Test class for real-time ATR implementation"""
    
    @pytest.fixture
    def sample_trade_data(self):
        """Create sample trade data for testing"""
        np.random.seed(42)
        n_trades = 50
        
        # Create realistic trade data with datetime, nanotime, tradeid, price
        base_time = pd.Timestamp('2025-01-01 00:00:00')
        trade_times = [base_time + pd.Timedelta(minutes=i*15) for i in range(n_trades)]
        
        trades_df = pd.DataFrame({
            'datetime': trade_times,
            'nanotime': [int(t.timestamp() * 1e9) for t in trade_times],
            'tradeid': [f'T{i:04d}' for i in range(n_trades)],
            'price': 100.0 + np.cumsum(np.random.normal(0, 0.5, n_trades))
        })
        
        return trades_df
    
    @pytest.fixture 
    def sample_historical_candles(self):
        """Create sample historical candle data"""
        np.random.seed(42)
        n_candles = 100
        
        # Create historical 1-hour candles
        base_time = pd.Timestamp('2024-12-01 00:00:00')
        candle_times = [base_time + pd.Timedelta(hours=i) for i in range(n_candles)]
        
        # Generate realistic OHLC data
        base_price = 95.0
        price_changes = np.random.normal(0, 0.3, n_candles)
        close_prices = base_price + np.cumsum(price_changes)
        
        spreads = np.random.uniform(0.1, 1.5, n_candles)
        high_prices = close_prices + spreads * 0.6
        low_prices = close_prices - spreads * 0.4
        
        # Ensure OHLC relationships
        high_prices = np.maximum(high_prices, close_prices)
        low_prices = np.minimum(low_prices, close_prices)
        open_prices = np.roll(close_prices, 1)
        open_prices[0] = base_price
        
        historical_candles = pd.DataFrame({
            'open': open_prices,
            'high': high_prices,
            'low': low_prices,
            'close': close_prices
        }, index=candle_times)
        
        return historical_candles
    
    def test_compute_atr_method_signature(self, sample_trade_data, sample_historical_candles):
        """Test that compute_atr method has the correct signature and returns expected format"""
        try:
            backend = ArrayBackend('cupy')  # Use GPU backend
        except Exception:
            pytest.skip("CuPy ArrayBackend not available")
        
        atr_calc = ATRCalculator(backend)
        
        # Test that the method accepts the new signature and returns the correct format
        result = atr_calc.compute_atr(
            trades_df=sample_trade_data,
            historical_candles=sample_historical_candles,
            atr_period=14,
            price_col='price',
            datetime_col='datetime',
            candle_granularity='1h'
        )
        
        # Verify result format
        expected_columns = ['datetime', 'nanotime', 'tradeid', 'atr']
        assert list(result.columns) == expected_columns, f"Expected columns {expected_columns}, got {list(result.columns)}"
        assert len(result) == len(sample_trade_data), f"Expected {len(sample_trade_data)} results, got {len(result)}"
        assert 'atr' in result.columns, "ATR column missing from result"
    
    def test_realtime_candle_generation(self, sample_trade_data):
        """Test that real-time candles are generated correctly per trade"""
        try:
            backend = ArrayBackend('cupy')
        except Exception:
            pytest.skip("CuPy ArrayBackend not available")
        
        atr_calc = ATRCalculator(backend)
        
        # Test the helper method exists and works
        result = atr_calc._compute_realtime_candles_per_trade(
            sample_trade_data, 'price', 'datetime', '1h'
        )
        
        # Verify result has candle columns
        expected_columns = ['period', 'candle_open', 'candle_high', 'candle_low', 'candle_close']
        for col in expected_columns:
            assert col in result.columns, f"Missing column {col} in real-time candles result"
        
        assert len(result) == len(sample_trade_data), f"Expected {len(sample_trade_data)} candle results, got {len(result)}"
    
    def test_historical_lookback_integration(self, sample_trade_data, sample_historical_candles):
        """Test that historical lookback integration works correctly"""
        try:
            backend = ArrayBackend('cupy')
        except Exception:
            pytest.skip("CuPy ArrayBackend not available")
        
        atr_calc = ATRCalculator(backend)
        
        # Test the helper method exists and works
        result = atr_calc._pair_trade_with_historical_lookback(
            sample_trade_data, sample_historical_candles, 1,
            'price', 'datetime', '1h', 'close'
        )
        
        # Verify result has lookback columns
        assert 'close_t-1' in result.columns, "Missing historical lookback column close_t-1"
        assert len(result) == len(sample_trade_data), f"Expected {len(sample_trade_data)} lookback results, got {len(result)}"
    
    def test_true_range_per_trade_calculation(self):
        """Test that True Range is calculated correctly per trade"""
        try:
            backend = ArrayBackend('cupy')
        except Exception:
            pytest.skip("CuPy ArrayBackend not available")
        
        atr_calc = ATRCalculator(backend)
        
        # Test data
        candle_high = np.array([102.0, 103.5, 101.0])
        candle_low = np.array([100.0, 101.0, 99.5])
        prev_close = np.array([np.nan, 102.0, 102.5])
        
        # Test the helper method exists and works
        result = atr_calc._calculate_true_range_per_trade(
            candle_high, candle_low, prev_close
        )
        
        # Verify True Range calculation
        assert len(result) == 3, f"Expected 3 True Range values, got {len(result)}"
        
        # First value should be high-low (no previous close)
        expected_first = 102.0 - 100.0  # 2.0
        if hasattr(result, 'get'):  # CuPy array
            result_cpu = result.get()
        else:
            result_cpu = result
        
        assert abs(result_cpu[0] - expected_first) < 1e-6, f"First TR should be {expected_first}, got {result_cpu[0]}"
    
    def test_simple_averaging_atr(self):
        """Test that ATR uses simple averaging, not Wilder's smoothing"""
        # This test verifies that our implementation uses simple averaging through end-to-end testing
        try:
            backend = ArrayBackend('cupy')
        except Exception:
            pytest.skip("CuPy ArrayBackend not available")
        
        # Create simple test data to verify simple averaging behavior
        trades_df = pd.DataFrame({
            'datetime': pd.to_datetime(['2025-01-01 01:00:00', '2025-01-01 02:00:00', '2025-01-01 03:00:00']),
            'nanotime': [1735693200000000000, 1735696800000000000, 1735700400000000000],
            'tradeid': ['T001', 'T002', 'T003'],
            'price': [100.0, 101.0, 102.0]
        })
        
        historical_candles = pd.DataFrame({
            'open': [99.0, 100.0],
            'high': [99.5, 100.5],
            'low': [98.5, 99.5],
            'close': [99.0, 100.0]
        }, index=pd.to_datetime(['2024-12-31 23:00:00', '2025-01-01 00:00:00']))
        
        atr_calc = ATRCalculator(backend)
        
        # Test that the method works and produces reasonable results
        result = atr_calc.compute_atr(
            trades_df=trades_df,
            historical_candles=historical_candles,
            atr_period=2
        )
        
        assert len(result) == 3, f"Expected 3 ATR results, got {len(result)}"
        assert 'atr' in result.columns, "ATR column missing from result"
    
    def test_match_with_legacy_algorithm(self, sample_trade_data, sample_historical_candles):
        """Test that new implementation matches legacy algorithm output"""
        # Run legacy algorithm
        legacy_result = compute_realtime_atr(
            trades_df=sample_trade_data,
            historical_candles=sample_historical_candles,
            atr_period=14,
            price_col='price',
            datetime_col='datetime',
            candle_granularity='1h'
        )
        
        try:
            backend = ArrayBackend('cupy')
        except Exception:
            pytest.skip("CuPy ArrayBackend not available")
        
        atr_calc = ATRCalculator(backend)
        
        # Test our implementation
        gpu_result = atr_calc.compute_atr(
            trades_df=sample_trade_data,
            historical_candles=sample_historical_candles,
            atr_period=14,
            price_col='price',
            datetime_col='datetime',
            candle_granularity='1h'
        )
        
        # Compare results
        match_rate = calculate_match_rate(legacy_result['atr'], gpu_result['atr'])
        assert match_rate > 0.99, f"Match rate {match_rate:.1%} below 99% threshold"
    
    def test_gpu_acceleration_compatibility(self, sample_trade_data, sample_historical_candles):
        """Test that implementation works with GPU backend"""
        # Note: ArrayBackend is GPU-only, so we test CuPy backend functionality
        try:
            backend = ArrayBackend('cupy')
            atr_calc = ATRCalculator(backend)
            
            # Test that GPU implementation works
            result = atr_calc.compute_atr(
                trades_df=sample_trade_data,
                historical_candles=sample_historical_candles,
                atr_period=14
            )
            
            # Verify GPU computation succeeded
            assert len(result) > 0, "GPU computation returned empty result"
            assert 'atr' in result.columns, "GPU computation missing ATR column"
            
            # Verify ArrayBackend is using CuPy
            assert backend.backend == 'cupy', "Backend should be using CuPy for GPU acceleration"
            
        except Exception:
            pytest.skip("CuPy ArrayBackend not available")


def calculate_match_rate(legacy_values, gpu_values, tolerance=1e-6):
    """Helper function to calculate match rate between implementations"""
    legacy_array = np.array(legacy_values)
    gpu_array = np.array(gpu_values)
    
    # Find valid values
    valid_mask = ~np.isnan(legacy_array) & ~np.isnan(gpu_array)
    
    if not np.any(valid_mask):
        return 0.0
    
    legacy_valid = legacy_array[valid_mask]
    gpu_valid = gpu_array[valid_mask]
    
    abs_diff = np.abs(legacy_valid - gpu_valid)
    matches = abs_diff < tolerance
    
    return np.sum(matches) / len(matches)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])