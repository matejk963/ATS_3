#!/usr/bin/env python3
"""
Fix First 50 Combo Files
Regenerate combo_000 through combo_049 using actual legacy functions
"""

import time
import pandas as pd
import numpy as np
from pathlib import Path
import sys
import warnings
warnings.filterwarnings('ignore')

# Add legacy functions path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root / "src"))
sys.path.append(str(project_root / "source_repos" / "EnergyTrading" / "Python" / "Utilities"))
sys.path.append(str(project_root / "source_repos" / "EnergyTrading" / "Python"))

# Import legacy implementations
try:
    from predictors_tools import (
        compute_realtime_atr,
        compute_realtime_macd,
        detect_swing_points
    )
    print("✅ Legacy functions imported successfully")
except ImportError as e:
    print(f"❌ Could not import legacy functions: {e}")
    sys.exit(1)

def load_prepared_data():
    """Load and prepare data for combo generation"""
    print("📂 Loading and preparing data...")
    
    legacy_data_path = "/mnt/c/Users/krajcovic/Documents/Testing Data/backtest_data/dem07_25_tr_ba_data.parquet"
    
    # Load tick data
    tick_data = pd.read_parquet(legacy_data_path)
    print(f"✅ Loaded tick data: {len(tick_data):,} rows")
    
    # Convert to 15-minute OHLCV candles
    ohlcv_data = tick_data['price'].resample('15T').agg({
        'open': 'first',
        'high': 'max', 
        'low': 'min',
        'close': 'last'
    }).dropna()
    
    # Add volume
    if 'volume' in tick_data.columns:
        volume_data = tick_data['volume'].resample('15T').sum()
        ohlcv_data['volume'] = volume_data.fillna(0)
    else:
        ohlcv_data['volume'] = np.random.exponential(1500, len(ohlcv_data))
    
    # Reset index to get timestamp column
    historical_candles = ohlcv_data.reset_index()
    historical_candles.rename(columns={'index': 'timestamp'}, inplace=True)
    
    # Create trades format for legacy functions
    trades_df = tick_data[['price']].reset_index()
    trades_df.columns = ['datetime', 'price']
    trades_df['nanotime'] = trades_df.index
    trades_df['tradeid'] = 'T' + trades_df.index.astype(str)
    
    # Set up historical candles with proper datetime index
    hist_candles = historical_candles.set_index('timestamp')
    hist_candles.index = pd.to_datetime(hist_candles.index)
    
    # Create swing points once
    print("📈 Computing swing points...")
    swing_points = detect_swing_points(hist_candles)
    print(f"✅ Data preparation complete")
    
    return trades_df, hist_candles, historical_candles, swing_points

def fix_combo_file(combo_id, trades_df, hist_candles, historical_candles, swing_points, 
                  combinations, output_dir):
    """Fix a single combo file using legacy functions"""
    combo = combinations[combo_id]
    
    try:
        # Extract parameters
        macd_short = combo['macd_params']['short']
        macd_long = combo['macd_params']['long']
        macd_signal = combo['macd_params']['signal']
        atr_period = combo['atr_lookback']
        
        # Use ACTUAL legacy functions
        legacy_macd = compute_realtime_macd(
            trades_df=trades_df,
            historical_candles=hist_candles,
            se=macd_short,
            le=macd_long,
            signal_period=macd_signal,
            price_col='price',
            datetime_col='datetime',
            candle_granularity='15min'
        )
        
        legacy_atr = compute_realtime_atr(
            trades_df=trades_df,
            historical_candles=hist_candles,
            atr_period=atr_period,
            price_col='price',
            datetime_col='datetime',
            candle_granularity='15min'
        )
        
        # Create result data (same process as optimized generator)
        result_data = historical_candles.copy()
        
        # Convert legacy results to candle periods
        legacy_macd['period'] = pd.to_datetime(legacy_macd['datetime']).dt.floor('15min')
        legacy_atr['period'] = pd.to_datetime(legacy_atr['datetime']).dt.floor('15min')
        
        # Take last value in each period
        macd_candle = legacy_macd.groupby('period')[['macd', 'signal', 'hist']].last().reset_index()
        atr_candle = legacy_atr.groupby('period')['atr'].last().reset_index()
        
        # Merge with result_data
        result_data = result_data.merge(macd_candle, left_on='timestamp', right_on='period', how='left')
        result_data = result_data.merge(atr_candle, left_on='timestamp', right_on='period', how='left')
        
        # Add swing points data
        result_data = result_data.merge(swing_points.reset_index(), left_on='timestamp', right_on='timestamp', how='left')
        
        # Clean up merge columns
        result_data = result_data.drop(columns=['period_x', 'period_y'], errors='ignore')
        
        # Rename columns to match expected combo format
        column_renames = {
            'macd': 'macd_line',
            'signal': 'macd_signal', 
            'hist': 'macd_histogram'
        }
        result_data = result_data.rename(columns=column_renames)
        
        # Add bias classification and position signals (same as before)
        bias_thresholds = combo['bias_thresholds']
        result_data['bias_classification'] = 'neutral'
        if 'macd_line' in result_data.columns:
            result_data.loc[result_data['macd_line'] > bias_thresholds['macd_line_upper'], 'bias_classification'] = 'bullish'
            result_data.loc[result_data['macd_line'] < bias_thresholds['macd_line_lower'], 'bias_classification'] = 'bearish'
        
        strategy_thresholds = combo['strategy_thresholds']
        result_data['position_signal'] = 'hold'
        
        if 'macd_histogram' in result_data.columns:
            bullish_mask = result_data['bias_classification'] == 'bullish'
            bearish_mask = result_data['bias_classification'] == 'bearish'
            neutral_mask = result_data['bias_classification'] == 'neutral'
            
            macd_positive = result_data['macd_histogram'] > 0
            macd_negative = result_data['macd_histogram'] < 0
            
            result_data.loc[bullish_mask & macd_positive, 'position_signal'] = 'buy'
            result_data.loc[neutral_mask & macd_positive, 'position_signal'] = 'buy'
            result_data.loc[bearish_mask & macd_negative, 'position_signal'] = 'sell'
            result_data.loc[neutral_mask & macd_negative, 'position_signal'] = 'sell'
        
        # Add combo metadata
        result_data['combo_id'] = combo_id
        result_data['contract'] = combo['contract']
        result_data['macd_short'] = macd_short
        result_data['macd_long'] = macd_long
        result_data['macd_signal_period'] = macd_signal
        result_data['atr_period'] = atr_period
        result_data['stop_loss'] = combo['stop_loss']
        result_data['take_profit'] = combo['tp_value']
        
        # Save combo file
        combo_file = output_dir / f"combo_{combo_id:03d}.parquet"
        result_data.to_parquet(combo_file, index=False)
        
        return True
        
    except Exception as e:
        print(f"   ❌ Error fixing combo {combo_id}: {e}")
        return False

