#!/usr/bin/env python3
"""
User Acceptance Testing (UAT) for Technical Indicators Phase 1 Infrastructure

This UAT file provides comprehensive testing with detailed outputs to validate
that all Phase 1 components work correctly and meet acceptance criteria.

Run with: pwsh -Command "python uat/test_phase1_infrastructure_uat.py"
"""

import sys
import os
import pandas as pd
import numpy as np
import time
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from technical_indicators import (
    ArrayBackend, GPUArrayConverter, DataFrameMetadata,
    ArrayLike, is_gpu_array, ensure_cpu_array, validate_array_compatibility
)


class UATTestRunner:
    """UAT Test Runner with detailed output reporting"""
    
    def __init__(self):
        self.tests_passed = 0
        self.tests_failed = 0
        self.test_results = []
        
    def run_test(self, test_name, test_func):
        """Run a single test with error handling and reporting"""
        print(f"\n{'='*80}")
        print(f"🧪 TEST: {test_name}")
        print(f"{'='*80}")
        
        try:
            start_time = time.time()
            result = test_func()
            end_time = time.time()
            
            self.tests_passed += 1
            status = "✅ PASSED"
            duration = f"{(end_time - start_time)*1000:.2f}ms"
            
            self.test_results.append({
                'test': test_name,
                'status': 'PASSED',
                'duration': duration,
                'details': result if result else 'Success'
            })
            
            print(f"\n{status} - Duration: {duration}")
            
        except Exception as e:
            self.tests_failed += 1
            status = "❌ FAILED"
            error_msg = str(e)
            
            self.test_results.append({
                'test': test_name,
                'status': 'FAILED', 
                'duration': 'N/A',
                'details': error_msg
            })
            
            print(f"\n{status} - Error: {error_msg}")
            import traceback
            traceback.print_exc()
    
    def print_summary(self):
        """Print final test summary"""
        total_tests = self.tests_passed + self.tests_failed
        success_rate = (self.tests_passed / total_tests * 100) if total_tests > 0 else 0
        
        print(f"\n{'='*80}")
        print(f"🏁 UAT SUMMARY")
        print(f"{'='*80}")
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {self.tests_passed} ✅")
        print(f"Failed: {self.tests_failed} ❌")
        print(f"Success Rate: {success_rate:.1f}%")
        
        if self.tests_failed == 0:
            print(f"\n🎉 ALL TESTS PASSED - PHASE 1 INFRASTRUCTURE READY FOR PRODUCTION!")
        else:
            print(f"\n⚠️  {self.tests_failed} TEST(S) FAILED - REVIEW REQUIRED")
        
        return self.tests_failed == 0


def create_test_data():
    """Create realistic market data for testing"""
    np.random.seed(42)  # Reproducible results
    dates = pd.date_range('2023-01-01', periods=1000, freq='D')
    
    # Generate realistic OHLCV data
    base_price = 100
    returns = np.random.normal(0.001, 0.02, 1000)  # 0.1% daily return, 2% volatility
    prices = base_price * np.exp(np.cumsum(returns))
    
    # Generate OHLC from prices with realistic spreads
    closes = prices
    opens = np.roll(closes, 1)
    opens[0] = closes[0]
    
    highs = closes * (1 + np.abs(np.random.normal(0, 0.01, 1000)))
    lows = closes * (1 - np.abs(np.random.normal(0, 0.01, 1000)))
    volumes = np.random.lognormal(10, 1, 1000).astype(int)
    
    df = pd.DataFrame({
        'open': opens,
        'high': highs, 
        'low': lows,
        'close': closes,
        'volume': volumes
    }, index=dates)
    
    return df


