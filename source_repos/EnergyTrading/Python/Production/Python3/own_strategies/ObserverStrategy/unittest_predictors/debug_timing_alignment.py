#!/usr/bin/env python3
"""
Debug script to understand the timing alignment drift issue.
"""

import os
import sys
sys.path.insert(0, '/Users/martin/Documents/GitHub/EnergyTrading/Python/Production/Python3')

import pandas as pd
import numpy as np
from data_transformation.real_data_loader import load_real_test_data
from data_transformation.orderbook_transformer import OrderBookToBacktestTransformer
from simulator.observer_simulation import ObserverSimulator
from predictors.local_ob_attributes import LocalOB_attributes

print("🔍 Debugging timing alignment issue...")

# Load test data
orderbook_snap, trades_df, expected_metrics = load_real_test_data('dey1', '2025-04-04')

# Transform and simulate
ob_tr = OrderBookToBacktestTransformer()
msgs = ob_tr.transform(orderbook_snap, trades_df)
simulator = ObserverSimulator("debug_timing")
strategy_after_simulation = simulator.run_simulation(msgs)

# Get strategy results
strategy_predictors = strategy_after_simulation.stats.predictor_dict.get('predictors', [])
strategy_timestamps = strategy_after_simulation.stats.predictor_dict.get('timestamp', [])

# Get OrderBook times and trade times
orderbook_times = pd.to_datetime(orderbook_snap.time_list)
trade_times = trades_df.index

# Build strategy snapshot selection
strategy_snapshot_indices = []
for trade_time in trade_times:
    valid_ob_indices = orderbook_times <= trade_time
    if valid_ob_indices.any():
        latest_ob_idx = np.where(valid_ob_indices)[0][-1]
        strategy_snapshot_indices.append(latest_ob_idx)

print(f"Strategy has {len(strategy_predictors)} predictors")
print(f"Strategy snapshot indices: {len(strategy_snapshot_indices)}")
print(f"First 20 snapshot indices: {strategy_snapshot_indices[:20]}")

# Extract n_bids from strategy
strategy_n_bids = [pred['n_bids'] for pred in strategy_predictors]

# Calculate local n_bids with different offset strategies
local_n_bids_no_offset = []
local_n_bids_plus1 = []
local_n_bids_minus1 = []

for i, strategy_time in enumerate(pd.to_datetime(strategy_timestamps, unit='s')):
    # No offset (current logic)
    if i < len(strategy_snapshot_indices):
        snap_idx = strategy_snapshot_indices[i]
        snapshot = orderbook_snap.LoB_dict[snap_idx]
        ob_attr = LocalOB_attributes(snapshot)
        local_n_bids_no_offset.append(len(ob_attr.bids))
    
    # +1 offset (current problematic logic)
    local_idx = i + 1
    if local_idx < len(strategy_snapshot_indices):
        snap_idx = strategy_snapshot_indices[local_idx]
        snapshot = orderbook_snap.LoB_dict[snap_idx]
        ob_attr = LocalOB_attributes(snapshot)
        local_n_bids_plus1.append(len(ob_attr.bids))
    elif i < len(strategy_snapshot_indices):
        snap_idx = strategy_snapshot_indices[i]
        snapshot = orderbook_snap.LoB_dict[snap_idx]
        ob_attr = LocalOB_attributes(snapshot)
        local_n_bids_plus1.append(len(ob_attr.bids))
    else:
        local_n_bids_plus1.append(0)
    
    # -1 offset (test alternative)
    local_idx = i - 1
    if local_idx >= 0 and local_idx < len(strategy_snapshot_indices):
        snap_idx = strategy_snapshot_indices[local_idx]
        snapshot = orderbook_snap.LoB_dict[snap_idx]
        ob_attr = LocalOB_attributes(snapshot)
        local_n_bids_minus1.append(len(ob_attr.bids))
    elif i < len(strategy_snapshot_indices):
        snap_idx = strategy_snapshot_indices[i]
        snapshot = orderbook_snap.LoB_dict[snap_idx]
        ob_attr = LocalOB_attributes(snapshot)
        local_n_bids_minus1.append(len(ob_attr.bids))
    else:
        local_n_bids_minus1.append(0)

# Compare first 20 elements
print("\nFirst 20 n_bids comparisons:")
print("Index | Strategy | No Offset | +1 Offset | -1 Offset")
print("-" * 55)
for i in range(min(20, len(strategy_n_bids))):
    strategy_val = strategy_n_bids[i]
    no_offset_val = local_n_bids_no_offset[i] if i < len(local_n_bids_no_offset) else 0
    plus1_val = local_n_bids_plus1[i] if i < len(local_n_bids_plus1) else 0
    minus1_val = local_n_bids_minus1[i] if i < len(local_n_bids_minus1) else 0
    
    print(f"{i:5d} | {strategy_val:8d} | {no_offset_val:9d} | {plus1_val:9d} | {minus1_val:9d}")

# Calculate match percentages
def calculate_match_percentage(strategy_vals, local_vals):
    matches = sum(1 for s, l in zip(strategy_vals, local_vals) if s == l)
    return (matches / len(strategy_vals)) * 100 if strategy_vals else 0

no_offset_match = calculate_match_percentage(strategy_n_bids, local_n_bids_no_offset)
plus1_match = calculate_match_percentage(strategy_n_bids, local_n_bids_plus1)
minus1_match = calculate_match_percentage(strategy_n_bids, local_n_bids_minus1)

print(f"\nMatch percentages:")
print(f"No offset: {no_offset_match:.1f}%")
print(f"+1 offset: {plus1_match:.1f}%")
print(f"-1 offset: {minus1_match:.1f}%")

# Check if the issue is with the strategy_snapshot_indices logic
print(f"\nSnapshot indices analysis:")
print(f"Total OrderBook snapshots: {len(orderbook_snap.LoB_dict)}")
print(f"Total trades: {len(trades_df)}")
print(f"Strategy snapshot indices: {len(strategy_snapshot_indices)}")

# Look at the actual snapshot indices vs their order
print("\nSnapshot index progression (first 20):")
for i in range(min(20, len(strategy_snapshot_indices))):
    print(f"Trade {i}: uses snapshot index {strategy_snapshot_indices[i]}")

# Check if strategy_snapshot_indices are monotonic
is_monotonic = all(strategy_snapshot_indices[i] <= strategy_snapshot_indices[i+1] 
                   for i in range(len(strategy_snapshot_indices)-1))
print(f"\nSnapshot indices are monotonic: {is_monotonic}")

print("🔍 Debug complete!")