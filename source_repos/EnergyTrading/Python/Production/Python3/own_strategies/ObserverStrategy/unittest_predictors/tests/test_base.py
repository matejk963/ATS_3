"""
Base test infrastructure for ObserverStrategy tests.

This module provides common utilities and base classes for all
ObserverStrategy tests.
"""

import unittest
import numpy as np
import pandas as pd
from abc import ABC, abstractmethod


class BaseObserverTest(unittest.TestCase):
    """Base class for all ObserverStrategy tests."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test class with shared strategy instance."""
        # This will be set by the test runner
        cls.strategy = None
        cls.simulator = None
        cls.test_data = None
    
    def setUp(self):
        """Set up individual test."""
        if self.strategy is None:
            self.skipTest("Strategy not available - run via test runner")
    
    def assertArraysClose(self, actual, expected, rtol=1e-6, atol=1e-6, msg=None):
        """Assert that two arrays are close within tolerance."""
        try:
            np.testing.assert_allclose(actual, expected, rtol=rtol, atol=atol)
        except AssertionError as e:
            if msg:
                raise AssertionError(f"{msg}: {e}")
            raise
    
    def assertValidTradeId(self, trade_id):
        """Assert that trade ID is valid."""
        self.assertIsNotNone(trade_id, "Trade ID is None")
        self.assertIsInstance(trade_id, str, "Trade ID is not a string")
        self.assertGreater(len(trade_id), 0, "Trade ID is empty")
    
    def assertValidPrice(self, price, field_name="price"):
        """Assert that price is valid."""
        self.assertIsNotNone(price, f"{field_name} is None")
        self.assertIsInstance(price, (int, float), f"{field_name} is not numeric")
        self.assertGreaterEqual(price, 0, f"{field_name} is negative")
        self.assertLess(price, 1000, f"{field_name} is unrealistically high")
    
    def assertSufficientVariance(self, data, field_name="data", min_variance=0.001):
        """Assert that data has sufficient variance (not fake)."""
        variance = np.var(data)
        self.assertGreater(variance, min_variance, 
                          f"{field_name} variance {variance} too low (indicates fake data)")
    
    def assertUniqueValues(self, data, field_name="data", min_unique=2):
        """Assert that data has sufficient unique values."""
        unique_count = len(set(data))
        self.assertGreaterEqual(unique_count, min_unique,
                               f"{field_name} has only {unique_count} unique values")


class TestDataValidator:
    """Utility class for validating test data."""
    
    @staticmethod
    def validate_market_data_dict(market_data_dict, expected_count=None):
        """Validate market data dictionary structure."""
        required_fields = ['timestamp', 'trade_id', 'b_price', 'a_price', 'trd_price']
        
        for field in required_fields:
            if field not in market_data_dict:
                raise ValueError(f"Missing required field: {field}")
            
            field_data = market_data_dict[field]
            if len(field_data) == 0:
                raise ValueError(f"Empty field: {field}")
            
            if expected_count is not None and len(field_data) != expected_count:
                raise ValueError(f"Field {field} has {len(field_data)} entries, expected {expected_count}")
    
    @staticmethod
    def validate_predictor_dict(predictor_dict, expected_count=None):
        """Validate predictor dictionary structure."""
        required_fields = ['timestamp', 'trade_id', 'predictors']
        
        for field in required_fields:
            if field not in predictor_dict:
                raise ValueError(f"Missing required field: {field}")
            
            field_data = predictor_dict[field]
            if len(field_data) == 0:
                raise ValueError(f"Empty field: {field}")
            
            if expected_count is not None and len(field_data) != expected_count:
                raise ValueError(f"Field {field} has {len(field_data)} entries, expected {expected_count}")
    
    @staticmethod
    def validate_predictor_data(predictor_list):
        """Validate individual predictor data entries."""
        expected_fields = ['b_price', 'a_price', 'ba_spread', 'mid_price', 'bid_volume', 'ask_volume']
        
        for i, predictor in enumerate(predictor_list):
            if not isinstance(predictor, dict):
                raise ValueError(f"Predictor at index {i} is not a dictionary")
            
            for field in expected_fields:
                if field not in predictor:
                    raise ValueError(f"Predictor at index {i} missing field: {field}")
                
                value = predictor[field]
                if value is not None and not isinstance(value, (int, float)):
                    raise ValueError(f"Predictor at index {i} field {field} is not numeric: {type(value)}")
    
    @staticmethod
    def validate_strategy_state(strategy):
        """Validate strategy state after simulation."""
        if not hasattr(strategy, 'initialized'):
            raise ValueError("Strategy missing 'initialized' attribute")
        
        if not strategy.initialized:
            raise ValueError("Strategy not properly initialized")
        
        if not hasattr(strategy, 'stats'):
            raise ValueError("Strategy missing 'stats' attribute")
        
        if not hasattr(strategy, 'duplicity_trade_list'):
            raise ValueError("Strategy missing 'duplicity_trade_list' attribute")
        
        if not hasattr(strategy.stats, 'market_data_dict'):
            raise ValueError("Strategy stats missing 'market_data_dict' attribute")
        
        if not hasattr(strategy.stats, 'predictor_dict'):
            raise ValueError("Strategy stats missing 'predictor_dict' attribute")


