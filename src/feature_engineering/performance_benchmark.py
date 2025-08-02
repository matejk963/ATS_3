"""
CPU/GPU Performance Benchmarking System

This module provides comprehensive benchmarking capabilities for comparing
performance between CPU (NumPy) and GPU (CuPy) implementations of technical indicators.

Key Features:
- Synthetic data generation for consistent testing
- Multi-run statistical analysis
- Memory usage tracking
- Automatic speedup calculation
- Performance reporting and visualization
- Threshold detection for GPU advantage
"""

import time
import warnings
import psutil
import os
from typing import Dict, List, Tuple, Callable, Optional, Any, Union
from dataclasses import dataclass
import pandas as pd
import numpy as np

from .unified_pipeline import UnifiedTechnicalIndicatorsPipeline


@dataclass
class BenchmarkConfig:
    """Configuration for performance benchmarking"""
    runs: int = 5
    warmup_runs: int = 1
    data_sizes: List[int] = None
    enable_memory_tracking: bool = True
    random_seed: int = 42
    
    def __post_init__(self):
        """Validate configuration"""
        if self.runs <= 0:
            raise ValueError("runs must be positive")
        if self.warmup_runs < 0:
            raise ValueError("warmup_runs cannot be negative")
        if self.data_sizes is None:
            self.data_sizes = [1000, 10000, 100000]


