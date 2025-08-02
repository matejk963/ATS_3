#!/usr/bin/env python3
"""
Swing Points Legacy Compatibility Test
Validates that GPU implementation matches legacy detect_swing_points() behavior
Expected to FAIL initially with ~3% match rate
"""

import pandas as pd
import numpy as np
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "source_repos/EnergyTrading/Python/Utilities"))

from feature_engineering.swing_point_detector import SwingPointDetector
from feature_engineering.array_backend import ArrayBackend
import predictors_tools


def test_swing_points_legacy_compatibility():
    """Test that swing detector matches legacy algorithm behavior"""
    
    # Load test data
    test_data_path = project_root / "Testing Data/backtest_data/dem07_25_tr_ba_data.parquet"
    if not test_data_path.exists():
        # Create minimal test data for development
        dates = pd.date_range('2024-01-01', periods=100, freq='1h')
        np.random.seed(42)
        prices = 100 + np.cumsum(np.random.randn(100) * 0.1)
        test_data = pd.DataFrame({
            'open': prices,
            'high': prices + np.random.uniform(0, 0.5, 100),
            'low': prices - np.random.uniform(0, 0.5, 100), 
            'close': prices + np.random.uniform(-0.2, 0.2, 100)
        }, index=dates)
    else:
        test_data = pd.read_parquet(test_data_path)
        # Use first 1000 rows for testing
        test_data = test_data.head(1000)
    
    print(f"Testing with {len(test_data)} data points")
    
    # Initialize current GPU implementation
    backend = ArrayBackend('cupy')  # GPU backend required
    swing_detector = SwingPointDetector(backend)
    
    # Run current implementation
    print("Running current GPU implementation...")
    current_result = swing_detector.detect_swings(test_data)
    
    # Run legacy implementation
    print("Running legacy implementation...")
    legacy_result = predictors_tools.detect_swing_points(test_data)
    
    # Compare results
    print("\nComparing results...")
    
    # Convert to comparable format
    current_highs = current_result['swing_high'].values
    current_lows = current_result['swing_low'].values
    legacy_highs = legacy_result['swing_high'].values
    legacy_lows = legacy_result['swing_low'].values
    
    # Calculate match rates
    high_matches = np.sum(np.isclose(current_highs, legacy_highs, rtol=1e-10, equal_nan=True))
    low_matches = np.sum(np.isclose(current_lows, legacy_lows, rtol=1e-10, equal_nan=True))
    
    total_points = len(current_highs)
    high_match_rate = (high_matches / total_points) * 100
    low_match_rate = (low_matches / total_points) * 100
    
    print(f"\nResults:")
    print(f"High match rate: {high_match_rate:.1f}% ({high_matches}/{total_points})")
    print(f"Low match rate: {low_match_rate:.1f}% ({low_matches}/{total_points})")
    
    # Show pattern differences
    print(f"\nPattern Analysis (first 20 points):")
    print("Index  | Current High | Legacy High  | Current Low  | Legacy Low")
    print("-------|--------------|--------------|--------------|------------")
    for i in range(min(20, len(current_highs))):
        curr_h = f"{current_highs[i]:.4f}" if not np.isnan(current_highs[i]) else "NaN    "
        leg_h = f"{legacy_highs[i]:.4f}" if not np.isnan(legacy_highs[i]) else "NaN    "
        curr_l = f"{current_lows[i]:.4f}" if not np.isnan(current_lows[i]) else "NaN    "
        leg_l = f"{legacy_lows[i]:.4f}" if not np.isnan(legacy_lows[i]) else "NaN    "
        print(f"{i:6d} | {curr_h:>12} | {leg_h:>12} | {curr_l:>12} | {leg_l:>12}")
    
    # TDD: This test should FAIL initially
    assert high_match_rate > 95.0, f"High match rate too low: {high_match_rate:.1f}% (expected >95%)"
    assert low_match_rate > 95.0, f"Low match rate too low: {low_match_rate:.1f}% (expected >95%)"
    
    print(f"\n✅ Test PASSED: Match rates above 95% threshold")


if __name__ == "__main__":
    test_swing_points_legacy_compatibility()