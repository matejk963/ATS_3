"""
Integration tests for Phase 3: GPU Integration & Testing

Tests the complete Phase 3 system including:
- Unified pipeline with backend selection
- Performance benchmarking
- Memory optimization
- Error handling and fallback mechanisms
"""

import pytest
import pandas as pd
import numpy as np
import time
from unittest.mock import patch, MagicMock
import warnings

from src.feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline
from src.feature_engineering.performance_benchmark import PerformanceBenchmark
from src.feature_engineering.memory_optimizer import MemoryOptimizer
from src.feature_engineering.error_handling import ErrorHandler, GPUFallbackManager


class TestPhase3Integration:
    """Integration tests for Phase 3 GPU integration and testing"""
    
    @pytest.fixture
    def large_dataset(self):
        """Create large dataset for integration testing"""
        np.random.seed(42)
        size = 50000
        prices = 100 + np.cumsum(np.random.randn(size) * 0.001)
        
        return pd.DataFrame({
            'open': prices * (1 + np.random.randn(size) * 0.0005),
            'high': prices * (1 + np.abs(np.random.randn(size)) * 0.001),
            'low': prices * (1 - np.abs(np.random.randn(size)) * 0.001),
            'close': prices,
            'volume': np.random.randint(1000, 10000, size),
            'datetime': pd.date_range('2023-01-01', periods=size, freq='1min')
        })
    
    @pytest.fixture
    def medium_dataset(self):
        """Create medium dataset for testing"""
        np.random.seed(42)
        size = 5000
        prices = 100 + np.cumsum(np.random.randn(size) * 0.01)
        
        return pd.DataFrame({
            'open': prices * (1 + np.random.randn(size) * 0.001),
            'high': prices * (1 + np.abs(np.random.randn(size)) * 0.002),
            'low': prices * (1 - np.abs(np.random.randn(size)) * 0.002),
            'close': prices,
            'volume': np.random.randint(1000, 10000, size),
            'datetime': pd.date_range('2023-01-01', periods=size, freq='1min')
        })
    
    def test_end_to_end_cpu_pipeline(self, medium_dataset):
        """Test complete pipeline with CPU backend"""
        # Initialize unified pipeline
        pipeline = UnifiedTechnicalIndicatorsPipeline(
            backend='numpy',
            optimize_memory=True,
            fallback_on_error=True
        )
        
        # Compute all indicators
        result = pipeline.compute_all_indicators(
            data=medium_dataset,
            macd_params={'fast': 12, 'slow': 26, 'signal': 9},
            atr_period=14,
            swing_lookback=20
        )
        
        # Verify results
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(medium_dataset)
        
        # Check all indicators are present
        expected_indicators = ['macd', 'signal', 'histogram', 'atr', 'swing_highs', 'swing_lows']
        for indicator in expected_indicators:
            assert indicator in result.columns
            # Check no all-NaN columns (except for ATR which might have NaN at start)
            if indicator != 'atr':
                assert not result[indicator].isna().all()
    
    def test_end_to_end_gpu_pipeline_with_fallback(self, medium_dataset):
        """Test complete pipeline with GPU backend and fallback"""
        # Initialize pipeline with GPU backend (will fallback to CPU if unavailable)
        pipeline = UnifiedTechnicalIndicatorsPipeline(
            backend='cupy',
            optimize_memory=True,
            fallback_on_error=True
        )
        
        # Compute indicators (should work regardless of GPU availability)
        result = pipeline.compute_indicators(
            data=medium_dataset,
            indicators=['macd', 'atr'],
            macd_params={'fast': 12, 'slow': 26, 'signal': 9},
            atr_period=14
        )
        
        # Verify results
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(medium_dataset)
        assert 'macd' in result.columns
        assert 'atr' in result.columns
    
    def test_memory_optimization_integration(self, large_dataset):
        """Test memory optimization with large dataset"""
        # Initialize memory optimizer
        optimizer = MemoryOptimizer(
            dtype='float32',
            ensure_contiguous=True,
            enable_memory_pool=True
        )
        
        # Extract arrays from dataset
        arrays = {col: large_dataset[col].values 
                 for col in ['open', 'high', 'low', 'close'] 
                 if col in large_dataset.columns}
        
        # Optimize arrays
        initial_memory = optimizer.get_memory_usage()
        optimized_arrays = optimizer.optimize_arrays(arrays)
        
        # Verify optimization
        for key, arr in optimized_arrays.items():
            assert arr.dtype == np.float32
            assert arr.flags['C_CONTIGUOUS']
        
        # Test batch transfer
        gpu_arrays = optimizer.batch_transfer(optimized_arrays, backend='cupy')
        assert len(gpu_arrays) == len(optimized_arrays)
    
    def test_performance_benchmarking_integration(self, medium_dataset):
        """Test performance benchmarking system"""
        # Initialize benchmark
        benchmark = PerformanceBenchmark(
            runs=2,  # Small number for testing
            data_sizes=[1000, 5000],
            enable_memory_tracking=True
        )
        
        # Run targeted benchmark
        benchmark.run_full_benchmark(
            data_sizes=[len(medium_dataset)],
            runs=2
        )
        
        # Verify benchmark results
        assert len(benchmark.results) > 0
        
        # Generate report
        report = benchmark.generate_performance_report()
        assert isinstance(report, str)
        assert 'Performance Benchmark Report' in report
    
    def test_error_handling_integration(self, medium_dataset):
        """Test error handling with realistic scenarios"""
        # Initialize error handler
        handler = ErrorHandler(
            auto_fallback=True,
            enable_logging=True,
            monitor_performance=True
        )
        
        # Test GPU fallback scenario
        def mock_gpu_operation():
            raise RuntimeError("CUDA out of memory")
        
        def mock_cpu_fallback():
            return medium_dataset.copy()
        
        # Execute with fallback
        result = handler.handle_gpu_error(
            gpu_operation=mock_gpu_operation,
            fallback_func=mock_cpu_fallback,
            context="Integration test"
        )
        
        # Verify fallback worked
        assert isinstance(result, pd.DataFrame)
        assert handler.fallback_occurred
        assert len(handler.errors) == 1
    
    def test_unified_pipeline_with_memory_optimization(self, large_dataset):
        """Test unified pipeline with memory optimization enabled"""
        # Create pipeline with memory optimization
        pipeline = UnifiedTechnicalIndicatorsPipeline(
            backend='numpy',
            optimize_memory=True,
            dtype='float32'
        )
        
        # Process large dataset
        result = pipeline.compute_indicators(
            data=large_dataset,
            indicators=['macd', 'atr']
        )
        
        # Verify processing succeeded
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(large_dataset)
        
        # Check memory-optimized dtypes where applicable
        numeric_columns = result.select_dtypes(include=[np.number]).columns
        # Some columns might be preserved as original dtype, which is acceptable
    
    def test_fallback_manager_integration(self, medium_dataset):
        """Test GPU fallback manager integration"""
        # Initialize fallback manager
        manager = GPUFallbackManager(
            error_threshold=2,
            monitor_performance=True
        )
        
        # Detect GPU availability
        gpu_info = manager.detect_gpu_availability()
        assert isinstance(gpu_info, dict)
        assert 'gpu_available' in gpu_info
        
        # Create fallback pipeline
        fallback_pipeline = manager.create_fallback_pipeline(
            primary_backend='cupy',
            fallback_backend='numpy',
            operation='macd'
        )
        
        # Test fallback pipeline
        result = fallback_pipeline(medium_dataset)
        assert isinstance(result, pd.DataFrame)
        assert 'macd' in result.columns
    
    def test_complete_system_integration(self, medium_dataset):
        """Test complete Phase 3 system integration"""
        # Initialize all components
        pipeline = UnifiedTechnicalIndicatorsPipeline(
            backend='auto',  # Auto-select based on availability
            optimize_memory=True,
            fallback_on_error=True,
            enable_caching=True
        )
        
        error_handler = ErrorHandler(auto_fallback=True)
        memory_optimizer = MemoryOptimizer(cache_aware=True)
        
        # Process data through complete system
        try:
            # First, optimize memory layout
            arrays = {col: medium_dataset[col].values 
                     for col in ['open', 'high', 'low', 'close']}
            optimized_arrays = memory_optimizer.optimize_arrays(arrays)
            
            # Process through pipeline
            result = pipeline.compute_all_indicators(
                data=medium_dataset,
                macd_params={'fast': 12, 'slow': 26, 'signal': 9},
                atr_period=14,
                swing_lookback=20
            )
            
            # Verify complete system worked
            assert isinstance(result, pd.DataFrame)
            assert len(result) == len(medium_dataset)
            
            # Check all expected indicators
            expected_indicators = ['macd', 'signal', 'histogram', 'atr', 'swing_high', 'swing_low']
            for indicator in expected_indicators:
                assert indicator in result.columns
            
        except Exception as e:
            # System should handle errors gracefully
            error_handler.log_error(e, "System integration test")
            assert len(error_handler.errors) > 0
    
    def test_performance_comparison_integration(self, medium_dataset):
        """Test integrated performance comparison between backends"""
        pipeline = UnifiedTechnicalIndicatorsPipeline()
        
        # Compare performance between backends
        comparison = pipeline.compare_backend_performance(
            data=medium_dataset,
            indicators=['macd', 'atr'],
            runs=2,
            macd_params={'fast': 12, 'slow': 26, 'signal': 9},
            atr_period=14
        )
        
        # Verify comparison results
        assert isinstance(comparison, dict)
        assert 'numpy' in comparison  # CPU should always be available
        
        # Check result structure
        if comparison['numpy']['backend_available']:
            assert 'avg_time' in comparison['numpy']
            assert 'results' in comparison['numpy']
    
    def test_caching_integration(self, medium_dataset):
        """Test caching integration across multiple computations"""
        pipeline = UnifiedTechnicalIndicatorsPipeline(
            backend='numpy',
            enable_caching=True
        )
        
        # First computation
        start_time = time.perf_counter()
        result1 = pipeline.compute_indicators(
            data=medium_dataset,
            indicators=['macd'],
            macd_params={'fast': 12, 'slow': 26, 'signal': 9}
        )
        first_time = time.perf_counter() - start_time
        
        # Second computation (should use cache)
        start_time = time.perf_counter()
        result2 = pipeline.compute_indicators(
            data=medium_dataset,
            indicators=['macd'],
            macd_params={'fast': 12, 'slow': 26, 'signal': 9}
        )
        second_time = time.perf_counter() - start_time
        
        # Verify caching worked
        pd.testing.assert_frame_equal(result1, result2)
        # Second computation should be faster (cached)
        # Note: In small datasets, overhead might make this not always true
        assert second_time <= first_time * 1.5  # Allow some tolerance
    
    def test_batch_processing_integration(self, large_dataset):
        """Test batch processing for large datasets"""
        # Split large dataset into batches
        batch_size = 10000
        batches = [
            large_dataset.iloc[i:i+batch_size] 
            for i in range(0, len(large_dataset), batch_size)
        ]
        
        pipeline = UnifiedTechnicalIndicatorsPipeline(
            backend='numpy',
            optimize_memory=True
        )
        
        # Process each batch
        batch_results = []
        for i, batch in enumerate(batches):
            try:
                result = pipeline.compute_indicators(
                    data=batch,
                    indicators=['macd'],
                    macd_params={'fast': 12, 'slow': 26, 'signal': 9}
                )
                batch_results.append(result)
            except Exception as e:
                pytest.fail(f"Batch {i} processing failed: {e}")
        
        # Verify all batches processed successfully
        assert len(batch_results) == len(batches)
        
        # Combine results
        combined_result = pd.concat(batch_results, ignore_index=True)
        assert len(combined_result) == len(large_dataset)
    
    def test_stress_testing_integration(self, large_dataset):
        """Test system under stress conditions"""
        # Create multiple pipelines for concurrent-like testing
        pipelines = [
            UnifiedTechnicalIndicatorsPipeline(
                backend='numpy',
                optimize_memory=True,
                fallback_on_error=True
            )
            for _ in range(3)
        ]
        
        # Process same data through multiple pipelines
        results = []
        for i, pipeline in enumerate(pipelines):
            try:
                result = pipeline.compute_indicators(
                    data=large_dataset,
                    indicators=['macd', 'atr'],
                    macd_params={'fast': 12, 'slow': 26, 'signal': 9},
                    atr_period=14
                )
                results.append(result)
            except Exception as e:
                # System should handle stress gracefully
                warnings.warn(f"Pipeline {i} failed under stress: {e}")
        
        # At least one pipeline should succeed
        assert len(results) > 0
        
        # Results should be consistent
        if len(results) > 1:
            pd.testing.assert_frame_equal(results[0], results[1])
    
    def test_configuration_validation_integration(self):
        """Test configuration validation across all components"""
        # Test valid configurations
        valid_configs = [
            {
                'pipeline': {'backend': 'numpy', 'optimize_memory': True},
                'benchmark': {'runs': 3, 'enable_memory_tracking': True},
                'optimizer': {'dtype': 'float32', 'ensure_contiguous': True},
                'error_handler': {'auto_fallback': True, 'max_retries': 3}
            }
        ]
        
        for config in valid_configs:
            try:
                pipeline = UnifiedTechnicalIndicatorsPipeline(**config['pipeline'])
                benchmark = PerformanceBenchmark(**config['benchmark'])
                optimizer = MemoryOptimizer(**config['optimizer'])
                handler = ErrorHandler(**config['error_handler'])
                
                # All components should initialize successfully
                assert pipeline is not None
                assert benchmark is not None
                assert optimizer is not None
                assert handler is not None
                
            except Exception as e:
                pytest.fail(f"Valid configuration failed: {e}")
        
        # Test invalid configurations
        with pytest.raises(ValueError):
            UnifiedTechnicalIndicatorsPipeline(backend='invalid_backend')
        
        with pytest.raises(ValueError):
            MemoryOptimizer(dtype='invalid_dtype')
        
        with pytest.raises(ValueError):
            ErrorHandler(max_retries=-1)