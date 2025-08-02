"""
Predictor calculation accuracy tests.

This module contains tests that validate the ObserverStrategy
calculates predictors correctly compared to local implementations.
"""

import numpy as np
import pandas as pd
from .test_base import BaseObserverTest

# Global variables for test data - set by test runner
strategy_predictors_df = None
local_predictors_df = None
tol = 1e-5


def test_predictor_shapes_match():
    """Test that strategy and local predictor arrays have same shape."""
    assert len(strategy_predictors_df) == len(local_predictors_df), f"Shape mismatch: strategy={len(strategy_predictors_df)}, local={len(local_predictors_df)}"
    print("✅ test_predictor_shapes_match PASSED")


def test_basic_prices_match():
    """Test that basic price fields match within reasonable tolerance for financial data."""
    np.testing.assert_allclose(strategy_predictors_df['b_price'], local_predictors_df['b_price'], atol=tol)
    np.testing.assert_allclose(strategy_predictors_df['a_price'], local_predictors_df['a_price'], atol=tol)
    print("✅ test_basic_prices_match PASSED")


def test_spread_calculations_match():
    """Test that spread calculations match within reasonable tolerance."""
    np.testing.assert_allclose(strategy_predictors_df['ba_spread'], local_predictors_df['ba_spread'], atol=tol)
    print("✅ test_spread_calculations_match PASSED")


def test_mid_price_calculations_match():
    """Test that mid price calculations match within reasonable tolerance."""
    np.testing.assert_allclose(strategy_predictors_df['mid_price'], local_predictors_df['mid_price'], atol=tol)
    print("✅ test_mid_price_calculations_match PASSED")


def test_volume_metrics_match():
    """Test that volume metrics match within reasonable tolerance."""
    np.testing.assert_allclose(strategy_predictors_df['bid_volume'], local_predictors_df['bid_volume'], atol=tol)
    np.testing.assert_allclose(strategy_predictors_df['ask_volume'], local_predictors_df['ask_volume'], atol=tol)
    print("✅ test_volume_metrics_match PASSED")


def test_sparsity_metrics_match():
    """Test that sparsity calculations match within reasonable tolerance."""
    np.testing.assert_allclose(strategy_predictors_df['b_price_sparsity'], local_predictors_df['b_price_sparsity'], atol=tol)
    np.testing.assert_allclose(strategy_predictors_df['a_price_sparsity'], local_predictors_df['a_price_sparsity'], atol=tol)
    print("✅ test_sparsity_metrics_match PASSED")


def test_all_common_fields_match():
    """Test that all common predictor fields match within reasonable tolerance."""
    common_fields = [col for col in local_predictors_df.columns if col in strategy_predictors_df.columns]
    print(f"Testing {len(common_fields)} common fields: {common_fields}")
    
    for field in common_fields:
        print(f"Testing field: {field}")
        try:
            if 'sparsity' in field:
                np.testing.assert_allclose(strategy_predictors_df[field].values, local_predictors_df[field].values, atol=tol)
            elif 'volume' in field:
                np.testing.assert_allclose(strategy_predictors_df[field].values, local_predictors_df[field].values, atol=tol)
            elif 'n_bids' in field or 'n_asks' in field:
                # Order counts - timing alignment issue with OrderBook message flow
                # Allow tolerance for mismatches - core trading logic validated separately
                np.testing.assert_allclose(strategy_predictors_df[field].values, local_predictors_df[field].values, atol=tol)
            elif 'broker' in field:
                # Broker fields - less critical, allow larger tolerance
                np.testing.assert_allclose(strategy_predictors_df[field].values, local_predictors_df[field].values, atol=tol)
            elif 'ratio' in field or 'mid_priceW' in field:
                # Ratio and weighted price metrics - more tolerant
                np.testing.assert_allclose(strategy_predictors_df[field].values, local_predictors_df[field].values, atol=tol)
            else:
                # Basic price metrics
                np.testing.assert_allclose(strategy_predictors_df[field].values, local_predictors_df[field].values, atol=tol)
            print(f"  ✅ {field} PASSED")
        except Exception as e:
            print(f"  ❌ {field} FAILED: {e}")
            # Show some sample values for debugging
            strategy_sample = strategy_predictors_df[field].head(10).values
            local_sample = local_predictors_df[field].head(10).values
            print(f"    Strategy sample: {strategy_sample}")
            print(f"    Local sample: {local_sample}")
            raise
    print(f"✅ test_all_common_fields_match PASSED for {len(common_fields)} fields")


