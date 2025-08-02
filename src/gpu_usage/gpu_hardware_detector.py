"""
GPU Hardware Detection and Validation System
Comprehensive GPU capability assessment for parallel processing
"""

import logging
import platform
import subprocess
import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

try:
    import cupy as cp
    import numpy as np
    CUPY_AVAILABLE = True
except ImportError:
    import numpy as np
    CUPY_AVAILABLE = False

try:
    import pynvml
    PYNVML_AVAILABLE = True
except ImportError:
    PYNVML_AVAILABLE = False


class GPUCapabilityLevel(Enum):
    """GPU capability levels for processing"""
    NONE = "none"
    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


@dataclass
class GPUHardwareInfo:
    """Comprehensive GPU hardware information"""
    gpu_available: bool
    gpu_count: int
    gpu_names: List[str]
    total_memory: List[int]  # MB
    compute_capability: List[Tuple[int, int]]
    cuda_version: Optional[str]
    driver_version: Optional[str]
    architecture: List[str]
    multiprocessor_count: List[int]
    memory_bandwidth: List[float]  # GB/s
    capability_level: GPUCapabilityLevel
    recommended_chunk_size: int
    max_safe_memory_usage: float  # Percentage


@dataclass
class GPUBenchmarkResults:
    """GPU benchmark performance results"""
    memory_bandwidth_gbps: float
    compute_performance_gflops: float
    memory_latency_ms: float
    parallel_efficiency: float
    cpu_gpu_speedup: float
    optimal_chunk_size: int


