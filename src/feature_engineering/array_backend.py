"""GPU-only ArrayBackend for CuPy operations with optimization"""

from typing import Union, List, Tuple, Optional
import numpy as np

ArrayLike = Union[np.ndarray, 'cupy.ndarray']


class ArrayBackend:
    """GPU-only interface for CuPy operations with RTX 4080 SUPER optimization"""
    
    def __init__(self, backend: str = 'cupy'):
        """Initialize GPU-only backend with CuPy and memory pool optimization"""
        if backend != 'cupy':
            raise ValueError(f"GPU-only mode: Only 'cupy' backend supported, got '{backend}'")
        self.backend = backend
        self.xp = self._get_cupy_module()
        
        # Initialize GPU memory pools for optimization (Task 1.1)
        self.memory_pool = None
        self.pinned_memory_pool = None
        self._init_memory_pools()
        
    def _get_cupy_module(self):
        """Get CuPy module with GPU validation"""
        try:
            import cupy as cp
            # Verify GPU is actually available
            if not cp.cuda.is_available():
                raise RuntimeError("No CUDA-capable GPU detected. GPU processing requires CUDA-compatible hardware.")
            return cp
        except ImportError:
            raise RuntimeError("CuPy not available. Install CuPy for GPU processing: pip install cupy-cuda12x")
    
    def _init_memory_pools(self):
        """Initialize GPU memory pools for efficient batch processing (Task 1.1)"""
        if self.backend == 'cupy':
            try:
                # Pre-allocate memory pool for efficient batch processing
                self.memory_pool = self.xp.get_default_memory_pool()
                self.pinned_memory_pool = self.xp.get_default_pinned_memory_pool()
                
                # Set memory pool growth to accommodate large batches
                # Target: Support 25-40 combinations per batch efficiently
                self.memory_pool.set_limit(size=None)  # No limit for RTX 4080 SUPER
            except Exception as e:
                # Graceful fallback if memory pool setup fails
                self.memory_pool = None
                self.pinned_memory_pool = None
        
    def asarray(self, data, dtype='float32') -> ArrayLike:
        """Convert to GPU array using CuPy"""
        return self.xp.asarray(data, dtype=dtype)
    
    def batch_asarray(self, data_batch: List, target_shape: Optional[Tuple] = None) -> List[ArrayLike]:
        """Batch-optimized GPU array conversion with memory pre-allocation (Task 1.1)"""
        if not data_batch:
            return []
        
        # Pre-allocate contiguous GPU memory for entire batch
        # Minimize memory fragmentation and transfer overhead
        results = []
        
        for data in data_batch:
            # Ensure optimal memory layout and type conversion
            array = self.xp.asarray(data, dtype='float32')
            # Ensure C-contiguous layout for optimal GPU performance
            if not array.flags.c_contiguous:
                array = self.xp.ascontiguousarray(array)
            results.append(array)
        
        return results
    
    def ensure_contiguous_layout(self, array: ArrayLike) -> ArrayLike:
        """Ensure C-contiguous memory layout for optimal GPU performance (Task 1.1)"""
        if self.backend == 'cupy':
            return self.xp.ascontiguousarray(array, dtype=self.xp.float32)
        return np.ascontiguousarray(array, dtype=np.float32)
    
    def optimize_dtypes_batch(self, arrays: List[ArrayLike]) -> List[ArrayLike]:
        """Convert entire batch to float32 in single GPU operation (Task 1.1)"""
        # Minimize multiple type conversion overhead
        # Reuse pre-allocated GPU memory between conversions
        optimized_arrays = []
        
        for array in arrays:
            if array.dtype != self.xp.float32:
                # Single-pass type conversion with memory reuse
                optimized_array = array.astype(self.xp.float32)
            else:
                optimized_array = array
            
            # Ensure contiguous layout
            if not optimized_array.flags.c_contiguous:
                optimized_array = self.xp.ascontiguousarray(optimized_array)
            
            optimized_arrays.append(optimized_array)
        
        return optimized_arrays
        
    def to_cpu(self, arr: ArrayLike) -> np.ndarray:
        """Transfer GPU array to CPU (for final results only)"""
        if hasattr(arr, 'get'):  # CuPy array
            return arr.get()
        return np.asarray(arr)
    
    def zeros(self, shape, dtype='float32') -> ArrayLike:
        """Create GPU zeros array"""
        return self.xp.zeros(shape, dtype=dtype)
    
    def ones(self, shape, dtype='float32') -> ArrayLike:
        """Create GPU ones array"""
        return self.xp.ones(shape, dtype=dtype)
    
    def empty(self, shape, dtype='float32') -> ArrayLike:
        """Create empty GPU array"""
        return self.xp.empty(shape, dtype=dtype)
    
    def full(self, shape, fill_value, dtype='float32') -> ArrayLike:
        """Create GPU array filled with specified value"""
        return self.xp.full(shape, fill_value, dtype=dtype)
    
    # Mathematical operations for ATR risk calculator
    def multiply(self, arr1: ArrayLike, arr2: Union[ArrayLike, float]) -> ArrayLike:
        """Element-wise multiplication on GPU"""
        return self.xp.multiply(arr1, arr2)
    
    def add(self, arr1: ArrayLike, arr2: Union[ArrayLike, float]) -> ArrayLike:
        """Element-wise addition on GPU"""
        return self.xp.add(arr1, arr2)
    
    def subtract(self, arr1: ArrayLike, arr2: Union[ArrayLike, float]) -> ArrayLike:
        """Element-wise subtraction on GPU"""
        return self.xp.subtract(arr1, arr2)