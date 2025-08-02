#!/usr/bin/env python3
"""
Usage example for Technical Indicators Phase 1 GPU-Ready Infrastructure

This example demonstrates how to use the Phase 1 components for 
DataFrame ↔ Array conversion with GPU compatibility.
"""

import pandas as pd
import numpy as np
from src.feature_engineering import (
    ArrayBackend, GPUArrayConverter, DataFrameMetadata,
    is_gpu_array, ensure_cpu_array, validate_array_compatibility
)


def create_sample_data():
    """Create sample market data for demonstration"""
    dates = pd.date_range('2023-01-01', periods=1000, freq='D')
    np.random.seed(42)  # For reproducible results
    
    data = pd.DataFrame({
        'open': np.random.uniform(100, 200, 1000).astype(np.float64),
        'high': np.random.uniform(150, 250, 1000).astype(np.float64),
        'low': np.random.uniform(50, 150, 1000).astype(np.float64),
        'close': np.random.uniform(80, 220, 1000).astype(np.float64),
        'volume': np.random.randint(1000, 10000, 1000).astype(np.int64)
    }, index=dates)
    
    return data


def demonstrate_basic_workflow():
    """Demonstrate basic DataFrame to Array conversion workflow"""
    print("=== Basic Workflow Demonstration ===")
    
    # Create sample data
    df = create_sample_data()
    print(f"Original DataFrame shape: {df.shape}")
    print(f"Original dtypes:\n{df.dtypes}")
    
    # Convert DataFrame to arrays
    arrays, metadata = GPUArrayConverter.to_arrays(df, dtype='float32', contiguous=True)
    print(f"\nConverted to {len(arrays)} arrays")
    
    for col, arr in arrays.items():
        print(f"  {col}: shape={arr.shape}, dtype={arr.dtype}, contiguous={arr.flags.c_contiguous}")
    
    # Reconstruct DataFrame
    reconstructed = GPUArrayConverter.from_arrays(arrays, metadata)
    print(f"\nReconstructed DataFrame shape: {reconstructed.shape}")
    
    # Verify data integrity
    max_diff = 0
    for col in df.columns:
        diff = np.abs(reconstructed[col].values - df[col].values).max()
        max_diff = max(max_diff, diff)
        print(f"  {col}: max difference = {diff:.2e}")
    
    print(f"Overall max difference: {max_diff:.2e}")


def demonstrate_backend_usage():
    """Demonstrate ArrayBackend usage"""
    print("\n=== Backend Usage Demonstration ===")
    
    df = create_sample_data().iloc[:100]  # Smaller dataset for demo
    
    # Test NumPy backend
    print("1. NumPy Backend:")
    numpy_backend = ArrayBackend('numpy')
    print(f"   Backend type: {numpy_backend.backend}")
    print(f"   Array module: {numpy_backend.xp.__name__}")
    
    # Convert to arrays and transfer to backend
    arrays, metadata = GPUArrayConverter.to_arrays(df)
    backend_arrays = {key: numpy_backend.asarray(arr) for key, arr in arrays.items()}
    
    # Verify arrays are on correct backend
    for col, arr in backend_arrays.items():
        print(f"   {col}: is_gpu_array = {is_gpu_array(arr)}")
    
    # Test CuPy backend (will fallback to NumPy without CuPy)
    print("\n2. CuPy Backend (fallback to NumPy):")
    cupy_backend = ArrayBackend('cupy')
    print(f"   Backend type: {cupy_backend.backend}")
    print(f"   Array module: {cupy_backend.xp.__name__}")
    
    # Arrays can be transferred between backends
    cpu_arrays = {key: cupy_backend.to_cpu(arr) for key, arr in backend_arrays.items()}
    reconstructed = GPUArrayConverter.from_arrays(cpu_arrays, metadata)
    print(f"   Reconstructed shape: {reconstructed.shape}")


