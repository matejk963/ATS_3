"""
Test suite for ATRRiskCalculator

Following TDD principles - write tests first to define expected behavior.
"""

import pytest
import numpy as np
import pandas as pd
from typing import Union

# Import the ArrayBackend for compatibility testing
from src.feature_engineering.array_backend import ArrayBackend

# This import will fail until we implement ATRRiskCalculator - that's expected in TDD
try:
    from src.feature_engineering.atr_risk_calculator import ATRRiskCalculator
    ATR_RISK_CALCULATOR_AVAILABLE = True
except ImportError:
    ATR_RISK_CALCULATOR_AVAILABLE = False


class TestATRRiskCalculatorBehavior:
    """Test expected behavior before implementation"""
    
    def test_stop_loss_distance_calculation(self):
        """Test that stop loss distance = ATR × stop_loss_ratio"""
        # This test defines the expected behavior
        # Implementation should follow: stop_loss_distance = atr * stop_loss_ratio
        
        # Test data
        atr_values = np.array([2.0, 2.5, 3.0, 1.5])
        stop_loss_ratio = 0.5
        expected_distances = np.array([1.0, 1.25, 1.5, 0.75])
        
        # This will fail until ATRRiskCalculator is implemented
        # calculator = ATRRiskCalculator(ArrayBackend())
        # result = calculator.compute_stop_loss_distance(atr_values, stop_loss_ratio)
        # np.testing.assert_array_almost_equal(result, expected_distances)
        
        # For now, just verify our expected calculation is correct
        manual_calculation = atr_values * stop_loss_ratio
        np.testing.assert_array_almost_equal(manual_calculation, expected_distances)
    
    def test_take_profit_distance_calculation(self):
        """Test that take profit distance = ATR × stop_loss_ratio × sl_tp_ratio"""
        
        # Test data
        atr_values = np.array([2.0, 2.5, 3.0, 1.5])
        stop_loss_ratio = 0.5
        sl_tp_ratio = 1.5
        expected_distances = np.array([1.5, 1.875, 2.25, 1.125])
        
        # Expected behavior: take_profit_distance = atr * stop_loss_ratio * sl_tp_ratio
        manual_calculation = atr_values * stop_loss_ratio * sl_tp_ratio
        np.testing.assert_array_almost_equal(manual_calculation, expected_distances)
    
    def test_risk_distances_together(self):
        """Test computing both distances together for efficiency"""
        
        # Test data
        atr_values = np.array([2.0, 3.0])
        stop_loss_ratio = 0.6
        sl_tp_ratio = 2.0
        
        expected_stop_loss = atr_values * stop_loss_ratio  # [1.2, 1.8]
        expected_take_profit = atr_values * stop_loss_ratio * sl_tp_ratio  # [2.4, 3.6]
        
        # Verify expected calculations
        np.testing.assert_array_almost_equal(expected_stop_loss, [1.2, 1.8])
        np.testing.assert_array_almost_equal(expected_take_profit, [2.4, 3.6])
    
    def test_risk_levels_long_position(self):
        """Test actual price levels for long positions"""
        
        # Test data
        entry_price = np.array([100.0, 200.0])
        atr_values = np.array([2.0, 4.0])
        stop_loss_ratio = 0.5
        sl_tp_ratio = 1.5
        
        # For long positions:
        # stop_loss_price = entry_price - (atr * stop_loss_ratio)
        # take_profit_price = entry_price + (atr * stop_loss_ratio * sl_tp_ratio)
        
        expected_stop_loss_levels = np.array([99.0, 198.0])  # 100-1.0, 200-2.0
        expected_take_profit_levels = np.array([101.5, 203.0])  # 100+1.5, 200+3.0
        
        # Verify calculations
        stop_loss_distance = atr_values * stop_loss_ratio
        take_profit_distance = atr_values * stop_loss_ratio * sl_tp_ratio
        
        calculated_stop_loss = entry_price - stop_loss_distance
        calculated_take_profit = entry_price + take_profit_distance
        
        np.testing.assert_array_almost_equal(calculated_stop_loss, expected_stop_loss_levels)
        np.testing.assert_array_almost_equal(calculated_take_profit, expected_take_profit_levels)
    
    def test_risk_levels_short_position(self):
        """Test actual price levels for short positions"""
        
        # Test data
        entry_price = np.array([100.0, 200.0])
        atr_values = np.array([2.0, 4.0])
        stop_loss_ratio = 0.5
        sl_tp_ratio = 1.5
        
        # For short positions:
        # stop_loss_price = entry_price + (atr * stop_loss_ratio)
        # take_profit_price = entry_price - (atr * stop_loss_ratio * sl_tp_ratio)
        
        expected_stop_loss_levels = np.array([101.0, 202.0])  # 100+1.0, 200+2.0
        expected_take_profit_levels = np.array([98.5, 197.0])  # 100-1.5, 200-3.0
        
        # Verify calculations
        stop_loss_distance = atr_values * stop_loss_ratio
        take_profit_distance = atr_values * stop_loss_ratio * sl_tp_ratio
        
        calculated_stop_loss = entry_price + stop_loss_distance
        calculated_take_profit = entry_price - take_profit_distance
        
        np.testing.assert_array_almost_equal(calculated_stop_loss, expected_stop_loss_levels)
        np.testing.assert_array_almost_equal(calculated_take_profit, expected_take_profit_levels)


