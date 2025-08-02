"""
Dynamic GPU Resource Management Implementation
Following Phase 3.2 recommendations for adaptive batch sizing and GPU utilization optimization.
"""
import cupy as cp
import pynvml
import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional, Iterator
from src.feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline


class GPUPerformanceMonitor:
    """Real-time GPU performance monitoring for dynamic resource management"""
    
    def __init__(self):
        """Initialize GPU performance monitoring"""
        pynvml.nvmlInit()
        self.gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        self.utilization_history = []
    
    def get_current_utilization(self) -> Dict[str, float]:
        """Get current GPU utilization rates"""
        util = pynvml.nvmlDeviceGetUtilizationRates(self.gpu_handle)
        mem = pynvml.nvmlDeviceGetMemoryInfo(self.gpu_handle)
        
        return {
            'core_usage': util.gpu / 100.0,
            'memory_usage': mem.used / mem.total,
            'memory_free': (mem.total - mem.used) / mem.total
        }
    
    def log_utilization(self):
        """Log current utilization for monitoring"""
        current = self.get_current_utilization()
        self.utilization_history.append(current)


class DynamicGPUBatchProcessor:
    """Automatically scales batch sizes to maintain target GPU utilization"""
    
    def __init__(self, target_memory_usage: float = 0.80, target_core_usage: float = 0.85):
        """Initialize dynamic GPU batch processor
        
        Args:
            target_memory_usage: Target GPU memory utilization (0.0-1.0)
            target_core_usage: Target GPU core utilization (0.0-1.0)
        """
        self.pipeline = UnifiedTechnicalIndicatorsPipeline()
        self.target_memory_usage = target_memory_usage
        self.target_core_usage = target_core_usage
        self.current_batch_size = 10000  # Starting batch size
        
        # Initialize GPU monitoring
        pynvml.nvmlInit()
        self.gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
    
    def calculate_optimal_batch_size(self, data_size: int) -> int:
        """Calculate batch size to achieve target GPU utilization
        
        Args:
            data_size: Total size of data to process
            
        Returns:
            Optimal batch size for target utilization
        """
        mem_info = pynvml.nvmlDeviceGetMemoryInfo(self.gpu_handle)
        available_memory = mem_info.total * self.target_memory_usage
        
        # Estimate memory per data point (empirically determined)
        memory_per_point = 42  # bytes per data point for indicators
        optimal_batch_size = int(available_memory / memory_per_point)
        
        # Ensure batch size is within reasonable bounds
        return min(max(optimal_batch_size, 1000), data_size)
    
    def process_with_dynamic_batching(self, data: pd.DataFrame) -> Dict[str, np.ndarray]:
        """Process data with automatically adjusted batch sizes
        
        Args:
            data: Input DataFrame to process
            
        Returns:
            Dictionary of computed indicators
        """
        optimal_batch_size = self.calculate_optimal_batch_size(len(data))
        
        results = []
        for i in range(0, len(data), optimal_batch_size):
            batch = data.iloc[i:i + optimal_batch_size]
            result = self.pipeline.compute_indicators(batch, ['macd', 'atr'])
            results.append(result)
            
            # Monitor and adjust if needed
            self._monitor_and_adjust()
        
        return self._combine_results(results)
    
    def create_optimal_batches(self, data: pd.DataFrame) -> List[pd.DataFrame]:
        """Create optimally sized batches from input data
        
        Args:
            data: Input DataFrame to batch
            
        Returns:
            List of optimally sized DataFrames
        """
        optimal_size = self.calculate_optimal_batch_size(len(data))
        batches = []
        
        for i in range(0, len(data), optimal_size):
            batch = data.iloc[i:i + optimal_size]
            batches.append(batch)
        
        return batches
    
    def _monitor_and_adjust(self):
        """Real-time monitoring and batch size adjustment"""
        mem = pynvml.nvmlDeviceGetMemoryInfo(self.gpu_handle)
        util = pynvml.nvmlDeviceGetUtilizationRates(self.gpu_handle)
        
        current_memory_usage = mem.used / mem.total
        current_core_usage = util.gpu / 100.0
        
        # Adjust batch size based on actual vs target utilization
        if current_memory_usage < self.target_memory_usage * 0.9:
            self.current_batch_size = int(self.current_batch_size * 1.1)
        elif current_memory_usage > self.target_memory_usage:
            self.current_batch_size = int(self.current_batch_size * 0.9)
    
    def _combine_results(self, results: List[Dict[str, np.ndarray]]) -> Dict[str, np.ndarray]:
        """Combine results from multiple batches
        
        Args:
            results: List of result dictionaries from batch processing
            
        Returns:
            Combined results dictionary
        """
        if not results:
            return {}
        
        combined = {}
        for key in results[0].keys():
            combined[key] = np.concatenate([result[key] for result in results])
        
        return combined