def test_dataframe_metadata_functionality():
    """UAT-001: Test DataFrameMetadata preserves DataFrame structure"""
    print("Creating test DataFrame with mixed dtypes...")
    
    df = create_test_data().iloc[:100]
    print(f"Original DataFrame:")
    print(f"  Shape: {df.shape}")
    print(f"  Index type: {type(df.index).__name__}")
    print(f"  Index range: {df.index[0]} to {df.index[-1]}")
    print(f"  Columns: {list(df.columns)}")
    print(f"  Dtypes:\n{df.dtypes}")
    
    print(f"\nExtracting metadata...")
    metadata = DataFrameMetadata.from_dataframe(df)
    
    print(f"Metadata extracted:")
    print(f"  Index preserved: {len(metadata.index)} entries")
    print(f"  Columns preserved: {metadata.columns}")
    print(f"  Dtypes preserved: {list(metadata.dtypes.keys())}")
    
    print(f"\nTesting reconstruction...")
    arrays = {col: df[col].values for col in df.columns}
    reconstructed = metadata.reconstruct(arrays)
    
    print(f"Reconstruction results:")
    print(f"  Shape match: {df.shape == reconstructed.shape}")
    print(f"  Index match: {df.index.equals(reconstructed.index)}")
    print(f"  Columns match: {list(df.columns) == list(reconstructed.columns)}")
    
    # Check data integrity
    max_diff = 0
    for col in df.columns:
        diff = np.abs(df[col] - reconstructed[col]).max()
        max_diff = max(max_diff, diff)
        print(f"  {col} max difference: {diff:.2e}")
    
    print(f"  Overall max difference: {max_diff:.2e}")
    
    # Assertions
    assert df.shape == reconstructed.shape, "Shape mismatch"
    assert df.index.equals(reconstructed.index), "Index mismatch"
    assert list(df.columns) == list(reconstructed.columns), "Columns mismatch"
    assert max_diff < 1e-10, f"Data difference too large: {max_diff}"
    
    return f"✅ Metadata preserves DataFrame structure perfectly"


def test_array_backend_numpy():
    """UAT-002: Test ArrayBackend with NumPy backend"""
    print("Testing NumPy backend...")
    
    backend = ArrayBackend('numpy')
    print(f"Backend initialized:")
    print(f"  Backend type: {backend.backend}")
    print(f"  Array module: {backend.xp.__name__}")
    print(f"  Module path: {backend.xp.__file__}")
    
    # Test array creation
    print(f"\nTesting array creation methods...")
    test_shape = (100, 5)
    
    zeros_arr = backend.zeros(test_shape, dtype='float32')
    ones_arr = backend.ones(test_shape, dtype='float32')
    empty_arr = backend.empty(test_shape, dtype='float32')
    
    print(f"  Zeros array: shape={zeros_arr.shape}, dtype={zeros_arr.dtype}")
    print(f"  Ones array: shape={ones_arr.shape}, dtype={ones_arr.dtype}")
    print(f"  Empty array: shape={empty_arr.shape}, dtype={empty_arr.dtype}")
    
    # Test data conversion
    print(f"\nTesting data conversion...")
    test_data = [1.0, 2.0, 3.0, 4.0, 5.0]
    arr = backend.asarray(test_data, dtype='float32')
    print(f"  Converted data: {arr}")
    print(f"  Array type: {type(arr).__name__}")
    print(f"  Is GPU array: {is_gpu_array(arr)}")
    
    # Test CPU transfer
    cpu_arr = backend.to_cpu(arr)
    print(f"  CPU transfer: {cpu_arr}")
    print(f"  CPU array type: {type(cpu_arr).__name__}")
    
    # Assertions
    assert zeros_arr.shape == test_shape, "Zeros array shape incorrect"
    assert ones_arr.shape == test_shape, "Ones array shape incorrect"
    assert np.all(zeros_arr == 0), "Zeros array contains non-zero values"
    assert np.all(ones_arr == 1), "Ones array contains non-one values"
    assert not is_gpu_array(arr), "NumPy array incorrectly identified as GPU"
    
    return f"✅ NumPy backend works correctly"


