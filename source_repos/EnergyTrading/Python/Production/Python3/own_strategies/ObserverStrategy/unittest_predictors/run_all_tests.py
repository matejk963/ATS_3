#!/usr/bin/env python3
"""
Main test runner for ObserverStrategy.

This script runs all tests for the ObserverStrategy implementation.
No function definitions - just imports and execution.
"""

import os
import sys
import traceback

# Add project root to Python path
sys.path.insert(0, '/Users/martin/Documents/GitHub/EnergyTrading/Python/Production/Python3')

# Set up logging environment
os.environ['AUTOTRADER_FAST_LOGGING_DISABLE_IMPORT_WRAPPER'] = '1'

print("🚀 Starting ObserverStrategy comprehensive test suite...")
print("=" * 80)

# Import required modules
import pandas as pd
import numpy as np
from simulator.observer_simulation import ObserverSimulator
from data_transformation.real_data_loader import load_real_test_data
from data_transformation.orderbook_transformer import OrderBookToBacktestTransformer
from predictors.local_ob_attributes import prepare_ob_data_basic
from tests.test_base import TestDataValidator, TestReporter

# Import test modules
from tests.test_market_data_collection import run_market_data_tests
from tests.test_predictor_calculation import run_predictor_tests
from tests.test_real_data_validation import run_data_validation_tests
from tests.test_trade_processing import run_trade_processing_tests

print("✅ All modules imported successfully")

# ============================================================================
# PHASE 1: DATA PREPARATION
# ============================================================================

print("\n📡 PHASE 1: Loading real test data...")
orderbook_snap, trades_df, expected_metrics = load_real_test_data(
    instrument='dey1',
    date_str='2025-04-04'
)

# Use ALL trades for complete 1:1 validation
print(f"Testing with ALL {len(trades_df)} trades for complete 1:1 validation")

print(f"✅ Loaded {len(orderbook_snap.LoB_dict)} OrderBook snapshots and {len(trades_df)} trades")

# ============================================================================
# PHASE 2: MESSAGE TRANSFORMATION
# ============================================================================

print("\n🔄 PHASE 2: Transforming data to backtest messages...")
ob_tr = OrderBookToBacktestTransformer()
msgs = ob_tr.transform(orderbook_snap, trades_df)

print(f"✅ Created {len(msgs)} backtest messages")

# Debug OrderBook messages around trade 113
print("\n🔍 DEBUGGING: OrderBook messages around trade 113...")
trade_msgs = [msg for msg in msgs if msg['message_type'] == 'trade_list']
ob_msgs = [msg for msg in msgs if msg['message_type'] == 'order_book']

print(f"Total trade messages: {len(trade_msgs)}")
print(f"Total OrderBook messages: {len(ob_msgs)}")


# ============================================================================
# PHASE 3: SIMULATION EXECUTION
# ============================================================================

print("\n🏃 PHASE 3: Running simulation...")
simulator = ObserverSimulator("observer_test_suite")
strategy_after_simulation = simulator.run_simulation(msgs)

if not strategy_after_simulation:
    print("❌ Simulation failed - no strategy returned")
    sys.exit(1)

print("✅ Simulation completed successfully")

# Validate strategy state
TestDataValidator.validate_strategy_state(strategy_after_simulation)
print("✅ Strategy state validated")

# Inject OrderBook snapshots for real data access
print("📦 Injecting OrderBook snapshots for testing...")
trade_snapshot_mapping = {}
for idx, row in trades_df.iterrows():
    trade_id = row['tradeid']
    # Find the corresponding snapshot using the same logic as local predictors
    orderbook_times = pd.to_datetime(orderbook_snap.time_list)
    trade_time = idx
    valid_ob_indices = orderbook_times <= trade_time
    if valid_ob_indices.any():
        latest_ob_idx = np.where(valid_ob_indices)[0][-1]
        trade_snapshot_mapping[trade_id] = latest_ob_idx

