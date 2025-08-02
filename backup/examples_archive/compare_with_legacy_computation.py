"""
Compare First Combo Data with Legacy Computation
Verifies if our GPU-computed data matches legacy processing for dem07_25
"""

import pandas as pd
import numpy as np
from pathlib import Path
import sys

# Add src to path
sys.path.append(str(Path(__file__).parent.parent / 'src'))

# Import legacy computation functions
sys.path.append('/mnt/c/Users/krajcovic/Documents/GitHub/ATS_3/source_repos/ATS_2/combinations_generation')
from local_technical_indicators import compute_macd_from_period_data, compute_atr_from_period_data

def load_legacy_data():
    """Load the same legacy data used by both systems"""
    print("📂 Loading legacy data for comparison...")
    
    legacy_data_path = "/mnt/c/Users/krajcovic/Documents/Testing Data/backtest_data/dem07_25_tr_ba_data.parquet"
    
    try:
        tick_data = pd.read_parquet(legacy_data_path)
        print(f"✅ Loaded {len(tick_data):,} tick records")
        print(f"   Date range: {tick_data.index.min()} to {tick_data.index.max()}")
        return tick_data
    except Exception as e:
        print(f"❌ Error loading legacy data: {e}")
        return None

def convert_to_legacy_format(tick_data):
    """Convert tick data to legacy period format"""
    print("🔄 Converting to legacy period format...")
    
    # Reset index to get datetime column
    period_data = tick_data.reset_index()
    period_data.rename(columns={period_data.columns[0]: 'datetime'}, inplace=True)
    
    # Add required columns for legacy functions
    if 'tradeid' not in period_data.columns:
        period_data['tradeid'] = 'T' + period_data.index.astype(str)
    if 'nanotime' not in period_data.columns:
        period_data['nanotime'] = period_data.index
    
    # Wrap in dictionary format expected by legacy functions
    period_dict = {'period_1': period_data}
    
    print(f"✅ Converted to legacy format: {len(period_data):,} records")
    return period_dict

def compute_legacy_macd(period_data, macd_params):
    """Compute MACD using legacy function"""
    print(f"🧮 Computing legacy MACD with params: {macd_params}")
    
    macd_result = compute_macd_from_period_data(
        period_data=period_data,
        granularity='15min',
        se=macd_params['short'],
        le=macd_params['long'], 
        cont=macd_params['signal']
    )
    
    return macd_result['period_1']

def compute_legacy_atr(period_data, atr_lookback):
    """Compute ATR using legacy function"""
    print(f"🧮 Computing legacy ATR with lookback: {atr_lookback}")
    
    atr_result = compute_atr_from_period_data(
        period_data=period_data,
        granularity='15min',
        atr_lookback=atr_lookback
    )
    
    return atr_result['period_1']

def load_our_combo_data():
    """Load our first combo result"""
    print("📊 Loading our combo_000 data...")
    
    try:
        combo_data = pd.read_parquet('/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data/data/combo_000.parquet')
        metadata = pd.read_parquet('/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data/combinations_metadata.parquet')
        combo_0_params = metadata[metadata['combo_id'] == 0].iloc[0]
        
        print(f"✅ Loaded combo_000: {combo_data.shape}")
        print(f"   MACD params: short={combo_0_params['macd_short']}, long={combo_0_params['macd_long']}, signal={combo_0_params['macd_signal']}")
        print(f"   ATR lookback: {combo_0_params['atr_lookback']}")
        
        return combo_data, combo_0_params
    except Exception as e:
        print(f"❌ Error loading combo data: {e}")
        return None, None

def compare_values(our_data, legacy_data, column_mapping, tolerance=1e-6):
    """Compare values between our data and legacy data"""
    print("🔍 Comparing computed values...")
    
    results = {}
    
    for our_col, legacy_col in column_mapping.items():
        if our_col not in our_data.columns:
            print(f"⚠️  Column {our_col} not found in our data")
            continue
        if legacy_col not in legacy_data.columns:
            print(f"⚠️  Column {legacy_col} not found in legacy data")
            continue
        
        # Get non-null values for comparison
        our_values = our_data[our_col].dropna()
        legacy_values = legacy_data[legacy_col].dropna()
        
        # Align by taking minimum length
        min_len = min(len(our_values), len(legacy_values))
        if min_len == 0:
            print(f"⚠️  No valid values for comparison in {our_col}")
            continue
        
        our_subset = our_values.iloc[:min_len]
        legacy_subset = legacy_values.iloc[:min_len]
        
        # Calculate differences
        abs_diff = np.abs(our_subset - legacy_subset)
        max_diff = abs_diff.max()
        mean_diff = abs_diff.mean()
        
        # Check if values match within tolerance
        matches = abs_diff <= tolerance
        match_rate = matches.sum() / len(matches) * 100
        
        results[our_col] = {
            'legacy_col': legacy_col,
            'max_diff': max_diff,
            'mean_diff': mean_diff,
            'match_rate': match_rate,
            'compared_values': min_len,
            'matches_tolerance': match_rate >= 95.0
        }
        
        status = "✅ MATCH" if match_rate >= 95.0 else "❌ MISMATCH"
        print(f"   {status} {our_col} vs {legacy_col}:")
        print(f"     Values compared: {min_len}")
        print(f"     Max difference: {max_diff:.2e}")
        print(f"     Mean difference: {mean_diff:.2e}")
        print(f"     Match rate: {match_rate:.1f}%")
        
        # Show sample values for debugging
        if match_rate < 95.0:
            print(f"     Sample our values: {our_subset.head(3).values}")
            print(f"     Sample legacy values: {legacy_subset.head(3).values}")
    
    return results