class PerformanceBenchmark:
    """
    Comprehensive performance benchmarking system for technical indicators.
    
    Provides statistical analysis of CPU vs GPU performance across different
    data sizes and operations, with memory usage tracking and reporting.
    """
    
    def __init__(self, 
                 runs: int = 5,
                 warmup_runs: int = 1,
                 data_sizes: List[int] = None,
                 enable_memory_tracking: bool = True,
                 random_seed: int = 42):
        """
        Initialize performance benchmark system.
        
        Args:
            runs: Number of benchmark runs for statistical analysis
            warmup_runs: Number of warmup runs to exclude from timing
            data_sizes: List of data sizes to benchmark
            enable_memory_tracking: Whether to track memory usage
            random_seed: Random seed for reproducible data generation
        """
        self.config = BenchmarkConfig(
            runs=runs,
            warmup_runs=warmup_runs,
            data_sizes=data_sizes,
            enable_memory_tracking=enable_memory_tracking,
            random_seed=random_seed
        )
        
        # Initialize results storage
        self.results = {}
        
        # Set random seed
        np.random.seed(self.config.random_seed)
        
        # Check GPU availability once during initialization
        self.gpu_available = self._check_gpu_availability()
    
    def _check_gpu_availability(self) -> bool:
        """Check if GPU/CuPy is available for benchmarking"""
        try:
            import cupy as cp
            # Try a simple operation to verify GPU works
            test_array = cp.array([1, 2, 3])
            _ = cp.sum(test_array)
            return True
        except (ImportError, Exception):
            return False
    
    def generate_test_data(self, size: int) -> pd.DataFrame:
        """
        Generate synthetic OHLCV data for testing.
        
        Args:
            size: Number of data points to generate
            
        Returns:
            DataFrame with OHLCV columns
        """
        # Use specific seed for this data size to ensure reproducibility
        local_rng = np.random.RandomState(self.config.random_seed + size)
        
        # Generate realistic price movement
        returns = local_rng.normal(0, 0.001, size)
        prices = 100 * np.exp(np.cumsum(returns))  # Geometric Brownian motion
        
        # Generate OHLC from prices with realistic spreads
        noise = local_rng.normal(0, 0.0005, size)
        open_prices = prices + noise
        close_prices = prices
        
        # Ensure high >= max(open, close) and low <= min(open, close)
        high_spread = np.abs(local_rng.normal(0, 0.002, size))
        low_spread = np.abs(local_rng.normal(0, 0.002, size))
        
        high_prices = np.maximum(open_prices, close_prices) * (1 + high_spread)
        low_prices = np.minimum(open_prices, close_prices) * (1 - low_spread)
        
        return pd.DataFrame({
            'open': open_prices,
            'high': high_prices,
            'low': low_prices,
            'close': close_prices,
            'volume': local_rng.randint(1000, 10000, size)
        })
    
    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB"""
        if not self.config.enable_memory_tracking:
            return 0.0
        
        try:
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / 1024 / 1024  # Convert to MB
        except Exception:
            return 0.0
    
    def benchmark_operation(self, 
                           operation_func: Callable,
                           data: pd.DataFrame,
                           backend: str,
                           runs: Optional[int] = None) -> Dict[str, Any]:
        """
        Benchmark a single operation with statistical analysis.
        
        Args:
            operation_func: Function to benchmark
            data: Input data for the operation
            backend: Backend to use ('numpy' or 'cupy')
            runs: Number of runs (defaults to config.runs)
            
        Returns:
            Dictionary with timing and memory statistics
        """
        if runs is None:
            runs = self.config.runs
        
        times = []
        memory_usage = []
        
        try:
            # Warmup runs
            for _ in range(self.config.warmup_runs):
                operation_func(data, backend)
            
            # Actual benchmark runs
            for _ in range(runs):
                start_memory = self._get_memory_usage()
                start_time = time.perf_counter()
                
                result = operation_func(data, backend)
                
                end_time = time.perf_counter()
                end_memory = self._get_memory_usage()
                
                times.append(end_time - start_time)
                memory_usage.append(end_memory - start_memory)
            
            return {
                'avg_time': np.mean(times),
                'std_time': np.std(times),
                'min_time': np.min(times),
                'max_time': np.max(times),
                'avg_memory': np.mean(memory_usage),
                'std_memory': np.std(memory_usage),
                'backend': backend,
                'data_size': len(data),
                'backend_available': True
            }
            
        except Exception as e:
            return {
                'error': str(e),
                'backend': backend,
                'data_size': len(data),
                'backend_available': False
            }
    
    def _benchmark_macd(self, data: pd.DataFrame, backend: str) -> pd.DataFrame:
        """Benchmark MACD calculation"""
        pipeline = UnifiedTechnicalIndicatorsPipeline(
            backend=backend,
            fallback_on_error=True  # Allow fallback for more robust benchmarking
        )
        
        return pipeline.compute_indicators(
            data=data,
            indicators=['macd'],
            macd_params={'fast': 12, 'slow': 26, 'signal': 9}
        )
    
    def _benchmark_atr(self, data: pd.DataFrame, backend: str) -> pd.DataFrame:
        """Benchmark ATR calculation"""
        pipeline = UnifiedTechnicalIndicatorsPipeline(
            backend=backend,
            fallback_on_error=True  # Allow fallback for more robust benchmarking
        )
        
        return pipeline.compute_indicators(
            data=data,
            indicators=['atr'],
            atr_period=14
        )
    
    def _benchmark_swing_points(self, data: pd.DataFrame, backend: str) -> pd.DataFrame:
        """Benchmark swing point detection"""
        pipeline = UnifiedTechnicalIndicatorsPipeline(
            backend=backend,
            fallback_on_error=True  # Allow fallback for more robust benchmarking
        )
        
        return pipeline.compute_indicators(
            data=data,
            indicators=['swing_points'],
            swing_lookback=20
        )
    
    def _benchmark_candles(self, data: pd.DataFrame, backend: str) -> pd.DataFrame:
        """Benchmark candle generation with actual computation"""
        # Perform actual candle-like aggregation to simulate real work
        if len(data) == 0:
            return data
        
        # Simulate candle aggregation by computing rolling statistics
        # This provides meaningful work to benchmark
        result = data.copy()
        
        # Compute rolling statistics (simulating candle generation work)
        window = min(20, len(data))
        result['rolling_mean'] = data['close'].rolling(window=window, min_periods=1).mean()
        result['rolling_std'] = data['close'].rolling(window=window, min_periods=1).std()
        result['rolling_max'] = data['high'].rolling(window=window, min_periods=1).max()
        result['rolling_min'] = data['low'].rolling(window=window, min_periods=1).min()
        
        # Add some computation to simulate actual candle processing
        result['price_range'] = result['high'] - result['low']
        result['body_size'] = abs(result['close'] - result['open'])
        result['upper_shadow'] = result['high'] - np.maximum(result['open'], result['close'])
        result['lower_shadow'] = np.minimum(result['open'], result['close']) - result['low']
        
        return result
    
    def _benchmark_macd_with_params(self, data: pd.DataFrame, backend: str, params: Dict) -> pd.DataFrame:
        """Benchmark MACD with custom parameters"""
        pipeline = UnifiedTechnicalIndicatorsPipeline(
            backend=backend,
            fallback_on_error=True  # Allow fallback for more robust benchmarking
        )
        
        return pipeline.compute_indicators(
            data=data,
            indicators=['macd'],
            macd_params=params
        )
    
    def _calculate_speedup(self, cpu_result: Dict, gpu_result: Dict) -> float:
        """Calculate speedup ratio between CPU and GPU"""
        if not (cpu_result.get('backend_available') and gpu_result.get('backend_available')):
            return None
        
        cpu_time = cpu_result.get('avg_time', 0)
        gpu_time = gpu_result.get('avg_time', 1)  # Avoid division by zero
        
        if gpu_time > 0:
            return cpu_time / gpu_time
        return None
    
    def run_full_benchmark(self, 
                          data_sizes: Optional[List[int]] = None,
                          custom_operations: Optional[Dict[str, Callable]] = None,
                          runs: Optional[int] = None) -> None:
        """
        Run complete benchmark suite across multiple data sizes.
        
        Args:
            data_sizes: Sizes to benchmark (defaults to config.data_sizes)
            custom_operations: Additional operations to benchmark
            runs: Number of runs per operation
        """
        if data_sizes is None:
            data_sizes = self.config.data_sizes
        
        # Default operations
        operations = {
            'MACD': self._benchmark_macd,
            'ATR': self._benchmark_atr,
            'Swing_Points': self._benchmark_swing_points,
            'Candle_Generation': self._benchmark_candles
        }
        
        # Add custom operations
        if custom_operations:
            operations.update(custom_operations)
        
        # Print GPU availability status
        gpu_status = "available" if self.gpu_available else "not available"
        print(f"GPU Status: {gpu_status}")
        
        for size in data_sizes:
            print(f"Benchmarking data size: {size}")
            test_data = self.generate_test_data(size)
            
            for op_name, op_func in operations.items():
                # CPU benchmark (always run)
                cpu_result = self.benchmark_operation(op_func, test_data, 'numpy', runs)
                
                # GPU benchmark (only if GPU available)
                if self.gpu_available:
                    gpu_result = self.benchmark_operation(op_func, test_data, 'cupy', runs)
                else:
                    # Create a placeholder result indicating GPU not available
                    gpu_result = {
                        'error': 'GPU/CuPy not available',
                        'backend': 'cupy',
                        'data_size': len(test_data),
                        'backend_available': False
                    }
                
                # Calculate speedup and memory ratio
                speedup = self._calculate_speedup(cpu_result, gpu_result)
                
                memory_ratio = 1.0
                if (cpu_result.get('backend_available') and 
                    gpu_result.get('backend_available') and 
                    cpu_result.get('avg_memory', 0) > 0):
                    memory_ratio = gpu_result.get('avg_memory', 0) / cpu_result.get('avg_memory', 1)
                
                # Store results
                key = f"{op_name}_{size}"
                self.results[key] = {
                    'cpu': cpu_result,
                    'gpu': gpu_result,
                    'speedup': speedup,
                    'memory_ratio': memory_ratio
                }
                
                if speedup:
                    print(f"  {op_name}: {speedup:.2f}x speedup")
                elif not self.gpu_available:
                    print(f"  {op_name}: GPU not available, CPU time: {cpu_result.get('avg_time', 0):.4f}s")
                else:
                    print(f"  {op_name}: benchmark failed")
    
    def generate_performance_report(self) -> str:
        """
        Generate detailed performance comparison report.
        
        Returns:
            Formatted performance report string
        """
        if not self.results:
            return "No benchmark results available. Run benchmarks first."
        
        report = ["# CPU vs GPU Performance Benchmark Report\n"]
        
        # Extract valid speedups for summary
        speedups = [r['speedup'] for r in self.results.values() 
                   if r['speedup'] is not None]
        
        if speedups:
            report.append("## Summary")
            report.append(f"- Average speedup: {np.mean(speedups):.2f}x")
            report.append(f"- Best speedup: {np.max(speedups):.2f}x")
            report.append(f"- Worst speedup: {np.min(speedups):.2f}x")
            report.append(f"- Benchmarks completed: {len(speedups)} / {len(self.results)}")
            report.append("")
        
        # GPU availability status in report
        gpu_status = "Available" if self.gpu_available else "Not Available"
        report.append(f"## GPU Status: {gpu_status}")
        if not self.gpu_available:
            report.append("- GPU/CuPy not detected in environment")
            report.append("- All operations ran on CPU only")
            report.append("- To enable GPU benchmarking, install CuPy and ensure CUDA is available")
        report.append("")
        
        # Detailed results
        report.append("## Detailed Results")
        for key, result in self.results.items():
            operation, size = key.rsplit('_', 1)
            report.append(f"### {operation} (Data Size: {size})")
            
            if result['cpu'].get('backend_available'):
                cpu = result['cpu']
                report.append(f"- CPU Time: {cpu['avg_time']:.4f}s ± {cpu['std_time']:.4f}s")
                if cpu.get('avg_memory', 0) > 0:
                    report.append(f"- CPU Memory: {cpu['avg_memory']:.2f} MB")
            else:
                report.append(f"- CPU: {result['cpu'].get('error', 'Failed')}")
            
            if result['gpu'].get('backend_available'):
                gpu = result['gpu']
                report.append(f"- GPU Time: {gpu['avg_time']:.4f}s ± {gpu['std_time']:.4f}s")
                if gpu.get('avg_memory', 0) > 0:
                    report.append(f"- GPU Memory: {gpu['avg_memory']:.2f} MB")
                report.append(f"- Speedup: {result['speedup']:.2f}x")
                report.append(f"- Memory Ratio: {result['memory_ratio']:.2f}x")
            else:
                report.append(f"- GPU: {result['gpu'].get('error', 'GPU/CuPy not available')}")
                report.append("- Speedup: N/A (GPU not available)")
            
            report.append("")
        
        return "\n".join(report)
    
    def prepare_visualization_data(self) -> Dict[str, Any]:
        """
        Prepare data for performance visualization.
        
        Returns:
            Dictionary with visualization data
        """
        operations = set()
        data_sizes = set()
        speedups = {}
        cpu_times = {}
        gpu_times = {}
        
        for key, result in self.results.items():
            if result['speedup'] is not None:
                operation, size = key.rsplit('_', 1)
                size = int(size)
                
                operations.add(operation)
                data_sizes.add(size)
                
                if operation not in speedups:
                    speedups[operation] = {}
                    cpu_times[operation] = {}
                    gpu_times[operation] = {}
                
                speedups[operation][size] = result['speedup']
                cpu_times[operation][size] = result['cpu']['avg_time']
                gpu_times[operation][size] = result['gpu']['avg_time']
        
        return {
            'operations': sorted(operations),
            'data_sizes': sorted(data_sizes),
            'speedups': speedups,
            'cpu_times': cpu_times,
            'gpu_times': gpu_times
        }
    
    def detect_gpu_advantage_threshold(self) -> Optional[int]:
        """
        Detect the data size threshold where GPU becomes advantageous.
        
        Returns:
            Data size threshold, or None if no clear threshold
        """
        # Group results by operation and size
        by_operation = {}
        for key, result in self.results.items():
            if result['speedup'] and result['speedup'] > 0:
                operation, size = key.rsplit('_', 1)
                size = int(size)
                
                if operation not in by_operation:
                    by_operation[operation] = {}
                by_operation[operation][size] = result['speedup']
        
        # Find minimum size where speedup > 1.0 across operations
        thresholds = []
        for operation, size_speedups in by_operation.items():
            sorted_sizes = sorted(size_speedups.keys())
            for size in sorted_sizes:
                if size_speedups[size] > 1.0:
                    thresholds.append(size)
                    break
        
        if thresholds:
            return min(thresholds)
        return None