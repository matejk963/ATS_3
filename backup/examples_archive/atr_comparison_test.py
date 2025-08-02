"""
ATR Comparison Test: Legacy vs GPU Implementation
Test to verify that ATR calculations match between legacy and GPU implementations.
"""

import sys
import os
import pandas as pd
import numpy as np
from pathlib import Path

# Add source directories to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root / "src"))
sys.path.append(str(project_root / "source_repos" / "EnergyTrading" / "Python" / "Utilities"))

# Import legacy implementation
from predictors_tools import compute_atr

# Import GPU implementation
from feature_engineering.array_backend import ArrayBackend
from feature_engineering.atr_calculator import ATRCalculator


def test_atr_implementations():
    """Test ATR implementations with identical synthetic data"""
    print("🧪 ATR Implementation Comparison Test")
    print("=" * 50)
    
    # Create synthetic OHLC data for testing
    np.random.seed(42)  # For reproducible results
    n_periods = 100
    
    # Generate realistic OHLC data
    base_price = 100.0
    price_changes = np.random.normal(0, 0.5, n_periods)
    close_prices = base_price + np.cumsum(price_changes)
    
    # Generate high/low with realistic spreads
    spreads = np.random.uniform(0.1, 2.0, n_periods)
    high_prices = close_prices + spreads * 0.6
    low_prices = close_prices - spreads * 0.4
    
    # Ensure high >= close >= low
    high_prices = np.maximum(high_prices, close_prices)
    low_prices = np.minimum(low_prices, close_prices)
    
    # Create DataFrame for legacy implementation
    test_df = pd.DataFrame({
        'high': high_prices,
        'low': low_prices, 
        'close': close_prices
    })
    
    print(f"📊 Test data: {n_periods} periods")
    print(f"   Price range: {close_prices.min():.2f} - {close_prices.max():.2f}")
    print(f"   Avg spread: {(high_prices - low_prices).mean():.3f}")
    
    # Test parameters
    atr_periods = [14, 21]  # Standard ATR periods
    
    for period in atr_periods:
        print(f"\n🔍 Testing ATR with period={period}")
        
        # Legacy ATR calculation
        print("   Computing legacy ATR...")
        legacy_atr = compute_atr(
            test_df,
            high_col='high',
            low_col='low', 
            close_col='close',
            period=period
        )
        
        # GPU ATR calculation
        print("   Computing GPU ATR...")
        try:
            backend = ArrayBackend('cupy')  # Use GPU backend
        except Exception as e:
            print(f"   ⚠️  CuPy not available, skipping GPU test: {e}")
            continue
        atr_calc = ATRCalculator(backend)
        
        gpu_atr = atr_calc.compute_atr(
            high=high_prices,
            low=low_prices,
            close=close_prices,
            period=period
        )
        
        # Convert to comparable formats
        legacy_values = legacy_atr.values
        
        # Handle CuPy to NumPy conversion properly
        if hasattr(gpu_atr, 'get'):  # CuPy array
            gpu_values = gpu_atr.get()  # Convert CuPy to NumPy
        else:
            gpu_values = np.array(gpu_atr)
        
        print(f"   Legacy ATR shape: {legacy_values.shape}")
        print(f"   GPU ATR shape: {gpu_values.shape}")
        
        # Find valid (non-NaN) values for comparison
        legacy_valid = ~np.isnan(legacy_values)
        gpu_valid = ~np.isnan(gpu_values)
        both_valid = legacy_valid & gpu_valid
        
        valid_count = np.sum(both_valid)
        print(f"   Valid values for comparison: {valid_count}/{n_periods}")
        
        if valid_count > 0:
            legacy_subset = legacy_values[both_valid]
            gpu_subset = gpu_values[both_valid]
            
            # Calculate differences
            abs_diff = np.abs(legacy_subset - gpu_subset)
            rel_diff = abs_diff / np.abs(legacy_subset)
            
            max_abs_diff = np.max(abs_diff)
            max_rel_diff = np.max(rel_diff)
            mean_abs_diff = np.mean(abs_diff)
            
            # Calculate match rate (within tolerance)
            tolerance = 1e-6
            matches = abs_diff < tolerance
            match_rate = np.sum(matches) / len(matches)
            
            print(f"   📈 Results:")
            print(f"      Max absolute difference: {max_abs_diff:.8f}")
            print(f"      Max relative difference: {max_rel_diff:.8f}")
            print(f"      Mean absolute difference: {mean_abs_diff:.8f}")
            print(f"      Match rate (±{tolerance}): {match_rate:.1%}")
            
            # Show sample values for debugging
            print(f"   🔍 Sample comparison (first 5 valid values):")
            for i in range(min(5, len(legacy_subset))):
                print(f"      [{i:2d}] Legacy: {legacy_subset[i]:10.6f}, GPU: {gpu_subset[i]:10.6f}, Diff: {abs_diff[i]:8.6f}")
            
            if match_rate > 0.99:
                print(f"   ✅ PASS: ATR implementations match within tolerance")
            else:
                print(f"   ❌ FAIL: ATR implementations differ significantly")
                
                # Debug first few calculations
                print(f"   🐛 Debug info for period={period}:")
                print(f"      First valid legacy: {legacy_subset[0]} at index {np.where(both_valid)[0][0]}")
                print(f"      First valid GPU: {gpu_subset[0]} at index {np.where(both_valid)[0][0]}")
        else:
            print(f"   ⚠️  No valid values for comparison")
        
        print("-" * 50)


