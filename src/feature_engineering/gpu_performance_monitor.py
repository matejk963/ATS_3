"""
GPU Performance Monitoring and Validation Tools
Implementation of comprehensive GPU utilization analysis and optimization validation.
"""
import pynvml
import numpy as np
import pandas as pd
import time
import threading
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from src.feature_engineering.dynamic_gpu_processor import DynamicGPUBatchProcessor


@dataclass
class PerformanceThresholds:
    """Performance thresholds for GPU validation"""
    min_points_per_second: float = 1500.0
    min_gpu_utilization: float = 80.0
    min_memory_efficiency: float = 60.0
    max_processing_time: float = 40.0  # seconds for 50K points


class GPUUtilizationMonitor:
    """Real-time GPU utilization monitoring for dynamic resource management"""
    
    def __init__(self):
        """Initialize GPU utilization monitor"""
        pynvml.nvmlInit()
        self.gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        self.monitoring_active = False
        self.utilization_history = []
        self._monitoring_thread = None
    
    def get_real_time_stats(self) -> Dict[str, float]:
        """Get current GPU utilization statistics
        
        Returns:
            Dictionary containing current GPU utilization metrics
        """
        util = pynvml.nvmlDeviceGetUtilizationRates(self.gpu_handle)
        mem = pynvml.nvmlDeviceGetMemoryInfo(self.gpu_handle)
        
        return {
            'core_utilization': float(util.gpu),
            'memory_utilization': float(util.memory),
            'memory_usage_percent': (mem.used / mem.total) * 100.0,
            'memory_used_gb': mem.used / (1024**3),
            'memory_free_gb': (mem.total - mem.used) / (1024**3),
            'memory_total_gb': mem.total / (1024**3),
            'timestamp': time.time()
        }
    
    def start_monitoring(self, interval: float = 1.0):
        """Start continuous GPU monitoring in background thread
        
        Args:
            interval: Monitoring interval in seconds
        """
        if self.monitoring_active:
            return
        
        self.monitoring_active = True
        self._monitoring_thread = threading.Thread(
            target=self._monitor_loop,
            args=(interval,),
            daemon=True
        )
        self._monitoring_thread.start()
    
    def stop_monitoring(self):
        """Stop continuous GPU monitoring"""
        self.monitoring_active = False
        if self._monitoring_thread:
            self._monitoring_thread.join(timeout=2.0)
    
    def _monitor_loop(self, interval: float):
        """Background monitoring loop"""
        while self.monitoring_active:
            try:
                stats = self.get_real_time_stats()
                self.utilization_history.append(stats)
                time.sleep(interval)
            except Exception as e:
                print(f"Monitoring error: {e}")
                break
    
    def calculate_average_utilization(self, window_seconds: Optional[float] = None) -> Dict[str, float]:
        """Calculate average utilization over specified time window
        
        Args:
            window_seconds: Time window for calculation (None for all data)
            
        Returns:
            Dictionary containing average utilization statistics
        """
        if not self.utilization_history:
            return {}
        
        data = self.utilization_history
        if window_seconds:
            cutoff_time = time.time() - window_seconds
            data = [d for d in data if d['timestamp'] >= cutoff_time]
        
        if not data:
            return {}
        
        core_utils = [d['core_utilization'] for d in data]
        memory_utils = [d['memory_utilization'] for d in data]
        
        return {
            'avg_core_utilization': np.mean(core_utils),
            'avg_memory_utilization': np.mean(memory_utils),
            'peak_core_utilization': np.max(core_utils),
            'peak_memory_utilization': np.max(memory_utils),
            'min_core_utilization': np.min(core_utils),
            'min_memory_utilization': np.min(memory_utils),
            'samples_count': len(data)
        }
    
    def clear_history(self):
        """Clear utilization history"""
        self.utilization_history = []


