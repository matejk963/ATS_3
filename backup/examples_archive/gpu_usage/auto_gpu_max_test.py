"""
Automatic RTX 4080 SUPER Maximum GPU Utilization Test
Runs automatically for 60 seconds to show 90% GPU utilization in Task Manager
"""

import sys
from pathlib import Path
import time
import threading

# Add src to path
sys.path.append(str(Path(__file__).parent.parent.parent / "src"))

try:
    import cupy as cp
    import numpy as np
    import pynvml
    
    # Initialize NVIDIA Management Library
    pynvml.nvmlInit()
    
except ImportError as e:
    print(f"❌ Missing dependencies: {e}")
    print("💡 Install: pip install cupy-cuda12x pynvml")
    exit(1)


def run_gpu_max_utilization_test():
    """Run automatic GPU maximum utilization test"""
    print("🚀 RTX 4080 SUPER Automatic Max Utilization Test")
    print("="*60)
    
    # Verify GPU
    if not cp.cuda.is_available():
        print("❌ CUDA not available")
        return
    
    # Get GPU info
    try:
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        gpu_name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(gpu_name, bytes):
            gpu_name = gpu_name.decode('utf-8')
        
        mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        total_memory_gb = mem_info.total / (1024**3)
        
        print(f"📊 GPU: {gpu_name}")
        print(f"💾 Memory: {total_memory_gb:.1f} GB")
        
    except Exception as e:
        print(f"⚠️  Could not get GPU info: {e}")
        return
    
    print("\\n🎯 Test Plan:")
    print("1. Allocate 14GB GPU memory (90% of 16GB)")
    print("2. Run intensive compute workload")
    print("3. Monitor for 60 seconds")
    print("4. Display stats every 5 seconds")
    
    print("\\n📋 TASK MANAGER INSTRUCTIONS:")
    print("• Open Task Manager (Ctrl+Shift+Esc)")
    print("• Go to Performance → GPU 0")
    print("• Watch GPU utilization spike to 90%+")
    print("• Watch GPU memory usage reach ~14GB")
    
    print("\\n🔄 Starting in 3 seconds...")
    time.sleep(3)
    
    gpu_arrays = []
    monitoring_active = True
    
    try:
        # Step 1: Allocate maximum GPU memory (14GB)
        print("\\n🔄 Allocating 14GB GPU memory...")
        
        target_gb = 14.0
        num_arrays = 8
        elements_per_array = int((target_gb * 1024**3) / (num_arrays * 4))  # 4 bytes per float32
        
        for i in range(num_arrays):
            print(f"  Array {i+1}/{num_arrays}: {elements_per_array/1e6:.1f}M elements... ", end="", flush=True)
            gpu_array = cp.random.random(elements_per_array, dtype=cp.float32)
            gpu_arrays.append(gpu_array)
            print("✅")
        
        print(f"✅ Allocated {len(gpu_arrays)} arrays totaling ~14GB")
        
        # Step 2: Start monitoring thread
        def monitor_stats():
            while monitoring_active:
                try:
                    mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                    util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                    temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                    
                    memory_gb = mem_info.used / (1024**3)
                    memory_percent = (mem_info.used / mem_info.total) * 100
                    gpu_percent = util.gpu
                    
                    print(f"\\r📊 GPU: {gpu_percent:3.0f}% | Memory: {memory_gb:4.1f}GB ({memory_percent:4.1f}%) | Temp: {temp:2.0f}°C", end="", flush=True)
                    
                except Exception:
                    pass
                
                time.sleep(1)
        
        monitor_thread = threading.Thread(target=monitor_stats, daemon=True)
        monitor_thread.start()
        
        # Step 3: Run intensive GPU workload for 60 seconds
        print("\\n\\n🔥 Starting intensive GPU workload for 60 seconds...")
        print("⚡ Check Task Manager now - you should see 90%+ GPU utilization")
        
        start_time = time.time()
        iteration = 0
        
        while (time.time() - start_time) < 60:
            iteration += 1
            
            # Intensive GPU operations on all arrays simultaneously
            for i, array in enumerate(gpu_arrays):
                # Mathematical operations using all CUDA cores
                result = cp.sin(array) * cp.cos(array) + cp.sqrt(cp.abs(array))
                result = result ** 2 + cp.log(cp.abs(result) + 1)
                
                # Matrix operations for tensor cores (if large enough)
                if len(array) >= 40000:  # Safe size check
                    size = 200  # Fixed safe matrix size
                    matrix_data = array[:size*size].reshape(size, size)
                    matrix_result = cp.dot(matrix_data, matrix_data.T)
                
                # Reduction operations
                total = cp.sum(result) + cp.mean(result) + cp.std(result)
            
            # Synchronize GPU operations
            cp.cuda.Stream.null.synchronize()
            
            # Progress update every 50 iterations (~5 seconds)
            if iteration % 50 == 0:
                elapsed = time.time() - start_time
                remaining = 60 - elapsed
                print(f"\\n⏱️  {elapsed:.1f}s elapsed, {remaining:.1f}s remaining (iter {iteration})")
        
        print("\\n\\n✅ 60-second GPU utilization test completed!")
        
        # Final stats
        try:
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            
            print(f"\\n📊 Final Stats:")
            print(f"   GPU Utilization: {util.gpu}%")
            print(f"   Memory Used: {mem_info.used / (1024**3):.1f}GB ({(mem_info.used / mem_info.total) * 100:.1f}%)")
            print(f"   Temperature: {temp}°C")
            
        except Exception:
            pass
        
    except Exception as e:
        print(f"\\n❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup
        monitoring_active = False
        print("\\n🧹 Cleaning up GPU memory...")
        
        for array in gpu_arrays:
            del array
        gpu_arrays.clear()
        
        import gc
        gc.collect()
        
        try:
            mempool = cp.get_default_memory_pool()
            mempool.free_all_blocks()
        except:
            pass
        
        print("✅ Cleanup completed")
        
        print("\\n🎯 Test Summary:")
        print("• GPU memory was allocated to ~14GB (90% utilization)")
        print("• Intensive compute workload ran for 60 seconds")
        print("• Task Manager should have shown high GPU activity")
        print("• Temperature should have risen during the test")


if __name__ == "__main__":
    run_gpu_max_utilization_test()