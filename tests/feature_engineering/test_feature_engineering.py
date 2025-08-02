"""
Test suite for Phase 4 Feature Engineering Pipeline
EXACT ATS_2 Legacy Implementation Tests

Test Priority: RED-GREEN-REFACTOR TDD Cycle
1. Write failing tests (RED)
2. Implement minimal code (GREEN) 
3. Refactor for optimization (REFACTOR)
"""

import pytest
import numpy as np
import cupy as cp
from unittest.mock import Mock

# Import the modules we're about to implement
from src.feature_engineering.gpu_feature_calculator import GPUFeatureCalculator
from src.feature_engineering.normalization_engine import NormalizationEngine
from src.feature_engineering.position_calculator import PositionCalculator


class TestGPUFeatureCalculator:
    """Test GPU Feature Calculator - EXACT ATS_2 Legacy Implementation"""
    
    def setup_method(self):
        """Setup test data matching ATS_2 structure"""
        self.calculator = GPUFeatureCalculator()
        
        # Test data matching Phase 3 outputs
        self.sample_indicators = {
            'macd_line': cp.array([0.1, 0.2, -0.1, 0.3, -0.2], dtype=cp.float32),
            'macd_histogram': cp.array([0.05, 0.1, -0.05, 0.15, -0.1], dtype=cp.float32),
            'atr': cp.array([2.0, 2.5, 1.5, 3.0, 1.8], dtype=cp.float32),
            'swing_highs': cp.array([100.5, 101.0, 99.8, 102.0, 100.2], dtype=cp.float32),
            'swing_lows': cp.array([98.0, 99.5, 97.5, 100.0, 98.8], dtype=cp.float32)
        }
        
        self.current_prices = cp.array([99.0, 100.2, 98.5, 101.5, 99.5], dtype=cp.float32)
    
    def test_compute_all_features_returns_correct_structure(self):
        """Test that compute_all_features returns all required legacy features"""
        # This should FAIL initially (RED phase)
        result = self.calculator.compute_all_features(self.sample_indicators, self.current_prices)
        
        # EXACT legacy feature names from complete_memory_solution.py
        expected_keys = ['macd_norm', 'macd_hist_norm', 'price_range', 'price_position']
        
        for key in expected_keys:
            assert key in result, f"Missing legacy feature: {key}"
            assert isinstance(result[key], cp.ndarray), f"Feature {key} should be cupy array"
            assert result[key].dtype == cp.float32, f"Feature {key} should be float32"
    
    def test_legacy_macd_normalization_exact_formula(self):
        """Test EXACT legacy formula: macd_norm = macd / atr"""
        # Expected result from EXACT legacy formula
        macd = self.sample_indicators['macd_line']
        atr = self.sample_indicators['atr']
        expected_macd_norm = macd / atr  # EXACT: temp['macd_norm'] = temp['macd'] / temp['atr']
        
        result = self.calculator.compute_all_features(self.sample_indicators, self.current_prices)
        
        cp.testing.assert_allclose(result['macd_norm'], expected_macd_norm, rtol=1e-6)
    
    def test_legacy_histogram_normalization_exact_formula(self):
        """Test EXACT legacy formula: macd_hist_norm = hist / atr"""
        # Expected result from EXACT legacy formula  
        hist = self.sample_indicators['macd_histogram']
        atr = self.sample_indicators['atr']
        expected_hist_norm = hist / atr  # EXACT: temp['macd_hist_norm'] = temp['hist'] / temp['atr']
        
        result = self.calculator.compute_all_features(self.sample_indicators, self.current_prices)
        
        cp.testing.assert_allclose(result['macd_hist_norm'], expected_hist_norm, rtol=1e-6)
    
    def test_legacy_price_range_exact_formula(self):
        """Test EXACT legacy formula: price_range = swing_high - swing_low"""
        # Expected result from EXACT legacy formula
        swing_highs = self.sample_indicators['swing_highs']
        swing_lows = self.sample_indicators['swing_lows']
        expected_price_range = swing_highs - swing_lows  # EXACT: temp['price_range'] = temp['swing_high'] - temp['swing_low']
        
        result = self.calculator.compute_all_features(self.sample_indicators, self.current_prices)
        
        cp.testing.assert_allclose(result['price_range'], expected_price_range, rtol=1e-6)
    
    def test_legacy_price_position_exact_formula(self):
        """Test EXACT legacy formula: price_position = (price - swing_low) / price_range"""
        # Expected result from EXACT legacy formula (two-step process)
        swing_highs = self.sample_indicators['swing_highs']
        swing_lows = self.sample_indicators['swing_lows']
        price_range = swing_highs - swing_lows  # Step 1
        expected_price_position = (self.current_prices - swing_lows) / price_range  # Step 2
        
        result = self.calculator.compute_all_features(self.sample_indicators, self.current_prices)
        
        cp.testing.assert_allclose(result['price_position'], expected_price_position, rtol=1e-6)
    
    def test_price_position_range_validation(self):
        """Test that price_position stays in [0,1] range as expected"""
        result = self.calculator.compute_all_features(self.sample_indicators, self.current_prices)
        
        # Price position should be in [0,1] for valid swing data
        assert cp.all(result['price_position'] >= 0.0), "Price position should be >= 0"
        assert cp.all(result['price_position'] <= 1.0), "Price position should be <= 1"
    
    def test_no_nan_values_in_features(self):
        """Test that no NaN values are produced (legacy requirement)"""
        result = self.calculator.compute_all_features(self.sample_indicators, self.current_prices)
        
        for feature_name, feature_array in result.items():
            assert not cp.any(cp.isnan(feature_array)), f"Feature {feature_name} contains NaN values"


