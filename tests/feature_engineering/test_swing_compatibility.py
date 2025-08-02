"""
Test suite for comparing new implementation with original legacy system.

This module tests the compatibility between our corrected legacy implementation
and the original ATS_2 system to ensure identical results.
"""

import pytest
import pandas as pd
import numpy as np
import sys
import os

# Add the ATS_2 source path for legacy code import
sys.path.append('/mnt/c/Users/krajcovic/Documents/GitHub/ATS_3/source_repos/ATS_2/EnergyTrading/Python/Utilities')

try:
    from predictors_tools import detect_swing_points as legacy_detect_swing_points
    LEGACY_AVAILABLE = True
except ImportError:
    LEGACY_AVAILABLE = False

from src.feature_engineering.legacy_swing_detector import LegacySwingDetector


class TestSwingCompatibility:
    """Test compatibility between legacy and new implementations."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.detector = LegacySwingDetector()
        
    @pytest.mark.skipif(not LEGACY_AVAILABLE, reason="Legacy ATS_2 code not available")
    def test_identical_results_with_corrected_legacy_simple_data(self):
        """Test that our implementation matches CORRECTED legacy exactly."""
        # Simple test data with OHLC (required by corrected algorithm)
        data = pd.DataFrame({
            'high': [10.0, 12.0, 11.0, 15.0, 14.0, 18.0, 17.0, 20.0],
            'low': [9.0, 10.0, 8.0, 13.0, 12.0, 16.0, 15.0, 18.0],
            'open': [9.5, 11.0, 10.5, 14.0, 13.5, 17.0, 16.5, 19.0],
            'close': [9.8, 11.5, 10.2, 14.5, 13.8, 17.5, 16.8, 19.5]
        })
        
        # Get results from both implementations
        legacy_result = legacy_detect_swing_points(data)
        new_result = self.detector.detect_swing_points(data)
        
        # Compare results - they should be identical
        pd.testing.assert_frame_equal(
            legacy_result, new_result,
            check_names=False,
            check_dtype=False
        )
        
    @pytest.mark.skipif(not LEGACY_AVAILABLE, reason="Legacy ATS_2 code not available")  
    def test_identical_results_with_legacy_complex_data(self):
        """Test with more complex market-like data."""
        # More complex market-like data with various patterns
        np.random.seed(42)  # For reproducible results
        
        # Generate realistic OHLC data
        prices = np.cumsum(np.random.randn(50) * 0.5) + 100
        highs = prices + np.abs(np.random.randn(50) * 0.3)
        lows = prices - np.abs(np.random.randn(50) * 0.3)
        
        data = pd.DataFrame({
            'high': highs,
            'low': lows
        })
        
        # Get results from both implementations  
        legacy_result = legacy_detect_swing_points(data)
        new_result = self.detector.detect_swing_points(data)
        
        # Compare results - they should be identical
        pd.testing.assert_frame_equal(
            legacy_result, new_result,
            check_names=False,
            check_dtype=False
        )
        
    @pytest.mark.skipif(not LEGACY_AVAILABLE, reason="Legacy ATS_2 code not available")
    def test_identical_results_edge_cases(self):
        """Test edge cases with legacy system."""
        
        # Test 1: Flat periods (no new extremes)
        flat_data = pd.DataFrame({
            'high': [10.0, 10.0, 10.0, 10.0],
            'low': [9.0, 9.0, 9.0, 9.0]
        })
        
        legacy_result = legacy_detect_swing_points(flat_data)
        new_result = self.detector.detect_swing_points(flat_data)
        
        pd.testing.assert_frame_equal(
            legacy_result, new_result,
            check_names=False,
            check_dtype=False
        )
        
        # Test 2: Single candle
        single_data = pd.DataFrame({
            'high': [10.0],
            'low': [9.0]
        })
        
        legacy_result = legacy_detect_swing_points(single_data)
        new_result = self.detector.detect_swing_points(single_data)
        
        pd.testing.assert_frame_equal(
            legacy_result, new_result,
            check_names=False,
            check_dtype=False
        )
        
    def test_algorithm_replicates_legacy_behavior(self):
        """Test that our implementation replicates exact legacy behavior (including bug)."""
        # This test data shows the legacy retroactive placement behavior
        
        data = pd.DataFrame({
            'high': [10.0, 9.0, 8.0, 15.0],  # New high at index 3
            'low': [8.0, 7.0, 6.0, 12.0]    # Minimum low at index 2
        })
        
        result = self.detector.detect_swing_points(data)
        
        # Legacy behavior places swing_low at index 3 (where new high occurs)
        # not at index 2 (where the actual minimum is) - this is the legacy bug
        
        # Before forward fill, the raw swing points should be:
        # Index 0: swing_high=10.0, swing_low=8.0 (initialization)
        # Index 1: no swing points (new low at 7.0)
        # Index 2: no swing points (but actual minimum is here)
        # Index 3: swing_high=15.0, swing_low=6.0 (retroactive but placed at wrong index)
        
        # After forward fill (legacy behavior):
        expected_high = [10.0, 10.0, 10.0, 15.0]
        expected_low = [8.0, 7.0, 6.0, 6.0]  # Note: sequence of new lows, then gap fill at new high
        
        pd.testing.assert_series_equal(
            result['swing_high'],
            pd.Series(expected_high, name='swing_high'),
            check_names=False
        )
        pd.testing.assert_series_equal(
            result['swing_low'],
            pd.Series(expected_low, name='swing_low'),
            check_names=False
        )
        
    def test_maintains_legacy_interface(self):
        """Test that interface matches legacy exactly."""
        data = pd.DataFrame({
            'high': [10.0, 12.0, 11.0],
            'low': [8.0, 9.0, 7.0]
        })
        
        result = self.detector.detect_swing_points(data)
        
        # Should return DataFrame with exactly these columns
        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ['swing_high', 'swing_low']
        
        # Should be forward-filled (no NaN values)
        assert not result.isnull().any().any()
        
        # Should maintain index from original data
        assert len(result) == len(data)