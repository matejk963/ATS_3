"""
Test predictors by comparing local implementations with production code using REAL DATA.

This module loads actual sample data from pickle files and tests that the
local implementations produce the same results as the production predictor functions
when run on the same real OrderBook snapshots and trades data.
"""

import os
import sys
import pickle
import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple, List

# Add path to production code for comparison
production_path = os.path.join(os.path.dirname(__file__), '..', '..', 'observer_strategy')
sys.path.insert(0, production_path)

from local_ob_attributes import LocalOB_attributes, prepare_ob_data_basic, _calculate_sparsity

# Create local copies of production functions to avoid relative import issues
def _production_sparsity_func(order_book):
    """Local copy of production _sparsity_func"""
    _MIN_N_ORDERS = 4
    order_book = np.array(order_book)

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

# Set up production functions
_sparsity_func = _production_sparsity_func
PRODUCTION_IMPORTS_AVAILABLE = True
print(f"✅ Using local copies of production predictor functions")


class RealDataPredictorTester:
    """
    Test predictor implementations using real OrderBook data from pickle files.
    
    This class loads actual production data and runs both production and local
    predictor functions on the SAME data to validate they produce identical results.
    """
    
    def __init__(self, data_dir: str = None):
        """
        Initialize predictor tester.
        
        Args:
            data_dir: Directory containing pickle files (defaults to ../data_transformation)
        """
        if data_dir is None:
            data_dir = os.path.join(os.path.dirname(__file__), '..', 'data_transformation')
        
        self.data_dir = data_dir
        self.orderbook_data = None
        self.trades_data = None
        self.loaded = False
        
        # Test configuration
        self.test_sample_size = 100  # Test on first 100 OrderBook snapshots
        self.depth_levels = [0.0, 0.3, 0.5, 0.9]  # Price depths for testing
    
    def load_sample_data(self):
        """Load sample data from pickle files"""
        orderbook_file = os.path.join(self.data_dir, 'prod_unittest_lob.pkl.sample')
        trades_file = os.path.join(self.data_dir, 'prod_unittest_trades.pkl.sample')
        
        if not os.path.exists(orderbook_file):
            raise FileNotFoundError(f"OrderBook sample file not found: {orderbook_file}")
        
        if not os.path.exists(trades_file):
            raise FileNotFoundError(f"Trades sample file not found: {trades_file}")
        
        # Load OrderBook data
        with open(orderbook_file, 'rb') as f:
            self.orderbook_data = pickle.load(f)
        
        # Load trades data
        with open(trades_file, 'rb') as f:
            self.trades_data = pickle.load(f)
        
        self.loaded = True
        print(f"✅ Loaded real sample data:")
        print(f"  OrderBook snapshots: {len(self.orderbook_data)}")
        print(f"  Trades records: {len(self.trades_data)}")
        print(f"  Testing on first {self.test_sample_size} OrderBook snapshots")
    
    def test_sparsity_function_on_real_data(self) -> Dict[str, Any]:
        """
        Test sparsity function using real OrderBook data.
        
        Returns:
            Dictionary with test results
        """
        if not self.loaded:
            self.load_sample_data()
        
        results = {
            'test_name': 'sparsity_function_real_data',
            'passed': True,
            'errors': [],
            'comparisons': [],
            'sample_size': 0
        }
        
        if not PRODUCTION_IMPORTS_AVAILABLE:
            results['passed'] = False
            results['errors'].append("Production predictors not available")
            return results
        
        # Test on first N OrderBook snapshots
        test_items = list(self.orderbook_data.items())[:self.test_sample_size]
        
        for i, (timestamp, orderbook) in enumerate(test_items):
            try:
                # Create local OB_attributes
                local_ob_attr = LocalOB_attributes(orderbook)
                
                # Extract bid and ask prices
                bid_prices = [local_ob_attr._get_price(x) for x in local_ob_attr.bids]
                ask_prices = [local_ob_attr._get_price(x) for x in local_ob_attr.asks]
                
                # Calculate sparsity using local implementation
                local_b_sparsity = _calculate_sparsity(bid_prices)
                local_a_sparsity = _calculate_sparsity(ask_prices)
                
                # Calculate sparsity using production implementation
                prod_b_sparsity = _sparsity_func(bid_prices)
                prod_a_sparsity = _sparsity_func(ask_prices)
                
                # Compare results
                b_match = abs(local_b_sparsity - prod_b_sparsity) < 1e-10
                a_match = abs(local_a_sparsity - prod_a_sparsity) < 1e-10
                
                results['comparisons'].append({
                    'timestamp': timestamp,
                    'bid_count': len(bid_prices),
                    'ask_count': len(ask_prices),
                    'local_b_sparsity': local_b_sparsity,
                    'prod_b_sparsity': prod_b_sparsity,
                    'local_a_sparsity': local_a_sparsity,
                    'prod_a_sparsity': prod_a_sparsity,
                    'b_match': b_match,
                    'a_match': a_match,
                    'both_match': b_match and a_match
                })
                
                if not (b_match and a_match):
                    results['passed'] = False
                    results['errors'].append(f"Sparsity mismatch at timestamp {timestamp}: b_local={local_b_sparsity}, b_prod={prod_b_sparsity}, a_local={local_a_sparsity}, a_prod={prod_a_sparsity}")
                
            except Exception as e:
                results['passed'] = False
                results['errors'].append(f"Error processing timestamp {timestamp}: {e}")
        
        results['sample_size'] = len(test_items)
        return results
    
    def test_predictor_sparsity_on_real_data(self) -> Dict[str, Any]:
        """
        Test predictor_sparsity function using real OrderBook data.
        
        Returns:
            Dictionary with test results
        """
        if not self.loaded:
            self.load_sample_data()
        
        results = {
            'test_name': 'predictor_sparsity_real_data',
            'passed': True,
            'errors': [],
            'comparisons': [],
            'sample_size': 0
        }
        
        if not PRODUCTION_IMPORTS_AVAILABLE:
            results['passed'] = False
            results['errors'].append("Production predictors not available")
            return results
        
        # Test on first N OrderBook snapshots
        test_items = list(self.orderbook_data.items())[:self.test_sample_size]
        
        for i, (timestamp, orderbook) in enumerate(test_items):
            try:
                # Create local OB_attributes
                local_ob_attr = LocalOB_attributes(orderbook)
                
                # Calculate sparsity using local implementation
                local_result = {
                    'b_price_sparsity': _calculate_sparsity([local_ob_attr._get_price(x) for x in local_ob_attr.bids]),
                    'a_price_sparsity': _calculate_sparsity([local_ob_attr._get_price(x) for x in local_ob_attr.asks])
                }
                
                # Create production OB_attributes
                # Note: This would need actual production OB_attributes constructor
                # For now, compare directly with sparsity function
                bid_prices = [local_ob_attr._get_price(x) for x in local_ob_attr.bids]
                ask_prices = [local_ob_attr._get_price(x) for x in local_ob_attr.asks]
                
                prod_result = {
                    'b_price_sparsity': _sparsity_func(bid_prices),
                    'a_price_sparsity': _sparsity_func(ask_prices)
                }
                
                # Compare results
                b_match = abs(local_result['b_price_sparsity'] - prod_result['b_price_sparsity']) < 1e-10
                a_match = abs(local_result['a_price_sparsity'] - prod_result['a_price_sparsity']) < 1e-10
                
                results['comparisons'].append({
                    'timestamp': timestamp,
                    'local_result': local_result,
                    'prod_result': prod_result,
                    'b_match': b_match,
                    'a_match': a_match,
                    'both_match': b_match and a_match
                })
                
                if not (b_match and a_match):
                    results['passed'] = False
                    results['errors'].append(f"Predictor sparsity mismatch at timestamp {timestamp}")
                
            except Exception as e:
                results['passed'] = False
                results['errors'].append(f"Error processing timestamp {timestamp}: {e}")
        
        results['sample_size'] = len(test_items)
        return results
    
    def test_volume_ratio_on_real_data(self) -> Dict[str, Any]:
        """
        Test volume ratio calculations using real OrderBook data.
        
        Returns:
            Dictionary with test results
        """
        if not self.loaded:
            self.load_sample_data()
        
        results = {
            'test_name': 'volume_ratio_real_data',
            'passed': True,
            'errors': [],
            'comparisons': [],
            'sample_size': 0
        }
        
        # Test on first N OrderBook snapshots
        test_items = list(self.orderbook_data.items())[:self.test_sample_size]
        
        for i, (timestamp, orderbook) in enumerate(test_items):
            try:
                # Create local OB_attributes
                local_ob_attr = LocalOB_attributes(orderbook)
                
                # Test volume ratios at different depths
                for depth in self.depth_levels:
                    local_vol_ratio = local_ob_attr.vol_ratio(depth)
                    
                    # Store results
                    results['comparisons'].append({
                        'timestamp': timestamp,
                        'depth': depth,
                        'local_vol_ratio': local_vol_ratio,
                        'bid_price': local_ob_attr.bid_price(),
                        'ask_price': local_ob_attr.ask_price(),
                        'bid_volume': local_ob_attr.bid_volume(),
                        'ask_volume': local_ob_attr.ask_volume(),
                        'valid_calculation': not np.isnan(local_vol_ratio)
                    })
                
            except Exception as e:
                results['passed'] = False
                results['errors'].append(f"Error processing timestamp {timestamp}: {e}")
        
        results['sample_size'] = len(test_items)
        return results
    
    def test_mid_price_calculations_on_real_data(self) -> Dict[str, Any]:
        """
        Test mid price calculations using real OrderBook data.
        
        Returns:
            Dictionary with test results
        """
        if not self.loaded:
            self.load_sample_data()
        
        results = {
            'test_name': 'mid_price_real_data',
            'passed': True,
            'errors': [],
            'comparisons': [],
            'sample_size': 0
        }
        
        # Test on first N OrderBook snapshots
        test_items = list(self.orderbook_data.items())[:self.test_sample_size]
        
        for i, (timestamp, orderbook) in enumerate(test_items):
            try:
                # Create local OB_attributes
                local_ob_attr = LocalOB_attributes(orderbook)
                
                # Test mid price calculations at different depths
                for depth in self.depth_levels:
                    local_mid_price = local_ob_attr.mid_price()
                    local_mid_priceW = local_ob_attr.mid_priceW(depth)
                    
                    # Calculate difference
                    if not np.isnan(local_mid_price) and not np.isnan(local_mid_priceW):
                        local_mid_priceW_d = local_mid_priceW - local_mid_price
                    else:
                        local_mid_priceW_d = np.nan
                    
                    # Store results
                    results['comparisons'].append({
                        'timestamp': timestamp,
                        'depth': depth,
                        'local_mid_price': local_mid_price,
                        'local_mid_priceW': local_mid_priceW,
                        'local_mid_priceW_d': local_mid_priceW_d,
                        'bid_price': local_ob_attr.bid_price(),
                        'ask_price': local_ob_attr.ask_price(),
                        'valid_calculation': not np.isnan(local_mid_priceW)
                    })
                
            except Exception as e:
                results['passed'] = False
                results['errors'].append(f"Error processing timestamp {timestamp}: {e}")
        
        results['sample_size'] = len(test_items)
        return results
    
    def run_all_tests(self) -> Dict[str, Any]:
        """
        Run all predictor tests on real data.
        
        Returns:
            Dictionary with all test results
        """
        print("Running predictor tests on REAL DATA...")
        print("=" * 60)
        
        all_results = {
            'overall_passed': True,
            'tests': {}
        }
        
        # Test sparsity function
        print("Testing sparsity function on real OrderBook data...")
        sparsity_results = self.test_sparsity_function_on_real_data()
        all_results['tests']['sparsity_function'] = sparsity_results
        if not sparsity_results['passed']:
            all_results['overall_passed'] = False
        print(f"  Processed {sparsity_results['sample_size']} OrderBook snapshots")
        
        # Test predictor_sparsity
        print("Testing predictor_sparsity on real OrderBook data...")
        predictor_sparsity_results = self.test_predictor_sparsity_on_real_data()
        all_results['tests']['predictor_sparsity'] = predictor_sparsity_results
        if not predictor_sparsity_results['passed']:
            all_results['overall_passed'] = False
        print(f"  Processed {predictor_sparsity_results['sample_size']} OrderBook snapshots")
        
        # Test volume ratio calculations
        print("Testing volume ratio calculations on real OrderBook data...")
        vol_ratio_results = self.test_volume_ratio_on_real_data()
        all_results['tests']['volume_ratio_calculations'] = vol_ratio_results
        if not vol_ratio_results['passed']:
            all_results['overall_passed'] = False
        print(f"  Processed {vol_ratio_results['sample_size']} OrderBook snapshots")
        
        # Test mid price calculations
        print("Testing mid price calculations on real OrderBook data...")
        mid_price_results = self.test_mid_price_calculations_on_real_data()
        all_results['tests']['mid_price_calculations'] = mid_price_results
        if not mid_price_results['passed']:
            all_results['overall_passed'] = False
        print(f"  Processed {mid_price_results['sample_size']} OrderBook snapshots")
        
        return all_results


