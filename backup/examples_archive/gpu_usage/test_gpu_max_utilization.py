"""
Test Script for RTX 4080 SUPER Maximum GPU Utilization
Simple script to verify 90% GPU utilization visible in Task Manager
"""

import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent.parent / "src"))

from gpu_usage.gpu_max_utilizer import RTX4080SuperMaxUtilizer

def test_gpu_utilization():
    """Test GPU utilization with visual Task Manager confirmation"""
    print("🎯 RTX 4080 SUPER GPU Utilization Test")
    print("="*50)
    
    try:
        # Initialize the utilizer
        print("🔧 Initializing GPU utilizer...")
        utilizer = RTX4080SuperMaxUtilizer()
        
        # Show GPU specs
        print(f"\n📊 RTX 4080 SUPER Specifications:")
        print(f"   CUDA Cores: {utilizer.specs.cuda_cores:,}")
        print(f"   Memory: {utilizer.specs.memory_gb} GB")
        print(f"   Memory Bandwidth: {utilizer.specs.memory_bandwidth_gbps} GB/s")
        print(f"   Architecture: {utilizer.specs.architecture}")
        
        # Quick benchmark
        print(f"\n🚀 Running performance benchmark...")
        utilizer.benchmark_gpu_performance()
        
        # Ask user to prepare Task Manager
        print(f"\n" + "="*50)
        print("📋 TASK MANAGER PREPARATION:")
        print("="*50)
        print("1. Open Task Manager (Ctrl+Shift+Esc)")
        print("2. Click on 'Performance' tab")
        print("3. Select 'GPU 0' from the left panel")
        print("4. You should see your RTX 4080 SUPER")
        print("5. Watch the GPU utilization graphs")
        print("="*50)
        
        input("\n✅ Press Enter when Task Manager is ready...")
        
        # Run maximum utilization test
        print(f"\n🔥 Starting 90% GPU utilization test...")
        print("⚡ You should now see:")
        print("   • GPU utilization spike to 90%+")
        print("   • GPU memory usage increase to ~14GB")
        print("   • Temperature rise to 75-80°C")
        print("   • Power usage increase significantly")
        
        # Run for 2 minutes - enough to see in Task Manager
        utilizer.run_max_utilization(
            duration_minutes=2.0,
            target_memory_percent=90.0,
            target_core_percent=90.0,
            show_task_manager_stats=True
        )
        
        print(f"\n✅ GPU utilization test completed!")
        print(f"📊 Check Task Manager to confirm the results")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

def quick_verification():
    """Quick verification that GPU is working"""
    print("🔍 Quick GPU Verification")
    print("-" * 30)
    
    try:
        import cupy as cp
        
        # Test basic GPU functionality
        print("Testing CUDA availability...", end=" ")
        gpu_available = cp.cuda.is_available()
        print("✅" if gpu_available else "❌")
        
        if gpu_available:
            print("Testing GPU memory allocation...", end=" ")
            test_array = cp.random.random(1000000, dtype=cp.float32)
            print("✅")
            
            print("Testing GPU computation...", end=" ")
            result = cp.sum(test_array)
            print("✅")
            
            print("Testing GPU memory info...", end=" ")
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            gpu_name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(gpu_name, bytes):
                gpu_name = gpu_name.decode('utf-8')
            print("✅")
            
            print(f"\n📊 GPU Info:")
            print(f"   Name: {gpu_name}")
            print(f"   Total Memory: {mem_info.total / (1024**3):.1f} GB")
            print(f"   Free Memory: {mem_info.free / (1024**3):.1f} GB")
            
            # Cleanup
            del test_array
            
            return True
        else:
            print("❌ CUDA not available")
            return False
            
    except ImportError as e:
        print(f"❌ Missing dependencies: {e}")
        print("💡 Install: pip install cupy-cuda12x pynvml")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    """Main test function"""
    print("🚀 RTX 4080 SUPER GPU Utilization Test Suite")
    print("="*60)
    
    # Quick verification first
    if not quick_verification():
        print("❌ GPU verification failed. Cannot proceed with utilization test.")
        return
    
    print("\n" + "="*60)
    print("Select test type:")
    print("1. Full utilization test (2 minutes)")
    print("2. Quick test (30 seconds)")
    print("3. Exit")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    if choice == "1":
        test_gpu_utilization()
    elif choice == "2":
        try:
            utilizer = RTX4080SuperMaxUtilizer()
            utilizer.quick_gpu_test(30)
        except Exception as e:
            print(f"❌ Quick test failed: {e}")
    elif choice == "3":
        print("Exiting...")
    else:
        print("Invalid choice")

if __name__ == "__main__":
    main()