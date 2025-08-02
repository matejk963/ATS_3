"""Tests for IndicatorResultConverter - TDD Implementation"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any

from src.feature_engineering.array_backend import ArrayBackend
from src.feature_engineering.indicator_result_converter import IndicatorResultConverter
from src.feature_engineering.gpu_converter import GPUArrayConverter, DataFrameMetadata


class TestIndicatorResultConverter:
    
    @pytest.fixture
    def sample_timestamps(self):
        """Create sample timestamp index"""
        start_time = datetime(2024, 1, 1, 9, 0)
        timestamps = [start_time + timedelta(minutes=i) for i in range(100)]
        return pd.DatetimeIndex(timestamps, name='datetime')
    
    @pytest.fixture
    def sample_metadata(self, sample_timestamps):
        """Create sample DataFrame metadata"""
        return DataFrameMetadata(
            index=sample_timestamps,
            columns=['price', 'volume'],
            dtypes={'price': 'float64', 'volume': 'float64'}
        )
    
    @pytest.fixture
    def macd_result(self):
        """Create sample MACD result"""
        n = 100
        return {
            'macd': np.random.randn(n) * 0.1,
            'signal': np.random.randn(n) * 0.05,
            'histogram': np.random.randn(n) * 0.02
        }
    
    @pytest.fixture
    def atr_result(self):
        """Create sample ATR result"""
        return np.abs(np.random.randn(100)) * 0.5
    
    @pytest.fixture
    def candle_result(self):
        """Create sample candle result"""
        n = 50  # Candles are typically fewer than ticks
        base_prices = 100 + np.cumsum(np.random.randn(n) * 0.1)
        return {
            'open': base_prices + np.random.randn(n) * 0.05,
            'high': base_prices + np.abs(np.random.randn(n)) * 0.1,
            'low': base_prices - np.abs(np.random.randn(n)) * 0.1,
            'close': base_prices + np.random.randn(n) * 0.05
        }
    
    @pytest.fixture
    def swing_result(self):
        """Create sample swing result"""
        n = 100
        swing_highs = np.zeros(n, dtype=bool)
        swing_lows = np.zeros(n, dtype=bool)
        
        # Add some random swing points
        swing_highs[[10, 30, 70, 90]] = True
        swing_lows[[5, 25, 55, 85]] = True
        
        return {
            'swing_highs': swing_highs,
            'swing_lows': swing_lows
        }
    
    def test_converter_initialization(self):
        """Test IndicatorResultConverter can be initialized"""
        converter = IndicatorResultConverter()
        assert converter is not None
    
    def test_macd_to_dataframe_basic(self, macd_result, sample_metadata):
        """Test MACD result conversion to DataFrame"""
        converter = IndicatorResultConverter()
        
        df = converter.macd_to_dataframe(macd_result, sample_metadata)
        
        # Should be a DataFrame
        assert isinstance(df, pd.DataFrame)
        
        # Should have correct columns
        expected_columns = ['macd', 'signal', 'histogram']
        assert list(df.columns) == expected_columns
        
        # Should have same length as input arrays
        assert len(df) == len(macd_result['macd'])
        
        # Should preserve index from metadata
        pd.testing.assert_index_equal(df.index, sample_metadata.index)
        
        # Data should match input arrays
        np.testing.assert_array_equal(df['macd'].values, macd_result['macd'])
        np.testing.assert_array_equal(df['signal'].values, macd_result['signal'])
        np.testing.assert_array_equal(df['histogram'].values, macd_result['histogram'])
    
    def test_macd_to_dataframe_with_prefix(self, macd_result, sample_metadata):
        """Test MACD conversion with column prefix"""
        converter = IndicatorResultConverter()
        
        df = converter.macd_to_dataframe(macd_result, sample_metadata, prefix='15min_')
        
        # Should have prefixed columns
        expected_columns = ['15min_macd', '15min_signal', '15min_histogram']
        assert list(df.columns) == expected_columns
        
        # Data should still match
        np.testing.assert_array_equal(df['15min_macd'].values, macd_result['macd'])
    
    def test_atr_to_dataframe_basic(self, atr_result, sample_metadata):
        """Test ATR result conversion to DataFrame"""
        converter = IndicatorResultConverter()
        
        df = converter.atr_to_dataframe(atr_result, sample_metadata)
        
        # Should be a DataFrame with single column
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ['atr']
        
        # Should have correct length and index
        assert len(df) == len(atr_result)
        pd.testing.assert_index_equal(df.index, sample_metadata.index)
        
        # Data should match
        np.testing.assert_array_equal(df['atr'].values, atr_result)
    
    def test_atr_to_dataframe_with_prefix(self, atr_result, sample_metadata):
        """Test ATR conversion with column prefix"""
        converter = IndicatorResultConverter()
        
        df = converter.atr_to_dataframe(atr_result, sample_metadata, prefix='14d_')
        
        # Should have prefixed column
        assert list(df.columns) == ['14d_atr']
        np.testing.assert_array_equal(df['14d_atr'].values, atr_result)
    
    def test_candles_to_dataframe_basic(self, candle_result, sample_timestamps):
        """Test candle result conversion to DataFrame"""
        converter = IndicatorResultConverter()
        
        # Create metadata for candle length
        candle_timestamps = sample_timestamps[:len(candle_result['open'])]
        candle_metadata = DataFrameMetadata(
            index=candle_timestamps,
            columns=['timestamp'],
            dtypes={'timestamp': 'datetime64[ns]'}
        )
        
        df = converter.candles_to_dataframe(candle_result, candle_metadata)
        
        # Should have OHLC columns
        expected_columns = ['open', 'high', 'low', 'close']
        assert list(df.columns) == expected_columns
        
        # Should have correct length
        assert len(df) == len(candle_result['open'])
        
        # Should preserve index
        pd.testing.assert_index_equal(df.index, candle_metadata.index)
        
        # Data should match
        for col in expected_columns:
            np.testing.assert_array_equal(df[col].values, candle_result[col])
    
    def test_candles_to_dataframe_with_prefix(self, candle_result, sample_timestamps):
        """Test candle conversion with prefix"""
        converter = IndicatorResultConverter()
        
        candle_timestamps = sample_timestamps[:len(candle_result['open'])]
        candle_metadata = DataFrameMetadata(
            index=candle_timestamps,
            columns=['timestamp'],
            dtypes={'timestamp': 'datetime64[ns]'}
        )
        
        df = converter.candles_to_dataframe(candle_result, candle_metadata, prefix='5min_')
        
        expected_columns = ['5min_open', '5min_high', '5min_low', '5min_close']
        assert list(df.columns) == expected_columns
    
    def test_swings_to_dataframe_basic(self, swing_result, sample_metadata):
        """Test swing points conversion to DataFrame"""
        converter = IndicatorResultConverter()
        
        df = converter.swings_to_dataframe(swing_result, sample_metadata)
        
        # Should have swing columns
        expected_columns = ['swing_highs', 'swing_lows']
        assert list(df.columns) == expected_columns
        
        # Should have boolean dtype
        assert df['swing_highs'].dtype == bool
        assert df['swing_lows'].dtype == bool
        
        # Should have correct length and index
        assert len(df) == len(swing_result['swing_highs'])
        pd.testing.assert_index_equal(df.index, sample_metadata.index)
        
        # Data should match
        np.testing.assert_array_equal(df['swing_highs'].values, swing_result['swing_highs'])
        np.testing.assert_array_equal(df['swing_lows'].values, swing_result['swing_lows'])
    
    def test_swings_to_dataframe_with_prefix(self, swing_result, sample_metadata):
        """Test swing conversion with prefix"""
        converter = IndicatorResultConverter()
        
        df = converter.swings_to_dataframe(swing_result, sample_metadata, prefix='20p_')
        
        expected_columns = ['20p_swing_highs', '20p_swing_lows']
        assert list(df.columns) == expected_columns
        assert df['20p_swing_highs'].dtype == bool
    
    def test_generic_arrays_to_dataframe(self, sample_metadata):
        """Test generic multi-array conversion"""
        converter = IndicatorResultConverter()
        
        # Create test arrays
        arrays = {
            'indicator1': np.random.randn(100),
            'indicator2': np.random.randn(100) * 2,
            'indicator3': np.random.randn(100) * 0.5
        }
        
        df = converter.arrays_to_dataframe(arrays, sample_metadata)
        
        # Should have all columns
        expected_columns = ['indicator1', 'indicator2', 'indicator3']
        assert set(df.columns) == set(expected_columns)
        
        # Should preserve data
        for col in expected_columns:
            np.testing.assert_array_equal(df[col].values, arrays[col])
    
    def test_generic_arrays_with_prefix(self, sample_metadata):
        """Test generic conversion with prefix"""
        converter = IndicatorResultConverter()
        
        arrays = {
            'value1': np.random.randn(100),
            'value2': np.random.randn(100)
        }
        
        df = converter.arrays_to_dataframe(arrays, sample_metadata, prefix='test_')
        
        expected_columns = ['test_value1', 'test_value2']
        assert list(df.columns) == expected_columns
    
    def test_gpu_array_compatibility(self, macd_result, sample_metadata):
        """Test conversion works with GPU arrays (CuPy)"""
        converter = IndicatorResultConverter()
        
        # Test with ArrayBackend to simulate GPU arrays
        backend = ArrayBackend('numpy')  # Will fallback if CuPy unavailable
        
        # Convert to backend arrays
        gpu_macd_result = {
            key: backend.asarray(value) for key, value in macd_result.items()
        }
        
        df = converter.macd_to_dataframe(gpu_macd_result, sample_metadata)
        
        # Should work the same way
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ['macd', 'signal', 'histogram']
        
        # Data should match original (allowing for tiny precision differences)
        np.testing.assert_allclose(df['macd'].values, macd_result['macd'], rtol=1e-7, atol=1e-10)
    
    def test_empty_arrays_handling(self, sample_timestamps):
        """Test handling of empty arrays"""
        converter = IndicatorResultConverter()
        
        # Create empty metadata
        empty_metadata = DataFrameMetadata(
            index=pd.DatetimeIndex([]),
            columns=[],
            dtypes={}
        )
        
        # Empty MACD result
        empty_macd = {
            'macd': np.array([]),
            'signal': np.array([]),
            'histogram': np.array([])
        }
        
        df = converter.macd_to_dataframe(empty_macd, empty_metadata)
        
        # Should be empty DataFrame with correct columns
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0
        assert list(df.columns) == ['macd', 'signal', 'histogram']
    
    def test_mismatched_array_lengths_error(self, sample_metadata):
        """Test error handling for mismatched array lengths"""
        converter = IndicatorResultConverter()
        
        # Create MACD result with mismatched lengths
        bad_macd = {
            'macd': np.random.randn(100),
            'signal': np.random.randn(50),  # Different length
            'histogram': np.random.randn(100)
        }
        
        with pytest.raises((ValueError, AssertionError)):
            converter.macd_to_dataframe(bad_macd, sample_metadata)
    
    def test_metadata_length_mismatch_error(self, sample_metadata):
        """Test error when metadata length doesn't match array length"""
        converter = IndicatorResultConverter()
        
        # Create result with different length than metadata
        short_atr = np.random.randn(50)  # Metadata has 100 timestamps
        
        with pytest.raises((ValueError, AssertionError)):
            converter.atr_to_dataframe(short_atr, sample_metadata)
    
    def test_integration_with_gpu_converter(self, macd_result, sample_metadata):
        """Test integration with existing GPUArrayConverter"""
        converter = IndicatorResultConverter()
        
        # Convert MACD to DataFrame using our converter
        macd_df = converter.macd_to_dataframe(macd_result, sample_metadata)
        
        # Convert back to arrays using GPUArrayConverter
        arrays, metadata = GPUArrayConverter.to_arrays(macd_df)
        
        # Should round-trip correctly
        reconstructed_df = GPUArrayConverter.from_arrays(arrays, metadata)
        
        pd.testing.assert_frame_equal(macd_df, reconstructed_df)
    
    def test_column_ordering_consistency(self, macd_result, sample_metadata):
        """Test that column ordering is consistent"""
        converter = IndicatorResultConverter()
        
        # Create multiple DataFrames
        df1 = converter.macd_to_dataframe(macd_result, sample_metadata)
        df2 = converter.macd_to_dataframe(macd_result, sample_metadata)
        
        # Column order should be consistent
        assert list(df1.columns) == list(df2.columns)
        assert list(df1.columns) == ['macd', 'signal', 'histogram']
    
    def test_dtype_preservation(self, sample_metadata):
        """Test that array dtypes are preserved in DataFrame"""
        converter = IndicatorResultConverter()
        
        # Create arrays with specific dtypes
        arrays = {
            'float32_col': np.array([1.0, 2.0, 3.0], dtype=np.float32),
            'float64_col': np.array([1.0, 2.0, 3.0], dtype=np.float64),
            'int32_col': np.array([1, 2, 3], dtype=np.int32)
        }
        
        # Create appropriate metadata
        short_metadata = DataFrameMetadata(
            index=sample_metadata.index[:3],
            columns=['test'],
            dtypes={'test': 'float64'}
        )
        
        df = converter.arrays_to_dataframe(arrays, short_metadata)
        
        # Dtypes should be preserved (or compatible)
        assert df['float32_col'].dtype == np.float32
        assert df['float64_col'].dtype == np.float64
        assert df['int32_col'].dtype == np.int32