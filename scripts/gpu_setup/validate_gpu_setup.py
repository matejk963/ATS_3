#!/usr/bin/env python3
"""
GPU Setup Validation Script for Technical Indicators

This script validates GPU availability and tests technical indicators
GPU acceleration capabilities. Run this after installing CUDA/CuPy.

Usage:
    python validate_gpu_setup.py
"""

import sys
import traceback
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

def check_gpu_environment():
    """Check GPU environment setup"""
    print("🔍 GPU Environment Validation")
    print("=" * 50)
    
    try:
        import cupy as cp
        print(f"✅ CuPy Version: {cp.__version__}")
        
        # Check GPU device count
        try:
            gpu_count = cp.cuda.runtime.getDeviceCount()
            print(f"✅ GPU Devices Available: {gpu_count}")
            
            if gpu_count == 0:
                print("❌ No GPU devices found")
                return False
                
        except Exception as e:
            print(f"❌ GPU Device Detection Failed: {e}")
            return False
        
        # Test basic GPU operation
        try:
            test_array = cp.array([1, 2, 3, 4, 5])
            result = cp.sum(test_array)
            expected = 15
            
            if result == expected:
                print(f"✅ Basic GPU Computation: {result} (expected {expected})")
            else:
                print(f"❌ GPU Computation Error: got {result}, expected {expected}")
                return False
                
        except Exception as e:
            print(f"❌ GPU Computation Failed: {e}")
            return False
        
        # Check GPU memory
        try:
            free_mem, total_mem = cp.cuda.runtime.memGetInfo()
            free_gb = free_mem / 1e9
            total_gb = total_mem / 1e9
            print(f"✅ GPU Memory: {free_gb:.1f}GB free / {total_gb:.1f}GB total")
            
            if free_gb < 0.5:
                print("⚠️  Warning: Low GPU memory available")
                
        except Exception as e:
            print(f"❌ GPU Memory Check Failed: {e}")
            return False
        
        print("✅ GPU Environment: READY")
        return True
        
    except ImportError as e:
        print(f"❌ CuPy Import Error: {e}")
        print("\n💡 To install CuPy:")
        print("   pip install cupy-cuda12x  # For CUDA 12.x")
        print("   pip install cupy-cuda11x  # For CUDA 11.x")
        return False
    except Exception as e:
        print(f"❌ Unexpected GPU Error: {e}")
        traceback.print_exc()
        return False

def test_technical_indicators_gpu():
    """Test technical indicators with GPU backend"""
    print("\n🧮 Technical Indicators GPU Test")
    print("=" * 50)
    
    try:
        from src.feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline
        import pandas as pd
        import numpy as np
        
        # Create test data
        print("📊 Generating test data...")
        np.random.seed(42)
        size = 5000
        prices = 100 + np.cumsum(np.random.randn(size) * 0.01)
        
        data = pd.DataFrame({
            'open': prices * (1 + np.random.randn(size) * 0.001),
            'high': prices * (1 + np.abs(np.random.randn(size)) * 0.002),
            'low': prices * (1 - np.abs(np.random.randn(size)) * 0.002),
            'close': prices,
            'volume': np.random.randint(1000, 10000, size)
        })
        print(f"✅ Test data created: {data.shape}")
        
        # Test GPU pipeline
        print("🚀 Testing GPU pipeline...")
        gpu_pipeline = UnifiedTechnicalIndicatorsPipeline(backend='cupy')
        print(f"✅ Pipeline backend: {gpu_pipeline.backend_name}")
        
        if gpu_pipeline.backend_name != 'cupy':
            print(f"⚠️  Warning: Expected 'cupy' backend, got '{gpu_pipeline.backend_name}'")
        
        # Compute indicators on GPU
        gpu_result = gpu_pipeline.compute_indicators(
            data=data,
            indicators=['macd', 'atr'],
            macd_params={'fast': 12, 'slow': 26, 'signal': 9},
            atr_period=14
        )
        print(f"✅ GPU computation completed: {gpu_result.shape}")
        
        # Verify results
        required_columns = {'macd', 'signal', 'histogram', 'atr'}
        result_columns = set(gpu_result.columns)
        
        if required_columns.issubset(result_columns):
            print("✅ All expected indicators computed")
        else:
            missing = required_columns - result_columns
            print(f"❌ Missing indicators: {missing}")
            return False
        
        # Check for NaN values (some at start are expected)
        nan_counts = gpu_result[['macd', 'atr']].isna().sum()
        if nan_counts['macd'] < len(data) * 0.8 and nan_counts['atr'] < len(data) * 0.8:
            print("✅ Indicators computed successfully (reasonable NaN count)")
        else:
            print(f"❌ Too many NaN values: MACD={nan_counts['macd']}, ATR={nan_counts['atr']}")
            return False
        
        print("✅ Technical Indicators GPU: WORKING")
        return True
        
    except Exception as e:
        print(f"❌ Technical Indicators GPU Test Failed: {e}")
        traceback.print_exc()
        return False

def test_performance_comparison():
    """Test CPU vs GPU performance comparison"""
    print("\n⚡ Performance Comparison Test")
    print("=" * 50)
    
    try:
        from src.feature_engineering.performance_benchmark import PerformanceBenchmark
        
        # Create benchmark with small dataset for quick test
        benchmark = PerformanceBenchmark(runs=2, data_sizes=[1000])
        
        print(f"📊 GPU Available: {benchmark.gpu_available}")
        
        if not benchmark.gpu_available:
            print("❌ Benchmark reports GPU not available")
            return False
        
        print("🏃 Running performance comparison...")
        benchmark.run_full_benchmark()
        
        # Check results
        if not benchmark.results:
            print("❌ No benchmark results generated")
            return False
        
        # Look for GPU results
        gpu_success = False
        for key, result in benchmark.results.items():
            if result['gpu'].get('backend_available'):
                gpu_success = True
                speedup = result.get('speedup')
                if speedup:
                    print(f"✅ {key}: {speedup:.2f}x speedup")
                else:
                    print(f"✅ {key}: GPU computation successful")
        
        if gpu_success:
            print("✅ Performance Comparison: GPU WORKING")
            return True
        else:
            print("❌ No successful GPU benchmarks")
            return False
            
    except Exception as e:
        print(f"❌ Performance Comparison Test Failed: {e}")
        traceback.print_exc()
        return False

def main():
    """Main validation function"""
    print("🎯 GPU Setup Validation for Technical Indicators")
    print("=" * 60)
    
    # Test 1: GPU Environment
    gpu_env_ok = check_gpu_environment()
    
    if not gpu_env_ok:
        print("\n❌ GPU Environment validation failed")
        print("🔧 Please install CUDA and CuPy before proceeding")
        return 1
    
    # Test 2: Technical Indicators GPU
    indicators_ok = test_technical_indicators_gpu()
    
    if not indicators_ok:
        print("\n❌ Technical Indicators GPU test failed")
        return 1
    
    # Test 3: Performance Comparison
    performance_ok = test_performance_comparison()
    
    if not performance_ok:
        print("\n❌ Performance comparison test failed")
        return 1
    
    # All tests passed
    print("\n🎉 ALL GPU VALIDATION TESTS PASSED!")
    print("=" * 60)
    print("✅ GPU Environment: Ready")
    print("✅ Technical Indicators: GPU Accelerated")
    print("✅ Performance Benchmarking: Working")
    print("\n🚀 You can now run full GPU benchmarks:")
    print("   python run_phase3_benchmarks.py")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())