def main():
    """Main comparison function"""
    print("🔬 LEGACY DATA COMPUTATION COMPARISON")
    print("=" * 60)
    print("This script compares our GPU-computed combo_000 data")
    print("with the same computation using legacy functions")
    print()
    
    # Load legacy tick data
    tick_data = load_legacy_data()
    if tick_data is None:
        return False
    
    # Load our combo data and parameters
    our_data, our_params = load_our_combo_data()
    if our_data is None or our_params is None:
        return False
    
    # Convert legacy data to period format
    period_data = convert_to_legacy_format(tick_data)
    
    # Extract parameters from our combo
    macd_params = {
        'short': int(our_params['macd_short']),
        'long': int(our_params['macd_long']),
        'signal': int(our_params['macd_signal'])
    }
    atr_lookback = int(our_params['atr_lookback'])
    
    print(f"\n📋 Comparison Parameters:")
    print(f"   MACD: {macd_params}")
    print(f"   ATR lookback: {atr_lookback}")
    print()
    
    # Compute legacy MACD
    try:
        legacy_macd = compute_legacy_macd(period_data, macd_params)
        print(f"✅ Legacy MACD computed: {len(legacy_macd):,} records")
    except Exception as e:
        print(f"❌ Error computing legacy MACD: {e}")
        return False
    
    # Compute legacy ATR
    try:
        legacy_atr = compute_legacy_atr(period_data, atr_lookback)
        print(f"✅ Legacy ATR computed: {len(legacy_atr):,} records")
    except Exception as e:
        print(f"❌ Error computing legacy ATR: {e}")
        return False
    
    # Merge legacy results
    legacy_combined = pd.merge(legacy_macd, legacy_atr, on=['tradeid', 'datetime', 'nanotime'], how='inner')
    print(f"✅ Combined legacy data: {len(legacy_combined):,} records")
    
    print(f"\n📊 Data Overview:")
    print(f"   Our data shape: {our_data.shape}")
    print(f"   Legacy data shape: {legacy_combined.shape}")
    print(f"   Our columns: {list(our_data.columns)}")
    print(f"   Legacy columns: {list(legacy_combined.columns)}")
    
    # Compare MACD values
    print(f"\n🔍 COMPARISON RESULTS:")
    print("=" * 40)
    
    column_mapping = {
        'macd_line': 'macd',
        'macd_signal': 'signal', 
        'macd_histogram': 'hist',
        'atr': 'atr'
    }
    
    comparison_results = compare_values(our_data, legacy_combined, column_mapping, tolerance=1e-4)
    
    # Summary
    print(f"\n📈 SUMMARY:")
    print("=" * 30)
    
    total_comparisons = len(comparison_results)
    successful_matches = sum(1 for r in comparison_results.values() if r['matches_tolerance'])
    
    print(f"   Total comparisons: {total_comparisons}")
    print(f"   Successful matches: {successful_matches}")
    print(f"   Overall success rate: {successful_matches/total_comparisons*100:.1f}%")
    
    if successful_matches == total_comparisons:
        print(f"\n🎉 SUCCESS! Our GPU computation matches legacy processing")
        print(f"✅ All {total_comparisons} indicators computed correctly")
    else:
        print(f"\n⚠️  PARTIAL MATCH: {successful_matches}/{total_comparisons} indicators match")
        print("🔧 Further investigation needed for mismatched indicators")
    
    return successful_matches == total_comparisons

if __name__ == "__main__":
    success = main()
    
    if success:
        print(f"\n🎊 VERIFICATION COMPLETE: Data consistency confirmed!")
    else:
        print(f"\n🔍 VERIFICATION INCOMPLETE: Some differences detected")