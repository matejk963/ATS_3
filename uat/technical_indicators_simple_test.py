"""
Simple Technical Indicators Test on Real 15-min Candle Data
=========================================================

This script loads real production data and demonstrates the technical indicators
pipeline with MACD (12,26,9), ATR (21), and swing points detection.
Creates a comprehensive plot showing all computed indicators.
"""

import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

# Add paths for imports
sys.path.append('src')

from technical_indicators.unified_pipeline import UnifiedTechnicalIndicatorsPipeline

def load_15min_candle_data():
    """Load 15-minute candle data from production path."""
    print("📊 Loading 15-minute candle data from production path...")
    
    # Path from the UAT script (line 40)
    data_path = Path("/mnt/c/Users/krajcovic/Documents/Testing Data/backtest_data/dem07_25_tr_ba_data.parquet")
    
    if not data_path.exists():
        print(f"❌ Production data file not found: {data_path}")
        return create_synthetic_data()
    
    try:
        # Load the parquet file (same way as ATS_2 backtests)
        print(f"📂 Loading: {data_path}")
        raw_data = pd.read_parquet(data_path)
        
        print(f"📈 Raw data shape: {raw_data.shape}")
        print(f"📈 Columns: {list(raw_data.columns)}")
        print(f"📅 Full date range: {raw_data.index.min()} to {raw_data.index.max()}")
        
        # Get last week of data for testing
        end_date = raw_data.index.max().date()
        start_date = end_date - pd.Timedelta(days=7)
        
        print(f"📅 Using last week: {start_date} to {end_date}")
        
        # Filter to last week
        week_data = raw_data[
            (raw_data.index.date >= start_date) & 
            (raw_data.index.date <= end_date)
        ].copy()
        
        if len(week_data) == 0:
            print("❌ No data found for the selected week")
            return create_synthetic_data()
        
        # Check available price columns and use the appropriate one
        price_col = None
        for col in ['trd_price', 'price', 'mid_price']:
            if col in week_data.columns:
                price_col = col
                break
        
        if price_col is None:
            print("❌ No suitable price column found")
            return create_synthetic_data()
        
        print(f"📈 Using price column: {price_col}")
        
        # Create 15-minute OHLC bars from tick data
        ohlc_data = week_data.resample('15min').agg({
            price_col: ['first', 'max', 'min', 'last'],
            'volume': 'sum'
        }).dropna()
        
        # Flatten column names
        ohlc_data.columns = ['open', 'high', 'low', 'close', 'volume']
        
        # Ensure we have valid OHLC data and filter trading hours
        ohlc_data = ohlc_data.dropna()
        
        # Filter to trading hours (8:00 - 18:00)
        ohlc_data = ohlc_data[
            (ohlc_data.index.hour >= 8) & 
            (ohlc_data.index.hour < 18)
        ]
        
        if len(ohlc_data) < 50:
            print(f"❌ Insufficient OHLC data ({len(ohlc_data)} bars)")
            return create_synthetic_data()
        
        print(f"📊 Weekly 15-min OHLC data created: {len(ohlc_data)} bars")
        print(f"📈 Price range: {ohlc_data['low'].min():.2f} - {ohlc_data['high'].max():.2f} €/MWh")
        print(f"📅 Time range: {ohlc_data.index[0]} to {ohlc_data.index[-1]}")
        
        return ohlc_data
        
    except Exception as e:
        print(f"❌ Error loading production data: {e}")
        print("📝 Creating synthetic data as fallback...")
        return create_synthetic_data()

