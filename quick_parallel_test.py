#!/usr/bin/env python3
"""
Quick test to verify TRUE PARALLEL GPU processor is working
"""

import pandas as pd
import numpy as np
import sys
import time

# Add source paths
sys.path.insert(0, '/mnt/c/Users/krajcovic/Documents/GitHub/ATS_3/src')

def quick_parallel_test():
    """Quick test of TRUE PARALLEL GPU processor"""
    print("🧪 Quick TRUE PARALLEL GPU Test...")
    
    try:
        from feature_engineering.gpu_technical_indicators_batch import GPUTechnicalIndicatorsBatch
        from feature_engineering.array_backend import ArrayBackend
        
        backend = ArrayBackend(backend='cupy')
        print(f"✅ GPU backend: {backend.backend}")
        
        # Check initial GPU memory
        free_mem, total_mem = backend.xp.cuda.Device().mem_info
        initial_usage = (total_mem - free_mem) / 1e9
        print(f"💾 Initial GPU memory usage: {initial_usage:.1f}GB")
        
        gpu_batch_processor = GPUTechnicalIndicatorsBatch(backend)
        
        # Create 10 combinations with realistic data
        print("📊 Creating 10 test combinations...")
        dates = pd.date_range(start='2025-01-01', periods=1000, freq='1min')
        
        np.random.seed(42)
        prices = 100.0 + np.cumsum(np.random.normal(0, 0.1, len(dates)))
        
        market_data = pd.DataFrame({
            'price': prices,
            'volume': np.random.randint(100, 1000, len(dates))
        }, index=dates)
        
        test_combinations = []
        for i in range(10):
            trades_df = market_data.reset_index()
            trades_df = trades_df.rename(columns={'index': 'datetime'})
            trades_df['tradeid'] = [f'trade_{j:06d}' for j in range(len(trades_df))]
            trades_df['nanotime'] = [int(t.timestamp() * 1e9) for t in trades_df['datetime']]
            
            combination_data = {
                'combo_id': i,
                'parameters': {
                    'candle_granularity': '5min',
                    'atr_period': 14,
                    'macd_params': {'se': 12, 'le': 26, 'signal': 9}
                },
                'tick_data': trades_df,
                'historical_candles': pd.DataFrame(),
                'atr_period': 14,
                'macd_params': {'se': 12, 'le': 26, 'signal': 9},
                'candle_granularity': '5min'
            }
            test_combinations.append(combination_data)
        
        print(f"🚀 Processing {len(test_combinations)} combinations...")
        
        start_time = time.time()
        results = gpu_batch_processor.process_combinations_batch(test_combinations)
        processing_time = time.time() - start_time
        
        # Check final GPU memory
        free_mem_after, total_mem_after = backend.xp.cuda.Device().mem_info
        final_usage = (total_mem_after - free_mem_after) / 1e9
        memory_increase = final_usage - initial_usage
        
        print(f"✅ Processing completed in {processing_time:.2f}s")
        print(f"📊 Results: {len(results)} combinations")
        print(f"💾 Final GPU memory usage: {final_usage:.1f}GB (+{memory_increase:.1f}GB)")
        print(f"⚡ Rate: {len(results)/processing_time:.2f} combinations/sec")
        
        # Check for TRUE parallel indicators
        parallel_count = 0
        success_count = 0
        
        for result in results:
            if 'atr_results' in result and 'macd_results' in result:
                success_count += 1
            if result.get('true_parallel_gpu', False):
                parallel_count += 1
        
        print(f"🎯 Results: {success_count}/{len(results)} successful")
        print(f"🔥 TRUE parallel indicators: {parallel_count}")
        
        if parallel_count > 0:
            print("\n🎉 SUCCESS: TRUE PARALLEL GPU processing detected!")
            return True
        else:
            print("\n⚠️  Still using sequential processing")
            return False
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = quick_parallel_test()
    sys.exit(0 if success else 1)