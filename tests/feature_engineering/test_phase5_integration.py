"""
Integration tests for Phase 5: Bias Classification Pipeline Integration

Tests the integration of GPU-accelerated bias classification with Phase 4 features
and the unified pipeline system.

Following TDD: These tests are written FIRST to define expected integration behavior.
"""

import pytest
import numpy as np
import pandas as pd
import time
from typing import Dict, Optional
from unittest.mock import MagicMock, patch

# TDD: Import from modules that will be implemented
from src.feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline
from src.feature_engineering.bias_classifier import ThresholdConfig, GPUBiasClassifier
from src.feature_engineering.array_backend import ArrayBackend


class TestPhase5PipelineIntegration:
    """Test bias classification integration with unified pipeline"""

    @pytest.fixture
    def sample_ohlcv_data(self):
        """Generate sample OHLCV data for testing"""
        np.random.seed(42)
        n_points = 1000
        
        dates = pd.date_range('2023-01-01', periods=n_points, freq='15min')
        
        # Generate realistic price movements
        price_base = 100.0
        price_changes = np.random.normal(0, 0.01, n_points).cumsum()
        close_prices = price_base * (1 + price_changes)
        
        # Generate OHLC from close prices with realistic spreads
        high_spread = np.random.uniform(0.001, 0.005, n_points)
        low_spread = np.random.uniform(0.001, 0.005, n_points)
        open_spread = np.random.uniform(-0.002, 0.002, n_points)
        
        data = pd.DataFrame({
            'timestamp': dates,
            'open': close_prices * (1 + open_spread),
            'high': close_prices * (1 + high_spread),
            'low': close_prices * (1 - low_spread),
            'close': close_prices,
            'volume': np.random.randint(1000, 10000, n_points)
        })
        
        return data

    @pytest.fixture
    def pipeline(self):
        """Create pipeline instance for testing"""
        # This will fail initially - part of TDD
        return UnifiedTechnicalIndicatorsPipeline()

    def test_pipeline_has_bias_classification_method(self, pipeline):
        """Test that pipeline has the new bias classification method"""
        # Test that the new method exists
        assert hasattr(pipeline, 'compute_all_indicators_features_and_bias')
        
        # Test method signature
        import inspect
        sig = inspect.signature(pipeline.compute_all_indicators_features_and_bias)
        expected_params = ['data', 'bias_thresholds', 'candle_granularity', 
                          'macd_params', 'atr_period', 'swing_lookback']
        
        actual_params = list(sig.parameters.keys())
        for param in expected_params:
            assert param in actual_params or param == 'self'

    def test_end_to_end_bias_classification_pipeline(self, pipeline, sample_ohlcv_data):
        """Test complete pipeline from OHLCV to bias classification"""
        # This is the main integration test - will fail initially
        result = pipeline.compute_all_indicators_features_and_bias(sample_ohlcv_data)
        
        # Verify all expected columns are present
        expected_columns = [
            # Phase 3: Technical indicators
            'macd_line', 'macd_histogram', 'macd_signal',
            'atr', 'swing_highs', 'swing_lows',
            
            # Phase 4: Engineered features (check actual column names)
            'macd_norm', 'macd_hist_norm',
            
            # Phase 5: Bias classification (NEW)
            'macd_line_class_numeric',
            'macd_histogram_class_numeric', 
            'bias_numeric',
            'bias_classification'
        ]
        
        for col in expected_columns:
            assert col in result.columns, f"Missing expected column: {col}"
        
        # Verify bias_numeric contains valid values (-2 to 2)
        bias_values = result['bias_numeric'].dropna()
        assert bias_values.min() >= -2
        assert bias_values.max() <= 2
        assert set(bias_values.unique()).issubset({-2, -1, 0, 1, 2})

    def test_bias_classification_with_custom_thresholds(self, pipeline, sample_ohlcv_data):
        """Test bias classification with custom threshold configuration"""
        custom_thresholds = ThresholdConfig(
            macd_line_lower=-0.2,
            macd_line_upper=0.2,
            macd_histogram_lower=-0.1,
            macd_histogram_upper=0.1
        )
        
        result = pipeline.compute_all_indicators_features_and_bias(
            sample_ohlcv_data,
            bias_thresholds=custom_thresholds
        )
        
        # Verify processing completed successfully
        assert 'bias_numeric' in result.columns
        assert not result['bias_numeric'].isna().all()

    def test_bias_classification_data_types(self, pipeline, sample_ohlcv_data):
        """Test that bias classification outputs have correct data types"""
        result = pipeline.compute_all_indicators_features_and_bias(sample_ohlcv_data)
        
        # Verify numeric columns are numeric
        assert pd.api.types.is_numeric_dtype(result['macd_line_class_numeric'])
        assert pd.api.types.is_numeric_dtype(result['macd_histogram_class_numeric'])
        assert pd.api.types.is_numeric_dtype(result['bias_numeric'])
        
        # Verify string column is string
        assert pd.api.types.is_string_dtype(result['bias_classification']) or \
               pd.api.types.is_object_dtype(result['bias_classification'])

    def test_bias_classification_consistency(self, pipeline, sample_ohlcv_data):
        """Test that bias classification results are consistent across runs"""
        result1 = pipeline.compute_all_indicators_features_and_bias(sample_ohlcv_data)
        result2 = pipeline.compute_all_indicators_features_and_bias(sample_ohlcv_data)
        
        # Results should be identical for same input
        pd.testing.assert_series_equal(
            result1['bias_numeric'], 
            result2['bias_numeric'],
            check_names=False
        )

    def test_phase4_to_phase5_data_flow(self, pipeline, sample_ohlcv_data):
        """Test data flow from Phase 4 features to Phase 5 bias classification"""
        # Get Phase 4 results
        phase4_result = pipeline.compute_all_indicators_and_features(sample_ohlcv_data)
        
        # Get Phase 5 results
        phase5_result = pipeline.compute_all_indicators_features_and_bias(sample_ohlcv_data)
        
        # Verify Phase 4 columns are preserved in Phase 5
        phase4_columns = ['macd_norm', 'macd_hist_norm']
        for col in phase4_columns:
            pd.testing.assert_series_equal(
                phase4_result[col],
                phase5_result[col],
                check_names=False
            )
        
        # Verify new Phase 5 columns exist
        phase5_new_columns = ['bias_numeric', 'bias_classification']
        for col in phase5_new_columns:
            assert col in phase5_result.columns
            assert col not in phase4_result.columns


