"""
Reusable Mock Helpers for Observer Strategy TDD Tests

This module provides common mock objects and helper functions used across
multiple test files to ensure consistency and reduce duplication.
"""

import time
from typing import List, Optional


def create_mock_strategy(strategy_id: str, instrument_ids: List[str], 
                        product_ids: List[str], broker_list: List[int]):
    """
    Create a properly configured mock strategy for testing.
    
    Args:
        strategy_id: Unique strategy identifier
        instrument_ids: List of instrument/delivery area IDs
        product_ids: List of product IDs  
        broker_list: List of broker IDs
        
    Returns:
        Configured CustomStrategy instance ready for testing
    """
    from own_strategies.ObserverStrategy.observer_strategy.custom_strategy import CustomStrategy
    
    # Create mock dependencies
    class MockAutotrader:
        def __init__(self):
            self.current_timestamp = time.time()
            self.halted = False
            self.halt_reason = None
            
        def get_exchange(self, exchange_name):
            return MockExchange()
            
    class MockExchange:
        def __init__(self):
            self.halted = False
            self.halt_reason = None
            self.products = MockProducts()
            
        def init_files_ready(self):
            return True
            
    class MockProducts:
        def get_by_id(self, product_id):
            return MockProduct()
            
        def get_by_timerange(self, *args, **kwargs):
            return [MockProduct()]
            
        def get_active_products(self, instrument_id):
            return [MockProduct()]
            
        def get_all(self):
            return [MockProduct()]
            
    class MockProduct:
        def __init__(self):
            self.id = product_ids[0] if product_ids else "dey1"
            self.product_id = product_ids[0] if product_ids else "dey1" 
            self.name = product_ids[0] if product_ids else "dey1"
            self.orders = MockOrders()
            
    class MockOrders:
        def get(self, portfolio_key=None):
            return []
    
    # Create strategy instance
    mock_autotrader = MockAutotrader()
    strategy = CustomStrategy(
        autotrader_instance=mock_autotrader,
        strategy_id=strategy_id,
        caption="TEST_OBSERVER",
        strategy_package_name="observer_strategy"
    )
    
    # Set required attributes
    strategy.delivery_areas = instrument_ids
    strategy.active = True
    strategy.halted = False
    strategy.halt_reason = None
    strategy._pt_active = True
    strategy.exchange_1 = "TRAYPORT"
    
    # Initialize strategy with configuration
    strategy_json = {
        'product_ids': product_ids,
        'broker_list': broker_list,
        'instrument_ids': instrument_ids,
        'delivery_areas': instrument_ids,
        'caption': 'TEST_OBSERVER'
    }
    
    strategy.on_strategy_configuration_update(strategy_json)
    
    # Ensure delivery_areas is set correctly after parent class configuration
    strategy.delivery_areas = instrument_ids
    
    # Also ensure ref_area is set correctly
    if hasattr(strategy, 'ref_area') and strategy.ref_area and 'None' in strategy.ref_area:
        from own_strategies.ObserverStrategy.observer_strategy.own_tools.instrument_key import InstrumentKey
        strategy.ref_area = InstrumentKey(instrument_ids[0], product_ids[0]).key
    
    return strategy


def create_mock_trade(trade_id: str, product_id: str, delivery_area: str,
                     initiator_broker_id: int, aggressor_broker_id: int,
                     price: float, quantity: float, portfolio_key: Optional[str] = None):
    """
    Create a mock trade object for testing.
    
    Args:
        trade_id: Unique trade identifier
        product_id: Product identifier
        delivery_area: Delivery area identifier
        initiator_broker_id: ID of trade initiator broker
        aggressor_broker_id: ID of trade aggressor broker
        price: Trade price
        quantity: Trade quantity
        portfolio_key: Optional portfolio key (use for arbitrage trades)
        
    Returns:
        Mock trade object with required attributes and methods
    """
    class MockTradeProduct:
        def __init__(self, product_id):
            self.product_id = product_id
            
    class MockTrade:
        def __init__(self):
            self.trade_id = trade_id
            self.buy_delivery_area = delivery_area
            self.sell_delivery_area = delivery_area
            self.product = MockTradeProduct(product_id)
            self.price = price
            self.quantity = quantity
            self.execution_time = int(time.time())
            self.initiator_broker_id = initiator_broker_id
            self.aggressor_broker_id = aggressor_broker_id
            self.portfolio_key = portfolio_key
            
        def match_delivery_areas(self, delivery_areas):
            return (self.buy_delivery_area in delivery_areas or 
                   self.sell_delivery_area in delivery_areas)
                   
    return MockTrade()


