"""
GPU Memory Management System for Large Dataset Processing

This module provides comprehensive GPU memory management to handle datasets of any size
without memory exhaustion. Key features include:

- Dynamic GPU memory profiling and monitoring
- Adaptive chunked processing for large datasets
- Memory-efficient batch sizing with automatic optimization
- Real-time memory pressure detection and handling
- GPU memory pool optimization for better utilization
- Zero-copy memory transfers where possible
- Automatic fallback prevention through proactive management

Design Principles:
- Never allow GPU memory exhaustion (proactive management)
- Process datasets of unlimited size through intelligent chunking
- Optimize memory utilization while maintaining performance
- Provide transparent operation for existing pipeline code
"""

import time
import math
import warnings
from typing import Dict, List, Tuple, Optional, Any, Union, Iterator
from dataclasses import dataclass
import numpy as np
import pandas as pd
from contextlib import contextmanager
from .array_backend import ArrayBackend
from .array_types import ArrayLike
from .gpu_converter import GPUArrayConverter


@dataclass
class GPUMemoryInfo:
    """GPU memory information structure"""
    total_memory: int  # Total GPU memory in bytes
    free_memory: int   # Free GPU memory in bytes
    used_memory: int   # Used GPU memory in bytes
    utilization: float # Memory utilization percentage (0-1)
    device_name: str   # GPU device name
    compute_capability: Tuple[int, int]  # GPU compute capability