def main():
    """Fix the first 50 combo files"""
    print("🔧 FIX FIRST 50 COMBO FILES")
    print("=" * 50)
    print("Regenerating combo_000 through combo_049 using ACTUAL legacy functions")
    
    # Load existing combinations metadata
    metadata = pd.read_parquet('/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data/combinations_metadata.parquet')
    
    # Convert metadata back to combinations format
    combinations = []
    for _, row in metadata.iterrows():
        combo = {
            'combo_id': int(row.combo_id),
            'macd_params': {
                'short': int(row.macd_short),
                'long': int(row.macd_long),
                'signal': int(row.macd_signal)
            },
            'atr_lookback': int(row.atr_lookback),
            'bias_thresholds': {
                'macd_line_lower': row.bias_macd_line_lower,
                'macd_line_upper': row.bias_macd_line_upper,
                'macd_histogram_lower': row.bias_macd_hist_lower,
                'macd_histogram_upper': row.bias_macd_hist_upper
            },
            'strategy_thresholds': {
                'neutral_buy': row.strategy_neutral_buy,
                'neutral_sell': row.strategy_neutral_sell
            },
            'stop_loss': row.stop_loss,
            'tp_value': row.tp_value,
            'contract': row.contract
        }
        combinations.append(combo)
    
    print(f"✅ Loaded {len(combinations)} combination parameters from metadata")
    
    # Prepare data
    trades_df, hist_candles, historical_candles, swing_points = load_prepared_data()
    
    # Output directory
    output_dir = Path("/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data/data")
    
    # Fix first 50 combo files
    print(f"\\n🔧 Fixing combo files 000-049...")
    
    start_time = time.time()
    fixed_count = 0
    
    for combo_id in range(50):
        print(f"   🔄 Fixing combo_{combo_id:03d}...", end="")
        
        success = fix_combo_file(combo_id, trades_df, hist_candles, historical_candles, 
                                swing_points, combinations, output_dir)
        
        if success:
            fixed_count += 1
            print(" ✅")
        else:
            print(" ❌")
    
    total_time = time.time() - start_time
    
    print(f"\\n📊 RESULTS:")
    print(f"   Fixed combo files: {fixed_count}/50")
    print(f"   Processing time: {total_time:.2f}s")
    print(f"   Average time per combo: {total_time/50:.2f}s")
    
    if fixed_count == 50:
        print(f"\\n🎉 SUCCESS: All 50 combo files fixed!")
        print(f"✅ Combo files 000-049 now use actual legacy functions")
        return True
    else:
        print(f"\\n⚠️  PARTIAL SUCCESS: {fixed_count}/50 combo files fixed")
        return False

if __name__ == "__main__":
    success = main()
    
    if success:
        print(f"\\n🎊 FIRST 50 COMBOS FIXED!")
    else:
        print(f"\\n💥 FIXING INCOMPLETE")