class GPUBenchmarkValidator:
    """GPU benchmark validation and performance assessment"""
    
    def __init__(self):
        """Initialize GPU benchmark validator"""
        self.benchmark_results = []
        self.performance_thresholds = PerformanceThresholds()
    
    def run_processing_benchmark(self, processor: DynamicGPUBatchProcessor, 
                               monitor: GPUUtilizationMonitor,
                               test_data: pd.DataFrame,
                               target_utilization: float = 0.85) -> Dict[str, Any]:
        """Run comprehensive GPU processing benchmark
        
        Args:
            processor: DynamicGPUBatchProcessor instance
            monitor: GPUUtilizationMonitor instance  
            test_data: Test data for benchmarking
            target_utilization: Target GPU utilization
            
        Returns:
            Benchmark results dictionary
        """
        # Clear previous monitoring data
        monitor.clear_history()
        
        # Start monitoring
        monitor.start_monitoring(interval=0.5)
        
        # Record start time
        start_time = time.time()
        
        # Run processing benchmark
        try:
            results = processor.process_with_dynamic_batching(test_data)
            processing_time = time.time() - start_time
            
            # Allow time for final monitoring samples
            time.sleep(1.0)
            
        finally:
            # Stop monitoring
            monitor.stop_monitoring()
        
        # Calculate performance metrics
        points_per_second = len(test_data) / processing_time if processing_time > 0 else 0
        
        # Get utilization statistics
        util_stats = monitor.calculate_average_utilization()
        current_stats = monitor.get_real_time_stats()
        
        benchmark = {
            'data_points': len(test_data),
            'processing_time': processing_time,
            'points_per_second': points_per_second,
            'avg_gpu_utilization': util_stats.get('avg_core_utilization', current_stats['core_utilization']),
            'peak_gpu_utilization': util_stats.get('peak_core_utilization', current_stats['core_utilization']),
            'avg_memory_utilization': util_stats.get('avg_memory_utilization', current_stats['memory_utilization']),
            'target_utilization': target_utilization * 100,
            'target_achieved': util_stats.get('avg_core_utilization', 0) >= (target_utilization * 100 * 0.9),
            'timestamp': time.time()
        }
        
        self.benchmark_results.append(benchmark)
        return benchmark
    
    def validate_performance(self, benchmark: Dict[str, Any]) -> Dict[str, Any]:
        """Validate benchmark performance against thresholds
        
        Args:
            benchmark: Benchmark results dictionary
            
        Returns:
            Validation results with recommendations
        """
        thresholds = self.performance_thresholds
        
        # Performance checks
        meets_speed_target = benchmark['points_per_second'] >= thresholds.min_points_per_second
        meets_utilization_target = benchmark['avg_gpu_utilization'] >= thresholds.min_gpu_utilization
        meets_time_target = benchmark['processing_time'] <= thresholds.max_processing_time
        
        # Overall performance rating
        if meets_speed_target and meets_utilization_target and meets_time_target:
            overall_performance = 'EXCELLENT'
        elif meets_speed_target or meets_utilization_target:
            overall_performance = 'GOOD'
        else:
            overall_performance = 'NEEDS_OPTIMIZATION'
        
        # Generate recommendations
        recommendations = []
        if not meets_speed_target:
            recommendations.append('Increase batch size or optimize memory access patterns')
        if not meets_utilization_target:
            recommendations.append('Consider dynamic batch sizing to maintain higher GPU utilization')
        if not meets_time_target:
            recommendations.append('Optimize processing pipeline for faster execution')
        if benchmark['avg_gpu_utilization'] < 50:
            recommendations.append('GPU utilization is very low - check for CPU bottlenecks')
        
        return {
            'meets_speed_target': meets_speed_target,
            'meets_utilization_target': meets_utilization_target,
            'meets_time_target': meets_time_target,
            'overall_performance': overall_performance,
            'performance_score': self._calculate_performance_score(benchmark),
            'recommendations': recommendations,
            'thresholds_used': {
                'min_points_per_second': thresholds.min_points_per_second,
                'min_gpu_utilization': thresholds.min_gpu_utilization,
                'max_processing_time': thresholds.max_processing_time
            }
        }
    
    def _calculate_performance_score(self, benchmark: Dict[str, Any]) -> float:
        """Calculate overall performance score (0-100)
        
        Args:
            benchmark: Benchmark results
            
        Returns:
            Performance score out of 100
        """
        speed_score = min(100, (benchmark['points_per_second'] / self.performance_thresholds.min_points_per_second) * 40)
        util_score = min(40, (benchmark['avg_gpu_utilization'] / self.performance_thresholds.min_gpu_utilization) * 40)
        time_score = min(20, (self.performance_thresholds.max_processing_time / benchmark['processing_time']) * 20)
        
        return speed_score + util_score + time_score


