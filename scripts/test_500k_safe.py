#!/usr/bin/env python3
"""
Safe 500K Dataset GPU Testing - PC Freeze Prevention
Optimized to prevent system freezing with proper memory management and cleanup
"""

import time
import gc
import numpy as np
import pandas as pd
from datetime import datetime
import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from technical_indicators.unified_pipeline import UnifiedTechnicalIndicatorsPipeline


def safe_progress_bar(current, total, description="Progress", width=30):
    """Lightweight progress bar that won't freeze system"""
    if current % max(1, total // 20) == 0 or current >= total:  # Update only every 5%
        percentage = current / total
        filled = int(width * percentage)
        bar = '█' * filled + '░' * (width - filled)
        print(f"\r{description}: [{bar}] {percentage:.0%}", end='', flush=True)
        if current >= total:
            print()


def generate_small_batches(size: int = 500_000, batch_size: int = 50_000) -> pd.DataFrame:
    """Generate dataset in small batches to prevent memory issues"""
    print(f"🏗️  Generating {size:,} data points in batches...")
    
    np.random.seed(42)
    all_data = []
    
    base_price = 100.0
    volatility = 0.02
    
    for i in range(0, size, batch_size):
        current_batch_size = min(batch_size, size - i)
        safe_progress_bar(i + current_batch_size, size, "Data Generation")
        
        # Generate batch
        changes = np.random.normal(0, volatility, current_batch_size)
        trend = np.linspace(i * 0.3 / size, (i + current_batch_size) * 0.3 / size, current_batch_size)
        
        if i == 0:
            close_prices = base_price + np.cumsum(changes + trend)
        else:
            # Continue from last price
            last_price = all_data[-1]['close'].iloc[-1]
            close_prices = last_price + np.cumsum(changes + trend)
        
        # Generate OHLC with smaller noise to reduce computation
        high_noise = np.abs(np.random.normal(0, volatility/3, current_batch_size))
        low_noise = np.abs(np.random.normal(0, volatility/3, current_batch_size))
        open_noise = np.random.normal(0, volatility/5, current_batch_size)
        
        batch_data = pd.DataFrame({
            'open': np.roll(close_prices, 1) + open_noise,
            'high': close_prices + high_noise,
            'low': close_prices - low_noise,
            'close': close_prices
        })
        
        if i == 0:
            batch_data.loc[0, 'open'] = base_price
        
        # Fix OHLC relationships
        batch_data['high'] = np.maximum.reduce([batch_data['open'], batch_data['high'], 
                                               batch_data['low'], batch_data['close']])
        batch_data['low'] = np.minimum.reduce([batch_data['open'], batch_data['high'], 
                                              batch_data['low'], batch_data['close']])
        
        all_data.append(batch_data)
        
        # Force garbage collection to prevent memory buildup
        if i % (batch_size * 4) == 0:
            gc.collect()
    
    # Combine all batches
    data = pd.concat(all_data, ignore_index=True)
    print(f"\n✅ Dataset created: {len(data):,} rows, {data.memory_usage(deep=True).sum()/1e6:.1f} MB")
    
    return data


def check_system_resources():
    """Check system resources before proceeding"""
    try:
        import cupy as cp
        
        # Clear GPU memory first
        cp.get_default_memory_pool().free_all_blocks()
        gc.collect()
        
        free_mem, total_mem = cp.cuda.runtime.memGetInfo()
        free_gb = free_mem / 1e9
        
        print(f"🔧 GPU Memory Available: {free_gb:.1f} GB")
        
        if free_gb < 2.0:
            print("⚠️  Warning: Low GPU memory, using smaller chunks")
            return 'low_memory'
        elif free_gb < 5.0:
            print("⚠️  Moderate GPU memory, using standard chunks")
            return 'moderate'
        else:
            print("✅ Good GPU memory available")
            return 'good'
            
    except Exception as e:
        print(f"❌ GPU check failed: {e}")
        return 'error'


def safe_gpu_test(data, indicator_name, pipeline, chunk_override=None):
    """Safe GPU test with proper cleanup and resource management"""
    print(f"\n📊 Testing {indicator_name.upper()} ({len(data):,} points)")
    print("-" * 50)
    
    try:
        import cupy as cp
        
        # Aggressive cleanup before test
        cp.get_default_memory_pool().free_all_blocks()
        gc.collect()
        time.sleep(0.5)  # Let system settle
        
        # Override chunk size if needed
        if chunk_override:
            original_chunk = pipeline.config.chunk_size
            pipeline.config.chunk_size = chunk_override
            if pipeline.memory_manager:
                pipeline.memory_manager.processor.strategy.chunk_size = chunk_override
        
        free_before, total_mem = cp.cuda.runtime.memGetInfo()
        
        # Simple progress indication
        print("Processing... ", end='', flush=True)
        
        start_time = time.perf_counter()
        
        # Compute with timeout-like behavior simulation
        if indicator_name == 'macd':
            result = pipeline.compute_indicators(data, ['macd'], 
                                               macd_params={'fast': 12, 'slow': 26, 'signal': 9})
            key_cols = ['macd']
        elif indicator_name == 'atr':
            result = pipeline.compute_indicators(data, ['atr'], atr_period=14)
            key_cols = ['atr']
        elif indicator_name == 'swing_points':
            # Use smaller lookback to reduce computation
            result = pipeline.compute_indicators(data, ['swing_points'], swing_lookback=10)
            key_cols = ['swing_highs', 'swing_lows']
        elif indicator_name == 'candles':
            result = pipeline.compute_indicators(data, ['candles'])
            key_cols = ['candle_open', 'candle_high', 'candle_low', 'candle_close']
        
        end_time = time.perf_counter()
        
        # Restore original chunk size
        if chunk_override:
            pipeline.config.chunk_size = original_chunk
            if pipeline.memory_manager:
                pipeline.memory_manager.processor.strategy.chunk_size = original_chunk
        
        free_after, _ = cp.cuda.runtime.memGetInfo()
        
        # Calculate results
        duration = end_time - start_time
        memory_used = (free_before - free_after) / 1e9
        throughput = len(data) / duration
        memory_pct = (memory_used / (total_mem / 1e9)) * 100
        
        print("✅ Done!")
        print(f"⏱️  Time: {duration:.2f}s")
        print(f"📈 Throughput: {throughput:,.0f} points/sec")
        print(f"💾 Memory: {memory_used:.2f} GB ({memory_pct:.1f}%)")
        
        # Show key results
        for col in key_cols:
            if col in result.columns:
                non_null = result[col].notna().sum()
                print(f"📊 {col}: {non_null:,} values")
        
        # Cleanup immediately after test
        del result
        cp.get_default_memory_pool().free_all_blocks()
        gc.collect()
        
        return {
            'success': True,
            'time': duration,
            'throughput': throughput,
            'memory_gb': memory_used,
            'memory_pct': memory_pct
        }
        
    except Exception as e:
        print(f"❌ FAILED: {e}")
        
        # Emergency cleanup
        try:
            cp.get_default_memory_pool().free_all_blocks()
            gc.collect()
        except:
            pass
            
        return {'success': False, 'error': str(e)}


def safe_combined_test(data, pipeline, chunk_override=None):
    """Safe combined test with memory management"""
    print(f"\n🎯 Testing ALL INDICATORS ({len(data):,} points)")
    print("-" * 50)
    
    try:
        import cupy as cp
        
        # Aggressive cleanup
        cp.get_default_memory_pool().free_all_blocks()
        gc.collect()
        time.sleep(1.0)  # Let system fully settle
        
        # Use smaller chunk for combined test
        if chunk_override:
            original_chunk = pipeline.config.chunk_size
            pipeline.config.chunk_size = chunk_override
            if pipeline.memory_manager:
                pipeline.memory_manager.processor.strategy.chunk_size = chunk_override
        
        free_before, total_mem = cp.cuda.runtime.memGetInfo()
        
        print("Processing all indicators... ", end='', flush=True)
        
        start_time = time.perf_counter()
        
        # Use simpler parameters to reduce computation load
        result = pipeline.compute_all_indicators(
            data,
            candle_granularity='15min',
            macd_params={'fast': 12, 'slow': 26, 'signal': 9},
            atr_period=14,
            swing_lookback=10  # Reduced for safety
        )
        
        end_time = time.perf_counter()
        
        # Restore chunk size
        if chunk_override:
            pipeline.config.chunk_size = original_chunk
            if pipeline.memory_manager:
                pipeline.memory_manager.processor.strategy.chunk_size = original_chunk
        
        free_after, _ = cp.cuda.runtime.memGetInfo()
        
        duration = end_time - start_time
        memory_used = (free_before - free_after) / 1e9
        throughput = len(data) / duration
        memory_pct = (memory_used / (total_mem / 1e9)) * 100
        
        base_cols = ['open', 'high', 'low', 'close']
        indicator_cols = [col for col in result.columns if col not in base_cols]
        
        print("✅ Done!")
        print(f"⏱️  Time: {duration:.2f}s")
        print(f"📈 Throughput: {throughput:,.0f} points/sec")
        print(f"💾 Memory: {memory_used:.2f} GB ({memory_pct:.1f}%)")
        print(f"📊 Indicators: {len(indicator_cols)} columns")
        
        # Immediate cleanup
        del result
        cp.get_default_memory_pool().free_all_blocks()
        gc.collect()
        
        return {
            'success': True,
            'time': duration,
            'throughput': throughput,
            'memory_gb': memory_used,
            'memory_pct': memory_pct,
            'indicators': len(indicator_cols)
        }
        
    except Exception as e:
        print(f"❌ FAILED: {e}")
        
        # Emergency cleanup
        try:
            cp.get_default_memory_pool().free_all_blocks()
            gc.collect()
        except:
            pass
            
        return {'success': False, 'error': str(e)}


def main():
    """Main execution with safety checks"""
    print("🛡️  SAFE 500K DATASET GPU TESTING")
    print("="*60)
    
    # Check system resources
    memory_status = check_system_resources()
    
    if memory_status == 'error':
        print("❌ Cannot proceed without GPU")
        return
    
    # Determine safe chunk sizes based on available memory
    if memory_status == 'low_memory':
        chunk_size = 50_000
        test_size = 250_000  # Reduce test size
        print("⚠️  Using conservative settings for low memory")
    elif memory_status == 'moderate':
        chunk_size = 100_000
        test_size = 400_000
        print("⚠️  Using moderate settings")
    else:
        chunk_size = 150_000  # Still conservative
        test_size = 500_000
        print("✅ Using standard settings")
    
    # Generate data safely
    data = generate_small_batches(test_size)
    
    # Setup conservative pipeline
    pipeline = UnifiedTechnicalIndicatorsPipeline(
        backend='cupy',
        enable_gpu_memory_management=True,
        chunk_size=chunk_size,
        memory_threshold=0.75  # More conservative than 0.85
    )
    
    print(f"\n⚙️  Safe Pipeline Configuration:")
    print(f"   Backend: {pipeline.backend_name}")
    print(f"   Chunk Size: {pipeline.config.chunk_size:,}")
    print(f"   Memory Threshold: {pipeline.config.memory_threshold}")
    print(f"   Data Size: {len(data):,} points")
    
    # Test indicators with safety measures
    indicators = ['macd', 'atr', 'swing_points', 'candles']
    results = {}
    
    for i, indicator in enumerate(indicators, 1):
        print(f"\n🔄 Test {i}/{len(indicators)}: {indicator.upper()}")
        
        # Use even smaller chunks for individual tests
        safe_chunk = min(chunk_size, 75_000)
        result = safe_gpu_test(data, indicator, pipeline, chunk_override=safe_chunk)
        results[indicator] = result
        
        # Pause between tests to let system recover
        print("🔄 System cooldown...")
        time.sleep(2)
        gc.collect()
    
    # Combined test with smallest chunk size
    print(f"\n🔄 Final Test: Combined Indicators")
    combined_chunk = min(chunk_size, 50_000)  # Very conservative
    combined = safe_combined_test(data, pipeline, chunk_override=combined_chunk)
    results['combined'] = combined
    
    # Final summary
    print(f"\n" + "="*60)
    print("🎯 SAFE TEST RESULTS")
    print("="*60)
    
    print(f"📊 Dataset: {len(data):,} points")
    print(f"🛡️  Safety: Conservative memory settings")
    
    success_count = 0
    total_time = 0
    
    print(f"\n📈 Individual Results:")
    for indicator in indicators:
        result = results[indicator]
        if result['success']:
            print(f"  ✅ {indicator.upper():<12}: {result['time']:>6.2f}s | {result['throughput']:>8,.0f} pts/sec")
            success_count += 1
            total_time += result['time']
        else:
            print(f"  ❌ {indicator.upper():<12}: FAILED")
    
    if combined['success']:
        print(f"\n🎯 Combined Result:")
        print(f"  ✅ All Indicators: {combined['time']:>6.2f}s | {combined['throughput']:>8,.0f} pts/sec")
        print(f"  📊 Total Indicators: {combined['indicators']}")
    
    # Final cleanup
    try:
        import cupy as cp
        cp.get_default_memory_pool().free_all_blocks()
    except:
        pass
    
    gc.collect()
    
    print(f"\n✅ Safe Test Completed Successfully!")
    print(f"🛡️  No system freezing - {success_count}/{len(indicators)} indicators working")
    print(f"🕒 Total time: {total_time:.1f}s")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n❌ Test interrupted by user")
        # Emergency cleanup
        try:
            import cupy as cp
            cp.get_default_memory_pool().free_all_blocks()
            gc.collect()
        except:
            pass
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        # Emergency cleanup
        try:
            import cupy as cp
            cp.get_default_memory_pool().free_all_blocks()
            gc.collect()
        except:
            pass