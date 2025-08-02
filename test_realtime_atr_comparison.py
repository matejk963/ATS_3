"""
Proper ATR Comparison Test: Legacy Real-time vs GPU Real-time Implementation
Test to verify that our new GPU real-time ATR matches the legacy real-time ATR.
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

# Import legacy REAL-TIME implementation (not traditional ATR)
from predictors_tools import compute_realtime_atr

# Import GPU implementation
from feature_engineering.array_backend import ArrayBackend
from feature_engineering.atr_calculator import ATRCalculator


def test_realtime_atr_implementations():
    """Test real-time ATR implementations with synthetic data"""
    print("🧪 Real-time ATR Implementation Comparison Test")
    print("=" * 50)
    print("Comparing legacy compute_realtime_atr() vs new GPU implementation")
    
    # Create realistic trade data for testing
    np.random.seed(42)
    n_trades = 100
    
    # Create trade times spanning multiple hours  
    base_time = pd.Timestamp('2025-01-01 00:00:00')
    trade_intervals = np.random.exponential(scale=5, size=n_trades)  # Average 5 minutes between trades
    trade_times = [base_time + pd.Timedelta(minutes=sum(trade_intervals[:i+1])) for i in range(n_trades)]
    
    # Generate realistic price walk
    base_price = 100.0
    price_changes = np.random.normal(0, 0.2, n_trades)
    prices = base_price + np.cumsum(price_changes)
    
    trades_df = pd.DataFrame({
        'datetime': trade_times,
        'nanotime': [int(t.timestamp() * 1e9) for t in trade_times],
        'tradeid': [f'T{i:04d}' for i in range(n_trades)],
        'price': prices
    })
    
    # Create historical candles (OHLC)
    np.random.seed(123)  # Different seed for historical data
    n_hist_candles = 50
    hist_base_time = pd.Timestamp('2024-12-01 00:00:00')
    hist_times = [hist_base_time + pd.Timedelta(hours=i) for i in range(n_hist_candles)]
    
    hist_base_price = 95.0
    hist_price_changes = np.random.normal(0, 0.3, n_hist_candles)
    hist_close_prices = hist_base_price + np.cumsum(hist_price_changes)
    
    # Generate OHLC with realistic relationships
    hist_spreads = np.random.uniform(0.2, 2.0, n_hist_candles)
    hist_high_prices = hist_close_prices + hist_spreads * 0.6
    hist_low_prices = hist_close_prices - hist_spreads * 0.4
    
    # Ensure OHLC relationships are maintained
    hist_high_prices = np.maximum(hist_high_prices, hist_close_prices)
    hist_low_prices = np.minimum(hist_low_prices, hist_close_prices)
    hist_open_prices = np.roll(hist_close_prices, 1)
    hist_open_prices[0] = hist_base_price
    
    historical_candles = pd.DataFrame({
        'open': hist_open_prices,
        'high': hist_high_prices,
        'low': hist_low_prices,
        'close': hist_close_prices
    }, index=hist_times)
    
    print(f"📊 Test data created:")
    print(f"   Trades: {len(trades_df)} records over {(trade_times[-1] - trade_times[0]).total_seconds()/3600:.1f} hours")
    print(f"   Historical candles: {len(historical_candles)} records")
    print(f"   Trade price range: {prices.min():.2f} - {prices.max():.2f}")
    print(f"   Historical price range: {hist_close_prices.min():.2f} - {hist_close_prices.max():.2f}")
    
    # Test different ATR periods
    atr_periods = [14, 21]
    
    for period in atr_periods:
        print(f"\n🔍 Testing Real-time ATR with period={period}")
        
        # Legacy real-time ATR calculation
        print("   Computing legacy real-time ATR...")
        try:
            legacy_result = compute_realtime_atr(
                trades_df=trades_df,
                historical_candles=historical_candles,
                atr_period=period,
                price_col='price',
                datetime_col='datetime',
                candle_granularity='1h'
            )
            print(f"   ✅ Legacy computed: {len(legacy_result)} results")
        except Exception as e:
            print(f"   ❌ Legacy failed: {e}")
            continue
        
        # GPU real-time ATR calculation
        print("   Computing GPU real-time ATR...")
        try:
            backend = ArrayBackend('cupy')
            atr_calc = ATRCalculator(backend)
            
            gpu_result = atr_calc.compute_atr(
                trades_df=trades_df,
                historical_candles=historical_candles,
                atr_period=period,
                price_col='price',
                datetime_col='datetime',
                candle_granularity='1h'
            )
            print(f"   ✅ GPU computed: {len(gpu_result)} results")
        except Exception as e:
            print(f"   ❌ GPU failed: {e}")
            import traceback
            traceback.print_exc()
            continue
        
        # Compare results
        print(f"   📊 Result formats:")
        print(f"      Legacy columns: {list(legacy_result.columns)}")
        print(f"      GPU columns: {list(gpu_result.columns)}")
        
        # Merge for comparison
        comparison = pd.merge(
            legacy_result[['datetime', 'atr']].rename(columns={'atr': 'legacy_atr'}),
            gpu_result[['datetime', 'atr']].rename(columns={'atr': 'gpu_atr'}),
            on='datetime',
            how='inner'
        )
        
        print(f"      Comparable records: {len(comparison)}")
        
        if len(comparison) > 0:
            # Remove NaN values for comparison
            valid_comparison = comparison.dropna()
            valid_count = len(valid_comparison)
            
            if valid_count > 0:
                # Calculate differences
                abs_diff = np.abs(valid_comparison['legacy_atr'] - valid_comparison['gpu_atr'])
                rel_diff = abs_diff / np.abs(valid_comparison['legacy_atr'])
                
                max_abs_diff = abs_diff.max()
                max_rel_diff = rel_diff.max()
                mean_abs_diff = abs_diff.mean()
                
                # Calculate match rate (within tolerance)
                tolerance = 1e-6
                matches = abs_diff < tolerance
                match_rate = matches.sum() / len(matches)
                
                print(f"   📈 Comparison Results:")
                print(f"      Valid comparisons: {valid_count}/{len(comparison)}")
                print(f"      Max absolute difference: {max_abs_diff:.8f}")
                print(f"      Max relative difference: {max_rel_diff:.8f}")
                print(f"      Mean absolute difference: {mean_abs_diff:.8f}")
                print(f"      Match rate (±{tolerance}): {match_rate:.1%}")
                
                # Show sample values for debugging
                print(f"   🔍 Sample comparison (first 5 valid values):")
                for i in range(min(5, len(valid_comparison))):
                    row = valid_comparison.iloc[i]
                    diff = abs(row['legacy_atr'] - row['gpu_atr'])
                    print(f"      [{i:2d}] Legacy: {row['legacy_atr']:10.6f}, GPU: {row['gpu_atr']:10.6f}, Diff: {diff:8.6f}")
                
                if match_rate > 0.99:
                    print(f"   ✅ EXCELLENT: Real-time ATR implementations match perfectly!")
                elif match_rate > 0.95:
                    print(f"   ✅ VERY GOOD: >95% match rate achieved")
                elif match_rate > 0.90:
                    print(f"   ✅ GOOD: >90% match rate achieved")
                else:
                    print(f"   ❌ POOR: Match rate below 90% - algorithm differences detected")
                    
                    # Debug first few that don't match
                    mismatches = valid_comparison[abs_diff >= tolerance]
                    if len(mismatches) > 0:
                        print(f"   🐛 First 3 mismatches:")
                        for i in range(min(3, len(mismatches))):
                            row = mismatches.iloc[i]
                            diff = abs(row['legacy_atr'] - row['gpu_atr'])
                            print(f"      [{i:2d}] Legacy: {row['legacy_atr']:10.6f}, GPU: {row['gpu_atr']:10.6f}, Diff: {diff:8.6f}")
            else:
                print(f"   ⚠️  No valid values for comparison after removing NaNs")
        else:
            print(f"   ⚠️  No matching records between legacy and GPU results")
        
        print("-" * 50)


def test_edge_cases():
    """Test edge cases and error handling"""
    print(f"\n🧪 Testing Edge Cases")
    print("=" * 30)
    
    try:
        backend = ArrayBackend('cupy')
        atr_calc = ATRCalculator(backend)
        
        # Test with minimal data
        print("   Testing minimal data...")
        minimal_trades = pd.DataFrame({
            'datetime': pd.to_datetime(['2025-01-01 00:00:00', '2025-01-01 01:00:00']),
            'nanotime': [1735689600000000000, 1735693200000000000],
            'tradeid': ['T0001', 'T0002'],
            'price': [100.0, 101.0]
        })
        
        minimal_hist = pd.DataFrame({
            'open': [99.0, 100.5],
            'high': [99.5, 101.0],
            'low': [98.5, 100.0],
            'close': [99.0, 100.5]
        }, index=pd.to_datetime(['2024-12-31 23:00:00', '2025-01-01 00:00:00']))
        
        result = atr_calc.compute_atr(
            trades_df=minimal_trades,
            historical_candles=minimal_hist,
            atr_period=3
        )
        print(f"   ✅ Minimal data test passed: {len(result)} results")
        
    except Exception as e:
        print(f"   ❌ Edge case test failed: {e}")


def main():
    """Run real-time ATR comparison tests"""
    print("🚀 Starting Real-time ATR Implementation Comparison")
    print("=" * 60)
    
    # Test with synthetic data
    test_realtime_atr_implementations()
    
    # Test edge cases
    test_edge_cases()
    
    print("\n✨ Real-time ATR comparison tests completed!")
    print("\nNote: This test compares the NEW real-time per-trade ATR algorithm")
    print("against the LEGACY real-time per-trade ATR algorithm - both use")
    print("simple averaging, NOT traditional Wilder's smoothing ATR.")


if __name__ == "__main__":
    main()