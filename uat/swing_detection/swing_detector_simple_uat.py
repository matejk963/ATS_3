"""
Simple UAT for CORRECTED Swing Point Detection - Data Table View
=============================================================

This simplified UAT shows a data table comparison of the CORRECTED swing point detection results.
Perfect for quick verification that all implementations produce identical results using the
CORRECTED legacy algorithm (predictors_tools.py lines 18-83).
"""

import sys
import pandas as pd
import numpy as np

# Add paths for imports
sys.path.append('/mnt/c/Users/krajcovic/Documents/GitHub/ATS_3/source_repos/ATS_2/EnergyTrading/Python/Utilities')

# Import legacy code
try:
    from predictors_tools import detect_swing_points as legacy_detect_swing_points
    LEGACY_AVAILABLE = True
except ImportError:
    LEGACY_AVAILABLE = False

# Import new implementations
from src.feature_engineering.legacy_swing_detector import LegacySwingDetector
from src.feature_engineering.vectorized_swing_detector import VectorizedSwingDetector

def run_simple_uat():
    """Run simple UAT with data table output."""
    print("🔬 Simple UAT: Swing Point Detection Data Comparison")
    print("=" * 70)
    
    # Create simple test data (German energy market pattern)
    print("📊 Creating test data (German energy market pattern)...")
    
    # Simulate a typical trading day with morning ramp, afternoon peak, evening decline
    hours = np.arange(0, 24, 0.25)  # 15-minute intervals
    base_price = 45.0  # €/MWh
    
    # Energy market pattern: low at night, peak in evening
    daily_pattern = (
        20 * np.sin(2 * np.pi * (hours - 6) / 24) +  # Main daily cycle
        10 * np.sin(4 * np.pi * (hours - 8) / 24) +  # Intraday variations
        5 * np.random.randn(len(hours))              # Random noise
    )
    
    prices = base_price + daily_pattern
    
    # Generate OHLC with realistic spreads
    np.random.seed(123)
    spread = 1.5
    highs = prices + np.abs(np.random.randn(len(prices)) * spread)
    lows = prices - np.abs(np.random.randn(len(prices)) * spread)
    
    # Take first 20 periods for clear visualization
    data = pd.DataFrame({
        'high': highs[:20],
        'low': lows[:20]
    })
    
    print(f"   Generated {len(data)} periods of OHLC data")
    print(f"   Price range: {data['low'].min():.2f} - {data['high'].max():.2f} €/MWh")
    
    # Run all implementations
    print("\n🔍 Running swing point detection...")
    
    results = {}
    
    # Initialize detectors
    legacy_detector = LegacySwingDetector()
    vectorized_detector = VectorizedSwingDetector()
    
    # Legacy ATS_2
    if LEGACY_AVAILABLE:
        results['Legacy_ATS2'] = legacy_detect_swing_points(data)
        print("   ✅ Legacy ATS_2 completed")
    
    # New implementations
    results['New_Legacy'] = legacy_detector.detect_swing_points(data)
    results['Vectorized'] = vectorized_detector.detect_swing_points(data)
    print("   ✅ All implementations completed")
    
    # Create comparison table
    print("\n📋 Results Comparison Table:")
    print("=" * 70)
    
    # Combine all results into one DataFrame for easy comparison
    comparison_df = pd.DataFrame({
        'Index': range(len(data)),
        'High': data['high'].round(2),
        'Low': data['low'].round(2)
    })
    
    for name, result in results.items():
        comparison_df[f'{name}_SwingHigh'] = result['swing_high'].round(2)
        comparison_df[f'{name}_SwingLow'] = result['swing_low'].round(2)
    
    # Show the table
    print(comparison_df.to_string(index=False))
    
    # Validate identical results
    print("\n🔬 Validation Results:")
    print("-" * 30)
    
    if len(results) > 1:
        result_names = list(results.keys())
        base_result = results[result_names[0]]
        
        all_identical = True
        for i in range(1, len(result_names)):
            name = result_names[i]
            try:
                pd.testing.assert_frame_equal(
                    base_result, results[name],
                    check_names=False, check_dtype=False
                )
                print(f"✅ {result_names[0]} ≡ {name} (IDENTICAL)")
            except AssertionError:
                print(f"❌ {result_names[0]} ≠ {name} (DIFFERENT)")
                all_identical = False
        
        if all_identical:
            print("\n🎉 SUCCESS: ALL IMPLEMENTATIONS PRODUCE IDENTICAL RESULTS!")
        else:
            print("\n⚠️  WARNING: Some implementations differ!")
    
    # Show swing point summary
    print(f"\n📊 Swing Point Summary:")
    print("-" * 30)
    
    for name, result in results.items():
        swing_high_changes = (result['swing_high'] != result['swing_high'].shift(1)).sum()
        swing_low_changes = (result['swing_low'] != result['swing_low'].shift(1)).sum()
        
        print(f"{name}:")
        print(f"   Swing High Changes: {swing_high_changes}")
        print(f"   Swing Low Changes:  {swing_low_changes}")
    
    return comparison_df, results

if __name__ == "__main__":
    try:
        comparison_df, results = run_simple_uat()
        
        print("\n" + "=" * 70)
        print("✅ Simple UAT completed successfully!")
        print("🎯 Review the table above to verify all implementations match exactly.")
        print("📋 Swing points should be identical across all columns.")
        
    except Exception as e:
        print(f"\n❌ UAT failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n🏁 UAT Complete")