class DynamicGPUDiagnostics:
    """Comprehensive GPU diagnostics and optimization reporting"""
    
    def __init__(self):
        """Initialize GPU diagnostics tool"""
        self.monitor = GPUUtilizationMonitor()
        self.validator = GPUBenchmarkValidator()
        self.diagnostic_reports = []
    
    def run_comprehensive_analysis(self, processor: DynamicGPUBatchProcessor,
                                 test_data: pd.DataFrame,
                                 target_utilization: float = 0.85,
                                 duration_seconds: float = 10.0) -> Dict[str, Any]:
        """Run comprehensive GPU analysis and diagnostics
        
        Args:
            processor: DynamicGPUBatchProcessor instance
            test_data: Test data for analysis
            target_utilization: Target GPU utilization
            duration_seconds: Analysis duration
            
        Returns:
            Comprehensive analysis results
        """
        analysis = {
            'analysis_timestamp': time.time(),
            'target_utilization': target_utilization,
            'analysis_duration': duration_seconds
        }
        
        # Hardware information
        try:
            gpu_info = pynvml.nvmlDeviceGetMemoryInfo(self.monitor.gpu_handle)
            device_name = pynvml.nvmlDeviceGetName(self.monitor.gpu_handle)
            
            analysis['hardware_info'] = {
                'device_name': device_name.decode() if isinstance(device_name, bytes) else str(device_name),
                'total_memory_gb': gpu_info.total / (1024**3),
                'available_memory_gb': (gpu_info.total - gpu_info.used) / (1024**3)
            }
        except Exception as e:
            analysis['hardware_info'] = {'error': str(e)}
        
        # Performance benchmark
        benchmark = self.validator.run_processing_benchmark(
            processor=processor,
            monitor=self.monitor,
            test_data=test_data,
            target_utilization=target_utilization
        )
        analysis['performance_benchmark'] = benchmark
        
        # Validation results
        validation = self.validator.validate_performance(benchmark)
        analysis['validation_results'] = validation
        
        # Utilization analysis
        util_analysis = self.monitor.calculate_average_utilization()
        analysis['utilization_analysis'] = util_analysis
        
        # Recommendations
        analysis['recommendations'] = validation['recommendations']
        
        self.diagnostic_reports.append(analysis)
        return analysis
    
    def generate_optimization_report(self, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate detailed optimization report
        
        Args:
            analysis_data: Comprehensive analysis results
            
        Returns:
            Optimization report with recommendations
        """
        benchmark = analysis_data['performance_benchmark']
        validation = analysis_data['validation_results']
        
        # Performance summary
        performance_summary = {
            'points_per_second': benchmark['points_per_second'],
            'processing_time': benchmark['processing_time'],
            'gpu_utilization': benchmark['avg_gpu_utilization'],
            'performance_rating': validation['overall_performance'],
            'performance_score': validation['performance_score']
        }
        
        # Optimization opportunities
        optimization_opportunities = []
        
        if benchmark['avg_gpu_utilization'] < 70:
            optimization_opportunities.append({
                'area': 'GPU Utilization',
                'current': f"{benchmark['avg_gpu_utilization']:.1f}%",
                'target': '85%+',
                'recommendation': 'Implement dynamic batch sizing for sustained GPU load'
            })
        
        if benchmark['points_per_second'] < 1500:
            optimization_opportunities.append({
                'area': 'Processing Speed',
                'current': f"{benchmark['points_per_second']:.0f} pts/sec",
                'target': '1500+ pts/sec',
                'recommendation': 'Optimize memory access patterns and increase batch sizes'
            })
        
        # Recommended settings
        recommended_settings = {
            'target_memory_usage': 0.85 if benchmark['avg_gpu_utilization'] < 80 else 0.90,
            'target_core_usage': 0.90,
            'recommended_batch_size': 'Dynamic based on GPU memory',
            'monitoring_interval': 0.5,
            'optimization_priority': 'GPU Utilization' if benchmark['avg_gpu_utilization'] < 70 else 'Performance Tuning'
        }
        
        return {
            'performance_summary': performance_summary,
            'optimization_opportunities': optimization_opportunities,
            'recommended_settings': recommended_settings,
            'performance_rating': validation['overall_performance'],
            'next_steps': validation['recommendations']
        }