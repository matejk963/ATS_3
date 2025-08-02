"""
Unit tests for Phase 5: GPU-accelerated bias classification system

Tests GPU-accelerated bias classification that transforms normalized MACD indicators
into actionable market sentiment classifications using the Decision Logic Matrix.

Following TDD: These tests are written FIRST to define expected behavior.
"""

import pytest
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional, Dict, Tuple
from unittest.mock import MagicMock, patch

# Tests will import from modules that don't exist yet - this is TDD
# We define the expected interface through tests first
from src.feature_engineering.bias_classifier import (
    ThresholdConfig,
    GPUBiasClassifier,
    create_gpu_bias_classifier,
    validate_gpu_bias_output,
    get_bias_distribution_stats_gpu
)
from src.feature_engineering.array_backend import ArrayBackend


class TestThresholdConfig:
    """Test threshold configuration with exact legacy validation logic"""

    def test_default_threshold_values(self):
        """Test default threshold values match legacy configuration"""
        config = ThresholdConfig()
        
        assert config.macd_line_lower == -0.1
        assert config.macd_line_upper == 0.1
        assert config.macd_histogram_lower == -0.05
        assert config.macd_histogram_upper == 0.05

    def test_threshold_validation_valid_config(self):
        """Test validation passes for valid threshold configuration"""
        config = ThresholdConfig(
            macd_line_lower=-0.2,
            macd_line_upper=0.2,
            macd_histogram_lower=-0.1,
            macd_histogram_upper=0.1
        )
        
        assert config.validate() is True

    def test_threshold_validation_invalid_macd_line(self):
        """Test validation fails when macd_line_lower >= macd_line_upper"""
        with pytest.raises(ValueError, match="macd_line_lower .* must be less than macd_line_upper"):
            ThresholdConfig(macd_line_lower=0.1, macd_line_upper=0.1)
        
        with pytest.raises(ValueError, match="macd_line_lower .* must be less than macd_line_upper"):
            ThresholdConfig(macd_line_lower=0.2, macd_line_upper=0.1)

    def test_threshold_validation_invalid_histogram(self):
        """Test validation fails when histogram thresholds are invalid"""
        with pytest.raises(ValueError, match="macd_histogram_lower .* must be less than macd_histogram_upper"):
            ThresholdConfig(macd_histogram_lower=0.1, macd_histogram_upper=0.1)

    def test_threshold_validation_zero_thresholds(self):
        """Test validation handles zero thresholds correctly"""
        config = ThresholdConfig(
            macd_line_lower=-0.1,
            macd_line_upper=0.0,
            macd_histogram_lower=-0.05,
            macd_histogram_upper=0.0
        )
        assert config.validate() is True


