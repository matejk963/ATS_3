"""
Basic test of the new real-time ATR implementation
"""

import sys
import os
import pandas as pd
import numpy as np
from pathlib import Path

# Add source directories to path
project_root = Path(__file__).parent
sys.path.append(str(project_root / "src"))
sys.path.append(str(project_root / "source_repos" / "EnergyTrading" / "Python" / "Utilities"))

# Import legacy implementation
from predictors_tools import compute_realtime_atr

# Import GPU implementation
from feature_engineering.array_backend import ArrayBackend
from feature_engineering.atr_calculator import ATRCalculator


def test_basic_implementation():
    """Basic test to see if our implementation runs"""
    print("🧪 Testing Basic Real-time ATR Implementation")
    print("=" * 50)
    
    # Create sample trade data
    np.random.seed(42)
    n_trades = 20
    
    base_time = pd.Timestamp('2025-01-01 00:00:00')
    trade_times = [base_time + pd.Timedelta(minutes=i*15) for i in range(n_trades)]
    
    sample_trades = pd.DataFrame({
        'datetime': trade_times,
        'nanotime': [int(t.timestamp() * 1e9) for t in trade_times],
        'tradeid': [f'T{i:04d}' for i in range(n_trades)],
        'price': 100.0 + np.cumsum(np.random.normal(0, 0.5, n_trades))
    })
    
    # Create sample historical candles
    n_candles = 30
    base_hist_time = pd.Timestamp('2024-12-01 00:00:00')
    candle_times = [base_hist_time + pd.Timedelta(hours=i) for i in range(n_candles)]
    
    base_price = 95.0
    price_changes = np.random.normal(0, 0.3, n_candles)
    close_prices = base_price + np.cumsum(price_changes)
    
    spreads = np.random.uniform(0.1, 1.5, n_candles)
    high_prices = close_prices + spreads * 0.6
    low_prices = close_prices - spreads * 0.4
    
    high_prices = np.maximum(high_prices, close_prices)
    low_prices = np.minimum(low_prices, close_prices)
    open_prices = np.roll(close_prices, 1)
    open_prices[0] = base_price
    
    sample_historical = pd.DataFrame({
        'open': open_prices,
        'high': high_prices,
        'low': low_prices,
        'close': close_prices
    }, index=candle_times)
    
    print(f"📊 Sample data:")
    print(f"   Trades: {len(sample_trades)} records")
    print(f"   Historical candles: {len(sample_historical)} records")
    print(f"   Trade price range: {sample_trades['price'].min():.2f} - {sample_trades['price'].max():.2f}")
    
    # Test legacy implementation
    print(f"\n🔍 Testing legacy implementation...")
    try:
        legacy_result = compute_realtime_atr(
            trades_df=sample_trades,
            historical_candles=sample_historical,
            atr_period=14,
            price_col='price',
            datetime_col='datetime',
            candle_granularity='1h'
        )
        print(f"   ✅ Legacy ATR computed: {len(legacy_result)} results")
        print(f"   ATR range: {legacy_result['atr'].min():.6f} - {legacy_result['atr'].max():.6f}")
    except Exception as e:
        print(f"   ❌ Legacy ATR failed: {e}")
        return
    
    # Test new implementation
    print(f"\n🚀 Testing new GPU implementation...")
    try:
        backend = ArrayBackend('cupy')
        atr_calc = ATRCalculator(backend)
        
        gpu_result = atr_calc.compute_atr(
            trades_df=sample_trades,
            historical_candles=sample_historical,
            atr_period=14,
            price_col='price',
            datetime_col='datetime',
            candle_granularity='1h'
        )
        print(f"   ✅ GPU ATR computed: {len(gpu_result)} results")
        print(f"   ATR range: {gpu_result['atr'].min():.6f} - {gpu_result['atr'].max():.6f}")
        
        # Check column structure
        expected_cols = ['datetime', 'nanotime', 'tradeid', 'atr']
        actual_cols = list(gpu_result.columns)
        print(f"   Columns: {actual_cols}")
        
        if actual_cols == expected_cols:
            print(f"   ✅ Column structure matches expected format")
        else:
            print(f"   ⚠️  Column structure differs. Expected: {expected_cols}")
            
    except Exception as e:
        print(f"   ❌ GPU ATR failed: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Compare results if both worked
    if len(legacy_result) > 0 and len(gpu_result) > 0:
        print(f"\n📈 Comparison Results:")
        
        # Merge results for comparison
        comparison = pd.merge(
            legacy_result[['datetime', 'atr']].rename(columns={'atr': 'legacy_atr'}),
            gpu_result[['datetime', 'atr']].rename(columns={'atr': 'gpu_atr'}),
            on='datetime',
            how='inner'
        )
        
        if len(comparison) > 0:
            # Calculate differences 
            comparison['abs_diff'] = np.abs(comparison['legacy_atr'] - comparison['gpu_atr'])
            comparison['rel_diff'] = comparison['abs_diff'] / np.abs(comparison['legacy_atr'])
            
            valid_comparisons = comparison.dropna()
            
            if len(valid_comparisons) > 0:
                max_abs_diff = valid_comparisons['abs_diff'].max()
                max_rel_diff = valid_comparisons['rel_diff'].max()
                mean_abs_diff = valid_comparisons['abs_diff'].mean()
                
                # Calculate match rate
                tolerance = 1e-6
                matches = valid_comparisons['abs_diff'] < tolerance
                match_rate = matches.sum() / len(matches)
                
                print(f"   Valid comparisons: {len(valid_comparisons)}")
                print(f"   Max absolute difference: {max_abs_diff:.8f}")
                print(f"   Max relative difference: {max_rel_diff:.8f}")
                print(f"   Mean absolute difference: {mean_abs_diff:.8f}")
                print(f"   Match rate (±{tolerance}): {match_rate:.1%}")
                
                # Show sample comparison
                print(f"\n   🔍 Sample comparison (first 5 results):")
                for i in range(min(5, len(valid_comparisons))):
                    row = valid_comparisons.iloc[i]
                    print(f"      [{i}] Legacy: {row['legacy_atr']:10.6f}, GPU: {row['gpu_atr']:10.6f}, Diff: {row['abs_diff']:8.6f}")
                
                if match_rate > 0.99:
                    print(f"   ✅ EXCELLENT: >99% match rate achieved!")
                elif match_rate > 0.90:
                    print(f"   ✅ GOOD: >90% match rate achieved")
                elif match_rate > 0.50:
                    print(f"   ⚠️  MODERATE: >50% match rate achieved")
                else:
                    print(f"   ❌ POOR: <50% match rate - significant algorithmic differences")
            else:
                print(f"   ⚠️  No valid values for comparison after removing NaNs")
        else:
            print(f"   ⚠️  No matching timestamps between legacy and GPU results")


if __name__ == "__main__":
    test_basic_implementation()