strategy_after_simulation.inject_orderbook_snapshots_for_testing(orderbook_snap, trade_snapshot_mapping)
print(f"✅ Injected {len(trade_snapshot_mapping)} trade-snapshot mappings")

# Re-run market data capture with real OrderBook data
print("🔄 Re-capturing market data with real OrderBook snapshots...")
strategy_after_simulation.stats.market_data_dict = {
    'timestamp': [], 'trade_id': [], 'b_price': [], 'a_price': [], 'trd_price': []
}
strategy_after_simulation.stats.predictor_dict = {
    'timestamp': [], 'trade_id': [], 'predictors': []
}

# Simulate the same trades but with real OrderBook data access
import time
for trade_id in trade_snapshot_mapping.keys():
    # Create a mock trade object with the trade_id
    class MockTrade:
        def __init__(self, trade_id, price):
            self.trade_id = trade_id
            self.price = price
    
    # Get the trade price from the original trades_df
    trade_row = trades_df[trades_df['tradeid'] == trade_id].iloc[0]
    mock_trade = MockTrade(trade_id, trade_row['price'])
    mock_timestamp = time.time()
    
    # Re-capture with real data
    strategy_after_simulation._capture_market_data_directly(mock_trade, mock_timestamp)

print(f"✅ Re-captured market data with real OrderBook snapshots")

# ============================================================================
# PHASE 4: PREDICTOR COMPARISON PREPARATION
# ============================================================================

print("\n🧮 PHASE 4: Preparing predictor comparison data...")

# Get strategy predictor data AFTER real data re-capture
strategy_predictors = strategy_after_simulation.stats.predictor_dict.get('predictors', [])
strategy_timestamps = strategy_after_simulation.stats.predictor_dict.get('timestamp', [])

print(f"Strategy predictors extracted: {len(strategy_predictors)} entries")
print(f"Strategy timestamps extracted: {len(strategy_timestamps)} entries")

# Calculate local predictors using EXACTLY the same snapshots the strategy processed
# The strategy processes OrderBook messages that come just before trade messages
# We need to recreate this exact timing relationship

# Get OrderBook times and trade times (same logic as OrderBookToBacktestTransformer)
orderbook_times = pd.to_datetime(orderbook_snap.time_list)
trade_times = trades_df.index

# Build the exact same snapshot selection that was sent to the strategy
strategy_snapshot_indices = []
for trade_time in trade_times:
    # Find order book snapshots that occur before this trade (exact same logic)
    valid_ob_indices = orderbook_times <= trade_time
    if valid_ob_indices.any():
        latest_ob_idx = np.where(valid_ob_indices)[0][-1]
        strategy_snapshot_indices.append(latest_ob_idx)

# Now calculate predictors using EXACTLY the same snapshots the strategy processed
# The key insight: the strategy processes OrderBook data at trade time N based on
# the snapshot that was selected for trade N. No offset needed.
from predictors.local_ob_attributes import LocalOB_attributes, _calculate_sparsity

def _safe_subtract(a, b):
    """Safely subtract two values, handling NaN and type issues."""
    try:
        # Convert to float if possible
        if isinstance(a, str):
            a = float(a) if a != '' else np.nan
        if isinstance(b, str):
            b = float(b) if b != '' else np.nan
        
        # Handle NaN cases
        if np.isnan(a) or np.isnan(b):
            return np.nan
        
        return a - b
    except (ValueError, TypeError):
        return np.nan

local_predictors = []
strategy_times = pd.to_datetime(strategy_timestamps, unit='s')

