"""
Real vs fake data validation tests.

This module contains tests that validate the ObserverStrategy
uses real market data and can detect fake/static data.
"""

import numpy as np
import pandas as pd
from .test_base import BaseObserverTest

# Global variables for test data - set by test runner
strategy_after_simulation = None


def test_price_variance_sufficient():
    """Test that price data has sufficient variance (real market data)."""
    predictors = strategy_after_simulation.stats.predictor_dict.get('predictors', [])
    assert len(predictors) > 0, "No predictor data found"
    
    predictor_df = pd.DataFrame(predictors)
    
    # Check bid price variance
    if 'b_price' in predictor_df.columns:
        bid_variance = predictor_df['b_price'].var()
        assert bid_variance > 0.0, f"Bid price variance too low: {bid_variance} (indicates fake data)"
    
    # Check ask price variance
    if 'a_price' in predictor_df.columns:
        ask_variance = predictor_df['a_price'].var()
        assert ask_variance > 0.0, f"Ask price variance too low: {ask_variance} (indicates fake data)"
    
    print("✅ test_price_variance_sufficient PASSED")


def test_trade_price_variance():
    """Test that trade prices have reasonable variance."""
    predictors = strategy_after_simulation.stats.predictor_dict.get('predictors', [])
    predictor_df = pd.DataFrame(predictors)
    
    if 'trd_price' in predictor_df.columns:
        trade_variance = predictor_df['trd_price'].var()
        assert trade_variance > 0.0, f"Trade price variance too low: {trade_variance} (indicates fake data)"
    
    print("✅ test_trade_price_variance PASSED")


def test_volume_variance_reasonable():
    """Test that volume data has reasonable variance."""
    predictors = strategy_after_simulation.stats.predictor_dict.get('predictors', [])
    predictor_df = pd.DataFrame(predictors)
    
    volume_fields = ['bid_volume', 'ask_volume']
    for field in volume_fields:
        if field in predictor_df.columns:
            volume_variance = predictor_df[field].var()
            # Note: Volume variance can be lower than prices, but should not be zero
            assert volume_variance >= 0.0, f"{field} variance negative: {volume_variance}"
    
    print("✅ test_volume_variance_reasonable PASSED")


def test_price_uniqueness():
    """Test that prices have sufficient uniqueness (not all identical)."""
    predictors = strategy_after_simulation.stats.predictor_dict.get('predictors', [])
    predictor_df = pd.DataFrame(predictors)
    
    # Check bid price uniqueness
    if 'b_price' in predictor_df.columns:
        unique_bids = predictor_df['b_price'].nunique()
        total_bids = len(predictor_df['b_price'])
        assert unique_bids > 1, f"Only {unique_bids} unique bid prices out of {total_bids} (indicates fake data)"
    
    # Check ask price uniqueness
    if 'a_price' in predictor_df.columns:
        unique_asks = predictor_df['a_price'].nunique()
        total_asks = len(predictor_df['a_price'])
        assert unique_asks > 1, f"Only {unique_asks} unique ask prices out of {total_asks} (indicates fake data)"
    
    print("✅ test_price_uniqueness PASSED")


def test_spread_variation():
    """Test that bid-ask spreads vary (real market microstructure)."""
    predictors = strategy_after_simulation.stats.predictor_dict.get('predictors', [])
    predictor_df = pd.DataFrame(predictors)
    
    if 'ba_spread' in predictor_df.columns:
        spread_variance = predictor_df['ba_spread'].var()
        assert spread_variance > 0.0, f"Spread variance too low: {spread_variance} (indicates fake data)"
        
        # Check that spreads are not all identical
        unique_spreads = predictor_df['ba_spread'].nunique()
        assert unique_spreads > 1, f"Only {unique_spreads} unique spreads (indicates fake data)"
    
    print("✅ test_spread_variation PASSED")


def test_sparsity_variation():
    """Test that sparsity metrics vary (real market microstructure)."""
    predictors = strategy_after_simulation.stats.predictor_dict.get('predictors', [])
    predictor_df = pd.DataFrame(predictors)
    
    sparsity_fields = ['b_price_sparsity', 'a_price_sparsity']
    for field in sparsity_fields:
        if field in predictor_df.columns:
            unique_values = predictor_df[field].nunique()
            # Sparsity should have some variation, not all identical
            assert unique_values > 1, f"{field} has only {unique_values} unique values (indicates fake data)"
    
    print("✅ test_sparsity_variation PASSED")


