"""
Visual UAT for CORRECTED Swing Point Detection - Phase 2.2
=======================================================

This UAT script loads real data from the legacy ATS_2 system and visually compares:
1. CORRECTED legacy swing point detection (lines 18-83)
2. New corrected legacy-compatible implementation  
3. Vectorized implementation

Run this to visually verify that all implementations produce identical results
using the CORRECTED algorithm with proper retroactive placement.
"""

import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Add paths for imports
sys.path.append('/mnt/c/Users/krajcovic/Documents/GitHub/ATS_3/source_repos/ATS_2/EnergyTrading/Python/Utilities')

# Import legacy code
try:
    from predictors_tools import detect_swing_points as legacy_detect_swing_points
    LEGACY_AVAILABLE = True
    print("✅ Legacy ATS_2 code loaded successfully")
except ImportError as e:
    LEGACY_AVAILABLE = False
    print(f"❌ Legacy ATS_2 code not available: {e}")

# Import new implementations
from src.feature_engineering.legacy_swing_detector import LegacySwingDetector
from src.feature_engineering.vectorized_swing_detector import VectorizedSwingDetector

def load_production_data():
    """Load the exact same parquet file used by the production backtest system."""
    from pathlib import Path
    
    print("📊 Loading production ATS_2 trading data...")
    
    # Use the exact same path as backtest_multi_parallel_enhanced.py line 179
    data_path = Path("/mnt/c/Users/krajcovic/Documents/Testing Data/backtest_data/dem07_25_tr_ba_data.parquet")
    
    if not data_path.exists():
        print(f"❌ Production data file not found: {data_path}")
        print("📝 Falling back to synthetic data...")
        return generate_synthetic_data()
    
    try:
        print(f"📂 Loading production data: {data_path}")
        raw_data = pd.read_parquet(data_path)
        
        print(f"📈 Raw data shape: {raw_data.shape}")
        print(f"📈 Columns: {list(raw_data.columns)}")
        print(f"📅 Date range: {raw_data.index.min()} to {raw_data.index.max()}")
        
        # Use last week of trading data
        end_date = raw_data.index.max().date()
        start_date = end_date - pd.Timedelta(days=7)
        
        print(f"📅 Using last week of data: {start_date} to {end_date}")
        
        week_data = raw_data[
            (raw_data.index.date >= start_date) & 
            (raw_data.index.date <= end_date)
        ].copy()
        
        if len(week_data) == 0:
            print("❌ No data found for the selected week")
            return generate_synthetic_data()
        
        # Check for price column (same logic as the other UAT)
        price_col = None
        for col in ['trd_price', 'price', 'mid_price']:
            if col in week_data.columns:
                price_col = col
                break
        
        if price_col is None:
            print("❌ No suitable price column found")
            return generate_synthetic_data()
        
        print(f"📈 Using price column: {price_col}")
        
        # Create OHLC bars from tick data (15-minute bars for detailed weekly view)
        ohlc_data = week_data.resample('15min').agg({
            price_col: ['first', 'max', 'min', 'last'],
            'volume': 'sum'
        }).dropna()
        
        # Flatten column names
        ohlc_data.columns = ['open', 'high', 'low', 'close', 'volume']
        ohlc_data = ohlc_data.dropna()
        
        if len(ohlc_data) < 10:
            print(f"❌ Insufficient OHLC data ({len(ohlc_data)} bars)")
            return generate_synthetic_data()
        
        print(f"📊 Weekly production OHLC data created: {len(ohlc_data)} bars")
        print(f"📈 Price range: {ohlc_data['low'].min():.2f} - {ohlc_data['high'].max():.2f}")
        print(f"📅 Time range: {ohlc_data.index[0]} to {ohlc_data.index[-1]}")
        
        # Return all weekly data
        return ohlc_data
        
    except Exception as e:
        print(f"❌ Error loading production data: {e}")
        print("📝 Falling back to synthetic data...")
        return generate_synthetic_data()

