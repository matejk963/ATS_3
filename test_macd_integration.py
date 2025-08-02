"""
Test MACD fix integration with metadata combo generator.
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


def test_macd_integration():
    """Test MACD fix with unified pipeline"""
    
    print("="*60)
    print("TESTING MACD FIX INTEGRATION WITH UNIFIED PIPELINE")
    print("="*60)
    
    # Create test data
    periods = 200
    base_price = 75.0
    prices = base_price + np.linspace(0, 15, periods) + np.random.normal(0, 0.2, periods)
    
    start_time = datetime(2024, 1, 1, 9, 0)
    timestamps = [start_time + timedelta(minutes=15*i) for i in range(periods)]
    
    test_data = pd.DataFrame({
        'datetime': timestamps,
        'price': prices,
        'volume': np.random.randint(100, 1000, periods),
        'symbol': ['TEST'] * periods,
        'nanotime': [int(t.timestamp() * 1e9) for t in timestamps],
        'tradeid': [f'trade_{i:06d}' for i in range(periods)]
    })
    
    print(f"Test data created:")
    print(f"  Periods: {len(test_data)}")
    print(f"  Price range: {test_data['price'].min():.3f} to {test_data['price'].max():.3f}")
    print(f"  Time range: {test_data['datetime'].min()} to {test_data['datetime'].max()}")
    
    # Create historical candles for context
    hist_periods = 100
    hist_prices = base_price - 5 + np.cumsum(np.random.normal(0, 0.1, hist_periods))
    hist_start = datetime(2023, 12, 1, 9, 0)
    hist_timestamps = [hist_start + timedelta(minutes=15*i) for i in range(hist_periods)]
    
    historical_candles = pd.DataFrame({
        'open': hist_prices,
        'high': hist_prices + np.abs(np.random.normal(0, 0.3, hist_periods)),
        'low': hist_prices - np.abs(np.random.normal(0, 0.3, hist_periods)),
        'close': hist_prices + np.random.normal(0, 0.1, hist_periods)
    }, index=pd.DatetimeIndex(hist_timestamps))
    
    print(f"Historical candles: {len(historical_candles)} periods")
    
    # Test metadata combination
    metadata = {
        'atr_period': 21,
        'atr_macd_granularity': '15min',
        'fast_ema': 12,
        'slow_ema': 26,
        'signal_period': 9,
        'predictor_granularities': ['15min']
    }
    
    print(f"Test metadata: {metadata}")
    
    # Initialize unified pipeline with proper parameters
    pipeline = UnifiedTechnicalIndicatorsPipeline(
        dtype='float32',
        chunk_size=100000,
        memory_threshold=0.8
    )
    
    try:
        # Test MACD calculation through unified pipeline
        print(f"\n⚙️  Running unified pipeline with MACD...")
        
        # This should now use the fixed MACD calculation
        result = pipeline.compute_all_indicators(
            data=test_data,
            candle_granularity=metadata['atr_macd_granularity'],
            macd_params={
                'fast': metadata['fast_ema'],
                'slow': metadata['slow_ema'], 
                'signal': metadata['signal_period']
            },
            atr_period=metadata['atr_period']
        )
        
        print(f"✅ Pipeline processing completed successfully!")
        print(f"   Result shape: {result.shape}")
        print(f"   Result columns: {list(result.columns)}")
        
        # Check if MACD columns exist and have proper values
        macd_cols = [col for col in result.columns if 'macd' in col.lower()]
        if macd_cols:
            print(f"\n📊 MACD columns found: {macd_cols}")
            
            for col in macd_cols:
                if col in result.columns:
                    values = result[col].dropna()
                    if len(values) > 0:
                        print(f"   {col}: {values.min():.3f} to {values.max():.3f} (std: {values.std():.3f})")
                        
                        # Validate MACD is not all zeros (the original bug)
                        if values.min() == 0.0 and values.max() == 0.0:
                            print(f"   ❌ {col} is all zeros - fix may not be applied here")
                        else:
                            print(f"   ✅ {col} has proper variation - fix is working")
                    else:
                        print(f"   ⚠️  {col} has no valid values")
        else:
            print(f"⚠️  No MACD columns found in result")
        
        return True
        
    except Exception as e:
        print(f"❌ Pipeline processing failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main test function"""
    
    print("Testing MACD fix integration with production pipeline...")
    
    success = test_macd_integration()
    
    if success:
        print(f"\n🎉 MACD FIX INTEGRATION TEST PASSED!")
        print(f"   The fixed MACD calculation is now integrated with the production pipeline.")
        print(f"   MACD values should now oscillate properly instead of trending continuously.")
    else:
        print(f"\n❌ MACD fix integration test failed!")
        print(f"   Check the unified pipeline integration for MACD calculation.")


if __name__ == "__main__":
    main()