"""
OrderBook.OrderBook module for unpickling test data.

This module provides the exact structure needed for unpickling:
OrderBook.OrderBook.OrderBookSnaps
"""

import pandas as pd
from datetime import datetime
from typing import List, Dict, Any, Optional


class OrderBookSnaps:
    """Stub for OrderBookSnaps class from OrderBook.OrderBook module."""
    
    def __init__(self, verbose: bool = False):
        self.__verbose = verbose
        self.LoB_dict = {}
        self.__time_list = []
        self.__date_list = []
        self.err_dict = {}
        
    @property
    def time_list(self):
        """Public property to access private time_list."""
        return self.__time_list
        
    @time_list.setter
    def time_list(self, value):
        """Setter for time_list property."""
        self.__time_list = value
        
    def update_data(self, lob_dict: Dict[int, Any], time_list: List[datetime]):
        """Update the OrderBook snapshots data."""
        self.LoB_dict = lob_dict
        self.__time_list = time_list
        
    def add_snapshot(self, key: int, snapshot: Any):
        """Add a single snapshot."""
        self.LoB_dict[key] = snapshot
        if hasattr(snapshot, 'time_snapshot') and snapshot.time_snapshot not in self.__time_list:
            self.__time_list.append(snapshot.time_snapshot)
            
    def get_snapshot_count(self) -> int:
        """Get the number of snapshots."""
        return len(self.LoB_dict)
        
    def get_time_range(self) -> tuple:
        """Get the time range of snapshots."""
        if not self.__time_list:
            return None, None
        return min(self.__time_list), max(self.__time_list)


class OrderBookSingle:
    """Stub for OrderBookSingle class."""
    def __init__(self, verbose: bool = False):
        self.__verbose = verbose
        self.__aux_dict = {}
        self.time_snapshot = None
        self.bids = []
        self.asks = []
        self.diff_dict = {}
        

class Order:
    """Stub for Order class."""
    def __init__(self, price: float, volume: int, side: int, po_id: str, 
                 timestamp: datetime, venue: int = 20):
        self.price = price
        self.volume = volume
        self.side = side
        self.po_id = po_id
        self.timestamp = timestamp
        self.venue = venue
        
        # Properties for compatibility
        self.price_val = price / 10000.0 if isinstance(price, int) else price
        self.quantity = volume


class OrderSim:
    """Stub for OrderSim class."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        
        # Ensure price_val exists for compatibility
        if hasattr(self, 'price') and not hasattr(self, 'price_val'):
            self.price_val = self.price / 10000.0 if isinstance(self.price, int) else self.price
        
        # Ensure quantity exists for compatibility
        if hasattr(self, 'volume') and not hasattr(self, 'quantity'):
            self.quantity = self.volume
            
    def __getattr__(self, name):
        """Handle missing attributes dynamically."""
        if name == 'price_val':
            if hasattr(self, 'price'):
                return self.price / 10000.0 if isinstance(self.price, int) else self.price
            return None
        elif name == 'volume_val':
            if hasattr(self, 'volume'):
                return self.volume
            return None
        elif name == 'quantity':
            if hasattr(self, 'volume'):
                return self.volume
            return None
        elif name == 'order_id':
            return getattr(self, 'po_id', None)
        elif name == 'po_id':
            return getattr(self, 'order_id', None)
        elif name == 'side':
            # Default side based on venue or other attributes
            return getattr(self, 'imp_ven', 1)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")


class OrderBook:
    """Main OrderBook class that contains OrderBookSnaps."""
    OrderBookSnaps = OrderBookSnaps
    OrderBookSingle = OrderBookSingle
    Order = Order
    OrderSim = OrderSim
    
    def __init__(self):
        pass


# Export the main classes
__all__ = ['OrderBook', 'OrderBookSnaps', 'OrderBookSingle', 'Order', 'OrderSim']