"""
GPU Parallel Processing Engine
High-performance parallel data processing using CUDA/CuPy
"""

import logging
import time
import warnings
from typing import Union, List, Callable, Any, Optional, Dict, Tuple
from dataclasses import dataclass
from enum import Enum
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import cupy as cp
    import numpy as np
    CUPY_AVAILABLE = True
except ImportError:
    import numpy as np
    CUPY_AVAILABLE = False

from .gpu_hardware_detector import GPUHardwareDetector, GPUCapabilityLevel


class ProcessingMode(Enum):
    """Processing mode selection"""
    AUTO = "auto"           # Automatically choose best method
    GPU_ONLY = "gpu_only"   # Force GPU processing
    CPU_ONLY = "cpu_only"   # Force CPU processing
    HYBRID = "hybrid"       # Use both GPU and CPU


class DataType(Enum):
    """Supported data types for processing"""
    FLOAT32 = np.float32
    FLOAT64 = np.float64
    INT32 = np.int32
    INT64 = np.int64


@dataclass
class ProcessingConfig:
    """Configuration for GPU parallel processing"""
    mode: ProcessingMode = ProcessingMode.AUTO
    chunk_size: Optional[int] = None
    max_memory_usage: float = 75.0  # Percentage
    data_type: DataType = DataType.FLOAT32
    use_streams: bool = True
    stream_count: int = 4
    enable_overlap: bool = True
    fallback_to_cpu: bool = True
    validation_enabled: bool = True


@dataclass
class ProcessingStats:
    """Statistics from processing operation"""
    total_time: float
    gpu_time: float
    cpu_time: float
    transfer_time: float
    data_size: int
    chunk_count: int
    gpu_utilization: float
    memory_used: float
    speedup_factor: float
    processing_mode: ProcessingMode


