"""
Memory Transfer Optimization for GPU-Ready Technical Indicators

This module provides comprehensive memory optimization capabilities for efficient
CPU-GPU data transfers and memory management in technical indicator computations.

Key Features:
- Array memory layout optimization (C-contiguous, aligned)
- Batch transfer optimization to minimize CPU-GPU roundtrips
- Memory pool management for reduced allocation overhead
- Lazy transfer mechanisms for on-demand GPU transfers
- Bandwidth monitoring and fragmentation analysis
- Cache-aware optimization for CPU efficiency
- Memory pressure handling and automatic fallback
"""

import time
import warnings
import psutil
import os
from typing import Dict, List, Tuple, Optional, Any, Union
from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class MemoryConfig:
    """Configuration for memory optimization"""
    dtype: str = 'float32'
    ensure_contiguous: bool = True
    lazy_transfer: bool = False
    use_pinned_memory: bool = False
    enable_memory_pool: bool = False
    cache_aware: bool = True
    monitor_bandwidth: bool = False
    max_memory_gb: float = 8.0
    
    def __post_init__(self):
        """Validate configuration"""
        valid_dtypes = ['float32', 'float64', 'int32', 'int64']
        if self.dtype not in valid_dtypes:
            raise ValueError(f"Unsupported dtype: {self.dtype}. Must be one of {valid_dtypes}")


class LazyArray:
    """Lazy transfer wrapper for arrays"""
    
    def __init__(self, cpu_array: np.ndarray, backend: str):
        self._cpu_array = cpu_array
        self._gpu_array = None
        self._backend = backend
        self._transferred = False
    
    @property
    def cpu_array(self) -> np.ndarray:
        """Get CPU array"""
        return self._cpu_array
    
    @property
    def gpu_array(self) -> np.ndarray:
        """Get GPU array, transferring if necessary"""
        if not self._transferred:
            self._transfer_to_gpu()
        return self._gpu_array
    
    def _transfer_to_gpu(self):
        """Transfer array to GPU"""
        if self._backend == 'cupy':
            try:
                import cupy as cp
                self._gpu_array = cp.asarray(self._cpu_array)
                self._transferred = True
            except ImportError:
                # Fallback to CPU
                self._gpu_array = self._cpu_array
                self._transferred = True
        else:
            self._gpu_array = self._cpu_array
            self._transferred = True