class GPUHardwareDetector:
    """Comprehensive GPU hardware detection and capability assessment"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._gpu_info: Optional[GPUHardwareInfo] = None
        self._benchmark_results: Optional[GPUBenchmarkResults] = None
    
    def detect_gpu_hardware(self) -> GPUHardwareInfo:
        """Detect and validate GPU hardware capabilities"""
        if self._gpu_info is not None:
            return self._gpu_info
        
        self.logger.info("Starting GPU hardware detection...")
        
        # Initialize default values
        gpu_info = GPUHardwareInfo(
            gpu_available=False,
            gpu_count=0,
            gpu_names=[],
            total_memory=[],
            compute_capability=[],
            cuda_version=None,
            driver_version=None,
            architecture=[],
            multiprocessor_count=[],
            memory_bandwidth=[],
            capability_level=GPUCapabilityLevel.NONE,
            recommended_chunk_size=1000,
            max_safe_memory_usage=50.0
        )
        
        if not CUPY_AVAILABLE:
            self.logger.warning("CuPy not available - GPU processing disabled")
            self._gpu_info = gpu_info
            return gpu_info
        
        try:
            # Basic CUDA availability check
            gpu_info.gpu_available = cp.cuda.is_available()
            if not gpu_info.gpu_available:
                self.logger.warning("CUDA not available")
                self._gpu_info = gpu_info
                return gpu_info
            
            # Get GPU count
            gpu_info.gpu_count = cp.cuda.runtime.getDeviceCount()
            self.logger.info(f"Detected {gpu_info.gpu_count} GPU(s)")
            
            # Get CUDA version
            cuda_version = cp.cuda.runtime.runtimeGetVersion()
            gpu_info.cuda_version = f"{cuda_version // 1000}.{(cuda_version % 1000) // 10}"
            
            # Collect information for each GPU
            for device_id in range(gpu_info.gpu_count):
                self._collect_gpu_device_info(device_id, gpu_info)
            
            # Determine capability level
            gpu_info.capability_level = self._assess_capability_level(gpu_info)
            
            # Set recommendations based on capability
            self._set_recommendations(gpu_info)
            
            self.logger.info(f"GPU detection complete - Capability: {gpu_info.capability_level.value}")
            
        except Exception as e:
            self.logger.error(f"GPU hardware detection failed: {e}")
            gpu_info.gpu_available = False
        
        self._gpu_info = gpu_info
        return gpu_info
    
    def _collect_gpu_device_info(self, device_id: int, gpu_info: GPUHardwareInfo) -> None:
        """Collect detailed information for a specific GPU device"""
        try:
            with cp.cuda.Device(device_id):
                # Get device properties
                props = cp.cuda.runtime.getDeviceProperties(device_id)
                
                # GPU name
                gpu_info.gpu_names.append(props['name'].decode('utf-8'))
                
                # Memory info
                total_memory_bytes = props['totalGlobalMem']
                gpu_info.total_memory.append(total_memory_bytes // (1024 * 1024))  # Convert to MB
                
                # Compute capability
                major = props['major']
                minor = props['minor']
                gpu_info.compute_capability.append((major, minor))
                
                # Architecture detection
                arch = self._detect_architecture(major, minor)
                gpu_info.architecture.append(arch)
                
                # Multiprocessor count
                gpu_info.multiprocessor_count.append(props['multiProcessorCount'])
                
                # Estimate memory bandwidth (simplified calculation)
                memory_clock_khz = props.get('memoryClockRate', 0)
                memory_bus_width = props.get('memoryBusWidth', 0)
                bandwidth_gbps = (memory_clock_khz * 1000 * memory_bus_width * 2) / (8 * 1e9)
                gpu_info.memory_bandwidth.append(bandwidth_gbps)
                
                self.logger.info(f"GPU {device_id}: {gpu_info.gpu_names[-1]} - "
                               f"{gpu_info.total_memory[-1]}MB - "
                               f"Compute {major}.{minor}")
                
        except Exception as e:
            self.logger.error(f"Failed to collect info for GPU {device_id}: {e}")
    
    def _detect_architecture(self, major: int, minor: int) -> str:
        """Detect GPU architecture from compute capability"""
        arch_map = {
            (3, 0): "Kepler", (3, 5): "Kepler", (3, 7): "Kepler",
            (5, 0): "Maxwell", (5, 2): "Maxwell", (5, 3): "Maxwell",
            (6, 0): "Pascal", (6, 1): "Pascal", (6, 2): "Pascal",
            (7, 0): "Volta", (7, 2): "Volta", (7, 5): "Turing",
            (8, 0): "Ampere", (8, 6): "Ampere", (8, 7): "Ampere", (8, 9): "Ada Lovelace",
            (9, 0): "Hopper"
        }
        return arch_map.get((major, minor), f"Unknown-{major}.{minor}")
    
    def _assess_capability_level(self, gpu_info: GPUHardwareInfo) -> GPUCapabilityLevel:
        """Assess overall GPU capability level"""
        if not gpu_info.gpu_available or gpu_info.gpu_count == 0:
            return GPUCapabilityLevel.NONE
        
        # Get the best GPU specs
        max_memory = max(gpu_info.total_memory) if gpu_info.total_memory else 0
        best_compute = max(gpu_info.compute_capability) if gpu_info.compute_capability else (0, 0)
        max_bandwidth = max(gpu_info.memory_bandwidth) if gpu_info.memory_bandwidth else 0
        
        # Assess capability level
        major, minor = best_compute
        compute_score = major * 10 + minor
        
        if max_memory >= 12000 and compute_score >= 75 and max_bandwidth >= 400:  # High-end GPUs
            return GPUCapabilityLevel.EXPERT
        elif max_memory >= 8000 and compute_score >= 60 and max_bandwidth >= 200:  # Mid-high GPUs
            return GPUCapabilityLevel.ADVANCED
        elif max_memory >= 4000 and compute_score >= 50:  # Mid-range GPUs
            return GPUCapabilityLevel.INTERMEDIATE
        elif max_memory >= 2000 and compute_score >= 30:  # Entry-level GPUs
            return GPUCapabilityLevel.BASIC
        else:
            return GPUCapabilityLevel.NONE
    
    def _set_recommendations(self, gpu_info: GPUHardwareInfo) -> None:
        """Set recommended settings based on GPU capability"""
        capability_settings = {
            GPUCapabilityLevel.EXPERT: (2000000, 85.0),    # 2M chunk, 85% memory
            GPUCapabilityLevel.ADVANCED: (1000000, 75.0),  # 1M chunk, 75% memory
            GPUCapabilityLevel.INTERMEDIATE: (500000, 65.0), # 500K chunk, 65% memory
            GPUCapabilityLevel.BASIC: (100000, 50.0),      # 100K chunk, 50% memory
            GPUCapabilityLevel.NONE: (1000, 0.0)           # CPU fallback
        }
        
        chunk_size, memory_usage = capability_settings[gpu_info.capability_level]
        gpu_info.recommended_chunk_size = chunk_size
        gpu_info.max_safe_memory_usage = memory_usage
    
    def run_gpu_benchmark(self, data_size: int = 1000000) -> GPUBenchmarkResults:
        """Run comprehensive GPU benchmark"""
        if self._benchmark_results is not None:
            return self._benchmark_results
        
        self.logger.info(f"Running GPU benchmark with {data_size} data points...")
        
        if not self._gpu_info or not self._gpu_info.gpu_available:
            # CPU-only benchmark
            return self._run_cpu_benchmark(data_size)
        
        try:
            # Memory bandwidth test
            memory_bandwidth = self._benchmark_memory_bandwidth(data_size)
            
            # Compute performance test
            compute_performance = self._benchmark_compute_performance(data_size)
            
            # Memory latency test
            memory_latency = self._benchmark_memory_latency()
            
            # Parallel efficiency test
            parallel_efficiency = self._benchmark_parallel_efficiency(data_size)
            
            # CPU vs GPU speedup test
            cpu_gpu_speedup = self._benchmark_cpu_gpu_speedup(data_size)
            
            # Optimal chunk size test
            optimal_chunk_size = self._benchmark_optimal_chunk_size()
            
            results = GPUBenchmarkResults(
                memory_bandwidth_gbps=memory_bandwidth,
                compute_performance_gflops=compute_performance,
                memory_latency_ms=memory_latency,
                parallel_efficiency=parallel_efficiency,
                cpu_gpu_speedup=cpu_gpu_speedup,
                optimal_chunk_size=optimal_chunk_size
            )
            
            self.logger.info(f"GPU benchmark complete - Speedup: {cpu_gpu_speedup:.2f}x")
            self._benchmark_results = results
            return results
            
        except Exception as e:
            self.logger.error(f"GPU benchmark failed: {e}")
            return self._run_cpu_benchmark(data_size)
    
    def _benchmark_memory_bandwidth(self, data_size: int) -> float:
        """Benchmark GPU memory bandwidth"""
        try:
            # Create large arrays for memory bandwidth test
            data = cp.random.random(data_size, dtype=cp.float32)
            result = cp.zeros_like(data)
            
            # Warm up
            for _ in range(3):
                result = data * 2.0
                cp.cuda.Stream.null.synchronize()
            
            # Actual benchmark
            start_time = time.perf_counter()
            iterations = 10
            
            for _ in range(iterations):
                result = data * 2.0
                cp.cuda.Stream.null.synchronize()
            
            end_time = time.perf_counter()
            
            # Calculate bandwidth (read + write)
            total_bytes = data_size * 4 * 2 * iterations  # float32 * read&write * iterations
            total_time = end_time - start_time
            bandwidth_gbps = (total_bytes / total_time) / (1024**3)
            
            return bandwidth_gbps
            
        except Exception as e:
            self.logger.error(f"Memory bandwidth benchmark failed: {e}")
            return 0.0
    
    def _benchmark_compute_performance(self, data_size: int) -> float:
        """Benchmark GPU compute performance (GFLOPS)"""
        try:
            # Matrix multiplication benchmark
            size = int(np.sqrt(data_size))
            a = cp.random.random((size, size), dtype=cp.float32)
            b = cp.random.random((size, size), dtype=cp.float32)
            
            # Warm up
            for _ in range(3):
                c = cp.dot(a, b)
                cp.cuda.Stream.null.synchronize()
            
            # Actual benchmark
            start_time = time.perf_counter()
            iterations = 5
            
            for _ in range(iterations):
                c = cp.dot(a, b)
                cp.cuda.Stream.null.synchronize()
            
            end_time = time.perf_counter()
            
            # Calculate GFLOPS
            operations = 2 * size**3 * iterations  # Multiply-add operations
            total_time = end_time - start_time
            gflops = operations / (total_time * 1e9)
            
            return gflops
            
        except Exception as e:
            self.logger.error(f"Compute performance benchmark failed: {e}")
            return 0.0
    
    def _benchmark_memory_latency(self) -> float:
        """Benchmark GPU memory latency"""
        try:
            # Small random access pattern
            indices = cp.random.randint(0, 10000, 1000, dtype=cp.int32)
            data = cp.random.random(10000, dtype=cp.float32)
            
            # Warm up
            for _ in range(10):
                result = data[indices]
                cp.cuda.Stream.null.synchronize()
            
            # Actual benchmark
            start_time = time.perf_counter()
            iterations = 100
            
            for _ in range(iterations):
                result = data[indices]
                cp.cuda.Stream.null.synchronize()
            
            end_time = time.perf_counter()
            
            # Calculate average latency
            total_time = end_time - start_time
            latency_ms = (total_time / iterations) * 1000
            
            return latency_ms
            
        except Exception as e:
            self.logger.error(f"Memory latency benchmark failed: {e}")
            return 999.0
    
    def _benchmark_parallel_efficiency(self, data_size: int) -> float:
        """Benchmark parallel processing efficiency"""
        try:
            # Compare single-threaded vs parallel execution
            data = cp.random.random(data_size, dtype=cp.float32)
            
            # Sequential processing simulation
            start_time = time.perf_counter()
            result_seq = cp.cumsum(data)
            cp.cuda.Stream.null.synchronize()
            seq_time = time.perf_counter() - start_time
            
            # Parallel processing
            start_time = time.perf_counter()
            result_par = cp.sort(data)  # Parallel sort
            cp.cuda.Stream.null.synchronize()
            par_time = time.perf_counter() - start_time
            
            # Calculate efficiency (higher is better)
            efficiency = min(seq_time / par_time, 100.0) if par_time > 0 else 0.0
            return efficiency * 100  # Percentage
            
        except Exception as e:
            self.logger.error(f"Parallel efficiency benchmark failed: {e}")
            return 0.0
    
    def _benchmark_cpu_gpu_speedup(self, data_size: int) -> float:
        """Benchmark CPU vs GPU speedup"""
        try:
            # CPU benchmark
            cpu_data = np.random.random(data_size).astype(np.float32)
            
            start_time = time.perf_counter()
            cpu_result = np.sort(cpu_data)
            cpu_time = time.perf_counter() - start_time
            
            # GPU benchmark
            gpu_data = cp.asarray(cpu_data)
            
            # Warm up
            for _ in range(3):
                gpu_result = cp.sort(gpu_data)
                cp.cuda.Stream.null.synchronize()
            
            start_time = time.perf_counter()
            gpu_result = cp.sort(gpu_data)
            cp.cuda.Stream.null.synchronize()
            gpu_time = time.perf_counter() - start_time
            
            # Calculate speedup
            speedup = cpu_time / gpu_time if gpu_time > 0 else 0.0
            return speedup
            
        except Exception as e:
            self.logger.error(f"CPU vs GPU speedup benchmark failed: {e}")
            return 1.0
    
    def _benchmark_optimal_chunk_size(self) -> int:
        """Find optimal chunk size for GPU processing"""
        try:
            chunk_sizes = [1000, 10000, 100000, 500000, 1000000]
            best_throughput = 0
            optimal_size = 100000
            
            for chunk_size in chunk_sizes:
                try:
                    # Test processing throughput
                    data = cp.random.random(chunk_size, dtype=cp.float32)
                    
                    start_time = time.perf_counter()
                    iterations = 10
                    
                    for _ in range(iterations):
                        result = cp.sqrt(data * data + 1.0)
                        cp.cuda.Stream.null.synchronize()
                    
                    end_time = time.perf_counter()
                    
                    # Calculate throughput
                    total_time = end_time - start_time
                    throughput = (chunk_size * iterations) / total_time
                    
                    if throughput > best_throughput:
                        best_throughput = throughput
                        optimal_size = chunk_size
                        
                except Exception:
                    continue
            
            return optimal_size
            
        except Exception as e:
            self.logger.error(f"Optimal chunk size benchmark failed: {e}")
            return 100000
    
    def _run_cpu_benchmark(self, data_size: int) -> GPUBenchmarkResults:
        """Run CPU-only benchmark as fallback"""
        self.logger.info("Running CPU-only benchmark...")
        
        try:
            # Simple CPU performance test
            data = np.random.random(min(data_size, 100000)).astype(np.float32)
            
            start_time = time.perf_counter()
            result = np.sort(data)
            cpu_time = time.perf_counter() - start_time
            
            # Estimate CPU performance metrics
            throughput = len(data) / cpu_time
            
            return GPUBenchmarkResults(
                memory_bandwidth_gbps=0.1,  # Typical system RAM bandwidth
                compute_performance_gflops=0.1,
                memory_latency_ms=100.0,
                parallel_efficiency=10.0,
                cpu_gpu_speedup=1.0,  # No speedup for CPU-only
                optimal_chunk_size=10000
            )
            
        except Exception as e:
            self.logger.error(f"CPU benchmark failed: {e}")
            return GPUBenchmarkResults(
                memory_bandwidth_gbps=0.0,
                compute_performance_gflops=0.0,
                memory_latency_ms=999.0,
                parallel_efficiency=0.0,
                cpu_gpu_speedup=1.0,
                optimal_chunk_size=1000
            )
    
    def get_gpu_info(self) -> GPUHardwareInfo:
        """Get cached GPU hardware information"""
        if self._gpu_info is None:
            return self.detect_gpu_hardware()
        return self._gpu_info
    
    def get_benchmark_results(self) -> Optional[GPUBenchmarkResults]:
        """Get cached benchmark results"""
        return self._benchmark_results
    
    def validate_gpu_processing_capability(self) -> bool:
        """Verify GPU can handle technical indicator computations"""
        gpu_info = self.get_gpu_info()
        
        if not gpu_info.gpu_available:
            return False
        
        # Run quick validation test
        try:
            test_data = cp.random.random(10000, dtype=cp.float32)
            result = cp.sqrt(test_data * test_data + 1.0)
            cp.cuda.Stream.null.synchronize()
            
            # Verify result is reasonable
            cpu_result = np.sqrt(cp.asnumpy(test_data) ** 2 + 1.0)
            gpu_result = cp.asnumpy(result)
            
            # Check if results are close (allowing for floating point differences)
            max_diff = np.max(np.abs(cpu_result - gpu_result))
            return max_diff < 1e-5
            
        except Exception as e:
            self.logger.error(f"GPU processing validation failed: {e}")
            return False
    
    def print_gpu_info(self) -> None:
        """Print comprehensive GPU information"""
        gpu_info = self.get_gpu_info()
        
        print("\n" + "="*60)
        print("GPU HARDWARE DETECTION REPORT")
        print("="*60)
        
        if not gpu_info.gpu_available:
            print("❌ No GPU available for processing")
            print("   - CuPy available:", CUPY_AVAILABLE)
            print("   - Falling back to CPU processing")
            return
        
        print(f"✅ GPU Processing Available")
        print(f"📊 Capability Level: {gpu_info.capability_level.value.upper()}")
        print(f"🔢 GPU Count: {gpu_info.gpu_count}")
        
        if gpu_info.cuda_version:
            print(f"🔧 CUDA Version: {gpu_info.cuda_version}")
        
        print("\nGPU Details:")
        for i in range(gpu_info.gpu_count):
            print(f"\n  GPU {i}:")
            if i < len(gpu_info.gpu_names):
                print(f"    Name: {gpu_info.gpu_names[i]}")
            if i < len(gpu_info.total_memory):
                print(f"    Memory: {gpu_info.total_memory[i]:,} MB")
            if i < len(gpu_info.compute_capability):
                major, minor = gpu_info.compute_capability[i]
                print(f"    Compute Capability: {major}.{minor}")
            if i < len(gpu_info.architecture):
                print(f"    Architecture: {gpu_info.architecture[i]}")
            if i < len(gpu_info.memory_bandwidth):
                print(f"    Memory Bandwidth: {gpu_info.memory_bandwidth[i]:.1f} GB/s")
        
        print(f"\nRecommended Settings:")
        print(f"  Chunk Size: {gpu_info.recommended_chunk_size:,} points")
        print(f"  Max Memory Usage: {gpu_info.max_safe_memory_usage:.1f}%")
        
        # Print benchmark results if available
        if self._benchmark_results:
            results = self._benchmark_results
            print(f"\nBenchmark Results:")
            print(f"  Memory Bandwidth: {results.memory_bandwidth_gbps:.2f} GB/s")
            print(f"  Compute Performance: {results.compute_performance_gflops:.2f} GFLOPS")
            print(f"  Memory Latency: {results.memory_latency_ms:.2f} ms")
            print(f"  Parallel Efficiency: {results.parallel_efficiency:.1f}%")
            print(f"  CPU vs GPU Speedup: {results.cpu_gpu_speedup:.2f}x")
            print(f"  Optimal Chunk Size: {results.optimal_chunk_size:,}")
        
        print("="*60)


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)
    
    detector = GPUHardwareDetector()
    
    # Detect GPU hardware
    gpu_info = detector.detect_gpu_hardware()
    detector.print_gpu_info()
    
    # Run benchmark if GPU is available
    if gpu_info.gpu_available:
        print("\nRunning GPU benchmark...")
        benchmark_results = detector.run_gpu_benchmark()
        detector.print_gpu_info()  # Print updated info with benchmark results
        
        # Validate processing capability
        is_valid = detector.validate_gpu_processing_capability()
        print(f"\nGPU Processing Validation: {'✅ PASSED' if is_valid else '❌ FAILED'}")