class TestGPUBiasClassifier:
    """Test GPU-accelerated bias classifier with decision matrix logic"""

    @pytest.fixture
    def mock_array_backend(self):
        """Mock ArrayBackend for testing"""
        backend = MagicMock(spec=ArrayBackend)
        backend.xp = np  # Use numpy as mock for testing
        return backend

    @pytest.fixture
    def classifier(self, mock_array_backend):
        """Create classifier instance for testing"""
        return GPUBiasClassifier(mock_array_backend)

    def test_classifier_initialization(self, mock_array_backend):
        """Test classifier initializes with correct configuration"""
        classifier = GPUBiasClassifier(mock_array_backend)
        
        assert classifier.array_backend == mock_array_backend
        assert isinstance(classifier.thresholds, ThresholdConfig)

    def test_classifier_custom_thresholds(self, mock_array_backend):
        """Test classifier accepts custom threshold configuration"""
        custom_thresholds = ThresholdConfig(
            macd_line_lower=-0.2,
            macd_line_upper=0.2,
            macd_histogram_lower=-0.1,
            macd_histogram_upper=0.1
        )
        
        classifier = GPUBiasClassifier(mock_array_backend, custom_thresholds)
        assert classifier.thresholds == custom_thresholds

    def test_classify_components_gpu_bearish_cases(self, classifier):
        """Test component classification for bearish cases"""
        # Test data that should classify as bearish
        macd_norm = np.array([-0.15, -0.2, -0.05])  # Below lower threshold
        macd_hist_norm = np.array([-0.1, -0.06, -0.02])  # Below lower threshold
        
        macd_class, hist_class = classifier.classify_components_gpu(macd_norm, macd_hist_norm)
        
        # First two should be bearish (-1), third should be neutral (0)
        expected_macd = np.array([-1, -1, 0])
        expected_hist = np.array([-1, -1, 0])
        
        np.testing.assert_array_equal(macd_class, expected_macd)
        np.testing.assert_array_equal(hist_class, expected_hist)

    def test_classify_components_gpu_bullish_cases(self, classifier):
        """Test component classification for bullish cases"""
        macd_norm = np.array([0.15, 0.2, 0.05])  # Above upper threshold
        macd_hist_norm = np.array([0.1, 0.06, 0.02])  # Above upper threshold
        
        macd_class, hist_class = classifier.classify_components_gpu(macd_norm, macd_hist_norm)
        
        # First two should be bullish (1), third should be neutral (0)
        expected_macd = np.array([1, 1, 0])
        expected_hist = np.array([1, 1, 0])
        
        np.testing.assert_array_equal(macd_class, expected_macd)
        np.testing.assert_array_equal(hist_class, expected_hist)

    def test_apply_decision_matrix_gpu_all_combinations(self, classifier):
        """Test decision matrix logic for all 9 combinations"""
        # Test all 9 combinations from the Decision Logic Matrix
        macd_classes = np.array([-1, -1, -1, 0, 0, 0, 1, 1, 1])
        hist_classes = np.array([-1, 0, 1, -1, 0, 1, -1, 0, 1])
        
        expected_bias = np.array([-2, -1, 0, -1, 0, 1, 0, 1, 2])
        
        result = classifier.apply_decision_matrix_gpu(macd_classes, hist_classes)
        
        np.testing.assert_array_equal(result, expected_bias)

    def test_compute_bias_classification_integration(self, classifier):
        """Test full bias classification integration"""
        # Test data representing different market conditions
        macd_norm = np.array([-0.15, -0.05, 0.05, 0.15, 0.0])
        macd_hist_norm = np.array([-0.1, 0.0, 0.0, 0.1, -0.06])
        
        bias_result = classifier.compute_bias_classification(macd_norm, macd_hist_norm)
        
        # Expected: Strong Bearish, Neutral, Neutral, Strong Bullish, Bearish
        expected_bias = np.array([-2, 0, 0, 2, -1])
        
        np.testing.assert_array_equal(bias_result, expected_bias)

    def test_handle_nan_values(self, classifier):
        """Test proper handling of NaN values in input data"""
        macd_norm = np.array([np.nan, -0.15, 0.15])
        macd_hist_norm = np.array([-0.1, np.nan, 0.1])
        
        bias_result = classifier.compute_bias_classification(macd_norm, macd_hist_norm)
        
        # NaN converts to 0 (neutral), then decision matrix applies:
        # Case 0: MACD=0 (neutral), Hist=-1 (bearish) -> Bias=-1 (bearish)
        # Case 1: MACD=-1 (bearish), Hist=0 (neutral) -> Bias=-1 (bearish)  
        # Case 2: MACD=1 (bullish), Hist=1 (bullish) -> Bias=2 (strong bullish)
        expected_bias = np.array([-1, -1, 2])
        
        np.testing.assert_array_equal(bias_result, expected_bias)

    def test_extreme_values_handling(self, classifier):
        """Test handling of extreme values beyond normal ranges"""
        macd_norm = np.array([-5.0, 5.0, -10.0, 10.0])
        macd_hist_norm = np.array([-2.0, 2.0, -5.0, 5.0])
        
        bias_result = classifier.compute_bias_classification(macd_norm, macd_hist_norm)
        
        # All should be classified as Strong Bearish or Strong Bullish
        expected_bias = np.array([-2, 2, -2, 2])
        
        np.testing.assert_array_equal(bias_result, expected_bias)


