#!/usr/bin/env python3
"""
Lightweight GPU Testing - Ultra Safe Version
Minimal resource usage to prevent system freezing
"""

import time
import gc
import numpy as np
import pandas as pd
import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from technical_indicators.unified_pipeline import UnifiedTechnicalIndicatorsPipeline


def create_test_data(size: int) -> pd.DataFrame:
    """Create minimal test data"""
    np.random.seed(42)
    
    # Simple price data
    base = 100.0
    prices = base + np.cumsum(np.random.randn(size) * 0.01)
    
    data = pd.DataFrame({
        'open': prices,
        'high': prices + 0.5,
        'low': prices - 0.5,
        'close': prices
    })
    
    return data


def test_single_indicator(data, indicator_name):
    """Test one indicator safely"""
    print(f"Testing {indicator_name} ({len(data):,} points)... ", end='', flush=True)
    
    try:
        # Very conservative pipeline
        pipeline = UnifiedTechnicalIndicatorsPipeline(
            backend='cupy',
            enable_gpu_memory_management=True,
            chunk_size=10000,  # Very small chunks
            memory_threshold=0.5  # Very conservative
        )
        
        start = time.perf_counter()
        
        if indicator_name == 'macd':
            result = pipeline.compute_indicators(data, ['macd'])
        elif indicator_name == 'atr':
            result = pipeline.compute_indicators(data, ['atr'])
        elif indicator_name == 'swing_points':
            result = pipeline.compute_indicators(data, ['swing_points'], swing_lookback=5)
        elif indicator_name == 'candles':
            result = pipeline.compute_indicators(data, ['candles'])
        
        duration = time.perf_counter() - start
        throughput = len(data) / duration
        
        print(f"✅ {duration:.1f}s ({throughput:,.0f} pts/sec)")
        
        # Immediate cleanup
        del result, pipeline
        gc.collect()
        
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        gc.collect()
        return False


def main():
    """Ultra-lightweight main test"""
    print("🧪 LIGHTWEIGHT GPU TESTING")
    print("="*40)
    
    # Check GPU first
    try:
        import cupy as cp
        free, total = cp.cuda.runtime.memGetInfo()
        print(f"GPU: {free/1e9:.1f} GB free / {total/1e9:.1f} GB total")
        
        # Clear memory
        cp.get_default_memory_pool().free_all_blocks()
        gc.collect()
        
    except Exception as e:
        print(f"GPU Error: {e}")
        return
    
    # Test with different sizes
    test_sizes = [10_000, 50_000, 100_000, 250_000]
    
    for size in test_sizes:
        print(f"\n📊 Testing {size:,} data points:")
        print("-" * 30)
        
        # Create data
        data = create_test_data(size)
        print(f"Data: {data.memory_usage(deep=True).sum()/1e6:.1f} MB")
        
        # Test each indicator
        indicators = ['macd', 'atr', 'swing_points', 'candles']
        success_count = 0
        
        for indicator in indicators:
            if test_single_indicator(data, indicator):
                success_count += 1
            
            # Small pause between tests
            time.sleep(0.5)
            gc.collect()
        
        print(f"Result: {success_count}/{len(indicators)} indicators working")
        
        # Pause between size tests
        time.sleep(1)
        
        # If we had failures, don't go larger
        if success_count < len(indicators):
            print(f"⚠️  Stopping at {size:,} points due to failures")
            break
    
    print(f"\n✅ Lightweight testing completed!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n❌ Interrupted")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        # Always cleanup
        try:
            import cupy as cp
            cp.get_default_memory_pool().free_all_blocks()
            gc.collect()
        except:
            pass