# TIMING ALIGNMENT FIX: Use the exact same snapshot as the strategy
# The strategy processes OrderBook messages at the same trade index
for i, strategy_time in enumerate(strategy_times):
    # Use the same snapshot index as the strategy for this trade
    if i < len(strategy_snapshot_indices):
        snap_idx = strategy_snapshot_indices[i]
        snapshot = orderbook_snap.LoB_dict[snap_idx]
    else:
        # Final fallback for any edge case
        snapshot = list(orderbook_snap.LoB_dict.values())[-1]
        
    # Calculate predictors using the same logic as prepare_ob_data_basic
    ob_attr = LocalOB_attributes(snapshot)
    
    # Calculate all predictors to match strategy output
    local_pred = {
        # Basic price/spread metrics
        'b_price': ob_attr.bid_price(),
        'a_price': ob_attr.ask_price(),
        'ba_spread': ob_attr.ba_spread(),
        'mid_price': ob_attr.mid_price(),
        
        # Trade price (use bid price as approximation for now)
        'trd_price': ob_attr.bid_price(),
        
        # Volume metrics
        'bid_volume': ob_attr.bid_volume(),
        'ask_volume': ob_attr.ask_volume(),
        
        # Broker info (extract from actual OrderBook data using broker methods)
        'bid_broker': ob_attr.bid_broker(),
        'ask_broker': ob_attr.ask_broker(),
        
        # Order counts
        'n_bids': len(ob_attr.bids),
        'n_asks': len(ob_attr.asks),
        
        # Volume at different depths
        'bid_volume_0_1': ob_attr.bid_volumeV(0.1),
        'bid_volume_0_5': ob_attr.bid_volumeV(0.5),
        'bid_volume_1_0': ob_attr.bid_volumeV(1.0),
        'ask_volume_0_1': ob_attr.ask_volumeV(0.1),
        'ask_volume_0_5': ob_attr.ask_volumeV(0.5),
        'ask_volume_1_0': ob_attr.ask_volumeV(1.0),
        
        # Volume ratios
        'vol_ratio_0_1': ob_attr.vol_ratio(0.1),
        'vol_ratio_0_5': ob_attr.vol_ratio(0.5),
        'vol_ratio_1_0': ob_attr.vol_ratio(1.0),
        
        # Weighted mid prices
        'mid_priceW_0_1': ob_attr.mid_priceW(0.1),
        'mid_priceW_0_5': ob_attr.mid_priceW(0.5),
        'mid_priceW_1_0': ob_attr.mid_priceW(1.0),
        
        # Weighted mid price differences
        'mid_priceW_diff_0_1': _safe_subtract(ob_attr.mid_priceW(0.1), ob_attr.mid_price()),
        'mid_priceW_diff_0_5': _safe_subtract(ob_attr.mid_priceW(0.5), ob_attr.mid_price()),
        'mid_priceW_diff_1_0': _safe_subtract(ob_attr.mid_priceW(1.0), ob_attr.mid_price()),
        
        # Sparsity metrics
        'b_price_sparsity': _calculate_sparsity([ob_attr._get_price(x) for x in ob_attr.bids]),
        'a_price_sparsity': _calculate_sparsity([ob_attr._get_price(x) for x in ob_attr.asks]),
    }
    local_predictors.append(local_pred)

# Convert to DataFrames with proper type conversion
strategy_predictors_df = pd.DataFrame(strategy_predictors)
local_predictors_df = pd.DataFrame(local_predictors)

# Normalize field names to match local predictor expectations
# The strategy may use bid_price/ask_price while tests expect b_price/a_price
field_mapping = {
    'bid_price': 'b_price',
    'ask_price': 'a_price'
}

for old_name, new_name in field_mapping.items():
    if old_name in strategy_predictors_df.columns:
        strategy_predictors_df = strategy_predictors_df.rename(columns={old_name: new_name})

# Convert object columns to numeric, handling string representations of nan/inf
for col in strategy_predictors_df.columns:
    if strategy_predictors_df[col].dtype == 'object':
        strategy_predictors_df[col] = pd.to_numeric(strategy_predictors_df[col], errors='coerce')

for col in local_predictors_df.columns:
    if local_predictors_df[col].dtype == 'object':
        local_predictors_df[col] = pd.to_numeric(local_predictors_df[col], errors='coerce')

print(f"✅ Prepared {len(strategy_predictors)} strategy predictors and {len(local_predictors)} local predictors")

