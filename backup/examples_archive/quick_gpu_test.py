#!/usr/bin/env python3
"""
Quick GPU Integration Test

Tests that the Phase 3.1 integrated system works with basic functionality.
"""

import sys
import os
import time
import numpy as np
import pandas as pd
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

def quick_test():
    """Quick test of GPU-only pipeline"""
    try:
        from technical_indicators.unified_pipeline import UnifiedTechnicalIndicatorsPipeline
        print("✅ Import successful")
        
        # Create small test data
        np.random.seed(42)
        data = pd.DataFrame({
            'open': np.random.random(1000) * 100,
            'high': np.random.random(1000) * 100 + 1,
            'low': np.random.random(1000) * 100 - 1,
            'close': np.random.random(1000) * 100,
            'volume': np.random.randint(1000, 10000, 1000)
        })
        
        # Test conservative mode (with CPU fallback)
        print("\n🔧 Testing conservative mode...")
        pipeline_conservative = UnifiedTechnicalIndicatorsPipeline(
            backend='cupy',
            fallback_on_error=True,  # Allow CPU fallback
            force_gpu_only=False,    # Allow CPU fallback
            chunk_size=50000,
            memory_threshold=0.85
        )
        
        result_conservative = pipeline_conservative.compute_indicators(
            data, ['macd', 'atr']
        )
        print(f"✅ Conservative mode: {result_conservative.shape}")
        
        # Test aggressive mode (GPU-only)
        print("\n🚀 Testing aggressive GPU-only mode...")
        pipeline_aggressive = UnifiedTechnicalIndicatorsPipeline(
            backend='cupy',
            fallback_on_error=False,  # No CPU fallback
            force_gpu_only=True,      # Strict GPU-only
            chunk_size=2000000,
            memory_threshold=0.98
        )
        
        result_aggressive = pipeline_aggressive.compute_indicators(
            data, ['macd', 'atr']
        )
        print(f"✅ Aggressive mode: {result_aggressive.shape}")
        
        # Compare results
        if result_conservative.shape == result_aggressive.shape:
            print("✅ Both modes produce same output shape")
        else:
            print("⚠️ Output shapes differ")
        
        # Get GPU stats
        gpu_stats = pipeline_aggressive.get_gpu_memory_statistics()
        print(f"\n📊 GPU Statistics:")
        for key, value in gpu_stats.items():
            print(f"   {key}: {value}")
        
        print(f"\n🎉 Integration test successful!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    quick_test()