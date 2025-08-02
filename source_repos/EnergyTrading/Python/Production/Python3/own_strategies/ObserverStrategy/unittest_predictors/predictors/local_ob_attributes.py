"""
Local implementation of OB_attributes for testing purposes.

This module contains the necessary functions and classes for processing
OrderBook data in tests, copied from external projects to ensure
the strategy is self-contained.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional


class LocalOB_attributes:
    """
    Local implementation of OB_attributes for testing.
    
    This class processes OrderBook data from pickle files and calculates
    the same metrics as the production OB_attributes class.
    """
    
    def __init__(self, orderbook_data):
        """
        Initialize with OrderBook data from pickle file.
        
        Args:
            orderbook_data: OrderBook object from pickle file
        """
        self.orderbook_data = orderbook_data
        self.bids = []
        self.asks = []
        self._extract_orders()
    
    def _extract_orders(self):
        """Extract bid and ask orders from OrderBook data"""
        # Handle different OrderBook data structures
        if hasattr(self.orderbook_data, 'bids') and hasattr(self.orderbook_data, 'asks'):
            # Direct bids/asks attributes - use price_val for real OrderBook objects
            self.bids = sorted(self.orderbook_data.bids, reverse=True, key=lambda x: getattr(x, 'price_val', getattr(x, 'price', 0)))
            self.asks = sorted(self.orderbook_data.asks, reverse=False, key=lambda x: getattr(x, 'price_val', getattr(x, 'price', 0)))
        elif hasattr(self.orderbook_data, 'LoB_dict'):
            # OrderBookSnaps structure
            self._extract_from_lob_dict()
        else:
            # Try to extract from any dict-like structure
            self._extract_from_dict_structure()
    
    def _extract_from_lob_dict(self):
        """Extract orders from LoB_dict structure"""
        # This handles OrderBookSnaps with LoB_dict
        try:
            if hasattr(self.orderbook_data, 'LoB_dict'):
                # Find first timestamp or key
                if self.orderbook_data.LoB_dict:
                    first_key = next(iter(self.orderbook_data.LoB_dict))
                    orderbook_single = self.orderbook_data.LoB_dict[first_key]
                    if hasattr(orderbook_single, 'bids') and hasattr(orderbook_single, 'asks'):
                        self.bids = sorted(orderbook_single.bids, reverse=True, key=lambda x: getattr(x, 'price_val', getattr(x, 'price', 0)))
                        self.asks = sorted(orderbook_single.asks, reverse=False, key=lambda x: getattr(x, 'price_val', getattr(x, 'price', 0)))
        except Exception:
            pass
    
    def _extract_from_dict_structure(self):
        """Extract orders from generic dict structure"""
        # Handle any other dict-like structures
        try:
            # Try to find bids and asks in the data
            if isinstance(self.orderbook_data, dict):
                if 'bids' in self.orderbook_data and 'asks' in self.orderbook_data:
                    self.bids = sorted(self.orderbook_data['bids'], reverse=True, key=lambda x: getattr(x, 'price_val', getattr(x, 'price', 0)))
                    self.asks = sorted(self.orderbook_data['asks'], reverse=False, key=lambda x: getattr(x, 'price_val', getattr(x, 'price', 0)))
        except Exception:
            pass
    
    def _get_price(self, order):
        """Get price from order, using real OrderBook attributes"""
        return getattr(order, 'price_val', getattr(order, 'price', 0))
    
    def _get_quantity(self, order):
        """Get quantity from order, using real OrderBook attributes"""
        return getattr(order, 'volume_val', getattr(order, 'volume', 0))
    
    def mid_price(self):
        """Calculate mid price"""
        return 0.5 * (self.bid_price() + self.ask_price())
    
    def ba_spread(self):
        """Calculate bid-ask spread"""
        return self.ask_price() - self.bid_price()
    
    def bid_price(self):
        """Get best bid price"""
        try:
            return self._get_price(self.bids[0])
        except (IndexError, AttributeError):
            return np.nan
    
    def ask_price(self):
        """Get best ask price"""
        try:
            return self._get_price(self.asks[0])
        except (IndexError, AttributeError):
            return np.nan
    
    def bid_volume(self):
        """Get best bid volume"""
        try:
            return self._get_quantity(self.bids[0])
        except (IndexError, AttributeError):
            return np.nan
    
    def ask_volume(self):
        """Get best ask volume"""
        try:
            return self._get_quantity(self.asks[0])
        except (IndexError, AttributeError):
            return np.nan
    
    def bid_volumeV(self, p_depth):
        """Calculate bid volume within price depth"""
        b_price = self.bid_price()
        if np.isnan(b_price):
            return 0
        return sum([self._get_quantity(x) for x in self.bids if self._get_price(x) >= b_price - p_depth])
    
    def ask_volumeV(self, p_depth):
        """Calculate ask volume within price depth"""
        a_price = self.ask_price()
        if np.isnan(a_price):
            return 0
        return sum([self._get_quantity(x) for x in self.asks if self._get_price(x) <= a_price + p_depth])
    
    def mid_priceW(self, p_depth):
        """Calculate volume-weighted mid price within depth"""
        b_price = self.bid_price()
        a_price = self.ask_price()
        
        if np.isnan(b_price) or np.isnan(a_price):
            return np.nan
        
        bid_vol = self.bid_volumeV(p_depth)
        ask_vol = self.ask_volumeV(p_depth)
        tot_vol = bid_vol + ask_vol
        
        if bid_vol * ask_vol == 0:
            return np.nan
        else:
            return (sum([self._get_price(x) * self._get_quantity(x) for x in self.bids
                         if self._get_price(x) >= b_price - p_depth]) +
                    sum([self._get_price(x) * self._get_quantity(x) for x in self.asks
                         if self._get_price(x) <= a_price + p_depth])) / tot_vol
    
    def vol_ratio(self, p_depth):
        """Calculate volume ratio within price depth"""
        bid_vol = self.bid_volumeV(p_depth)
        ask_vol = self.ask_volumeV(p_depth)
        tot_vol = bid_vol + ask_vol
        
        if tot_vol == 0:
            return np.nan
        else:
            return (bid_vol - ask_vol) / tot_vol
    
    def bid_broker(self):
        """Get best bid broker/venue"""
        try:
            # Use venue attribute as broker_id (venue is the broker identifier in OrderBook data)
            return getattr(self.bids[0], 'venue', 1)
        except (IndexError, AttributeError):
            return 1  # Default broker ID

    def ask_broker(self):
        """Get best ask broker/venue"""
        try:
            # Use venue attribute as broker_id (venue is the broker identifier in OrderBook data)
            return getattr(self.asks[0], 'venue', 1)
        except (IndexError, AttributeError):
            return 1  # Default broker ID


class LocalTR_attributes:
    """
    Local implementation of TR_attributes for testing.
    
    This class processes trade data and calculates trade-related metrics.
    """
    
    def __init__(self, attr_list):
        """
        Initialize with attribute list.
        
        Args:
            attr_list: List of attributes to calculate
        """
        self.attr_list = attr_list
    
    def prepare_reg_data(self, trades_df, timestamp_index, additional_params, period_list):
        """
        Prepare trade data for regression analysis.
        
        Args:
            trades_df: DataFrame with trade data
            timestamp_index: Timestamp index for alignment
            additional_params: Additional parameters (unused in basic implementation)
            period_list: List of periods for calculations
            
        Returns:
            DataFrame with processed trade data
        """
        # Basic implementation - align trades with timestamp index
        if len(trades_df) == 0:
            # Return empty DataFrame with required columns
            result = pd.DataFrame(index=timestamp_index)
            for attr in self.attr_list:
                result[attr] = np.nan
            return result
        
        # Align trades with timestamp index
        trades_aligned = trades_df.reindex(timestamp_index, method='ffill')
        
        # Calculate basic trade attributes
        result = pd.DataFrame(index=timestamp_index)
        
        # Add trade price
        if 'trd_price' in self.attr_list:
            result['trd_price'] = trades_aligned.get('trd_price', trades_aligned.get('price', np.nan))
        
        # Add other trade attributes as needed
        for attr in self.attr_list:
            if attr not in result.columns:
                result[attr] = np.nan
        
        return result


def prepare_ob_data_basic(orderbook_dict, depth_list):
    """
    Prepare basic OrderBook data for analysis.
    
    This function processes OrderBook data and calculates various metrics
    at different depth levels.
    
    Args:
        orderbook_dict: Dictionary containing OrderBook data
        depth_list: List of depths to calculate metrics for
        
    Returns:
        Dictionary with calculated metrics
    """
    result = {}
    
    # Lists to store calculated values
    timestamps = []
    b_prices = []
    a_prices = []
    ba_spreads = []
    mid_prices = []
    bid_volumes = []
    ask_volumes = []
    
    # Volume ratio calculations for each depth
    volrat_data = {f'ba_volrat_{int(d*100):02d}': [] for d in depth_list}
    
    # Price sparsity calculations
    b_price_sparsity = []
    a_price_sparsity = []
    
    # Process each timestamp in the orderbook
    for timestamp, orderbook in orderbook_dict.LoB_dict.items():
        ob_attr = LocalOB_attributes(orderbook)
        
        timestamps.append(timestamp)
        b_prices.append(ob_attr.bid_price())
        a_prices.append(ob_attr.ask_price())
        ba_spreads.append(ob_attr.ba_spread())
        mid_prices.append(ob_attr.mid_price())
        bid_volumes.append(ob_attr.bid_volume())
        ask_volumes.append(ob_attr.ask_volume())
        
        # Calculate volume ratios for each depth
        for depth in depth_list:
            depth_key = f'ba_volrat_{int(depth*100):02d}'
            volrat_data[depth_key].append(ob_attr.vol_ratio(depth))
        
        # Calculate price sparsity (simplified implementation)
        bids = [ob_attr._get_price(x) for x in ob_attr.bids]
        asks = [ob_attr._get_price(x) for x in ob_attr.asks]
        
        b_price_sparsity.append(_calculate_sparsity(bids))
        a_price_sparsity.append(_calculate_sparsity(asks))
    
    # Store results
    result['timestamp'] = timestamps
    result['b_price'] = b_prices
    result['a_price'] = a_prices
    result['ba_spread'] = ba_spreads
    result['mid_price'] = mid_prices
    result['bid_volume'] = bid_volumes
    result['ask_volume'] = ask_volumes
    result['b_price_sparsity'] = b_price_sparsity
    result['a_price_sparsity'] = a_price_sparsity
    
    # Add volume ratio data
    result.update(volrat_data)
    
    return result


def _calculate_sparsity(price_list):
    """
    Calculate price sparsity using the same algorithm as production.
    
    Args:
        price_list: List of prices
        
    Returns:
        Sparsity value
    """
    _MIN_N_ORDERS = 4
    
    if len(price_list) < _MIN_N_ORDERS:
        return 2.0
    
    order_book = np.array(price_list)
    
    # Calculate differences
    diff = np.diff(order_book)
    
    if len(diff) < 1:
        return 2.0
    
    length = len(diff)
    if length < _MIN_N_ORDERS:
        return 2.0
    
    # Define the manual kernel and normalize
    manual_kernel = np.array([2, 1.5, 1.25, 1, 1])
    kernel_list = manual_kernel / 2
    
    # Calculate weighted differences
    sum_w_diff = 0
    for i in range(min(4, length)):
        sum_w_diff += kernel_list[i] * abs(diff[i])
    
    return min(round(sum_w_diff, 2), 1)


def unify_time_pd(ob_data, timestamp_index):
    """
    Unify time series data with timestamp index.
    
    Args:
        ob_data: OrderBook data DataFrame
        timestamp_index: Target timestamp index
        
    Returns:
        Unified DataFrame
    """
    # Simple implementation - align data with timestamp index
    return ob_data.reindex(timestamp_index, method='ffill')


def attr_list():
    """
    Return list of standard attributes for OB_attributes.
    
    Returns:
        List of attribute names
    """
    return [
        'b_price', 'a_price', 'ba_spread', 'mid_price',
        'bid_volume', 'ask_volume', 'b_price_sparsity', 'a_price_sparsity',
        'ba_volrat_00', 'ba_volrat_30', 'ba_volrat_50', 'ba_volrat_90'
    ]