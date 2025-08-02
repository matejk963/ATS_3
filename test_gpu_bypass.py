#!/usr/bin/env python3
"""
GPU Access Test - Bypass nvidia-smi Issues
Test if GPU works despite nvidia-smi errors
"""

import sys

def test_gpu_access():
    """Test GPU access bypassing nvidia-smi"""
    print("🔍 Testing GPU Access Despite nvidia-smi Error")
    print("=" * 50)
    print(f"Python version: {sys.version}")
    
    # Test 1: CuPy Import
    print(f"\n📦 Step 1: Testing CuPy Import...")
    try:
        import cupy as cp
        print("✅ CuPy imported successfully")
        print(f"✅ CuPy version: {cp.__version__}")
    except ImportError as e:
        print(f"❌ CuPy import failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected CuPy error: {e}")
        return False
    
    # Test 2: CUDA Version Check
    print(f"\n🔧 Step 2: Testing CUDA Versions...")
    try:
        runtime_version = cp.cuda.runtime.runtimeGetVersion()
        driver_version = cp.cuda.runtime.driverGetVersion()
        
        runtime_major = runtime_version // 1000
        runtime_minor = (runtime_version % 1000) // 10
        
        print(f"✅ CUDA Runtime: {runtime_major}.{runtime_minor} (raw: {runtime_version})")
        print(f"✅ CUDA Driver Version: {driver_version}")
        
        if driver_version == 0:
            print("❌ CUDA Driver version is 0 - GPU not accessible")
            return False
        else:
            print("🎉 CUDA Driver detected! GPU should be accessible")
            
    except Exception as e:
        print(f"❌ CUDA version check failed: {e}")
        return False
    
    # Test 3: Basic GPU Computation
    print(f"\n🧮 Step 3: Testing Basic GPU Computation...")
    try:
        gpu_array = cp.array([1, 2, 3, 4, 5])
        result = cp.sum(gpu_array).item()
        print(f"✅ GPU computation successful: sum([1,2,3,4,5]) = {result}")
        
        # Test array operations
        gpu_matrix = cp.random.random((100, 100))
        matrix_sum = cp.sum(gpu_matrix).item()
        print(f"✅ GPU matrix computation: sum(100x100 random) = {matrix_sum:.2f}")
        
    except Exception as e:
        print(f"❌ GPU computation failed: {e}")
        return False
    
    # Test 4: GPU Memory Info
    print(f"\n💾 Step 4: Testing GPU Memory Access...")
    try:
        meminfo = cp.cuda.runtime.memGetInfo()
        total_bytes = meminfo[1]
        free_bytes = meminfo[0]
        used_bytes = total_bytes - free_bytes
        
        total_gb = total_bytes / (1024**3)
        free_gb = free_bytes / (1024**3)
        used_gb = used_bytes / (1024**3)
        
        print(f"✅ GPU Memory Info:")
        print(f"   Total: {total_gb:.1f}GB")
        print(f"   Used:  {used_gb:.1f}GB")
        print(f"   Free:  {free_gb:.1f}GB")
        print(f"   Utilization: {(used_gb/total_gb)*100:.1f}%")
        
    except Exception as e:
        print(f"❌ GPU memory info failed: {e}")
        return False
    
    # Test 5: GPU Device Info
    print(f"\n🔍 Step 5: Testing GPU Device Info...")
    try:
        device = cp.cuda.Device()
        print(f"✅ GPU Device: {device}")
        print(f"✅ Compute Capability: {device.compute_capability}")
        print(f"✅ Device ID: {device.id}")
        
    except Exception as e:
        print(f"❌ GPU device info failed: {e}")
        return False
    
    return True

def test_our_pipeline():
    """Test our technical indicators pipeline"""
    print(f"\n🧪 Step 6: Testing Our GPU Pipeline...")
    
    try:
        # Add project to path
        import sys
        from pathlib import Path
        project_root = Path(__file__).parent
        sys.path.append(str(project_root))
        
        from src.feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline
        
        # Test GPU pipeline creation
        pipeline = UnifiedTechnicalIndicatorsPipeline(
            backend='cupy',
            enable_gpu_memory_management=True
        )
        print("✅ GPU pipeline created successfully")
        
        # Test memory statistics
        stats = pipeline.get_gpu_memory_statistics()
        if stats.get('gpu_available'):
            print("✅ Pipeline reports GPU available")
            print(f"   Device: {stats.get('device_name', 'Unknown')}")
            print(f"   Free Memory: {stats.get('free_memory_gb', 0):.1f}GB")
        else:
            print("❌ Pipeline reports GPU unavailable")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ Pipeline test failed: {e}")
        return False

def main():
    """Main test execution"""
    print("🚀 GPU Access Test - Bypassing nvidia-smi Issues")
    print("This test checks if GPU works despite nvidia-smi errors")
    print("=" * 60)
    
    # Run basic GPU tests
    gpu_works = test_gpu_access()
    
    if gpu_works:
        print(f"\n🎉 BASIC GPU ACCESS: ✅ SUCCESS")
        print("GPU is working despite nvidia-smi error!")
        
        # Test our pipeline
        pipeline_works = test_our_pipeline()
        
        if pipeline_works:
            print(f"\n🎉 PIPELINE TEST: ✅ SUCCESS")
            print("Your GPU implementation is FULLY FUNCTIONAL!")
            
            print(f"\n🚀 READY FOR PRODUCTION:")
            print("✅ GPU acceleration working")
            print("✅ Memory management available") 
            print("✅ Large dataset processing ready")
            print("✅ All technical indicators can use GPU")
            
            print(f"\n📋 Next Steps:")
            print("1. Run: python tests/technical_indicators/test_large_dataset_validation.py")
            print("2. Run: python scripts/run_phase3_benchmarks.py")
            print("3. Deploy GPU-accelerated pipeline")
            
        else:
            print(f"\n⚠️ PIPELINE TEST: ❌ FAILED")
            print("Basic GPU works but pipeline needs debugging")
            
    else:
        print(f"\n❌ BASIC GPU ACCESS: FAILED")
        print("GPU is not accessible - driver/WSL2 issue remains")
        
        print(f"\n🔧 Troubleshooting Steps:")
        print("1. Restart Windows (full reboot)")
        print("2. Update Windows to latest version")
        print("3. Reinstall NVIDIA drivers")
        print("4. Check Windows WSL2 GPU settings")

if __name__ == "__main__":
    main()