def demonstrate_memory_optimization():
    """Demonstrate memory optimization features"""
    print("\n=== Memory Optimization Demonstration ===")
    
    # Create DataFrame with mixed dtypes and non-contiguous arrays
    df = create_sample_data().iloc[:200]
    
    # Convert with different dtypes
    arrays_f64, _ = GPUArrayConverter.to_arrays(df, dtype='float64', contiguous=False)
    
    print("Before optimization:")
    for col, arr in arrays_f64.items():
        print(f"  {col}: dtype={arr.dtype}, contiguous={arr.flags.c_contiguous}")
    
    # Optimize for GPU
    optimized = GPUArrayConverter.optimize_for_gpu(arrays_f64)
    
    print("\nAfter optimization:")
    for col, arr in optimized.items():
        print(f"  {col}: dtype={arr.dtype}, contiguous={arr.flags.c_contiguous}")
    
    # Compare memory usage (approximate)
    original_size = sum(arr.nbytes for arr in arrays_f64.values())
    optimized_size = sum(arr.nbytes for arr in optimized.values())
    
    print(f"\nMemory usage:")
    print(f"  Original (float64): {original_size:,} bytes")
    print(f"  Optimized (float32): {optimized_size:,} bytes")
    print(f"  Reduction: {(1 - optimized_size/original_size)*100:.1f}%")


def demonstrate_array_compatibility():
    """Demonstrate array compatibility validation"""
    print("\n=== Array Compatibility Demonstration ===")
    
    backend = ArrayBackend('numpy')
    
    # Create compatible arrays
    arr1 = backend.zeros((1000,), dtype='float32')
    arr2 = backend.ones((1000,), dtype='float32')
    arr3 = backend.zeros((500,), dtype='float32')  # Different shape
    arr4 = backend.zeros((1000,), dtype='float64')  # Different dtype
    
    print("Compatibility checks:")
    print(f"  arr1 vs arr2 (same shape, dtype): {validate_array_compatibility(arr1, arr2)}")
    print(f"  arr1 vs arr3 (different shape): {validate_array_compatibility(arr1, arr3)}")
    print(f"  arr1 vs arr4 (different dtype): {validate_array_compatibility(arr1, arr4)}")


def demonstrate_complete_pipeline():
    """Demonstrate complete processing pipeline"""
    print("\n=== Complete Pipeline Demonstration ===")
    
    # Create sample data
    df = create_sample_data().iloc[:500]
    print(f"1. Input DataFrame: {df.shape}")
    
    # Initialize backend
    backend = ArrayBackend('numpy')
    print(f"2. Backend initialized: {backend.backend}")
    
    # Convert DataFrame to GPU-optimized arrays
    arrays, metadata = GPUArrayConverter.to_arrays(df, dtype='float32', contiguous=True)
    optimized_arrays = GPUArrayConverter.optimize_for_gpu(arrays)
    print(f"3. Converted to {len(optimized_arrays)} optimized arrays")
    
    # Transfer to backend
    backend_arrays = {key: backend.asarray(arr) for key, arr in optimized_arrays.items()}
    print(f"4. Transferred to backend")
    
    # Simulate processing (simple moving average)
    processed_arrays = {}
    window = 20
    for key, arr in backend_arrays.items():
        # Simple moving average using NumPy
        padded = backend.xp.pad(arr, (window-1, 0), mode='edge')
        kernel = backend.xp.ones(window) / window
        ma = backend.xp.convolve(padded, kernel, mode='valid')
        processed_arrays[f"{key}_ma{window}"] = ma
    
    print(f"5. Processed arrays (moving averages): {len(processed_arrays)}")
    
    # Combine original and processed data
    combined_arrays = {**backend_arrays, **processed_arrays}
    
    # Reconstruct DataFrame (need to create new metadata for combined data)
    combined_df_data = {}
    for key, arr in combined_arrays.items():
        combined_df_data[key] = ensure_cpu_array(arr)
    
    combined_df = pd.DataFrame(combined_df_data, index=df.index)
    print(f"6. Final result: {combined_df.shape}")
    print(f"   Columns: {list(combined_df.columns)}")
    
    return combined_df


def main():
    """Run all demonstrations"""
    print("Technical Indicators Phase 1 GPU-Ready Infrastructure Demo")
    print("=" * 60)
    
    demonstrate_basic_workflow()
    demonstrate_backend_usage()
    demonstrate_memory_optimization()
    demonstrate_array_compatibility()
    result_df = demonstrate_complete_pipeline()
    
    print("\n" + "=" * 60)
    print("Phase 1 infrastructure is ready for Phase 2 calculator implementations!")
    print(f"Final processed dataset: {result_df.shape}")
    
    # Display sample of results
    print("\nSample results (first 5 rows, first 4 columns):")
    print(result_df.iloc[:5, :4].round(2))


if __name__ == "__main__":
    main()