class TestGPUPerformanceIntegration:
    """Test GPU performance requirements for Phase 5 integration"""

    @pytest.fixture
    def large_dataset(self):
        """Generate large dataset for performance testing"""
        np.random.seed(42)
        n_points = 10000  # Large enough for meaningful performance test
        
        dates = pd.date_range('2020-01-01', periods=n_points, freq='1min')
        
        price_base = 100.0
        price_changes = np.random.normal(0, 0.001, n_points).cumsum()
        close_prices = price_base * (1 + price_changes)
        
        data = pd.DataFrame({
            'timestamp': dates,
            'open': close_prices * (1 + np.random.uniform(-0.001, 0.001, n_points)),
            'high': close_prices * (1 + np.random.uniform(0.001, 0.005, n_points)),
            'low': close_prices * (1 - np.random.uniform(0.001, 0.005, n_points)),
            'close': close_prices,
            'volume': np.random.randint(1000, 10000, n_points)
        })
        
        return data

    @pytest.fixture
    def pipeline(self):
        """Create GPU-optimized pipeline for performance testing"""
        return UnifiedTechnicalIndicatorsPipeline()

    def test_bias_classification_performance_overhead(self, pipeline, large_dataset):
        """Test that Phase 5 adds <0.1s overhead to Phase 4 pipeline"""
        # Get Phase 4 result once
        phase4_result = pipeline.compute_all_indicators_and_features(large_dataset)
        
        # Measure only the bias classification step
        from src.feature_engineering.bias_classifier import GPUBiasClassifier
        bias_classifier = GPUBiasClassifier(pipeline.array_backend)
        
        # Extract required data
        macd_norm = pipeline.array_backend.asarray(phase4_result['macd_norm'].values)
        macd_hist_norm = pipeline.array_backend.asarray(phase4_result['macd_hist_norm'].values)
        
        # Measure pure bias classification time
        start_time = time.time()
        macd_class, hist_class = bias_classifier.classify_components_gpu(macd_norm, macd_hist_norm)
        bias_numeric = bias_classifier.compute_bias_classification(macd_norm, macd_hist_norm)
        bias_classification_time = time.time() - start_time
        
        print(f"Phase 4 dataset size: {len(large_dataset)} points")
        print(f"Pure bias classification time: {bias_classification_time:.3f}s")
        print(f"Bias classification rate: {len(large_dataset)/bias_classification_time:.1f} points/sec")
        
        # Verify bias classification is fast (<0.1s for 10k points)
        assert bias_classification_time < 0.1, f"Bias classification {bias_classification_time:.3f}s exceeds 0.1s requirement"
        
        # Verify results are valid
        assert len(bias_numeric) == len(large_dataset)
        # Check if it's a GPU array (CuPy) by checking for 'get' method or device attribute
        import cupy as cp
        assert isinstance(bias_numeric, cp.ndarray), "Should be CuPy GPU array"

    def test_gpu_memory_efficiency(self, pipeline, large_dataset):
        """Test that GPU memory usage remains efficient with bias classification"""
        # This test would require GPU monitoring
        # For now, verify that processing completes without memory errors
        try:
            result = pipeline.compute_all_indicators_features_and_bias(large_dataset)
            assert len(result) == len(large_dataset)
            assert 'bias_numeric' in result.columns
        except Exception as e:
            pytest.fail(f"GPU memory efficiency test failed: {e}")

    def test_large_dataset_scalability(self, pipeline):
        """Test bias classification handles very large datasets efficiently"""
        # Generate progressively larger datasets
        dataset_sizes = [1000, 5000, 10000]
        processing_times = []
        
        for size in dataset_sizes:
            # Generate dataset
            dates = pd.date_range('2020-01-01', periods=size, freq='1min')
            data = pd.DataFrame({
                'timestamp': dates,
                'open': 100 + np.random.randn(size) * 0.1,
                'high': 100 + np.random.randn(size) * 0.1 + 0.5,
                'low': 100 + np.random.randn(size) * 0.1 - 0.5,
                'close': 100 + np.random.randn(size) * 0.1,
                'volume': np.random.randint(1000, 10000, size)
            })
            
            # Measure processing time
            start_time = time.time()
            result = pipeline.compute_all_indicators_features_and_bias(data)
            processing_time = time.time() - start_time
            processing_times.append(processing_time)
            
            # Verify results
            assert len(result) == size
            assert 'bias_numeric' in result.columns
        
        # Verify linear or sub-linear scaling
        for i in range(1, len(processing_times)):
            size_ratio = dataset_sizes[i] / dataset_sizes[i-1]
            time_ratio = processing_times[i] / processing_times[i-1]
            
            # Time ratio should not exceed size ratio significantly (max 2x for overhead)
            assert time_ratio <= size_ratio * 2, \
                f"Poor scaling: {size_ratio}x data took {time_ratio}x time"


