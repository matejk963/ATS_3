"""
Test suite for CORRECTED legacy swing point detection algorithm validation.

This module tests the corrected legacy swing point detector to ensure
it produces identical results to the CORRECTED ATS_2 system (lines 18-83).
"""

import pytest
import pandas as pd
import numpy as np
from src.feature_engineering.legacy_swing_detector import LegacySwingDetector


class TestLegacySwingValidation:
    """Test CORRECTED legacy swing point detection algorithm."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.detector = LegacySwingDetector()
        
    def test_corrected_algorithm_exact_match_simple_case(self):
        """Test CORRECTED algorithm with simple uptrend data."""
        # Simple uptrend with clear swing points
        data = pd.DataFrame({
            'high': [10.0, 12.0, 11.0, 15.0, 14.0, 18.0],
            'low': [9.0, 10.0, 8.0, 13.0, 12.0, 16.0],
            'open': [9.5, 11.0, 10.5, 14.0, 13.5, 17.0], 
            'close': [9.8, 11.5, 10.2, 14.5, 13.8, 17.5]
        })
        
        # Expected results based on CORRECTED algorithm behavior (from actual legacy run)
        expected_high = [10.0, 12.0, 12.0, 15.0, np.nan, 18.0]
        expected_low = [9.0, np.nan, 8.0, 8.0, np.nan, 12.0]
        
        result = self.detector.detect_swing_points(data)
        
        # Verify exact match with expected results
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
        
    def test_corrected_algorithm_retroactive_gap_filling(self):
        """Test the CORRECTED retroactive gap filling logic."""
        # Data designed to test gap filling between swing points
        data = pd.DataFrame({
            'high': [10.0, 9.0, 8.0, 15.0],  # New high at index 3
            'low': [8.0, 7.0, 6.0, 12.0],   # Minimum low at index 2
            'open': [9.0, 8.5, 7.5, 14.0],
            'close': [9.5, 8.0, 7.0, 14.5]
        })
        
        result = self.detector.detect_swing_points(data)
        
        # CORRECTED: When new high occurs at index 3, swing_low should be placed
        # at current index (3) with minimum value from gap, but state tracks actual index
        assert result.loc[3, 'swing_high'] == 15.0
        assert result.loc[3, 'swing_low'] == 6.0  # Minimum from gap period (placed at current idx)
        
    def test_corrected_algorithm_enhanced_state_management(self):
        """Test CORRECTED enhanced state management across iterations."""
        data = pd.DataFrame({
            'high': [10.0, 12.0, 8.0, 15.0, 7.0],
            'low': [8.0, 10.0, 6.0, 13.0, 5.0],
            'open': [9.0, 11.0, 7.0, 14.0, 6.0],
            'close': [9.5, 11.5, 7.5, 14.5, 6.5]
        })
        
        result = self.detector.detect_swing_points(data)
        
        # Verify enhanced state is properly maintained
        # The corrected algorithm uses last_min/max and last_min2/max2 tracking
        # First high: 10.0 -> 12.0 (new high at idx 1)
        # First low: 8.0 -> 6.0 (new low at idx 2) 
        # Second high: 12.0 -> 15.0 (new high at idx 3)
        # Second low: 6.0 -> 5.0 (new low at idx 4)
        
        assert not pd.isna(result.loc[1, 'swing_high'])  # New high
        assert not pd.isna(result.loc[2, 'swing_low'])   # New low
        assert not pd.isna(result.loc[3, 'swing_high'])  # New high  
        assert not pd.isna(result.loc[4, 'swing_low'])   # New low
        
    def test_corrected_algorithm_no_forward_fill(self):
        """Test that CORRECTED algorithm does NOT use forward fill."""
        data = pd.DataFrame({
            'high': [10.0, 12.0, 11.0],
            'low': [8.0, 9.0, 7.0],
            'open': [9.0, 11.0, 10.0],
            'close': [9.5, 11.5, 10.5]
        })
        
        result = self.detector.detect_swing_points(data)
        
        # CORRECTED: Result should contain NaN values (no forward fill)
        assert result.isnull().any().any(), "Corrected algorithm should NOT forward fill"
        
    def test_corrected_algorithm_initialization(self):
        """Test proper initialization of first candle in CORRECTED algorithm."""
        data = pd.DataFrame({
            'high': [10.0, 9.0, 11.0],
            'low': [8.0, 7.0, 9.0],
            'open': [9.0, 8.0, 10.0],
            'close': [9.5, 8.5, 10.5]
        })
        
        result = self.detector.detect_swing_points(data)
        
        # First candle should be initialized with both swing_high and swing_low
        # (this behavior is same in corrected algorithm)
        assert result.loc[0, 'swing_high'] == 10.0
        assert result.loc[0, 'swing_low'] == 8.0