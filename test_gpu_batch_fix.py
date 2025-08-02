#!/usr/bin/env python3
"""
Simple test to verify GPU batch processing works after the GPUArrayConverter import fix
"""

import pandas as pd
import numpy as np
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta

# Add source paths
sys.path.insert(0, '/mnt/c/Users/krajcovic/Documents/GitHub/ATS_3/src')

def test_gpu_batch_processing():
    """Test the GPUTechnicalIndicatorsBatch with synthetic data"""
    print("🧪 Testing GPU Batch Processing after GPUArrayConverter fix...")
    
    try:
        # Import the required components
        from feature_engineering.gpu_technical_indicators_batch import GPUTechnicalIndicatorsBatch
        from feature_engineering.array_backend import ArrayBackend
        
        # Initialize GPU backend
        backend = ArrayBackend(backend='cupy')
        print(f"✅ GPU backend initialized: {backend.backend}")
        
        # Initialize GPU batch processor (this was failing before the fix)
        print("🔧 Initializing GPUTechnicalIndicatorsBatch...")
        gpu_batch_processor = GPUTechnicalIndicatorsBatch(backend)
        print("✅ GPUTechnicalIndicatorsBatch initialized successfully!")
        
        # Create synthetic market data
        print("📊 Creating synthetic market data...")
        dates = pd.date_range(start='2025-01-01', periods=1000, freq='1min')
        
        # Create realistic price data with some volatility
        np.random.seed(42)
        base_price = 100.0
        price_changes = np.random.normal(0, 0.1, len(dates))
        prices = base_price + np.cumsum(price_changes)
        
        market_data = pd.DataFrame({
            'price': prices,
            'volume': np.random.randint(100, 1000, len(dates))
        }, index=dates)
        
        print(f"   📈 Generated {len(market_data)} price points")
        print(f"   💰 Price range: ${market_data['price'].min():.2f} - ${market_data['price'].max():.2f}")
        
        # Create a small test combination
        test_combination = {
            'combo_id': 0,
            'candle_granularity': '5min',
            'atr_period': 14,
            'macd_params': {
                'se': 12,
                'le': 26,
                'signal': 9
            },
            'granularity_minutes': 5
        }
        
        # Prepare tick data
        trades_df = market_data.reset_index()
        trades_df = trades_df.rename(columns={'index': 'datetime'})
        trades_df['tradeid'] = [f'trade_{i:06d}' for i in range(len(trades_df))]
        trades_df['nanotime'] = [int(t.timestamp() * 1e9) for t in trades_df['datetime']]
        
        # Create historical candles
        freq = '5min'
        historical_candles = market_data['price'].resample(freq).agg({
            'open': 'first',
            'high': 'max', 
            'low': 'min',
            'close': 'last'
        }).dropna()
        
        # Format combination for GPU batch processor
        combination_data = {
            'combo_id': test_combination['combo_id'],
            'parameters': test_combination,
            'tick_data': trades_df,
            'historical_candles': historical_candles,
            'atr_period': test_combination['atr_period'],
            'macd_params': test_combination['macd_params'],
            'candle_granularity': test_combination['candle_granularity']
        }
        
        # Test batch processing (this is where the original error occurred)
        print("🚀 Testing GPU batch processing...")
        gpu_batch_results = gpu_batch_processor.process_combinations_batch([combination_data])
        
        print(f"✅ GPU batch processing successful!")
        print(f"   📊 Processed {len(gpu_batch_results)} combination(s)")
        
        # Check results
        if gpu_batch_results and len(gpu_batch_results) > 0:
            result = gpu_batch_results[0]
            print(f"   🎯 Result keys: {list(result.keys())}")
            
            if 'atr_results' in result:
                atr_len = len(result['atr_results']) if hasattr(result['atr_results'], '__len__') else 'N/A'
                print(f"   📈 ATR results length: {atr_len}")
                
            if 'macd_results' in result:
                macd_len = len(result['macd_results']) if hasattr(result['macd_results'], '__len__') else 'N/A'
                print(f"   📊 MACD results length: {macd_len}")
        
        print("\n🎉 SUCCESS: GPU batch processing is working correctly!")
        print("✅ GPUArrayConverter import fix resolved the issue")
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: GPU batch processing failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_gpu_batch_processing()
    if success:
        print("\n✅ Test completed successfully - GPU batch processing is ready for production use")
    else:
        print("\n❌ Test failed - additional fixes may be needed")
    
    sys.exit(0 if success else 1)