class TestReporter:
    """Utility class for test reporting."""
    
    @staticmethod
    def print_test_summary(test_results):
        """Print summary of test results."""
        total_tests = len(test_results)
        passed_tests = sum(1 for result in test_results if result['status'] == 'PASSED')
        failed_tests = total_tests - passed_tests
        
        print(f"\n{'='*60}")
        print(f"TEST SUMMARY")
        print(f"{'='*60}")
        print(f"Total tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Success rate: {passed_tests/total_tests*100:.1f}%")
        
        if failed_tests > 0:
            print(f"\nFAILED TESTS:")
            for result in test_results:
                if result['status'] == 'FAILED':
                    print(f"  ❌ {result['name']}: {result['error']}")
        
        print(f"{'='*60}")
    
    @staticmethod
    def print_data_summary(strategy):
        """Print summary of strategy data."""
        if not strategy:
            print("No strategy data available")
            return
        
        trades_processed = len(strategy.duplicity_trade_list)
        market_data_count = len(strategy.stats.market_data_dict.get('timestamp', []))
        predictor_count = len(strategy.stats.predictor_dict.get('timestamp', []))
        
        print(f"\n📊 STRATEGY DATA SUMMARY:")
        print(f"  Strategy ID: {strategy.strategy_id}")
        print(f"  Initialized: {strategy.initialized}")
        print(f"  Trades processed: {trades_processed}")
        print(f"  Market data entries: {market_data_count}")
        print(f"  Predictor entries: {predictor_count}")
        print(f"  Delivery areas: {strategy.delivery_areas}")
        print(f"  Product IDs: {strategy.product_ids}")
        print(f"  Broker list: {strategy.broker_list}")


class TestFixtures:
    """Common test fixtures and data."""
    
    @staticmethod
    def create_sample_market_data():
        """Create sample market data for testing."""
        return {
            'timestamp': [1656324000.0, 1656324001.0, 1656324002.0],
            'trade_id': ['test_trade_1', 'test_trade_2', 'test_trade_3'],
            'b_price': [82.0, 82.1, 82.2],
            'a_price': [82.5, 82.6, 82.7],
            'trd_price': [82.3, 82.4, 82.5]
        }
    
    @staticmethod
    def create_sample_predictor_data():
        """Create sample predictor data for testing."""
        return [
            {
                'b_price': 82.0,
                'a_price': 82.5,
                'ba_spread': 0.5,
                'mid_price': 82.25,
                'bid_volume': 1,
                'ask_volume': 1,
                'b_price_sparsity': 0.1,
                'a_price_sparsity': 0.1
            },
            {
                'b_price': 82.1,
                'a_price': 82.6,
                'ba_spread': 0.5,
                'mid_price': 82.35,
                'bid_volume': 2,
                'ask_volume': 1,
                'b_price_sparsity': 0.12,
                'a_price_sparsity': 0.11
            }
        ]
    
    @staticmethod
    def create_sample_messages():
        """Create sample backtest messages."""
        return [
            {
                'message_type': 'trade_list',
                'timestamp': pd.Timestamp('2022-06-27 10:00:00'),
                'data': [{
                    'trade_id': 'test_trade_1',
                    'price': 82.3,
                    'quantity': 1,
                    'initiator_broker_id': '38',
                    'aggressor_broker_id': '38'
                }]
            },
            {
                'message_type': 'order_book',
                'timestamp': pd.Timestamp('2022-06-27 10:00:00'),
                'data': [{
                    'price': 82.0,
                    'quantity': 1,
                    'direction': 'buy',
                    'broker_id': '38',
                    'action': 'ADD'
                }]
            }
        ]