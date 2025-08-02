"""
Fixed DateTime Technical Indicators Plot
=======================================

Creates a plot using only the actual datetime points from the dataset,
no calendar gaps or missing trading periods.
"""

import sys
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
from pathlib import Path

# Add paths for imports
sys.path.append('src')

from technical_indicators.unified_pipeline import UnifiedTechnicalIndicatorsPipeline

def load_production_data():
    """Load production data and create 15-minute candles."""
    print("📊 Loading production data...")
    
    data_path = Path("/mnt/c/Users/krajcovic/Documents/Testing Data/backtest_data/dem07_25_tr_ba_data.parquet")
    
    if not data_path.exists():
        print(f"❌ Production data file not found: {data_path}")
        return create_sample_data()
    
    try:
        raw_data = pd.read_parquet(data_path)
        price_col = 'price' if 'price' in raw_data.columns else 'trd_price'
        
        # Create 15-minute OHLC bars
        ohlc_data = raw_data.resample('15min').agg({
            price_col: ['first', 'max', 'min', 'last'],
            'volume': 'sum'
        }).dropna()
        
        ohlc_data.columns = ['open', 'high', 'low', 'close', 'volume']
        
        # Filter to trading hours
        ohlc_data = ohlc_data[
            (ohlc_data.index.hour >= 8) & 
            (ohlc_data.index.hour < 18)
        ].dropna()
        
        print(f"📊 Created {len(ohlc_data)} 15-min bars")
        print(f"📅 Date range: {ohlc_data.index[0]} to {ohlc_data.index[-1]}")
        return ohlc_data
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return create_sample_data()

def create_sample_data():
    """Create sample data if production data not available."""
    print("🔧 Creating sample data...")
    
    # Create only trading days and hours
    trading_days = pd.bdate_range('2024-06-01', '2024-06-30')  # Business days only
    timestamps = []
    
    for day in trading_days:
        day_times = pd.date_range(
            day.replace(hour=8), 
            day.replace(hour=17, minute=45), 
            freq='15min'
        )
        timestamps.extend(day_times)
    
    timestamps = pd.DatetimeIndex(timestamps)
    
    np.random.seed(42)
    n = len(timestamps)
    
    # Create realistic price data
    base_price = 75.0
    daily_pattern = 8 * np.sin(2 * np.pi * (np.arange(n) * 0.25 % 24 - 6) / 24)
    trend = np.linspace(0, 10, n)
    random_walk = np.cumsum(np.random.randn(n) * 0.4)
    
    close_prices = base_price + daily_pattern + trend + random_walk
    
    volatility = 1.5 + 0.3 * np.abs(np.random.randn(n))
    highs = close_prices + np.abs(np.random.randn(n)) * volatility
    lows = close_prices - np.abs(np.random.randn(n)) * volatility
    opens = close_prices + np.random.randn(n) * 0.5
    
    # Ensure OHLC relationships
    highs = np.maximum(highs, np.maximum(opens, close_prices))
    lows = np.minimum(lows, np.minimum(opens, close_prices))
    
    data = pd.DataFrame({
        'open': opens,
        'high': highs,
        'low': lows,
        'close': close_prices,
        'volume': np.random.randint(100, 500, n)
    }, index=timestamps)
    
    print(f"📊 Created {len(data)} sample bars")
    return data

def compute_indicators(data):
    """Compute technical indicators."""
    print(f"🚀 Computing indicators on {len(data)} data points...")
    
    pipeline = UnifiedTechnicalIndicatorsPipeline()
    
    result = pipeline.compute_indicators(
        data=data,
        indicators=['macd', 'atr', 'swing_points'],
        macd_params={'fast': 12, 'slow': 26, 'signal': 9},
        atr_period=21,
        swing_lookback=20
    )
    
    # Convert swing points to price values
    if 'swing_highs' in result.columns and 'swing_lows' in result.columns:
        swing_high_prices = pd.Series(index=result.index, dtype=float)
        swing_low_prices = pd.Series(index=result.index, dtype=float)
        
        swing_high_mask = result['swing_highs'].astype(bool)
        swing_low_mask = result['swing_lows'].astype(bool)
        
        swing_high_prices[swing_high_mask] = result.loc[swing_high_mask, 'high']
        swing_low_prices[swing_low_mask] = result.loc[swing_low_mask, 'low']
        
        result['swing_high_prices'] = swing_high_prices
        result['swing_low_prices'] = swing_low_prices
    
    print(f"✅ Indicators computed successfully")
    return result