def generate_synthetic_data(n_candles=96):
    """Generate synthetic energy market data as fallback."""
    print("🔧 Generating synthetic energy market data...")
    np.random.seed(42)
    
    # Simulate energy price patterns with intraday cycles
    base_price = 50.0  # €/MWh base price
    
    # Add daily pattern (higher prices during peak hours)
    hours = np.linspace(0, 24, n_candles)
    daily_pattern = 10 * np.sin(2 * np.pi * hours / 24) + 5 * np.sin(4 * np.pi * hours / 24)
    
    # Add trend and random walk
    trend = np.linspace(0, 5, n_candles)
    random_walk = np.cumsum(np.random.randn(n_candles) * 0.8)
    
    # Base prices
    prices = base_price + daily_pattern + trend + random_walk
    
    # Generate OHLC with realistic spreads
    volatility = 1.2
    highs = prices + np.abs(np.random.randn(n_candles) * volatility)
    lows = prices - np.abs(np.random.randn(n_candles) * volatility)
    opens = prices + np.random.randn(n_candles) * 0.3
    closes = prices + np.random.randn(n_candles) * 0.3
    
    # Ensure OHLC consistency
    for i in range(n_candles):
        all_prices = [opens[i], highs[i], lows[i], closes[i]]
        highs[i] = max(all_prices)
        lows[i] = min(all_prices)
    
    # Create timestamps (15-minute intervals)
    timestamps = pd.date_range('2024-01-01 08:00', periods=n_candles, freq='15min')
    
    return pd.DataFrame({
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes
    }, index=timestamps)

def run_visual_uat():
    """Run the visual UAT test."""
    print("🔬 Running Visual UAT for Swing Point Detection")
    print("=" * 60)
    
    # Load production data
    print("📊 Loading production ATS_2 data (same as backtest system)...")
    data = load_production_data()  # Load from dem07_25_tr_ba_data.parquet
    print(f"   Loaded {len(data)} candles of OHLC data")
    
    # Initialize detectors
    legacy_detector = LegacySwingDetector()
    vectorized_detector = VectorizedSwingDetector()
    
    # Run detections
    print("\n🔍 Running swing point detection algorithms...")
    
    results = {}
    
    # Legacy ATS_2 (if available) - CORRECTED: Use full OHLC data
    if LEGACY_AVAILABLE:
        try:
            results['Legacy ATS_2'] = legacy_detect_swing_points(data)
            print("   ✅ Legacy ATS_2 detection completed")
        except Exception as e:
            print(f"   ❌ Legacy ATS_2 detection failed: {e}")
    
    # New legacy-compatible - CORRECTED: Use full OHLC data
    try:
        results['New Legacy Compatible'] = legacy_detector.detect_swing_points(data)
        print("   ✅ New legacy-compatible detection completed")
    except Exception as e:
        print(f"   ❌ New legacy-compatible detection failed: {e}")
    
    # Vectorized - CORRECTED: Use full OHLC data
    try:
        results['Vectorized'] = vectorized_detector.detect_swing_points(data)
        print("   ✅ Vectorized detection completed")
    except Exception as e:
        print(f"   ❌ Vectorized detection failed: {e}")
    
    # Validate results are identical
    print("\n🔬 Validating result consistency...")
    if len(results) > 1:
        result_keys = list(results.keys())
        base_result = results[result_keys[0]]
        
        all_identical = True
        for i in range(1, len(result_keys)):
            key = result_keys[i]
            try:
                pd.testing.assert_frame_equal(
                    base_result, results[key],
                    check_names=False, check_dtype=False
                )
                print(f"   ✅ {result_keys[0]} ≡ {key}")
            except AssertionError as e:
                print(f"   ❌ {result_keys[0]} ≠ {key}: {e}")
                all_identical = False
        
        if all_identical:
            print("   🎉 ALL IMPLEMENTATIONS PRODUCE IDENTICAL RESULTS!")
        else:
            print("   ⚠️  Some implementations differ!")
    
    # Create visualization
    print("\n📈 Creating visualization...")
    create_comparison_plot(data, results)
    
    # Summary statistics - CORRECTED: Proper swing point counting
    print("\n📊 Summary Statistics:")
    for name, result in results.items():
        swing_highs = result['swing_high'].dropna()
        swing_lows = result['swing_low'].dropna()
        
        print(f"   {name}:")
        print(f"      Swing highs detected: {len(swing_highs)}")
        print(f"      Swing lows detected: {len(swing_lows)}")
        print(f"      Total swing points: {len(swing_highs) + len(swing_lows)}")
        print(f"      Price range: {data['low'].min():.2f} - {data['high'].max():.2f} €/MWh")

