"""
GPU Usage Module
High-performance GPU parallel processing and utilization for RTX 4080 SUPER
"""

from .gpu_hardware_detector import GPUHardwareDetector, GPUHardwareInfo, GPUBenchmarkResults
from .gpu_parallel_processor import GPUParallelProcessor, ProcessingConfig, ProcessingMode
from .gpu_performance_comparator import GPUPerformanceComparator, BenchmarkType
from .gpu_max_utilizer import RTX4080SuperMaxUtilizer

__all__ = [
    'GPUHardwareDetector',
    'GPUHardwareInfo', 
    'GPUBenchmarkResults',
    'GPUParallelProcessor',
    'ProcessingConfig',
    'ProcessingMode',
    'GPUPerformanceComparator',
    'BenchmarkType',
    'RTX4080SuperMaxUtilizer'
]