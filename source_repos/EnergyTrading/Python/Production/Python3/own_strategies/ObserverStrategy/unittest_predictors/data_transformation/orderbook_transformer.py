"""
OrderBook to Backtest format transformer.
TDD implementation - driven by test requirements.
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Any
from datetime import datetime


class OrderBookMetricsCalculator:
    """
    Calculate OrderBook metrics following OB_attributes algorithms.
    Ported from /Users/martin/Documents/GitHub/EnergyTrading/Python/Strategies/Sparse_momentum/ob_attributes.py
    """
    
    def __init__(self, depth_list: List[float] = [0.0, 0.3, 0.5, 0.9]):
        """
        Initialize metrics calculator.
        
        Args:
            depth_list: Price depths in EUR for volume ratio calculations
        """
        self.depth_list = depth_list
    
    @staticmethod
    def _sparsity_func(order_book_prices: List[float]) -> float:
        """
        Calculate price sparsity using weighted kernel.
        Ported from OB_attributes._sparsity_func()
        
        Args:
            order_book_prices: List of price levels (bid or ask)
            
        Returns:
            Sparsity value between 0-1 (higher = more sparse)
        """
        _MIN_N_ORDERS = 4
        order_book = np.array(order_book_prices)

        # Calculate differences
        diff = np.diff(order_book)

        # Shift the differences to align with the required positions
        if len(diff) < 1:
            return 2.0

        length = len(diff)
        if length < _MIN_N_ORDERS:
            return 2.0

        # Define the manual kernel and normalize (from OB_attributes)
        manual_kernel = np.array([2, 1.5, 1.25, 1, 1])
        kernel_list = manual_kernel / 2

        # Calculate weighted differences
        sum_w_diff = 0
        for i in range(min(4, length)):  # To handle cases where length is less than 5
            sum_w_diff += kernel_list[i] * abs(diff[i])

        return min(round(sum_w_diff, 2), 1)
    
    def calculate_volume_ratio(self, bid_volumes: List[float], ask_volumes: List[float], 
                              bid_prices: List[float], ask_prices: List[float], 
                              best_bid: float, best_ask: float, depth: float) -> float:
        """
        Calculate bid-ask volume ratio at given price depth.
        Ported from OB_attributes.vol_ratio()
        
        Args:
            bid_volumes: List of bid volumes
            ask_volumes: List of ask volumes  
            bid_prices: List of bid prices
            ask_prices: List of ask prices
            best_bid: Best bid price
            best_ask: Best ask price
            depth: Price depth in EUR
            
        Returns:
            Volume ratio: (bid_vol - ask_vol) / (bid_vol + ask_vol)
        """
        # Calculate bid volume within depth
        bid_vol = sum([vol for vol, price in zip(bid_volumes, bid_prices) 
                      if price >= best_bid - depth])
        
        # Calculate ask volume within depth  
        ask_vol = sum([vol for vol, price in zip(ask_volumes, ask_prices)
                      if price <= best_ask + depth])
        
        tot_vol = bid_vol + ask_vol
        if tot_vol == 0:
            return np.nan
        else:
            return (bid_vol - ask_vol) / tot_vol
    
    def calculate_volume_weighted_mid_price(self, bid_volumes: List[float], ask_volumes: List[float],
                                          bid_prices: List[float], ask_prices: List[float],
                                          best_bid: float, best_ask: float, depth: float) -> float:
        """
        Calculate volume-weighted mid price at given depth.
        Ported from OB_attributes.mid_priceW()
        
        Args:
            bid_volumes: List of bid volumes
            ask_volumes: List of ask volumes
            bid_prices: List of bid prices  
            ask_prices: List of ask prices
            best_bid: Best bid price
            best_ask: Best ask price
            depth: Price depth in EUR
            
        Returns:
            Volume-weighted mid price
        """
        # Calculate bid volume within depth
        bid_vol = sum([vol for vol, price in zip(bid_volumes, bid_prices) 
                      if price >= best_bid - depth])
        
        # Calculate ask volume within depth
        ask_vol = sum([vol for vol, price in zip(ask_volumes, ask_prices)
                      if price <= best_ask + depth])
        
        tot_vol = bid_vol + ask_vol
        if bid_vol * ask_vol == 0 or tot_vol == 0:
            return np.nan
        else:
            # Volume-weighted price calculation
            bid_weighted = sum([price * vol for vol, price in zip(bid_volumes, bid_prices)
                               if price >= best_bid - depth])
            ask_weighted = sum([price * vol for vol, price in zip(ask_volumes, ask_prices) 
                               if price <= best_ask + depth])
            
            return (bid_weighted + ask_weighted) / tot_vol


class OrderBookToBacktestTransformer:
    """
    Transform OrderBookSnaps + trades DataFrame to backtest message format.
    
    Following TDD - implementation driven by failing tests.
    """
    
    def __init__(self):
        """Initialize transformer"""
        pass
    
    def transform(self, orderbook_snaps, trades_df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Transform OrderBookSnaps and trades to backtest messages.
        
        Args:
            orderbook_snaps: OrderBookSnaps object with LoB_dict and time_list
            trades_df: DataFrame with trade data
            
        Returns:
            List of backtest messages (order_book and trade_list types)
        """
        messages = []
        
        # Extract primary broker_id from trades data for OrderBook messages
        self.primary_broker_id = str(trades_df['broker_id'].iloc[0]) if len(trades_df) > 0 and 'broker_id' in trades_df.columns else "38"
        
        # Create trade list messages first to get trade timestamps
        trade_list_messages = self._create_trade_list_messages(trades_df)
        messages.extend(trade_list_messages)
        
        # Create order book messages aligned with trades
        order_book_messages = self._create_aligned_order_book_messages(orderbook_snaps, trades_df)
        messages.extend(order_book_messages)
        
        # Sort by timestamp for proper ordering
        # When timestamps are equal, trade messages should come first
        messages.sort(key=lambda msg: (msg['timestamp'], msg['message_type'] != 'trade_list'))
        
        return messages
    
    def _create_aligned_order_book_messages(self, orderbook_snaps, trades_df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Create order book messages aligned with trade timestamps for dynamic state updates"""
        messages = []
        
        # Convert orderbook timestamps to pandas timestamps for easier comparison
        import pandas as pd
        orderbook_times = pd.to_datetime(orderbook_snaps.time_list)
        trade_times = trades_df.index
        
        # print(f"Aligning {len(orderbook_times)} order book snapshots with {len(trade_times)} trades...")
        
        # Track previous snapshot and order IDs to enable proper CANCEL + ADD sequences
        prev_snapshot = None
        prev_order_ids = {'bids': [], 'asks': []}
        
        # For each trade, find the closest order book snapshot that occurs before the trade
        for trade_idx, trade_time in enumerate(trade_times):
            # Find order book snapshots that occur before this trade
            valid_ob_indices = orderbook_times <= trade_time
            
            if valid_ob_indices.any():
                # Get the most recent order book snapshot before this trade
                import numpy as np
                latest_ob_idx = np.where(valid_ob_indices)[0][-1]  # Find last True index
                
                # Get the corresponding snapshot
                snap_idx = latest_ob_idx  # Using the index directly
                orderbook_single = orderbook_snaps.LoB_dict[snap_idx]
                
                # Create order book message slightly before the trade (to ensure proper timing)
                ob_timestamp = trade_time - pd.Timedelta(milliseconds=50)  # 50ms before trade
                
                # Simple approach: Send complete OrderBook snapshot 
                # Focus on getting the basic functionality working first
                snapshot_message = self._create_timestamped_orderbook_message(
                    timestamp=ob_timestamp,
                    trade_idx=trade_idx,
                    orderbook_single=orderbook_single
                )
                messages.append(snapshot_message)
                
                prev_snapshot = orderbook_single
                
                # if trade_idx < 10:  # Debug first 10 trades
                #     print(f"  Trade {trade_idx} at {trade_time} -> OB snapshot {snap_idx} at {orderbook_times[latest_ob_idx]}")
        
        # print(f"Created {len(messages)} aligned order book state transition messages")
        return messages
    
    def _create_state_transition_messages(self, timestamp: datetime, prev_snapshot, current_snapshot, trade_idx: int) -> List[Dict[str, Any]]:
        """Create CANCEL messages for orders that need to be removed between snapshots"""
        cancel_messages = []
        
        # Get current order prices to compare with previous
        current_bid_prices = set(bid.price_val for bid in current_snapshot.bids)
        current_ask_prices = set(ask.price_val for ask in current_snapshot.asks)
        
        # Cancel bid orders that are no longer in current snapshot
        for order_idx, prev_bid in enumerate(prev_snapshot.bids):
            if prev_bid.price_val not in current_bid_prices:
                cancel_message = self._create_cancel_order_message(
                    timestamp=timestamp,
                    order_id=f"BID_{trade_idx-1}_{order_idx}",  # Previous trade's order ID
                    direction="buy"
                )
                cancel_messages.append(cancel_message)
        
        # Cancel ask orders that are no longer in current snapshot
        for order_idx, prev_ask in enumerate(prev_snapshot.asks):
            if prev_ask.price_val not in current_ask_prices:
                cancel_message = self._create_cancel_order_message(
                    timestamp=timestamp,
                    order_id=f"ASK_{trade_idx-1}_{order_idx}",  # Previous trade's order ID
                    direction="sell"
                )
                cancel_messages.append(cancel_message)
        
        return cancel_messages
    
    def _create_complete_clear_messages(self, timestamp: datetime, prev_trade_idx: int) -> List[Dict[str, Any]]:
        """Create CANCEL messages to completely clear previous order book state"""
        clear_messages = []
        
        # Cancel all previous bids (assume up to 10 levels)
        for order_idx in range(10):
            cancel_message = self._create_cancel_order_message(
                timestamp=timestamp,
                order_id=f"BID_trade_{prev_trade_idx}_{order_idx}",
                direction="buy"
            )
            clear_messages.append(cancel_message)
        
        # Cancel all previous asks (assume up to 10 levels)
        for order_idx in range(10):
            cancel_message = self._create_cancel_order_message(
                timestamp=timestamp,
                order_id=f"ASK_trade_{prev_trade_idx}_{order_idx}",
                direction="sell"
            )
            clear_messages.append(cancel_message)
        
        return clear_messages
    
    def _create_cancel_all_orders_message(self, timestamp: datetime, prev_trade_idx: int) -> List[Dict[str, Any]]:
        """Create CANCEL messages to remove all previous orders using exact order IDs"""
        cancel_messages = []
        
        # Generate the same timestamp suffix that was used in the previous snapshot
        prev_ts = timestamp - pd.Timedelta(milliseconds=100)  # Approximate previous timestamp
        prev_ts_suffix = int(prev_ts.timestamp() * 1000) % 1000000
        
        # Cancel all previous bid orders (up to 10 levels to match what we add)
        for order_idx in range(10):
            cancel_message = self._create_cancel_order_message(
                timestamp=timestamp,
                order_id=f"BID_{prev_ts_suffix}_{order_idx}",
                direction="buy"
            )
            cancel_messages.append(cancel_message)
        
        # Cancel all previous ask orders (up to 10 levels to match what we add)
        for order_idx in range(10):
            cancel_message = self._create_cancel_order_message(
                timestamp=timestamp,
                order_id=f"ASK_{prev_ts_suffix}_{order_idx}",
                direction="sell"
            )
            cancel_messages.append(cancel_message)
        
        return cancel_messages
    
    def _create_cancel_previous_orders(self, timestamp: datetime, prev_order_ids: dict) -> List[Dict[str, Any]]:
        """Create CANCEL messages for specific previous order IDs"""
        cancel_messages = []
        
        # Cancel all previous bid orders
        for order_id in prev_order_ids['bids']:
            cancel_message = self._create_cancel_order_message(
                timestamp=timestamp,
                order_id=order_id,
                direction="buy"
            )
            cancel_messages.append(cancel_message)
        
        # Cancel all previous ask orders
        for order_id in prev_order_ids['asks']:
            cancel_message = self._create_cancel_order_message(
                timestamp=timestamp,
                order_id=order_id,
                direction="sell"
            )
            cancel_messages.append(cancel_message)
        
        return cancel_messages
    
    def _create_timestamped_orderbook_message_with_tracking(self, timestamp: datetime, trade_idx: int, orderbook_single) -> tuple:
        """Create order book message with timestamp-based unique IDs and return order ID tracking"""
        data_entries = []
        current_order_ids = {'bids': [], 'asks': []}
        
        # Generate unique timestamp suffix for order IDs
        ts_suffix = int(timestamp.timestamp() * 1000) % 1000000  # Use microseconds for uniqueness
        
        # Add all bids from the snapshot with unique IDs
        for order_idx, bid_order in enumerate(orderbook_single.bids):
            order_id = f"BID_{ts_suffix}_{order_idx}"
            current_order_ids['bids'].append(order_id)
            
            order_data = {
                "counter_party_ok": False,
                "system_rank": "487290945",
                "broker_id": self.primary_broker_id,
                "txt": False,
                "user_id": "0",
                "old_engine_id": "1",
                "state": "ACTI",
                "inst_specifier": [
                    {
                        "instrument_id": "10100482",
                        "first_item_id": "20",
                        "term_format_id": None,
                        "second_item_id": "0",
                        "sequence_span": "Single",
                        "first_sequence_id": "10000106_20"
                    }
                ],
                "type": "O",
                "old_broker_id": self.primary_broker_id,
                "direction": "buy",
                "initial_order_id": order_id,
                "engine_id": "1",
                "order_id": order_id,
                "timestamp": timestamp,
                "price": bid_order.price_val,
                "validity_date": None,
                "terms": [],
                "validity_restriction": "NON",
                "account": "0",
                "is_tradable": True,
                "execution_restriction": "NON",
                "implied": False,
                "action": "ADD",
                "traded": False,
                "quantity": bid_order.volume_val,
                "system_rank": 1,
                "counter_party_ok": True
            }
            data_entries.append(order_data)
        
        # Add all asks from the snapshot with unique IDs
        for order_idx, ask_order in enumerate(orderbook_single.asks):
            order_id = f"ASK_{ts_suffix}_{order_idx}"
            current_order_ids['asks'].append(order_id)
            
            order_data = {
                "counter_party_ok": False,
                "system_rank": "487290945",
                "broker_id": self.primary_broker_id,
                "txt": False,
                "user_id": "0",
                "old_engine_id": "1",
                "state": "ACTI",
                "inst_specifier": [
                    {
                        "instrument_id": "10100482",
                        "first_item_id": "20",
                        "term_format_id": None,
                        "second_item_id": "0",
                        "sequence_span": "Single",
                        "first_sequence_id": "10000106_20"
                    }
                ],
                "type": "O",
                "old_broker_id": self.primary_broker_id,
                "direction": "sell",
                "initial_order_id": order_id,
                "engine_id": "1",
                "order_id": order_id,
                "timestamp": timestamp,
                "price": ask_order.price_val,
                "validity_date": None,
                "terms": [],
                "validity_restriction": "NON",
                "account": "0",
                "is_tradable": True,
                "execution_restriction": "NON",
                "implied": False,
                "action": "ADD",
                "traded": False,
                "quantity": ask_order.volume_val,
                "system_rank": 1,
                "counter_party_ok": True
            }
            data_entries.append(order_data)
        
        message = {
            "timestamp": timestamp,
            "exchange": "TRAYPORT",
            "message_type": "order_book",
            "data": data_entries
        }
        
        return message, current_order_ids
    
    def _create_cancel_all_message(self, timestamp: datetime) -> Dict[str, Any]:
        """Create a CANCEL ALL message to clear OrderBook state"""
        return {
            "timestamp": timestamp,
            "exchange": "TRAYPORT",
            "message_type": "delete_all",
            "data": []
        }
    
    def _create_unique_orderbook_message(self, timestamp: datetime, trade_idx: int, orderbook_single) -> Dict[str, Any]:
        """Create OrderBook message with unique order IDs for each snapshot"""
        all_orders = []
        
        # Process bid orders with unique IDs
        for order_idx, bid_order in enumerate(orderbook_single.bids):
            order_id = f"BID_{trade_idx}_{order_idx}"
            bid_message = {
                "quantity": bid_order.volume_val,
                "order_id": order_id,
                "user_id": "0",
                "price": bid_order.price_val,
                "state": "ACTI",
                "inst_specifier": [
                    {
                        "instrument_id": "10100482",
                        "first_item_id": "20",
                        "term_format_id": None,
                        "second_item_id": "0",
                        "sequence_span": "Single",
                        "first_sequence_id": "10000106_20"
                    }
                ],
                "type": "O",
                "old_broker_id": self.primary_broker_id,
                "direction": "buy",
                "initial_order_id": order_id,
                "engine_id": "1",
                "timestamp": timestamp,
                "validity_date": None,
                "terms": [],
                "validity_restriction": "NON",
                "account": "0",
                "is_tradable": True,
                "execution_restriction": "NON",
                "implied": False,
                "action": "ADD",
                "traded": False,
                "broker_id": self.primary_broker_id,
                "system_rank": 1
            }
            all_orders.append(bid_message)
        
        # Process ask orders with unique IDs
        for order_idx, ask_order in enumerate(orderbook_single.asks):
            order_id = f"ASK_{trade_idx}_{order_idx}"
            ask_message = {
                "quantity": ask_order.volume_val,
                "order_id": order_id,
                "user_id": "0",
                "price": ask_order.price_val,
                "state": "ACTI",
                "inst_specifier": [
                    {
                        "instrument_id": "10100482",
                        "first_item_id": "20",
                        "term_format_id": None,
                        "second_item_id": "0",
                        "sequence_span": "Single",
                        "first_sequence_id": "10000106_20"
                    }
                ],
                "type": "O",
                "old_broker_id": self.primary_broker_id,
                "direction": "sell",
                "initial_order_id": order_id,
                "engine_id": "1",
                "timestamp": timestamp,
                "validity_date": None,
                "terms": [],
                "validity_restriction": "NON",
                "account": "0",
                "is_tradable": True,
                "execution_restriction": "NON",
                "implied": False,
                "action": "ADD",
                "traded": False,
                "broker_id": self.primary_broker_id,
                "system_rank": 1
            }
            all_orders.append(ask_message)
        
        return {
            "timestamp": timestamp,
            "exchange": "TRAYPORT",
            "message_type": "order_book",
            "data": all_orders
        }
    
    def _create_timestamped_orderbook_message(self, timestamp: datetime, trade_idx: int, orderbook_single) -> Dict[str, Any]:
        """Create order book message with timestamp-based unique IDs"""
        data_entries = []
        
        # Generate unique timestamp suffix for order IDs
        ts_suffix = int(timestamp.timestamp() * 1000) % 1000000  # Use microseconds for uniqueness
        
        # Add all bids from the snapshot with unique IDs
        for order_idx, bid_order in enumerate(orderbook_single.bids):
            order_data = {
                "counter_party_ok": False,
                "system_rank": "487290945",
                "broker_id": self.primary_broker_id,
                "txt": False,
                "user_id": "0",
                "old_engine_id": "1",
                "state": "ACTI",
                "inst_specifier": [
                    {
                        "instrument_id": "10100482",
                        "first_item_id": "20",
                        "term_format_id": None,
                        "second_item_id": "0",
                        "sequence_span": "Single",
                        "first_sequence_id": "10000106_20"
                    }
                ],
                "type": "O",
                "old_broker_id": self.primary_broker_id,
                "direction": "buy",
                "initial_order_id": f"BID_{ts_suffix}_{order_idx}",  # Unique timestamp-based ID
                "engine_id": "1",
                "order_id": f"BID_{ts_suffix}_{order_idx}",  # Unique timestamp-based ID
                "timestamp": timestamp,
                "price": bid_order.price_val,
                "validity_date": None,
                "terms": [],
                "validity_restriction": "NON",
                "account": "0",
                "is_tradable": True,
                "execution_restriction": "NON",
                "implied": False,
                "action": "ADD",
                "traded": False,
                "quantity": bid_order.volume_val,
                "system_rank": 1,
                "counter_party_ok": True
            }
            data_entries.append(order_data)
        
        # Add all asks from the snapshot with unique IDs
        for order_idx, ask_order in enumerate(orderbook_single.asks):
            order_data = {
                "counter_party_ok": False,
                "system_rank": "487290945",
                "broker_id": self.primary_broker_id,
                "txt": False,
                "user_id": "0",
                "old_engine_id": "1",
                "state": "ACTI",
                "inst_specifier": [
                    {
                        "instrument_id": "10100482",
                        "first_item_id": "20",
                        "term_format_id": None,
                        "second_item_id": "0",
                        "sequence_span": "Single",
                        "first_sequence_id": "10000106_20"
                    }
                ],
                "type": "O",
                "old_broker_id": self.primary_broker_id,
                "direction": "sell",
                "initial_order_id": f"ASK_{ts_suffix}_{order_idx}",  # Unique timestamp-based ID
                "engine_id": "1",
                "order_id": f"ASK_{ts_suffix}_{order_idx}",  # Unique timestamp-based ID
                "timestamp": timestamp,
                "price": ask_order.price_val,
                "validity_date": None,
                "terms": [],
                "validity_restriction": "NON",
                "account": "0",
                "is_tradable": True,
                "execution_restriction": "NON",
                "implied": False,
                "action": "ADD",
                "traded": False,
                "quantity": ask_order.volume_val,
                "system_rank": 1,
                "counter_party_ok": True
            }
            data_entries.append(order_data)
        
        return {
            "timestamp": timestamp,
            "exchange": "TRAYPORT",
            "message_type": "order_book",
            "data": data_entries
        }
    
    def _create_clear_orderbook_messages(self, timestamp: datetime, snap_idx: int) -> List[Dict[str, Any]]:
        """Create CANCEL messages to clear previous order book state"""
        # For simplicity, we'll track order IDs to cancel
        # In a real implementation, this would track active orders
        clear_messages = []
        
        # Cancel all previous bids and asks by creating CANCEL messages for known order patterns
        # This assumes we know the order ID pattern from previous snapshots
        prev_snap_idx = snap_idx - 1
        
        # Cancel previous bid orders  
        for order_idx in range(10):  # Match the number we add
            cancel_message = self._create_cancel_order_message(
                timestamp=timestamp,
                order_id=f"BID_{prev_snap_idx}_{order_idx}",
                direction="buy"
            )
            clear_messages.append(cancel_message)
        
        # Cancel previous ask orders
        for order_idx in range(10):  # Match the number we add  
            cancel_message = self._create_cancel_order_message(
                timestamp=timestamp,
                order_id=f"ASK_{prev_snap_idx}_{order_idx}",
                direction="sell"
            )
            clear_messages.append(cancel_message)
        
        return clear_messages
    
    def _create_cancel_order_message(self, timestamp: datetime, order_id: str, direction: str) -> Dict[str, Any]:
        """Create a CANCEL message for an order"""
        return {
            "timestamp": timestamp,
            "exchange": "TRAYPORT",
            "message_type": "order_book",
            "data": [
                {
                    "counter_party_ok": False,
                    "system_rank": "487290945",
                    "broker_id": self.primary_broker_id,
                    "txt": False,
                    "user_id": "0",
                    "old_engine_id": "1",
                    "state": "ACTI",
                    "inst_specifier": [
                        {
                            "instrument_id": "10100482",
                            "first_item_id": "20",
                            "term_format_id": None,
                            "second_item_id": "0",
                            "sequence_span": "Single",
                            "first_sequence_id": "10000106_20"
                        }
                    ],
                    "type": "O",
                    "old_broker_id": self.primary_broker_id,
                    "direction": direction,
                    "initial_order_id": order_id,
                    "engine_id": "1",
                    "order_id": order_id,
                    "timestamp": timestamp,
                    "price": 0.0,  # Price not relevant for CANCEL
                    "validity_date": None,
                    "terms": [],
                    "validity_restriction": "NON",
                    "account": "0",
                    "is_tradable": True,
                    "execution_restriction": "NON",
                    "implied": False,
                    "action": "CANCEL",  # This is the key difference
                    "traded": False,
                    "quantity": 0  # Quantity not relevant for CANCEL
                }
            ]
        }
    
    def _create_snapshot_add_messages(self, timestamp: datetime, snap_idx: int, orderbook_single) -> List[Dict[str, Any]]:
        """Create ADD messages for current snapshot orders"""
        messages = []
        
        # Process bids from the snapshot
        for order_idx, bid_order in enumerate(orderbook_single.bids):  # All levels
            order_message = self._create_add_order_message(
                timestamp=timestamp,
                broker_id="38",
                instrument_id="10100482",
                item_id="20",
                term_format_id=None,
                sequence_id="10000106",
                direction="buy",
                order_id=f"BID_{snap_idx}_{order_idx}",
                price=bid_order.price_val,
                quantity=bid_order.volume_val
            )
            messages.append(order_message)
        
        # Process asks from the snapshot
        for order_idx, ask_order in enumerate(orderbook_single.asks):  # All levels
            order_message = self._create_add_order_message(
                timestamp=timestamp,
                broker_id="38",
                instrument_id="10100482",
                item_id="20",
                term_format_id=None,
                sequence_id="10000106",
                direction="sell",
                order_id=f"ASK_{snap_idx}_{order_idx}",
                price=ask_order.price_val,
                quantity=ask_order.volume_val
            )
            messages.append(order_message)
        
        return messages
    
    def _create_orderbook_snapshot_message(self, timestamp: datetime, snap_idx: int, orderbook_single) -> Dict[str, Any]:
        """Create a single message representing complete order book snapshot"""
        data_entries = []
        
        # Add all bids from the snapshot
        for order_idx, bid_order in enumerate(orderbook_single.bids):  # All levels for better depth
            order_data = {
                "counter_party_ok": False,
                "system_rank": "487290945",
                "broker_id": self.primary_broker_id,
                "txt": False,
                "user_id": "0",
                "old_engine_id": "1",
                "state": "ACTI",
                "inst_specifier": [
                    {
                        "instrument_id": "10100482",
                        "first_item_id": "20",
                        "term_format_id": None,
                        "second_item_id": "0",
                        "sequence_span": "Single",
                        "first_sequence_id": "10000106_20"
                    }
                ],
                "type": "O",
                "old_broker_id": self.primary_broker_id,
                "direction": "buy",
                "initial_order_id": f"BID_{snap_idx}_{order_idx}",
                "engine_id": "1",
                "order_id": f"BID_{snap_idx}_{order_idx}",
                "timestamp": timestamp,
                "price": bid_order.price_val,
                "validity_date": None,
                "terms": [],
                "validity_restriction": "NON",
                "account": "0",
                "is_tradable": True,
                "execution_restriction": "NON",
                "implied": False,
                "action": "ADD",
                "traded": False,
                "quantity": bid_order.volume_val,
                "system_rank": 1,
                "counter_party_ok": True,
                "_snapshot_id": snap_idx  # Track which snapshot this belongs to
            }
            data_entries.append(order_data)
        
        # Add all asks from the snapshot  
        for order_idx, ask_order in enumerate(orderbook_single.asks):  # All levels for better depth
            order_data = {
                "counter_party_ok": False,
                "system_rank": "487290945",
                "broker_id": self.primary_broker_id,
                "txt": False,
                "user_id": "0",
                "old_engine_id": "1",
                "state": "ACTI",
                "inst_specifier": [
                    {
                        "instrument_id": "10100482",
                        "first_item_id": "20",
                        "term_format_id": None,
                        "second_item_id": "0",
                        "sequence_span": "Single",
                        "first_sequence_id": "10000106_20"
                    }
                ],
                "type": "O",
                "old_broker_id": self.primary_broker_id,
                "direction": "sell",
                "initial_order_id": f"ASK_{snap_idx}_{order_idx}",
                "engine_id": "1",
                "order_id": f"ASK_{snap_idx}_{order_idx}",
                "timestamp": timestamp,
                "price": ask_order.price_val,
                "validity_date": None,
                "terms": [],
                "validity_restriction": "NON",
                "account": "0",
                "is_tradable": True,
                "execution_restriction": "NON",
                "implied": False,
                "action": "ADD",
                "traded": False,
                "quantity": ask_order.volume_val,
                "system_rank": 1,
                "counter_party_ok": True,
                "_snapshot_id": snap_idx  # Track which snapshot this belongs to
            }
            data_entries.append(order_data)
        
        return {
            "timestamp": timestamp,
            "exchange": "TRAYPORT",
            "message_type": "order_book",
            "data": data_entries,
            "_snapshot_id": snap_idx,  # Track which snapshot this represents
            "_is_snapshot": True  # Mark as complete snapshot
        }
    
    def _create_trade_list_messages(self, trades_df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Create trade_list type messages from trades DataFrame"""
        messages = []
        
        for idx, row in trades_df.iterrows():
            # Use actual broker_id from trade data instead of hardcoding
            actual_broker_id = str(row.get('broker_id', "38"))  # Fallback to "38" if not found
            
            trade_message = self._create_add_trade_message(
                timestamp=idx,
                broker_id=actual_broker_id,  # Use actual broker_id from data
                instrument_id="10100482",  # Always use working strategy constants
                item_id="20",  # Always use working strategy constants
                term_format_id=None,  # Match real backtest format
                sequence_id="10000106",  # Always use working strategy constants
                direction='buy' if row['action'] == 1 else 'sell',
                trade_id=row['tradeid'],
                price=row['price'],
                quantity=row['volume']
            )
            messages.append(trade_message)
        
        return messages
    
    def _create_add_order_message(self, timestamp: datetime, broker_id: str, 
                                 instrument_id: str, item_id: str, term_format_id: int,
                                 sequence_id: str, direction: str, order_id: str,
                                 price: float, quantity: int) -> Dict[str, Any]:
        """Create order_book message matching backtest format"""
        return {
            "timestamp": timestamp,
            "exchange": "TRAYPORT",
            "message_type": "order_book",
            "data": [
                {
                    "counter_party_ok": False,
                    "system_rank": "487290945",
                    "broker_id": broker_id,
                    "txt": False,
                    "user_id": "0",
                    "old_engine_id": "1",
                    "state": "ACTI",
                    "inst_specifier": [
                        {
                            "instrument_id": instrument_id,
                            "first_item_id": item_id,
                            "term_format_id": term_format_id,
                            "second_item_id": "0",
                            "sequence_span": "Single",
                            "first_sequence_id": sequence_id
                        }
                    ],
                    "type": "O",
                    "old_broker_id": broker_id,
                    "direction": direction,
                    "initial_order_id": order_id,
                    "engine_id": "1",
                    "order_id": order_id,
                    "timestamp": timestamp,
                    "price": price,
                    "validity_date": None,
                    "terms": [],
                    "validity_restriction": "NON",
                    "account": "0",
                    "is_tradable": True,
                    "execution_restriction": "NON",
                    "implied": False,
                    "action": "ADD",
                    "traded": False,
                    "quantity": quantity
                }
            ]
        }
    
    def _create_add_trade_message(self, timestamp: datetime, broker_id: str,
                                 instrument_id: str, item_id: str, term_format_id: int, 
                                 sequence_id: str, direction: str, trade_id: str,
                                 price: float, quantity: int) -> Dict[str, Any]:
        """Create trade_list message matching backtest format"""
        return {
            "timestamp": timestamp,
            "exchange": "TRAYPORT",
            "message_type": "trade_list",
            "data": [
                {
                    "quantity": quantity,
                    "price": price,
                    "initiator_user_id": "0",
                    "initiator_broker_id": broker_id,
                    "initiator_company_id": "0",
                    "initiator_company": "",
                    "initiator_action": "buy" if direction == "sell" else "sell",
                    "aggressor_user_id": "0",
                    "aggressor_broker_id": broker_id,
                    "aggressor_company_id": "0",
                    "aggressor_company": "",
                    "aggressor_action": direction,
                    "trade_id": trade_id,
                    "timestamp": timestamp,
                    "execution_time": timestamp,
                    "buy_delivery_area": instrument_id,
                    "sell_delivery_area": instrument_id,
                    "state": "ACTI",
                    "term": [],
                    "order_id": trade_id,
                    "txt": None,
                    "annotations": [],
                    "inst_specifier": [
                        {
                            "instrument_id": instrument_id,
                            "first_item_id": item_id,
                            "term_format_id": term_format_id,
                            "second_item_id": "0",
                            "sequence_span": "Single",
                            "first_sequence_id": sequence_id
                        }
                    ]
                }
            ]
        }