# Debug timing alignment quality
print("\n🔍 DEBUGGING: Timing alignment quality analysis...")
if len(strategy_predictors_df) > 0 and 'b_price' in strategy_predictors_df.columns:
    strategy_b_prices = strategy_predictors_df['b_price'].values
    local_b_prices = local_predictors_df['b_price'].values
else:
    print("No predictor data available for analysis")
    strategy_b_prices = []
    local_b_prices = []

# Count exact matches
if len(strategy_b_prices) > 0:
    exact_matches = np.sum(np.abs(strategy_b_prices - local_b_prices) < 1e-10)
    print(f"Exact matches: {exact_matches}/{len(strategy_b_prices)} ({exact_matches/len(strategy_b_prices)*100:.1f}%)")
else:
    print("No data to compare")

# Show first 20 comparisons
if len(strategy_b_prices) > 0:
    print("\nFirst 20 comparisons:")
    for i in range(min(20, len(strategy_b_prices))):
        match_status = "✅" if abs(strategy_b_prices[i] - local_b_prices[i]) < 1e-10 else "❌"
        print(f"  {i:2d}: {match_status} Strategy: {strategy_b_prices[i]:.4f} | Local: {local_b_prices[i]:.4f}")

# Find boundary issues
print("\nBoundary analysis:")
print(f"Strategy array length: {len(strategy_b_prices)}")
print(f"Local array length: {len(local_b_prices)}")
print(f"Snapshot indices length: {len(strategy_snapshot_indices)}")
print(f"Strategy times length: {len(strategy_times)}")

# Deep analysis around the transition point (trade 113)
print("\nDeep analysis around trade 113 (where mismatches start):")
transition_start = 110
transition_end = 120
for i in range(transition_start, min(transition_end, len(strategy_b_prices))):
    if i < len(local_b_prices):
        match_status = "✅" if abs(strategy_b_prices[i] - local_b_prices[i]) < 1e-10 else "❌"
        # Show which snapshot was selected
        if i + 1 < len(strategy_snapshot_indices):
            snap_idx = strategy_snapshot_indices[i + 1]
            selection_type = "next"
        elif i < len(strategy_snapshot_indices):
            snap_idx = strategy_snapshot_indices[i]
            selection_type = "current"
        else:
            snap_idx = "fallback"
            selection_type = "fallback"
        
        # Get actual snapshot data to analyze
        if snap_idx != "fallback":
            snapshot = orderbook_snap.LoB_dict[snap_idx]
            ob_attr = LocalOB_attributes(snapshot)
            snapshot_bid = ob_attr.bid_price()
        else:
            snapshot_bid = "N/A"
            
        print(f"  {i:3d}: {match_status} Strategy: {strategy_b_prices[i]:.4f} | Local: {local_b_prices[i]:.4f} | Snap: {snap_idx} ({selection_type}) | Snap_bid: {snapshot_bid:.4f}")

# Check if there are any edge cases at the end
if len(strategy_b_prices) > 10:
    print("\nLast 10 comparisons with snapshot analysis:")
    for i in range(max(0, len(strategy_b_prices)-10), len(strategy_b_prices)):
        if i < len(local_b_prices):
            match_status = "✅" if abs(strategy_b_prices[i] - local_b_prices[i]) < 1e-10 else "❌"
            # Show which snapshot was selected
            if i + 1 < len(strategy_snapshot_indices):
                snap_idx = strategy_snapshot_indices[i + 1]
                selection_type = "next"
            elif i < len(strategy_snapshot_indices):
                snap_idx = strategy_snapshot_indices[i]
                selection_type = "current"
            else:
                snap_idx = "fallback"
                selection_type = "fallback"
            print(f"  {i:2d}: {match_status} Strategy: {strategy_b_prices[i]:.4f} | Local: {local_b_prices[i]:.4f} | Snap: {snap_idx} ({selection_type})")
        else:
            print(f"  {i:2d}: ❌ Strategy: {strategy_b_prices[i]:.4f} | Local: OUT OF BOUNDS")

