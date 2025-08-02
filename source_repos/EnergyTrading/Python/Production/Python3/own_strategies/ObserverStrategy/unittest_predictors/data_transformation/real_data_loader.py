"""
Real market data loader using local implementations and sample data.

This module loads sample data from pickle files and calculates
metrics using local implementations without external dependencies.
"""

import os
import pickle
import pandas as pd
import numpy as np
from datetime import datetime, time, timedelta
from typing import Tuple, Dict, Any, Optional

# Import local implementations
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'predictors'))

# Import OrderBook stub classes for unpickling (avoid matplotlib)
try:
    # Try to import from local predictors directory
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'predictors'))
    import OrderBook
except ImportError:
    # Create minimal stub if not available
    class Order:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
    
    class OrderBookSingle:
        def __init__(self, **kwargs):
            self.bids = []
            self.asks = []
            for k, v in kwargs.items():
                setattr(self, k, v)
    
    class OrderBookSnaps:
        def __init__(self, **kwargs):
            self.LoB_dict = {}
            self.time_list = []
            for k, v in kwargs.items():
                setattr(self, k, v)
    
    class OrderBook:
        Order = Order
        OrderBookSingle = OrderBookSingle
        OrderBookSnaps = OrderBookSnaps
    
from local_ob_attributes import LocalOB_attributes, LocalTR_attributes, prepare_ob_data_basic, unify_time_pd