class ContinuousIndicatorProcessor:
    """Maintains target GPU utilization through adaptive processing"""
    
    def __init__(self, target_gpu_usage: float = 0.85):
        """Initialize continuous indicator processor
        
        Args:
            target_gpu_usage: Target GPU utilization level
        """
        self.pipeline = UnifiedTechnicalIndicatorsPipeline()
        self.batch_processor = DynamicGPUBatchProcessor(target_memory_usage=target_gpu_usage)
        self.processing_queue = []
        self.gpu_keep_alive = True
        self.target_gpu_usage = target_gpu_usage
    
    def process_streaming_data(self, data_stream: Iterator[pd.DataFrame]):
        """Process continuous data stream with adaptive batch sizing
        
        Args:
            data_stream: Iterator of DataFrame batches to process
        """
        while self.gpu_keep_alive:
            try:
                for data_batch in data_stream:
                    # Automatically scale batch to maintain GPU utilization
                    result = self.batch_processor.process_with_dynamic_batching(data_batch)
                    # No idle time, optimal resource usage
                    yield result
            except StopIteration:
                break


class AdaptiveRealTimeProcessor:
    """Real-time GPU utilization optimization for live market data feeds"""
    
    def __init__(self, target_memory_usage: float = 0.85, target_core_usage: float = 0.90):
        """Initialize adaptive real-time processor
        
        Args:
            target_memory_usage: Target GPU memory utilization
            target_core_usage: Target GPU core utilization
        """
        self.batch_processor = DynamicGPUBatchProcessor(
            target_memory_usage=target_memory_usage,
            target_core_usage=target_core_usage
        )
        self.performance_monitor = GPUPerformanceMonitor()
    
    def process_live_feed(self, market_data_stream: List[pd.DataFrame]):
        """Process live data with adaptive batch sizing for optimal GPU usage
        
        Args:
            market_data_stream: List of market data DataFrames to process
        """
        for data_chunk in market_data_stream:
            # Automatically determine optimal batch size based on current GPU state
            optimal_batches = self.batch_processor.create_optimal_batches(data_chunk)
            
            for batch in optimal_batches:
                result = self.batch_processor.process_with_dynamic_batching(batch)
                # Continuous monitoring and adjustment
                self.performance_monitor.log_utilization()
                yield result


class GPUMemoryManager:
    """Intelligent GPU memory management for consistent utilization"""
    
    def __init__(self, target_utilization: float = 0.85):
        """Initialize GPU memory manager
        
        Args:
            target_utilization: Target memory utilization level
        """
        self.target_utilization = target_utilization
        self.memory_monitor = GPUPerformanceMonitor()
        
        pynvml.nvmlInit()
        self.gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
    
    def get_available_memory(self) -> int:
        """Get currently available GPU memory in bytes"""
        mem_info = pynvml.nvmlDeviceGetMemoryInfo(self.gpu_handle)
        return int(mem_info.total * self.target_utilization)
    
    def calculate_batch_size(self, available_memory: int) -> int:
        """Calculate optimal batch size based on available memory
        
        Args:
            available_memory: Available GPU memory in bytes
            
        Returns:
            Optimal batch size
        """
        memory_per_point = 42  # Empirically determined
        return max(int(available_memory / memory_per_point), 1000)
    
    def process_in_optimal_batches(self, data: pd.DataFrame, batch_size: int) -> Dict[str, np.ndarray]:
        """Process data in optimal batches
        
        Args:
            data: Input DataFrame
            batch_size: Optimal batch size
            
        Returns:
            Processing results
        """
        pipeline = UnifiedTechnicalIndicatorsPipeline()
        results = []
        
        for i in range(0, len(data), batch_size):
            batch = data.iloc[i:i + batch_size]
            result = pipeline.compute_indicators(batch, ['macd', 'atr'])
            results.append(result)
        
        # Combine results
        if not results:
            return {}
        
        combined = {}
        for key in results[0].keys():
            combined[key] = np.concatenate([result[key] for result in results])
        
        return combined


class AdaptiveGPUProcessor:
    """Real-time GPU utilization optimization"""
    
    def __init__(self, target_utilization: float = 0.85):
        """Initialize adaptive GPU processor
        
        Args:
            target_utilization: Target GPU utilization level
        """
        self.target_utilization = target_utilization
        self.current_batch_size = 10000
        self.pipeline = UnifiedTechnicalIndicatorsPipeline()
        
        pynvml.nvmlInit()
        self.gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
    
    def get_gpu_utilization(self) -> float:
        """Get current GPU utilization"""
        util = pynvml.nvmlDeviceGetUtilizationRates(self.gpu_handle)
        return util.gpu / 100.0
    
    def increase_batch_size(self):
        """Increase batch size for higher utilization"""
        self.current_batch_size = int(self.current_batch_size * 1.1)
    
    def decrease_batch_size(self):
        """Decrease batch size to prevent overload"""
        self.current_batch_size = int(self.current_batch_size * 0.9)
    
    def process_continuous_stream(self, data_stream: Iterator[pd.DataFrame]):
        """Continuously adapt processing to maintain target GPU usage
        
        Args:
            data_stream: Continuous stream of data to process
        """
        while data_stream.has_data():
            # Monitor current GPU state
            current_utilization = self.get_gpu_utilization()
            
            # Adjust batch size based on target vs actual utilization
            if current_utilization < self.target_utilization:
                self.increase_batch_size()
            elif current_utilization > self.target_utilization:
                self.decrease_batch_size()
            
            # Process with optimized batch size
            batch = data_stream.get_next_batch(self.current_batch_size)
            result = self.pipeline.process_indicators(batch)
            yield result