class TestErrorHandlingIntegration:
    """Test error handling in pipeline integration"""

    @pytest.fixture
    def pipeline(self):
        return UnifiedTechnicalIndicatorsPipeline()

    def test_invalid_input_data_handling(self, pipeline):
        """Test pipeline handles invalid input data gracefully"""
        # Empty DataFrame
        empty_data = pd.DataFrame()
        
        with pytest.raises(ValueError, match="Input data cannot be empty"):
            pipeline.compute_all_indicators_features_and_bias(empty_data)

    def test_missing_required_columns(self, pipeline):
        """Test pipeline handles missing required columns"""
        # Data missing required OHLCV columns
        incomplete_data = pd.DataFrame({
            'timestamp': pd.date_range('2023-01-01', periods=10, freq='1H'),
            'close': [100] * 10
            # Missing open, high, low, volume
        })
        
        with pytest.raises(ValueError, match="Missing required columns"):
            pipeline.compute_all_indicators_features_and_bias(incomplete_data)

    def test_invalid_threshold_configuration(self, pipeline):
        """Test pipeline handles invalid threshold configuration"""
        data = pd.DataFrame({
            'timestamp': pd.date_range('2023-01-01', periods=10, freq='1H'),
            'open': [100] * 10,
            'high': [102] * 10,
            'low': [98] * 10,
            'close': [101] * 10,
            'volume': [1000] * 10
        })
        
        # Invalid thresholds should raise error during ThresholdConfig creation
        with pytest.raises(ValueError, match="macd_line_lower .* must be less than macd_line_upper"):
            invalid_thresholds = ThresholdConfig(
                macd_line_lower=0.1,  # Should be negative
                macd_line_upper=0.05  # Should be > lower
            )

    def test_nan_handling_in_pipeline(self, pipeline):
        """Test pipeline handles NaN values appropriately"""
        data = pd.DataFrame({
            'timestamp': pd.date_range('2023-01-01', periods=10, freq='1H'),
            'open': [100, np.nan, 100, 100, 100, 100, 100, 100, 100, 100],
            'high': [102, 102, np.nan, 102, 102, 102, 102, 102, 102, 102],
            'low': [98, 98, 98, np.nan, 98, 98, 98, 98, 98, 98],
            'close': [101, 101, 101, 101, np.nan, 101, 101, 101, 101, 101],
            'volume': [1000] * 10
        })
        
        # Should not raise error, but handle NaN gracefully
        result = pipeline.compute_all_indicators_features_and_bias(data)
        
        # Verify result structure is maintained
        assert len(result) == 10
        assert 'bias_numeric' in result.columns