class GPUParallelProcessor:
    """High-performance GPU parallel processing engine"""
    
    def __init__(self, config: Optional[ProcessingConfig] = None):
        self.logger = logging.getLogger(__name__)
        self.config = config or ProcessingConfig()
        
        # Initialize GPU detector
        self.gpu_detector = GPUHardwareDetector()
        self.gpu_info = self.gpu_detector.detect_gpu_hardware()
        
        # Initialize processing state
        self._streams: List[cp.cuda.Stream] = []
        self._memory_pool = None
        self._initialized = False
        
        # Performance tracking
        self._stats_history: List[ProcessingStats] = []
        
        # Initialize if GPU available
        if self.gpu_info.gpu_available and CUPY_AVAILABLE:
            self._initialize_gpu_processing()
    
    def _initialize_gpu_processing(self) -> None:
        """Initialize GPU processing environment"""
        try:
            # Set memory pool for efficient memory management
            if hasattr(cp.get_default_memory_pool, '__call__'):
                self._memory_pool = cp.get_default_memory_pool()
            
            # Create CUDA streams for concurrent processing
            if self.config.use_streams:
                self._streams = [cp.cuda.Stream() for _ in range(self.config.stream_count)]
                self.logger.info(f"Created {len(self._streams)} CUDA streams")
            
            # Set optimal chunk size if not specified
            if self.config.chunk_size is None:
                self.config.chunk_size = self.gpu_info.recommended_chunk_size
            
            self._initialized = True
            self.logger.info("GPU processing environment initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize GPU processing: {e}")
            self._initialized = False
    
    def process_array(self, 
                     data: Union[np.ndarray, List], 
                     operation: Union[str, Callable],
                     **kwargs) -> np.ndarray:
        """
        Process array data using GPU parallel processing
        
        Args:
            data: Input data array or list
            operation: Operation to perform ('sort', 'sum', 'mean', etc.) or custom function
            **kwargs: Additional arguments for the operation
            
        Returns:
            Processed data as numpy array
        """
        start_time = time.perf_counter()
        
        # Convert input to numpy array
        if isinstance(data, list):
            data = np.array(data, dtype=self.config.data_type.value)
        elif not isinstance(data, np.ndarray):
            data = np.asarray(data, dtype=self.config.data_type.value)
        
        data_size = len(data)
        self.logger.info(f"Processing {data_size:,} elements using {self.config.mode.value} mode")
        
        # Determine processing strategy
        processing_mode = self._determine_processing_mode(data_size)
        
        # Execute processing based on mode
        if processing_mode == ProcessingMode.GPU_ONLY:
            result = self._process_gpu_only(data, operation, **kwargs)
        elif processing_mode == ProcessingMode.CPU_ONLY:
            result = self._process_cpu_only(data, operation, **kwargs)
        elif processing_mode == ProcessingMode.HYBRID:
            result = self._process_hybrid(data, operation, **kwargs)
        else:  # AUTO mode
            result = self._process_auto(data, operation, **kwargs)
        
        # Record performance statistics
        total_time = time.perf_counter() - start_time
        self._record_stats(data_size, total_time, processing_mode)
        
        return result
    
    def _determine_processing_mode(self, data_size: int) -> ProcessingMode:
        """Determine optimal processing mode based on data size and hardware"""
        if self.config.mode != ProcessingMode.AUTO:
            return self.config.mode
        
        if not self.gpu_info.gpu_available or not self._initialized:
            return ProcessingMode.CPU_ONLY
        
        # Use heuristics to determine best mode
        if data_size < 1000:
            return ProcessingMode.CPU_ONLY  # GPU overhead not worth it
        elif data_size < 100000:
            return ProcessingMode.GPU_ONLY
        elif data_size > 10000000:
            return ProcessingMode.HYBRID  # Split large datasets
        else:
            return ProcessingMode.GPU_ONLY
    
    def _process_gpu_only(self, data: np.ndarray, operation: Union[str, Callable], **kwargs) -> np.ndarray:
        """Process data using GPU only"""
        if not self._initialized:
            raise RuntimeError("GPU processing not available")
        
        gpu_start = time.perf_counter()
        
        try:
            # Transfer data to GPU
            gpu_data = cp.asarray(data)
            
            # Process in chunks if data is large
            if len(data) > self.config.chunk_size:
                result = self._process_chunked_gpu(gpu_data, operation, **kwargs)
            else:
                result = self._apply_operation_gpu(gpu_data, operation, **kwargs)
            
            # Transfer result back to CPU
            cpu_result = cp.asnumpy(result)
            
            # Cleanup GPU memory
            del gpu_data, result
            if self._memory_pool:
                self._memory_pool.free_all_blocks()
            
            gpu_time = time.perf_counter() - gpu_start
            self.logger.debug(f"GPU processing completed in {gpu_time:.4f}s")
            
            return cpu_result
            
        except Exception as e:
            self.logger.error(f"GPU processing failed: {e}")
            if self.config.fallback_to_cpu:
                self.logger.info("Falling back to CPU processing")
                return self._process_cpu_only(data, operation, **kwargs)
            else:
                raise
    
    def _process_cpu_only(self, data: np.ndarray, operation: Union[str, Callable], **kwargs) -> np.ndarray:
        """Process data using CPU only"""
        cpu_start = time.perf_counter()
        
        result = self._apply_operation_cpu(data, operation, **kwargs)
        
        cpu_time = time.perf_counter() - cpu_start
        self.logger.debug(f"CPU processing completed in {cpu_time:.4f}s")
        
        return result
    
    def _process_hybrid(self, data: np.ndarray, operation: Union[str, Callable], **kwargs) -> np.ndarray:
        """Process data using both GPU and CPU"""
        if not self._initialized:
            return self._process_cpu_only(data, operation, **kwargs)
        
        hybrid_start = time.perf_counter()
        
        # Split data between GPU and CPU
        gpu_portion = 0.8  # 80% to GPU, 20% to CPU
        split_point = int(len(data) * gpu_portion)
        
        gpu_data = data[:split_point]
        cpu_data = data[split_point:]
        
        # Process both portions concurrently
        with ThreadPoolExecutor(max_workers=2) as executor:
            gpu_future = executor.submit(self._process_gpu_only, gpu_data, operation, **kwargs)
            cpu_future = executor.submit(self._process_cpu_only, cpu_data, operation, **kwargs)
            
            gpu_result = gpu_future.result()
            cpu_result = cpu_future.result()
        
        # Combine results
        if isinstance(operation, str) and operation in ['sort']:
            # For sorting, need to merge sorted arrays
            result = self._merge_sorted_arrays(gpu_result, cpu_result)
        else:
            # For most operations, concatenate results
            result = np.concatenate([gpu_result, cpu_result])
        
        hybrid_time = time.perf_counter() - hybrid_start
        self.logger.debug(f"Hybrid processing completed in {hybrid_time:.4f}s")
        
        return result
    
    def _process_auto(self, data: np.ndarray, operation: Union[str, Callable], **kwargs) -> np.ndarray:
        """Automatically select best processing method"""
        # For AUTO mode, we already determined the best mode in _determine_processing_mode
        # This is just a fallback
        return self._process_gpu_only(data, operation, **kwargs)
    
    def _process_chunked_gpu(self, gpu_data: cp.ndarray, operation: Union[str, Callable], **kwargs) -> cp.ndarray:
        """Process large GPU data in chunks"""
        chunk_size = self.config.chunk_size
        data_size = len(gpu_data)
        num_chunks = (data_size + chunk_size - 1) // chunk_size
        
        self.logger.debug(f"Processing {data_size:,} elements in {num_chunks} chunks of {chunk_size:,}")
        
        if self.config.use_streams and len(self._streams) > 0:
            return self._process_chunked_streams(gpu_data, operation, **kwargs)
        else:
            return self._process_chunked_sequential(gpu_data, operation, **kwargs)
    
    def _process_chunked_streams(self, gpu_data: cp.ndarray, operation: Union[str, Callable], **kwargs) -> cp.ndarray:
        """Process chunks using CUDA streams for overlap"""
        chunk_size = self.config.chunk_size
        data_size = len(gpu_data)
        num_streams = len(self._streams)
        
        # Calculate chunks per stream
        chunks_per_stream = (data_size + chunk_size - 1) // chunk_size
        stream_chunks = (chunks_per_stream + num_streams - 1) // num_streams
        
        results = []
        
        # Process chunks with stream overlap
        for stream_idx, stream in enumerate(self._streams):
            start_chunk = stream_idx * stream_chunks
            end_chunk = min((stream_idx + 1) * stream_chunks, chunks_per_stream)
            
            if start_chunk >= chunks_per_stream:
                break
            
            with stream:
                for chunk_idx in range(start_chunk, end_chunk):
                    start_idx = chunk_idx * chunk_size
                    end_idx = min((chunk_idx + 1) * chunk_size, data_size)
                    
                    chunk_data = gpu_data[start_idx:end_idx]
                    chunk_result = self._apply_operation_gpu(chunk_data, operation, **kwargs)
                    results.append(chunk_result)
        
        # Synchronize all streams
        for stream in self._streams:
            stream.synchronize()
        
        # Combine results
        return self._combine_chunk_results(results, operation)
    
    def _process_chunked_sequential(self, gpu_data: cp.ndarray, operation: Union[str, Callable], **kwargs) -> cp.ndarray:
        """Process chunks sequentially"""
        chunk_size = self.config.chunk_size
        data_size = len(gpu_data)
        results = []
        
        for start_idx in range(0, data_size, chunk_size):
            end_idx = min(start_idx + chunk_size, data_size)
            chunk_data = gpu_data[start_idx:end_idx]
            chunk_result = self._apply_operation_gpu(chunk_data, operation, **kwargs)
            results.append(chunk_result)
        
        return self._combine_chunk_results(results, operation)
    
    def _apply_operation_gpu(self, gpu_data: cp.ndarray, operation: Union[str, Callable], **kwargs) -> cp.ndarray:
        """Apply operation to GPU data"""
        if isinstance(operation, str):
            return self._apply_builtin_operation_gpu(gpu_data, operation, **kwargs)
        elif callable(operation):
            return self._apply_custom_operation_gpu(gpu_data, operation, **kwargs)
        else:
            raise ValueError(f"Unsupported operation type: {type(operation)}")
    
    def _apply_builtin_operation_gpu(self, gpu_data: cp.ndarray, operation: str, **kwargs) -> cp.ndarray:
        """Apply built-in operation using CuPy"""
        operation = operation.lower()
        
        if operation == 'sort':
            return cp.sort(gpu_data, **kwargs)
        elif operation == 'sum':
            return cp.sum(gpu_data, **kwargs)
        elif operation == 'mean':
            return cp.mean(gpu_data, **kwargs)
        elif operation == 'std':
            return cp.std(gpu_data, **kwargs)
        elif operation == 'var':
            return cp.var(gpu_data, **kwargs)
        elif operation == 'min':
            return cp.min(gpu_data, **kwargs)
        elif operation == 'max':
            return cp.max(gpu_data, **kwargs)
        elif operation == 'median':
            return cp.median(gpu_data, **kwargs)
        elif operation == 'cumsum':
            return cp.cumsum(gpu_data, **kwargs)
        elif operation == 'cumprod':
            return cp.cumprod(gpu_data, **kwargs)
        elif operation == 'diff':
            return cp.diff(gpu_data, **kwargs)
        elif operation == 'abs':
            return cp.abs(gpu_data)
        elif operation == 'sqrt':
            return cp.sqrt(gpu_data)
        elif operation == 'square':
            return cp.square(gpu_data)
        elif operation == 'log':
            return cp.log(gpu_data)
        elif operation == 'exp':
            return cp.exp(gpu_data)
        elif operation == 'sin':
            return cp.sin(gpu_data)
        elif operation == 'cos':
            return cp.cos(gpu_data)
        elif operation == 'tan':
            return cp.tan(gpu_data)
        elif operation == 'fft':
            return cp.fft.fft(gpu_data, **kwargs)
        elif operation == 'rolling_mean':
            window = kwargs.get('window', 10)
            return self._rolling_mean_gpu(gpu_data, window)
        elif operation == 'rolling_std':
            window = kwargs.get('window', 10)
            return self._rolling_std_gpu(gpu_data, window)
        else:
            raise ValueError(f"Unsupported built-in operation: {operation}")
    
    def _apply_custom_operation_gpu(self, gpu_data: cp.ndarray, operation: Callable, **kwargs) -> cp.ndarray:
        """Apply custom operation to GPU data"""
        try:
            # Try to apply operation directly
            result = operation(gpu_data, **kwargs)
            
            # Ensure result is a CuPy array
            if not isinstance(result, cp.ndarray):
                result = cp.asarray(result)
            
            return result
            
        except Exception as e:
            self.logger.error(f"Custom GPU operation failed: {e}")
            # Convert to CPU, apply operation, convert back
            cpu_data = cp.asnumpy(gpu_data)
            cpu_result = operation(cpu_data, **kwargs)
            return cp.asarray(cpu_result)
    
    def _apply_operation_cpu(self, cpu_data: np.ndarray, operation: Union[str, Callable], **kwargs) -> np.ndarray:
        """Apply operation to CPU data"""
        if isinstance(operation, str):
            return self._apply_builtin_operation_cpu(cpu_data, operation, **kwargs)
        elif callable(operation):
            return operation(cpu_data, **kwargs)
        else:
            raise ValueError(f"Unsupported operation type: {type(operation)}")
    
    def _apply_builtin_operation_cpu(self, cpu_data: np.ndarray, operation: str, **kwargs) -> np.ndarray:
        """Apply built-in operation using NumPy"""
        operation = operation.lower()
        
        if operation == 'sort':
            return np.sort(cpu_data, **kwargs)
        elif operation == 'sum':
            return np.sum(cpu_data, **kwargs)
        elif operation == 'mean':
            return np.mean(cpu_data, **kwargs)
        elif operation == 'std':
            return np.std(cpu_data, **kwargs)
        elif operation == 'var':
            return np.var(cpu_data, **kwargs)
        elif operation == 'min':
            return np.min(cpu_data, **kwargs)
        elif operation == 'max':
            return np.max(cpu_data, **kwargs)
        elif operation == 'median':
            return np.median(cpu_data, **kwargs)
        elif operation == 'cumsum':
            return np.cumsum(cpu_data, **kwargs)
        elif operation == 'cumprod':
            return np.cumprod(cpu_data, **kwargs)
        elif operation == 'diff':
            return np.diff(cpu_data, **kwargs)
        elif operation == 'abs':
            return np.abs(cpu_data)
        elif operation == 'sqrt':
            return np.sqrt(cpu_data)
        elif operation == 'square':
            return np.square(cpu_data)
        elif operation == 'log':
            return np.log(cpu_data)
        elif operation == 'exp':
            return np.exp(cpu_data)
        elif operation == 'sin':
            return np.sin(cpu_data)
        elif operation == 'cos':
            return np.cos(cpu_data)
        elif operation == 'tan':
            return np.tan(cpu_data)
        elif operation == 'fft':
            return np.fft.fft(cpu_data, **kwargs)
        elif operation == 'rolling_mean':
            window = kwargs.get('window', 10)
            return self._rolling_mean_cpu(cpu_data, window)
        elif operation == 'rolling_std':
            window = kwargs.get('window', 10)
            return self._rolling_std_cpu(cpu_data, window)
        else:
            raise ValueError(f"Unsupported built-in operation: {operation}")
    
    def _rolling_mean_gpu(self, data: cp.ndarray, window: int) -> cp.ndarray:
        """Compute rolling mean on GPU"""
        if len(data) < window:
            return cp.full(len(data), cp.nan)
        
        # Use convolution for efficient rolling mean
        kernel = cp.ones(window) / window
        result = cp.convolve(data, kernel, mode='valid')
        
        # Pad the beginning with NaNs
        padding = cp.full(window - 1, cp.nan)
        return cp.concatenate([padding, result])
    
    def _rolling_std_gpu(self, data: cp.ndarray, window: int) -> cp.ndarray:
        """Compute rolling standard deviation on GPU"""
        if len(data) < window:
            return cp.full(len(data), cp.nan)
        
        # Compute rolling mean first
        rolling_mean = self._rolling_mean_gpu(data, window)
        
        # Compute rolling variance
        squared_diff = (data - rolling_mean) ** 2
        rolling_var = self._rolling_mean_gpu(squared_diff, window)
        
        return cp.sqrt(rolling_var)
    
    def _rolling_mean_cpu(self, data: np.ndarray, window: int) -> np.ndarray:
        """Compute rolling mean on CPU"""
        if len(data) < window:
            return np.full(len(data), np.nan)
        
        # Use pandas-style rolling mean
        result = np.convolve(data, np.ones(window) / window, mode='valid')
        padding = np.full(window - 1, np.nan)
        return np.concatenate([padding, result])
    
    def _rolling_std_cpu(self, data: np.ndarray, window: int) -> np.ndarray:
        """Compute rolling standard deviation on CPU"""
        if len(data) < window:
            return np.full(len(data), np.nan)
        
        rolling_mean = self._rolling_mean_cpu(data, window)
        squared_diff = (data - rolling_mean) ** 2
        rolling_var = self._rolling_mean_cpu(squared_diff, window)
        
        return np.sqrt(rolling_var)
    
    def _combine_chunk_results(self, results: List[cp.ndarray], operation: str) -> cp.ndarray:
        """Combine results from multiple chunks"""
        if not results:
            return cp.array([])
        
        if isinstance(operation, str):
            operation = operation.lower()
            
            if operation in ['sort']:
                # For sorting, need to merge sorted chunks
                combined = cp.concatenate(results)
                return cp.sort(combined)
            elif operation in ['sum', 'mean', 'std', 'var']:
                # For aggregation operations, return single values
                if len(results[0].shape) == 0:  # Scalar results
                    return cp.array(results)
                else:
                    return cp.concatenate(results)
            else:
                # For element-wise operations, concatenate
                return cp.concatenate(results)
        else:
            # For custom operations, concatenate by default
            return cp.concatenate(results)
    
    def _merge_sorted_arrays(self, arr1: np.ndarray, arr2: np.ndarray) -> np.ndarray:
        """Merge two sorted arrays"""
        result = np.empty(len(arr1) + len(arr2), dtype=arr1.dtype)
        i = j = k = 0
        
        while i < len(arr1) and j < len(arr2):
            if arr1[i] <= arr2[j]:
                result[k] = arr1[i]
                i += 1
            else:
                result[k] = arr2[j]
                j += 1
            k += 1
        
        while i < len(arr1):
            result[k] = arr1[i]
            i += 1
            k += 1
        
        while j < len(arr2):
            result[k] = arr2[j]
            j += 1
            k += 1
        
        return result
    
    def _record_stats(self, data_size: int, total_time: float, mode: ProcessingMode) -> None:
        """Record processing statistics"""
        # Calculate speedup factor (approximate)
        speedup = 1.0
        if mode == ProcessingMode.GPU_ONLY and self._stats_history:
            # Compare with last CPU processing time
            cpu_stats = [s for s in self._stats_history if s.processing_mode == ProcessingMode.CPU_ONLY]
            if cpu_stats:
                avg_cpu_time = sum(s.total_time for s in cpu_stats[-5:]) / len(cpu_stats[-5:])
                speedup = avg_cpu_time / total_time if total_time > 0 else 1.0
        
        stats = ProcessingStats(
            total_time=total_time,
            gpu_time=total_time if mode == ProcessingMode.GPU_ONLY else 0.0,
            cpu_time=total_time if mode == ProcessingMode.CPU_ONLY else 0.0,
            transfer_time=0.0,  # TODO: Measure actual transfer time
            data_size=data_size,
            chunk_count=max(1, (data_size + self.config.chunk_size - 1) // self.config.chunk_size),
            gpu_utilization=0.0,  # TODO: Measure actual GPU utilization
            memory_used=0.0,  # TODO: Measure actual memory usage
            speedup_factor=speedup,
            processing_mode=mode
        )
        
        self._stats_history.append(stats)
        
        # Keep only last 100 stats
        if len(self._stats_history) > 100:
            self._stats_history = self._stats_history[-100:]
    
    def get_performance_stats(self) -> List[ProcessingStats]:
        """Get performance statistics history"""
        return self._stats_history.copy()
    
    def get_latest_stats(self) -> Optional[ProcessingStats]:
        """Get latest performance statistics"""
        return self._stats_history[-1] if self._stats_history else None
    
    def clear_stats(self) -> None:
        """Clear performance statistics history"""
        self._stats_history.clear()
    
    def get_gpu_info(self) -> Dict[str, Any]:
        """Get GPU hardware information"""
        return {
            'gpu_available': self.gpu_info.gpu_available,
            'gpu_count': self.gpu_info.gpu_count,
            'gpu_names': self.gpu_info.gpu_names,
            'total_memory': self.gpu_info.total_memory,
            'capability_level': self.gpu_info.capability_level.value,
            'recommended_chunk_size': self.gpu_info.recommended_chunk_size,
            'max_safe_memory_usage': self.gpu_info.max_safe_memory_usage,
            'initialized': self._initialized
        }
    
    def benchmark_operation(self, operation: Union[str, Callable], data_sizes: List[int] = None) -> Dict[str, Any]:
        """Benchmark an operation across different data sizes"""
        if data_sizes is None:
            data_sizes = [1000, 10000, 100000, 1000000]
        
        results = {}
        
        for size in data_sizes:
            # Generate test data
            test_data = np.random.random(size).astype(self.config.data_type.value)
            
            # Benchmark GPU processing
            gpu_time = None
            if self.gpu_info.gpu_available:
                start_time = time.perf_counter()
                try:
                    gpu_result = self.process_array(test_data, operation)
                    gpu_time = time.perf_counter() - start_time
                except Exception as e:
                    self.logger.error(f"GPU benchmark failed for size {size}: {e}")
            
            # Benchmark CPU processing
            original_mode = self.config.mode
            self.config.mode = ProcessingMode.CPU_ONLY
            
            start_time = time.perf_counter()
            cpu_result = self.process_array(test_data, operation)
            cpu_time = time.perf_counter() - start_time
            
            self.config.mode = original_mode
            
            # Calculate speedup
            speedup = cpu_time / gpu_time if gpu_time and gpu_time > 0 else 1.0
            
            results[size] = {
                'cpu_time': cpu_time,
                'gpu_time': gpu_time,
                'speedup': speedup,
                'data_size': size
            }
            
            self.logger.info(f"Size {size:,}: CPU {cpu_time:.4f}s, GPU {gpu_time:.4f}s, "
                           f"Speedup: {speedup:.2f}x" if gpu_time else f"Size {size:,}: CPU {cpu_time:.4f}s")
        
        return results
    
    def __del__(self):
        """Cleanup GPU resources"""
        try:
            if hasattr(self, '_streams'):
                for stream in self._streams:
                    if hasattr(stream, '__del__'):
                        del stream
            
            if hasattr(self, '_memory_pool') and self._memory_pool:
                self._memory_pool.free_all_blocks()
                
        except Exception:
            pass  # Ignore cleanup errors


# Convenience functions for common operations
def gpu_sort(data: Union[np.ndarray, List], **kwargs) -> np.ndarray:
    """Sort data using GPU acceleration"""
    processor = GPUParallelProcessor()
    return processor.process_array(data, 'sort', **kwargs)


def gpu_sum(data: Union[np.ndarray, List], **kwargs) -> np.ndarray:
    """Sum data using GPU acceleration"""
    processor = GPUParallelProcessor()
    return processor.process_array(data, 'sum', **kwargs)


def gpu_mean(data: Union[np.ndarray, List], **kwargs) -> np.ndarray:
    """Calculate mean using GPU acceleration"""
    processor = GPUParallelProcessor()
    return processor.process_array(data, 'mean', **kwargs)


def gpu_std(data: Union[np.ndarray, List], **kwargs) -> np.ndarray:
    """Calculate standard deviation using GPU acceleration"""
    processor = GPUParallelProcessor()
    return processor.process_array(data, 'std', **kwargs)


def gpu_rolling_mean(data: Union[np.ndarray, List], window: int = 10, **kwargs) -> np.ndarray:
    """Calculate rolling mean using GPU acceleration"""
    processor = GPUParallelProcessor()
    return processor.process_array(data, 'rolling_mean', window=window, **kwargs)


if __name__ == "__main__":
    # Example usage and benchmarking
    logging.basicConfig(level=logging.INFO)
    
    # Create processor
    config = ProcessingConfig(
        mode=ProcessingMode.AUTO,
        chunk_size=100000,
        max_memory_usage=75.0,
        use_streams=True,
        stream_count=4
    )
    
    processor = GPUParallelProcessor(config)
    
    # Print GPU info
    print("GPU Information:")
    gpu_info = processor.get_gpu_info()
    for key, value in gpu_info.items():
        print(f"  {key}: {value}")
    
    # Generate test data
    test_size = 1000000
    test_data = np.random.random(test_size).astype(np.float32)
    
    print(f"\nTesting with {test_size:,} data points:")
    
    # Test different operations
    operations = ['sort', 'sum', 'mean', 'std', 'rolling_mean']
    
    for operation in operations:
        print(f"\nBenchmarking {operation}:")
        try:
            if operation == 'rolling_mean':
                results = processor.benchmark_operation(operation, [10000, 100000, 500000])
            else:
                results = processor.benchmark_operation(operation, [10000, 100000, 500000])
            
            for size, stats in results.items():
                speedup = stats['speedup']
                print(f"  Size {size:,}: {speedup:.2f}x speedup")
                
        except Exception as e:
            print(f"  Error benchmarking {operation}: {e}")
    
    # Print performance statistics
    stats = processor.get_performance_stats()
    if stats:
        print(f"\nProcessed {len(stats)} operations")
        avg_speedup = sum(s.speedup_factor for s in stats) / len(stats)
        print(f"Average speedup: {avg_speedup:.2f}x")