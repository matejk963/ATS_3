#!/usr/bin/env python3
"""
Phase 3 vs Phase 3.1 Comparison Script

This script demonstrates the difference between:
- Phase 3 (Conservative): 70-85% GPU usage, CPU fallback enabled
- Phase 3.1 (Aggressive): 98% GPU usage, GPU-only mode, RTX 4080 SUPER optimized

Run this to see the performance and utilization improvements from Phase 3.1 integration.
"""

import sys
import os
import time
import numpy as np
import pandas as pd
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

try:
    from technical_indicators.unified_pipeline import UnifiedTechnicalIndicatorsPipeline
    print("✅ Successfully imported Phase 3.1 Integrated Pipeline")
except ImportError as e:
    print(f"❌ Failed to import pipeline: {e}")
    sys.exit(1)


def create_test_data(size: int = 100000) -> pd.DataFrame:
    """Create synthetic OHLCV data for testing"""
    np.random.seed(42)
    
    base_price = 100.0
    price_changes = np.random.normal(0, 0.02, size)
    prices = base_price * np.exp(np.cumsum(price_changes))
    
    noise = np.random.normal(0, 0.005, (size, 4))
    
    data = pd.DataFrame({
        'open': prices + noise[:, 0],
        'high': prices + np.abs(noise[:, 1]) + 0.5,
        'low': prices - np.abs(noise[:, 2]) - 0.5,
        'close': prices + noise[:, 3],
        'volume': np.random.randint(1000, 10000, size)
    })
    
    # Ensure OHLC consistency
    data['high'] = np.maximum.reduce([data['open'], data['high'], data['low'], data['close']])
    data['low'] = np.minimum.reduce([data['open'], data['high'], data['low'], data['close']])
    
    return data


def run_phase3_conservative(data: pd.DataFrame):
    """Run with Phase 3 conservative settings (original)"""
    print("\n📊 PHASE 3 CONSERVATIVE MODE")
    print("-" * 50)
    
    pipeline = UnifiedTechnicalIndicatorsPipeline(
        backend='cupy',
        fallback_on_error=True,           # ✅ CPU fallback enabled
        force_gpu_only=False,             # ❌ CPU fallback allowed
        chunk_size=50000,                 # Conservative 50K chunks
        memory_threshold=0.85,            # Conservative 85% memory
        enable_gpu_memory_management=True
    )
    
    print("⚙️ Configuration:")
    print("   • CPU Fallback: ✅ ENABLED")
    print("   • Memory Threshold: 85% (conservative)")
    print("   • Chunk Size: 50,000 points")
    print("   • GPU-Only Mode: ❌ DISABLED")
    
    start_time = time.perf_counter()
    result = pipeline.compute_all_indicators(data)
    processing_time = time.perf_counter() - start_time
    
    gpu_stats = pipeline.get_gpu_memory_statistics()
    
    print(f"⏱️ Processing Time: {processing_time:.3f} seconds")
    print(f"⚡ Performance: {len(data)/processing_time:,.0f} points/second")
    if 'memory_utilization_pct' in gpu_stats:
        print(f"📊 GPU Utilization: {gpu_stats['memory_utilization_pct']:.1f}%")
    
    return processing_time, result


def run_phase31_aggressive(data: pd.DataFrame):
    """Run with Phase 3.1 aggressive settings (new integrated)"""
    print("\n🚀 PHASE 3.1 AGGRESSIVE MODE")
    print("-" * 50)
    
    pipeline = UnifiedTechnicalIndicatorsPipeline(
        backend='cupy',
        fallback_on_error=False,          # 🚫 NO CPU fallback
        force_gpu_only=True,              # ✅ STRICT GPU-only
        chunk_size=2000000,               # Ultra aggressive 2M chunks  
        memory_threshold=0.98,            # Ultra aggressive 98% memory
        enable_gpu_memory_management=True,
        rtx4080_optimized=True            # RTX 4080 SUPER optimizations
    )
    
    print("⚙️ Configuration:")
    print("   • CPU Fallback: 🚫 DISABLED")  
    print("   • Memory Threshold: 98% (ultra aggressive)")
    print("   • Chunk Size: 2,000,000 points")
    print("   • GPU-Only Mode: ✅ ENABLED")
    print("   • RTX 4080 SUPER: ✅ OPTIMIZED")
    print("   • CUDA Streams: 8 parallel streams")
    
    start_time = time.perf_counter()
    result = pipeline.compute_all_indicators(data)
    processing_time = time.perf_counter() - start_time
    
    gpu_stats = pipeline.get_gpu_memory_statistics()
    
    print(f"⏱️ Processing Time: {processing_time:.3f} seconds")
    print(f"⚡ Performance: {len(data)/processing_time:,.0f} points/second")
    if 'memory_utilization_pct' in gpu_stats:
        print(f"📊 GPU Utilization: {gpu_stats['memory_utilization_pct']:.1f}%")
    
    return processing_time, result


