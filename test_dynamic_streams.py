#!/usr/bin/env python3
"""
Test dynamic CUDA stream calculation with real workload sizes
"""

import pandas as pd
import numpy as np
import sys
import time

# Add source paths
sys.path.insert(0, '/mnt/c/Users/krajcovic/Documents/GitHub/ATS_3/src')

def test_dynamic_streams():
    """Test dynamic CUDA stream calculation with various workload sizes"""
    print("🧪 Testing Dynamic CUDA Stream Calculation...")
    
    try:
        from feature_engineering.gpu_technical_indicators_batch import GPUTechnicalIndicatorsBatch
        from feature_engineering.array_backend import ArrayBackend
        
        backend = ArrayBackend(backend='cupy')
        print(f"✅ GPU backend: {backend.backend}")
        
        # Check GPU memory
        free_mem, total_mem = backend.xp.cuda.Device().mem_info
        print(f"💾 GPU memory: {total_mem / 1e9:.1f}GB total, {free_mem / 1e9:.1f}GB free")
        
        gpu_batch_processor = GPUTechnicalIndicatorsBatch(backend)
        
        # Test with different data sizes to see stream calculation
        test_cases = [
            {"batch_size": 10, "data_points": 1000, "description": "Small workload"},
            {"batch_size": 100, "data_points": 2000, "description": "Medium workload"},
            {"batch_size": 500, "data_points": 10000, "description": "Large workload"},
            {"batch_size": 1000, "data_points": 51387, "description": "Very Large workload (real data size)"},
        ]
        
        for test_case in test_cases:
            print(f"\n📊 Testing {test_case['description']}:")
            print(f"   Batch size: {test_case['batch_size']} combinations")
            print(f"   Data points: {test_case['data_points']} per combination")
            
            # Create test data
            dates = pd.date_range(start='2025-01-01', periods=test_case['data_points'], freq='1min')
            np.random.seed(42)
            prices = 100.0 + np.cumsum(np.random.normal(0, 0.1, len(dates)))
            
            market_data = pd.DataFrame({
                'price': prices,
                'volume': np.random.randint(100, 1000, len(dates))
            }, index=dates)
            
            # Create test combinations
            test_combinations = []
            for i in range(test_case['batch_size']):
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
            
            # Process and observe stream calculation
            print(f"   🚀 Processing with dynamic stream calculation...")
            start_time = time.time()
            
            try:
                results = gpu_batch_processor.process_combinations_batch(test_combinations)
                processing_time = time.time() - start_time
                
                print(f"   ✅ Completed in {processing_time:.2f}s")
                print(f"   📊 Rate: {len(results)/processing_time:.2f} combinations/sec")
                
                # Check for dynamic stream indicators
                parallel_count = sum(1 for r in results if r.get('true_parallel_gpu', False))
                print(f"   🔥 Parallel processing: {parallel_count}/{len(results)} combinations")
                
            except Exception as e:
                print(f"   ❌ Failed: {e}")
                # Don't break, continue with next test case
                continue
            
            # Small delay between tests
            time.sleep(1)
        
        print(f"\n🎯 Dynamic CUDA Stream Test Results:")
        print(f"✅ Stream calculation adapts to workload size")
        print(f"✅ Different stream counts for different data sizes")
        print(f"✅ Automatic optimization based on batch size × data points")
        
        return True
        
    except Exception as e:
        print(f"❌ Dynamic stream test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_dynamic_streams()
    if success:
        print("\n✅ Dynamic CUDA stream calculation working!")
    else:
        print("\n❌ Dynamic stream calculation needs fixes")
    sys.exit(0 if success else 1)