def test_atr_with_real_data():
    """Test ATR with sample real market data if available"""
    print(f"\n🏪 Testing with real market data...")
    
    # Try to load test data
    test_data_path = project_root / "Testing Data" / "backtest_data" / "dem07_25_tr_ba_data.parquet"
    
    if not test_data_path.exists():
        print(f"   ⚠️  Real data not found at: {test_data_path}")
        return
    
    try:
        # Load tick data
        tick_data = pd.read_parquet(test_data_path)
        print(f"   📊 Loaded {len(tick_data)} tick records")
        
        # Convert to OHLC candles using legacy method
        tick_data['datetime'] = pd.to_datetime(tick_data['datetime'])
        tick_data = tick_data.set_index('datetime')
        
        # Create 15-minute candles (matching analysis data)
        candles = tick_data.groupby(pd.Grouper(freq='15T')).agg({
            'price': ['first', 'max', 'min', 'last']
        }).dropna()
        
        candles.columns = ['open', 'high', 'low', 'close']
        print(f"   📊 Generated {len(candles)} 15-minute candles")
        
        if len(candles) > 30:  # Need sufficient data for ATR
            # Test with ATR period 21 (from analysis)
            period = 21
            
            # Legacy ATR
            legacy_atr = compute_atr(candles, period=period)
            
            # GPU ATR  
            try:
                backend = ArrayBackend('cupy')
            except Exception as e:
                print(f"   ⚠️  CuPy not available, skipping real data GPU test: {e}")
                return
            atr_calc = ATRCalculator(backend)
            gpu_atr = atr_calc.compute_atr(
                high=candles['high'].values,
                low=candles['low'].values,
                close=candles['close'].values,
                period=period
            )
            
            # Compare results
            legacy_values = legacy_atr.values
            
            # Handle CuPy to NumPy conversion properly
            if hasattr(gpu_atr, 'get'):  # CuPy array
                gpu_values = gpu_atr.get()  # Convert CuPy to NumPy
            else:
                gpu_values = np.array(gpu_atr)
            
            both_valid = ~np.isnan(legacy_values) & ~np.isnan(gpu_values)
            valid_count = np.sum(both_valid)
            
            if valid_count > 0:
                legacy_subset = legacy_values[both_valid]
                gpu_subset = gpu_values[both_valid]
                
                abs_diff = np.abs(legacy_subset - gpu_subset)
                matches = abs_diff < 1e-6
                match_rate = np.sum(matches) / len(matches)
                
                print(f"   📈 Real data results (period={period}):")
                print(f"      Valid comparisons: {valid_count}")
                print(f"      Max difference: {np.max(abs_diff):.8f}")
                print(f"      Match rate: {match_rate:.1%}")
                
                if match_rate > 0.99:
                    print(f"   ✅ PASS: Real data ATR matches")
                else:
                    print(f"   ❌ FAIL: Real data ATR differs")
            else:
                print(f"   ⚠️  No valid values in real data test")
        else:
            print(f"   ⚠️  Insufficient candle data for ATR test")
            
    except Exception as e:
        print(f"   ❌ Error testing real data: {e}")


def main():
    """Run ATR comparison tests"""
    print("🚀 Starting ATR Implementation Comparison")
    print("=" * 60)
    
    # Test with synthetic data
    test_atr_implementations()
    
    # Test with real data if available
    test_atr_with_real_data()
    
    print("\n✨ ATR comparison tests completed!")


if __name__ == "__main__":
    main()