class MemoryOptimizer:
    """
    Memory optimization system for GPU-ready technical indicators.
    
    Provides comprehensive memory management including layout optimization,
    transfer batching, memory pooling, and bandwidth monitoring.
    """
    
    def __init__(self,
                 dtype: str = 'float32',
                 ensure_contiguous: bool = True,
                 lazy_transfer: bool = False,
                 use_pinned_memory: bool = False,
                 enable_memory_pool: bool = False,
                 cache_aware: bool = True,
                 monitor_bandwidth: bool = False,
                 max_memory_gb: float = 8.0):
        """
        Initialize memory optimizer.
        
        Args:
            dtype: Default data type for arrays
            ensure_contiguous: Ensure C-contiguous memory layout
            lazy_transfer: Use lazy transfer for GPU arrays
            use_pinned_memory: Use pinned memory for faster transfers
            enable_memory_pool: Enable memory pool for allocation
            cache_aware: Optimize for CPU cache efficiency
            monitor_bandwidth: Monitor transfer bandwidth
            max_memory_gb: Maximum memory usage limit
        """
        self.config = MemoryConfig(
            dtype=dtype,
            ensure_contiguous=ensure_contiguous,
            lazy_transfer=lazy_transfer,
            use_pinned_memory=use_pinned_memory,
            enable_memory_pool=enable_memory_pool,
            cache_aware=cache_aware,
            monitor_bandwidth=monitor_bandwidth,
            max_memory_gb=max_memory_gb
        )
        
        # Initialize memory pool if enabled
        self.memory_pool = {} if enable_memory_pool else None
        
        # Bandwidth monitoring
        self._transfer_stats = []
    
    def get_memory_usage(self) -> float:
        """Get current memory usage in MB"""
        try:
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / 1024 / 1024
        except Exception:
            return 0.0
    
    def optimize_arrays(self, 
                       arrays: Dict[str, np.ndarray],
                       dtype: Optional[str] = None,
                       ensure_contiguous: Optional[bool] = None) -> Dict[str, np.ndarray]:
        """
        Optimize array memory layout for GPU transfers.
        
        Args:
            arrays: Dictionary of arrays to optimize
            dtype: Target data type (overrides config)
            ensure_contiguous: Ensure contiguous layout (overrides config)
            
        Returns:
            Dictionary of optimized arrays
        """
        target_dtype = dtype or self.config.dtype
        contiguous = ensure_contiguous if ensure_contiguous is not None else self.config.ensure_contiguous
        
        optimized = {}
        
        for key, arr in arrays.items():
            # Convert dtype if needed
            if key == 'volume' and 'int' not in target_dtype:
                # Keep volume as integer type
                if arr.dtype != np.int32:
                    arr = arr.astype(np.int32)
            else:
                if arr.dtype.name != target_dtype:
                    arr = arr.astype(target_dtype)
            
            # Ensure contiguous layout
            if contiguous and not arr.flags['C_CONTIGUOUS']:
                arr = np.ascontiguousarray(arr)
            
            # Ensure alignment
            if not arr.flags['ALIGNED']:
                arr = np.copy(arr)  # This typically ensures alignment
            
            optimized[key] = arr
        
        return optimized
    
    def optimize_dtypes(self,
                       arrays: Dict[str, np.ndarray],
                       target_float: str = 'float32',
                       target_int: str = 'int32') -> Dict[str, np.ndarray]:
        """
        Optimize data types for GPU efficiency.
        
        Args:
            arrays: Dictionary of arrays to optimize
            target_float: Target floating point type
            target_int: Target integer type
            
        Returns:
            Dictionary of dtype-optimized arrays
        """
        optimized = {}
        
        for key, arr in arrays.items():
            if np.issubdtype(arr.dtype, np.floating):
                optimized[key] = arr.astype(target_float)
            elif np.issubdtype(arr.dtype, np.integer):
                optimized[key] = arr.astype(target_int)
            else:
                optimized[key] = arr  # Keep as-is for other types
        
        return optimized
    
    def batch_transfer(self, 
                      arrays: Dict[str, np.ndarray],
                      backend: str = 'cupy') -> Dict[str, np.ndarray]:
        """
        Perform batch transfer to GPU to minimize transfer overhead.
        
        Args:
            arrays: Dictionary of arrays to transfer
            backend: Target backend ('cupy' or 'numpy')
            
        Returns:
            Dictionary of transferred arrays
        """
        if backend == 'numpy':
            return arrays  # No transfer needed
        
        if backend != 'cupy':
            raise ValueError(f"Unsupported backend: {backend}")
        
        try:
            import cupy as cp
            
            # Batch transfer all arrays
            gpu_arrays = {}
            for key, arr in arrays.items():
                gpu_arrays[key] = cp.asarray(arr)
            
            return gpu_arrays
            
        except ImportError:
            warnings.warn("CuPy not available, returning CPU arrays")
            return arrays
    
    def minimize_cpu_gpu_transfers(self,
                                  arrays: Dict[str, np.ndarray],
                                  operations: List[Dict]) -> Dict[str, Any]:
        """
        Analyze operations to minimize CPU-GPU transfers.
        
        Args:
            arrays: Input arrays
            operations: List of operations with inputs/outputs
            
        Returns:
            Transfer optimization plan
        """
        # Analyze which arrays are needed on GPU
        gpu_needed = set()
        cpu_outputs = set()
        
        for op in operations:
            gpu_needed.update(op.get('inputs', []))
            # Assume outputs stay on GPU until final transfer
        
        # Determine what needs initial transfer
        initial_transfer = [key for key in arrays.keys() if key in gpu_needed]
        
        # All outputs need final transfer back to CPU
        final_transfer = []
        for op in operations:
            final_transfer.extend(op.get('outputs', []))
        
        # Calculate estimated savings
        naive_transfers = len(operations) * 2  # Transfer in/out for each operation
        optimized_transfers = 2  # Initial batch + final batch
        estimated_savings = max(0, naive_transfers - optimized_transfers)
        
        return {
            'initial_transfer': initial_transfer,
            'final_transfer': final_transfer,
            'estimated_savings': estimated_savings,
            'transfer_ratio': optimized_transfers / naive_transfers if naive_transfers > 0 else 1.0
        }
    
    def create_lazy_transfer(self,
                           arrays: Dict[str, np.ndarray],
                           backend: str = 'cupy') -> Dict[str, LazyArray]:
        """
        Create lazy transfer wrappers for arrays.
        
        Args:
            arrays: Arrays to wrap
            backend: Target backend
            
        Returns:
            Dictionary of lazy transfer wrappers
        """
        return {key: LazyArray(arr, backend) for key, arr in arrays.items()}
    
    def allocate_from_pool(self, size: int, dtype: str = 'float32') -> Optional[np.ndarray]:
        """
        Allocate memory from pool if available.
        
        Args:
            size: Number of elements to allocate
            dtype: Data type for allocation
            
        Returns:
            Allocated array or None if pool disabled
        """
        if not self.memory_pool:
            return np.empty(size, dtype=dtype)
        
        # Simple pool implementation - in practice would be more sophisticated
        pool_key = f"{size}_{dtype}"
        
        if pool_key in self.memory_pool:
            return self.memory_pool.pop(pool_key)
        else:
            return np.empty(size, dtype=dtype)
    
    def analyze_fragmentation(self, arrays: Dict[str, np.ndarray]) -> Dict[str, Any]:
        """
        Analyze memory fragmentation in array dictionary.
        
        Args:
            arrays: Arrays to analyze
            
        Returns:
            Fragmentation analysis report
        """
        total_memory = sum(arr.nbytes for arr in arrays.values())
        contiguous_count = sum(1 for arr in arrays.values() if arr.flags['C_CONTIGUOUS'])
        
        fragmentation_ratio = 1.0 - (contiguous_count / len(arrays)) if arrays else 0.0
        
        recommendations = []
        if fragmentation_ratio > 0.5:
            recommendations.append("High fragmentation detected - consider array consolidation")
        if any(not arr.flags['ALIGNED'] for arr in arrays.values()):
            recommendations.append("Unaligned arrays detected - consider memory realignment")
        
        return {
            'total_memory': total_memory,
            'total_arrays': len(arrays),
            'contiguous_arrays': contiguous_count,
            'fragmentation_ratio': fragmentation_ratio,
            'recommendations': recommendations
        }
    
    def create_pinned_arrays(self, arrays: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        """
        Create pinned memory arrays for faster transfers.
        
        Args:
            arrays: Arrays to pin
            
        Returns:
            Dictionary of pinned arrays
        """
        # Note: Actual pinned memory would require specific CUDA/CuPy APIs
        # This is a simplified implementation
        pinned = {}
        
        for key, arr in arrays.items():
            # Ensure optimal layout for transfer
            if not arr.flags['C_CONTIGUOUS']:
                arr = np.ascontiguousarray(arr)
            
            # In real implementation, would use cupy.cuda.alloc_pinned_memory()
            pinned[key] = arr
        
        return pinned
    
    def monitor_transfer_bandwidth(self, 
                                 arrays: Dict[str, np.ndarray],
                                 backend: str = 'cupy') -> Dict[str, float]:
        """
        Monitor CPU-GPU transfer bandwidth.
        
        Args:
            arrays: Arrays to transfer and monitor
            backend: Target backend
            
        Returns:
            Bandwidth statistics
        """
        if not self.config.monitor_bandwidth:
            return {'bandwidth_gbps': 0.0, 'transfer_time': 0.0, 'data_size': 0.0}
        
        total_size = sum(arr.nbytes for arr in arrays.values())
        
        start_time = time.perf_counter()
        transferred = self.batch_transfer(arrays, backend)
        end_time = time.perf_counter()
        
        transfer_time = end_time - start_time
        bandwidth_gbps = (total_size / 1e9) / transfer_time if transfer_time > 0 else 0.0
        
        stats = {
            'transfer_time': transfer_time,
            'data_size': total_size / 1e6,  # MB
            'bandwidth_gbps': bandwidth_gbps
        }
        
        self._transfer_stats.append(stats)
        return stats
    
    def optimize_for_cache(self, arrays: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        """
        Optimize arrays for CPU cache efficiency.
        
        Args:
            arrays: Arrays to optimize
            
        Returns:
            Cache-optimized arrays
        """
        if not self.config.cache_aware:
            return arrays
        
        optimized = {}
        
        for key, arr in arrays.items():
            # Ensure C-contiguous layout for cache efficiency
            if not arr.flags['C_CONTIGUOUS']:
                arr = np.ascontiguousarray(arr)
            
            # Ensure proper alignment for SIMD operations
            if not arr.flags['ALIGNED']:
                arr = np.copy(arr)
            
            optimized[key] = arr
        
        return optimized
    
    def handle_memory_pressure(self, 
                             arrays: Dict[str, np.ndarray],
                             max_memory_gb: Optional[float] = None) -> Dict[str, Any]:
        """
        Handle memory pressure situations.
        
        Args:
            arrays: Arrays causing memory pressure
            max_memory_gb: Memory limit in GB
            
        Returns:
            Memory pressure handling result
        """
        limit = max_memory_gb or self.config.max_memory_gb
        current_usage = self.get_memory_usage() / 1024  # Convert to GB
        
        if current_usage <= limit:
            return {'status': 'ok', 'action_taken': 'none'}
        
        # Calculate array memory usage
        array_memory = sum(arr.nbytes for arr in arrays.values()) / 1e9  # GB
        
        if array_memory > limit:
            return {
                'status': 'exceeded_limit',
                'action_taken': 'recommendation_to_batch',
                'current_gb': current_usage,
                'limit_gb': limit,
                'array_gb': array_memory
            }
        else:
            # Try to free some memory
            import gc
            gc.collect()
            
            return {
                'status': 'handled',
                'action_taken': 'garbage_collection',
                'memory_after_gc': self.get_memory_usage() / 1024
            }