def test_array_backend_cupy_fallback():
    """UAT-003: Test ArrayBackend CuPy behavior (available or fallback)"""
    print("Testing CuPy backend...")
    
    # Capture print output to check for fallback message
    import io
    from contextlib import redirect_stdout
    
    f = io.StringIO()
    with redirect_stdout(f):
        backend = ArrayBackend('cupy')
    fallback_output = f.getvalue()
    
    print(f"Backend initialization:")
    print(f"  Requested backend: cupy")
    print(f"  Actual backend type: {backend.backend}")
    print(f"  Array module: {backend.xp.__name__}")
    print(f"  Fallback message: '{fallback_output.strip()}'")
    
    # Test that backend works
    arr = backend.asarray([1, 2, 3], dtype='float32')
    print(f"\nFunctionality test:")
    print(f"  Created array: {arr}")
    print(f"  Array type: {type(arr).__name__}")
    print(f"  Is GPU array: {is_gpu_array(arr)}")
    
    # Check if CuPy is actually available or fell back
    cupy_available = backend.xp.__name__ == 'cupy'
    
    if cupy_available:
        print(f"\n🎉 CuPy is available and working!")
        # Test CuPy-specific functionality
        assert backend.backend == 'cupy', "Backend name should be 'cupy'"
        assert backend.xp.__name__ == 'cupy', "Should use CuPy module"
        assert fallback_output.strip() == '', "Should not show fallback message"
        assert is_gpu_array(arr), "CuPy array should be GPU array"
        
        # Test GPU to CPU transfer
        cpu_arr = backend.to_cpu(arr)
        print(f"  GPU to CPU transfer: {cpu_arr}")
        print(f"  CPU array type: {type(cpu_arr).__name__}")
        assert not is_gpu_array(cpu_arr), "CPU transfer should not be GPU"
        
        return f"✅ CuPy backend works correctly (GPU available)"
    else:
        print(f"\n📝 CuPy not available, fallback to NumPy working")
        # Test fallback behavior
        assert backend.backend == 'cupy', "Backend name should stay 'cupy'"
        assert backend.xp.__name__ == 'numpy', "Should fallback to numpy"
        assert "CuPy not available" in fallback_output, "Should show fallback message"
        assert not is_gpu_array(arr), "Fallback array should not be GPU"
        
        return f"✅ CuPy fallback works correctly"


def test_gpu_converter_basic_workflow():
    """UAT-004: Test GPUArrayConverter basic DataFrame conversion"""
    print("Testing DataFrame to Arrays conversion...")
    
    df = create_test_data().iloc[:200]
    print(f"Input DataFrame:")
    print(f"  Shape: {df.shape}")
    print(f"  Memory usage: {df.memory_usage(deep=True).sum():,} bytes")
    print(f"  Dtypes: {df.dtypes.to_dict()}")
    
    # Convert to arrays
    print(f"\nConverting to arrays...")
    arrays, metadata = GPUArrayConverter.to_arrays(df, dtype='float32', contiguous=True)
    
    print(f"Conversion results:")
    print(f"  Number of arrays: {len(arrays)}")
    total_array_memory = sum(arr.nbytes for arr in arrays.values())
    print(f"  Total array memory: {total_array_memory:,} bytes")
    print(f"  Memory reduction: {(1 - total_array_memory/df.memory_usage(deep=True).sum())*100:.1f}%")
    
    for col, arr in arrays.items():
        print(f"  {col}: shape={arr.shape}, dtype={arr.dtype}, contiguous={arr.flags.c_contiguous}")
    
    # Test reconstruction
    print(f"\nTesting reconstruction...")
    reconstructed = GPUArrayConverter.from_arrays(arrays, metadata)
    
    print(f"Reconstruction results:")
    print(f"  Shape preserved: {df.shape == reconstructed.shape}")
    print(f"  Index preserved: {df.index.equals(reconstructed.index)}")
    print(f"  Columns preserved: {list(df.columns) == list(reconstructed.columns)}")
    
    # Check data accuracy
    max_error = 0
    for col in df.columns:
        error = np.abs(df[col] - reconstructed[col]).max()
        max_error = max(max_error, error)
        print(f"  {col} max error: {error:.2e}")
    
    print(f"  Overall max error: {max_error:.2e}")
    
    # Assertions
    assert len(arrays) == len(df.columns), "Wrong number of arrays"
    assert all(arr.flags.c_contiguous for arr in arrays.values()), "Arrays not contiguous"
    assert all(arr.dtype == np.float32 for arr in arrays.values()), "Wrong dtype"
    assert max_error < 1e-5, f"Reconstruction error too large: {max_error}"
    
    return f"✅ DataFrame conversion works with {max_error:.2e} max error"