class TestATRRiskCalculatorValidation:
    """Test validation and edge cases"""
    
    def test_positive_distances_requirement(self):
        """Test that all distance values should be positive"""
        
        # Positive ATR should always produce positive distances
        atr_values = np.array([1.0, 2.0, 3.0])
        stop_loss_ratio = 0.5
        sl_tp_ratio = 1.5
        
        stop_loss_distances = atr_values * stop_loss_ratio
        take_profit_distances = atr_values * stop_loss_ratio * sl_tp_ratio
        
        assert np.all(stop_loss_distances > 0)
        assert np.all(take_profit_distances > 0)
    
    def test_take_profit_greater_than_stop_loss(self):
        """Test that take profit distance >= stop loss distance when sl_tp_ratio >= 1.0"""
        
        atr_values = np.array([1.0, 2.0, 3.0])
        stop_loss_ratio = 0.5
        sl_tp_ratio = 1.5  # >= 1.0
        
        stop_loss_distances = atr_values * stop_loss_ratio
        take_profit_distances = atr_values * stop_loss_ratio * sl_tp_ratio
        
        assert np.all(take_profit_distances >= stop_loss_distances)
    
    def test_nan_atr_handling(self):
        """Test graceful handling of NaN ATR values"""
        
        atr_values = np.array([1.0, np.nan, 2.0])
        stop_loss_ratio = 0.5
        
        stop_loss_distances = atr_values * stop_loss_ratio
        
        # Should preserve NaN positions
        assert np.isnan(stop_loss_distances[1])
        assert stop_loss_distances[0] == 0.5
        assert stop_loss_distances[2] == 1.0
    
    def test_ratio_proportionality(self):
        """Test that distances are proportional to ATR"""
        
        atr_values = np.array([2.0, 4.0, 6.0])
        stop_loss_ratio = 0.5
        
        stop_loss_distances = atr_values * stop_loss_ratio
        ratios = stop_loss_distances / atr_values
        
        # All ratios should equal stop_loss_ratio
        np.testing.assert_array_almost_equal(ratios, [0.5, 0.5, 0.5])