def create_synthetic_data():
    """Create synthetic 15-minute energy market data for testing."""
    print("🔧 Creating synthetic 15-minute energy market data...")
    
    # Create 3 days of 15-minute intervals during trading hours
    timestamps = pd.date_range(
        '2024-07-24 08:00', 
        '2024-07-26 18:00', 
        freq='15min'
    )
    
    # Filter to trading hours only (8:00-18:00)
    timestamps = timestamps[
        (timestamps.hour >= 8) & (timestamps.hour < 18)
    ]
    
    np.random.seed(42)
    n_points = len(timestamps)
    
    # German energy market characteristics
    base_price = 75.0  # €/MWh base price
    
    # Create realistic price patterns
    hours = np.arange(n_points) * 0.25  # 15-min intervals
    
    # Daily pattern (morning ramp, evening peak)
    daily_pattern = (
        8 * np.sin(2 * np.pi * (hours % 24 - 6) / 24) +   # Daily cycle
        4 * np.sin(4 * np.pi * (hours % 24) / 24) +       # Intraday variations
        2 * np.sin(2 * np.pi * hours / (24 * 3))          # 3-day pattern
    )
    
    # Add trend and volatility
    trend = np.linspace(0, 5, n_points)  # Upward trend
    volatility = 1.5 + 0.5 * np.abs(np.random.randn(n_points))
    random_walk = np.cumsum(np.random.randn(n_points) * 0.4)
    
    # Calculate close prices
    close_prices = base_price + daily_pattern + trend + random_walk
    
    # Generate realistic OHLC
    highs = close_prices + np.abs(np.random.randn(n_points)) * volatility
    lows = close_prices - np.abs(np.random.randn(n_points)) * volatility
    opens = close_prices + np.random.randn(n_points) * 0.5
    
    # Ensure OHLC relationships are correct
    highs = np.maximum(highs, np.maximum(opens, close_prices))
    lows = np.minimum(lows, np.minimum(opens, close_prices))
    
    data = pd.DataFrame({
        'open': opens,
        'high': highs,
        'low': lows,
        'close': close_prices,
        'volume': np.random.randint(100, 800, n_points)
    }, index=timestamps)
    
    print(f"📊 Synthetic data created: {len(data)} 15-min bars")
    print(f"📈 Price range: {data['low'].min():.2f} - {data['high'].max():.2f} €/MWh")
    print(f"📅 Time range: {data.index[0]} to {data.index[-1]}")
    
    return data

def compute_technical_indicators(data):
    """Compute MACD (12,26,9), ATR (21), and swing points using GPU pipeline."""
    print(f"\n🚀 Computing technical indicators on {len(data)} data points...")
    
    # Initialize GPU-accelerated pipeline
    pipeline = UnifiedTechnicalIndicatorsPipeline()
    
    # Compute indicators with custom parameters
    result = pipeline.compute_indicators(
        data=data,
        indicators=['macd', 'atr', 'swing_points'],
        macd_params={'fast': 12, 'slow': 26, 'signal': 9},
        atr_period=21,
        swing_lookback=20
    )
    
    print(f"✅ Indicators computed successfully")
    print(f"📊 Result columns: {list(result.columns)}")
    
    # Print some statistics
    macd_signals = result['macd_histogram'].dropna()
    atr_values = result['atr'].dropna()
    swing_highs = result['swing_highs'].dropna()
    swing_lows = result['swing_lows'].dropna()
    
    print(f"📈 MACD histogram range: {macd_signals.min():.4f} to {macd_signals.max():.4f}")
    print(f"📈 ATR average: {atr_values.mean():.3f}")
    print(f"📈 Swing highs detected: {len(swing_highs)}")
    print(f"📈 Swing lows detected: {len(swing_lows)}")
    
    return result