def test_gpu_converter_memory_optimization():
    """UAT-005: Test GPUArrayConverter memory optimization"""
    print("Testing memory optimization features...")
    
    # Create DataFrame with mixed dtypes and non-optimal layout
    df = create_test_data().iloc[:500]
    
    # Convert with different configurations
    print(f"Testing different conversion configurations...")
    
    # Original conversion (float64)
    arrays_f64, _ = GPUArrayConverter.to_arrays(df, dtype='float64', contiguous=False)
    print(f"\nFloat64 arrays:")
    f64_memory = sum(arr.nbytes for arr in arrays_f64.values())
    print(f"  Memory usage: {f64_memory:,} bytes")
    for col, arr in list(arrays_f64.items())[:2]:  # Show first 2
        print(f"  {col}: dtype={arr.dtype}, contiguous={arr.flags.c_contiguous}")
    
    # Optimized conversion
    arrays_f32, _ = GPUArrayConverter.to_arrays(df, dtype='float32', contiguous=True)
    print(f"\nFloat32 arrays:")
    f32_memory = sum(arr.nbytes for arr in arrays_f32.values())
    print(f"  Memory usage: {f32_memory:,} bytes")
    print(f"  Memory reduction: {(1 - f32_memory/f64_memory)*100:.1f}%")
    for col, arr in list(arrays_f32.items())[:2]:  # Show first 2
        print(f"  {col}: dtype={arr.dtype}, contiguous={arr.flags.c_contiguous}")
    
    # Test GPU optimization
    print(f"\nTesting GPU optimization...")
    optimized = GPUArrayConverter.optimize_for_gpu(arrays_f64)
    opt_memory = sum(arr.nbytes for arr in optimized.values())
    
    print(f"GPU optimized arrays:")
    print(f"  Memory usage: {opt_memory:,} bytes")
    print(f"  Memory reduction from f64: {(1 - opt_memory/f64_memory)*100:.1f}%")
    
    for col, arr in list(optimized.items())[:2]:  # Show first 2
        print(f"  {col}: dtype={arr.dtype}, contiguous={arr.flags.c_contiguous}")
    
    # Assertions
    assert f32_memory < f64_memory, "Float32 should use less memory"
    assert opt_memory == f32_memory, "Optimized should match float32"
    assert all(arr.dtype == np.float32 for arr in optimized.values()), "All should be float32"
    assert all(arr.flags.c_contiguous for arr in optimized.values()), "All should be contiguous"
    
    reduction = (1 - opt_memory/f64_memory)*100
    return f"✅ Memory optimization achieves {reduction:.1f}% reduction"