def create_trading_time_plot(data, indicators):
    """Create plot using only actual trading datetime points."""
    print("📊 Creating plot with only actual trading datetime points...")
    
    # Filter to periods with actual values (remove initial NaN periods)
    valid_macd = indicators['macd_line'].notna()
    valid_atr = indicators['atr'].notna()
    
    # Find first valid index where both indicators have values
    first_valid_idx = None
    for i, (macd_valid, atr_valid) in enumerate(zip(valid_macd, valid_atr)):
        if macd_valid and atr_valid:
            first_valid_idx = i
            break
    
    if first_valid_idx is None:
        first_valid_idx = 0
    
    # Use only periods with valid data
    plot_data = data.iloc[first_valid_idx:].copy()
    plot_indicators = indicators.iloc[first_valid_idx:].copy()
    
    print(f"📊 Plotting {len(plot_data)} actual trading periods")
    
    # Create sequential integer index for x-axis (no gaps)
    x_positions = np.arange(len(plot_data))
    
    # Create figure with 3 stacked subplots
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(18, 12), sharex=True)
    fig.subplots_adjust(hspace=0.1)
    
    # 1. Price Chart with Swing Points
    ax = ax1
    
    # Plot price line using sequential positions
    ax.plot(x_positions, plot_data['close'], 'black', linewidth=1.5, label='Close Price')
    
    # Add high/low envelope
    ax.fill_between(x_positions, plot_data['low'], plot_data['high'], 
                    alpha=0.15, color='lightgray', label='High-Low Range')
    
    # Add swing points
    if 'swing_high_prices' in plot_indicators.columns:
        swing_highs = plot_indicators['swing_high_prices'].dropna()
        if len(swing_highs) > 0:
            # Get x positions for swing points
            swing_high_positions = [x_positions[plot_indicators.index.get_loc(idx)] for idx in swing_highs.index]
            ax.scatter(swing_high_positions, swing_highs.values, 
                      color='red', marker='^', s=80, alpha=0.9, 
                      label=f'Swing Highs ({len(swing_highs)})', zorder=5)
    
    if 'swing_low_prices' in plot_indicators.columns:
        swing_lows = plot_indicators['swing_low_prices'].dropna()
        if len(swing_lows) > 0:
            # Get x positions for swing points
            swing_low_positions = [x_positions[plot_indicators.index.get_loc(idx)] for idx in swing_lows.index]
            ax.scatter(swing_low_positions, swing_lows.values,
                      color='blue', marker='v', s=80, alpha=0.9,
                      label=f'Swing Lows ({len(swing_lows)})', zorder=5)
    
    ax.set_title('Price Chart with Swing Points Detection', fontsize=14, fontweight='bold')
    ax.set_ylabel('Price (€/MWh)', fontsize=12)
    ax.legend(loc='upper left', fontsize=10)
    ax.grid(True, alpha=0.3)
    
    # 2. MACD Chart
    ax = ax2
    
    # Plot MACD lines
    ax.plot(x_positions, plot_indicators['macd_line'], 'blue', linewidth=2, label='MACD Line')
    ax.plot(x_positions, plot_indicators['macd_signal'], 'red', linewidth=2, label='Signal Line')
    
    # MACD histogram with colors
    histogram = plot_indicators['macd_histogram']
    positive_mask = histogram >= 0
    negative_mask = histogram < 0
    
    ax.bar(x_positions[positive_mask], histogram[positive_mask], 
           alpha=0.7, color='green', width=1.0, label='Histogram +')
    ax.bar(x_positions[negative_mask], histogram[negative_mask], 
           alpha=0.7, color='red', width=1.0, label='Histogram -')
    
    # Zero line
    ax.axhline(y=0, color='black', linestyle='-', alpha=0.5, linewidth=1)
    
    ax.set_title('MACD (12, 26, 9)', fontsize=14, fontweight='bold')
    ax.set_ylabel('MACD Value', fontsize=12)
    ax.legend(loc='upper left', fontsize=10)
    ax.grid(True, alpha=0.3)
    
    # 3. ATR Chart
    ax = ax3
    
    # Plot ATR
    ax.plot(x_positions, plot_indicators['atr'], 'purple', linewidth=2, label='ATR (21)')
    ax.fill_between(x_positions, 0, plot_indicators['atr'], alpha=0.3, color='purple')
    
    # Add ATR mean line
    atr_mean = plot_indicators['atr'].mean()
    ax.axhline(y=atr_mean, color='orange', linestyle='--', alpha=0.8, 
               linewidth=2, label=f'Mean ATR ({atr_mean:.3f})')
    
    ax.set_title('Average True Range (ATR 21)', fontsize=14, fontweight='bold')
    ax.set_ylabel('ATR Value', fontsize=12)
    ax.set_xlabel('Trading Periods (15-min intervals)', fontsize=12)
    ax.legend(loc='upper left', fontsize=10)
    ax.grid(True, alpha=0.3)
    
    # Custom x-axis labels showing actual dates at regular intervals
    n_labels = 10  # Number of date labels to show
    label_positions = np.linspace(0, len(x_positions)-1, n_labels, dtype=int)
    label_dates = [plot_data.index[i].strftime('%m-%d %H:%M') for i in label_positions]
    
    ax3.set_xticks(label_positions)
    ax3.set_xticklabels(label_dates, rotation=45, ha='right')
    
    # Add overall title and statistics
    total_days = len(set(plot_data.index.date))
    swing_count = (len(plot_indicators['swing_high_prices'].dropna()) + 
                   len(plot_indicators['swing_low_prices'].dropna()))
    
    plt.suptitle(f'Technical Indicators - {len(plot_data)} Trading Periods over {total_days} Days\n' + 
                 f'Price Range: {plot_data["low"].min():.2f} - {plot_data["high"].max():.2f} €/MWh | ' +
                 f'Total Swings: {swing_count} | No Calendar Gaps', 
                 fontsize=16, fontweight='bold', y=0.98)
    
    # Save plot
    output_path = 'uat/trading_periods_only_plot.png'
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"📁 Trading periods plot saved as '{output_path}'")
    
    plt.close()

def main():
    """Main function."""
    print("🚀 Trading Periods Only Technical Indicators Plot")
    print("=" * 60)
    
    # Load data
    data = load_production_data()
    
    # Compute indicators
    indicators = compute_indicators(data)
    
    # Create plot with only trading periods
    create_trading_time_plot(data, indicators)
    
    print("\n✅ Trading periods technical indicators plot completed!")
    print("📊 No calendar gaps - only actual trading datetime points plotted!")

if __name__ == "__main__":
    main()