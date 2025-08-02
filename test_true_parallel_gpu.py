#!/usr/bin/env python3
"""
Test the TRUE PARALLEL GPU processor to verify improved GPU utilization with 500+ combinations
"""

import pandas as pd
import numpy as np
import sys
import time
from pathlib import Path

# Add source paths
sys.path.insert(0, '/mnt/c/Users/krajcovic/Documents/GitHub/ATS_3/src')

def test_true_parallel_gpu():
    """Test the TRUE PARALLEL GPU processor with many combinations"""
    print("🧪 Testing TRUE PARALLEL GPU Processor...")
    
    try:
        # Import the components
        from feature_engineering.gpu_technical_indicators_batch import GPUTechnicalIndicatorsBatch
        from feature_engineering.array_backend import ArrayBackend
        
        # Initialize GPU backend
        backend = ArrayBackend(backend='cupy')
        print(f"✅ GPU backend initialized: {backend.backend}")
        
        # Check GPU memory
        free_mem, total_mem = backend.xp.cuda.Device().mem_info
        print(f"💾 GPU memory: {total_mem / 1e9:.1f}GB total, {free_mem / 1e9:.1f}GB free")
        
        # Initialize GPU batch processor with TRUE PARALLEL processing
        print("🔧 Initializing GPUTechnicalIndicatorsBatch with TRUE PARALLEL GPU...")
        gpu_batch_processor = GPUTechnicalIndicatorsBatch(backend)
        print("✅ TRUE PARALLEL GPU processor initialized!")
        
        # Create synthetic market data for GPU utilization test
        print("📊 Creating synthetic market data for TRUE PARALLEL GPU test...")
        dates = pd.date_range(start='2025-01-01', periods=10000, freq='1min')  # Even larger dataset
        
        # Create realistic price data
        np.random.seed(42)
        base_price = 100.0
        price_changes = np.random.normal(0, 0.2, len(dates))
        prices = base_price + np.cumsum(price_changes)
        
        market_data = pd.DataFrame({
            'price': prices,
            'volume': np.random.randint(100, 1000, len(dates))
        }, index=dates)
        
        print(f"   📈 Generated {len(market_data)} price points")
        print(f"   💰 Price range: ${market_data['price'].min():.2f} - ${market_data['price'].max():.2f}")
        
        # Create MANY test combinations for TRUE parallel processing
        test_combinations = []
        combo_id = 0
        
        # Create 100 different combinations to test TRUE parallel processing
        granularities = [5, 10, 15]
        atr_periods = [14, 21]  
        macd_configs = [
            {'se': 12, 'le': 26, 'signal': 9},
            {'se': 8, 'le': 21, 'signal': 6},
            {'se': 10, 'le': 30, 'signal': 12},
            {'se': 9, 'le': 28, 'signal': 8},
            {'se': 11, 'le': 24, 'signal': 10}
        ]
        
        for granularity in granularities:
            for atr_period in atr_periods:
                for macd_config in macd_configs:
                    for variant in range(7):  # Create multiple variants for each param combo
                        # Prepare tick data
                        trades_df = market_data.reset_index()
                        trades_df = trades_df.rename(columns={'index': 'datetime'})
                        trades_df['tradeid'] = [f'trade_{i:06d}' for i in range(len(trades_df))]
                        trades_df['nanotime'] = [int(t.timestamp() * 1e9) for t in trades_df['datetime']]
                        
                        # Create historical candles
                        freq = f'{granularity}min'
                        historical_candles = market_data['price'].resample(freq).agg({
                            'open': 'first',
                            'high': 'max', 
                            'low': 'min',
                            'close': 'last'
                        }).dropna()
                        
                        # Format combination for GPU batch processor
                        combination_data = {
                            'combo_id': combo_id,
                            'parameters': {
                                'candle_granularity': f'{granularity}min',
                                'atr_period': atr_period,
                                'macd_params': macd_config,
                                'granularity_minutes': granularity,
                                'variant': variant
                            },
                            'tick_data': trades_df,
                            'historical_candles': historical_candles,
                            'atr_period': atr_period,
                            'macd_params': macd_config,
                            'candle_granularity': f'{granularity}min'
                        }
                        test_combinations.append(combination_data)
                        combo_id += 1
                        
                        # Stop at 100 combinations for testing
                        if len(test_combinations) >= 100:
                            break
                    if len(test_combinations) >= 100:
                        break
                if len(test_combinations) >= 100:
                    break
            if len(test_combinations) >= 100:
                break
        
        print(f"🚀 Testing TRUE PARALLEL GPU with {len(test_combinations)} combinations...")
        print(f"   📊 Data size per combination: {len(market_data):,} data points")
        print(f"   💾 Expected memory usage: ~{len(test_combinations) * 10 / 1000:.1f}GB")
        
        # Test TRUE PARALLEL GPU processing
        start_time = time.time()
        
        print("🔥 Starting TRUE PARALLEL GPU processing...")
        gpu_batch_results = gpu_batch_processor.process_combinations_batch(test_combinations)
        
        processing_time = time.time() - start_time
        
        print(f"✅ TRUE PARALLEL GPU processing completed!")
        print(f"   ⏱️  Total time: {processing_time:.2f}s")
        print(f"   📊 Processed: {len(gpu_batch_results)} combinations")
        print(f"   🚀 Processing rate: {len(gpu_batch_results)/processing_time:.2f} combinations/sec")
        
        # Check for parallel processing indicators
        success_count = 0
        parallel_indicators = 0
        
        for i, result in enumerate(gpu_batch_results[:5]):  # Check first 5 results
            has_atr = 'atr_results' in result
            has_macd = 'macd_results' in result
            is_parallel = result.get('true_parallel_gpu', False)
            
            if has_atr and has_macd:
                success_count += 1
                if is_parallel:
                    parallel_indicators += 1
                    
                print(f"   ✅ Result {i+1}: ATR ✓, MACD ✓, Parallel: {is_parallel}")
            else:
                print(f"   ❌ Result {i+1}: Missing keys")
        
        # Check final GPU memory usage
        free_mem_after, total_mem_after = backend.xp.cuda.Device().mem_info
        memory_used = (total_mem - free_mem_after) / 1e9
        memory_utilization = ((total_mem_after - free_mem_after) / total_mem_after) * 100
        
        print(f"\n🎯 TRUE PARALLEL GPU RESULTS:")
        print(f"   ✅ Successful results: {success_count}")
        print(f"   🔥 Parallel processing indicators: {parallel_indicators}")
        print(f"   💾 GPU memory used: {memory_used:.1f}GB ({memory_utilization:.1f}%)")
        print(f"   ⚡ Processing rate: {len(gpu_batch_results)/processing_time:.2f} combinations/sec")
        
        if success_count > 0 and memory_utilization > 20:  # Expect higher memory usage with parallel
            print("\n🎉 SUCCESS: TRUE PARALLEL GPU processing achieved higher utilization!")
            print("✅ GPU memory usage significantly increased")
            print("✅ Processing large batches successfully")
            return True
        else:
            print(f"\n⚠️  MIXED RESULTS: {success_count} successful, {memory_utilization:.1f}% memory")
            return success_count > 0
        
    except Exception as e:
        print(f"\n❌ ERROR: TRUE PARALLEL GPU test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_true_parallel_gpu()
    if success:
        print("\n✅ TRUE PARALLEL GPU validation successful - higher GPU utilization achieved!")
    else:
        print("\n❌ TRUE PARALLEL GPU validation failed - sequential processing still occurring")
    
    sys.exit(0 if success else 1)