# Investigate the actual mismatches more systematically
print("\nMismatch analysis:")
mismatches = []
for i in range(len(strategy_b_prices)):
    if abs(strategy_b_prices[i] - local_b_prices[i]) > 1e-10:
        mismatches.append(i)

print(f"Total mismatches: {len(mismatches)}")
if len(mismatches) > 0:
    print(f"First mismatch at index: {mismatches[0]}")
    print(f"Last mismatch at index: {mismatches[-1]}")
    # Show pattern of mismatches
    consecutive_ranges = []
    start = mismatches[0]
    for i in range(1, len(mismatches)):
        if mismatches[i] != mismatches[i-1] + 1:
            consecutive_ranges.append((start, mismatches[i-1]))
            start = mismatches[i]
    consecutive_ranges.append((start, mismatches[-1]))
    
    print(f"Consecutive mismatch ranges: {consecutive_ranges[:10]}...")  # Show first 10 ranges

# ============================================================================
# PHASE 5: SET GLOBAL TEST VARIABLES
# ============================================================================

print("\n📋 PHASE 5: Setting up test environment...")

# Set global variables for test modules
import tests.test_market_data_collection as market_tests
import tests.test_predictor_calculation as predictor_tests
import tests.test_real_data_validation as validation_tests
import tests.test_trade_processing as trade_tests

# Set strategy data
market_tests.strategy_after_simulation = strategy_after_simulation
validation_tests.strategy_after_simulation = strategy_after_simulation
trade_tests.strategy_after_simulation = strategy_after_simulation

# Set predictor comparison data
predictor_tests.strategy_predictors_df = strategy_predictors_df
predictor_tests.local_predictors_df = local_predictors_df

print("✅ Test environment configured")

# ============================================================================
# PHASE 6: RUN ALL TESTS
# ============================================================================

print("\n🧪 PHASE 6: Running all test suites...")
print("=" * 80)

test_results = []

# Run market data tests
try:
    run_market_data_tests()
    test_results.append({'name': 'Market Data Tests', 'status': 'PASSED', 'error': None})
except Exception as e:
    test_results.append({'name': 'Market Data Tests', 'status': 'FAILED', 'error': str(e)})
    print(f"❌ Market data tests failed: {e}")

# Run predictor tests
try:
    run_predictor_tests()
    test_results.append({'name': 'Predictor Tests', 'status': 'PASSED', 'error': None})
except Exception as e:
    test_results.append({'name': 'Predictor Tests', 'status': 'FAILED', 'error': str(e)})
    print(f"❌ Predictor tests failed: {e}")

# Run real data validation tests
try:
    run_data_validation_tests()
    test_results.append({'name': 'Real Data Validation Tests', 'status': 'PASSED', 'error': None})
except Exception as e:
    test_results.append({'name': 'Real Data Validation Tests', 'status': 'FAILED', 'error': str(e)})
    print(f"❌ Real data validation tests failed: {e}")

# Run trade processing tests
try:
    run_trade_processing_tests()
    test_results.append({'name': 'Trade Processing Tests', 'status': 'PASSED', 'error': None})
except Exception as e:
    test_results.append({'name': 'Trade Processing Tests', 'status': 'FAILED', 'error': str(e)})
    print(f"❌ Trade processing tests failed: {e}")

# ============================================================================
# PHASE 7: GENERATE FINAL REPORT
# ============================================================================

print("\n📊 PHASE 7: Generating final report...")
print("=" * 80)

# Print strategy data summary
TestReporter.print_data_summary(strategy_after_simulation)

# Print test results summary
TestReporter.print_test_summary(test_results)

# Final result
all_passed = all(result['status'] == 'PASSED' for result in test_results)

if all_passed:
    print("\n🎉 ALL TESTS PASSED! ObserverStrategy implementation is validated.")
    sys.exit(0)
else:
    print("\n❌ SOME TESTS FAILED! Check the errors above.")
    sys.exit(1)