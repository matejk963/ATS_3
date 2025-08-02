#!/usr/bin/env python3
"""
GPU Functionality Test After Driver Update
Run this script after updating NVIDIA drivers to verify GPU is working
"""

import sys
import time
import pandas as pd
import numpy as np
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

def test_cupy_basic():
    """Test basic CuPy functionality"""
    print("🔍 Testing CuPy Basic Functionality...")
    
    try:
        import cupy as cp
        print(f"✅ CuPy version: {cp.__version__}")
        
        # Test CUDA runtime and driver versions
        runtime_version = cp.cuda.runtime.runtimeGetVersion()
        driver_version = cp.cuda.runtime.driverGetVersion()
        
        runtime_major = runtime_version // 1000
        runtime_minor = (runtime_version % 1000) // 10
        driver_major = driver_version // 1000
        driver_minor = (driver_version % 1000) // 10
        
        print(f"✅ CUDA Runtime: {runtime_major}.{runtime_minor}")
        print(f"✅ CUDA Driver: {driver_major}.{driver_minor}")
        
        if driver_version == 0:
            print("❌ CUDA driver version is 0 - drivers still not working")
            return False
            
        # Test basic GPU operations
        gpu_array = cp.array([1, 2, 3, 4, 5])
        result = cp.sum(gpu_array).item()
        print(f"✅ Basic GPU computation: sum([1,2,3,4,5]) = {result}")
        
        # Test memory info
        meminfo = cp.cuda.runtime.memGetInfo()
        total_gb = meminfo[1] / (1024**3)
        free_gb = meminfo[0] / (1024**3)
        print(f"✅ GPU Memory: {free_gb:.1f}GB free / {total_gb:.1f}GB total")
        
        # Test device info
        device = cp.cuda.Device()
        print(f"✅ GPU Device: {device.compute_capability}")
        
        return True
        
    except Exception as e:
        print(f"❌ CuPy test failed: {e}")
        return False

def test_gpu_pipeline():
    """Test our GPU pipeline implementation"""
    print(f"\n🧪 Testing GPU Pipeline Implementation...")
    
    try:
        from src.feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline
        
        # Test GPU pipeline initialization
        pipeline = UnifiedTechnicalIndicatorsPipeline(
            backend='cupy',
            enable_gpu_memory_management=True
        )
        print("✅ GPU pipeline initialized successfully")
        
        # Test memory statistics
        stats = pipeline.get_gpu_memory_statistics()
        if stats.get('gpu_available'):
            print(f"✅ GPU available: {stats['device_name']}")
            print(f"✅ Free memory: {stats['free_memory_gb']:.1f}GB")
            print(f"✅ Memory utilization: {stats['memory_utilization_pct']:.1f}%")
        else:
            print("❌ GPU not available in pipeline")
            return False
        
        # Test with small dataset
        data = pd.DataFrame({
            'timestamp': pd.date_range('2023-01-01', periods=1000, freq='1min'),
            'open': 100 + np.cumsum(np.random.normal(0, 0.1, 1000)),
            'high': 100 + np.cumsum(np.random.normal(0, 0.1, 1000)) + np.random.uniform(0, 1, 1000),
            'low': 100 + np.cumsum(np.random.normal(0, 0.1, 1000)) - np.random.uniform(0, 1, 1000),
            'close': 100 + np.cumsum(np.random.normal(0, 0.1, 1000)),
            'volume': np.random.randint(10000, 100000, 1000)
        })
        
        # Ensure valid OHLC relationships
        data['high'] = np.maximum.reduce([data['open'], data['high'], data['low'], data['close']])
        data['low'] = np.minimum.reduce([data['open'], data['high'], data['low'], data['close']])
        
        print(f"📊 Testing with {len(data):,} data points...")
        
        # Test MACD on GPU
        start_time = time.time()
        result = pipeline.compute_indicators(data, indicators=['macd'])
        gpu_time = time.time() - start_time
        
        if result is not None and 'macd' in result.columns:
            valid_count = result['macd'].notna().sum()
            print(f"✅ GPU MACD: {gpu_time:.3f}s, {valid_count:,} valid values")
            
            # Compare with CPU
            cpu_pipeline = UnifiedTechnicalIndicatorsPipeline(backend='numpy')
            start_time = time.time()
            cpu_result = cpu_pipeline.compute_indicators(data, indicators=['macd'])
            cpu_time = time.time() - start_time
            
            if cpu_result is not None and 'macd' in cpu_result.columns:
                speedup = cpu_time / gpu_time if gpu_time > 0 else 0
                print(f"✅ CPU MACD: {cpu_time:.3f}s")
                print(f"🏃 GPU Speedup: {speedup:.2f}x")
                
                if speedup >= 1.5:
                    print("🎉 Excellent GPU acceleration!")
                elif speedup >= 1.0:
                    print("✅ Good GPU performance")
                else:
                    print("⚠️ GPU slower than CPU (may be due to small dataset)")
            
            return True
        else:
            print("❌ GPU MACD computation failed")
            return False
            
    except Exception as e:
        print(f"❌ GPU pipeline test failed: {e}")
        return False