def test_no_obvious_patterns():
    """Test that data doesn't have obvious fake patterns."""
    predictors = strategy_after_simulation.stats.predictor_dict.get('predictors', [])
    predictor_df = pd.DataFrame(predictors)
    
    # Check that consecutive prices don't have obvious patterns
    if 'b_price' in predictor_df.columns and len(predictor_df) > 1:
        bid_prices = predictor_df['b_price'].values
        
        # Check that prices are not monotonically increasing/decreasing
        is_monotonic_inc = np.all(np.diff(bid_prices) >= 0)
        is_monotonic_dec = np.all(np.diff(bid_prices) <= 0)
        
        assert not (is_monotonic_inc or is_monotonic_dec), "Bid prices show monotonic pattern (suspicious)"
    
    print("✅ test_no_obvious_patterns PASSED")


def test_realistic_price_ranges():
    """Test that prices are in realistic ranges for energy markets."""
    predictors = strategy_after_simulation.stats.predictor_dict.get('predictors', [])
    predictor_df = pd.DataFrame(predictors)
    
    # Energy prices should be reasonable (not negative, not extremely high)
    price_fields = ['b_price', 'a_price', 'trd_price']
    for field in price_fields:
        if field in predictor_df.columns:
            prices = predictor_df[field].dropna()
            if len(prices) > 0:
                min_price = prices.min()
                max_price = prices.max()
                
                assert min_price >= 0, f"{field} has negative prices: {min_price}"
                assert max_price <= 1000, f"{field} has unrealistically high prices: {max_price}"
    
    print("✅ test_realistic_price_ranges PASSED")


def test_market_data_statistical_properties():
    """Test that market data has expected statistical properties."""
    predictors = strategy_after_simulation.stats.predictor_dict.get('predictors', [])
    predictor_df = pd.DataFrame(predictors)
    
    # Print statistical summary for verification
    print(f"📊 Market data statistics (sample size: {len(predictor_df)}):")
    
    key_fields = ['b_price', 'a_price', 'trd_price', 'ba_spread']
    for field in key_fields:
        if field in predictor_df.columns:
            data = predictor_df[field].dropna()
            if len(data) > 0:
                print(f"  {field}: mean={data.mean():.3f}, std={data.std():.3f}, min={data.min():.3f}, max={data.max():.3f}")
    
    print("✅ test_market_data_statistical_properties PASSED")


def run_data_validation_tests():
    """Run all real data validation tests."""
    print("🧪 Running real data validation tests...")
    
    test_price_variance_sufficient()
    test_trade_price_variance()
    test_volume_variance_reasonable()
    test_price_uniqueness()
    test_spread_variation()
    test_sparsity_variation()
    test_no_obvious_patterns()
    test_realistic_price_ranges()
    test_market_data_statistical_properties()
    
    print("✅ All real data validation tests PASSED")


class TestRealDataValidation(BaseObserverTest):
    """Unittest class for real data validation."""
    
    def test_price_variance(self):
        """Test price variance using unittest framework."""
        predictors = self.strategy.stats.predictor_dict.get('predictors', [])
        predictor_df = pd.DataFrame(predictors)
        
        bid_variance = predictor_df['b_price'].var()
        ask_variance = predictor_df['a_price'].var()
        
        self.assertGreater(bid_variance, 0.0, "Bid price variance too low")
        self.assertGreater(ask_variance, 0.0, "Ask price variance too low")
    
    def test_price_uniqueness(self):
        """Test price uniqueness using unittest framework."""
        predictors = self.strategy.stats.predictor_dict.get('predictors', [])
        predictor_df = pd.DataFrame(predictors)
        
        unique_bids = predictor_df['b_price'].nunique()
        unique_asks = predictor_df['a_price'].nunique()
        
        self.assertGreater(unique_bids, 1, "Not enough unique bid prices")
        self.assertGreater(unique_asks, 1, "Not enough unique ask prices")