def test_array_compatibility_validation():
    """UAT-006: Test array compatibility validation utilities"""
    print("Testing array compatibility validation...")
    
    backend = ArrayBackend('numpy')
    
    # Create test arrays with different characteristics
    print(f"Creating test arrays...")
    arr1 = backend.zeros((1000,), dtype='float32')
    arr2 = backend.ones((1000,), dtype='float32')  # Same shape, dtype
    arr3 = backend.zeros((500,), dtype='float32')   # Different shape
    arr4 = backend.zeros((1000,), dtype='float64')  # Different dtype
    
    print(f"Test arrays created:")
    print(f"  arr1: shape={arr1.shape}, dtype={arr1.dtype}")
    print(f"  arr2: shape={arr2.shape}, dtype={arr2.dtype}")
    print(f"  arr3: shape={arr3.shape}, dtype={arr3.dtype}")
    print(f"  arr4: shape={arr4.shape}, dtype={arr4.dtype}")
    
    # Test compatibility checks
    print(f"\nTesting compatibility checks...")
    
    compat_1_2 = validate_array_compatibility(arr1, arr2)
    compat_1_3 = validate_array_compatibility(arr1, arr3)
    compat_1_4 = validate_array_compatibility(arr1, arr4)
    
    print(f"  arr1 vs arr2 (same shape, dtype): {compat_1_2}")
    print(f"  arr1 vs arr3 (different shape): {compat_1_3}")
    print(f"  arr1 vs arr4 (different dtype): {compat_1_4}")
    
    # Test GPU detection
    print(f"\nTesting GPU detection...")
    for i, arr in enumerate([arr1, arr2, arr3, arr4], 1):
        is_gpu = is_gpu_array(arr)
        cpu_arr = ensure_cpu_array(arr)
        print(f"  arr{i}: is_gpu={is_gpu}, cpu_conversion_type={type(cpu_arr).__name__}")
    
    # Assertions
    assert compat_1_2 == True, "Compatible arrays should validate as compatible"
    assert compat_1_3 == False, "Different shapes should be incompatible"
    assert compat_1_4 == False, "Different dtypes should be incompatible"
    assert all(not is_gpu_array(arr) for arr in [arr1, arr2, arr3, arr4]), "NumPy arrays should not be GPU"
    
    return f"✅ Array compatibility validation works correctly"


def test_complete_end_to_end_workflow():
    """UAT-007: Test complete end-to-end processing workflow"""
    print("Testing complete end-to-end workflow...")
    
    # Create realistic dataset
    df = create_test_data().iloc[:1000]
    print(f"Dataset created:")
    print(f"  Shape: {df.shape}")
    print(f"  Date range: {df.index[0].date()} to {df.index[-1].date()}")
    print(f"  Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")
    print(f"  Volume range: {df['volume'].min():,} - {df['volume'].max():,}")
    
    # Initialize backend
    print(f"\nInitializing processing backend...")
    backend = ArrayBackend('numpy')
    print(f"  Backend: {backend.backend} ({backend.xp.__name__})")
    
    # Convert and optimize
    print(f"\nConverting DataFrame to optimized arrays...")
    arrays, metadata = GPUArrayConverter.to_arrays(df, dtype='float32', contiguous=True)
    optimized_arrays = GPUArrayConverter.optimize_for_gpu(arrays)
    
    print(f"  Converted {len(optimized_arrays)} arrays")
    print(f"  Memory usage: {sum(arr.nbytes for arr in optimized_arrays.values()):,} bytes")
    
    # Transfer to backend
    backend_arrays = {key: backend.asarray(arr) for key, arr in optimized_arrays.items()}
    print(f"  Transferred to {backend.backend} backend")
    
    # Simulate technical indicator calculations
    print(f"\nSimulating technical indicator calculations...")
    
    processed_arrays = {}
    
    # Simple Moving Average (SMA)
    window = 20
    for col in ['open', 'high', 'low', 'close']:
        prices = backend_arrays[col]
        # Pad array to handle window
        padded = backend.xp.pad(prices, (window-1, 0), mode='edge')
        # Calculate SMA using convolution
        kernel = backend.xp.ones(window) / window
        sma = backend.xp.convolve(padded, kernel, mode='valid')
        processed_arrays[f'{col}_sma{window}'] = sma
        
    print(f"  Calculated SMA{window} for OHLC data")
    
    # Price volatility (rolling std approximation)
    vol_window = 20
    close_prices = backend_arrays['close']
    returns = backend.xp.diff(backend.xp.log(close_prices))
    # Simple rolling volatility approximation
    vol = backend.xp.sqrt(backend.xp.var(returns)) * backend.xp.ones_like(close_prices)
    processed_arrays['volatility'] = vol
    
    print(f"  Calculated volatility indicator")
    
    # Combine original and processed data
    all_arrays = {**backend_arrays, **processed_arrays}
    print(f"  Total indicators: {len(all_arrays)}")
    
    # Convert back to DataFrame format
    print(f"\nReconstructing results...")
    cpu_arrays = {key: ensure_cpu_array(arr) for key, arr in all_arrays.items()}
    
    # Create new DataFrame (since we have additional columns)
    result_df = pd.DataFrame(cpu_arrays, index=df.index)
    print(f"  Final DataFrame shape: {result_df.shape}")
    print(f"  Original columns: {len(df.columns)}")
    print(f"  New columns: {len(result_df.columns) - len(df.columns)}")
    
    # Validate results
    print(f"\nValidating results...")
    
    # Check data integrity of original columns
    max_error = 0
    for col in df.columns:
        error = np.abs(df[col] - result_df[col]).max()
        max_error = max(max_error, error)
    
    print(f"  Original data preservation: max error = {max_error:.2e}")
    
    # Check new indicators
    sma_cols = [col for col in result_df.columns if 'sma' in col]
    print(f"  SMA indicators: {len(sma_cols)}")
    print(f"  SMA sample values: {result_df[sma_cols[0]].iloc[-5:].round(2).tolist()}")
    
    vol_values = result_df['volatility'].iloc[-5:]
    print(f"  Volatility sample: {vol_values.round(4).tolist()}")
    
    # Performance metrics
    processing_memory = sum(arr.nbytes for arr in all_arrays.values())
    original_memory = df.memory_usage(deep=True).sum()
    
    print(f"\nPerformance metrics:")
    print(f"  Original memory: {original_memory:,} bytes")
    print(f"  Processing memory: {processing_memory:,} bytes")
    print(f"  Final memory: {result_df.memory_usage(deep=True).sum():,} bytes")
    
    # Assertions
    assert result_df.shape[0] == df.shape[0], "Row count should be preserved"
    assert result_df.shape[1] > df.shape[1], "Should have additional columns"
    assert max_error < 2e-5, f"Original data error too large: {max_error}"
    assert len(sma_cols) == 4, "Should have 4 SMA indicators"
    assert 'volatility' in result_df.columns, "Should have volatility indicator"
    
    return f"✅ End-to-end workflow processes {df.shape[0]} rows → {result_df.shape[1]} indicators"