class RealDataLoader:
    """
    Load real market data from sample pickle files.
    
    This class processes sample data using local implementations
    to ensure the strategy is self-contained and testable.
    """
    
    def __init__(self, instrument: str = 'dey1', verbose: bool = True):
        """
        Initialize real data loader.
        
        Args:
            instrument: Market instrument (for compatibility)
            verbose: Enable verbose logging
        """
        self.instrument = instrument
        self.verbose = verbose
        
        # Configuration
        self.depth_list = [0.0, 0.3, 0.5, 0.9]
        self.period_list = [5, 20]
        
        # Initialize attributes calculators
        self.trAtt = LocalTR_attributes(['trd_price', 'trd_gap', 'trd_side', 'last_trade_margin'])
        
        # Paths to sample data
        self.data_dir = os.path.dirname(__file__)
        self.orderbook_file = os.path.join(self.data_dir, 'prod_unittest_ob_snaps.pkl.sample')
        self.trades_file = os.path.join(self.data_dir, 'prod_unittest_trades.pkl.sample')
    
    def load_single_day_data(self, date_str: str = '2025-04-04') -> Tuple[Dict, pd.DataFrame, Dict[str, Any]]:
        """
        Load sample data and calculate expected metrics.
        
        Args:
            date_str: Date string (for compatibility - not used with sample data)
            
        Returns:
            Tuple of (orderbook_dict, trades_df, expected_metrics_dict)
            
        Raises:
            Exception: If sample data cannot be loaded
        """
        if self.verbose:
            print(f"Loading sample data for {self.instrument} (date: {date_str})")
        
        # Load sample data
        orderbook_dict = self._load_orderbook_sample()
        trades_df = self._load_trades_sample()
        
        # Calculate expected metrics using local implementations
        expected_metrics = self._calculate_expected_metrics(orderbook_dict, trades_df)
        
        if self.verbose:
            print(f"✅ Loaded sample data successfully:")
            print(f"  OrderBook snapshots: {len(orderbook_dict.LoB_dict)}")
            print(f"  Trades: {len(trades_df)}")
            print(f"  Expected metrics: {len(expected_metrics)} calculated")
        
        return orderbook_dict, trades_df, expected_metrics
    
    def _load_orderbook_sample(self) -> Dict:
        """Load OrderBook sample data from pickle file"""
        if not os.path.exists(self.orderbook_file):
            raise FileNotFoundError(f"OrderBook sample file not found: {self.orderbook_file}")
        

        orderbook_data =  pickle.load(open(self.orderbook_file, 'rb'))
        
        if self.verbose:
            print(f"Loaded OrderBook sample with {len(orderbook_data.LoB_dict)} snapshots")
        
        return orderbook_data
    
    def _load_trades_sample(self) -> pd.DataFrame:
        """Load trades sample data from pickle file"""
        if not os.path.exists(self.trades_file):
            raise FileNotFoundError(f"Trades sample file not found: {self.trades_file}")
        
        with open(self.trades_file, 'rb') as f:
            trades_data = pickle.load(f)
        
        if self.verbose:
            print(f"Loaded trades sample with {len(trades_data)} records")
        
        return trades_data
    
    def _calculate_expected_metrics(self, orderbook_dict: Dict, trades_df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate expected metrics using local implementations"""
        if self.verbose:
            print(f"Calculating expected metrics using local implementations...")
        
        # Process OrderBook data using local implementation
        ob_data = prepare_ob_data_basic(orderbook_dict, self.depth_list)
        
        if self.verbose:
            print(f"Available OB metrics: {list(ob_data.keys())}")
        
        expected_metrics = {}
        
        # Basic price metrics
        metric_mappings = {
            'b_price_mean': 'b_price',
            'a_price_mean': 'a_price', 
            'spread_mean': 'ba_spread',
            'mid_price_mean': 'mid_price',
            'b_price_sparsity': 'b_price_sparsity',
            'a_price_sparsity': 'a_price_sparsity',
            'ba_volrat_00': 'ba_volrat_00',
            'ba_volrat_30': 'ba_volrat_30',
            'ba_volrat_50': 'ba_volrat_50',
            'ba_volrat_90': 'ba_volrat_90',
            'bid_volume_mean': 'bid_volume',
            'ask_volume_mean': 'ask_volume',
        }
        
        # Extract metrics
        for expected_key, ob_key in metric_mappings.items():
            if ob_key in ob_data:
                series_data = pd.Series(ob_data[ob_key])
                expected_metrics[expected_key] = series_data.mean()
                if self.verbose:
                    print(f"  {expected_key}: {expected_metrics[expected_key]:.6f} (from {len(series_data)} values)")
        
        # Trade metrics
        expected_metrics['trade_count'] = len(trades_df)
        if isinstance(trades_df, pd.DataFrame) and 'quantity' in trades_df.columns:
            expected_metrics['trade_volume_sum'] = trades_df['quantity'].sum()
        else:
            expected_metrics['trade_volume_sum'] = 0
        
        if self.verbose:
            print(f"Successfully calculated {len(expected_metrics)} expected metrics")
            print(f"Trade metrics: count={expected_metrics['trade_count']}, volume={expected_metrics['trade_volume_sum']}")
        
        return expected_metrics


def load_real_test_data(instrument: str = 'dey1', date_str: str = '2025-04-04') -> Tuple[Dict, pd.DataFrame, Dict[str, Any]]:
    """
    Convenience function to load sample test data.
    
    Args:
        instrument: Market instrument (for compatibility)
        date_str: Date string (for compatibility)
        
    Returns:
        Tuple of (orderbook_dict, trades_df, expected_metrics_dict)
    """
    loader = RealDataLoader(instrument=instrument, verbose=True)
    return loader.load_single_day_data(date_str)


def save_real_data_sample(filename: str = 'real_test_data.pkl', 
                         instrument: str = 'dey1', date_str: str = '2025-04-04'):
    """
    Save a real data sample using local implementations.
    
    Args:
        filename: Output pickle filename
        instrument: Market instrument (for compatibility)
        date_str: Date string (for compatibility)
    """
    orderbook_dict, trades_df, expected_metrics = load_real_test_data(instrument, date_str)
    
    data_sample = {
        'orderbook_dict': orderbook_dict,
        'trades_df': trades_df,
        'expected_metrics': expected_metrics,
        'metadata': {
            'instrument': instrument,
            'date': date_str,
            'generation_time': datetime.now().isoformat(),
            'source': 'local_implementations',
            'data_validation': 'Sample data with local calculations'
        }
    }
    
    with open(filename, 'wb') as f:
        pickle.dump(data_sample, f)
    
    print(f"✅ Sample data saved to {filename}")
    print(f"Contains {len(orderbook_dict)} OrderBook snapshots and {len(trades_df)} trades")


if __name__ == '__main__':
    print("Testing Real Data Loader (Local Implementation)")
    print("=" * 60)
    
    try:
        print("Loading sample data using local implementations...")
        orderbook_dict, trades_df, expected_metrics = load_real_test_data(
            instrument='dey1',
            date_str='2025-04-04'
        )
        
        print("✅ Sample data loader test successful!")
        print(f"  OrderBook snapshots: {len(orderbook_dict)}")
        print(f"  Trades: {len(trades_df)}")
        print(f"  Expected metrics: {len(expected_metrics)}")
        print(f"  Sample metrics: {dict(list(expected_metrics.items())[:5])}")
        
    except Exception as e:
        print(f"❌ Sample data loader test failed: {e}")
        import traceback
        traceback.print_exc()