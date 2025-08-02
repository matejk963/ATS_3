"""
GPU vs CPU Performance Comparison Framework
Comprehensive benchmarking and performance analysis system
"""

import logging
import time
import json
import statistics
from typing import Dict, List, Any, Optional, Tuple, Union, Callable
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

try:
    import cupy as cp
    CUPY_AVAILABLE = True
except ImportError:
    CUPY_AVAILABLE = False

from .gpu_hardware_detector import GPUHardwareDetector
from .gpu_parallel_processor import GPUParallelProcessor, ProcessingConfig, ProcessingMode


class BenchmarkType(Enum):
    """Types of benchmarks to run"""
    SORTING = "sorting"
    MATHEMATICAL = "mathematical"
    STATISTICAL = "statistical"
    SIGNAL_PROCESSING = "signal_processing"
    TECHNICAL_INDICATORS = "technical_indicators"
    MEMORY_INTENSIVE = "memory_intensive"
    COMPUTE_INTENSIVE = "compute_intensive"


@dataclass
class BenchmarkResult:
    """Single benchmark result"""
    operation: str
    data_size: int
    cpu_time: float
    gpu_time: Optional[float]
    speedup: float
    cpu_memory_mb: float
    gpu_memory_mb: Optional[float]
    validation_passed: bool
    error_message: Optional[str]


@dataclass
class BenchmarkSuite:
    """Complete benchmark suite results"""
    timestamp: str
    gpu_available: bool
    gpu_info: Dict[str, Any]
    benchmark_type: BenchmarkType
    results: List[BenchmarkResult]
    summary_stats: Dict[str, float]
    recommendations: List[str]


