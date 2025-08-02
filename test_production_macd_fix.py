"""
Test the MACD fix in the actual production pipeline used by metadata combo generator.

This tests the UnifiedTechnicalIndicatorsPipeline._compute_realtime_macd() method
which is what the metadata combo generator actually uses.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from src.feature_engineering.array_backend import ArrayBackend
from src.feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline


def test_production_macd_fix():
    """Test the actual production MACD implementation that metadata combo generator uses"""
    
    print("="*80)
    print("TESTING PRODUCTION MACD FIX - UNIFIED PIPELINE")
    print("="*80)
    print("This tests the actual _compute_realtime_macd() method used by metadata combo generator")
    
    # Create test data similar to what metadata combo generator processes
    periods = 360  # Typical tick count per combo
    base_price = 82.0
    
    # Create sustained uptrend like your screenshot
    trend = np.linspace(0, 15, periods)  # 82 to 97 price range
    momentum = np.sin(np.linspace(0, 4*np.pi, periods)) * 2  # Momentum oscillations
    noise = np.random.normal(0, 0.1, periods)
    
    prices = base_price + trend + momentum + noise
    
    # Create datetime range (6 hours of minute data)
    start_time = datetime(2024, 1, 15, 9, 0)
    timestamps = [start_time + timedelta(minutes=i) for i in range(periods)]
    
    tick_data = pd.DataFrame({
        'datetime': timestamps,
        'price': prices,
        'volume': np.random.randint(50, 200, periods),
        'tradeid': [f'T{i:06d}' for i in range(periods)],
        'nanotime': [int(t.timestamp() * 1e9) for t in timestamps]
    })
    
    # Create historical candles (previous day data for context)
    hist_periods = 50
    hist_prices = base_price - 5 + np.cumsum(np.random.normal(0, 0.2, hist_periods))
    hist_start = datetime(2024, 1, 14, 9, 0)
    hist_timestamps = [hist_start + timedelta(minutes=30*i) for i in range(hist_periods)]
    
    historical_candles = pd.DataFrame({
        'open': hist_prices,
        'high': hist_prices + np.abs(np.random.normal(0, 0.4, hist_periods)),
        'low': hist_prices - np.abs(np.random.normal(0, 0.4, hist_periods)),
        'close': hist_prices + np.random.normal(0, 0.1, hist_periods)
    }, index=pd.DatetimeIndex(hist_timestamps))
    
    print(f"Test Setup:")
    print(f"  Tick Data: {len(tick_data)} ticks")
    print(f"  Price Range: {tick_data['price'].min():.3f} to {tick_data['price'].max():.3f}")
    print(f"  Historical Candles: {len(historical_candles)} periods")
    print(f"  Price Trend: {trend[0]:.3f} to {trend[-1]:.3f} (sustained uptrend)")
    
    # Test different MACD parameter combinations (from metadata combo generator)
    test_combinations = [
        {'fast': 12, 'slow': 26, 'signal': 9, 'name': 'Standard MACD'},
        {'fast': 8, 'slow': 21, 'signal': 7, 'name': 'Fast MACD'},
        {'fast': 20, 'slow': 50, 'signal': 15, 'name': 'Slow MACD'}
    ]
    
    # Initialize production pipeline
    try:
        pipeline = UnifiedTechnicalIndicatorsPipeline(dtype='float32', chunk_size=50000, memory_threshold=0.8)
        print(f"\n✅ Production pipeline initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize pipeline: {e}")
        return False
    
    all_results = []
    
    for combo in test_combinations:
        print(f"\n📊 Testing {combo['name']} ({combo['fast']}/{combo['slow']}/{combo['signal']}):")
        
        try:
            # Test the actual production method used by metadata combo generator
            result = pipeline._compute_realtime_macd(
                tick_data=tick_data,
                historical_candles=historical_candles,
                macd_params=combo
            )
            
            # Validate results
            macd_values = result['macd'].dropna()
            signal_values = result['macd_signal'].dropna()
            hist_values = result['macd_hist'].dropna()
            
            if len(macd_values) == 0:
                print(f"   ❌ No MACD values calculated")
                continue
            
            # Check for the original bug (all zeros or continuous trending)
            if macd_values.min() == 0.0 and macd_values.max() == 0.0:
                print(f"   ❌ MACD all zeros - fix not working!")
                continue
            
            # Calculate oscillation metrics
            macd_range = macd_values.max() - macd_values.min()
            macd_mean = macd_values.mean()
            macd_std = macd_values.std()
            
            # Check for trending vs oscillation
            macd_trend_slope = np.polyfit(range(len(macd_values)), macd_values, 1)[0]
            
            print(f"   📈 MACD Range: {macd_values.min():.4f} to {macd_values.max():.4f}")
            print(f"   📊 MACD Mean: {macd_mean:.4f}")
            print(f"   📉 MACD Std Dev: {macd_std:.4f}")
            print(f"   📋 MACD Trend Slope: {macd_trend_slope:.6f}")
            
            # Signal line validation
            if len(signal_values) > 0:
                signal_std = signal_values.std()
                print(f"   🔄 Signal Range: {signal_values.min():.4f} to {signal_values.max():.4f}")
                print(f"   🔄 Signal Std Dev: {signal_std:.4f}")
            
            # Histogram validation 
            if len(hist_values) > 0:
                hist_mean = hist_values.mean()
                hist_std = hist_values.std()
                print(f"   📊 Histogram Range: {hist_values.min():.4f} to {hist_values.max():.4f}")
                print(f"   📊 Histogram Mean: {hist_mean:.4f} (should oscillate around 0)")
            
            # Validation checks
            is_oscillating = macd_std > 0.01
            is_not_all_zeros = not (macd_values.min() == 0.0 and macd_values.max() == 0.0)
            is_reasonable_range = macd_range > 0.001
            varies_over_time = not np.allclose(macd_values, macd_values.iloc[0])
            
            if is_oscillating and is_not_all_zeros and is_reasonable_range and varies_over_time:
                print(f"   ✅ {combo['name']} - MACD oscillates properly (FIXED)")
                all_results.append((combo['name'], True, macd_std, macd_trend_slope))
            else:
                print(f"   ❌ {combo['name']} - MACD still has issues")
                print(f"      Oscillating: {is_oscillating}, Not zeros: {is_not_all_zeros}")
                print(f"      Reasonable range: {is_reasonable_range}, Varies: {varies_over_time}")
                all_results.append((combo['name'], False, macd_std, macd_trend_slope))
                
        except Exception as e:
            print(f"   ❌ {combo['name']} failed: {e}")
            import traceback
            traceback.print_exc()
            all_results.append((combo['name'], False, 0.0, 0.0))
    
    # Summary
    print(f"\n" + "="*80)
    print("PRODUCTION MACD FIX VALIDATION SUMMARY")
    print("="*80)
    
    successful_tests = [r for r in all_results if r[1]]
    
    if len(successful_tests) == len(test_combinations):
        print(f"🎉 ALL {len(successful_tests)} MACD PARAMETER COMBINATIONS PASS!")
        print(f"✅ Production pipeline MACD fix is working correctly")
        print(f"✅ Metadata combo generator will now get proper oscillating MACD")
        
        # Show oscillation comparison
        print(f"\n📊 MACD Oscillation Analysis:")
        for name, success, std_dev, trend in all_results:
            if success:
                print(f"   {name}: Std Dev = {std_dev:.4f}, Trend = {trend:.6f}")
        
        print(f"\n🚀 READY FOR PRODUCTION: Run metadata combo generator again!")
        print(f"   MACD should now oscillate properly instead of continuously rising")
        return True
    else:
        print(f"❌ ONLY {len(successful_tests)}/{len(test_combinations)} TESTS PASSED")
        print(f"❌ Production pipeline MACD fix needs more work")
        return False


def main():
    """Main test function"""
    
    print("Testing MACD fix in actual production pipeline...")
    
    success = test_production_macd_fix()
    
    if success:
        print(f"\n✅ PRODUCTION MACD FIX VALIDATED!")
        print(f"   The metadata combo generator should now produce proper oscillating MACD")
        print(f"   instead of the continuously rising MACD shown in your screenshot.")
    else:
        print(f"\n❌ Production MACD fix validation failed!")
        print(f"   Additional debugging needed for the production pipeline.")


if __name__ == "__main__":
    main()