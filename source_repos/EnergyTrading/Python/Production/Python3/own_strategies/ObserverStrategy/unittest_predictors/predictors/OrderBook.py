"""
OrderBook stub for unpickling test data.

This module provides minimal OrderBook classes required for unpickling
the test data files, avoiding dependencies on external packages.
"""

import pandas as pd
from datetime import datetime
from typing import List, Dict, Any, Optional


class OrderBookSnaps:
    """Stub for OrderBookSnaps class from OrderBook module."""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.LoB_dict = {}
        self.time_list = []
        
    def update_data(self, lob_dict: Dict[int, Any], time_list: List[datetime]):
        """Update the OrderBook snapshots data."""
        self.LoB_dict = lob_dict
        self.time_list = time_list
        
    def add_snapshot(self, key: int, snapshot: Any):
        """Add a single snapshot."""
        self.LoB_dict[key] = snapshot
        if hasattr(snapshot, 'time_snapshot') and snapshot.time_snapshot not in self.time_list:
            self.time_list.append(snapshot.time_snapshot)
            
    def get_snapshot_count(self) -> int:
        """Get the number of snapshots."""
        return len(self.LoB_dict)
        
    def get_time_range(self) -> tuple:
        """Get the time range of snapshots."""
        if not self.time_list:
            return None, None
        return min(self.time_list), max(self.time_list)


# Create the exact nested structure expected by pickle: OrderBook.OrderBook.OrderBookSnaps
class OrderBook:
    """Main OrderBook module structure."""
    
    class OrderBook:
        """Nested OrderBook class structure for pickle compatibility."""
        
        # The class that pickle is looking for
        OrderBookSnaps = OrderBookSnaps
        
        # For completeness, add other classes that might be needed
        class OrderBookSingle:
            """Nested OrderBookSingle class."""
            def __init__(self, verbose: bool = False):
                self.verbose = verbose
                self.time_snapshot = None
                self.bids = []
                self.asks = []
                
        class Order:
            """Nested Order class."""
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


# Export the main classes
__all__ = ['OrderBook', 'OrderBookSnaps']