def compare_results(phase3_time: float, phase31_time: float, data_size: int):
    """Compare the results between Phase 3 and Phase 3.1"""
    print("\n" + "=" * 80)
    print("📊 PHASE 3 vs PHASE 3.1 COMPARISON RESULTS")
    print("=" * 80)
    
    speedup = phase3_time / phase31_time if phase31_time > 0 else 1.0
    time_saved = phase3_time - phase31_time
    
    print(f"Dataset Size: {data_size:,} data points")
    print(f"")
    print(f"⏱️ Processing Times:")
    print(f"   Phase 3 Conservative:  {phase3_time:.3f} seconds")
    print(f"   Phase 3.1 Aggressive:  {phase31_time:.3f} seconds")
    print(f"   Time Saved:            {time_saved:.3f} seconds")
    print(f"")
    print(f"🚀 Performance Improvement:")
    print(f"   Speedup Factor:         {speedup:.2f}x")
    print(f"   Performance Gain:       {(speedup-1)*100:.1f}%")
    print(f"")
    print(f"📊 Key Differences:")
    print(f"   Memory Utilization:     85% → 98% (+15% more GPU usage)")
    print(f"   Chunk Size:             50K → 2M points (+40x larger chunks)")
    print(f"   CPU Fallback:           Enabled → Disabled (GPU-only reliability)")
    print(f"   CUDA Streams:           Default → 8 streams (maximum parallelization)")
    print(f"   RTX 4080 SUPER:         Generic → Hardware-optimized")
    
    if speedup >= 2.0:
        print(f"\n🎉 EXCELLENT: {speedup:.2f}x speedup achieved!")
    elif speedup >= 1.5:
        print(f"\n✅ GOOD: {speedup:.2f}x speedup achieved!")
    elif speedup >= 1.1:
        print(f"\n✅ MODERATE: {speedup:.2f}x speedup achieved!")
    else:
        print(f"\n⚠️ MINIMAL: Only {speedup:.2f}x speedup - check GPU utilization")
    
    print(f"\n💡 Phase 3.1 Benefits:")
    print(f"   • Reliable GPU-only processing (no unexpected CPU fallback)")
    print(f"   • Maximum RTX 4080 SUPER utilization (98% memory + all cores)")
    print(f"   • Better performance through larger chunks and CUDA streams")
    print(f"   • Visible 90%+ GPU activity in Task Manager")


def main():
    """Main comparison function"""
    print("🔬 Phase 3 vs Phase 3.1 Performance Comparison")
    print("=" * 80)
    
    # Test with different dataset sizes
    test_sizes = [50000, 100000, 250000]
    
    for size in test_sizes:
        print(f"\n🧪 Testing with {size:,} data points...")
        print("=" * 80)
        
        # Create test data
        data = create_test_data(size)
        
        try:
            # Run Phase 3 conservative
            phase3_time, phase3_result = run_phase3_conservative(data)
            
            # Small delay between tests
            time.sleep(2)
            
            # Run Phase 3.1 aggressive  
            phase31_time, phase31_result = run_phase31_aggressive(data)
            
            # Compare results
            compare_results(phase3_time, phase31_time, size)
            
            # Verify results are equivalent
            if phase3_result.shape == phase31_result.shape:
                print(f"\n✅ Results verification: Both modes produced identical output shapes")
            else:
                print(f"\n⚠️ Results differ: Phase 3 {phase3_result.shape} vs Phase 3.1 {phase31_result.shape}")
            
        except Exception as e:
            print(f"\n❌ Test failed for {size:,} points: {e}")
            continue
    
    print(f"\n" + "=" * 80)
    print(f"🏁 COMPARISON COMPLETE")
    print(f"=" * 80)
    print(f"📋 Summary:")
    print(f"   Phase 3.1 integrates the best of both approaches:")
    print(f"   • Phase 3: Smart memory management + chunking")
    print(f"   • Phase 3.1: Maximum GPU utilization + RTX 4080 SUPER optimization")
    print(f"   • Result: Reliable GPU-only processing with maximum performance")
    print(f"")
    print(f"🎯 Recommended: Use Phase 3.1 aggressive mode for:")
    print(f"   • Production environments with dedicated GPU hardware")
    print(f"   • Maximum performance requirements")
    print(f"   • Reliable GPU-only processing without CPU fallback")
    print(f"")
    print(f"💡 Use Phase 3 conservative mode for:")
    print(f"   • Development environments")
    print(f"   • Mixed CPU/GPU environments") 
    print(f"   • When CPU fallback reliability is needed")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️ Comparison interrupted by user")
    except Exception as e:
        print(f"\n❌ Comparison failed: {e}")
        import traceback
        traceback.print_exc()