class TestATRRiskCalculatorDocumentedExamples:
    """Test examples from the documentation"""
    
    def test_documentation_example_1(self):
        """Test example: ATR = 2.5, Stop Loss Ratio = 0.5 → Stop Loss Distance = 1.25"""
        
        atr = 2.5
        stop_loss_ratio = 0.5
        expected_distance = 1.25
        
        calculated_distance = atr * stop_loss_ratio
        assert calculated_distance == expected_distance
    
    def test_documentation_example_2(self):
        """Test example: ATR = 2.5, Stop Loss Ratio = 0.5, SL/TP Ratio = 1.5 → Take Profit Distance = 1.875"""
        
        atr = 2.5
        stop_loss_ratio = 0.5
        sl_tp_ratio = 1.5
        expected_distance = 1.875
        
        calculated_distance = atr * stop_loss_ratio * sl_tp_ratio
        assert calculated_distance == expected_distance
    
    def test_documentation_trading_example(self):
        """Test trading example from documentation"""
        
        # For a trade entry at price 100.0 with ATR = 2.0, stop_loss = 0.5, sl_tp_ratio = 1.5:
        entry_price = 100.0
        atr_value = 2.0
        stop_loss_ratio = 0.5
        sl_tp_ratio = 1.5
        
        stop_loss_distance = atr_value * stop_loss_ratio  # Expected: 1.0
        take_profit_distance = atr_value * stop_loss_ratio * sl_tp_ratio  # Expected: 1.5
        
        # Actual trade levels for long position
        stop_loss_price = entry_price - stop_loss_distance  # Expected: 99.0
        take_profit_price = entry_price + take_profit_distance  # Expected: 101.5
        
        assert stop_loss_distance == 1.0
        assert take_profit_distance == 1.5
        assert stop_loss_price == 99.0
        assert take_profit_price == 101.5


class TestATRRiskCalculatorParameterRanges:
    """Test with parameter ranges from documentation"""
    
    def test_stop_loss_value_ranges(self):
        """Test with STOP_LOSS_VALUES = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]"""
        
        stop_loss_values = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
        atr = 2.0
        
        for stop_loss_ratio in stop_loss_values:
            distance = atr * stop_loss_ratio
            assert 0.6 <= distance <= 1.6  # For ATR=2.0
            assert distance > 0
    
    def test_sl_tp_ratio_ranges(self):
        """Test with STOP_LOSS_TO_TAKE_PROFIT_RATIOS = [1.0, 1.2, 1.5, 1.8, 2.0, 2.2]"""
        
        sl_tp_ratios = [1.0, 1.2, 1.5, 1.8, 2.0, 2.2]
        atr = 2.0
        stop_loss_ratio = 0.5
        
        stop_loss_distance = atr * stop_loss_ratio  # 1.0
        
        for sl_tp_ratio in sl_tp_ratios:
            take_profit_distance = stop_loss_distance * sl_tp_ratio
            assert take_profit_distance >= stop_loss_distance
            assert take_profit_distance == atr * stop_loss_ratio * sl_tp_ratio