def create_comparison_plot(data, results):
    """Create comparison plot of all implementations with continuous trading periods."""
    fig, axes = plt.subplots(len(results), 1, figsize=(24, 8 * len(results)))
    if len(results) == 1:
        axes = [axes]
    
    colors = ['blue', 'red', 'green', 'orange']
    
    # Create continuous x-axis positions for trading periods only
    x_positions = range(len(data))
    
    for idx, (name, result) in enumerate(results.items()):
        ax = axes[idx]
        
        # Plot OHLC candlestick data using continuous positions
        for i, (timestamp, row) in enumerate(data.iterrows()):
            x_pos = x_positions[i]
            open_price = row['open']
            high_price = row['high']
            low_price = row['low']
            close_price = row['close']
            
            # Candlestick body
            color = 'green' if close_price >= open_price else 'red'
            ax.plot([x_pos, x_pos], [low_price, high_price], 'k-', linewidth=0.5)
            ax.plot([x_pos, x_pos], [open_price, close_price], color, linewidth=3)
        
        # Plot swing points using continuous positions
        swing_highs = result['swing_high'].dropna()
        swing_lows = result['swing_low'].dropna()
        
        # Create mapping from timestamps to x positions
        timestamp_to_pos = {timestamp: i for i, timestamp in enumerate(data.index)}
        
        # Mark swing highs
        if len(swing_highs) > 0:
            swing_high_positions = [timestamp_to_pos[ts] for ts in swing_highs.index if ts in timestamp_to_pos]
            swing_high_values = [swing_highs[ts] for ts in swing_highs.index if ts in timestamp_to_pos]
            
            ax.scatter(swing_high_positions, swing_high_values, 
                      color='red', marker='^', s=120, label=f'Swing Highs ({len(swing_highs)})', zorder=5)
            
            # Annotate swing high values (limit to avoid clutter)
            for i, (pos, value) in enumerate(zip(swing_high_positions[:12], swing_high_values[:12])):
                ax.annotate(f'{value:.1f}', (pos, value), xytext=(0, 12),
                           textcoords='offset points', ha='center', fontsize=8,
                           color='red', fontweight='bold')
        
        # Mark swing lows  
        if len(swing_lows) > 0:
            swing_low_positions = [timestamp_to_pos[ts] for ts in swing_lows.index if ts in timestamp_to_pos]
            swing_low_values = [swing_lows[ts] for ts in swing_lows.index if ts in timestamp_to_pos]
            
            ax.scatter(swing_low_positions, swing_low_values,
                      color='blue', marker='v', s=120, label=f'Swing Lows ({len(swing_lows)})', zorder=5)
            
            # Annotate swing low values (limit to avoid clutter)
            for i, (pos, value) in enumerate(zip(swing_low_positions[:12], swing_low_values[:12])):
                ax.annotate(f'{value:.1f}', (pos, value), xytext=(0, -15),
                           textcoords='offset points', ha='center', fontsize=8,
                           color='blue', fontweight='bold')
        
        ax.set_title(f'{name} - Swing Point Detection (Trading Periods Only)', fontsize=14, fontweight='bold')
        ax.set_ylabel('Price (€/MWh)', fontsize=12)
        ax.set_xlabel('Trading Period (15-min intervals)')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # Set custom x-axis labels showing dates and times at key intervals
        # Show every Nth label to avoid overcrowding
        label_interval = max(1, len(data) // 12)  # Show ~12 labels max
        tick_positions = list(range(0, len(data), label_interval))
        tick_labels = [data.index[i].strftime('%m-%d %H:%M') for i in tick_positions]
        
        ax.set_xticks(tick_positions)
        ax.set_xticklabels(tick_labels, rotation=45)
        ax.set_xlim(-1, len(data))
    
    plt.xlabel('Time', fontsize=12)
    plt.suptitle('Production ATS_2 Data - Last Week - Swing Point Detection Visual UAT\nUsing dem07_25_tr_ba_data.parquet (CORRECTED Algorithm)', 
                 fontsize=16, fontweight='bold')
    plt.tight_layout()
    
    # Save plot to proper UAT directory
    output_path = '/mnt/c/Users/krajcovic/Documents/GitHub/ATS_3/uat/swing_detection/visual_uat_weekly_15min_continuous.png'
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"   💾 Plot saved to: {output_path}")
    
    # Don't show plot in automated testing - just save it
    print("   📈 Plot generated and saved (not displayed in automated mode)")

if __name__ == "__main__":
    print("🚀 Starting Swing Point Detection Visual UAT")
    print("=" * 60)
    
    try:
        run_visual_uat()
        print("\n✅ Visual UAT completed successfully!")
        print("📋 Check the generated plot to visually verify swing point detection.")
        print("🎯 All implementations should show identical swing point locations.")
        
    except Exception as e:
        print(f"\n❌ UAT failed with error: {e}")
        import traceback
        traceback.print_exc()
        
    print("\n" + "=" * 60)
    print("🏁 UAT Complete")