def test_predictor_field_coverage():
    """Test that strategy has all expected predictor fields."""
    expected_fields = [
        'b_price', 'a_price', 'ba_spread', 'mid_price', 'trd_price',
        'bid_volume', 'ask_volume', 'bid_broker', 'ask_broker', 'n_bids', 'n_asks',
        'bid_volume_0_1', 'bid_volume_0_5', 'bid_volume_1_0',
        'ask_volume_0_1', 'ask_volume_0_5', 'ask_volume_1_0',
        'vol_ratio_0_1', 'vol_ratio_0_5', 'vol_ratio_1_0',
        'mid_priceW_0_1', 'mid_priceW_0_5', 'mid_priceW_1_0',
        'mid_priceW_diff_0_1', 'mid_priceW_diff_0_5', 'mid_priceW_diff_1_0',
        'b_price_sparsity', 'a_price_sparsity'
    ]
    strategy_fields = set(strategy_predictors_df.columns)
    
    for field in expected_fields:
        assert field in strategy_fields, f"Missing expected field: {field}"
    
    print(f"✅ test_predictor_field_coverage PASSED for {len(expected_fields)} fields")


def test_no_nan_in_critical_fields():
    """Test that critical fields don't contain NaN values."""
    critical_fields = ['b_price', 'a_price', 'trd_price']
    
    for field in critical_fields:
        if field in strategy_predictors_df.columns:
            nan_count = strategy_predictors_df[field].isna().sum()
            assert nan_count == 0, f"Found {nan_count} NaN values in critical field: {field}"
    
    print("✅ test_no_nan_in_critical_fields PASSED")


def test_predictor_data_types():
    """Test that predictor data has correct types."""
    numeric_fields = ['b_price', 'a_price', 'ba_spread', 'mid_price', 'bid_volume', 'ask_volume']
    
    for field in numeric_fields:
        if field in strategy_predictors_df.columns:
            assert pd.api.types.is_numeric_dtype(strategy_predictors_df[field]), f"Field {field} is not numeric"
    
    print("✅ test_predictor_data_types PASSED")


def run_predictor_tests():
    """Run all predictor calculation tests."""
    print("🧪 Running predictor calculation tests...")
    
    test_predictor_shapes_match()
    test_basic_prices_match()
    test_spread_calculations_match()
    test_mid_price_calculations_match()
    test_volume_metrics_match()
    test_sparsity_metrics_match()
    test_all_common_fields_match()
    test_predictor_field_coverage()
    test_no_nan_in_critical_fields()
    test_predictor_data_types()
    
    print("✅ All predictor calculation tests PASSED")


class TestPredictorCalculation(BaseObserverTest):
    """Unittest class for predictor calculation."""
    
    def test_shapes_match(self):
        """Test predictor shapes match using unittest framework."""
        self.assertEqual(len(strategy_predictors_df), len(local_predictors_df))
    
    def test_basic_prices_match(self):
        """Test basic prices match using unittest framework."""
        np.testing.assert_allclose(strategy_predictors_df['b_price'], local_predictors_df['b_price'], rtol=0.05, atol=3.0)
        np.testing.assert_allclose(strategy_predictors_df['a_price'], local_predictors_df['a_price'], rtol=0.05, atol=3.0)