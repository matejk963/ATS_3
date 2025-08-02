"""
Test Data Fixtures for Observer Strategy TDD Tests

This module provides common test data fixtures used across multiple test files
to ensure consistency and realistic test scenarios.
"""

import time
import pickle
import os
from typing import Dict, List, Any, Tuple


class TestDataFixtures:
    """
    Centralized test data fixtures for Observer Strategy testing.
    
    Provides realistic market data scenarios for comprehensive testing.
    """
    
    @staticmethod
    def create_realistic_market_scenario():
        """
        Create a realistic market scenario with OrderBook and trades.
        
        Returns:
            Tuple of (orderbook_data, trades_data) representing a realistic market session
        """
        # Create realistic orderbook progression
        orderbook_data = {}
        base_timestamp = int(time.time())
        
        for i in range(20):
            timestamp = base_timestamp + i * 60  # 1-minute intervals
            orderbook_data[timestamp] = TestDataFixtures._create_realistic_orderbook_snapshot(i)
            
        # Create realistic trade sequence
        trades_data = []
        for i in range(10):
            trade = TestDataFixtures._create_realistic_trade(i, base_timestamp + i * 120)
            trades_data.append(trade)
            
        return orderbook_data, trades_data
        
    @staticmethod
    def create_high_volatility_scenario():
        """
        Create a high-volatility market scenario.
        
        Returns:
            Tuple of (orderbook_data, trades_data) with high price volatility
        """
        orderbook_data = {}
        base_timestamp = int(time.time())
        
        # Create volatile orderbook with large price swings
        for i in range(15):
            timestamp = base_timestamp + i * 30  # 30-second intervals
            volatility_factor = 1.0 + (i % 3 - 1) * 0.1  # ±10% swings
            orderbook_data[timestamp] = TestDataFixtures._create_volatile_orderbook_snapshot(i, volatility_factor)
            
        # Create trades with high price volatility
        trades_data = []
        for i in range(8):
            volatility_factor = 1.0 + (i % 2 - 0.5) * 0.2  # ±20% swings
            trade = TestDataFixtures._create_volatile_trade(i, base_timestamp + i * 90, volatility_factor)
            trades_data.append(trade)
            
        return orderbook_data, trades_data
        
    @staticmethod
    def create_low_volume_scenario():
        """
        Create a low-volume market scenario.
        
        Returns:
            Tuple of (orderbook_data, trades_data) with low trading volume
        """
        orderbook_data = {}
        base_timestamp = int(time.time())
        
        # Create orderbook with low volume
        for i in range(25):
            timestamp = base_timestamp + i * 120  # 2-minute intervals
            orderbook_data[timestamp] = TestDataFixtures._create_low_volume_orderbook_snapshot(i)
            
        # Create infrequent trades
        trades_data = []
        for i in range(3):  # Very few trades
            trade = TestDataFixtures._create_low_volume_trade(i, base_timestamp + i * 300)
            trades_data.append(trade)
            
        return orderbook_data, trades_data
        
    @staticmethod
    def create_edge_case_scenarios():
        """
        Create edge case scenarios for robust testing.
        
        Returns:
            Dictionary of scenario_name -> (orderbook_data, trades_data)
        """
        return {
            'empty_orderbook': (
                {int(time.time()): TestDataFixtures._create_empty_orderbook()},
                []
            ),
            'single_sided_bids': (
                {int(time.time()): TestDataFixtures._create_bids_only_orderbook()},
                []
            ),
            'single_sided_asks': (
                {int(time.time()): TestDataFixtures._create_asks_only_orderbook()},
                []
            ),
            'wide_spread': (
                {int(time.time()): TestDataFixtures._create_wide_spread_orderbook()},
                []
            ),
            'crossed_market': (
                {int(time.time()): TestDataFixtures._create_crossed_market_orderbook()},
                []
            ),
        }
        
    @staticmethod
    def load_production_data_sample():
        """
        Load ACTUAL production data sample.
        
        Returns:
            Tuple of (orderbook_data, trades_data) from REAL production data
        """
        try:
            # First try to load from RealDataLoader
            from real_data_loader import RealDataLoader
            loader = RealDataLoader()
            orderbook_dict, trades_df, _ = loader.load_single_day_data('2025-04-04')
            
            # Convert trades DataFrame to list if needed
            if trades_df is not None and len(trades_df) > 0:
                trades_data = trades_df.to_dict('records')
            else:
                trades_data = []
                
            return orderbook_dict, trades_data
            
        except Exception as e:
            print(f"Could not load data from RealDataLoader: {e}")
            
            # Fall back to pickle files if RealDataLoader fails
            base_path = os.path.dirname(os.path.abspath(__file__))
            lob_file = os.path.join(base_path, '..', 'prod_unittest_lob.pkl.sample')
            trades_file = os.path.join(base_path, '..', 'prod_unittest_trades.pkl.sample')
            
            orderbook_data = {}
            trades_data = []
            
            try:
                if os.path.exists(lob_file):
                    with open(lob_file, 'rb') as f:
                        orderbook_data = pickle.load(f)
                        
                if os.path.exists(trades_file):
                    with open(trades_file, 'rb') as f:
                        trades_data = pickle.load(f)
                        
                return orderbook_data, trades_data
                
            except Exception as e2:
                print(f"Could not load production data samples from pickle files: {e2}")
                raise ValueError("No real production data available! Tests require actual market data, not mock data.")
                
        return {}, []
        
    # Private helper methods for creating specific data scenarios
    
    @staticmethod
    def _create_realistic_orderbook_snapshot(sequence_number):
        """Create realistic orderbook snapshot"""
        class MockOrder:
            def __init__(self, price, volume):
                self.price = price
                self.price_val = price
                self.volume = volume
                self.volume_val = volume
                
        class MockOrderBook:
            def __init__(self):
                base_price = 80.0
                price_variation = sequence_number * 0.1
                
                # Create realistic bid ladder
                self.bids = [
                    MockOrder(base_price - 0.5 + price_variation, 50.0),
                    MockOrder(base_price - 1.0 + price_variation, 30.0),
                    MockOrder(base_price - 1.5 + price_variation, 20.0),
                    MockOrder(base_price - 2.0 + price_variation, 15.0),
                    MockOrder(base_price - 2.5 + price_variation, 10.0),
                ]
                
                # Create realistic ask ladder
                self.asks = [
                    MockOrder(base_price + 0.5 + price_variation, 45.0),
                    MockOrder(base_price + 1.0 + price_variation, 35.0),
                    MockOrder(base_price + 1.5 + price_variation, 25.0),
                    MockOrder(base_price + 2.0 + price_variation, 18.0),
                    MockOrder(base_price + 2.5 + price_variation, 12.0),
                ]
                
        return MockOrderBook()
        
    @staticmethod
    def _create_volatile_orderbook_snapshot(sequence_number, volatility_factor):
        """Create volatile orderbook snapshot"""
        class MockOrder:
            def __init__(self, price, volume):
                self.price = price
                self.price_val = price
                self.volume = volume
                self.volume_val = volume
                
        class MockOrderBook:
            def __init__(self):
                base_price = 80.0 * volatility_factor
                
                # Create volatile bid ladder
                self.bids = [
                    MockOrder(base_price - 0.5, 40.0),
                    MockOrder(base_price - 1.5, 25.0),
                    MockOrder(base_price - 3.0, 15.0),
                ]
                
                # Create volatile ask ladder
                self.asks = [
                    MockOrder(base_price + 0.5, 35.0),
                    MockOrder(base_price + 1.5, 20.0),
                    MockOrder(base_price + 3.0, 10.0),
                ]
                
        return MockOrderBook()
        
    @staticmethod
    def _create_low_volume_orderbook_snapshot(sequence_number):
        """Create low volume orderbook snapshot"""
        class MockOrder:
            def __init__(self, price, volume):
                self.price = price
                self.price_val = price
                self.volume = volume
                self.volume_val = volume
                
        class MockOrderBook:
            def __init__(self):
                base_price = 80.0
                
                # Create low volume bid ladder
                self.bids = [
                    MockOrder(base_price - 0.5, 2.0),
                    MockOrder(base_price - 1.0, 1.5),
                    MockOrder(base_price - 1.5, 1.0),
                ]
                
                # Create low volume ask ladder
                self.asks = [
                    MockOrder(base_price + 0.5, 1.8),
                    MockOrder(base_price + 1.0, 1.2),
                    MockOrder(base_price + 1.5, 0.8),
                ]
                
        return MockOrderBook()
        
    @staticmethod
    def _create_realistic_trade(sequence_number, timestamp):
        """Create realistic trade"""
        from shared.mock_helpers import create_mock_trade
        
        base_price = 80.0 + sequence_number * 0.1
        return create_mock_trade(
            trade_id=f"REALISTIC_TRADE_{sequence_number:03d}",
            product_id="dey1",
            delivery_area="dey1",
            initiator_broker_id=38,
            aggressor_broker_id=39,
            price=base_price,
            quantity=1.0 + sequence_number * 0.1
        )
        
    @staticmethod
    def _create_volatile_trade(sequence_number, timestamp, volatility_factor):
        """Create volatile trade"""
        from shared.mock_helpers import create_mock_trade
        
        base_price = 80.0 * volatility_factor
        return create_mock_trade(
            trade_id=f"VOLATILE_TRADE_{sequence_number:03d}",
            product_id="dey1",
            delivery_area="dey1",
            initiator_broker_id=38,
            aggressor_broker_id=39,
            price=base_price,
            quantity=0.5 + sequence_number * 0.2
        )
        
    @staticmethod
    def _create_low_volume_trade(sequence_number, timestamp):
        """Create low volume trade"""
        from shared.mock_helpers import create_mock_trade
        
        return create_mock_trade(
            trade_id=f"LOW_VOL_TRADE_{sequence_number:03d}",
            product_id="dey1",
            delivery_area="dey1",
            initiator_broker_id=38,
            aggressor_broker_id=39,
            price=80.0,
            quantity=0.1  # Very small quantity
        )
        
    @staticmethod
    def _create_empty_orderbook():
        """Create empty orderbook for edge case testing"""
        class MockOrderBook:
            def __init__(self):
                self.bids = []
                self.asks = []
                
        return MockOrderBook()
        
    @staticmethod
    def _create_bids_only_orderbook():
        """Create orderbook with only bids"""
        class MockOrder:
            def __init__(self, price, volume):
                self.price = price
                self.price_val = price
                self.volume = volume
                self.volume_val = volume
                
        class MockOrderBook:
            def __init__(self):
                self.bids = [
                    MockOrder(79.5, 10.0),
                    MockOrder(79.0, 15.0),
                    MockOrder(78.5, 20.0),
                ]
                self.asks = []
                
        return MockOrderBook()
        
    @staticmethod
    def _create_asks_only_orderbook():
        """Create orderbook with only asks"""
        class MockOrder:
            def __init__(self, price, volume):
                self.price = price
                self.price_val = price
                self.volume = volume
                self.volume_val = volume
                
        class MockOrderBook:
            def __init__(self):
                self.bids = []
                self.asks = [
                    MockOrder(80.0, 12.0),
                    MockOrder(80.5, 18.0),
                    MockOrder(81.0, 25.0),
                ]
                
        return MockOrderBook()
        
    @staticmethod
    def _create_wide_spread_orderbook():
        """Create orderbook with wide bid-ask spread"""
        class MockOrder:
            def __init__(self, price, volume):
                self.price = price
                self.price_val = price
                self.volume = volume
                self.volume_val = volume
                
        class MockOrderBook:
            def __init__(self):
                self.bids = [
                    MockOrder(75.0, 10.0),  # Low bid
                    MockOrder(74.0, 15.0),
                ]
                self.asks = [
                    MockOrder(85.0, 12.0),  # High ask - wide spread
                    MockOrder(86.0, 18.0),
                ]
                
        return MockOrderBook()
        
    @staticmethod
    def _create_crossed_market_orderbook():
        """Create crossed market orderbook (bid >= ask)"""
        class MockOrder:
            def __init__(self, price, volume):
                self.price = price
                self.price_val = price
                self.volume = volume
                self.volume_val = volume
                
        class MockOrderBook:
            def __init__(self):
                self.bids = [
                    MockOrder(80.5, 10.0),  # Bid higher than ask
                    MockOrder(80.0, 15.0),
                ]
                self.asks = [
                    MockOrder(80.0, 12.0),  # Ask lower than bid
                    MockOrder(80.5, 18.0),
                ]
                
        return MockOrderBook()


# Convenience functions for easy access to common test scenarios
def get_realistic_market_data():
    """Get realistic market data for testing"""
    return TestDataFixtures.create_realistic_market_scenario()


def get_high_volatility_data():
    """Get high volatility market data for testing"""
    return TestDataFixtures.create_high_volatility_scenario()


def get_low_volume_data():
    """Get low volume market data for testing"""
    return TestDataFixtures.create_low_volume_scenario()


def get_edge_case_data():
    """Get edge case scenarios for testing"""
    return TestDataFixtures.create_edge_case_scenarios()


def get_production_data():
    """Get production data sample for testing"""
    return TestDataFixtures.load_production_data_sample()