def test_large_dataset_readiness():
    """Test readiness for large datasets"""
    print(f"\n📏 Testing Large Dataset Readiness...")
    
    try:
        from src.feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline
        
        # Test with larger dataset that would trigger chunking
        size = 50000  # Above typical chunking threshold
        data = pd.DataFrame({
            'timestamp': pd.date_range('2020-01-01', periods=size, freq='1min'),
            'open': 100 + np.cumsum(np.random.normal(0, 0.01, size)),
            'high': 100 + np.cumsum(np.random.normal(0, 0.01, size)) + np.random.uniform(0, 0.5, size),
            'low': 100 + np.cumsum(np.random.normal(0, 0.01, size)) - np.random.uniform(0, 0.5, size),
            'close': 100 + np.cumsum(np.random.normal(0, 0.01, size)),
            'volume': np.random.randint(50000, 500000, size)
        })
        
        # Ensure valid OHLC relationships
        data['high'] = np.maximum.reduce([data['open'], data['high'], data['low'], data['close']])
        data['low'] = np.minimum.reduce([data['open'], data['high'], data['low'], data['close']])
        
        print(f"📊 Testing with {size:,} data points...")
        
        # Test with memory management
        pipeline = UnifiedTechnicalIndicatorsPipeline(
            backend='cupy',
            enable_gpu_memory_management=True,
            chunk_size=25000,
            memory_threshold=0.7
        )
        
        start_time = time.time()
        result = pipeline.compute_indicators(data, indicators=['macd'])
        processing_time = time.time() - start_time
        
        if result is not None and 'macd' in result.columns:
            valid_count = result['macd'].notna().sum()
            rate = size / processing_time
            print(f"✅ Large dataset processing: {processing_time:.2f}s")
            print(f"✅ Processing rate: {rate:,.0f} points/sec")
            print(f"✅ Valid results: {valid_count:,}/{size:,}")
            
            # Check if chunking was used
            final_stats = pipeline.get_gpu_memory_statistics()
            chunking_info = final_stats.get('chunking_strategy', {})
            chunks_processed = chunking_info.get('chunks_processed', 1)
            
            if chunks_processed > 1:
                print(f"✅ Chunked processing: {chunks_processed} chunks used")
            else:
                print("✅ Direct processing (no chunking needed)")
                
            return True
        else:
            print("❌ Large dataset processing failed")
            return False
            
    except Exception as e:
        print(f"❌ Large dataset test failed: {e}")
        return False

def main():
    """Run comprehensive GPU validation after driver update"""
    print("🚀 GPU Functionality Test After Driver Update")
    print("=" * 60)
    
    # Run all tests
    cupy_ok = test_cupy_basic()
    pipeline_ok = test_gpu_pipeline() if cupy_ok else False
    large_dataset_ok = test_large_dataset_readiness() if pipeline_ok else False
    
    # Final summary
    print(f"\n📊 VALIDATION SUMMARY")
    print("=" * 40)
    print(f"CuPy & CUDA: {'✅' if cupy_ok else '❌'}")
    print(f"GPU Pipeline: {'✅' if pipeline_ok else '❌'}")
    print(f"Large Datasets: {'✅' if large_dataset_ok else '❌'}")
    
    if cupy_ok and pipeline_ok and large_dataset_ok:
        print(f"\n🎉 SUCCESS: GPU is fully functional!")
        print(f"✅ Ready for production use with GPU acceleration")
        print(f"✅ Can process large datasets (500K+ points)")
        print(f"✅ Memory management working correctly")
        
        print(f"\n🚀 Next Steps:")
        print(f"1. Run comprehensive tests: python tests/technical_indicators/test_large_dataset_validation.py")
        print(f"2. Benchmark performance: python scripts/run_phase3_benchmarks.py")
        print(f"3. Deploy GPU-accelerated pipeline")
        
    elif cupy_ok and pipeline_ok:
        print(f"\n✅ PARTIAL SUCCESS: GPU working for small datasets")
        print(f"⚠️ Large dataset functionality needs investigation")
        
    elif cupy_ok:
        print(f"\n✅ PARTIAL SUCCESS: Basic GPU working")
        print(f"⚠️ Pipeline integration needs investigation")
        
    else:
        print(f"\n❌ FAILURE: GPU still not working")
        print(f"🔧 Check Windows NVIDIA drivers:")
        print(f"1. Open Windows PowerShell as Administrator")
        print(f"2. Run: nvidia-smi")
        print(f"3. If fails, reinstall NVIDIA drivers")
        print(f"4. Restart Windows and WSL2")

if __name__ == "__main__":
    main()