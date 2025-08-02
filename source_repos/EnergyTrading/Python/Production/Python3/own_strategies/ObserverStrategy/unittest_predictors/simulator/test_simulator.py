"""
Unit tests for ObserverSimulator correctness.

This module tests the simulator infrastructure to ensure proper
operation independent of strategy logic.
"""

import unittest
import numpy as np
import pandas as pd
from unittest.mock import Mock, patch
from .observer_simulation import ObserverSimulator


class TestObserverSimulator(unittest.TestCase):
    """Test ObserverSimulator functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.simulator = ObserverSimulator("test_strategy")
        
        # Create sample messages for testing
        self.sample_trade_msg = {
            'message_type': 'trade_list',
            'timestamp': pd.Timestamp('2022-06-27 10:00:00'),
            'data': [{
                'trade_id': 'test_trade_1',
                'price': 82.5,
                'quantity': 1,
                'initiator_broker_id': '38',
                'aggressor_broker_id': '38',
                'inst_specifier': [{
                    'instrument_id': '10100482',
                    'first_item_id': '20',
                    'term_format_id': 1,
                    'first_sequence_id': '10000106'
                }]
            }]
        }
        
        self.sample_order_msg = {
            'message_type': 'order_book',
            'timestamp': pd.Timestamp('2022-06-27 10:00:00'),
            'data': [{
                'price': 82.4,
                'quantity': 1,
                'direction': 'buy',
                'broker_id': '38',
                'action': 'ADD',
                'inst_specifier': [{
                    'instrument_id': '10100482',
                    'first_item_id': '20',
                    'term_format_id': 1,
                    'first_sequence_id': '10000106'
                }]
            }]
        }
    
    def test_simulator_initialization(self):
        """Test simulator initializes with correct configuration."""
        self.assertEqual(self.simulator.strategy_id, "test_strategy")
        self.assertEqual(self.simulator.instrument_ids, ["10100482"])
        self.assertEqual(self.simulator.product_ids, ["10000106_20"])
        self.assertEqual(self.simulator.broker_list, ["38", "27"])
        self.assertEqual(self.simulator.timeout_seconds, 300)
    
    def test_message_format_fixing(self):
        """Test message format fixing preserves data while fixing format."""
        # Test trade message fixing
        fixed_trade = self.simulator._fix_message_format(self.sample_trade_msg)
        
        # Should have sequential timestamp
        self.assertIsInstance(fixed_trade['timestamp'], float)
        self.assertGreater(fixed_trade['timestamp'], 0)
        
        # Should fix term_format_id
        self.assertIsNone(fixed_trade['data'][0]['inst_specifier'][0]['term_format_id'])
        
        # Should preserve original data
        self.assertEqual(fixed_trade['data'][0]['trade_id'], 'test_trade_1')
        self.assertEqual(fixed_trade['data'][0]['price'], 82.5)
    
    def test_real_data_validation_passes(self):
        """Test real data validation passes with sufficient variance."""
        # Create messages with varying prices
        msgs = []
        for i in range(10):
            msg = {
                'message_type': 'order_book',
                'timestamp': float(i),
                'data': [{
                    'direction': 'buy',
                    'price': 82.0 + i * 0.1,  # Varying prices
                    'quantity': 1
                }, {
                    'direction': 'sell', 
                    'price': 82.5 + i * 0.1,  # Varying prices
                    'quantity': 1
                }]
            }
            msgs.append(msg)
        
        # Should not raise exception
        try:
            self.simulator._validate_real_data(msgs)
        except ValueError:
            self.fail("Real data validation failed with sufficient variance")
    
    def test_real_data_validation_fails_fake_data(self):
        """Test real data validation fails with insufficient variance."""
        # Create messages with static prices (fake data)
        msgs = []
        for i in range(10):
            msg = {
                'message_type': 'order_book',
                'timestamp': float(i),
                'data': [{
                    'direction': 'buy',
                    'price': 82.0,  # Static price
                    'quantity': 1
                }, {
                    'direction': 'sell',
                    'price': 82.5,  # Static price
                    'quantity': 1
                }]
            }
            msgs.append(msg)
        
        # Should raise ValueError for fake data
        with self.assertRaises(ValueError) as context:
            self.simulator._validate_real_data(msgs)
        
        self.assertIn("FAKE DATA DETECTED", str(context.exception))
    
    def test_message_processing_preserves_order(self):
        """Test message processing preserves chronological order."""
        # Create messages with different timestamps
        msgs = [
            {**self.sample_trade_msg, 'timestamp': pd.Timestamp('2022-06-27 10:00:02')},
            {**self.sample_order_msg, 'timestamp': pd.Timestamp('2022-06-27 10:00:01')},
            {**self.sample_trade_msg, 'timestamp': pd.Timestamp('2022-06-27 10:00:03')}
        ]
        
        processed = self.simulator._process_messages_for_exchange(msgs)
        
        # Should have 3 messages
        self.assertEqual(len(processed), 3)
        
        # Should be in chronological order (timestamps should be sequential)
        for i in range(1, len(processed)):
            self.assertGreater(processed[i]['timestamp'], processed[i-1]['timestamp'])
    
    def test_simulator_stats_calculation(self):
        """Test simulation statistics calculation."""
        # Mock strategy object
        mock_strategy = Mock()
        mock_strategy.strategy_id = "test_strategy"
        mock_strategy.initialized = True
        mock_strategy.delivery_areas = ["10100482"]
        mock_strategy.product_ids = ["10000106_20"]
        mock_strategy.broker_list = ["38", "27"]
        mock_strategy.duplicity_trade_list = ["trade1", "trade2", "trade3"]
        mock_strategy.stats.market_data_dict = {'timestamp': [1, 2, 3]}
        mock_strategy.stats.predictor_dict = {'timestamp': [1, 2, 3]}
        
        stats = self.simulator.get_simulation_stats(mock_strategy)
        
        expected_stats = {
            'strategy_id': "test_strategy",
            'initialized': True,
            'delivery_areas': ["10100482"],
            'product_ids': ["10000106_20"],
            'broker_list': ["38", "27"],
            'trades_processed': 3,
            'market_data_entries': 3,
            'predictor_data_entries': 3,
        }
        
        self.assertEqual(stats, expected_stats)
    
    def test_timeout_configuration(self):
        """Test timeout configuration works correctly."""
        custom_simulator = ObserverSimulator("test_timeout")
        custom_simulator.timeout_seconds = 10
        
        self.assertEqual(custom_simulator.timeout_seconds, 10)


def test_simulator_initialization():
    """Simple test for simulator initialization."""
    simulator = ObserverSimulator("test_init")
    assert simulator.strategy_id == "test_init"
    assert simulator.instrument_ids == ["10100482"]
    print("✅ test_simulator_initialization PASSED")


def test_message_format_fixing():
    """Simple test for message format fixing."""
    simulator = ObserverSimulator("test_format")
    
    sample_msg = {
        'message_type': 'trade_list',
        'timestamp': pd.Timestamp('2022-06-27 10:00:00'),
        'data': [{
            'trade_id': 'test_123',
            'price': 85.0,
            'inst_specifier': [{'term_format_id': 1}]
        }]
    }
    
    fixed_msg = simulator._fix_message_format(sample_msg)
    assert fixed_msg['data'][0]['inst_specifier'][0]['term_format_id'] is None
    assert fixed_msg['data'][0]['trade_id'] == 'test_123'
    print("✅ test_message_format_fixing PASSED")


def test_real_data_validation():
    """Simple test for real data validation."""
    simulator = ObserverSimulator("test_validation")
    
    # Create valid varying data
    msgs = []
    for i in range(5):
        msg = {
            'message_type': 'order_book',
            'timestamp': float(i),
            'data': [{
                'direction': 'buy',
                'price': 80.0 + i * 0.5,
                'quantity': 1
            }, {
                'direction': 'sell',
                'price': 81.0 + i * 0.5,
                'quantity': 1
            }]
        }
        msgs.append(msg)
    
    # Should not raise exception
    simulator._validate_real_data(msgs)
    print("✅ test_real_data_validation PASSED")


if __name__ == '__main__':
    # Run simple tests
    print("Running simulator tests...")
    test_simulator_initialization()
    test_message_format_fixing()
    test_real_data_validation()
    print("🎉 All simulator tests passed!")
    
    # Run unittest suite
    unittest.main(verbosity=2)