@pytest.mark.skipif(not ATR_RISK_CALCULATOR_AVAILABLE, reason="ATRRiskCalculator not implemented yet")
class TestATRRiskCalculatorImplementation:
    """Test actual ATRRiskCalculator implementation - these will fail until implemented"""
    
    def setup_method(self):
        """Setup calculator for each test"""
        try:
            self.backend = ArrayBackend(backend='cupy')  # Use CuPy backend
            self.calculator = ATRRiskCalculator(self.backend)
            self.gpu_available = True
        except (ImportError, RuntimeError) as e:
            pytest.skip(f"GPU not available for testing: {e}")
            self.gpu_available = False
    
    def test_calculator_initialization(self):
        """Test that calculator initializes with ArrayBackend"""
        assert self.calculator is not None
        assert hasattr(self.calculator, 'backend')
    
    def test_compute_stop_loss_distance_method(self):
        """Test compute_stop_loss_distance method"""
        atr_values = np.array([2.0, 2.5, 3.0, 1.5])
        stop_loss_ratio = 0.5
        expected_distances = np.array([1.0, 1.25, 1.5, 0.75])
        
        result = self.calculator.compute_stop_loss_distance(atr_values, stop_loss_ratio)
        result_cpu = self.backend.to_cpu(result)
        np.testing.assert_array_almost_equal(result_cpu, expected_distances)
    
    def test_compute_take_profit_distance_method(self):
        """Test compute_take_profit_distance method"""
        atr_values = np.array([2.0, 2.5, 3.0, 1.5])
        stop_loss_ratio = 0.5
        sl_tp_ratio = 1.5
        expected_distances = np.array([1.5, 1.875, 2.25, 1.125])
        
        result = self.calculator.compute_take_profit_distance(atr_values, stop_loss_ratio, sl_tp_ratio)
        result_cpu = self.backend.to_cpu(result)
        np.testing.assert_array_almost_equal(result_cpu, expected_distances)
    
    def test_compute_risk_distances_method(self):
        """Test compute_risk_distances method returns both distances"""
        atr_values = np.array([2.0, 3.0])
        stop_loss_ratio = 0.6
        sl_tp_ratio = 2.0
        
        expected_stop_loss = np.array([1.2, 1.8])
        expected_take_profit = np.array([2.4, 3.6])
        
        stop_loss_result, take_profit_result = self.calculator.compute_risk_distances(
            atr_values, stop_loss_ratio, sl_tp_ratio
        )
        
        stop_loss_cpu = self.backend.to_cpu(stop_loss_result)
        take_profit_cpu = self.backend.to_cpu(take_profit_result)
        np.testing.assert_array_almost_equal(stop_loss_cpu, expected_stop_loss)
        np.testing.assert_array_almost_equal(take_profit_cpu, expected_take_profit)
    
    def test_compute_risk_levels_long_position(self):
        """Test compute_risk_levels method for long positions"""
        entry_price = np.array([100.0, 200.0])
        atr_values = np.array([2.0, 4.0])
        stop_loss_ratio = 0.5
        sl_tp_ratio = 1.5
        
        expected_stop_loss_levels = np.array([99.0, 198.0])
        expected_take_profit_levels = np.array([101.5, 203.0])
        
        stop_loss_result, take_profit_result = self.calculator.compute_risk_levels(
            entry_price, atr_values, stop_loss_ratio, sl_tp_ratio, position_type='long'
        )
        
        stop_loss_cpu = self.backend.to_cpu(stop_loss_result)
        take_profit_cpu = self.backend.to_cpu(take_profit_result)
        np.testing.assert_array_almost_equal(stop_loss_cpu, expected_stop_loss_levels)
        np.testing.assert_array_almost_equal(take_profit_cpu, expected_take_profit_levels)
    
    def test_compute_risk_levels_short_position(self):
        """Test compute_risk_levels method for short positions"""
        entry_price = np.array([100.0, 200.0])
        atr_values = np.array([2.0, 4.0])
        stop_loss_ratio = 0.5
        sl_tp_ratio = 1.5
        
        expected_stop_loss_levels = np.array([101.0, 202.0])
        expected_take_profit_levels = np.array([98.5, 197.0])
        
        stop_loss_result, take_profit_result = self.calculator.compute_risk_levels(
            entry_price, atr_values, stop_loss_ratio, sl_tp_ratio, position_type='short'
        )
        
        stop_loss_cpu = self.backend.to_cpu(stop_loss_result)
        take_profit_cpu = self.backend.to_cpu(take_profit_result)
        np.testing.assert_array_almost_equal(stop_loss_cpu, expected_stop_loss_levels)
        np.testing.assert_array_almost_equal(take_profit_cpu, expected_take_profit_levels)
    
    def test_backend_compatibility(self):
        """Test that calculator works with GPU backend"""
        atr_values = np.array([2.0, 3.0])
        stop_loss_ratio = 0.5
        
        # Test with CuPy backend 
        result = self.calculator.compute_stop_loss_distance(atr_values, stop_loss_ratio)
        
        # Convert back to CPU for comparison
        result_cpu = self.backend.to_cpu(result)
        expected = np.array([1.0, 1.5])
        np.testing.assert_array_almost_equal(result_cpu, expected)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])