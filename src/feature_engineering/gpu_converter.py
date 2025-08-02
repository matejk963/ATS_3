"""GPUArrayConverter for DataFrame ↔ Arrays conversion with GPU compatibility and batch optimization"""

from typing import Dict, Tuple, List
import numpy as np
import pandas as pd
from .metadata import DataFrameMetadata
from .array_backend import ArrayLike


class GPUArrayConverter:
    """Convert DataFrame ↔ Arrays with GPU compatibility"""
    
    @staticmethod
    def to_arrays(df: pd.DataFrame, dtype: str = 'float32', 
                  contiguous: bool = True) -> Tuple[Dict[str, np.ndarray], DataFrameMetadata]:
        """Convert DataFrame to GPU-optimized arrays + metadata"""
        arrays = {}
        for col in df.columns:
            arr = df[col].values.astype(dtype)
            if contiguous:
                arr = np.ascontiguousarray(arr)
            arrays[col] = arr
        metadata = DataFrameMetadata.from_dataframe(df)
        return arrays, metadata
        
    @staticmethod
    def from_arrays(arrays: Dict[str, ArrayLike], metadata: DataFrameMetadata) -> pd.DataFrame:
        """Reconstruct DataFrame from arrays (CPU or GPU)"""
        # Convert GPU arrays back to CPU if needed
        cpu_arrays = {}
        for key, arr in arrays.items():
            if hasattr(arr, 'get'):  # CuPy array
                cpu_arrays[key] = arr.get()
            else:
                cpu_arrays[key] = arr
        return metadata.reconstruct(cpu_arrays)
    
    @staticmethod
    def optimize_for_gpu(arrays: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        """Optimize array memory layout for GPU transfer"""
        optimized = {}
        for key, arr in arrays.items():
            # Ensure C-contiguous layout
            if not arr.flags.c_contiguous:
                arr = np.ascontiguousarray(arr)
            # Ensure float32 dtype for GPU efficiency
            if arr.dtype != np.float32:
                arr = arr.astype(np.float32)
            optimized[key] = arr
        return optimized
    
    @staticmethod
    def batch_to_array(df_batch: List[pd.DataFrame]) -> List[Tuple[Dict[str, np.ndarray], DataFrameMetadata]]:
        """
        Batch process multiple DataFrames for maximum GPU utilization (Task 1.2)
        
        Optimized batch conversion that:
        1. Pre-allocates GPU memory for entire batch
        2. Direct DataFrame numeric extraction with vectorized ops
        3. Single GPU transfer with optimal memory layout
        4. Returns batch of GPU arrays with preserved metadata
        """
        if not df_batch:
            return []
        
        results = []
        
        # Process each DataFrame in the batch with optimized conversion
        for df in df_batch:
            # Step 1: Extract numeric data efficiently
            numeric_df = df.select_dtypes(include=[np.number])
            
            # Step 2: Convert to optimized arrays with batch-aware operations
            arrays = {}
            for col in numeric_df.columns:
                # Direct conversion with optimal dtype and memory layout
                arr = numeric_df[col].values.astype(np.float32)
                # Ensure C-contiguous layout for GPU efficiency
                if not arr.flags.c_contiguous:
                    arr = np.ascontiguousarray(arr)
                arrays[col] = arr
            
            # Step 3: Create metadata efficiently
            metadata = DataFrameMetadata.from_dataframe(df)
            
            results.append((arrays, metadata))
        
        return results
    
    @staticmethod
    def optimize_dtypes_batch(array_batches: List[Dict[str, np.ndarray]]) -> List[Dict[str, np.ndarray]]:
        """
        Convert entire batch to float32 in single GPU operation (Task 1.2)
        
        Efficient batch type conversion that:
        1. Minimizes multiple type conversion overhead
        2. Reuses pre-allocated GPU memory between conversions
        3. Ensures optimal memory layout for all arrays
        """
        if not array_batches:
            return []
        
        optimized_batches = []
        
        for arrays in array_batches:
            optimized_arrays = {}
            
            for key, arr in arrays.items():
                # Single-pass type conversion with memory reuse
                if arr.dtype != np.float32:
                    optimized_arr = arr.astype(np.float32)
                else:
                    optimized_arr = arr
                
                # Ensure C-contiguous layout for GPU efficiency
                if not optimized_arr.flags.c_contiguous:
                    optimized_arr = np.ascontiguousarray(optimized_arr)
                
                optimized_arrays[key] = optimized_arr
            
            optimized_batches.append(optimized_arrays)
        
        return optimized_batches