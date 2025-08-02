#!/usr/bin/env python3
"""
GPU-Only Technical Indicators Pipeline

This is the simplified, production-ready GPU-only version.
- No CPU fallback options
- RTX 4080 SUPER optimized by default
- 98% GPU memory utilization
- 8 CUDA streams for maximum parallelization
- 2M point chunks for maximum efficiency

Usage:
    python examples/gpu_only_technical_indicators.py
"""

import sys
import os
import time
import numpy as np
import pandas as pd
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

def create_sample_data(size: int = 50000) -> pd.DataFrame:
    """Create sample OHLCV data for demonstration"""
    print(f"📊 Generating {size:,} sample data points...")
    
    np.random.seed(42)
    
    # Generate realistic price movement
    base_price = 100.0
    price_changes = np.random.normal(0, 0.02, size)
    prices = base_price * np.exp(np.cumsum(price_changes))
    
    # Create OHLCV data
    data = pd.DataFrame({
        'open': prices * np.random.normal(1.0, 0.001, size),
        'high': prices * np.random.uniform(1.005, 1.02, size),
        'low': prices * np.random.uniform(0.98, 0.995, size),
        'close': prices,
        'volume': np.random.randint(10000, 100000, size)
    })
    
    # Ensure OHLC consistency
    data['high'] = np.maximum.reduce([data['open'], data['high'], data['low'], data['close']])
    data['low'] = np.minimum.reduce([data['open'], data['high'], data['low'], data['close']])
    
    return data


def main():
    """Demonstrate GPU-only technical indicators processing"""
    print("🚀 GPU-Only Technical Indicators Pipeline")
    print("RTX 4080 SUPER Optimized with Maximum Performance")
    print("=" * 80)
    
    try:
        from technical_indicators.unified_pipeline import UnifiedTechnicalIndicatorsPipeline
        
        # Initialize GPU-only pipeline (all defaults are now aggressive GPU settings)
        print("🔧 Initializing GPU-only pipeline...")
        pipeline = UnifiedTechnicalIndicatorsPipeline()
        
        # Create sample data
        data = create_sample_data(50000)
        
        # Process all indicators
        print(f"\n⚡ Processing all technical indicators...")
        start_time = time.perf_counter()
        
        result = pipeline.compute_all_indicators(
            data=data,
            macd_params={'fast': 12, 'slow': 26, 'signal': 9},
            atr_period=14,
            swing_lookback=20
        )
        
        processing_time = time.perf_counter() - start_time
        
        # Display results
        print(f"\n✅ Processing completed successfully!")
        print(f"⏱️  Processing time: {processing_time:.3f} seconds")
        print(f"⚡ Performance: {len(data)/processing_time:,.0f} points/second")
        print(f"📊 Result shape: {result.shape}")
        
        # Show available indicators
        indicator_columns = [col for col in result.columns if col not in ['open', 'high', 'low', 'close', 'volume']]
        print(f"📈 Computed indicators ({len(indicator_columns)}):")
        for col in indicator_columns:
            print(f"   • {col}")
        
        # Display GPU statistics
        gpu_stats = pipeline.get_gpu_memory_statistics()
        print(f"\n🎯 GPU Statistics:")
        print(f"   Device: {gpu_stats.get('device_name', 'Unknown')}")
        print(f"   Memory Utilization: {gpu_stats.get('memory_utilization_pct', 0):.1f}%")
        print(f"   CUDA Streams: {gpu_stats.get('cuda_streams', 0)}")
        print(f"   Chunk Size: {gpu_stats.get('ultra_chunk_size', 0):,} points")
        print(f"   Memory Threshold: {gpu_stats.get('aggressive_memory_threshold', 0):.0%}")
        
        # Sample results
        print(f"\n📋 Sample Results (last 5 rows):")
        print(result[['close', 'macd_line', 'atr', 'swing_highs', 'candle_close']].tail())
        
        print(f"\n🎉 GPU-only processing demonstration completed!")
        print(f"💡 Check Windows Task Manager → Performance → GPU to see utilization")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print(f"💡 Ensure:")
        print(f"   • CUDA is installed")
        print(f"   • CuPy is installed: pip install cupy-cuda12x")
        print(f"   • CUDA-compatible GPU is available")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()