class TestNormalizationEngine:
    """Test Normalization Engine - EXACT ATS_2 Legacy Formulas"""
    
    def setup_method(self):
        self.engine = NormalizationEngine()
        
        # Test data
        self.macd_values = cp.array([0.1, 0.2, -0.1, 0.3, -0.2], dtype=cp.float32)
        self.histogram_values = cp.array([0.05, 0.1, -0.05, 0.15, -0.1], dtype=cp.float32)
        self.atr_values = cp.array([2.0, 2.5, 1.5, 3.0, 1.8], dtype=cp.float32)
    
    def test_legacy_normalize_macd_by_atr_exact_formula(self):
        """Test EXACT legacy: macd_norm = macd / atr"""
        expected = self.macd_values / self.atr_values
        
        result = self.engine.legacy_normalize_macd_by_atr(self.macd_values, self.atr_values)
        
        cp.testing.assert_allclose(result, expected, rtol=1e-6)
        assert result.dtype == cp.float32
    
    def test_legacy_normalize_histogram_by_atr_exact_formula(self):
        """Test EXACT legacy: macd_hist_norm = hist / atr"""
        expected = self.histogram_values / self.atr_values
        
        result = self.engine.legacy_normalize_histogram_by_atr(self.histogram_values, self.atr_values)
        
        cp.testing.assert_allclose(result, expected, rtol=1e-6)
        assert result.dtype == cp.float32
    
    def test_zero_atr_handling(self):
        """Test handling of zero ATR values (edge case)"""
        atr_with_zero = cp.array([2.0, 0.0, 1.5], dtype=cp.float32)
        macd_values = cp.array([0.1, 0.2, -0.1], dtype=cp.float32)
        
        # Should handle division by zero gracefully
        result = self.engine.legacy_normalize_macd_by_atr(macd_values, atr_with_zero)
        
        # Check that we don't get NaN or inf in result
        assert cp.isfinite(result[0])  # Normal case
        assert cp.isfinite(result[2])  # Normal case
        # Index 1 behavior depends on implementation (could be inf, large number, or handled)


class TestPositionCalculator:
    """Test Position Calculator - EXACT ATS_2 Legacy Implementation"""
    
    def setup_method(self):
        self.calculator = PositionCalculator()
        
        # Test data
        self.current_prices = cp.array([99.0, 100.2, 98.5, 101.5, 99.5], dtype=cp.float32)
        self.swing_highs = cp.array([100.5, 101.0, 99.8, 102.0, 100.2], dtype=cp.float32)
        self.swing_lows = cp.array([98.0, 99.5, 97.5, 100.0, 98.8], dtype=cp.float32)
    
    def test_calculate_legacy_position_exact_formula(self):
        """Test EXACT legacy two-step process"""
        # Step 1: price_range = swing_high - swing_low
        expected_price_range = self.swing_highs - self.swing_lows
        
        # Step 2: price_position = (price - swing_low) / price_range
        expected_price_position = (self.current_prices - self.swing_lows) / expected_price_range
        
        price_range, price_position = self.calculator.calculate_legacy_position(
            self.current_prices, self.swing_highs, self.swing_lows
        )
        
        cp.testing.assert_allclose(price_range, expected_price_range, rtol=1e-6)
        cp.testing.assert_allclose(price_position, expected_price_position, rtol=1e-6)
    
    def test_position_range_bounds(self):
        """Test that position stays in [0,1] for valid data"""
        price_range, price_position = self.calculator.calculate_legacy_position(
            self.current_prices, self.swing_highs, self.swing_lows
        )
        
        # For valid swing data where current_price is between swing_low and swing_high
        assert cp.all(price_position >= 0.0), "Price position should be >= 0"
        assert cp.all(price_position <= 1.0), "Price position should be <= 1"
    
    def test_edge_case_price_at_swing_low(self):
        """Test when current price equals swing low (position = 0)"""
        # Set current prices to swing lows
        prices_at_low = self.swing_lows.copy()
        
        price_range, price_position = self.calculator.calculate_legacy_position(
            prices_at_low, self.swing_highs, self.swing_lows
        )
        
        # Position should be 0 when price = swing_low
        expected_position = cp.zeros_like(prices_at_low)
        cp.testing.assert_allclose(price_position, expected_position, rtol=1e-6)
    
    def test_edge_case_price_at_swing_high(self):
        """Test when current price equals swing high (position = 1)"""
        # Set current prices to swing highs
        prices_at_high = self.swing_highs.copy()
        
        price_range, price_position = self.calculator.calculate_legacy_position(
            prices_at_high, self.swing_highs, self.swing_lows
        )
        
        # Position should be 1 when price = swing_high
        expected_position = cp.ones_like(prices_at_high)
        cp.testing.assert_allclose(price_position, expected_position, rtol=1e-6)


if __name__ == "__main__":
    # Run tests to verify they FAIL (RED phase)
    pytest.main([__file__, "-v"])