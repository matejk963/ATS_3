#!/usr/bin/env python3
"""
EMA Algorithm Comparison: Sequential vs Vectorized
Demonstrates performance and numerical precision differences
"""

import numpy as np
import pandas as pd
import time
from typing import Dict, Tuple
import warnings
warnings.filterwarnings('ignore')

try:
    import cupy as cp
    HAS_CUPY = True
    print("✅ CuPy available for GPU testing")
except ImportError:
    HAS_CUPY = False
    print("❌ CuPy not available - GPU tests will be skipped")


class EMAComparison:
    """Compare different EMA implementations"""
    
    def __init__(self):
        self.results = {}
    
    def pandas_ema(self, data: np.ndarray, span: int) -> np.ndarray:
        """Original pandas EMA - ground truth"""
        return pd.Series(data).ewm(span=span).mean().values
    
    def sequential_ema_numpy(self, data: np.ndarray, span: int) -> np.ndarray:
        """Sequential EMA - Phase 2 specified algorithm (NumPy)"""
        alpha = 2.0 / (span + 1)
        result = np.zeros_like(data, dtype=np.float64)
        result[0] = data[0]
        
        for i in range(1, len(data)):
            result[i] = alpha * data[i] + (1 - alpha) * result[i-1]
        
        return result
    
    def sequential_ema_cupy(self, data: np.ndarray, span: int) -> np.ndarray:
        """Sequential EMA on GPU - demonstrates inefficiency"""
        if not HAS_CUPY:
            return self.sequential_ema_numpy(data, span)
        
        # Transfer to GPU
        gpu_data = cp.asarray(data, dtype=cp.float64)
        alpha = 2.0 / (span + 1)
        result = cp.zeros_like(gpu_data, dtype=cp.float64)
        result[0] = gpu_data[0]
        
        # Sequential loop on GPU - very inefficient!
        for i in range(1, len(gpu_data)):
            result[i] = alpha * gpu_data[i] + (1 - alpha) * result[i-1]
        
        return result.get()  # Transfer back to CPU
    
    def vectorized_ema_v1(self, data: np.ndarray, span: int) -> np.ndarray:
        """Vectorized EMA using prefix sum approach (NumPy)"""
        alpha = 2.0 / (span + 1)
        alpha_rev = 1 - alpha
        n = len(data)
        
        # Create exponential weights
        weights = alpha * (alpha_rev ** np.arange(n)[::-1])
        
        # Compute using convolution-like approach
        result = np.zeros_like(data, dtype=np.float64)
        for i in range(n):
            end_idx = i + 1
            w = weights[-end_idx:]
            result[i] = np.sum(data[:end_idx] * w) / np.sum(w)
        
        return result
    
    def vectorized_ema_v2(self, data: np.ndarray, span: int) -> np.ndarray:
        """Improved vectorized EMA using cumulative operations"""
        alpha = 2.0 / (span + 1)
        alpha_rev = 1 - alpha
        n = len(data)
        
        # More efficient vectorized computation
        pows = alpha_rev ** np.arange(n + 1)
        scale_arr = 1 / pows[:-1]
        offset = data[0] * pows[1:]
        pw0 = alpha * alpha_rev ** (n - 1)
        mult = data * pw0 * scale_arr
        cumsums = mult.cumsum()
        result = offset + cumsums * scale_arr[::-1]
        
        return result
    
    def vectorized_ema_cupy(self, data: np.ndarray, span: int) -> np.ndarray:
        """Vectorized EMA on GPU using CuPy"""
        if not HAS_CUPY:
            return self.vectorized_ema_v2(data, span)
        
        # Transfer to GPU
        gpu_data = cp.asarray(data, dtype=cp.float64)
        alpha = 2.0 / (span + 1)
        alpha_rev = 1 - alpha
        n = len(gpu_data)
        
        # Vectorized operations on GPU
        pows = alpha_rev ** cp.arange(n + 1)
        scale_arr = 1 / pows[:-1]
        offset = gpu_data[0] * pows[1:]
        pw0 = alpha * alpha_rev ** (n - 1)
        mult = gpu_data * pw0 * scale_arr
        cumsums = cp.cumsum(mult)
        result_gpu = offset + cumsums * scale_arr[::-1]
        
        return result_gpu.get()  # Transfer back to CPU
    
    def benchmark_algorithms(self, data_sizes: list, span: int = 26, 
                           num_runs: int = 5) -> Dict[str, Dict]:
        """Benchmark all EMA algorithms"""
        results = {}
        
        algorithms = {
            'pandas': self.pandas_ema,
            'sequential_numpy': self.sequential_ema_numpy,
            'sequential_cupy': self.sequential_ema_cupy,
            'vectorized_v1': self.vectorized_ema_v1,
            'vectorized_v2': self.vectorized_ema_v2,
            'vectorized_cupy': self.vectorized_ema_cupy,
        }
        
        for size in data_sizes:
            print(f"\n📊 Benchmarking with {size:,} data points, span={span}")
            
            # Generate test data
            np.random.seed(42)
            data = np.random.randn(size).cumsum() + 100.0
            
            size_results = {}
            
            for name, func in algorithms.items():
                if not HAS_CUPY and 'cupy' in name:
                    print(f"  ⏭️  Skipping {name} (CuPy not available)")
                    continue
                
                times = []
                result = None
                
                for run in range(num_runs):
                    start_time = time.time()
                    try:
                        result = func(data, span)
                        end_time = time.time()
                        times.append(end_time - start_time)
                    except Exception as e:
                        print(f"  ❌ {name} failed: {e}")
                        break
                
                if times:
                    avg_time = np.mean(times)
                    std_time = np.std(times)
                    size_results[name] = {
                        'avg_time': avg_time,
                        'std_time': std_time,
                        'result': result
                    }
                    print(f"  ✅ {name:20s}: {avg_time*1000:6.2f}ms ± {std_time*1000:4.2f}ms")
            
            results[size] = size_results
        
        return results
    
    def numerical_precision_test(self, data_sizes: list, span: int = 26) -> Dict[str, Dict]:
        """Test numerical precision against pandas ground truth"""
        print(f"\n🔬 Numerical Precision Test (span={span})")
        print("=" * 60)
        
        precision_results = {}
        
        algorithms = {
            'sequential_numpy': self.sequential_ema_numpy,
            'vectorized_v1': self.vectorized_ema_v1,
            'vectorized_v2': self.vectorized_ema_v2,
        }
        
        if HAS_CUPY:
            algorithms.update({
                'sequential_cupy': self.sequential_ema_cupy,
                'vectorized_cupy': self.vectorized_ema_cupy,
            })
        
        for size in data_sizes:
            print(f"\n📏 Testing precision with {size:,} data points")
            
            # Generate test data
            np.random.seed(42)
            data = np.random.randn(size).cumsum() + 100.0
            
            # Ground truth
            pandas_result = self.pandas_ema(data, span)
            
            size_results = {}
            
            for name, func in algorithms.items():
                try:
                    result = func(data, span)
                    
                    # Calculate precision metrics
                    abs_error = np.abs(result - pandas_result)
                    max_error = np.max(abs_error)
                    mean_error = np.mean(abs_error)
                    rel_error = np.max(np.abs((result - pandas_result) / pandas_result))
                    
                    size_results[name] = {
                        'max_abs_error': max_error,
                        'mean_abs_error': mean_error,
                        'max_rel_error': rel_error,
                        'passes_phase2_req': max_error < 1e-10  # Phase 2 requirement
                    }
                    
                    status = "✅ PASS" if max_error < 1e-10 else "❌ FAIL"
                    print(f"  {name:20s}: max_err={max_error:.2e}, rel_err={rel_error:.2e} {status}")
                    
                except Exception as e:
                    print(f"  {name:20s}: ❌ ERROR - {e}")
            
            precision_results[size] = size_results
        
        return precision_results
    
    def performance_analysis(self, benchmark_results: Dict) -> None:
        """Analyze performance results"""
        print(f"\n📈 Performance Analysis")
        print("=" * 60)
        
        for size, results in benchmark_results.items():
            if 'pandas' not in results:
                continue
                
            pandas_time = results['pandas']['avg_time']
            print(f"\n🎯 Dataset size: {size:,} points")
            print(f"   Pandas baseline: {pandas_time*1000:.2f}ms")
            
            for name, data in results.items():
                if name == 'pandas':
                    continue
                
                speedup = pandas_time / data['avg_time']
                if speedup > 1:
                    print(f"   {name:20s}: {speedup:5.1f}x FASTER")
                else:
                    print(f"   {name:20s}: {1/speedup:5.1f}x SLOWER")


