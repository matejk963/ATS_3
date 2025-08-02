#!/usr/bin/env python3
"""
Validate Legacy Combo File
Validate that the legacy combo files actually use the correct predictors_tools functions
"""

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

def load_original_data():
    """Load the same data used to create combo files"""
    print("📂 Loading original data...")
    
    legacy_data_path = "/mnt/c/Users/krajcovic/Documents/Testing Data/backtest_data/dem07_25_tr_ba_data.parquet"
    
    # Load tick data
    tick_data = pd.read_parquet(legacy_data_path)
    
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
    
    # Add required columns for legacy functions
    trades_df['nanotime'] = trades_df.index
    trades_df['tradeid'] = 'T' + trades_df.index.astype(str)
    
    # Set up historical candles with proper datetime index
    hist_candles = historical_candles.set_index('timestamp')
    hist_candles.index = pd.to_datetime(hist_candles.index)
    
    print(f"✅ Data loaded and prepared")
    
    return trades_df, hist_candles, historical_candles

def validate_legacy_combo_file(combo_file_path):
    """Validate a legacy combo file against actual legacy computation"""
    print(f"\n🔬 VALIDATING: {combo_file_path}")
    print("=" * 70)
    
    # Load combo file
    combo_data = pd.read_parquet(combo_file_path)
    print(f"✅ Loaded combo data: {combo_data.shape}")
    
    # Extract parameters from combo data
    combo_id = combo_data['combo_id'].iloc[0]
    macd_short = combo_data['macd_short'].iloc[0]
    macd_long = combo_data['macd_long'].iloc[0]
    macd_signal = combo_data['macd_signal_period'].iloc[0]
    atr_period = combo_data['atr_period'].iloc[0]
    
    print(f"📋 Combo parameters:")
    print(f"   Combo ID: {combo_id}")
    print(f"   MACD: short={macd_short}, long={macd_long}, signal={macd_signal}")
    print(f"   ATR: period={atr_period}")
    
    # Load original data
    trades_df, hist_candles, historical_candles = load_original_data()
    
    # Compute with legacy functions using exact same parameters
    print(f"\n🔧 Computing with legacy functions...")
    
    # Compute MACD
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
    
    # Compute ATR
    legacy_atr = compute_realtime_atr(
        trades_df=trades_df,
        historical_candles=hist_candles,
        atr_period=atr_period,
        price_col='price',
        datetime_col='datetime',
        candle_granularity='15min'
    )
    
    # Convert legacy results to candle periods
    legacy_macd['period'] = pd.to_datetime(legacy_macd['datetime']).dt.floor('15min')
    legacy_atr['period'] = pd.to_datetime(legacy_atr['datetime']).dt.floor('15min')
    
    # Take last value in each period (most recent for that candle)
    macd_candle = legacy_macd.groupby('period')[['macd', 'signal', 'hist']].last().reset_index()
    atr_candle = legacy_atr.groupby('period')['atr'].last().reset_index()
    
    # Merge with historical candles for comparison
    validation_data = historical_candles.copy()
    validation_data = validation_data.merge(macd_candle, left_on='timestamp', right_on='period', how='left')
    validation_data = validation_data.merge(atr_candle, left_on='timestamp', right_on='period', how='left')
    
    # Clean up merge columns
    validation_data = validation_data.drop(columns=['period_x', 'period_y'], errors='ignore')
    
    print(f"✅ Legacy computation complete")
    
    # Compare results
    print(f"\n🔍 VALIDATION RESULTS:")
    print("=" * 40)
    
    tolerance = 1e-10
    results = {}
    
    # Compare MACD line
    if 'macd_line' in combo_data.columns and 'macd' in validation_data.columns:
        combo_macd = combo_data['macd_line'].dropna()
        legacy_macd_values = validation_data['macd'].dropna()
        
        min_len = min(len(combo_macd), len(legacy_macd_values))
        if min_len > 0:
            combo_subset = combo_macd.iloc[:min_len]
            legacy_subset = legacy_macd_values.iloc[:min_len]
            
            abs_diff = np.abs(combo_subset - legacy_subset)
            matches = abs_diff <= tolerance
            match_rate = matches.sum() / len(matches) * 100
            
            results['macd_line'] = match_rate
            status = "✅ MATCH" if match_rate >= 95.0 else "❌ MISMATCH"
            print(f"   {status} MACD Line: {match_rate:.1f}% match rate")
            
            if match_rate < 95.0:
                print(f"     Max difference: {abs_diff.max():.2e}")
                print(f"     Sample combo: {combo_subset.head(3).values}")
                print(f"     Sample legacy: {legacy_subset.head(3).values}")
    
    # Compare MACD signal
    if 'macd_signal' in combo_data.columns and 'signal' in validation_data.columns:
        combo_signal = combo_data['macd_signal'].dropna()
        legacy_signal = validation_data['signal'].dropna()
        
        min_len = min(len(combo_signal), len(legacy_signal))
        if min_len > 0:
            combo_subset = combo_signal.iloc[:min_len]
            legacy_subset = legacy_signal.iloc[:min_len]
            
            abs_diff = np.abs(combo_subset - legacy_subset)
            matches = abs_diff <= tolerance
            match_rate = matches.sum() / len(matches) * 100
            
            results['macd_signal'] = match_rate
            status = "✅ MATCH" if match_rate >= 95.0 else "❌ MISMATCH"
            print(f"   {status} MACD Signal: {match_rate:.1f}% match rate")
    
    # Compare MACD histogram
    if 'macd_histogram' in combo_data.columns and 'hist' in validation_data.columns:
        combo_hist = combo_data['macd_histogram'].dropna()
        legacy_hist = validation_data['hist'].dropna()
        
        min_len = min(len(combo_hist), len(legacy_hist))
        if min_len > 0:
            combo_subset = combo_hist.iloc[:min_len]
            legacy_subset = legacy_hist.iloc[:min_len]
            
            abs_diff = np.abs(combo_subset - legacy_subset)
            matches = abs_diff <= tolerance
            match_rate = matches.sum() / len(matches) * 100
            
            results['macd_histogram'] = match_rate
            status = "✅ MATCH" if match_rate >= 95.0 else "❌ MISMATCH"
            print(f"   {status} MACD Histogram: {match_rate:.1f}% match rate")
    
    # Compare ATR
    if 'atr' in combo_data.columns and 'atr' in validation_data.columns:
        combo_atr = combo_data['atr'].dropna()
        legacy_atr_values = validation_data['atr'].dropna()
        
        min_len = min(len(combo_atr), len(legacy_atr_values))
        if min_len > 0:
            combo_subset = combo_atr.iloc[:min_len]
            legacy_subset = legacy_atr_values.iloc[:min_len]
            
            abs_diff = np.abs(combo_subset - legacy_subset)
            matches = abs_diff <= tolerance
            match_rate = matches.sum() / len(matches) * 100
            
            results['atr'] = match_rate
            status = "✅ MATCH" if match_rate >= 95.0 else "❌ MISMATCH"
            print(f"   {status} ATR: {match_rate:.1f}% match rate")
            
            if match_rate < 95.0:
                print(f"     Max difference: {abs_diff.max():.2e}")
                print(f"     Sample combo: {combo_subset.head(3).values}")
                print(f"     Sample legacy: {legacy_subset.head(3).values}")
    
    # Overall assessment
    if results:
        avg_match_rate = sum(results.values()) / len(results)
        perfect_matches = sum(1 for rate in results.values() if rate >= 99.9)
        
        print(f"\n📊 OVERALL ASSESSMENT:")
        print(f"   Indicators tested: {len(results)}")
        print(f"   Average match rate: {avg_match_rate:.1f}%")
        print(f"   Perfect matches (≥99.9%): {perfect_matches}/{len(results)}")
        
        if avg_match_rate >= 95.0:
            print(f"\n🎉 SUCCESS: Combo file uses actual legacy functions!")
            print(f"✅ {perfect_matches}/{len(results)} indicators match perfectly")
            return True
        else:
            print(f"\n❌ VALIDATION FAILED: Combo file does NOT use legacy functions")
            print(f"⚠️  Only {perfect_matches}/{len(results)} indicators match")
            return False
    else:
        print(f"\n⚠️  No indicators could be compared")
        return False

def main():
    """Validate legacy combo files"""
    print("🔬 LEGACY COMBO FILE VALIDATION")
    print("=" * 60)
    
    # Test the legacy combo files we just created
    test_legacy_dir = Path("/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data/test_legacy")
    
    if not test_legacy_dir.exists():
        print(f"❌ Test legacy directory not found: {test_legacy_dir}")
        return False
    
    # Find all legacy combo files
    combo_files = list(test_legacy_dir.glob("legacy_combo_*.parquet"))
    
    if not combo_files:
        print(f"❌ No legacy combo files found in {test_legacy_dir}")
        return False
    
    print(f"📁 Found {len(combo_files)} legacy combo files to validate")
    
    # Validate first combo file
    success = validate_legacy_combo_file(combo_files[0])
    
    return success

if __name__ == "__main__":
    success = main()
    
    if success:
        print(f"\n🎊 VALIDATION SUCCESSFUL!")
        print(f"✅ Legacy combo files use actual predictors_tools functions!")
    else:
        print(f"\n💥 VALIDATION FAILED!")
        print(f"❌ Legacy combo files do NOT use actual predictors_tools functions!")