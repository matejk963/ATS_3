"""
Test suite for memory transfer optimization.

Following TDD principles: write tests first, then implement memory optimizations.
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock

# Import will be created after test
from src.feature_engineering.memory_optimizer import MemoryOptimizer


class TestMemoryOptimization:
    """Test memory optimization functionality"""
    
    @pytest.fixture
    def sample_data(self):
        """Create sample OHLCV data"""
        np.random.seed(42)
        size = 10000
        prices = 100 + np.cumsum(np.random.randn(size) * 0.01)
        
        return pd.DataFrame({
            'open': prices * (1 + np.random.randn(size) * 0.001),
            'high': prices * (1 + np.abs(np.random.randn(size)) * 0.002),
            'low': prices * (1 - np.abs(np.random.randn(size)) * 0.002),
            'close': prices,
            'volume': np.random.randint(1000, 10000, size),
            'datetime': pd.date_range('2023-01-01', periods=size, freq='1min')
        })
    
    def test_memory_optimizer_initialization(self):
        """Test memory optimizer initializes properly"""
        optimizer = MemoryOptimizer()
        
        assert hasattr(optimizer, 'optimize_arrays')
        assert hasattr(optimizer, 'batch_transfer')
        assert hasattr(optimizer, 'minimize_cpu_gpu_transfers')
        assert hasattr(optimizer, 'get_memory_usage')
    
    def test_array_memory_optimization(self, sample_data):
        """Test array memory layout optimization"""
        optimizer = MemoryOptimizer()
        
        # Convert DataFrame to arrays
        arrays = {col: sample_data[col].values for col in sample_data.columns if col != 'datetime'}
        
        # Optimize memory layout
        optimized_arrays = optimizer.optimize_arrays(
            arrays, 
            dtype='float32',
            ensure_contiguous=True
        )
        
        # Check optimization results
        for key, arr in optimized_arrays.items():
            if key != 'volume':  # volume might remain int
                assert arr.dtype == np.float32
            assert arr.flags['C_CONTIGUOUS']  # Should be C-contiguous
            assert not arr.flags['OWNDATA'] or arr.flags['ALIGNED']  # Should be aligned
    
    def test_batch_transfer_optimization(self, sample_data):
        """Test batch transfer to minimize GPU transfers"""
        optimizer = MemoryOptimizer()
        
        # Mock GPU arrays
        arrays = {col: sample_data[col].values.astype('float32') 
                 for col in ['open', 'high', 'low', 'close']}
        
        # Test batch transfer
        with patch('cupy.asarray') as mock_cupy:
            mock_cupy.side_effect = lambda x: x  # Mock identity transfer
            
            gpu_arrays = optimizer.batch_transfer(arrays, backend='cupy')
            
            # Should have called cupy.asarray for each array
            assert mock_cupy.call_count == len(arrays)
            assert set(gpu_arrays.keys()) == set(arrays.keys())
    
    def test_memory_usage_tracking(self, sample_data):
        """Test memory usage tracking"""
        optimizer = MemoryOptimizer()
        
        arrays = {'close': sample_data['close'].values.astype('float32')}
        
        # Get memory usage before and after optimization
        initial_usage = optimizer.get_memory_usage()
        optimized_arrays = optimizer.optimize_arrays(arrays)
        final_usage = optimizer.get_memory_usage()
        
        # Memory usage should be tracked
        assert isinstance(initial_usage, (int, float))
        assert isinstance(final_usage, (int, float))
        assert initial_usage >= 0
        assert final_usage >= 0
    
    def test_transfer_minimization_strategy(self, sample_data):
        """Test strategy to minimize CPU-GPU transfers"""
        optimizer = MemoryOptimizer()
        
        # Simulate multiple operations that would normally require transfers
        arrays = {col: sample_data[col].values.astype('float32') 
                 for col in ['open', 'high', 'low', 'close']}
        
        operations = [
            {'op': 'macd', 'inputs': ['close'], 'outputs': ['macd', 'signal', 'histogram']},
            {'op': 'atr', 'inputs': ['high', 'low', 'close'], 'outputs': ['atr']},
            {'op': 'swing', 'inputs': ['high', 'low'], 'outputs': ['swing_high', 'swing_low']}
        ]
        
        # Optimize transfer strategy
        transfer_plan = optimizer.minimize_cpu_gpu_transfers(arrays, operations)
        
        # Should return an optimized plan
        assert isinstance(transfer_plan, dict)
        assert 'initial_transfer' in transfer_plan
        assert 'final_transfer' in transfer_plan
        assert 'estimated_savings' in transfer_plan
    
    def test_dtype_optimization(self, sample_data):
        """Test data type optimization for GPU efficiency"""
        optimizer = MemoryOptimizer()
        
        # Test with mixed dtypes
        arrays = {
            'close_float64': sample_data['close'].values,  # float64
            'volume_int64': sample_data['volume'].values,  # int64
        }
        
        # Optimize dtypes for GPU
        optimized = optimizer.optimize_dtypes(
            arrays, 
            target_float='float32',
            target_int='int32'
        )
        
        assert optimized['close_float64'].dtype == np.float32
        assert optimized['volume_int64'].dtype == np.int32
    
    def test_memory_pool_management(self):
        """Test memory pool management for GPU arrays"""
        optimizer = MemoryOptimizer(enable_memory_pool=True)
        
        # Test memory pool initialization
        assert hasattr(optimizer, 'memory_pool')
        
        # Test pool allocation
        size = 1000
        allocated_memory = optimizer.allocate_from_pool(size, dtype='float32')
        
        assert allocated_memory is not None
        assert len(allocated_memory) == size
    
    def test_lazy_transfer_optimization(self, sample_data):
        """Test lazy transfer to delay GPU transfers until needed"""
        optimizer = MemoryOptimizer(lazy_transfer=True)
        
        arrays = {'close': sample_data['close'].values.astype('float32')}
        
        # Create lazy transfer wrapper
        lazy_arrays = optimizer.create_lazy_transfer(arrays, backend='cupy')
        
        # Should not have transferred to GPU yet
        assert hasattr(lazy_arrays['close'], '_cpu_array')
        assert not hasattr(lazy_arrays['close'], '_gpu_array')
        
        # Access should trigger transfer
        with patch('cupy.asarray') as mock_cupy:
            mock_cupy.return_value = arrays['close']
            gpu_value = lazy_arrays['close'].gpu_array
            mock_cupy.assert_called_once()
    
    def test_memory_fragmentation_analysis(self, sample_data):
        """Test memory fragmentation analysis"""
        optimizer = MemoryOptimizer()
        
        arrays = {col: sample_data[col].values 
                 for col in ['open', 'high', 'low', 'close']}
        
        # Analyze memory fragmentation
        fragmentation_report = optimizer.analyze_fragmentation(arrays)
        
        assert isinstance(fragmentation_report, dict)
        assert 'total_memory' in fragmentation_report
        assert 'fragmentation_ratio' in fragmentation_report
        assert 'recommendations' in fragmentation_report
    
    def test_pinned_memory_optimization(self, sample_data):
        """Test pinned memory for faster CPU-GPU transfers"""
        optimizer = MemoryOptimizer(use_pinned_memory=True)
        
        arrays = {'close': sample_data['close'].values.astype('float32')}
        
        # Create pinned memory arrays
        pinned_arrays = optimizer.create_pinned_arrays(arrays)
        
        # Check that arrays are optimized for transfer
        assert 'close' in pinned_arrays
        # Pinned memory specific checks would depend on implementation
    
    def test_transfer_bandwidth_monitoring(self, sample_data):
        """Test monitoring of CPU-GPU transfer bandwidth"""
        optimizer = MemoryOptimizer(monitor_bandwidth=True)
        
        arrays = {'close': sample_data['close'].values.astype('float32')}
        
        # Monitor transfer
        with patch('time.perf_counter') as mock_time:
            mock_time.side_effect = [0.0, 0.1]  # 100ms transfer
            
            bandwidth_stats = optimizer.monitor_transfer_bandwidth(
                arrays, backend='cupy'
            )
        
        assert isinstance(bandwidth_stats, dict)
        assert 'transfer_time' in bandwidth_stats
        assert 'data_size' in bandwidth_stats
        assert 'bandwidth_gbps' in bandwidth_stats
    
    def test_cache_aware_optimization(self, sample_data):
        """Test cache-aware memory optimization"""
        optimizer = MemoryOptimizer(cache_aware=True)
        
        arrays = {col: sample_data[col].values.astype('float32') 
                 for col in ['open', 'high', 'low', 'close']}
        
        # Optimize for cache efficiency
        cache_optimized = optimizer.optimize_for_cache(arrays)
        
        # Should return arrays optimized for CPU cache
        assert isinstance(cache_optimized, dict)
        for key, arr in cache_optimized.items():
            assert arr.flags['C_CONTIGUOUS']  # Cache-friendly layout
    
    def test_memory_pressure_handling(self, sample_data):
        """Test handling of memory pressure situations"""
        optimizer = MemoryOptimizer()
        
        # Simulate memory pressure
        large_arrays = {}
        for i in range(10):
            large_arrays[f'array_{i}'] = np.random.randn(100000).astype('float32')
        
        # Should handle memory pressure gracefully
        result = optimizer.handle_memory_pressure(
            large_arrays, 
            max_memory_gb=0.1  # Very low limit to trigger pressure
        )
        
        assert isinstance(result, dict)
        assert 'status' in result
        assert 'action_taken' in result
    
    def test_optimization_configuration(self):
        """Test optimization configuration validation"""
        # Valid configuration
        config = {
            'dtype': 'float32',
            'ensure_contiguous': True,
            'lazy_transfer': False,
            'use_pinned_memory': True,
            'enable_memory_pool': True
        }
        
        optimizer = MemoryOptimizer(**config)
        assert optimizer.config.dtype == 'float32'
        
        # Invalid configuration
        with pytest.raises(ValueError, match="Unsupported dtype"):
            MemoryOptimizer(dtype='float16')  # Not supported for technical indicators