class TestBiasClassificationUtilities:
    """Test utility functions for bias classification"""

    @pytest.fixture
    def mock_array_backend(self):
        """Mock ArrayBackend for testing"""
        backend = MagicMock(spec=ArrayBackend)
        backend.xp = np
        return backend

    def test_create_gpu_bias_classifier_default(self, mock_array_backend):
        """Test factory function creates classifier with default config"""
        classifier = create_gpu_bias_classifier(mock_array_backend)
        
        assert isinstance(classifier, GPUBiasClassifier)
        assert classifier.array_backend == mock_array_backend

    def test_create_gpu_bias_classifier_custom_thresholds(self, mock_array_backend):
        """Test factory function accepts custom threshold parameters"""
        classifier = create_gpu_bias_classifier(
            mock_array_backend,
            macd_line_lower=-0.2,
            macd_line_upper=0.2
        )
        
        assert classifier.thresholds.macd_line_lower == -0.2
        assert classifier.thresholds.macd_line_upper == 0.2

    def test_validate_gpu_bias_output_valid(self):
        """Test validation passes for valid bias output"""
        bias_arrays = {
            'macd_line_class_numeric': np.array([-1, 0, 1]),
            'macd_histogram_class_numeric': np.array([-1, 0, 1]),
            'bias_numeric': np.array([-2, 0, 2]),
            'bias_classification': np.array(['Strong Bearish', 'Neutral', 'Strong Bullish'])
        }
        
        assert validate_gpu_bias_output(bias_arrays) is True

    def test_validate_gpu_bias_output_invalid_range(self):
        """Test validation fails for invalid bias ranges"""
        bias_arrays = {
            'bias_numeric': np.array([-3, 0, 3])  # Invalid range
        }
        
        assert validate_gpu_bias_output(bias_arrays) is False

    def test_get_bias_distribution_stats_gpu(self):
        """Test bias distribution statistics computation"""
        bias_numeric = np.array([-2, -1, 0, 1, 2, -1, 0, 1])
        
        stats = get_bias_distribution_stats_gpu(bias_numeric)
        
        expected_stats = {
            'strong_bearish_pct': 12.5,  # 1/8
            'bearish_pct': 25.0,         # 2/8
            'neutral_pct': 25.0,         # 2/8
            'bullish_pct': 25.0,         # 2/8
            'strong_bullish_pct': 12.5,  # 1/8
            'total_count': 8
        }
        
        assert stats == expected_stats


class TestErrorHandling:
    """Test error handling and edge cases"""

    @pytest.fixture
    def mock_array_backend(self):
        backend = MagicMock(spec=ArrayBackend)
        backend.xp = np
        return backend

    def test_invalid_input_shapes(self, mock_array_backend):
        """Test error handling for mismatched input array shapes"""
        classifier = GPUBiasClassifier(mock_array_backend)
        
        macd_norm = np.array([1, 2, 3])
        macd_hist_norm = np.array([1, 2])  # Different length
        
        with pytest.raises(ValueError, match="Input arrays must have the same shape"):
            classifier.compute_bias_classification(macd_norm, macd_hist_norm)

    def test_empty_arrays(self, mock_array_backend):
        """Test handling of empty input arrays"""
        classifier = GPUBiasClassifier(mock_array_backend)
        
        macd_norm = np.array([])
        macd_hist_norm = np.array([])
        
        result = classifier.compute_bias_classification(macd_norm, macd_hist_norm)
        
        assert len(result) == 0
        assert isinstance(result, np.ndarray)

    def test_single_value_arrays(self, mock_array_backend):
        """Test handling of single-value arrays"""
        classifier = GPUBiasClassifier(mock_array_backend)
        
        macd_norm = np.array([0.15])
        macd_hist_norm = np.array([0.1])
        
        result = classifier.compute_bias_classification(macd_norm, macd_hist_norm)
        
        expected = np.array([2])  # Strong Bullish
        np.testing.assert_array_equal(result, expected)