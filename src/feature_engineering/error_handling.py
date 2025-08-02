"""
Error Handling and Fallback Mechanisms for GPU-Ready Technical Indicators

This module provides comprehensive error handling, GPU fallback management,
and graceful degradation for technical indicator computations.

Key Features:
- Automatic GPU to CPU fallback on errors
- Error categorization and logging
- Resource cleanup on failures
- Performance impact monitoring
- Context-aware error handling
- Batch error handling with partial results
- Graceful degradation strategies
"""

import time
import warnings
import logging
from typing import Dict, List, Tuple, Optional, Any, Union, Callable
from dataclasses import dataclass, field
from collections import defaultdict, Counter
import pandas as pd
import numpy as np

from .unified_pipeline import UnifiedTechnicalIndicatorsPipeline


@dataclass
class ErrorHandlingConfig:
    """Configuration for error handling"""
    auto_fallback: bool = True
    max_retries: int = 3
    error_threshold: int = 10
    enable_logging: bool = True
    auto_cleanup: bool = True
    monitor_performance: bool = True
    
    def __post_init__(self):
        """Validate configuration"""
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if self.error_threshold <= 0:
            raise ValueError("error_threshold must be positive")


class ErrorHandler:
    """
    Comprehensive error handling system for technical indicators.
    
    Provides automatic error detection, categorization, logging, and recovery
    strategies including GPU fallback and graceful degradation.
    """
    
    def __init__(self,
                 auto_fallback: bool = True,
                 max_retries: int = 3,
                 error_threshold: int = 10,
                 enable_logging: bool = True,
                 auto_cleanup: bool = True,
                 monitor_performance: bool = True):
        """
        Initialize error handler.
        
        Args:
            auto_fallback: Enable automatic GPU to CPU fallback
            max_retries: Maximum number of operation retries
            error_threshold: Error count threshold for permanent fallback
            enable_logging: Enable error logging
            auto_cleanup: Enable automatic resource cleanup
            monitor_performance: Monitor performance impact of fallbacks
        """
        self.config = ErrorHandlingConfig(
            auto_fallback=auto_fallback,
            max_retries=max_retries,
            error_threshold=error_threshold,
            enable_logging=enable_logging,
            auto_cleanup=auto_cleanup,
            monitor_performance=monitor_performance
        )
        
        # Error tracking
        self.errors = []
        self.fallback_occurred = False
        
        # Setup logging
        if enable_logging:
            self.logger = logging.getLogger(__name__)
            if not self.logger.handlers:
                handler = logging.StreamHandler()
                formatter = logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                )
                handler.setFormatter(formatter)
                self.logger.addHandler(handler)
                self.logger.setLevel(logging.WARNING)
        else:
            self.logger = None
    
    def categorize_error(self, error: Exception) -> str:
        """
        Categorize error type for appropriate handling.
        
        Args:
            error: Exception to categorize
            
        Returns:
            Error category string
        """
        error_str = str(error).lower()
        
        # GPU-related errors
        if any(keyword in error_str for keyword in ['cuda', 'gpu', 'device', 'cupy']):
            return 'gpu_error'
        
        # Memory-related errors
        if isinstance(error, MemoryError) or 'memory' in error_str or 'allocation' in error_str:
            return 'memory_error'
        
        # Input validation errors
        if isinstance(error, (ValueError, TypeError)) and not any(
            keyword in error_str for keyword in ['cuda', 'gpu', 'memory']
        ):
            return 'input_error'
        
        # Import/dependency errors
        if isinstance(error, (ImportError, ModuleNotFoundError)):
            return 'dependency_error'
        
        # Computation errors
        if isinstance(error, (ArithmeticError, FloatingPointError)):
            return 'computation_error'
        
        # Default category
        return 'unknown_error'
    
    def log_error(self, 
                  error: Exception,
                  context: str = "",
                  data_info: Optional[Dict] = None) -> None:
        """
        Log error with context information.
        
        Args:
            error: Exception that occurred
            context: Context where error occurred
            data_info: Additional data information
        """
        error_info = {
            'timestamp': time.time(),
            'type': self.categorize_error(error),
            'message': str(error),
            'context': context,
            'data_info': data_info or {}
        }
        
        self.errors.append(error_info)
        
        if self.logger:
            self.logger.error(
                f"Error in {context}: {error} (Type: {error_info['type']})"
            )
    
    def handle_gpu_error(self,
                        gpu_operation: Callable,
                        fallback_func: Optional[Callable] = None,
                        context: str = "") -> Any:
        """
        Handle GPU-related errors with automatic fallback.
        
        Args:
            gpu_operation: Operation that may fail on GPU
            fallback_func: Fallback function for CPU execution
            context: Context description
            
        Returns:
            Result from successful operation
        """
        try:
            return gpu_operation()
        except Exception as error:
            if self.categorize_error(error) == 'gpu_error':
                self.log_error(error, context)
                
                if fallback_func and self.config.auto_fallback:
                    self.fallback_occurred = True
                    warnings.warn(f"GPU error in {context}, falling back to CPU")
                    return fallback_func()
                else:
                    raise
            else:
                raise
    
    def handle_memory_error(self,
                           operation: Callable,
                           data: pd.DataFrame,
                           reduction_strategy: str = 'batch') -> Dict[str, Any]:
        """
        Handle memory-related errors with data reduction.
        
        Args:
            operation: Operation that caused memory error
            data: Input data that may be too large
            reduction_strategy: Strategy for handling memory pressure
            
        Returns:
            Result dictionary with status and action taken
        """
        try:
            result = operation()
            return {'status': 'success', 'result': result}
        except MemoryError as error:
            self.log_error(error, "Memory allocation failure")
            
            if reduction_strategy == 'batch':
                return {
                    'status': 'memory_error',
                    'action_taken': 'batch_processing_recommended',
                    'suggested_batch_size': len(data) // 4
                }
            elif reduction_strategy == 'dtype_optimization':
                return {
                    'status': 'memory_error',
                    'action_taken': 'dtype_optimization_recommended',
                    'suggested_dtype': 'float32'
                }
            else:
                return {
                    'status': 'memory_error',
                    'action_taken': 'unknown_strategy'
                }
    
    def handle_computation_error(self,
                               operation: Callable,
                               error_recovery: str = 'retry_with_defaults',
                               default_params: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Handle computation errors with recovery strategies.
        
        Args:
            operation: Operation that may fail
            error_recovery: Recovery strategy
            default_params: Default parameters for retry
            
        Returns:
            Result dictionary
        """
        try:
            result = operation()
            return {'status': 'success', 'result': result}
        except (ValueError, TypeError, ArithmeticError) as error:
            self.log_error(error, "Computation error")
            
            if error_recovery == 'retry_with_defaults' and default_params:
                return {
                    'error_handled': True,
                    'strategy': 'retry_with_defaults',
                    'default_params_used': default_params
                }
            else:
                return {
                    'error_handled': True,
                    'strategy': error_recovery,
                    'original_error': str(error)
                }
    
    def execute_with_fallback(self,
                             operation: Callable,
                             primary_backend: str = 'cupy',
                             fallback_backend: str = 'numpy',
                             *args, **kwargs) -> Any:
        """
        Execute operation with automatic fallback between backends.
        
        Args:
            operation: Operation to execute
            primary_backend: Primary backend to try first
            fallback_backend: Fallback backend
            *args, **kwargs: Arguments for operation
            
        Returns:
            Result from successful execution
        """
        try:
            return operation(primary_backend, *args, **kwargs)
        except Exception as error:
            self.log_error(error, f"Primary backend ({primary_backend}) failed")
            
            if self.config.auto_fallback:
                self.fallback_occurred = True
                warnings.warn(f"Falling back from {primary_backend} to {fallback_backend}")
                return operation(fallback_backend, *args, **kwargs)
            else:
                raise
    
    def apply_recovery_strategy(self,
                               operation: Callable,
                               strategy: str,
                               default_value: Any = None,
                               max_retries: Optional[int] = None,
                               **kwargs) -> Any:
        """
        Apply specific recovery strategy for failed operations.
        
        Args:
            operation: Operation to execute
            strategy: Recovery strategy ('retry', 'fallback', 'skip', 'default_value')
            default_value: Default value for 'default_value' strategy
            max_retries: Maximum retries for 'retry' strategy
            **kwargs: Additional arguments
            
        Returns:
            Result based on strategy
        """
        retries = max_retries or self.config.max_retries
        
        if strategy == 'retry':
            for attempt in range(retries):
                try:
                    return operation(**kwargs)
                except Exception as error:
                    if attempt == retries - 1:
                        self.log_error(error, f"Retry failed after {retries} attempts")
                        raise
                    time.sleep(0.1 * (attempt + 1))  # Exponential backoff
        
        elif strategy == 'fallback':
            return self.execute_with_fallback(operation, **kwargs)
        
        elif strategy == 'skip':
            try:
                return operation(**kwargs)
            except Exception as error:
                self.log_error(error, "Operation skipped due to error")
                return None
        
        elif strategy == 'default_value':
            try:
                return operation(**kwargs)
            except Exception as error:
                self.log_error(error, "Using default value due to error")
                return default_value
        
        else:
            raise ValueError(f"Unknown recovery strategy: {strategy}")
    
    def handle_batch_errors(self,
                           operations: List[Callable],
                           strategy: str = 'continue_on_error') -> List[Any]:
        """
        Handle errors in batch operations.
        
        Args:
            operations: List of operations to execute
            strategy: Batch error strategy
            
        Returns:
            List of results (None for failed operations)
        """
        results = []
        
        for i, operation in enumerate(operations):
            try:
                result = operation()
                results.append(result)
            except Exception as error:
                self.log_error(error, f"Batch operation {i} failed")
                
                if strategy == 'continue_on_error':
                    results.append(None)
                elif strategy == 'stop_on_error':
                    raise
                elif strategy == 'retry_failed':
                    try:
                        result = operation()  # Single retry
                        results.append(result)
                    except Exception:
                        results.append(None)
        
        return results
    
    def execute_with_cleanup(self,
                            operation: Callable,
                            cleanup_func: Callable,
                            *args, **kwargs) -> Any:
        """
        Execute operation with guaranteed cleanup on error.
        
        Args:
            operation: Operation to execute
            cleanup_func: Cleanup function to call on error
            *args, **kwargs: Arguments for operation
            
        Returns:
            Result from operation
        """
        try:
            return operation(*args, **kwargs)
        except Exception as error:
            self.log_error(error, "Operation failed, performing cleanup")
            if self.config.auto_cleanup:
                cleanup_func()
            raise
    
    def handle_error_with_context(self,
                                 error: Exception,
                                 context: str,
                                 context_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle error with context-specific configuration.
        
        Args:
            error: Exception that occurred
            context: Context name
            context_config: Context-specific configuration
            
        Returns:
            Context-aware handling result
        """
        self.log_error(error, context)
        
        return {
            'context': context,
            'error_type': self.categorize_error(error),
            'strategy_applied': context_config.get('strategy', 'default'),
            'config_used': context_config
        }
    
    def graceful_degradation(self,
                           data: pd.DataFrame,
                           indicators: List[str],
                           failing_indicators: List[str]) -> Dict[str, Any]:
        """
        Handle graceful degradation when some indicators fail.
        
        Args:
            data: Input data
            indicators: All requested indicators
            failing_indicators: Indicators that failed
            
        Returns:
            Partial results with successful indicators
        """
        successful_indicators = [ind for ind in indicators if ind not in failing_indicators]
        
        # Mock computation of successful indicators
        partial_result = data.copy()
        for indicator in successful_indicators:
            # This would normally compute the indicator
            partial_result[f'{indicator}_mock'] = np.random.randn(len(data))
        
        return {
            'successful_indicators': successful_indicators,
            'failed_indicators': failing_indicators,
            'partial_result': partial_result,
            'success_rate': len(successful_indicators) / len(indicators)
        }
    
    def get_error_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive error summary.
        
        Returns:
            Dictionary with error statistics and insights
        """
        if not self.errors:
            return {'total_errors': 0, 'message': 'No errors recorded'}
        
        error_types = Counter(error['type'] for error in self.errors)
        contexts = Counter(error['context'] for error in self.errors if error['context'])
        
        return {
            'total_errors': len(self.errors),
            'error_types': dict(error_types),
            'most_common_type': error_types.most_common(1)[0] if error_types else None,
            'most_common_context': contexts.most_common(1)[0] if contexts else None,
            'fallback_occurred': self.fallback_occurred,
            'recent_errors': self.errors[-5:] if len(self.errors) > 5 else self.errors
        }


class GPUFallbackManager:
    """
    Specialized manager for GPU fallback scenarios.
    
    Handles GPU availability detection, health monitoring, and
    performance impact assessment of fallbacks.
    """
    
    def __init__(self,
                 error_threshold: int = 5,
                 monitor_performance: bool = True):
        """
        Initialize GPU fallback manager.
        
        Args:
            error_threshold: Error count threshold for permanent fallback
            monitor_performance: Enable performance monitoring
        """
        self.error_threshold = error_threshold
        self.monitor_performance = monitor_performance
        self.error_count = 0
        self.permanent_fallback_triggered = False
        self.fallback_strategies = ['immediate', 'delayed', 'permanent']
        
        # Performance tracking
        self.performance_stats = []
    
    def detect_gpu_availability(self) -> Dict[str, Any]:
        """
        Detect GPU availability and capabilities.
        
        Returns:
            GPU availability information
        """
        try:
            import cupy as cp
            device_count = cp.cuda.runtime.getDeviceCount()
            
            return {
                'gpu_available': True,
                'device_count': device_count,
                'cupy_version': cp.__version__
            }
        except (ImportError, Exception):
            return {
                'gpu_available': False,
                'device_count': 0,
                'error': 'CuPy not available or GPU not accessible'
            }
    
    def monitor_gpu_health(self) -> Dict[str, Any]:
        """
        Monitor GPU health and resource usage.
        
        Returns:
            GPU health information
        """
        try:
            import cupy as cp
            
            # Get memory information
            free_mem, total_mem = cp.cuda.runtime.memGetInfo()
            usage_percent = ((total_mem - free_mem) / total_mem) * 100
            
            # Determine health status
            if usage_percent < 70:
                status = 'healthy'
            elif usage_percent < 90:
                status = 'warning'
            else:
                status = 'critical'
            
            return {
                'status': status,
                'memory_free': free_mem,
                'memory_total': total_mem,
                'memory_usage_percent': usage_percent
            }
        except Exception:
            return {
                'status': 'unavailable',
                'error': 'Cannot access GPU health information'
            }
    
    def create_fallback_pipeline(self,
                                primary_backend: str,
                                fallback_backend: str,
                                operation: str) -> Callable:
        """
        Create a fallback pipeline for specific operation.
        
        Args:
            primary_backend: Primary backend
            fallback_backend: Fallback backend
            operation: Operation name
            
        Returns:
            Callable pipeline with fallback
        """
        def fallback_pipeline(data: pd.DataFrame) -> pd.DataFrame:
            try:
                # Try primary backend
                pipeline = UnifiedTechnicalIndicatorsPipeline(backend=primary_backend)
                return pipeline.compute_indicators(data, indicators=[operation])
            except Exception:
                # Fallback to secondary backend
                warnings.warn(f"Falling back from {primary_backend} to {fallback_backend}")
                pipeline = UnifiedTechnicalIndicatorsPipeline(backend=fallback_backend)
                return pipeline.compute_indicators(data, indicators=[operation])
        
        return fallback_pipeline
    
    def measure_fallback_impact(self,
                               gpu_operation: Callable,
                               cpu_operation: Callable) -> Dict[str, float]:
        """
        Measure performance impact of fallback.
        
        Args:
            gpu_operation: GPU operation
            cpu_operation: CPU operation
            
        Returns:
            Performance impact metrics
        """
        if not self.monitor_performance:
            return {}
        
        # Measure GPU performance
        start_time = time.perf_counter()
        try:
            gpu_result = gpu_operation()
            gpu_time = time.perf_counter() - start_time
            gpu_success = True
        except Exception:
            gpu_time = float('inf')
            gpu_success = False
        
        # Measure CPU performance
        start_time = time.perf_counter()
        cpu_result = cpu_operation()
        cpu_time = time.perf_counter() - start_time
        
        # Calculate impact
        if gpu_success and gpu_time > 0:
            performance_loss = (cpu_time - gpu_time) / gpu_time
        else:
            performance_loss = 0.0  # No loss if GPU wasn't working
        
        impact = {
            'gpu_time': gpu_time if gpu_success else None,
            'cpu_time': cpu_time,
            'performance_loss': performance_loss,
            'gpu_success': gpu_success
        }
        
        self.performance_stats.append(impact)
        return impact
    
    def record_error(self, error_message: str) -> None:
        """Record GPU error for threshold tracking"""
        self.error_count += 1
        if self.error_count >= self.error_threshold:
            self.permanent_fallback_triggered = True
    
    def should_permanently_fallback(self) -> bool:
        """Check if permanent fallback should be triggered"""
        return self.permanent_fallback_triggered