#!/usr/bin/env python3
"""
Test pipeline integration with new state-tracking swing detector
"""

import pandas as pd
import numpy as np
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline


def test_pipeline_swing_integration():
    """Test that pipeline works with new swing detector"""
    
    # Create test data
    dates = pd.date_range('2024-01-01', periods=100, freq='1h')
    np.random.seed(42)
    prices = 100 + np.cumsum(np.random.randn(100) * 0.1)
    test_data = pd.DataFrame({
        'open': prices,
        'high': prices + np.random.uniform(0, 0.5, 100),
        'low': prices - np.random.uniform(0, 0.5, 100), 
        'close': prices + np.random.uniform(-0.2, 0.2, 100)
    }, index=dates)
    
    print(f"Testing pipeline with {len(test_data)} data points")
    
    # Initialize pipeline
    pipeline = UnifiedTechnicalIndicatorsPipeline()
    
    # Test swing points computation through pipeline
    print("Running swing points through pipeline...")
    result = pipeline.compute_indicators(test_data, ['swing_points'])
    
    # Validate results
    assert 'swing_highs' in result.columns, "Missing swing_highs column"
    assert 'swing_lows' in result.columns, "Missing swing_lows column"
    assert len(result) == len(test_data), "Result length mismatch"
    
    # Check that we have actual swing values (not all NaN)
    swing_highs = result['swing_highs'].values
    swing_lows = result['swing_lows'].values
    
    high_non_nan = ~np.isnan(swing_highs)
    low_non_nan = ~np.isnan(swing_lows)
    
    print(f"Swing highs: {high_non_nan.sum()}/{len(swing_highs)} non-NaN values")
    print(f"Swing lows: {low_non_nan.sum()}/{len(swing_lows)} non-NaN values")
    
    # Should have some swing points
    assert high_non_nan.sum() > 0, "No swing highs detected"
    assert low_non_nan.sum() > 0, "No swing lows detected"
    
    # For now, only test swing points since MACD needs different setup
    print("Testing swing points only (MACD/ATR require different data format)...")
    
    print("✅ Pipeline integration test PASSED")


if __name__ == "__main__":
    test_pipeline_swing_integration()