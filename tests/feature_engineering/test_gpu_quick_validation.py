#!/usr/bin/env python3
"""
Quick GPU validation test
"""

import sys
import time
import pandas as pd
import numpy as np
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

def test_gpu_availability():
    """Test if GPU is available"""
    print("🔍 GPU Availability Check...")
    
    try:
        import cupy as cp
        print(f"✅ CuPy version: {cp.__version__}")
        
        # Test basic GPU operation
        gpu_array = cp.array([1, 2, 3, 4, 5])
        result = cp.sum(gpu_array)
        print(f"✅ Basic GPU operation: {result}")
        
        # Memory info
        meminfo = cp.cuda.runtime.memGetInfo()
        total_gb = meminfo[1] / (1024**3)
        free_gb = meminfo[0] / (1024**3)
        print(f"✅ GPU Memory: {free_gb:.1f}GB free / {total_gb:.1f}GB total")
        
        return True
    except Exception as e:
        print(f"❌ GPU not available: {e}")
        return False

def test_pipeline_import():
    """Test pipeline import"""
    print("\n📦 Pipeline Import Test...")
    
    try:
        from src.feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline
        print("✅ Pipeline imported successfully")
        
        # Test basic initialization
        pipeline = UnifiedTechnicalIndicatorsPipeline(backend='numpy')
        print("✅ NumPy pipeline initialized")
        
        # Test GPU pipeline if available
        try:
            gpu_pipeline = UnifiedTechnicalIndicatorsPipeline(
                backend='cupy',
                enable_gpu_memory_management=True
            )
            print("✅ GPU pipeline initialized with memory management")
            
            # Test memory stats
            stats = gpu_pipeline.get_gpu_memory_statistics()
            if stats.get('gpu_available'):
                print(f"✅ GPU stats: {stats['free_memory_gb']:.1f}GB free")
            return True
        except Exception as e:
            print(f"⚠️ GPU pipeline error: {e}")
            return False
            
    except Exception as e:
        print(f"❌ Pipeline import failed: {e}")
        return False

def test_small_dataset():
    """Test with small dataset"""
    print("\n🧪 Small Dataset Test...")
    
    try:
        from src.feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline
        
        # Create minimal test data
        data = pd.DataFrame({
            'timestamp': pd.date_range('2023-01-01', periods=1000, freq='1min'),
            'open': np.random.uniform(100, 110, 1000),
            'high': np.random.uniform(110, 120, 1000),
            'low': np.random.uniform(90, 100, 1000),
            'close': np.random.uniform(100, 110, 1000),
            'volume': np.random.randint(1000, 10000, 1000)
        })
        
        print(f"📊 Test data: {len(data)} rows")
        
        # Test CPU pipeline
        cpu_pipeline = UnifiedTechnicalIndicatorsPipeline(backend='numpy')
        start_time = time.time()
        cpu_result = cpu_pipeline.compute_indicators(data, indicators=['macd'])
        cpu_time = time.time() - start_time
        
        if cpu_result is not None and 'macd' in cpu_result.columns:
            valid_macd = cpu_result['macd'].notna().sum()
            print(f"✅ CPU MACD: {cpu_time:.3f}s, {valid_macd} valid values")
        else:
            print("❌ CPU MACD failed")
            return False
        
        # Test GPU pipeline if available
        if test_gpu_availability():
            try:
                gpu_pipeline = UnifiedTechnicalIndicatorsPipeline(
                    backend='cupy',
                    enable_gpu_memory_management=True
                )
                
                start_time = time.time()
                gpu_result = gpu_pipeline.compute_indicators(data, indicators=['macd'])
                gpu_time = time.time() - start_time
                
                if gpu_result is not None and 'macd' in gpu_result.columns:
                    valid_macd = gpu_result['macd'].notna().sum()
                    speedup = cpu_time / gpu_time if gpu_time > 0 else 0
                    print(f"✅ GPU MACD: {gpu_time:.3f}s, {valid_macd} valid values")
                    print(f"🏃 Speedup: {speedup:.2f}x")
                else:
                    print("❌ GPU MACD failed")
                    
            except Exception as e:
                print(f"❌ GPU test error: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Small dataset test failed: {e}")
        return False

def main():
    """Run quick validation"""
    print("🚀 Quick GPU Validation Test")
    print("=" * 40)
    
    # Run tests
    gpu_available = test_gpu_availability()
    pipeline_ok = test_pipeline_import()
    small_test_ok = test_small_dataset()
    
    print(f"\n📊 VALIDATION SUMMARY")
    print("=" * 40)
    print(f"GPU Available: {'✅' if gpu_available else '❌'}")
    print(f"Pipeline Import: {'✅' if pipeline_ok else '❌'}")
    print(f"Small Dataset Test: {'✅' if small_test_ok else '❌'}")
    
    if gpu_available and pipeline_ok and small_test_ok:
        print(f"\n🎉 GPU Implementation: ✅ READY FOR LARGE DATASET TESTING")
    else:
        print(f"\n⚠️ GPU Implementation: Issues detected - check logs above")

if __name__ == "__main__":
    main()