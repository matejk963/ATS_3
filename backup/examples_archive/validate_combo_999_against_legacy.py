#!/usr/bin/env python3
"""
Validate Combo 999 Against Legacy Code
Compare combo_999.parquet data with exact same computation using predictors_tools legacy functions
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

def load_original_legacy_data():
    """Load the original legacy tick data used to create combo files"""
    print("📂 Loading original legacy tick data...")
    
    legacy_data_path = "/mnt/c/Users/krajcovic/Documents/Testing Data/backtest_data/dem07_25_tr_ba_data.parquet"
    
    try:
        # Load tick data with proper DatetimeIndex (same as final_1000_combo_generator.py)
        tick_data = pd.read_parquet(legacy_data_path)
        print(f"✅ Loaded tick data: {len(tick_data):,} rows")
        
        # Convert to same 15-minute OHLCV format used in combo generation
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
        
        # Reset index to get timestamp column (same as combo generation)
        historical_candles = ohlcv_data.reset_index()
        historical_candles.rename(columns={'index': 'timestamp'}, inplace=True)
        
        # Create trades format for legacy functions (need datetime + price + nanotime + tradeid)
        trades_df = tick_data[['price']].reset_index()
        trades_df.columns = ['datetime', 'price']
        
        # Add required columns for legacy functions
        trades_df['nanotime'] = trades_df.index
        trades_df['tradeid'] = 'T' + trades_df.index.astype(str)
        
        # Set up historical candles with proper datetime index
        hist_candles = historical_candles.set_index('timestamp')
        hist_candles.index = pd.to_datetime(hist_candles.index)
        
        print(f"✅ Created historical candles: {historical_candles.shape}")
        print(f"✅ Created trades data: {trades_df.shape}")
        
        return trades_df, hist_candles, historical_candles
        
    except Exception as e:
        print(f"❌ Failed to load legacy data: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None

def load_combo_999_data():
    """Load combo_999.parquet and its parameters"""
    print("\\n📊 Loading combo_999 data...")
    
    try:
        # Load combo data
        combo_data = pd.read_parquet('/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data/data/combo_999.parquet')
        
        # Load metadata to get exact parameters
        metadata = pd.read_parquet('/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data/combinations_metadata.parquet')
        combo_999 = metadata[metadata['combo_id'] == 999].iloc[0]
        
        print(f"✅ Loaded combo_999: {combo_data.shape}")
        print(f"   MACD params: short={combo_999.macd_short}, long={combo_999.macd_long}, signal={combo_999.macd_signal}")
        print(f"   ATR lookback: {combo_999.atr_lookback}")
        
        return combo_data, combo_999
        
    except Exception as e:
        print(f"❌ Failed to load combo data: {e}")
        return None, None

def compute_legacy_indicators(trades_df, hist_candles, historical_candles, combo_params):
    """Compute indicators using legacy predictors_tools functions"""
    print("\\n🔧 Computing indicators with legacy predictors_tools functions...")
    
    try:
        # Extract parameters
        macd_short = int(combo_params.macd_short)
        macd_long = int(combo_params.macd_long) 
        macd_signal = int(combo_params.macd_signal)
        atr_lookback = int(combo_params.atr_lookback)
        
        print(f"📈 Computing MACD with params: short={macd_short}, long={macd_long}, signal={macd_signal}")
        
        # Compute MACD using legacy function (correct parameters: se, le)
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
        
        print(f"✅ Legacy MACD computed: {legacy_macd.shape}")
        
        print(f"📊 Computing ATR with lookback: {atr_lookback}")
        
        # Compute ATR using legacy function
        legacy_atr = compute_realtime_atr(
            trades_df=trades_df,
            historical_candles=hist_candles,
            atr_period=atr_lookback,
            price_col='price',
            datetime_col='datetime',
            candle_granularity='15min'
        )
        
        print(f"✅ Legacy ATR computed: {legacy_atr.shape}")
        
        # Convert legacy results to candle periods (same as combo generation)
        legacy_macd['period'] = pd.to_datetime(legacy_macd['datetime']).dt.floor('15min')
        legacy_atr['period'] = pd.to_datetime(legacy_atr['datetime']).dt.floor('15min')
        
        # Take last value in each period (most recent for that candle)
        macd_candle = legacy_macd.groupby('period')[['macd', 'signal', 'hist']].last().reset_index()
        atr_candle = legacy_atr.groupby('period')['atr'].last().reset_index()
        
        # Merge with historical candles to create validation data
        validation_data = historical_candles.copy()
        validation_data = validation_data.merge(macd_candle, left_on='timestamp', right_on='period', how='left')
        validation_data = validation_data.merge(atr_candle, left_on='timestamp', right_on='period', how='left')
        
        # Clean up merge columns
        validation_data = validation_data.drop(columns=['period_x', 'period_y'], errors='ignore')
        
        print(f"✅ Legacy computation and aggregation complete")
        print(f"   Validation data shape: {validation_data.shape}")
        
        return validation_data
        
    except Exception as e:
        print(f"❌ Error computing legacy indicators: {e}")
        import traceback
        traceback.print_exc()
        return None

def compare_indicators(combo_data, validation_data, tolerance=1e-10):
    """Compare combo data with legacy computations"""
    print("\\n🔍 Comparing combo data with legacy computations...")
    
    results = {}
    
    # Compare MACD indicators (map combo columns to legacy columns)
    macd_comparisons = {
        'macd_line': 'macd',
        'macd_signal': 'signal', 
        'macd_histogram': 'hist'
    }
    
    print("📈 MACD Comparisons:")
    for combo_col, legacy_col in macd_comparisons.items():
        if combo_col not in combo_data.columns:
            print(f"⚠️  Column {combo_col} not found in combo data")
            continue
        if legacy_col not in validation_data.columns:
            print(f"⚠️  Column {legacy_col} not found in validation data")
            continue
        
        # Get non-null values
        combo_values = combo_data[combo_col].dropna()
        legacy_values = validation_data[legacy_col].dropna()
        
        # Align by taking minimum length
        min_len = min(len(combo_values), len(legacy_values))
        if min_len == 0:
            print(f"⚠️  No valid values for comparison in {combo_col}")
            continue
        
        combo_subset = combo_values.iloc[:min_len]
        legacy_subset = legacy_values.iloc[:min_len]
        
        # Calculate differences
        abs_diff = np.abs(combo_subset - legacy_subset)
        max_diff = abs_diff.max()
        mean_diff = abs_diff.mean()
        
        # Check if values match within tolerance
        matches = abs_diff <= tolerance
        match_rate = matches.sum() / len(matches) * 100
        
        results[combo_col] = {
            'legacy_col': legacy_col,
            'max_diff': max_diff,
            'mean_diff': mean_diff,
            'match_rate': match_rate,
            'compared_values': min_len,
            'matches_tolerance': match_rate >= 95.0
        }
        
        status = "✅ MATCH" if match_rate >= 95.0 else "❌ MISMATCH"
        print(f"   {status} {combo_col} vs {legacy_col}:")
        print(f"     Values compared: {min_len}")
        print(f"     Max difference: {max_diff:.2e}")
        print(f"     Mean difference: {mean_diff:.2e}")
        print(f"     Match rate: {match_rate:.1f}%")
        
        # Show sample values if mismatch
        if match_rate < 95.0:
            print(f"     Sample combo values: {combo_subset.head(3).values}")
            print(f"     Sample legacy values: {legacy_subset.head(3).values}")
            print(f"     Sample differences: {abs_diff.head(3).values}")
    
    # Compare ATR
    print("\\n📊 ATR Comparison:")
    if 'atr' in combo_data.columns and 'atr' in validation_data.columns:
        combo_atr = combo_data['atr'].dropna()
        legacy_atr_values = validation_data['atr'].dropna()
        
        min_len = min(len(combo_atr), len(legacy_atr_values))
        if min_len > 0:
            combo_atr_subset = combo_atr.iloc[:min_len]
            legacy_atr_subset = legacy_atr_values.iloc[:min_len]
            
            abs_diff = np.abs(combo_atr_subset - legacy_atr_subset)
            max_diff = abs_diff.max()
            mean_diff = abs_diff.mean()
            
            matches = abs_diff <= tolerance
            match_rate = matches.sum() / len(matches) * 100
            
            results['atr'] = {
                'legacy_col': 'atr',
                'max_diff': max_diff,
                'mean_diff': mean_diff,
                'match_rate': match_rate,
                'compared_values': min_len,
                'matches_tolerance': match_rate >= 95.0
            }
            
            status = "✅ MATCH" if match_rate >= 95.0 else "❌ MISMATCH"
            print(f"   {status} atr vs atr:")
            print(f"     Values compared: {min_len}")
            print(f"     Max difference: {max_diff:.2e}")
            print(f"     Mean difference: {mean_diff:.2e}")
            print(f"     Match rate: {match_rate:.1f}%")
            
            if match_rate < 95.0:
                print(f"     Sample combo values: {combo_atr_subset.head(3).values}")
                print(f"     Sample legacy values: {legacy_atr_subset.head(3).values}")
                print(f"     Sample differences: {abs_diff.head(3).values}")
        else:
            print("   ⚠️  No valid ATR values for comparison")
    else:
        print("   ⚠️  ATR columns not found for comparison")
    
    return results

def main():
    """Main validation function"""
    print("🔬 COMBO 999 vs LEGACY PREDICTORS_TOOLS VALIDATION")
    print("=" * 70)
    print("This validates combo_999.parquet against exact same computation")
    print("using the correct legacy predictors_tools functions.")
    print()
    
    # Load original legacy data
    trades_df, hist_candles, historical_candles = load_original_legacy_data()
    if trades_df is None or hist_candles is None or historical_candles is None:
        return False
    
    # Load combo_999 data and parameters
    combo_data, combo_params = load_combo_999_data()
    if combo_data is None or combo_params is None:
        return False
    
    # Compute indicators using legacy functions with exact same parameters
    validation_data = compute_legacy_indicators(trades_df, hist_candles, historical_candles, combo_params)
    if validation_data is None:
        return False
    
    # Compare results
    comparison_results = compare_indicators(combo_data, validation_data)
    
    # Summary
    print(f"\\n📈 VALIDATION SUMMARY:")
    print("=" * 40)
    
    total_comparisons = len(comparison_results)
    successful_matches = sum(1 for r in comparison_results.values() if r['matches_tolerance'])
    
    print(f"   Total indicators compared: {total_comparisons}")
    print(f"   Successful matches: {successful_matches}")
    print(f"   Overall success rate: {successful_matches/total_comparisons*100:.1f}%") if total_comparisons > 0 else print("   No comparisons made")
    
    if successful_matches == total_comparisons and total_comparisons > 0:
        print(f"\\n🎉 SUCCESS! Combo 999 matches legacy predictors_tools computation")
        print(f"✅ All {total_comparisons} indicators computed correctly")
        print(f"✅ MACD and ATR generated using correct legacy functions")
    else:
        print(f"\\n⚠️  VALIDATION ISSUES: {successful_matches}/{total_comparisons} indicators match")
        print("❌ Differences detected - combo data does NOT match legacy computation")
        print("🔧 This indicates the combo generation used different algorithms")
        print("💡 Need to regenerate combos using actual predictors_tools functions")
    
    return successful_matches == total_comparisons and total_comparisons > 0

if __name__ == "__main__":
    success = main()
    
    if success:
        print(f"\\n🎊 VALIDATION COMPLETE: Combo 999 verified against legacy code!")
    else:
        print(f"\\n🚨 VALIDATION FAILED: Combo 999 does NOT match legacy computation!")
        print("   The combo files need to be regenerated using correct predictors_tools functions")