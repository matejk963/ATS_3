"""ArrayLike type definitions and utilities for CPU/GPU compatibility"""

from typing import Union, Protocol, runtime_checkable
import numpy as np

# Union type for arrays that work on both CPU and GPU
ArrayLike = Union[np.ndarray, 'cupy.ndarray']


@runtime_checkable
class ArrayProtocol(Protocol):
    """Protocol for array-like objects"""
    shape: tuple
    dtype: np.dtype
    
    def __array__(self) -> np.ndarray:
        """Convert to NumPy array"""
        ...
    
    def astype(self, dtype) -> 'ArrayProtocol':
        """Convert dtype"""
        ...


def is_gpu_array(arr: ArrayLike) -> bool:
    """Check if array is on GPU (CuPy array)"""
    return hasattr(arr, 'get')


def ensure_cpu_array(arr: ArrayLike) -> np.ndarray:
    """Ensure array is on CPU"""
    if is_gpu_array(arr):
        return arr.get()
    return np.asarray(arr)


def validate_array_compatibility(arr1: ArrayLike, arr2: ArrayLike) -> bool:
    """Validate that two arrays are compatible for operations"""
    return (
        arr1.shape == arr2.shape and
        type(arr1) == type(arr2) and  # Same backend (NumPy/CuPy)
        arr1.dtype == arr2.dtype
    )