def test_performance_benchmarks():
    """UAT-008: Test performance benchmarks and scalability"""
    print("Testing performance benchmarks...")
    
    # Test different dataset sizes
    sizes = [100, 1000, 5000, 10000]
    results = []
    
    print(f"Testing scalability across different dataset sizes...")
    
    for size in sizes:
        print(f"\n--- Testing with {size:,} rows ---")
        
        # Create dataset
        df = create_test_data().iloc[:size]
        original_memory = df.memory_usage(deep=True).sum()
        
        # Time the complete workflow
        start_time = time.time()
        
        # Convert
        arrays, metadata = GPUArrayConverter.to_arrays(df, dtype='float32', contiguous=True)
        
        # Optimize
        optimized = GPUArrayConverter.optimize_for_gpu(arrays)
        
        # Backend transfer
        backend = ArrayBackend('numpy')
        backend_arrays = {key: backend.asarray(arr) for key, arr in optimized.items()}
        
        # Reconstruct
        reconstructed = GPUArrayConverter.from_arrays(backend_arrays, metadata)
        
        end_time = time.time()
        
        # Calculate metrics
        duration = (end_time - start_time) * 1000  # milliseconds
        optimized_memory = sum(arr.nbytes for arr in optimized.values())
        memory_reduction = (1 - optimized_memory/original_memory) * 100
        
        # Per-row performance
        ms_per_row = duration / size
        
        results.append({
            'rows': size,
            'duration_ms': duration,
            'ms_per_row': ms_per_row,
            'original_memory': original_memory,
            'optimized_memory': optimized_memory,
            'memory_reduction': memory_reduction
        })
        
        print(f"  Duration: {duration:.2f}ms ({ms_per_row:.4f}ms/row)")
        print(f"  Original memory: {original_memory:,} bytes")
        print(f"  Optimized memory: {optimized_memory:,} bytes")
        print(f"  Memory reduction: {memory_reduction:.1f}%")
        
        # Verify data integrity
        max_error = max(np.abs(df[col] - reconstructed[col]).max() for col in df.columns)
        print(f"  Data integrity: {max_error:.2e} max error")
        
        assert max_error < 2e-5, f"Data integrity failed for {size} rows"
    
    # Analyze performance trends
    print(f"\n--- Performance Analysis ---")
    print(f"{'Rows':<8} {'Duration':<12} {'ms/row':<10} {'Memory Red.':<12}")
    print(f"{'-'*8} {'-'*12} {'-'*10} {'-'*12}")
    
    for r in results:
        print(f"{r['rows']:<8,} {r['duration_ms']:<12.2f} {r['ms_per_row']:<10.4f} {r['memory_reduction']:<12.1f}%")
    
    # Performance requirements check
    largest_test = results[-1]
    avg_ms_per_row = sum(r['ms_per_row'] for r in results) / len(results)
    min_memory_reduction = min(r['memory_reduction'] for r in results)
    
    print(f"\nPerformance Summary:")
    print(f"  Largest dataset: {largest_test['rows']:,} rows in {largest_test['duration_ms']:.2f}ms")
    print(f"  Average performance: {avg_ms_per_row:.4f}ms per row")
    print(f"  Minimum memory reduction: {min_memory_reduction:.1f}%")
    print(f"  Scalability: {'Linear' if largest_test['ms_per_row'] < avg_ms_per_row * 2 else 'Non-linear'}")
    
    # Assertions
    assert largest_test['duration_ms'] < 1000, "10K rows should process in <1 second"
    assert avg_ms_per_row < 0.1, "Should average <0.1ms per row"
    assert min_memory_reduction > 40, "Should achieve >40% memory reduction"
    
    return f"✅ Performance: {avg_ms_per_row:.4f}ms/row, {min_memory_reduction:.1f}% memory reduction"


