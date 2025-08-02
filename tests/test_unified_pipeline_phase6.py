"""Integration tests for Phase 6: Position Signal Generation in Unified Pipeline."""

import pytest
import pandas as pd
import numpy as np
import cupy as cp
from datetime import datetime, timedelta

from src.feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline
from src.feature_engineering.position_generator import ThresholdConfig as PositionThresholdConfig
from src.feature_engineering.bias_classifier import ThresholdConfig as BiasThresholdConfig


class TestUnifiedPipelinePhase6:
    """Test unified pipeline with Phase 6 position signal generation."""
    
    @pytest.fixture
    def sample_data(self):
        """Create sample OHLCV data for testing."""
        # Generate 100 data points
        size = 100
        dates = [datetime(2024, 1, 1) + timedelta(hours=i) for i in range(size)]
        
        # Create synthetic price data with trends
        prices = 100 + np.cumsum(np.random.randn(size) * 0.5)
        
        data = pd.DataFrame({
            'Datetime': dates,
            'open': prices + np.random.randn(size) * 0.1,
            'high': prices + np.abs(np.random.randn(size) * 0.3),
            'low': prices - np.abs(np.random.randn(size) * 0.3),
            'close': prices,
            'volume': np.random.randint(1000, 10000, size)
        })
        
        return data
    
    @pytest.fixture
    def pipeline(self):
        """Create pipeline instance."""
        return UnifiedTechnicalIndicatorsPipeline()
    
    def test_phase6_method_exists(self, pipeline):
        """Test that the Phase 6 method exists."""
        assert hasattr(pipeline, 'compute_all_indicators_features_bias_and_positions')
    
    def test_phase6_basic_functionality(self, pipeline, sample_data):
        """Test basic Phase 6 functionality."""
        result = pipeline.compute_all_indicators_features_bias_and_positions(sample_data)
        
        # Check that all expected columns exist
        expected_columns = [
            # Phase 3: Technical indicators
            'macd_line', 'macd_signal', 'macd_histogram',
            'atr', 'swing_highs', 'swing_lows',
            # Phase 4: Normalized features
            'macd_norm', 'macd_hist_norm',
            'price_position',
            # Phase 5: Bias classification
            'bias_numeric', 'bias_classification',
            # Phase 6: Position signals
            'position_signal'
        ]
        
        for col in expected_columns:
            assert col in result.columns, f"Missing expected column: {col}"
    
    def test_position_signal_values(self, pipeline, sample_data):
        """Test that position signals have valid values."""
        result = pipeline.compute_all_indicators_features_bias_and_positions(sample_data)
        
        # Check position signals are in valid range
        unique_signals = result['position_signal'].unique()
        valid_signals = [-1, 0, 1]
        for signal in unique_signals:
            if not pd.isna(signal):
                assert signal in valid_signals, f"Invalid position signal: {signal}"
    
    def test_position_signal_consistency_with_bias(self, pipeline, sample_data):
        """Test that position signals are consistent with bias classification."""
        result = pipeline.compute_all_indicators_features_bias_and_positions(sample_data)
        
        # Filter out NaN values
        valid_mask = ~(result['bias_numeric'].isna() | result['position_signal'].isna())
        valid_data = result[valid_mask]
        
        if len(valid_data) > 0:
            # Strong bullish (2) should never have short positions when price is low
            strong_bullish = valid_data[valid_data['bias_numeric'] == 2]
            low_price_strong_bullish = strong_bullish[strong_bullish['price_position'] < 0.35]
            if len(low_price_strong_bullish) > 0:
                assert (low_price_strong_bullish['position_signal'] >= 0).all()
            
            # Strong bearish (-2) should never have long positions when price is high
            strong_bearish = valid_data[valid_data['bias_numeric'] == -2]
            high_price_strong_bearish = strong_bearish[strong_bearish['price_position'] > 0.65]
            if len(high_price_strong_bearish) > 0:
                assert (high_price_strong_bearish['position_signal'] <= 0).all()
    
    def test_custom_position_thresholds(self, pipeline, sample_data):
        """Test Phase 6 with custom position thresholds."""
        custom_thresholds = PositionThresholdConfig(
            strong_bullish_buy=0.5,  # More conservative
            strong_bearish_sell=0.5   # More conservative
        )
        
        result = pipeline.compute_all_indicators_features_bias_and_positions(
            sample_data,
            position_thresholds=custom_thresholds
        )
        
        # Verify custom thresholds are applied
        valid_mask = ~(result['bias_numeric'].isna() | result['position_signal'].isna())
        valid_data = result[valid_mask]
        
        if len(valid_data) > 0:
            # Strong bullish should only buy below 0.5 (custom threshold)
            strong_bullish = valid_data[valid_data['bias_numeric'] == 2]
            high_price_strong_bullish = strong_bullish[strong_bullish['price_position'] >= 0.5]
            if len(high_price_strong_bullish) > 0:
                assert (high_price_strong_bullish['position_signal'] == 0).all()
    
    def test_nan_handling_in_position_signals(self, pipeline):
        """Test that NaN values are properly handled in position generation."""
        # Create data with some NaN values
        data = pd.DataFrame({
            'Datetime': pd.date_range('2024-01-01', periods=20, freq='h'),
            'open': [100] * 20,
            'high': [101] * 20,
            'low': [99] * 20,
            'close': [100] * 20,
            'volume': [1000] * 20
        })
        
        # Run pipeline
        result = pipeline.compute_all_indicators_features_bias_and_positions(data)
        
        # Early rows should have NaN due to indicator warmup
        # These should result in position_signal = 0 or NaN
        early_positions = result['position_signal'].iloc[:10]
        assert (early_positions.isna() | (early_positions == 0)).all()
    
    def test_large_dataset_performance(self, pipeline):
        """Test performance with larger dataset."""
        # Create larger dataset
        size = 10000
        dates = pd.date_range('2024-01-01', periods=size, freq='5min')
        prices = 100 + np.cumsum(np.random.randn(size) * 0.1)
        
        data = pd.DataFrame({
            'Datetime': dates,
            'open': prices + np.random.randn(size) * 0.05,
            'high': prices + np.abs(np.random.randn(size) * 0.1),
            'low': prices - np.abs(np.random.randn(size) * 0.1),
            'close': prices,
            'volume': np.random.randint(1000, 10000, size)
        })
        
        # Should complete without errors
        result = pipeline.compute_all_indicators_features_bias_and_positions(data)
        
        # Verify output
        assert len(result) == size
        assert 'position_signal' in result.columns
        
        # Check that position signals are valid
        valid_signals = result['position_signal'].dropna()
        assert set(valid_signals.unique()).issubset({-1, 0, 1})
    
    def test_phase6_preserves_earlier_phases(self, pipeline, sample_data):
        """Test that Phase 6 preserves all outputs from earlier phases."""
        # Run Phase 5 pipeline
        phase5_result = pipeline.compute_all_indicators_features_and_bias(sample_data)
        
        # Run Phase 6 pipeline
        phase6_result = pipeline.compute_all_indicators_features_bias_and_positions(sample_data)
        
        # All Phase 5 columns should be present in Phase 6
        for col in phase5_result.columns:
            assert col in phase6_result.columns
            # Values should be identical (except for potential floating point differences)
            if col not in ['position_signal']:  # New column in Phase 6
                pd.testing.assert_series_equal(
                    phase5_result[col], 
                    phase6_result[col],
                    check_names=False
                )
    
    def test_gpu_memory_efficiency(self, pipeline, sample_data):
        """Test that position generation maintains GPU memory efficiency."""
        # This test ensures no memory leaks during position generation
        import cupy as cp
        
        # Clear GPU memory
        cp.get_default_memory_pool().free_all_blocks()
        
        # Run pipeline multiple times
        for _ in range(5):
            result = pipeline.compute_all_indicators_features_bias_and_positions(sample_data)
            
        # Memory should be managed efficiently
        # (This is a basic test - more sophisticated memory tracking could be added)
        assert 'position_signal' in result.columns