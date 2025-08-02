#!/usr/bin/env python3
"""
Phase 2 Algorithm Correctness Validation

This script validates that the corrected Phase 2 GPU implementations produce
identical results to the reference implementations from predictors_tools.py.

Tests both ATR and MACD implementations against reference patterns.
"""

import pandas as pd
import numpy as np
import sys
import os
from datetime import datetime, timedelta

# Add source paths
sys.path.append('src')
sys.path.append('source_repos/EnergyTrading/Python/Utilities')

def create_validation_data():
    """Create controlled test data for algorithm validation"""
    print("🔧 Creating validation test data...")
    
    # Create 50 historical candles with stable characteristics
    start_date = pd.Timestamp('2024-01-01 00:00:00')
    historical_periods = pd.date_range(start_date, periods=50, freq='1h')
    
    # Generate stable OHLC data for historical candles
    np.random.seed(42)  # Reproducible results
    base_price = 100.0
    
    historical_candles = []
    for i, period in enumerate(historical_periods):
        # Create realistic OHLC with some volatility
        open_price = base_price + np.random.normal(0, 1.5)
        high_price = open_price + abs(np.random.normal(2, 0.5))
        low_price = open_price - abs(np.random.normal(2, 0.5))
        close_price = open_price + np.random.normal(0, 1.0)
        
        historical_candles.append({
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close_price
        })
        base_price = close_price  # Price evolution
    
    historical_df = pd.DataFrame(historical_candles, index=historical_periods)
    
    # Create 100 real-time trades (ticks) for current period
    current_period = pd.Timestamp('2024-01-03 02:00:00')  # 50 hours after start
    tick_timestamps = pd.date_range(current_period, periods=100, freq='30s')
    
    # Generate realistic tick prices evolving from last historical close
    last_close = historical_df['close'].iloc[-1]
    tick_prices = []
    current_price = last_close
    
    for i in range(100):
        # Small random price movements
        price_change = np.random.normal(0, 0.1)
        current_price += price_change
        tick_prices.append(current_price)
    
    # Create trades DataFrame with required columns
    trades_df = pd.DataFrame({
        'datetime': tick_timestamps,
        'price': tick_prices,
        'tradeid': [f'trade_{i:06d}' for i in range(100)],
        'nanotime': [t.value for t in tick_timestamps]
    })
    
    print(f"✓ Created {len(historical_df)} historical candles")
    print(f"✓ Created {len(trades_df)} trade ticks")
    print(f"✓ Historical price range: {historical_df['close'].min():.2f} - {historical_df['close'].max():.2f}")
    print(f"✓ Tick price range: {min(tick_prices):.2f} - {max(tick_prices):.2f}")
    
    return historical_df, trades_df