def create_mock_orders(product_id: str, delivery_area: str, num_orders: int = 5):
    """
    Create mock order book orders for testing.
    
    Args:
        product_id: Product identifier
        delivery_area: Delivery area identifier
        num_orders: Number of orders to create
        
    Returns:
        List of mock order objects
    """
    class MockOrderProduct:
        def __init__(self, product_id):
            self.product_id = product_id
            
    class MockOrder:
        def __init__(self, delivery_area_id, product_id, price, quantity, direction, broker_id):
            self.delivery_area_id = delivery_area_id
            self.product = MockOrderProduct(product_id)
            self.price = price
            self.quantity = quantity
            self.direction = direction
            self.broker_id = broker_id
            self.is_tradable = True
            
    orders = []
    
    # Create some bid orders
    for i in range(num_orders):
        orders.append(MockOrder(
            delivery_area_id=delivery_area,
            product_id=product_id,
            price=79.0 + i * 0.1,  # Increasing bid prices
            quantity=1.0 + i * 0.5,
            direction='buy',
            broker_id=38
        ))
        
    # Create some ask orders  
    for i in range(num_orders):
        orders.append(MockOrder(
            delivery_area_id=delivery_area,
            product_id=product_id,
            price=80.0 + i * 0.1,  # Increasing ask prices
            quantity=1.0 + i * 0.5,
            direction='sell',
            broker_id=39
        ))
        
    return orders


def create_mock_orderbook_data():
    """
    Create mock order book data structure for testing metric calculations.
    
    Returns:
        Mock orderbook object with bids and asks for local_ob_attributes testing
    """
    class MockOrderBookOrder:
        def __init__(self, price, volume):
            self.price = price
            self.price_val = price
            self.volume = volume
            self.volume_val = volume
            
    class MockOrderBook:
        def __init__(self):
            # Create realistic bid/ask structure
            self.bids = [
                MockOrderBookOrder(79.5, 10.0),
                MockOrderBookOrder(79.0, 15.0),
                MockOrderBookOrder(78.5, 20.0),
                MockOrderBookOrder(78.0, 25.0),
                MockOrderBookOrder(77.5, 30.0),
            ]
            
            self.asks = [
                MockOrderBookOrder(80.0, 12.0),
                MockOrderBookOrder(80.5, 18.0),
                MockOrderBookOrder(81.0, 25.0),
                MockOrderBookOrder(81.5, 28.0),
                MockOrderBookOrder(82.0, 35.0),
            ]
            
    return MockOrderBook()


def assert_metric_precision_match(actual_value: float, expected_value: float, 
                                metric_name: str, tolerance: float = 1e-10):
    """
    Assert that two metric values match within floating-point precision tolerance.
    
    Args:
        actual_value: Value calculated by strategy
        expected_value: Value calculated by local implementation
        metric_name: Name of metric for error messages
        tolerance: Maximum allowed difference
        
    Raises:
        AssertionError: If values don't match within tolerance
    """
    import unittest
    
    if abs(actual_value - expected_value) > tolerance:
        raise AssertionError(
            f"Metric '{metric_name}' precision mismatch:\n"
            f"  Strategy value: {actual_value}\n"
            f"  Local value: {expected_value}\n"
            f"  Difference: {abs(actual_value - expected_value)}\n"
            f"  Tolerance: {tolerance}"
        )