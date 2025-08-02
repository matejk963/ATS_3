"""
Simple RTX 4080 SUPER Maximum GPU Utilization Test
Designed to achieve 90% GPU utilization visible in Task Manager
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


class SimpleGPUMaxUtilizer:
    """Simplified GPU maximum utilization for Task Manager visibility"""
    
    def __init__(self):
        self.gpu_arrays = []
        self.monitoring_active = False
        self.gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        
    def allocate_gpu_memory(self, target_gb=14.0):
        """Allocate maximum GPU memory"""
        print(f"🔄 Allocating {target_gb} GB GPU memory...")
        
        # Calculate array sizes
        bytes_per_gb = 1024**3
        total_bytes = int(target_gb * bytes_per_gb)
        num_arrays = 8
        elements_per_array = total_bytes // (num_arrays * 4)  # 4 bytes per float32
        
        self.gpu_arrays = []
        
        for i in range(num_arrays):
            print(f"  Array {i+1}/{num_arrays}: {elements_per_array/1e6:.1f}M elements... ", end="", flush=True)
            gpu_array = cp.random.random(elements_per_array, dtype=cp.float32)
            self.gpu_arrays.append(gpu_array)
            print("✅")
        
        # Calculate actual allocated memory
        total_elements = sum(len(arr) for arr in self.gpu_arrays)
        allocated_gb = (total_elements * 4) / (1024**3)
        print(f"✅ Total allocated: {allocated_gb:.1f} GB")
        
        return allocated_gb
    
    def monitor_gpu_stats(self):
        """Monitor and display GPU statistics"""
        def monitor_loop():
            while self.monitoring_active:
                try:
                    # Memory info
                    mem_info = pynvml.nvmlDeviceGetMemoryInfo(self.gpu_handle)
                    memory_used_gb = mem_info.used / (1024**3)
                    memory_total_gb = mem_info.total / (1024**3)
                    memory_percent = (mem_info.used / mem_info.total) * 100
                    
                    # GPU utilization
                    util = pynvml.nvmlDeviceGetUtilizationRates(self.gpu_handle)
                    gpu_percent = util.gpu
                    
                    # Temperature
                    temp_c = pynvml.nvmlDeviceGetTemperature(self.gpu_handle, pynvml.NVML_TEMPERATURE_GPU)
                    
                    # Display stats
                    print(f"\\r📊 GPU: {gpu_percent:3.0f}% | Memory: {memory_used_gb:4.1f}GB ({memory_percent:4.1f}%) | Temp: {temp_c:2.0f}°C", end="", flush=True)
                    
                except Exception:
                    pass
                
                time.sleep(1)
        
        self.monitoring_active = True
        monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        monitor_thread.start()
    
    def intensive_gpu_workload(self):
        """Simple but intensive GPU workload"""
        if not self.gpu_arrays:
            return
        
        # Parallel processing on all arrays
        for i, array in enumerate(self.gpu_arrays):
            # Mathematical operations to keep GPU busy
            
            # 1. Element-wise operations (all CUDA cores)
            result1 = cp.sin(array) * cp.cos(array) + cp.sqrt(cp.abs(array))
            
            # 2. Matrix operations (if array is large enough)
            if len(array) >= 10000:
                size = int(cp.sqrt(len(array) // 100))  # Safe size calculation
                if size > 10:
                    matrix_data = array[:size*size].reshape(size, size)
                    matrix_result = cp.dot(matrix_data, matrix_data.T)
            
            # 3. Reduction operations
            sum_result = cp.sum(result1)
            mean_result = cp.mean(result1)
            std_result = cp.std(result1)
            
            # 4. Convolution (memory intensive)
            if len(array) >= 1000:
                kernel_size = min(1000, len(array) // 1000)
                kernel = cp.ones(kernel_size) / kernel_size
                conv_result = cp.convolve(result1[:len(result1)//2], kernel, mode='valid')
        
        # Synchronize to ensure all operations complete
        cp.cuda.Stream.null.synchronize()
    
    def run_max_utilization_test(self, duration_seconds=60):
        """Run maximum GPU utilization test"""
        print(f"🎯 RTX 4080 SUPER Max Utilization Test")
        print(f"⏱️  Duration: {duration_seconds} seconds")
        print("="*50)
        
        try:
            # Step 1: Allocate maximum memory
            allocated_gb = self.allocate_gpu_memory(14.0)
            
            # Step 2: Start monitoring
            print(f"\\n📊 Starting GPU monitoring...")
            self.monitor_gpu_stats()
            time.sleep(2)  # Let monitoring start
            
            # Step 3: Display instructions
            print(f"\\n" + "="*50)
            print("📋 TASK MANAGER INSTRUCTIONS:")
            print("1. Open Task Manager (Ctrl+Shift+Esc)")
            print("2. Go to Performance tab")
            print("3. Select GPU 0 (RTX 4080 SUPER)")
            print("4. Watch GPU utilization and memory usage")
            print("="*50)
            
            input("\\n✅ Press Enter when Task Manager is ready...")
            
            # Step 4: Run intensive workload
            print(f"\\n🔥 Starting intensive GPU workload...")
            print("⚡ You should see 90%+ GPU utilization in Task Manager")
            
            start_time = time.time()
            iteration = 0
            
            while (time.time() - start_time) < duration_seconds:
                iteration += 1
                
                # Run intensive workload
                self.intensive_gpu_workload()
                
                # Small pause to prevent system overload
                time.sleep(0.05)
                
                # Progress update every 10 iterations
                if iteration % 10 == 0:
                    elapsed = time.time() - start_time
                    remaining = duration_seconds - elapsed
                    print(f"\\n⏱️  {elapsed:.1f}s elapsed, {remaining:.1f}s remaining (iteration {iteration})")
            
            print(f"\\n\\n✅ GPU utilization test completed!")
            
        except KeyboardInterrupt:
            print(f"\\n\\n⚠️  Test interrupted by user")
        except Exception as e:
            print(f"\\n\\n❌ Error: {e}")
        finally:
            # Cleanup
            self.monitoring_active = False
            self.cleanup_memory()
    
    def cleanup_memory(self):
        """Clean up GPU memory"""
        print(f"\\n🧹 Cleaning up GPU memory...")
        
        for i, array in enumerate(self.gpu_arrays):
            del array
        self.gpu_arrays.clear()
        
        # Force memory cleanup
        import gc
        gc.collect()
        
        try:
            mempool = cp.get_default_memory_pool()
            mempool.free_all_blocks()
        except:
            pass
        
        print("✅ GPU memory cleanup completed")


def main():
    """Main test function"""
    print("🚀 Simple RTX 4080 SUPER Max GPU Utilization Test")
    print("="*60)
    
    # Verify GPU is available
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
        
        print(f"📊 Detected GPU: {gpu_name}")
        print(f"💾 Total Memory: {total_memory_gb:.1f} GB")
        
    except Exception as e:
        print(f"⚠️  Could not get detailed GPU info: {e}")
    
    # Run the test
    try:
        utilizer = SimpleGPUMaxUtilizer()
        
        print(f"\\nSelect test duration:")
        print("1. Quick test (30 seconds)")
        print("2. Standard test (60 seconds)")
        print("3. Extended test (120 seconds)")
        print("4. Custom duration")
        
        choice = input("\\nEnter choice (1-4): ").strip()
        
        if choice == "1":
            duration = 30
        elif choice == "2":
            duration = 60
        elif choice == "3":
            duration = 120
        elif choice == "4":
            try:
                duration = int(input("Enter duration in seconds: "))
            except ValueError:
                print("Invalid input, using 60 seconds")
                duration = 60
        else:
            print("Invalid choice, using 60 seconds")
            duration = 60
        
        utilizer.run_max_utilization_test(duration)
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()