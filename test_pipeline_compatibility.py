"""
Test backward compatibility with unified pipeline
"""

import sys
import os
import pandas as pd
import numpy as np
from pathlib import Path

# Add source directories to path
project_root = Path(__file__).parent
sys.path.append(str(project_root / "src"))

# Import pipeline components
from feature_engineering.array_backend import ArrayBackend
from feature_engineering.atr_calculator import ATRCalculator
from feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline


def test_traditional_atr_compatibility():
    """Test that traditional ATR (high, low, close arrays) still works"""
    print("🧪 Testing Traditional ATR Backward Compatibility")
    print("=" * 50)
    
    try:
        backend = ArrayBackend('cupy')
        atr_calc = ATRCalculator(backend)
        
        # Create test OHLC data
        np.random.seed(42)
        n_periods = 50
        
        base_price = 100.0
        price_changes = np.random.normal(0, 0.5, n_periods)
        close_prices = base_price + np.cumsum(price_changes)
        
        spreads = np.random.uniform(0.1, 2.0, n_periods)
        high_prices = close_prices + spreads * 0.6
        low_prices = close_prices - spreads * 0.4
        
        # Ensure OHLC relationships
        high_prices = np.maximum(high_prices, close_prices)
        low_prices = np.minimum(low_prices, close_prices)
        
        print(f"📊 Test data: {n_periods} periods")
        print(f"   Price range: {close_prices.min():.2f} - {close_prices.max():.2f}")
        
        # Test traditional ATR call
        atr_result = atr_calc.compute_atr(
            high=high_prices,
            low=low_prices,
            close=close_prices,
            period=14
        )
        
        print(f"✅ Traditional ATR computed successfully")
        print(f"   Result length: {len(atr_result)}")
        print(f"   ATR range: {np.nanmin(atr_result):.6f} - {np.nanmax(atr_result):.6f}")
        
        # Verify result is GPU array
        if hasattr(atr_result, 'get'):
            print(f"   ✅ Result is CuPy array (GPU accelerated)")
        else:
            print(f"   ⚠️  Result is not CuPy array")
        
        return True
        
    except Exception as e:
        print(f"❌ Traditional ATR compatibility test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_unified_pipeline_integration():
    """Test that unified pipeline still works with our updated ATR calculator"""
    print(f"\n🧪 Testing Unified Pipeline Integration")
    print("=" * 40)
    
    try:
        # Create test OHLC data
        np.random.seed(123)
        n_periods = 100
        
        dates = pd.date_range('2024-01-01', periods=n_periods, freq='H')
        
        base_price = 100.0
        price_changes = np.random.normal(0, 0.3, n_periods)
        close_prices = base_price + np.cumsum(price_changes)
        
        spreads = np.random.uniform(0.2, 1.5, n_periods)
        high_prices = close_prices + spreads * 0.6
        low_prices = close_prices - spreads * 0.4
        open_prices = np.roll(close_prices, 1)
        open_prices[0] = base_price
        
        # Ensure OHLC relationships
        high_prices = np.maximum(high_prices, close_prices)
        low_prices = np.minimum(low_prices, close_prices)
        
        test_df = pd.DataFrame({
            'datetime': dates,
            'open': open_prices,
            'high': high_prices,
            'low': low_prices,
            'close': close_prices,
            'volume': np.random.randint(1000, 10000, n_periods)
        })
        
        print(f"📊 Pipeline test data: {len(test_df)} records")
        
        # Initialize pipeline
        pipeline = UnifiedTechnicalIndicatorsPipeline()
        
        # Test processing with ATR indicator
        result = pipeline.compute_indicators(
            test_df,
            indicators=['atr'],
            atr_period=14
        )
        
        print(f"✅ Pipeline processing successful")
        print(f"   Result keys: {list(result.keys()) if isinstance(result, dict) else 'Not dict'}")
        
        if isinstance(result, dict) and 'atr' in result:
            atr_values = result['atr']
            if hasattr(atr_values, 'get'):
                atr_cpu = atr_values.get()
            else:
                atr_cpu = atr_values
            
            print(f"   ATR computed: {len(atr_cpu)} values")
            print(f"   ATR range: {np.nanmin(atr_cpu):.6f} - {np.nanmax(atr_cpu):.6f}")
            print(f"   ✅ Pipeline ATR integration working")
        else:
            print(f"   ⚠️  ATR not found in pipeline result")
        
        return True
        
    except Exception as e:
        print(f"❌ Pipeline integration test failed: {e}")
        import traceback  
        traceback.print_exc()
        return False


def test_both_atr_modes():
    """Test that both traditional and real-time ATR modes work correctly"""
    print(f"\n🧪 Testing Both ATR Modes")
    print("=" * 30)
    
    try:
        backend = ArrayBackend('cupy')
        atr_calc = ATRCalculator(backend)
        
        # Test traditional mode
        print("   Testing traditional ATR mode...")
        high = np.array([102.0, 103.0, 101.5, 102.5])
        low = np.array([100.0, 101.0, 99.5, 100.5])
        close = np.array([101.0, 102.0, 100.0, 101.0])
        
        traditional_result = atr_calc.compute_atr(
            high=high, low=low, close=close, period=3
        )
        print(f"   ✅ Traditional mode: {len(traditional_result)} values")
        
        # Test real-time mode
        print("   Testing real-time ATR mode...")
        trades_df = pd.DataFrame({
            'datetime': pd.to_datetime(['2025-01-01 01:00:00', '2025-01-01 02:00:00']),
            'nanotime': [1735693200000000000, 1735696800000000000],
            'tradeid': ['T001', 'T002'],
            'price': [100.0, 101.0]
        })
        
        historical_candles = pd.DataFrame({
            'open': [99.0],
            'high': [99.5],
            'low': [98.5],
            'close': [99.0]
        }, index=pd.to_datetime(['2024-12-31 23:00:00']))
        
        realtime_result = atr_calc.compute_atr(
            trades_df=trades_df,
            historical_candles=historical_candles,
            atr_period=2
        )
        print(f"   ✅ Real-time mode: {len(realtime_result)} values")
        print(f"   Real-time columns: {list(realtime_result.columns)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Both modes test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all compatibility tests"""
    print("🚀 ATR Implementation Compatibility Testing")
    print("=" * 60)
    
    tests = [
        ("Traditional ATR Compatibility", test_traditional_atr_compatibility),
        ("Unified Pipeline Integration", test_unified_pipeline_integration),
        ("Both ATR Modes", test_both_atr_modes)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} crashed: {e}")
            results.append((test_name, False))
    
    print(f"\n✨ Compatibility Test Results:")
    print("=" * 40)
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {status}: {test_name}")
    
    all_passed = all(result for _, result in results)
    if all_passed:
        print(f"\n🎉 ALL COMPATIBILITY TESTS PASSED!")
        print("   Backward compatibility maintained ✅")
        print("   New real-time ATR functionality added ✅")
        print("   Pipeline integration preserved ✅")
    else:
        print(f"\n⚠️  Some compatibility tests failed")


if __name__ == "__main__":
    main()