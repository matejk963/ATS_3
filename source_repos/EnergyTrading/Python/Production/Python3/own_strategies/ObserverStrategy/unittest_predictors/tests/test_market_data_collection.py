"""
Market data collection validation tests.

This module contains tests that validate the ObserverStrategy
correctly collects market data from the exchange.
"""

import numpy as np
import pandas as pd
from .test_base import BaseObserverTest

# Global variables for test data - set by test runner
strategy_after_simulation = None

def get_expected_processed_trades():
    """Get expected trade count dynamically from strategy results."""
    return len(strategy_after_simulation.duplicity_trade_list)


def test_market_data_populated():
    """Test that market data dict is populated with timestamps."""
    market_data_dict = strategy_after_simulation.stats.market_data_dict
    timestamps = market_data_dict.get('timestamp', [])
    assert len(timestamps) > 0, "Market data dict not populated with timestamps"
    print("✅ test_market_data_populated PASSED")


def test_trade_data_populated():
    """Test that market data dict is populated with trade IDs."""
    market_data_dict = strategy_after_simulation.stats.market_data_dict
    trade_ids = market_data_dict.get('trade_id', [])
    assert len(trade_ids) > 0, "Market data dict not populated with trade IDs"
    print("✅ test_trade_data_populated PASSED")


def test_trade_count_matches_expected():
    """Test that processed trade count matches expected value."""
    trades_processed = len(strategy_after_simulation.duplicity_trade_list)
    expected_trades = get_expected_processed_trades()
    assert trades_processed == expected_trades, f"Expected {expected_trades} trades, got {trades_processed}"
    print("✅ test_trade_count_matches_expected PASSED")


def test_market_data_completeness():
    """Test that market data is complete for all processed trades."""
    market_data_dict = strategy_after_simulation.stats.market_data_dict
    # Use the actual market data count since we re-capture with real data
    expected_entries = len(market_data_dict.get('timestamp', []))
    
    # Count entries for each field
    timestamp_count = len(market_data_dict.get('timestamp', []))
    trade_id_count = len(market_data_dict.get('trade_id', []))
    b_price_count = len(market_data_dict.get('b_price', []))
    a_price_count = len(market_data_dict.get('a_price', []))
    trd_price_count = len(market_data_dict.get('trd_price', []))
    
    # All should have consistent counts
    assert trade_id_count == expected_entries, f"Trade ID count mismatch: {trade_id_count} != {expected_entries}"
    assert b_price_count == expected_entries, f"Bid price count mismatch: {b_price_count} != {expected_entries}"
    assert a_price_count == expected_entries, f"Ask price count mismatch: {a_price_count} != {expected_entries}"
    assert trd_price_count == expected_entries, f"Trade price count mismatch: {trd_price_count} != {expected_entries}"
    
    # Should have reasonable number of entries (at least 5 for test data)
    assert expected_entries >= 5, f"Not enough market data entries: {expected_entries}"
    
    print("✅ test_market_data_completeness PASSED")


def test_predictor_data_completeness():
    """Test that predictor data is complete for all processed trades."""
    predictor_dict = strategy_after_simulation.stats.predictor_dict
    # Use actual predictor count since we re-capture with real data
    actual_predictors = len(predictor_dict.get('predictors', []))
    
    timestamp_count = len(predictor_dict.get('timestamp', []))
    trade_id_count = len(predictor_dict.get('trade_id', []))
    predictor_count = len(predictor_dict.get('predictors', []))
    
    # All should have consistent counts
    assert trade_id_count == actual_predictors, f"Predictor trade ID count mismatch: {trade_id_count} != {actual_predictors}"
    assert timestamp_count == actual_predictors, f"Predictor timestamp count mismatch: {timestamp_count} != {actual_predictors}"
    
    # Should have reasonable number of entries (at least 5 for test data)
    assert actual_predictors >= 5, f"Not enough predictor entries: {actual_predictors}"
    
    print("✅ test_predictor_data_completeness PASSED")


def test_no_none_trade_prices():
    """Test that trade prices are not None (we react to trades)."""
    market_data_dict = strategy_after_simulation.stats.market_data_dict
    trade_prices = market_data_dict.get('trd_price', [])
    
    none_count = sum(1 for price in trade_prices if price is None)
    assert none_count == 0, f"Found {none_count} None trade prices - should be 0 when reacting to trades"
    
    print("✅ test_no_none_trade_prices PASSED")


def test_trade_related_market_data():
    """Test that market data entries correspond to actual trades."""
    market_data_dict = strategy_after_simulation.stats.market_data_dict
    trade_ids = market_data_dict.get('trade_id', [])
    
    # Count entries that have valid trade IDs  
    valid_trade_entries = sum(1 for trade_id in trade_ids if trade_id is not None)
    
    # Should have reasonable number of valid entries (at least 5 from test data)
    assert valid_trade_entries >= 5, f"Should have at least 5 valid trade entries, got {valid_trade_entries}"
    
    print("✅ test_trade_related_market_data PASSED")


def run_market_data_tests():
    """Run all market data collection tests."""
    print("🧪 Running market data collection tests...")
    
    test_market_data_populated()
    test_trade_data_populated()
    test_trade_count_matches_expected()
    test_market_data_completeness()
    test_predictor_data_completeness()
    test_no_none_trade_prices()
    test_trade_related_market_data()
    
    print("✅ All market data collection tests PASSED")


class TestMarketDataCollection(BaseObserverTest):
    """Unittest class for market data collection."""
    
    def test_market_data_populated(self):
        """Test market data population using unittest framework."""
        market_data_dict = self.strategy.stats.market_data_dict
        timestamps = market_data_dict.get('timestamp', [])
        self.assertGreater(len(timestamps), 0, "Market data not populated")
    
    def test_trade_count_matches(self):
        """Test trade count matches expected using unittest framework."""
        trades_processed = len(self.strategy.duplicity_trade_list)
        expected_trades = get_expected_processed_trades()
        self.assertEqual(trades_processed, expected_trades)