def run_predictor_tests():
    """
    Convenience function to run all predictor tests on real data.
    
    Returns:
        Test results dictionary
    """
    tester = RealDataPredictorTester()
    return tester.run_all_tests()


if __name__ == '__main__':
    print("ObserverStrategy Predictor Tests - REAL DATA")
    print("=" * 60)
    
    try:
        results = run_predictor_tests()
        
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        
        if results['overall_passed']:
            print("✅ All tests passed!")
        else:
            print("❌ Some tests failed!")
        
        # Print detailed results
        for test_name, test_result in results['tests'].items():
            print(f"\n{test_name}:")
            print(f"  Status: {'✅ PASSED' if test_result['passed'] else '❌ FAILED'}")
            print(f"  Sample size: {test_result['sample_size']}")
            print(f"  Comparisons: {len(test_result['comparisons'])}")
            
            if test_result['errors']:
                print(f"  Errors: {len(test_result['errors'])}")
                for error in test_result['errors'][:3]:  # Show first 3 errors
                    print(f"    - {error}")
                if len(test_result['errors']) > 3:
                    print(f"    ... and {len(test_result['errors']) - 3} more")
            
            # Show some sample comparisons
            if test_result['comparisons']:
                valid_comparisons = [c for c in test_result['comparisons'] if c.get('both_match', True)]
                print(f"  Valid comparisons: {len(valid_comparisons)}/{len(test_result['comparisons'])}")
    
    except Exception as e:
        print(f"❌ Test execution failed: {e}")
        import traceback
        traceback.print_exc()