def main():
    """Run comprehensive EMA algorithm comparison"""
    print("🚀 EMA Algorithm Comparison: Sequential vs Vectorized")
    print("=" * 80)
    
    comparison = EMAComparison()
    
    # Test different dataset sizes
    data_sizes = [100, 1000, 5000, 10000]
    if HAS_CUPY:
        data_sizes.append(50000)  # Larger test for GPU
    
    # Run benchmarks
    benchmark_results = comparison.benchmark_algorithms(data_sizes, span=26, num_runs=3)
    
    # Test numerical precision
    precision_results = comparison.numerical_precision_test(data_sizes, span=26)
    
    # Analyze results
    comparison.performance_analysis(benchmark_results)
    
    # Summary of findings
    print(f"\n🎯 Key Findings:")
    print("=" * 40)
    
    # Check if any GPU algorithms are actually faster
    gpu_faster = False
    cpu_faster = False
    
    for size, results in benchmark_results.items():
        if size < 1000:  # Small datasets
            continue
            
        if 'sequential_numpy' in results and 'sequential_cupy' in results:
            numpy_time = results['sequential_numpy']['avg_time']
            cupy_time = results['sequential_cupy']['avg_time']
            
            if cupy_time > numpy_time * 1.5:  # 50% slower threshold
                cpu_faster = True
        
        if 'vectorized_v2' in results and 'vectorized_cupy' in results:
            numpy_time = results['vectorized_v2']['avg_time']
            cupy_time = results['vectorized_cupy']['avg_time']
            
            if cupy_time < numpy_time * 0.8:  # 20% faster threshold
                gpu_faster = True
    
    print(f"1. Sequential algorithm on GPU: {'❌ SLOWER than CPU' if cpu_faster else '⚠️  No clear benefit'}")
    print(f"2. Vectorized algorithm on GPU: {'✅ FASTER than CPU' if gpu_faster else '⚠️  No clear benefit'}")
    
    # Check precision requirements
    phase2_compatible = True
    for size, results in precision_results.items():
        for alg, metrics in results.items():
            if not metrics.get('passes_phase2_req', False):
                phase2_compatible = False
                break
    
    print(f"3. Phase 2 precision requirement: {'✅ All algorithms pass' if phase2_compatible else '❌ Some algorithms fail'}")
    
    print(f"\n💡 Recommendations:")
    print(f"   • Use adaptive algorithm selection based on dataset size and backend")
    print(f"   • Sequential algorithm should be CPU-only for small datasets")
    print(f"   • Vectorized algorithm should be used for GPU and large datasets")
    print(f"   • Validate numerical precision for each implementation")


if __name__ == "__main__":
    main()