def create_comprehensive_plot(data, indicators):
    """Create comprehensive plot showing price data with all computed indicators."""
    print("\n📊 Creating comprehensive technical indicators plot...")
    
    # Create figure with subplots
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(20, 16))
    fig.suptitle('Technical Indicators Analysis - 15-minute Candles\nMACD (12,26,9) | ATR (21) | Swing Points', 
                 fontsize=16, fontweight='bold')
    
    timestamps = data.index
    
    # Plot 1: Price data with swing points
    ax = ax1
    
    # Plot OHLC candlesticks (simplified)
    ax.plot(timestamps, data['high'], 'lightblue', linewidth=1, label='High', alpha=0.8)
    ax.plot(timestamps, data['low'], 'lightcoral', linewidth=1, label='Low', alpha=0.8)
    ax.plot(timestamps, data['close'], 'black', linewidth=2, label='Close')
    ax.fill_between(timestamps, data['low'], data['high'], alpha=0.1, color='lightgray')
    
    # Add swing points
    if 'swing_highs' in indicators.columns:
        swing_highs = indicators['swing_highs'].dropna()
        if len(swing_highs) > 0:
            ax.scatter(swing_highs.index, swing_highs.values, 
                      color='red', marker='^', s=80, alpha=0.9, 
                      label=f'Swing Highs ({len(swing_highs)})', zorder=5)
    
    if 'swing_lows' in indicators.columns:
        swing_lows = indicators['swing_lows'].dropna()
        if len(swing_lows) > 0:
            ax.scatter(swing_lows.index, swing_lows.values,
                      color='blue', marker='v', s=80, alpha=0.9,
                      label=f'Swing Lows ({len(swing_lows)})', zorder=5)
    
    ax.set_title('Price Data with Swing Points')
    ax.set_ylabel('Price (€/MWh)')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # Plot 2: MACD
    ax = ax2
    
    if all(col in indicators.columns for col in ['macd_line', 'macd_signal', 'macd_histogram']):
        ax.plot(timestamps, indicators['macd_line'], 'blue', linewidth=2, label='MACD Line')
        ax.plot(timestamps, indicators['macd_signal'], 'red', linewidth=2, label='Signal Line')
        
        # MACD histogram
        histogram = indicators['macd_histogram']
        colors = ['green' if x >= 0 else 'red' for x in histogram]
        ax.bar(timestamps, histogram, alpha=0.6, color=colors, width=0.006, label='Histogram')
        
        ax.axhline(y=0, color='black', linestyle='-', alpha=0.3)
    
    ax.set_title('MACD (12, 26, 9)')
    ax.set_ylabel('MACD Value')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # Plot 3: ATR
    ax = ax3
    
    if 'atr' in indicators.columns:
        ax.plot(timestamps, indicators['atr'], 'purple', linewidth=2, label='ATR (21)')
        ax.fill_between(timestamps, 0, indicators['atr'], alpha=0.3, color='purple')
    
    ax.set_title('Average True Range (ATR 21)')
    ax.set_ylabel('ATR Value')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # Plot 4: Volume
    ax = ax4
    
    ax.bar(timestamps, data['volume'], alpha=0.6, color='gray', width=0.006, label='Volume')
    
    # Mark swing points on volume
    if 'swing_highs' in indicators.columns and len(indicators['swing_highs'].dropna()) > 0:
        for timestamp in indicators['swing_highs'].dropna().index:
            ax.axvline(x=timestamp, color='red', alpha=0.4, linestyle='--', linewidth=1)
    
    if 'swing_lows' in indicators.columns and len(indicators['swing_lows'].dropna()) > 0:
        for timestamp in indicators['swing_lows'].dropna().index:
            ax.axvline(x=timestamp, color='blue', alpha=0.4, linestyle='--', linewidth=1)
    
    ax.set_title('Volume with Swing Point Timing')
    ax.set_xlabel('Time')
    ax.set_ylabel('Volume')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # Format x-axis for all plots
    import matplotlib.dates as mdates
    for axis in [ax1, ax2, ax3, ax4]:
        axis.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
        axis.xaxis.set_major_locator(mdates.HourLocator(interval=6))
        axis.tick_params(axis='x', rotation=45)
    
    # Add statistics text
    stats_text = f"""Technical Indicators Summary:
• Data Points: {len(data)} (15-min candles)
• Time Range: {data.index[0].strftime('%Y-%m-%d %H:%M')} to {data.index[-1].strftime('%Y-%m-%d %H:%M')}
• Price Range: {data['low'].min():.2f} - {data['high'].max():.2f} €/MWh
• MACD Parameters: Fast=12, Slow=26, Signal=9
• ATR Period: 21
• Swing Lookback: 20"""

    if 'swing_highs' in indicators.columns and 'swing_lows' in indicators.columns:
        swing_highs_count = len(indicators['swing_highs'].dropna())
        swing_lows_count = len(indicators['swing_lows'].dropna())
        stats_text += f"\n• Swing Highs: {swing_highs_count}\n• Swing Lows: {swing_lows_count}"
    
    ax1.text(0.02, 0.98, stats_text, transform=ax1.transAxes, va='top', ha='left',
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.9),
             fontsize=9, fontfamily='monospace')
    
    plt.tight_layout()
    
    # Save plot
    output_path = 'uat/technical_indicators_comprehensive_test.png'
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"📁 Plot saved as '{output_path}'")
    
    plt.show()

def main():
    """Main test function."""
    print("🚀 Technical Indicators Simple Test on Real 15-min Candle Data")
    print("=" * 80)
    
    # Load 15-minute candle data
    data = load_15min_candle_data()
    
    # Compute technical indicators using GPU pipeline
    indicators = compute_technical_indicators(data)
    
    # Create comprehensive visualization
    create_comprehensive_plot(data, indicators)
    
    print(f"\n{'='*80}")
    print("✅ Technical Indicators Test Completed Successfully!")
    print("📊 All indicators computed using GPU-accelerated pipeline")
    print("📈 Comprehensive plot generated with price data and indicators")
    print("🎯 Test Complete!")

if __name__ == "__main__":
    main()