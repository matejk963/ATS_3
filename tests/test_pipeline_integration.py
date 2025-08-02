"""
Tests for pipeline integration with legacy swing detector.

This test suite validates that the UnifiedTechnicalIndicatorsPipeline works
correctly with the new LegacySwingPointDetector integration.
"""

import pytest
import pandas as pd
import numpy as np
import sys
import os

# Add source to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline


class TestPipelineIntegration:
    """Test suite for pipeline integration with legacy swing detector"""
    
    @pytest.fixture
    def sample_ohlc_data(self):
        """Generate sample OHLC data for testing"""
        np.random.seed(42)
        n_points = 50  # Smaller dataset for faster testing
        
        # Generate realistic price data
        base_price = 100.0
        prices = [base_price]
        
        for i in range(n_points - 1):
            change = np.random.normal(0, 0.5)
            if i % 15 == 0:  # Trend every 15 points
                change += np.random.choice([-1.5, 1.5])
            prices.append(max(50, prices[-1] + change))
        
        # Create OHLC from prices
        data = []
        for i, close in enumerate(prices):
            high = close + abs(np.random.normal(0, 0.2))
            low = close - abs(np.random.normal(0, 0.2))
            open_price = prices[i-1] if i > 0 else close
            
            data.append({
                'open': open_price,
                'high': high,
                'low': low,
                'close': close,
                'volume': 1000 + np.random.randint(-100, 100)  # Add volume
            })
        
        return pd.DataFrame(data)
    
    @pytest.fixture
    def pipeline(self):
        """Initialize GPU pipeline for testing"""
        try:
            return UnifiedTechnicalIndicatorsPipeline()
        except (ImportError, RuntimeError) as e:
            pytest.skip(f"GPU pipeline not available: {e}")
    
    def test_swing_points_indicator_computation(self, pipeline, sample_ohlc_data):
        """Test that swing points are computed correctly"""
        result = pipeline.compute_indicators(
            data=sample_ohlc_data,
            indicators=['swing_points']
        )
        
        # Check that swing columns exist
        assert 'swing_highs' in result.columns
        assert 'swing_lows' in result.columns
        
        # Check that results have correct length
        assert len(result) == len(sample_ohlc_data)
        
        # Check that swing values are continuous price values (not booleans)
        assert result['swing_highs'].dtype in ['float32', 'float64']
        assert result['swing_lows'].dtype in ['float32', 'float64']
        
        # Check that we have some non-NaN values
        assert result['swing_highs'].notna().any()
        assert result['swing_lows'].notna().any()
    
    def test_all_indicators_computation(self, pipeline, sample_ohlc_data):
        """Test that all indicators work together"""
        result = pipeline.compute_all_indicators(
            data=sample_ohlc_data,
            swing_lookback=20  # Should be ignored
        )
        
        # Check that all expected columns exist
        expected_columns = [
            'open', 'high', 'low', 'close',  # OHLC
            'macd_line', 'macd_signal', 'macd_histogram',  # MACD
            'atr',  # ATR
            'swing_highs', 'swing_lows'  # Swing points
        ]
        
        for col in expected_columns:
            assert col in result.columns, f"Missing column: {col}"
        
        # Check data types
        assert result['swing_highs'].dtype in ['float32', 'float64']
        assert result['swing_lows'].dtype in ['float32', 'float64']
    
    def test_feature_engineering_integration(self, pipeline, sample_ohlc_data):
        """Test that feature engineering works with legacy swing detector"""
        result = pipeline.compute_all_indicators_and_features(
            data=sample_ohlc_data
        )
        
        # Check that feature engineering columns are added
        feature_columns = [
            'macd_norm', 'macd_hist_norm', 'price_position'
        ]
        
        for col in feature_columns:
            assert col in result.columns, f"Missing feature column: {col}"
        
        # Check that swing values are properly processed
        assert 'swing_highs' in result.columns
        assert 'swing_lows' in result.columns
        
        # Swing values should be continuous (no NaN after forward fill in features)
        # Note: The original swing detection may have NaN, but after feature processing
        # they should be forward filled
        swing_highs = result['swing_highs'].values
        swing_lows = result['swing_lows'].values
        
        # Check that we have meaningful swing data
        assert not np.isnan(swing_highs).all(), "All swing highs are NaN"
        assert not np.isnan(swing_lows).all(), "All swing lows are NaN"
    
    def test_bias_classification_integration(self, pipeline, sample_ohlc_data):
        """Test that bias classification works with legacy swing detector"""
        result = pipeline.compute_all_indicators_features_and_bias(
            data=sample_ohlc_data
        )
        
        # Check that bias columns are added
        bias_columns = [
            'macd_line_class_numeric', 'macd_histogram_class_numeric',
            'bias_numeric', 'bias_classification'
        ]
        
        for col in bias_columns:
            assert col in result.columns, f"Missing bias column: {col}"
        
        # Check that swing data is still present and processed
        assert 'swing_highs' in result.columns
        assert 'swing_lows' in result.columns
        assert 'price_position' in result.columns
    
    def test_position_signal_integration(self, pipeline, sample_ohlc_data):
        """Test that position signal generation works with legacy swing detector"""
        result = pipeline.compute_all_indicators_features_bias_and_positions(
            data=sample_ohlc_data
        )
        
        # Check that position signal column is added
        assert 'position_signal' in result.columns
        
        # Check that all previous columns are still present
        expected_columns = [
            'swing_highs', 'swing_lows', 'price_position',
            'bias_numeric', 'bias_classification', 'position_signal'
        ]
        
        for col in expected_columns:
            assert col in result.columns, f"Missing column in full pipeline: {col}"
        
        # Check position signal values are valid
        position_signals = result['position_signal'].values
        unique_signals = np.unique(position_signals[~np.isnan(position_signals)])
        
        # Position signals should be in {-1, 0, 1}
        for signal in unique_signals:
            assert signal in [-1, 0, 1], f"Invalid position signal: {signal}"
    
    def test_lookback_parameter_ignored(self, pipeline, sample_ohlc_data):
        """Test that swing_lookback parameter is properly ignored"""
        # Test with different lookback values - results should be identical
        result1 = pipeline.compute_indicators(
            data=sample_ohlc_data,
            indicators=['swing_points'],
            swing_lookback=5
        )
        
        result2 = pipeline.compute_indicators(
            data=sample_ohlc_data,
            indicators=['swing_points'],
            swing_lookback=50
        )
        
        # Results should be identical since lookback is ignored
        np.testing.assert_array_equal(
            result1['swing_highs'].values,
            result2['swing_highs'].values,
            err_msg="Different lookback values produced different results"
        )
        
        np.testing.assert_array_equal(
            result1['swing_lows'].values,
            result2['swing_lows'].values,
            err_msg="Different lookback values produced different results"
        )
    
    def test_continuous_price_values_format(self, pipeline, sample_ohlc_data):
        """Test that swing detector returns continuous price values not boolean masks"""
        result = pipeline.compute_indicators(
            data=sample_ohlc_data,
            indicators=['swing_points']
        )
        
        # Check data types are numeric, not boolean
        assert result['swing_highs'].dtype in ['float32', 'float64']
        assert result['swing_lows'].dtype in ['float32', 'float64']
        
        # Check that we have actual price values (should be in reasonable range)
        swing_highs = result['swing_highs'].dropna()
        swing_lows = result['swing_lows'].dropna()
        
        if len(swing_highs) > 0:
            # Swing highs should be within reasonable range of the actual high prices
            assert swing_highs.min() >= sample_ohlc_data['high'].min() * 0.9
            assert swing_highs.max() <= sample_ohlc_data['high'].max() * 1.1
        
        if len(swing_lows) > 0:
            # Swing lows should be within reasonable range of the actual low prices
            assert swing_lows.min() >= sample_ohlc_data['low'].min() * 0.9
            assert swing_lows.max() <= sample_ohlc_data['low'].max() * 1.1


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])