def main():
    """Run all UAT tests"""
    print("🚀 TECHNICAL INDICATORS PHASE 1 INFRASTRUCTURE")
    print("   User Acceptance Testing (UAT)")
    print(f"   Executed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    runner = UATTestRunner()
    
    # Define all UAT tests
    tests = [
        ("DataFrameMetadata Functionality", test_dataframe_metadata_functionality),
        ("ArrayBackend NumPy Support", test_array_backend_numpy),
        ("ArrayBackend CuPy Support", test_array_backend_cupy_fallback),
        ("GPUConverter Basic Workflow", test_gpu_converter_basic_workflow),
        ("GPUConverter Memory Optimization", test_gpu_converter_memory_optimization),
        ("Array Compatibility Validation", test_array_compatibility_validation),
        ("Complete End-to-End Workflow", test_complete_end_to_end_workflow),
        ("Performance Benchmarks", test_performance_benchmarks),
    ]
    
    # Run all tests
    for test_name, test_func in tests:
        runner.run_test(test_name, test_func)
    
    # Print final summary
    success = runner.print_summary()
    
    if success:
        print(f"\n🎯 ACCEPTANCE CRITERIA MET:")
        print(f"   ✅ DataFrame structure preservation")
        print(f"   ✅ Multi-backend support (NumPy + CuPy/fallback)")
        print(f"   ✅ Memory optimization (>40% reduction)")
        print(f"   ✅ Array conversion accuracy (<2e-5 error)")
        print(f"   ✅ Performance scalability (<0.1ms/row)")
        print(f"   ✅ End-to-end workflow validation")
        print(f"\n🏁 PHASE 1 INFRASTRUCTURE IS PRODUCTION READY!")
        
        return 0
    else:
        print(f"\n❌ ACCEPTANCE CRITERIA NOT MET - REVIEW REQUIRED")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)