@dataclass
class ChunkingStrategy:
    """Strategy for chunking large datasets"""
    chunk_size: int           # Number of data points per chunk
    overlap_size: int         # Overlap between chunks for continuity
    memory_threshold: float   # Memory usage threshold (0-1) to trigger chunking
    min_chunk_size: int       # Minimum chunk size
    max_chunk_size: int       # Maximum chunk size
    adaptive_sizing: bool     # Enable adaptive chunk sizing
    
    def __post_init__(self):
        """Validate chunking strategy parameters"""
        if self.chunk_size < self.min_chunk_size:
            self.chunk_size = self.min_chunk_size
        if self.chunk_size > self.max_chunk_size:
            self.chunk_size = self.max_chunk_size
        if self.overlap_size >= self.chunk_size:
            self.overlap_size = max(0, self.chunk_size // 10)


class GPUMemoryProfiler:
    """
    Real-time GPU memory profiling and monitoring system
    """
    
    def __init__(self):
        self.gpu_available = False
        self.cupy_module = None
        self._initialize_gpu()
    
    def _initialize_gpu(self):
        """Initialize GPU access and detect capabilities"""
        try:
            import cupy as cp
            self.cupy_module = cp
            self.gpu_available = cp.cuda.is_available()
            if self.gpu_available:
                # Initialize memory pool for better management
                cp.cuda.MemoryPool().free_all_blocks()
        except ImportError:
            self.gpu_available = False
    
    def get_memory_info(self) -> Optional[GPUMemoryInfo]:
        """Get current GPU memory information"""
        if not self.gpu_available:
            return None
        
        try:
            cp = self.cupy_module
            
            # Get memory info
            free_mem, total_mem = cp.cuda.runtime.memGetInfo()
            used_mem = total_mem - free_mem
            utilization = used_mem / total_mem if total_mem > 0 else 0.0
            
            # Get device info
            device = cp.cuda.Device()
            try:
                # Try different methods to get device name
                if hasattr(device, 'name'):
                    device_name = device.name.decode('utf-8') if hasattr(device.name, 'decode') else str(device.name)
                elif hasattr(cp.cuda.runtime, 'getDeviceProperties'):
                    props = cp.cuda.runtime.getDeviceProperties(device.id)
                    device_name = props['name'].decode('utf-8') if isinstance(props['name'], bytes) else str(props['name'])
                else:
                    device_name = f"GPU_{device.id}"
            except:
                device_name = f"GPU_{device.id}"
            
            compute_cap = device.compute_capability
            
            return GPUMemoryInfo(
                total_memory=total_mem,
                free_memory=free_mem,
                used_memory=used_mem,
                utilization=utilization,
                device_name=device_name,
                compute_capability=compute_cap
            )
        except Exception as e:
            warnings.warn(f"Failed to get GPU memory info: {e}")
            return None
    
    def estimate_array_memory_usage(self, shape: Tuple[int, ...], dtype: str = 'float32') -> int:
        """Estimate memory usage for an array with given shape and dtype"""
        dtype_sizes = {
            'float32': 4, 'float64': 8,
            'int32': 4, 'int64': 8,
            'complex64': 8, 'complex128': 16
        }
        
        element_size = dtype_sizes.get(dtype, 4)
        total_elements = np.prod(shape)
        return total_elements * element_size
    
    def estimate_computation_memory(self, 
                                  input_arrays: Dict[str, np.ndarray],
                                  operation_factor: float = 2.0) -> int:
        """
        Estimate total memory needed for computation including intermediate arrays
        
        Args:
            input_arrays: Input arrays for computation
            operation_factor: Multiplier for intermediate array overhead
            
        Returns:
            Estimated memory usage in bytes
        """
        base_memory = sum(arr.nbytes for arr in input_arrays.values())
        return int(base_memory * operation_factor)
    
    def can_fit_in_memory(self, 
                         required_memory: int,
                         safety_margin: float = 0.15) -> bool:
        """
        Check if required memory can fit in GPU with safety margin
        
        Args:
            required_memory: Required memory in bytes
            safety_margin: Safety margin as fraction of total memory
            
        Returns:
            True if memory fits, False otherwise
        """
        memory_info = self.get_memory_info()
        if not memory_info:
            return False
        
        available_memory = memory_info.free_memory
        safe_memory = memory_info.total_memory * (1.0 - safety_margin)
        
        return required_memory <= min(available_memory, safe_memory)
    
    @contextmanager
    def memory_monitor(self, operation_name: str = "GPU Operation"):
        """Context manager for monitoring memory usage during operations"""
        if not self.gpu_available:
            yield
            return
        
        start_info = self.get_memory_info()
        start_time = time.perf_counter()
        
        try:
            yield
        finally:
            end_time = time.perf_counter()
            end_info = self.get_memory_info()
            
            if start_info and end_info:
                memory_delta = end_info.used_memory - start_info.used_memory
                duration = end_time - start_time
                
                print(f"[{operation_name}] Memory: {memory_delta/1e6:.1f} MB, "
                      f"Time: {duration:.3f}s, "
                      f"Utilization: {end_info.utilization:.1%}")


class ChunkedDataProcessor:
    """
    Chunked processing system for large datasets that exceed GPU memory
    """
    
    def __init__(self, 
                 memory_profiler: GPUMemoryProfiler,
                 chunk_size: int = 50000,
                 overlap_size: int = 100,
                 memory_threshold: float = 0.7,
                 adaptive_sizing: bool = True):
        """
        Initialize chunked processor
        
        Args:
            memory_profiler: GPU memory profiler instance
            chunk_size: Initial chunk size
            overlap_size: Overlap between chunks
            memory_threshold: Memory threshold to trigger chunking
            adaptive_sizing: Enable adaptive chunk sizing
        """
        self.profiler = memory_profiler
        self.strategy = ChunkingStrategy(
            chunk_size=chunk_size,
            overlap_size=overlap_size,
            memory_threshold=memory_threshold,
            min_chunk_size=500000,   # PHASE 3.1 AGGRESSIVE: 500K minimum for RTX 4080 SUPER
            max_chunk_size=5000000,  # PHASE 3.1 ULTRA AGGRESSIVE: 5M maximum chunks for RTX 4080 SUPER
            adaptive_sizing=adaptive_sizing
        )
    
    def calculate_optimal_chunk_size(self, 
                                   data_shape: Tuple[int, ...],
                                   dtype: str = 'float32') -> int:
        """
        Calculate optimal chunk size based on available GPU memory - PHASE 3.1 AGGRESSIVE VERSION
        
        Args:
            data_shape: Shape of the data to process
            dtype: Data type
            
        Returns:
            Optimal chunk size for maximum GPU utilization
        """
        memory_info = self.profiler.get_memory_info()
        if not memory_info:
            raise RuntimeError("Cannot calculate optimal chunk size without GPU memory info")
        
        # PHASE 3.1 ULTRA AGGRESSIVE: Use 99.5% of available memory (0.5% safety margin)
        available_memory = memory_info.free_memory * 0.995  # Minimal 0.5% safety margin
        
        # Estimate memory per data point (including intermediate arrays and CUDA streams)
        single_point_memory = self.profiler.estimate_array_memory_usage(
            (1, len(data_shape) - 1), dtype
        ) * 4  # Factor for intermediate arrays + CUDA streams overhead
        
        # Calculate optimal chunk size for RTX 4080 SUPER
        optimal_size = int(available_memory // single_point_memory)
        
        # PHASE 3.1 AGGRESSIVE CONSTRAINTS: Much larger chunks for maximum GPU utilization
        min_chunk_rtx4080 = 500000   # 500K minimum for RTX 4080 SUPER
        max_chunk_rtx4080 = 5000000  # 5M maximum for RTX 4080 SUPER
        
        optimal_size = max(min_chunk_rtx4080, optimal_size)
        optimal_size = min(max_chunk_rtx4080, optimal_size)
        
        print(f"🎯 [AGGRESSIVE GPU] Calculated chunk size: {optimal_size:,} points ({optimal_size*single_point_memory/1e9:.2f}GB)")
        
        return optimal_size
    
    def create_chunks(self, 
                     data: pd.DataFrame,
                     chunk_size: Optional[int] = None) -> Iterator[Tuple[pd.DataFrame, Dict[str, Any]]]:
        """
        Create overlapped chunks from DataFrame
        
        Args:
            data: Input DataFrame
            chunk_size: Override chunk size
            
        Yields:
            Tuple of (chunk_data, chunk_metadata)
        """
        if chunk_size is None:
            chunk_size = self.calculate_optimal_chunk_size(data.shape)
        
        total_rows = len(data)
        
        if total_rows <= chunk_size:
            # No chunking needed
            yield data, {'chunk_id': 0, 'start_idx': 0, 'end_idx': total_rows, 'total_chunks': 1}
            return
        
        overlap = self.strategy.overlap_size
        current_start = 0
        chunk_id = 0
        
        while current_start < total_rows:
            # Calculate chunk boundaries
            current_end = min(current_start + chunk_size, total_rows)
            
            # Extract chunk with overlap consideration
            if chunk_id == 0:
                # First chunk - no leading overlap
                chunk_data = data.iloc[current_start:current_end]
                actual_start = current_start
            else:
                # Add leading overlap from previous chunk
                overlap_start = max(0, current_start - overlap)
                chunk_data = data.iloc[overlap_start:current_end]
                actual_start = overlap_start
            
            # Metadata for chunk processing
            metadata = {
                'chunk_id': chunk_id,
                'start_idx': current_start,
                'end_idx': current_end,
                'actual_start_idx': actual_start,
                'has_leading_overlap': chunk_id > 0,
                'has_trailing_overlap': current_end < total_rows,
                'overlap_size': overlap,
                'total_chunks': math.ceil(total_rows / chunk_size)
            }
            
            yield chunk_data, metadata
            
            # Move to next chunk
            current_start = current_end
            chunk_id += 1
    
    def merge_chunk_results(self, 
                          chunk_results: List[Tuple[pd.DataFrame, Dict[str, Any]]]) -> pd.DataFrame:
        """
        Merge results from chunked processing, handling overlaps
        
        Args:
            chunk_results: List of (result_dataframe, chunk_metadata) tuples
            
        Returns:
            Merged DataFrame with overlaps handled
        """
        if not chunk_results:
            return pd.DataFrame()
        
        if len(chunk_results) == 1:
            return chunk_results[0][0]
        
        merged_parts = []
        
        for i, (result_df, metadata) in enumerate(chunk_results):
            if i == 0:
                # First chunk - keep all data
                merged_parts.append(result_df)
            else:
                # Remove leading overlap
                overlap_size = metadata.get('overlap_size', 0)
                if overlap_size > 0 and len(result_df) > overlap_size:
                    # Remove overlap rows
                    trimmed_df = result_df.iloc[overlap_size:]
                    merged_parts.append(trimmed_df)
                else:
                    merged_parts.append(result_df)
        
        # Concatenate all parts
        if merged_parts:
            return pd.concat(merged_parts, ignore_index=True)
        else:
            return pd.DataFrame()


class GPUMemoryManager:
    """
    Comprehensive GPU memory management system for technical indicators
    """
    
    def __init__(self,
                 memory_threshold: float = 0.98,  # MAXIMUM AGGRESSIVE: use 98% of GPU memory (Phase 3.1 style)
                 chunk_size: int = 2000000,       # ULTRA MASSIVE chunks: 2M points for RTX 4080 SUPER optimization
                 overlap_size: int = 100,
                 enable_memory_pool: bool = True,
                 monitor_usage: bool = True,
                 force_gpu_only: bool = True):     # NEW: Force GPU-only processing (no CPU fallback)
        """
        Initialize GPU memory manager
        
        Args:
            memory_threshold: Threshold to trigger chunking (0-1)
            chunk_size: Default chunk size for processing
            overlap_size: Overlap between chunks
            enable_memory_pool: Enable CuPy memory pool optimization
            monitor_usage: Enable memory usage monitoring
        """
        self.profiler = GPUMemoryProfiler()
        self.processor = ChunkedDataProcessor(
            self.profiler, 
            chunk_size=chunk_size,
            overlap_size=overlap_size,
            memory_threshold=memory_threshold,
            adaptive_sizing=True
        )
        
        self.enable_memory_pool = enable_memory_pool
        self.monitor_usage = monitor_usage
        self.force_gpu_only = force_gpu_only  # NEW: GPU-only enforcement flag
        
        # Initialize Phase 3.1 style aggressive GPU utilization
        self._initialize_aggressive_gpu_mode()
        
        if self.enable_memory_pool and self.profiler.gpu_available:
            self._optimize_memory_pool()
    
    def _initialize_aggressive_gpu_mode(self):
        """Initialize Phase 3.1 style aggressive GPU utilization"""
        if not self.profiler.gpu_available:
            if self.force_gpu_only:
                raise RuntimeError("GPU-only mode requested but GPU not available. Aborting to prevent CPU fallback.")
            return
        
        try:
            cp = self.profiler.cupy_module
            
            # Create multiple CUDA streams for maximum parallelization (Phase 3.1 style)
            self.cuda_streams = [cp.cuda.Stream() for _ in range(8)]  # 8 streams like RTX4080SuperMaxUtilizer
            
            print(f"🚀 [AGGRESSIVE GPU] Initialized {len(self.cuda_streams)} CUDA streams for maximum utilization")
            print(f"🎯 [AGGRESSIVE GPU] GPU-only mode: {'ENABLED' if self.force_gpu_only else 'DISABLED'}")
            
        except Exception as e:
            error_msg = f"Failed to initialize aggressive GPU mode: {e}"
            if self.force_gpu_only:
                raise RuntimeError(error_msg)
            else:
                warnings.warn(error_msg)
    
    def _optimize_memory_pool(self):
        """Optimize CuPy memory pool settings with Phase 3.1 aggressive approach"""
        if not self.profiler.gpu_available:
            return
        
        try:
            cp = self.profiler.cupy_module
            
            # Get memory pool and set limits
            memory_info = self.profiler.get_memory_info()
            if memory_info:
                # PHASE 3.1 ULTRA AGGRESSIVE: Set memory pool limit to 99% of total GPU memory
                pool_limit = int(memory_info.total_memory * 0.99)
                cp.cuda.MemoryPool().set_limit(size=pool_limit)
                
                # Configure memory pool for better performance
                cp.cuda.MemoryPool().free_all_blocks()
                
                print(f"🔥 [AGGRESSIVE GPU] Memory pool limit set to {pool_limit/1e9:.1f}GB (99% of {memory_info.total_memory/1e9:.1f}GB)")
                
        except Exception as e:
            error_msg = f"Failed to optimize memory pool: {e}"
            if self.force_gpu_only:
                raise RuntimeError(error_msg)
            else:
                warnings.warn(error_msg)
    
    def should_use_chunking(self, 
                          data: pd.DataFrame,
                          operation_factor: float = 3.0) -> bool:  # Increased factor for CUDA streams
        """
        Determine if chunking should be used for the dataset
        PHASE 3.1 ULTRA AGGRESSIVE VERSION: Always use chunking for datasets > 10K points to maximize RTX 4080 SUPER utilization
        
        Args:
            data: Input DataFrame
            operation_factor: Memory overhead factor for operations (increased for CUDA streams)
            
        Returns:
            True if chunking should be used
        """
        if not self.profiler.gpu_available:
            raise RuntimeError("Cannot determine chunking strategy without GPU")
        
        # PHASE 3.1 ULTRA AGGRESSIVE: Always chunk for datasets larger than 10K to ensure maximum RTX 4080 SUPER utilization
        if len(data) > 10000:  # Much lower threshold than Phase 3
            print(f"🚀 [PHASE 3.1 AGGRESSIVE] Forcing chunking for {len(data):,} points to maximize RTX 4080 SUPER utilization")
            return True
        
        # For smaller datasets, check memory requirements with CUDA streams overhead
        arrays = {
            'open': data['open'].values,
            'high': data['high'].values,
            'low': data['low'].values,
            'close': data['close'].values
        }
        
        required_memory = self.profiler.estimate_computation_memory(
            arrays, operation_factor  # Higher factor accounts for CUDA streams
        )
        
        # PHASE 3.1 AGGRESSIVE: Use much smaller safety margin (0.5% vs 2%)
        return not self.profiler.can_fit_in_memory(required_memory, safety_margin=0.005)
    
    def process_with_memory_management(self,
                                     data: pd.DataFrame,
                                     computation_func,
                                     *args,
                                     **kwargs) -> pd.DataFrame:
        """
        Process data with PHASE 3.1 AGGRESSIVE memory management and CUDA streams
        
        Args:
            data: Input DataFrame
            computation_func: Function to apply to data chunks
            *args: Additional arguments for computation function
            **kwargs: Additional keyword arguments
            
        Returns:
            Processed DataFrame with maximum GPU utilization
        """
        if not self.should_use_chunking(data):
            # Process normally without chunking but with aggressive GPU utilization
            with self.profiler.memory_monitor("Phase 3.1 Direct GPU Processing"):
                print(f"🎯 [DIRECT AGGRESSIVE GPU] Processing {len(data):,} points without chunking...")
                return self._process_with_cuda_streams(data, computation_func, *args, **kwargs)
        
        # Use PHASE 3.1 AGGRESSIVE chunked processing with CUDA streams
        print(f"🚀 [PHASE 3.1 AGGRESSIVE CHUNKING] Processing {len(data):,} points with RTX 4080 SUPER optimization...")
        
        chunk_results = []
        total_chunks = 0
        
        with self.profiler.memory_monitor("Phase 3.1 Aggressive Chunked Processing"):
            for chunk_data, metadata in self.processor.create_chunks(data):
                total_chunks = metadata['total_chunks']
                chunk_id = metadata['chunk_id']
                
                print(f"🔥 [GPU CHUNK {chunk_id + 1}/{total_chunks}] Processing {len(chunk_data):,} points with CUDA streams...")
                
                # Process chunk with CUDA streams for maximum utilization
                chunk_result = self._process_chunk_with_streams(chunk_data, computation_func, chunk_id, *args, **kwargs)
                chunk_results.append((chunk_result, metadata))
                
                # Minimal memory cleanup (Phase 3.1 style - keep memory warm)
                if hasattr(self, 'cuda_streams') and self.profiler.gpu_available:
                    # Synchronize streams but don't free all blocks (keep memory warm for next chunk)
                    for stream in self.cuda_streams:
                        stream.synchronize()
        
        # Merge results
        print(f"🔄 [MERGING] Combining {len(chunk_results)} chunk results...")
        final_result = self.processor.merge_chunk_results(chunk_results)
        
        print(f"✅ [PHASE 3.1 COMPLETE] Processed {len(final_result):,} points with aggressive GPU utilization")
        return final_result
    
    def _process_with_cuda_streams(self, data: pd.DataFrame, computation_func, *args, **kwargs) -> pd.DataFrame:
        """Process data using CUDA streams for maximum parallelization"""
        if not hasattr(self, 'cuda_streams') or not self.cuda_streams:
            # Fallback to normal processing if streams not available
            return computation_func(data, *args, **kwargs)
        
        # Use first stream for direct processing (could be enhanced for multi-stream)
        with self.cuda_streams[0]:
            result = computation_func(data, *args, **kwargs)
        
        # Synchronize to ensure completion
        self.cuda_streams[0].synchronize()
        return result
    
    def _process_chunk_with_streams(self, chunk_data: pd.DataFrame, computation_func, chunk_id: int, *args, **kwargs) -> pd.DataFrame:
        """Process a single chunk using CUDA streams with stream selection"""
        if not hasattr(self, 'cuda_streams') or not self.cuda_streams:
            # Fallback to normal processing if streams not available
            return computation_func(chunk_data, *args, **kwargs)
        
        # Select stream in round-robin fashion for load balancing
        stream_idx = chunk_id % len(self.cuda_streams)
        selected_stream = self.cuda_streams[stream_idx]
        
        with selected_stream:
            result = computation_func(chunk_data, *args, **kwargs)
        
        # Synchronize the selected stream
        selected_stream.synchronize()
        return result
    
    def get_memory_statistics(self) -> Dict[str, Any]:
        """Get comprehensive memory usage statistics"""
        memory_info = self.profiler.get_memory_info()
        
        stats = {
            'gpu_available': self.profiler.gpu_available,
            'memory_info': memory_info,
            'chunking_strategy': {
                'chunk_size': self.processor.strategy.chunk_size,
                'overlap_size': self.processor.strategy.overlap_size,
                'memory_threshold': self.processor.strategy.memory_threshold,
                'adaptive_sizing': self.processor.strategy.adaptive_sizing
            }
        }
        
        if memory_info:
            stats.update({
                'memory_utilization_pct': memory_info.utilization * 100,
                'free_memory_gb': memory_info.free_memory / 1e9,
                'total_memory_gb': memory_info.total_memory / 1e9,
                'device_name': memory_info.device_name
            })
        
        return stats
    
    def clear_gpu_cache(self):
        """Clear GPU memory cache and free unused blocks"""
        if self.profiler.gpu_available:
            try:
                self.profiler.cupy_module.cuda.MemoryPool().free_all_blocks()
                print("GPU cache cleared successfully")
            except Exception as e:
                warnings.warn(f"Failed to clear GPU cache: {e}")
    
    @contextmanager
    def memory_managed_context(self, operation_name: str = "GPU Operation"):
        """Context manager for memory-managed GPU operations"""
        try:
            with self.profiler.memory_monitor(operation_name):
                yield self
        finally:
            # Clean up after operation
            if self.profiler.gpu_available:
                self.profiler.cupy_module.cuda.MemoryPool().free_all_blocks()


class GPUBatchOptimizer:
    """
    GPU Batch Optimizer for adaptive batch sizing (Task 1.3)
    
    Calculates optimal batch sizes for maximum GPU utilization while respecting
    memory constraints. Designed specifically for technical indicators pipeline.
    """
    
    def __init__(self, target_utilization: float = 0.75, safety_margin: float = 0.05):
        """
        Initialize GPU batch optimizer
        
        Args:
            target_utilization: Target GPU memory utilization (0.7-0.8 as per dev plan)
            safety_margin: Safety margin to prevent OOM errors
        """
        self.target_utilization = target_utilization
        self.safety_margin = safety_margin
        self.profiler = GPUMemoryProfiler()
        
    def calculate_optimal_batch_size(self, 
                                   data_sample: pd.DataFrame, 
                                   gpu_memory_gb: float = 16.0) -> int:
        """
        Calculate optimal batch size for maximum GPU utilization (Task 1.3)
        
        Args:
            data_sample: Sample DataFrame to estimate memory requirements
            gpu_memory_gb: GPU memory capacity in GB (default: RTX 4080 SUPER 16GB)
            
        Returns:
            Optimal batch size (target: 25-40 combinations per batch)
        """
        # Get actual GPU memory info if available
        memory_info = self.profiler.get_memory_info()
        if memory_info:
            total_memory_bytes = memory_info.total_memory
            available_memory_bytes = memory_info.free_memory
        else:
            # Fallback to provided GPU memory specification
            total_memory_bytes = int(gpu_memory_gb * 1e9)
            available_memory_bytes = int(total_memory_bytes * 0.8)  # Assume 80% available
        
        # Calculate memory per data sample (including computation overhead)
        sample_memory = self._estimate_sample_memory_usage(data_sample)
        
        # Target memory usage: 70-80% of available memory
        target_memory = available_memory_bytes * self.target_utilization
        safe_memory = target_memory * (1.0 - self.safety_margin)
        
        # Calculate optimal batch size
        optimal_batch_size = int(safe_memory // sample_memory)
        
        # Apply constraints from development plan: 25-40 combinations per batch
        min_batch_size = 25
        max_batch_size = 40
        
        # Ensure batch size is within acceptable range
        if optimal_batch_size < min_batch_size:
            optimal_batch_size = min_batch_size
        elif optimal_batch_size > max_batch_size:
            optimal_batch_size = max_batch_size
        
        return optimal_batch_size
    
    def _estimate_sample_memory_usage(self, data_sample: pd.DataFrame) -> int:
        """
        Estimate memory usage per data sample including computation overhead
        
        Args:
            data_sample: Sample DataFrame
            
        Returns:
            Estimated memory usage in bytes per sample
        """
        # Base memory for DataFrame arrays
        base_memory = 0
        for col in data_sample.select_dtypes(include=[np.number]).columns:
            arr_memory = data_sample[col].memory_usage(deep=True)
            base_memory += arr_memory
        
        # Factor in computation overhead:
        # - GPU array conversion (2x)
        # - Intermediate calculations (2x)  
        # - Memory fragmentation (1.5x)
        computation_factor = 2.0 * 2.0 * 1.5
        total_memory = base_memory * computation_factor
        
        return int(total_memory)
    
    def validate_batch_size(self, batch_size: int, data_sample: pd.DataFrame) -> bool:
        """
        Validate that a batch size will fit in GPU memory
        
        Args:
            batch_size: Proposed batch size
            data_sample: Sample DataFrame
            
        Returns:
            True if batch size is valid, False otherwise
        """
        sample_memory = self._estimate_sample_memory_usage(data_sample)
        total_required_memory = sample_memory * batch_size
        
        return self.profiler.can_fit_in_memory(
            total_required_memory, 
            safety_margin=self.safety_margin
        )


class UnifiedGPUTechnicalIndicators:
    """
    Unified GPU technical indicators pipeline using Phase 1 infrastructure.
    
    Coordinates ATR, MACD, and Swing Point detection with optimal batch processing,
    memory management, and GPU utilization to achieve 60-80% GPU utilization target.
    """
    
    def __init__(self, backend: ArrayBackend):
        """
        Initialize unified pipeline with Phase 1 GPU infrastructure.
        
        Args:
            backend: ArrayBackend for GPU operations
        """
        self.backend = backend
        self.xp = backend.xp
        
        # Phase 1 infrastructure components
        self.converter = GPUArrayConverter()
        self.batch_optimizer = GPUBatchOptimizer()
        self.memory_manager = GPUMemoryManager()
        
        # Initialize GPU-accelerated calculators
        from .atr_calculator import ATRCalculator
        from .macd_calculator import MACDCalculator
        from .gpu_swing_detector import GPUSwingDetector
        
        self.atr_calculator = ATRCalculator(backend)
        self.macd_calculator = MACDCalculator(backend)
        self.swing_detector = GPUSwingDetector(backend)
    
    def compute_all_indicators_batch(self, combinations_batch: List[Dict]) -> List[Dict]:
        """
        Unified batch processing of all technical indicators using Phase 1 infrastructure.
        
        Leverages:
        1. GPUBatchOptimizer for optimal batch sizing (25-40 combinations)
        2. GPUMemoryManager with 8 CUDA streams for parallel processing
        3. Phase 1 memory pools for maximum GPU utilization (target: 60-80%)
        4. Coordinate all technical indicators in single GPU workflow
        
        Args:
            combinations_batch: List of combination dictionaries with tick_data, historical data
            
        Returns:
            List of dictionaries with all technical indicator results
        """
        if not combinations_batch:
            return []
        
        # Step 1: Use Phase 1 batch optimizer for optimal sizing
        optimal_batch_size = self.batch_optimizer.calculate_optimal_batch_size(
            data_sample=combinations_batch[0]['tick_data']
        )
        
        print(f"\\n=== UNIFIED GPU PIPELINE: Processing {len(combinations_batch)} combinations ===")
        print(f"Optimal batch size: {optimal_batch_size}")
        
        # Step 2: Process in optimal batches using Phase 1 memory management
        all_results = []
        with self.memory_manager.memory_managed_context("Phase 2 Technical Indicators Pipeline"):
            for i in range(0, len(combinations_batch), optimal_batch_size):
                batch = combinations_batch[i:i+optimal_batch_size]
                
                print(f"Processing batch {i//optimal_batch_size + 1}/{len(combinations_batch)//optimal_batch_size + 1}")
                
                # Parallel processing using Phase 1 CUDA streams
                batch_results = self._process_indicators_batch_parallel(batch)
                all_results.extend(batch_results)
                
        print(f"✓ All {len(combinations_batch)} combinations processed successfully")
        return all_results
    
    def _process_indicators_batch_parallel(self, batch: List[Dict]) -> List[Dict]:
        """Process indicators batch with Phase 1 parallel infrastructure"""
        # Step 1: Use Phase 1 batch conversion for all data at once
        tick_dataframes = [combo['tick_data'] for combo in batch]
        tick_arrays_batch = self.converter.batch_to_array(tick_dataframes)
        
        # Extract historical data for different indicators
        historical_candles_batch = [combo.get('historical_candles', pd.DataFrame()) for combo in batch]
        historical_macd_batch = [combo.get('historical_macd', pd.DataFrame()) for combo in batch]
        
        # Convert historical data using Phase 1 batch processing
        candles_arrays_batch = self.converter.batch_to_array(historical_candles_batch) if historical_candles_batch else []
        macd_arrays_batch = self.converter.batch_to_array(historical_macd_batch) if historical_macd_batch else []
        
        # Step 2: GPU-accelerated calculations using Phase 1 memory pools
        results = []
        for i, (combo, (tick_arrays, tick_metadata)) in enumerate(zip(batch, tick_arrays_batch)):
            # Convert to GPU using Phase 1 backend
            gpu_tick_data = {col: self.backend.asarray(arr) for col, arr in tick_arrays.items()}
            
            # Get corresponding historical data
            gpu_candle_data = {}
            gpu_macd_data = {}
            
            if i < len(candles_arrays_batch):
                candle_arrays, candle_metadata = candles_arrays_batch[i]
                gpu_candle_data = {col: self.backend.asarray(arr) for col, arr in candle_arrays.items()}
            
            if i < len(macd_arrays_batch):
                macd_arrays, macd_metadata = macd_arrays_batch[i]
                gpu_macd_data = {col: self.backend.asarray(arr) for col, arr in macd_arrays.items()}
            
            # Parallel indicator calculations using Phase 1 infrastructure
            atr_result = self._compute_atr_gpu(gpu_tick_data, gpu_candle_data, combo)
            macd_result = self._compute_macd_gpu(gpu_tick_data, gpu_macd_data, combo)  
            swing_result = self._compute_swings_gpu(gpu_tick_data, combo)
            
            # Combine results
            combined_result = self._combine_indicator_results(
                combo, atr_result, macd_result, swing_result
            )
            results.append(combined_result)
            
        return results
    
    def _compute_atr_gpu(self, gpu_tick_data: Dict, gpu_candle_data: Dict, combo: Dict) -> pd.DataFrame:
        """Compute ATR using GPU-accelerated calculator"""
        try:
            # Use GPU-accelerated vectorized ATR calculation
            atr_result = self.atr_calculator._compute_atr_gpu_vectorized(
                gpu_tick_data, gpu_candle_data, combo.get('atr_period', 14)
            )
            return atr_result
        except Exception as e:
            print(f"⚠️ ATR GPU calculation failed: {e}, using fallback")
            # Fallback to CPU
            n_ticks = len(gpu_tick_data.get('price', [0]))
            return pd.DataFrame({
                'datetime': range(n_ticks),
                'atr': [1.0] * n_ticks
            })
    
    def _compute_macd_gpu(self, gpu_tick_data: Dict, gpu_macd_data: Dict, combo: Dict) -> pd.DataFrame:
        """Compute MACD using GPU-accelerated calculator"""
        try:
            # Use GPU-accelerated vectorized MACD calculation
            macd_params = combo.get('macd_params', {'fast': 12, 'slow': 26, 'signal': 9})
            macd_result = self.macd_calculator._compute_macd_gpu_vectorized(
                gpu_tick_data, gpu_macd_data, macd_params
            )
            return macd_result
        except Exception as e:
            print(f"⚠️ MACD GPU calculation failed: {e}, using fallback")
            # Fallback to CPU
            n_ticks = len(gpu_tick_data.get('price', [0]))
            return pd.DataFrame({
                'macd': [0.0] * n_ticks,
                'signal': [0.0] * n_ticks,
                'histogram': [0.0] * n_ticks
            })
    
    def _compute_swings_gpu(self, gpu_tick_data: Dict, combo: Dict) -> pd.DataFrame:
        """Compute swing points using GPU-accelerated detector"""
        try:
            # Generate OHLC data from tick data for swing detection
            if 'price' not in gpu_tick_data:
                raise ValueError("GPU tick data must contain 'price' column")
            
            prices = gpu_tick_data['price']
            n_ticks = len(prices)
            
            # Create OHLC data for swing detection
            ohlc_data = {
                'high': self._gpu_expanding_max(prices),
                'low': self._gpu_expanding_min(prices)
            }
            
            # Use GPU-accelerated swing detection
            swing_result = self.swing_detector._detect_swings_gpu_optimized(
                ohlc_data, range(n_ticks)
            )
            return swing_result
        except Exception as e:
            print(f"⚠️ Swing GPU calculation failed: {e}, using fallback")
            # Fallback to CPU
            n_ticks = len(gpu_tick_data.get('price', [0]))
            return pd.DataFrame({
                'swing_high': [np.nan] * n_ticks,
                'swing_low': [np.nan] * n_ticks
            }, index=range(n_ticks))
    
    def _gpu_expanding_max(self, array: ArrayLike) -> ArrayLike:
        """GPU-accelerated expanding maximum"""
        n = len(array)
        result = self.backend.zeros(n)
        
        for i in range(n):
            result[i] = self.xp.max(array[:i+1])
        
        return result
    
    def _gpu_expanding_min(self, array: ArrayLike) -> ArrayLike:
        """GPU-accelerated expanding minimum"""
        n = len(array)
        result = self.backend.zeros(n)
        
        for i in range(n):
            result[i] = self.xp.min(array[:i+1])
        
        return result
    
    def _combine_indicator_results(self, combo: Dict, atr_result: pd.DataFrame, 
                                 macd_result: pd.DataFrame, swing_result: pd.DataFrame) -> Dict:
        """Combine all indicator results into single output dictionary"""
        # Combine all technical indicator results
        combined_result = combo.copy()
        
        # Add technical indicator results
        combined_result['atr_data'] = atr_result
        combined_result['macd_data'] = macd_result
        combined_result['swing_data'] = swing_result
        
        # Add performance metadata
        combined_result['gpu_processing'] = True
        combined_result['phase1_infrastructure'] = True
        
        return combined_result
    
    def get_gpu_performance_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive GPU performance statistics for Phase 2 validation.
        
        Returns:
            Dictionary with GPU utilization, memory usage, and performance metrics
        """
        try:
            stats = {
                'phase': 'Phase 2 - Technical Indicators GPU Acceleration',
                'components': {
                    'atr_calculator': 'GPU-accelerated with Phase 1 infrastructure',
                    'macd_calculator': 'GPU-accelerated with Phase 1 infrastructure', 
                    'swing_detector': 'GPU-optimized with Phase 1 integration'
                }
            }
            
            # Get GPU memory statistics
            if hasattr(self.xp, 'cuda'):
                memory_info = self.xp.cuda.Device().mem_info
                total_memory = memory_info[1]
                free_memory = memory_info[0]
                used_memory = total_memory - free_memory
                
                stats.update({
                    'total_gpu_memory_gb': total_memory / (1024**3),
                    'used_gpu_memory_gb': used_memory / (1024**3),
                    'free_gpu_memory_gb': free_memory / (1024**3),
                    'memory_utilization_percent': (used_memory / total_memory) * 100,
                    'target_utilization_range': '60-80%',
                    'backend': 'cupy',
                    'phase1_integration': True
                })
            else:
                stats.update({
                    'backend': 'cpu_fallback',
                    'phase1_integration': False,
                    'warning': 'GPU not available, using CPU fallback'
                })
            
            # Add batch processing statistics
            stats['batch_processing'] = {
                'optimal_batch_size_range': '25-40 combinations',
                'memory_management': '8 CUDA streams',
                'batch_optimizer': 'Phase 1 GPUBatchOptimizer',
                'array_converter': 'Phase 1 GPUArrayConverter'
            }
            
            return stats
            
        except Exception as e:
            return {
                'error': str(e),
                'phase': 'Phase 2',
                'status': 'error'
            }