class GPUPerformanceComparator:
    """Comprehensive GPU vs CPU performance comparison framework"""
    
    def __init__(self, output_dir: str = "benchmark_results"):
        self.logger = logging.getLogger(__name__)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # Initialize components
        self.gpu_detector = GPUHardwareDetector()
        self.gpu_info = self.gpu_detector.detect_gpu_hardware()
        
        # Initialize processors
        self.gpu_processor = GPUParallelProcessor(ProcessingConfig(
            mode=ProcessingMode.GPU_ONLY,
            fallback_to_cpu=False
        ))
        self.cpu_processor = GPUParallelProcessor(ProcessingConfig(
            mode=ProcessingMode.CPU_ONLY
        ))
        
        # Benchmark configurations
        self.default_data_sizes = [1000, 5000, 10000, 50000, 100000, 500000, 1000000]
        self.warmup_iterations = 3
        self.benchmark_iterations = 5
        
    def run_comprehensive_benchmark(self) -> Dict[BenchmarkType, BenchmarkSuite]:
        """Run comprehensive benchmark across all operation types"""
        self.logger.info("Starting comprehensive GPU vs CPU benchmark")
        
        results = {}
        
        for benchmark_type in BenchmarkType:
            self.logger.info(f"Running {benchmark_type.value} benchmarks")
            suite = self.run_benchmark_suite(benchmark_type)
            results[benchmark_type] = suite
            
            # Save individual suite results
            self._save_benchmark_suite(suite, benchmark_type.value)
        
        # Generate comparative analysis
        self._generate_comparative_report(results)
        
        return results
    
    def run_benchmark_suite(self, benchmark_type: BenchmarkType) -> BenchmarkSuite:
        """Run a specific benchmark suite"""
        operations = self._get_operations_for_type(benchmark_type)
        results = []
        
        for operation in operations:
            self.logger.info(f"Benchmarking {operation}")
            
            for data_size in self.default_data_sizes:
                result = self._benchmark_operation(operation, data_size)
                results.append(result)
                
                # Log progress
                speedup_str = f"{result.speedup:.2f}x" if result.gpu_time else "N/A" 
                self.logger.info(f"  Size {data_size:,}: {speedup_str} speedup")
        
        # Calculate summary statistics
        summary_stats = self._calculate_summary_stats(results)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(results, benchmark_type)
        
        return BenchmarkSuite(
            timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
            gpu_available=self.gpu_info.gpu_available,
            gpu_info=self._get_gpu_info_dict(),
            benchmark_type=benchmark_type,
            results=results,
            summary_stats=summary_stats,
            recommendations=recommendations
        )
    
    def _get_operations_for_type(self, benchmark_type: BenchmarkType) -> List[str]:
        """Get operations to benchmark for a specific type"""
        operations_map = {
            BenchmarkType.SORTING: ['sort'],
            BenchmarkType.MATHEMATICAL: ['sum', 'mean', 'sqrt', 'square', 'log', 'exp'],
            BenchmarkType.STATISTICAL: ['std', 'var', 'min', 'max', 'median'],
            BenchmarkType.SIGNAL_PROCESSING: ['fft', 'cumsum', 'diff'],
            BenchmarkType.TECHNICAL_INDICATORS: ['rolling_mean', 'rolling_std'],
            BenchmarkType.MEMORY_INTENSIVE: ['sort', 'cumsum'],
            BenchmarkType.COMPUTE_INTENSIVE: ['sqrt', 'log', 'exp', 'sin', 'cos']
        }
        
        return operations_map.get(benchmark_type, ['sum', 'mean'])
    
    def _benchmark_operation(self, operation: str, data_size: int) -> BenchmarkResult:
        """Benchmark a single operation"""
        # Generate test data
        test_data = self._generate_test_data(data_size, operation)
        
        # CPU benchmark
        cpu_times = []
        cpu_memory = 0
        cpu_result = None
        
        for i in range(self.warmup_iterations + self.benchmark_iterations):
            start_time = time.perf_counter()
            
            try:
                result = self.cpu_processor.process_array(test_data, operation, 
                                                        **self._get_operation_kwargs(operation))
                cpu_result = result
                
            except Exception as e:
                return BenchmarkResult(
                    operation=operation,
                    data_size=data_size,
                    cpu_time=0,
                    gpu_time=None,
                    speedup=0,
                    cpu_memory_mb=0,
                    gpu_memory_mb=None,
                    validation_passed=False,
                    error_message=f"CPU error: {str(e)}"
                )
            
            elapsed = time.perf_counter() - start_time
            
            # Skip warmup iterations
            if i >= self.warmup_iterations:
                cpu_times.append(elapsed)
        
        cpu_time = statistics.mean(cpu_times)
        cpu_memory = self._estimate_memory_usage(test_data, cpu_result)
        
        # GPU benchmark
        gpu_times = []
        gpu_memory = None
        gpu_result = None
        gpu_time = None
        speedup = 1.0
        validation_passed = True
        error_message = None
        
        if self.gpu_info.gpu_available and CUPY_AVAILABLE:
            try:
                for i in range(self.warmup_iterations + self.benchmark_iterations):
                    start_time = time.perf_counter()
                    
                    result = self.gpu_processor.process_array(test_data, operation,
                                                            **self._get_operation_kwargs(operation))
                    gpu_result = result
                    
                    elapsed = time.perf_counter() - start_time
                    
                    # Skip warmup iterations
                    if i >= self.warmup_iterations:
                        gpu_times.append(elapsed)
                
                gpu_time = statistics.mean(gpu_times)
                gpu_memory = self._estimate_memory_usage(test_data, gpu_result)
                speedup = cpu_time / gpu_time if gpu_time > 0 else 1.0
                
                # Validate results match
                validation_passed = self._validate_results(cpu_result, gpu_result, operation)
                
            except Exception as e:
                error_message = f"GPU error: {str(e)}"
                validation_passed = False
        
        return BenchmarkResult(
            operation=operation,
            data_size=data_size,
            cpu_time=cpu_time,
            gpu_time=gpu_time,
            speedup=speedup,
            cpu_memory_mb=cpu_memory,
            gpu_memory_mb=gpu_memory,
            validation_passed=validation_passed,
            error_message=error_message
        )
    
    def _generate_test_data(self, size: int, operation: str) -> np.ndarray:
        """Generate appropriate test data for operation"""
        np.random.seed(42)  # Consistent results
        
        if operation in ['log']:
            # Positive values for logarithm
            return np.random.uniform(0.1, 100.0, size).astype(np.float32)
        elif operation in ['sqrt']:
            # Non-negative values for square root
            return np.random.uniform(0.0, 100.0, size).astype(np.float32)
        elif operation in ['sin', 'cos', 'tan']:
            # Reasonable range for trigonometric functions
            return np.random.uniform(-np.pi, np.pi, size).astype(np.float32)
        elif operation in ['fft']:
            # Complex signal for FFT
            t = np.linspace(0, 1, size, endpoint=False).astype(np.float32)
            return np.sin(2 * np.pi * 5 * t) + 0.5 * np.sin(2 * np.pi * 10 * t)
        else:
            # General random data
            return np.random.uniform(-100.0, 100.0, size).astype(np.float32)
    
    def _get_operation_kwargs(self, operation: str) -> Dict[str, Any]:
        """Get operation-specific keyword arguments"""
        kwargs_map = {
            'rolling_mean': {'window': 20},
            'rolling_std': {'window': 20},
            'fft': {}
        }
        
        return kwargs_map.get(operation, {})
    
    def _estimate_memory_usage(self, input_data: np.ndarray, output_data: Any) -> float:
        """Estimate memory usage in MB"""
        input_mb = input_data.nbytes / (1024 * 1024)
        
        if hasattr(output_data, 'nbytes'):
            output_mb = output_data.nbytes / (1024 * 1024)
        elif isinstance(output_data, (int, float)):
            output_mb = 0.001  # Negligible for scalar
        else:
            output_mb = input_mb  # Estimate same as input
        
        return input_mb + output_mb
    
    def _validate_results(self, cpu_result: Any, gpu_result: Any, operation: str) -> bool:
        """Validate that CPU and GPU results match"""
        try:
            # Handle scalar results
            if isinstance(cpu_result, (int, float, np.number)):
                if isinstance(gpu_result, (int, float, np.number)):
                    return abs(float(cpu_result) - float(gpu_result)) < 1e-4
                else:
                    return False
            
            # Handle array results
            if hasattr(cpu_result, 'shape') and hasattr(gpu_result, 'shape'):
                if cpu_result.shape != gpu_result.shape:
                    return False
                
                # Convert to numpy arrays
                cpu_array = np.asarray(cpu_result)
                gpu_array = np.asarray(gpu_result)
                
                # Check for complex numbers (FFT results)
                if np.iscomplexobj(cpu_array) or np.iscomplexobj(gpu_array):
                    cpu_array = np.abs(cpu_array)
                    gpu_array = np.abs(gpu_array)
                
                # Handle NaN values
                if np.any(np.isnan(cpu_array)) or np.any(np.isnan(gpu_array)):
                    # Check if NaN patterns match
                    nan_match = np.array_equal(np.isnan(cpu_array), np.isnan(gpu_array))
                    if not nan_match:
                        return False
                    
                    # Compare non-NaN values
                    valid_mask = ~np.isnan(cpu_array)
                    if np.any(valid_mask):
                        max_diff = np.max(np.abs(cpu_array[valid_mask] - gpu_array[valid_mask]))
                        return max_diff < 1e-3
                    else:
                        return True  # All NaN
                else:
                    # Compare all values
                    max_diff = np.max(np.abs(cpu_array - gpu_array))
                    return max_diff < 1e-3
            
            return False
            
        except Exception as e:
            self.logger.warning(f"Result validation failed for {operation}: {e}")
            return False
    
    def _calculate_summary_stats(self, results: List[BenchmarkResult]) -> Dict[str, float]:
        """Calculate summary statistics from benchmark results"""
        successful_results = [r for r in results if r.validation_passed and r.gpu_time is not None]
        
        if not successful_results:
            return {
                'avg_speedup': 1.0,
                'max_speedup': 1.0,
                'min_speedup': 1.0,
                'median_speedup': 1.0,
                'success_rate': 0.0,
                'total_tests': len(results)
            }
        
        speedups = [r.speedup for r in successful_results]
        
        return {
            'avg_speedup': statistics.mean(speedups),
            'max_speedup': max(speedups),
            'min_speedup': min(speedups),
            'median_speedup': statistics.median(speedups),
            'success_rate': len(successful_results) / len(results) * 100,
            'total_tests': len(results)
        }
    
    def _generate_recommendations(self, results: List[BenchmarkResult], 
                                benchmark_type: BenchmarkType) -> List[str]:
        """Generate performance recommendations"""
        recommendations = []
        
        if not self.gpu_info.gpu_available:
            recommendations.append("GPU not available - consider installing CUDA and CuPy for acceleration")
            return recommendations
        
        successful_results = [r for r in results if r.validation_passed and r.gpu_time is not None]
        
        if not successful_results:
            recommendations.append("No successful GPU operations - check GPU drivers and CUDA installation")
            return recommendations
        
        # Analyze speedup patterns
        speedups = [r.speedup for r in successful_results]
        avg_speedup = statistics.mean(speedups)
        max_speedup = max(speedups)
        
        if avg_speedup < 1.5:
            recommendations.append("GPU shows minimal speedup - data sizes may be too small for GPU efficiency")
        elif avg_speedup < 3.0:
            recommendations.append("Moderate GPU speedup observed - consider larger batch sizes")
        elif avg_speedup < 10.0:
            recommendations.append("Good GPU speedup achieved - optimal for most workloads")
        else:
            recommendations.append("Excellent GPU speedup - highly suitable for parallel processing")
        
        # Analyze by data size
        large_data_results = [r for r in successful_results if r.data_size >= 100000]
        small_data_results = [r for r in successful_results if r.data_size < 10000]
        
        if large_data_results:
            large_speedup = statistics.mean([r.speedup for r in large_data_results])
            if large_speedup > avg_speedup * 1.5:
                recommendations.append("GPU performance improves significantly with larger datasets")
        
        if small_data_results:
            small_speedup = statistics.mean([r.speedup for r in small_data_results])
            if small_speedup < 1.2:
                recommendations.append("Avoid GPU for small datasets due to overhead")
        
        # Operation-specific recommendations
        op_speedups = {}
        for result in successful_results:
            if result.operation not in op_speedups:
                op_speedups[result.operation] = []
            op_speedups[result.operation].append(result.speedup)
        
        best_ops = []
        worst_ops = []
        
        for op, speeds in op_speedups.items():
            avg_speed = statistics.mean(speeds)
            if avg_speed > avg_speedup * 1.5:
                best_ops.append((op, avg_speed))
            elif avg_speed < avg_speedup * 0.7:
                worst_ops.append((op, avg_speed))
        
        if best_ops:
            best_ops.sort(key=lambda x: x[1], reverse=True)
            op_names = [op[0] for op in best_ops[:3]]
            recommendations.append(f"Best GPU operations: {', '.join(op_names)}")
        
        if worst_ops:
            worst_ops.sort(key=lambda x: x[1])
            op_names = [op[0] for op in worst_ops[:3]]
            recommendations.append(f"Consider CPU for: {', '.join(op_names)}")
        
        return recommendations
    
    def _get_gpu_info_dict(self) -> Dict[str, Any]:
        """Get GPU information as dictionary"""
        return {
            'gpu_available': self.gpu_info.gpu_available,
            'gpu_count': self.gpu_info.gpu_count,
            'gpu_names': self.gpu_info.gpu_names,
            'total_memory': self.gpu_info.total_memory,
            'compute_capability': self.gpu_info.compute_capability,
            'capability_level': self.gpu_info.capability_level.value,
            'recommended_chunk_size': self.gpu_info.recommended_chunk_size
        }
    
    def _save_benchmark_suite(self, suite: BenchmarkSuite, name: str) -> None:
        """Save benchmark suite results to file"""
        filename = f"benchmark_{name}_{int(time.time())}.json"
        filepath = self.output_dir / filename
        
        # Convert to dictionary for JSON serialization
        suite_dict = asdict(suite)
        
        # Handle enum conversion
        suite_dict['benchmark_type'] = suite.benchmark_type.value
        
        with open(filepath, 'w') as f:
            json.dump(suite_dict, f, indent=2)
        
        self.logger.info(f"Benchmark results saved to {filepath}")
    
    def _generate_comparative_report(self, results: Dict[BenchmarkType, BenchmarkSuite]) -> None:
        """Generate comprehensive comparative analysis report"""
        report_path = self.output_dir / f"comparative_report_{int(time.time())}.md"
        
        with open(report_path, 'w') as f:
            f.write("# GPU vs CPU Performance Comparison Report\n\n")
            f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            # System information
            f.write("## System Information\n\n")
            if self.gpu_info.gpu_available:
                f.write(f"**GPU Available**: Yes\n")
                f.write(f"**GPU Count**: {self.gpu_info.gpu_count}\n")
                for i, name in enumerate(self.gpu_info.gpu_names):
                    f.write(f"**GPU {i}**: {name}\n")
                    if i < len(self.gpu_info.total_memory):
                        f.write(f"  - Memory: {self.gpu_info.total_memory[i]:,} MB\n")
                    if i < len(self.gpu_info.compute_capability):
                        major, minor = self.gpu_info.compute_capability[i]
                        f.write(f"  - Compute Capability: {major}.{minor}\n")
                f.write(f"**Capability Level**: {self.gpu_info.capability_level.value.upper()}\n")
            else:
                f.write("**GPU Available**: No\n")
            
            f.write("\n")
            
            # Summary statistics
            f.write("## Summary Statistics\n\n")
            f.write("| Benchmark Type | Avg Speedup | Max Speedup | Success Rate | Total Tests |\n")
            f.write("|---------------|-------------|-------------|--------------|-------------|\n")
            
            for benchmark_type, suite in results.items():
                stats = suite.summary_stats
                f.write(f"| {benchmark_type.value.title()} | "
                       f"{stats['avg_speedup']:.2f}x | "
                       f"{stats['max_speedup']:.2f}x | "
                       f"{stats['success_rate']:.1f}% | "
                       f"{int(stats['total_tests'])} |\n")
            
            f.write("\n")
            
            # Detailed results by benchmark type
            for benchmark_type, suite in results.items():
                f.write(f"## {benchmark_type.value.title()} Benchmarks\n\n")
                
                # Best performing operations
                successful_results = [r for r in suite.results 
                                    if r.validation_passed and r.gpu_time is not None]
                
                if successful_results:
                    # Group by operation
                    op_results = {}
                    for result in successful_results:
                        if result.operation not in op_results:
                            op_results[result.operation] = []
                        op_results[result.operation].append(result)
                    
                    f.write("### Performance by Operation\n\n")
                    f.write("| Operation | Avg Speedup | Best Size | Max Speedup |\n")
                    f.write("|-----------|-------------|-----------|-------------|\n")
                    
                    for operation, op_results_list in op_results.items():
                        speedups = [r.speedup for r in op_results_list]
                        avg_speedup = statistics.mean(speedups)
                        max_result = max(op_results_list, key=lambda x: x.speedup)
                        
                        f.write(f"| {operation} | {avg_speedup:.2f}x | "
                               f"{max_result.data_size:,} | {max_result.speedup:.2f}x |\n")
                    
                    f.write("\n")
                
                # Recommendations
                if suite.recommendations:
                    f.write("### Recommendations\n\n")
                    for rec in suite.recommendations:
                        f.write(f"- {rec}\n")
                    f.write("\n")
            
            # Overall conclusions
            f.write("## Conclusions\n\n")
            
            all_successful = []
            for suite in results.values():
                all_successful.extend([r for r in suite.results 
                                     if r.validation_passed and r.gpu_time is not None])
            
            if all_successful:
                overall_speedup = statistics.mean([r.speedup for r in all_successful])
                max_speedup = max([r.speedup for r in all_successful])
                
                f.write(f"- **Overall Average Speedup**: {overall_speedup:.2f}x\n")
                f.write(f"- **Maximum Speedup Achieved**: {max_speedup:.2f}x\n")
                
                success_rate = len(all_successful) / sum(len(s.results) for s in results.values()) * 100
                f.write(f"- **Overall Success Rate**: {success_rate:.1f}%\n")
                
                if overall_speedup > 5:
                    f.write("- **Recommendation**: GPU acceleration highly beneficial for this workload\n")
                elif overall_speedup > 2:
                    f.write("- **Recommendation**: GPU acceleration provides moderate benefits\n")
                else:
                    f.write("- **Recommendation**: Consider workload characteristics before using GPU\n")
            else:
                f.write("- No successful GPU operations completed\n")
                f.write("- Consider checking GPU drivers and CUDA installation\n")
        
        self.logger.info(f"Comparative report saved to {report_path}")
    
    def plot_performance_comparison(self, suite: BenchmarkSuite, save_path: Optional[str] = None) -> None:
        """Generate performance comparison plots"""
        if not suite.results:
            self.logger.warning("No results to plot")
            return
        
        # Group results by operation
        op_results = {}
        for result in suite.results:
            if result.validation_passed and result.gpu_time is not None:
                if result.operation not in op_results:
                    op_results[result.operation] = {'sizes': [], 'speedups': []}
                op_results[result.operation]['sizes'].append(result.data_size)
                op_results[result.operation]['speedups'].append(result.speedup)
        
        if not op_results:
            self.logger.warning("No successful results to plot")
            return
        
        # Create subplot for each operation
        fig, axes = plt.subplots(len(op_results), 1, figsize=(12, 4 * len(op_results)))
        if len(op_results) == 1:
            axes = [axes]
        
        for i, (operation, data) in enumerate(op_results.items()):
            ax = axes[i]
            ax.semilogx(data['sizes'], data['speedups'], 'bo-', linewidth=2, markersize=6)
            ax.set_xlabel('Data Size')
            ax.set_ylabel('Speedup (x)')
            ax.set_title(f'{operation.title()} - GPU vs CPU Speedup')
            ax.grid(True, alpha=0.3)
            ax.axhline(y=1, color='r', linestyle='--', alpha=0.7, label='No speedup')
            ax.legend()
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            self.logger.info(f"Performance plot saved to {save_path}")
        else:
            plot_path = self.output_dir / f"performance_plot_{suite.benchmark_type.value}_{int(time.time())}.png"
            plt.savefig(plot_path, dpi=300, bbox_inches='tight')
            self.logger.info(f"Performance plot saved to {plot_path}")
        
        plt.close()
    
    def quick_benchmark(self, operations: List[str] = None, 
                       data_sizes: List[int] = None) -> BenchmarkSuite:
        """Run a quick benchmark with specified operations and sizes"""
        if operations is None:
            operations = ['sort', 'sum', 'mean', 'std']
        
        if data_sizes is None:
            data_sizes = [10000, 100000, 500000]
        
        self.logger.info(f"Running quick benchmark with {len(operations)} operations")
        
        results = []
        for operation in operations:
            for data_size in data_sizes:
                result = self._benchmark_operation(operation, data_size)
                results.append(result)
        
        summary_stats = self._calculate_summary_stats(results)
        recommendations = self._generate_recommendations(results, BenchmarkType.MATHEMATICAL)
        
        return BenchmarkSuite(
            timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
            gpu_available=self.gpu_info.gpu_available,
            gpu_info=self._get_gpu_info_dict(),
            benchmark_type=BenchmarkType.MATHEMATICAL,
            results=results,
            summary_stats=summary_stats,
            recommendations=recommendations
        )


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Create comparator
    comparator = GPUPerformanceComparator()
    
    # Run quick benchmark
    print("Running quick benchmark...")
    quick_results = comparator.quick_benchmark()
    
    print(f"\nQuick Benchmark Results:")
    print(f"Average Speedup: {quick_results.summary_stats['avg_speedup']:.2f}x")
    print(f"Max Speedup: {quick_results.summary_stats['max_speedup']:.2f}x")
    print(f"Success Rate: {quick_results.summary_stats['success_rate']:.1f}%")
    
    print("\nRecommendations:")
    for rec in quick_results.recommendations:
        print(f"- {rec}")
    
    # Plot results
    comparator.plot_performance_comparison(quick_results)
    
    # Optionally run comprehensive benchmark
    print("\nTo run comprehensive benchmark, uncomment the following lines:")
    print("# comprehensive_results = comparator.run_comprehensive_benchmark()")
    
    # comprehensive_results = comparator.run_comprehensive_benchmark()
    # print("Comprehensive benchmark complete!")