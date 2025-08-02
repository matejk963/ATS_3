"""Rolling window operations for vectorized swing detection"""

import numpy as np
from .array_backend import ArrayBackend
from .array_types import ArrayLike


def sliding_window_view_compat(arr: ArrayLike, window_shape: int, xp) -> ArrayLike:
    """Create sliding window view compatible with both NumPy and CuPy"""
    
    if hasattr(xp.lib.stride_tricks, 'sliding_window_view'):
        # NumPy >= 1.20.0 or CuPy with sliding_window_view
        return xp.lib.stride_tricks.sliding_window_view(arr, window_shape)
    else:
        # Manual implementation for older versions or missing functions
        n = len(arr)
        if window_shape > n:
            return xp.empty((0, window_shape), dtype=arr.dtype)
        
        # Create manual sliding windows using array indexing
        num_windows = n - window_shape + 1
        windows = xp.zeros((num_windows, window_shape), dtype=arr.dtype)
        
        for i in range(num_windows):
            windows[i] = arr[i:i + window_shape]
        
        return windows


def rolling_window_max(data: ArrayLike, window: int, backend: ArrayBackend, center: bool = True) -> ArrayLike:
    """
    Compute rolling maximum with center alignment
    
    Args:
        data: Input array
        window: Window size (should be odd for proper centering)
        backend: ArrayBackend instance
        center: If True, center the window; if False, trailing window
        
    Returns:
        Array of rolling maxima, same length as input
    """
    xp = backend.xp
    n = len(data)
    
    if window >= n:
        # Window larger than data, return global max for all positions
        global_max = xp.max(data)
        return xp.full(n, global_max, dtype=data.dtype)
    
    if center:
        # Center the window
        half_window = window // 2
        padded_data = xp.concatenate([
            xp.full(half_window, data[0], dtype=data.dtype),  # Pad start
            data,
            xp.full(half_window, data[-1], dtype=data.dtype)  # Pad end
        ])
        
        # Create sliding windows
        windows = sliding_window_view_compat(padded_data, window, xp)
        
        # Compute max for each window
        rolling_max = xp.max(windows, axis=1)
        
        return rolling_max
    else:
        # Trailing window (standard rolling)
        result = xp.zeros_like(data)
        
        for i in range(n):
            start = max(0, i - window + 1)
            result[i] = xp.max(data[start:i+1])
        
        return result


def rolling_window_min(data: ArrayLike, window: int, backend: ArrayBackend, center: bool = True) -> ArrayLike:
    """
    Compute rolling minimum with center alignment
    
    Args:
        data: Input array
        window: Window size (should be odd for proper centering)
        backend: ArrayBackend instance  
        center: If True, center the window; if False, trailing window
        
    Returns:
        Array of rolling minima, same length as input
    """
    xp = backend.xp
    n = len(data)
    
    if window >= n:
        # Window larger than data, return global min for all positions
        global_min = xp.min(data)
        return xp.full(n, global_min, dtype=data.dtype)
    
    if center:
        # Center the window
        half_window = window // 2
        padded_data = xp.concatenate([
            xp.full(half_window, data[0], dtype=data.dtype),  # Pad start
            data,
            xp.full(half_window, data[-1], dtype=data.dtype)  # Pad end
        ])
        
        # Create sliding windows
        windows = sliding_window_view_compat(padded_data, window, xp)
        
        # Compute min for each window
        rolling_min = xp.min(windows, axis=1)
        
        return rolling_min
    else:
        # Trailing window (standard rolling)
        result = xp.zeros_like(data)
        
        for i in range(n):
            start = max(0, i - window + 1)
            result[i] = xp.min(data[start:i+1])
        
        return result


def check_neighbor_conditions(data: ArrayLike, indices: ArrayLike, lookback: int, 
                            backend: ArrayBackend, is_high: bool = True) -> ArrayLike:
    """
    Vectorized check of neighbor conditions for swing detection
    
    Args:
        data: Price data array
        indices: Indices to check 
        lookback: Lookback period
        backend: ArrayBackend instance
        is_high: True for swing highs, False for swing lows
        
    Returns:
        Boolean array indicating which indices satisfy neighbor conditions
    """
    xp = backend.xp
    n = len(data)
    
    if len(indices) == 0:
        return xp.array([], dtype=bool)
    
    results = xp.zeros(len(indices), dtype=bool)
    
    for i, idx in enumerate(indices):
        if idx < lookback or idx >= n - lookback:
            results[i] = False
            continue
            
        # Check left neighbors
        left_slice = data[max(0, idx - lookback):idx]
        # Check right neighbors  
        right_slice = data[idx + 1:min(n, idx + lookback + 1)]
        
        if is_high:
            # For swing highs: current value should be > min of neighbors
            left_ok = len(left_slice) == 0 or data[idx] > xp.min(left_slice)
            right_ok = len(right_slice) == 0 or data[idx] > xp.min(right_slice)
        else:
            # For swing lows: current value should be < max of neighbors
            left_ok = len(left_slice) == 0 or data[idx] < xp.max(left_slice)
            right_ok = len(right_slice) == 0 or data[idx] < xp.max(right_slice)
        
        results[i] = left_ok and right_ok
    
    return results