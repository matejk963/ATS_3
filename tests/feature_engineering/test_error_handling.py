"""
Test suite for error handling and fallback mechanisms.

Following TDD principles: write tests first, then implement error handling.
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock
import warnings

# Import will be created after test
from src.feature_engineering.error_handling import ErrorHandler, GPUFallbackManager


class TestErrorHandling:
    """Test error handling and fallback mechanisms"""
    
    @pytest.fixture
    def sample_data(self):
        """Create sample OHLCV data"""
        np.random.seed(42)
        size = 1000
        prices = 100 + np.cumsum(np.random.randn(size) * 0.01)
        
        return pd.DataFrame({
            'open': prices * (1 + np.random.randn(size) * 0.001),
            'high': prices * (1 + np.abs(np.random.randn(size)) * 0.002),
            'low': prices * (1 - np.abs(np.random.randn(size)) * 0.002),
            'close': prices,
            'volume': np.random.randint(1000, 10000, size),
            'datetime': pd.date_range('2023-01-01', periods=size, freq='1min')
        })
    
    def test_error_handler_initialization(self):
        """Test error handler initializes properly"""
        handler = ErrorHandler()
        
        assert hasattr(handler, 'handle_gpu_error')
        assert hasattr(handler, 'handle_memory_error')
        assert hasattr(handler, 'handle_computation_error')
        assert hasattr(handler, 'get_error_summary')
        assert hasattr(handler, 'errors')
        assert isinstance(handler.errors, list)
    
    def test_gpu_error_handling(self, sample_data):
        """Test GPU error detection and fallback"""
        handler = ErrorHandler()
        
        # Mock GPU error
        def failing_gpu_operation():
            raise RuntimeError("CUDA out of memory")
        
        # Handle GPU error
        result = handler.handle_gpu_error(
            failing_gpu_operation,
            fallback_func=lambda: "CPU fallback executed",
            context="MACD calculation"
        )
        
        assert result == "CPU fallback executed"
        assert len(handler.errors) == 1
        assert "CUDA out of memory" in handler.errors[0]['message']
        assert handler.errors[0]['type'] == 'gpu_error'
        assert handler.errors[0]['context'] == "MACD calculation"
    
    def test_memory_error_handling(self, sample_data):
        """Test memory error detection and recovery"""
        handler = ErrorHandler()
        
        # Mock memory error
        def memory_intensive_operation():
            raise MemoryError("Unable to allocate memory")
        
        # Handle memory error with data reduction strategy
        result = handler.handle_memory_error(
            memory_intensive_operation,
            data=sample_data,
            reduction_strategy='batch'
        )
        
        assert 'status' in result
        assert 'action_taken' in result
        assert len(handler.errors) == 1
        assert handler.errors[0]['type'] == 'memory_error'
    
    def test_computation_error_handling(self, sample_data):
        """Test computation error handling"""
        handler = ErrorHandler()
        
        # Mock computation error
        def failing_computation():
            raise ValueError("Invalid parameter combination")
        
        # Handle computation error
        result = handler.handle_computation_error(
            failing_computation,
            error_recovery='retry_with_defaults',
            default_params={'fast': 12, 'slow': 26}
        )
        
        assert 'error_handled' in result
        assert len(handler.errors) == 1
        assert handler.errors[0]['type'] == 'computation_error'
    
    def test_fallback_manager_initialization(self):
        """Test GPU fallback manager initialization"""
        manager = GPUFallbackManager()
        
        assert hasattr(manager, 'detect_gpu_availability')
        assert hasattr(manager, 'create_fallback_pipeline')
        assert hasattr(manager, 'monitor_gpu_health')
        assert hasattr(manager, 'fallback_strategies')
    
    def test_gpu_availability_detection(self):
        """Test GPU availability detection"""
        manager = GPUFallbackManager()
        
        # Test with CuPy available (mocked)
        with patch('cupy.cuda.runtime.getDeviceCount') as mock_count:
            mock_count.return_value = 1
            availability = manager.detect_gpu_availability()
            
            assert availability['gpu_available'] == True
            assert availability['device_count'] == 1
        
        # Test with CuPy unavailable
        with patch('cupy.cuda.runtime.getDeviceCount') as mock_count:
            mock_count.side_effect = ImportError("CuPy not installed")
            availability = manager.detect_gpu_availability()
            
            assert availability['gpu_available'] == False
    
    def test_fallback_pipeline_creation(self, sample_data):
        """Test creation of fallback pipeline"""
        manager = GPUFallbackManager()
        
        # Create fallback from GPU to CPU
        fallback_pipeline = manager.create_fallback_pipeline(
            primary_backend='cupy',
            fallback_backend='numpy',
            operation='macd'
        )
        
        assert callable(fallback_pipeline)
        
        # Test the fallback pipeline
        result = fallback_pipeline(sample_data)
        assert isinstance(result, pd.DataFrame)
    
    def test_gpu_health_monitoring(self):
        """Test GPU health monitoring"""
        manager = GPUFallbackManager()
        
        # Mock GPU health check
        with patch('cupy.cuda.runtime.memGetInfo') as mock_mem:
            mock_mem.return_value = (1000000000, 8000000000)  # 1GB free, 8GB total
            
            health = manager.monitor_gpu_health()
            
            assert 'memory_free' in health
            assert 'memory_total' in health
            assert 'memory_usage_percent' in health
            assert health['status'] in ['healthy', 'warning', 'critical']
    
    def test_automatic_fallback_on_error(self, sample_data):
        """Test automatic fallback when GPU operation fails"""
        handler = ErrorHandler(auto_fallback=True)
        
        # Mock operation that fails on GPU but works on CPU
        def mock_operation(backend):
            if backend == 'cupy':
                raise RuntimeError("GPU computation failed")
            return sample_data.copy()
        
        result = handler.execute_with_fallback(
            operation=mock_operation,
            primary_backend='cupy',
            fallback_backend='numpy'
        )
        
        assert isinstance(result, pd.DataFrame)
        assert len(handler.errors) == 1
        assert handler.fallback_occurred
    
    def test_error_recovery_strategies(self, sample_data):
        """Test different error recovery strategies"""
        handler = ErrorHandler()
        
        strategies = ['retry', 'fallback', 'skip', 'default_value']
        
        for strategy in strategies:
            # Mock failing operation
            def failing_op():
                raise ValueError("Test error")
            
            result = handler.apply_recovery_strategy(
                operation=failing_op,
                strategy=strategy,
                default_value=sample_data.copy(),
                max_retries=2
            )
            
            if strategy == 'default_value':
                assert isinstance(result, pd.DataFrame)
            elif strategy == 'skip':
                assert result is None
    
    def test_error_categorization(self):
        """Test automatic error categorization"""
        handler = ErrorHandler()
        
        error_types = [
            (RuntimeError("CUDA error"), 'gpu_error'),
            (MemoryError("Out of memory"), 'memory_error'),
            (ValueError("Invalid input"), 'input_error'),
            (ImportError("Module not found"), 'dependency_error'),
            (Exception("Unknown error"), 'unknown_error')
        ]
        
        for error, expected_category in error_types:
            category = handler.categorize_error(error)
            assert category == expected_category
    
    def test_error_logging_and_reporting(self, sample_data):
        """Test error logging and reporting functionality"""
        handler = ErrorHandler(enable_logging=True)
        
        # Generate some errors
        handler.log_error(
            error=RuntimeError("GPU error"),
            context="MACD calculation",
            data_info={'size': len(sample_data), 'columns': list(sample_data.columns)}
        )
        
        handler.log_error(
            error=MemoryError("Memory error"),
            context="ATR calculation"
        )
        
        # Get error summary
        summary = handler.get_error_summary()
        
        assert isinstance(summary, dict)
        assert 'total_errors' in summary
        assert 'error_types' in summary
        assert 'most_common_context' in summary
        assert summary['total_errors'] == 2
    
    def test_performance_impact_monitoring(self, sample_data):
        """Test monitoring performance impact of fallbacks"""
        manager = GPUFallbackManager(monitor_performance=True)
        
        # Mock timed operations
        with patch('time.perf_counter') as mock_time:
            mock_time.side_effect = [0.0, 0.1, 0.0, 0.2]  # GPU: 0.1s, CPU: 0.2s
            
            # Simulate fallback scenario
            perf_impact = manager.measure_fallback_impact(
                gpu_operation=lambda: sample_data.copy(),
                cpu_operation=lambda: sample_data.copy()
            )
        
        assert 'gpu_time' in perf_impact
        assert 'cpu_time' in perf_impact
        assert 'performance_loss' in perf_impact
    
    def test_batch_error_handling(self, sample_data):
        """Test handling errors in batch operations"""
        handler = ErrorHandler()
        
        # Mock batch operations where some fail
        operations = [
            lambda: sample_data.copy(),  # Success
            lambda: (_ for _ in ()).throw(ValueError("Failed op")),  # Failure
            lambda: sample_data.copy(),  # Success
        ]
        
        results = handler.handle_batch_errors(
            operations,
            strategy='continue_on_error'
        )
        
        assert len(results) == 3
        assert results[0] is not None  # Success
        assert results[1] is None     # Failed
        assert results[2] is not None  # Success
        assert len(handler.errors) == 1
    
    def test_resource_cleanup_on_error(self, sample_data):
        """Test resource cleanup when errors occur"""
        handler = ErrorHandler(auto_cleanup=True)
        
        # Mock operation that allocates resources then fails
        resources = {'allocated': True}
        
        def failing_operation():
            resources['gpu_memory'] = "allocated"
            raise RuntimeError("Operation failed")
        
        def cleanup_func():
            resources.clear()
        
        handler.execute_with_cleanup(
            operation=failing_operation,
            cleanup_func=cleanup_func
        )
        
        assert len(resources) == 0  # Resources should be cleaned up
        assert len(handler.errors) == 1
    
    def test_error_threshold_management(self, sample_data):
        """Test error threshold management"""
        manager = GPUFallbackManager(error_threshold=3)
        
        # Simulate multiple errors
        for i in range(5):
            manager.record_error(f"Error {i}")
        
        # Should trigger permanent fallback after threshold
        assert manager.should_permanently_fallback()
        assert manager.permanent_fallback_triggered
    
    def test_configuration_validation(self):
        """Test error handling configuration validation"""
        # Valid configuration
        config = {
            'auto_fallback': True,
            'max_retries': 3,
            'error_threshold': 5,
            'enable_logging': True
        }
        
        handler = ErrorHandler(**config)
        assert handler.config.auto_fallback == True
        
        # Invalid configuration
        with pytest.raises(ValueError, match="max_retries must be non-negative"):
            ErrorHandler(max_retries=-1)
    
    def test_context_aware_error_handling(self, sample_data):
        """Test context-aware error handling"""
        handler = ErrorHandler()
        
        # Different contexts should have different handling strategies
        contexts = {
            'real_time_trading': {'strategy': 'fast_fallback', 'timeout': 0.1},
            'batch_analysis': {'strategy': 'retry_with_backoff', 'max_retries': 5},
            'research': {'strategy': 'detailed_logging', 'preserve_errors': True}
        }
        
        for context, config in contexts.items():
            result = handler.handle_error_with_context(
                error=ValueError("Test error"),
                context=context,
                context_config=config
            )
            
            assert 'context' in result
            assert result['context'] == context
    
    def test_graceful_degradation(self, sample_data):
        """Test graceful degradation when components fail"""
        handler = ErrorHandler()
        
        # Mock system where some indicators fail but others succeed
        indicators = ['macd', 'atr', 'swing_points']
        failing_indicators = ['macd']  # MACD fails
        
        results = handler.graceful_degradation(
            data=sample_data,
            indicators=indicators,
            failing_indicators=failing_indicators
        )
        
        # Should return partial results
        assert 'successful_indicators' in results
        assert 'failed_indicators' in results
        assert 'partial_result' in results
        assert set(results['failed_indicators']) == set(failing_indicators)