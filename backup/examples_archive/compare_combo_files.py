#!/usr/bin/env python3
"""
Compare Combo Files
Direct comparison between main combo files and test legacy combo files
"""

import pandas as pd
import numpy as np

def compare_combo_files():
    """Compare main combo_000 with test_legacy combo_000"""
    print("🔍 DIRECT COMBO FILE COMPARISON")
    print("=" * 50)
    
    # Load main combo_000
    main_combo = pd.read_parquet('/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data/data/combo_000.parquet')
    print(f"✅ Loaded main combo_000: {main_combo.shape}")
    print(f"   Columns: {list(main_combo.columns)}")
    
    # Load test legacy combo_000  
    test_combo = pd.read_parquet('/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data/test_legacy/legacy_combo_000.parquet')
    print(f"✅ Loaded test legacy combo_000: {test_combo.shape}")
    print(f"   Columns: {list(test_combo.columns)}")
    
    # Check parameters
    print(f"\\n📋 Parameter Comparison:")
    if 'macd_short' in main_combo.columns and 'macd_short' in test_combo.columns:
        main_params = (main_combo['macd_short'].iloc[0], main_combo['macd_long'].iloc[0], main_combo['macd_signal_period'].iloc[0])
        test_params = (test_combo['macd_short'].iloc[0], test_combo['macd_long'].iloc[0], test_combo['macd_signal_period'].iloc[0])
        print(f"   Main MACD params: {main_params}")
        print(f"   Test MACD params: {test_params}")
        print(f"   MACD params match: {main_params == test_params}")
        
        main_atr = main_combo['atr_period'].iloc[0]
        test_atr = test_combo['atr_period'].iloc[0]
        print(f"   Main ATR period: {main_atr}")
        print(f"   Test ATR period: {test_atr}")
        print(f"   ATR period match: {main_atr == test_atr}")
    
    # Compare MACD values directly
    print(f"\\n🔍 MACD Value Comparison:")
    if 'macd_line' in main_combo.columns and 'macd_line' in test_combo.columns:
        main_macd = main_combo['macd_line'].dropna()
        test_macd = test_combo['macd_line'].dropna()
        
        min_len = min(len(main_macd), len(test_macd))
        if min_len > 0:
            main_subset = main_macd.iloc[:min_len]
            test_subset = test_macd.iloc[:min_len]
            
            abs_diff = np.abs(main_subset - test_subset)
            match_rate = (abs_diff <= 1e-10).sum() / len(abs_diff) * 100
            
            print(f"   MACD values compared: {min_len}")
            print(f"   Max difference: {abs_diff.max():.2e}")
            print(f"   Mean difference: {abs_diff.mean():.2e}")
            print(f"   Match rate: {match_rate:.1f}%")
            print(f"   First 5 main values: {main_subset.head(5).values}")
            print(f"   First 5 test values: {test_subset.head(5).values}")
            print(f"   First 5 differences: {abs_diff.head(5).values}")
            
            if match_rate >= 99.0:
                print(f"   ✅ MACD values match!")
            else:
                print(f"   ❌ MACD values don't match")
    
    # Compare ATR values directly
    print(f"\\n🔍 ATR Value Comparison:")
    if 'atr' in main_combo.columns and 'atr' in test_combo.columns:
        main_atr = main_combo['atr'].dropna()
        test_atr = test_combo['atr'].dropna()
        
        min_len = min(len(main_atr), len(test_atr))
        if min_len > 0:
            main_subset = main_atr.iloc[:min_len]
            test_subset = test_atr.iloc[:min_len]
            
            abs_diff = np.abs(main_subset - test_subset)
            match_rate = (abs_diff <= 1e-10).sum() / len(abs_diff) * 100
            
            print(f"   ATR values compared: {min_len}")
            print(f"   Max difference: {abs_diff.max():.2e}")
            print(f"   Mean difference: {abs_diff.mean():.2e}")
            print(f"   Match rate: {match_rate:.1f}%")
            print(f"   First 5 main values: {main_subset.head(5).values}")
            print(f"   First 5 test values: {test_subset.head(5).values}")
            print(f"   First 5 differences: {abs_diff.head(5).values}")
            
            if match_rate >= 99.0:
                print(f"   ✅ ATR values match!")
            else:
                print(f"   ❌ ATR values don't match")

if __name__ == "__main__":
    compare_combo_files()