def test_atr_algorithm_correctness():
    """Test ATR implementation against reference pattern"""
    print("\n🧪 TESTING ATR ALGORITHM CORRECTNESS")
    print("=" * 60)
    
    try:
        # Import reference and our implementation
        from predictors_tools import compute_realtime_atr
        from src.feature_engineering.atr_calculator import ATRCalculator
        from src.feature_engineering.array_backend import ArrayBackend
        
        # Create test data
        historical_candles, trades_df = create_validation_data()
        
        # Test parameters
        atr_period = 21
        print(f"Testing ATR with period: {atr_period}")
        
        # Reference implementation
        print("\n📋 Computing reference ATR...")
        reference_result = compute_realtime_atr(
            trades_df=trades_df,
            historical_candles=historical_candles,
            atr_period=atr_period,
            price_col='price',
            datetime_col='datetime',
            candle_granularity='1h'
        )
        print(f"✓ Reference ATR computed, shape: {reference_result.shape}")
        
        # Our corrected implementation
        print("\n🔧 Computing our corrected ATR...")
        backend = ArrayBackend()
        atr_calculator = ATRCalculator(backend)
        
        our_result = atr_calculator._compute_realtime_atr(
            trades_df=trades_df,
            historical_candles=historical_candles,
            atr_period=atr_period,
            price_col='price',
            datetime_col='datetime',
            candle_granularity='1h'
        )
        print(f"✓ Our ATR computed, shape: {our_result.shape}")
        
        # Compare results
        print("\n📊 COMPARING ATR RESULTS:")
        ref_atr = reference_result['atr'].values
        our_atr = our_result['atr'].values
        
        # Ensure same length
        min_len = min(len(ref_atr), len(our_atr))
        ref_atr = ref_atr[:min_len]
        our_atr = our_atr[:min_len]
        
        # Calculate differences
        differences = np.abs(ref_atr - our_atr)
        avg_diff = np.mean(differences)
        max_diff = np.max(differences)
        std_diff = np.std(differences)
        
        print(f"📈 Reference ATR range: {ref_atr.min():.6f} - {ref_atr.max():.6f}")
        print(f"🔧 Our ATR range: {our_atr.min():.6f} - {our_atr.max():.6f}")
        print(f"📊 Average difference: {avg_diff:.6f}")
        print(f"📊 Maximum difference: {max_diff:.6f}")
        print(f"📊 Std deviation of differences: {std_diff:.6f}")
        
        # Debug: Show first few values for detailed comparison
        print(f"\n🔍 DETAILED COMPARISON (first 10 values):")
        for i in range(min(10, len(ref_atr))):
            print(f"  [{i:2d}] Ref: {ref_atr[i]:.6f}, Ours: {our_atr[i]:.6f}, Diff: {differences[i]:.6f}")
        
        # Debug: Check if our implementation has any NaN or inf values
        ref_invalid = np.sum(~np.isfinite(ref_atr))
        our_invalid = np.sum(~np.isfinite(our_atr))
        print(f"\n🔍 INVALID VALUES:")
        print(f"  Reference invalid (NaN/inf): {ref_invalid}")
        print(f"  Our implementation invalid (NaN/inf): {our_invalid}")
        
        # Validation criteria
        success = True
        if avg_diff > 0.01:
            print(f"❌ FAIL: Average difference {avg_diff:.6f} > 0.01 threshold")
            success = False
        else:
            print(f"✅ PASS: Average difference {avg_diff:.6f} <= 0.01 threshold")
        
        if max_diff > 0.05:
            print(f"❌ FAIL: Maximum difference {max_diff:.6f} > 0.05 threshold")
            success = False
        else:
            print(f"✅ PASS: Maximum difference {max_diff:.6f} <= 0.05 threshold")
        
        return success, {
            'avg_diff': avg_diff,
            'max_diff': max_diff,
            'std_diff': std_diff,
            'ref_range': (ref_atr.min(), ref_atr.max()),
            'our_range': (our_atr.min(), our_atr.max())
        }
        
    except Exception as e:
        print(f"❌ ATR test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False, {'error': str(e)}

def test_macd_algorithm_correctness():
    """Test MACD implementation against reference pattern"""
    print("\n🧪 TESTING MACD ALGORITHM CORRECTNESS")
    print("=" * 60)
    
    try:
        # Import reference and our implementation
        from predictors_tools import compute_realtime_macd
        from src.feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline
        from src.feature_engineering.array_backend import ArrayBackend
        
        # Create test data
        historical_candles, trades_df = create_validation_data()
        
        # Test parameters (standard MACD)
        macd_params = {'fast': 12, 'slow': 26, 'signal': 9}
        print(f"Testing MACD with params: {macd_params}")
        
        # Reference implementation
        print("\n📋 Computing reference MACD...")
        reference_result = compute_realtime_macd(
            trades_df=trades_df,
            historical_candles=historical_candles,
            se=macd_params['fast'],
            le=macd_params['slow'],
            signal_period=macd_params['signal'],
            price_col='price',
            datetime_col='datetime',
            candle_granularity='1h'
        )
        print(f"✓ Reference MACD computed, shape: {reference_result.shape}")
        
        # Our corrected implementation
        print("\n🔧 Computing our corrected MACD...")
        pipeline = UnifiedTechnicalIndicatorsPipeline(dtype='float32')
        
        our_result = pipeline._compute_realtime_macd(
            tick_data=trades_df,
            historical_candles=historical_candles,
            macd_params=macd_params
        )
        print(f"✓ Our MACD computed, shape: {our_result.shape}")
        
        # Compare results
        print("\n📊 COMPARING MACD RESULTS:")
        
        # Compare MACD line
        ref_macd = reference_result['macd'].values
        our_macd = our_result['macd'].values
        
        min_len = min(len(ref_macd), len(our_macd))
        ref_macd = ref_macd[:min_len]
        our_macd = our_macd[:min_len]
        
        macd_differences = np.abs(ref_macd - our_macd)
        macd_avg_diff = np.mean(macd_differences)
        macd_max_diff = np.max(macd_differences)
        
        print(f"📈 MACD Line Comparison:")
        print(f"   Reference range: {ref_macd.min():.6f} - {ref_macd.max():.6f}")
        print(f"   Our range: {our_macd.min():.6f} - {our_macd.max():.6f}")
        print(f"   Average difference: {macd_avg_diff:.6f}")
        print(f"   Maximum difference: {macd_max_diff:.6f}")
        
        # Compare Signal Line
        ref_signal = reference_result['signal'].values
        our_signal = our_result['signal'].values
        
        ref_signal = ref_signal[:min_len]
        our_signal = our_signal[:min_len]
        
        signal_differences = np.abs(ref_signal - our_signal)
        signal_avg_diff = np.mean(signal_differences)
        signal_max_diff = np.max(signal_differences)
        
        print(f"📈 Signal Line Comparison:")
        print(f"   Reference range: {ref_signal.min():.6f} - {ref_signal.max():.6f}")
        print(f"   Our range: {our_signal.min():.6f} - {our_signal.max():.6f}")
        print(f"   Average difference: {signal_avg_diff:.6f}")
        print(f"   Maximum difference: {signal_max_diff:.6f}")
        
        # Compare Histogram (reference uses 'hist', our implementation uses 'histogram')
        ref_hist = reference_result['hist'].values
        our_hist = our_result['histogram'].values
        
        ref_hist = ref_hist[:min_len]
        our_hist = our_hist[:min_len]
        
        hist_differences = np.abs(ref_hist - our_hist)
        hist_avg_diff = np.mean(hist_differences)
        hist_max_diff = np.max(hist_differences)
        
        print(f"📈 Histogram Comparison:")
        print(f"   Reference range: {ref_hist.min():.6f} - {ref_hist.max():.6f}")
        print(f"   Our range: {our_hist.min():.6f} - {our_hist.max():.6f}")
        print(f"   Average difference: {hist_avg_diff:.6f}")
        print(f"   Maximum difference: {hist_max_diff:.6f}")
        
        # Validation criteria
        success = True
        threshold = 0.01  # Strict threshold for MACD
        
        for name, avg_diff, max_diff in [
            ('MACD Line', macd_avg_diff, macd_max_diff),
            ('Signal Line', signal_avg_diff, signal_max_diff),
            ('Histogram', hist_avg_diff, hist_max_diff)
        ]:
            if avg_diff > threshold:
                print(f"❌ FAIL: {name} average difference {avg_diff:.6f} > {threshold} threshold")
                success = False
            else:
                print(f"✅ PASS: {name} average difference {avg_diff:.6f} <= {threshold} threshold")
        
        return success, {
            'macd_avg_diff': macd_avg_diff,
            'macd_max_diff': macd_max_diff,
            'signal_avg_diff': signal_avg_diff,
            'signal_max_diff': signal_max_diff,
            'hist_avg_diff': hist_avg_diff,
            'hist_max_diff': hist_max_diff
        }
        
    except Exception as e:
        print(f"❌ MACD test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False, {'error': str(e)}

def main():
    """Main validation function"""
    print("🚀 PHASE 2 ALGORITHM CORRECTNESS VALIDATION")
    print("=" * 70)
    print(f"Validation started at: {datetime.now()}")
    print()
    
    # Test ATR
    atr_success, atr_results = test_atr_algorithm_correctness()
    
    # Test MACD
    macd_success, macd_results = test_macd_algorithm_correctness()
    
    # Final summary
    print("\n" + "=" * 70)
    print("🎯 FINAL VALIDATION SUMMARY")
    print("=" * 70)
    
    if atr_success:
        print("✅ ATR Algorithm: CORRECTNESS VALIDATED")
        if 'avg_diff' in atr_results:
            print(f"   Average difference: {atr_results['avg_diff']:.6f}")
    else:
        print("❌ ATR Algorithm: CORRECTNESS VALIDATION FAILED")
        if 'error' in atr_results:
            print(f"   Error: {atr_results['error']}")
    
    if macd_success:
        print("✅ MACD Algorithm: CORRECTNESS VALIDATED")
        if 'macd_avg_diff' in macd_results:
            print(f"   MACD line avg diff: {macd_results['macd_avg_diff']:.6f}")
            print(f"   Signal line avg diff: {macd_results['signal_avg_diff']:.6f}")
    else:
        print("❌ MACD Algorithm: CORRECTNESS VALIDATION FAILED")
        if 'error' in macd_results:
            print(f"   Error: {macd_results['error']}")
    
    overall_success = atr_success and macd_success
    
    if overall_success:
        print("\n🎉 ALL ALGORITHM CORRECTNESS TESTS PASSED!")
        print("✅ Phase 2 GPU implementations maintain reference compatibility")
        print("✅ Ready for production deployment")
    else:
        print("\n❌ ALGORITHM CORRECTNESS VALIDATION FAILED")
        print("⚠️  Phase 2 implementations need further corrections")
        print("⚠️  DO NOT deploy to production until fixed")
    
    print(f"\nValidation completed at: {datetime.now()}")
    return overall_success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)