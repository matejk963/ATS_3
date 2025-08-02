"""
Test Suite for GPU Memory Manager
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import Mock, patch, MagicMock
import warnings

from src.feature_engineering.gpu_memory_manager import (
    GPUMemoryProfiler, ChunkedDataProcessor, GPUMemoryManager,
    GPUMemoryInfo, ChunkingStrategy
)


class TestGPUMemoryProfiler:
    """Test GPU memory profiling functionality"""
    
    @patch('builtins.__import__', side_effect=ImportError)
    def test_init_without_cupy(self, mock_import):
        """Test initialization when CuPy is not available"""
        profiler = GPUMemoryProfiler()
        assert not profiler.gpu_available
        assert profiler.cupy_module is None
    
    @patch('cupy.cuda.MemoryPool')
    @patch('cupy.cuda.is_available', return_value=True)
    def test_init_with_cupy(self, mock_is_available, mock_memory_pool):
        """Test initialization when CuPy is available"""
        mock_pool = Mock()
        mock_memory_pool.return_value = mock_pool
        
        profiler = GPUMemoryProfiler()
        assert profiler.gpu_available
        mock_pool.free_all_blocks.assert_called_once()
    
    @patch('builtins.__import__', side_effect=ImportError)
    def test_get_memory_info_no_gpu(self, mock_import):
        """Test getting memory info when GPU is not available"""
        profiler = GPUMemoryProfiler()
        
        result = profiler.get_memory_info()
        assert result is None
    
    @patch('cupy.cuda.MemoryPool')
    @patch('cupy.cuda.is_available', return_value=True)
    def test_get_memory_info_with_gpu(self, mock_is_available, mock_memory_pool):
        """Test getting memory info when GPU is available"""
        # Setup mocks
        mock_pool = Mock()
        mock_memory_pool.return_value = mock_pool
        
        # Create profiler with GPU available
        profiler = GPUMemoryProfiler()
        
        # Mock the CuPy module directly
        profiler.cupy_module = Mock()
        profiler.cupy_module.cuda.runtime.memGetInfo.return_value = (8000000000, 16000000000)
        
        mock_device_instance = Mock()
        mock_device_instance.name = b'RTX 4080'
        mock_device_instance.compute_capability = (8, 6)
        profiler.cupy_module.cuda.Device.return_value = mock_device_instance
        
        result = profiler.get_memory_info()
        
        assert result is not None
        assert result.total_memory == 16000000000
        assert result.free_memory == 8000000000
        assert result.used_memory == 8000000000
        assert result.utilization == 0.5
        assert result.device_name == 'RTX 4080'
        assert result.compute_capability == (8, 6)
    
    @patch('builtins.__import__', side_effect=ImportError)
    def test_estimate_array_memory_usage(self, mock_import):
        """Test array memory usage estimation"""
        profiler = GPUMemoryProfiler()
        
        # Test float32 array
        memory = profiler.estimate_array_memory_usage((1000, 5), 'float32')
        assert memory == 1000 * 5 * 4  # 4 bytes per float32
        
        # Test float64 array
        memory = profiler.estimate_array_memory_usage((1000, 5), 'float64')
        assert memory == 1000 * 5 * 8  # 8 bytes per float64
    
    @patch('builtins.__import__', side_effect=ImportError)
    def test_estimate_computation_memory(self, mock_import):
        """Test computation memory estimation"""
        profiler = GPUMemoryProfiler()
        
        arrays = {
            'array1': np.ones((1000, 4), dtype='float32'),  # 16KB
            'array2': np.ones((1000, 2), dtype='float32')   # 8KB
        }
        
        # Total: 24KB, with 2.0 factor = 48KB
        estimated = profiler.estimate_computation_memory(arrays, 2.0)
        expected = (16000 + 8000) * 2
        assert estimated == expected
    
    @patch('builtins.__import__', side_effect=ImportError)
    def test_can_fit_in_memory_no_gpu(self, mock_import):
        """Test memory fitting check when GPU not available"""
        profiler = GPUMemoryProfiler()
        
        result = profiler.can_fit_in_memory(1000000)
        assert result is False
    
    @patch('cupy.cuda.MemoryPool')
    @patch('cupy.cuda.is_available', return_value=True)
    def test_can_fit_in_memory_with_gpu(self, mock_is_available, mock_memory_pool):
        """Test memory fitting check with GPU"""
        mock_pool = Mock()
        mock_memory_pool.return_value = mock_pool
        
        profiler = GPUMemoryProfiler()
        
        # Mock memory info
        memory_info = GPUMemoryInfo(
            total_memory=16000000000,  # 16GB
            free_memory=8000000000,    # 8GB
            used_memory=8000000000,    # 8GB
            utilization=0.5,
            device_name='RTX 4080',
            compute_capability=(8, 6)
        )
        
        profiler.get_memory_info = Mock(return_value=memory_info)
        
        # Test case that fits
        assert profiler.can_fit_in_memory(1000000000)  # 1GB
        
        # Test case that doesn't fit (too large)
        assert not profiler.can_fit_in_memory(10000000000)  # 10GB


class TestChunkedDataProcessor:
    """Test chunked data processing functionality"""
    
    @pytest.fixture
    def mock_profiler(self):
        """Create mock profiler for testing"""
        profiler = Mock(spec=GPUMemoryProfiler)
        profiler.gpu_available = True
        
        memory_info = GPUMemoryInfo(
            total_memory=16000000000,
            free_memory=8000000000,
            used_memory=8000000000,
            utilization=0.5,
            device_name='RTX 4080',
            compute_capability=(8, 6)
        )
        profiler.get_memory_info.return_value = memory_info
        profiler.estimate_array_memory_usage.return_value = 1000
        
        return profiler
    
    def test_chunking_strategy_validation(self):
        """Test chunking strategy parameter validation"""
        strategy = ChunkingStrategy(
            chunk_size=500,
            overlap_size=100,
            memory_threshold=0.8,
            min_chunk_size=1000,  # Larger than chunk_size
            max_chunk_size=10000,
            adaptive_sizing=True
        )
        
        # Should adjust chunk_size to min_chunk_size
        assert strategy.chunk_size == 1000
    
    def test_calculate_optimal_chunk_size_no_gpu(self, mock_profiler):
        """Test chunk size calculation when GPU not available"""
        mock_profiler.get_memory_info.return_value = None
        
        processor = ChunkedDataProcessor(mock_profiler)
        result = processor.calculate_optimal_chunk_size((10000, 5))
        
        # Should return default chunk size
        assert result == processor.strategy.chunk_size
    
    def test_calculate_optimal_chunk_size_with_gpu(self, mock_profiler):
        """Test chunk size calculation with GPU"""
        processor = ChunkedDataProcessor(mock_profiler, chunk_size=50000)
        
        result = processor.calculate_optimal_chunk_size((10000, 5))
        
        # Should calculate based on available memory
        assert isinstance(result, int)
        assert result >= processor.strategy.min_chunk_size
        assert result <= processor.strategy.max_chunk_size
    
    def test_create_chunks_small_data(self, mock_profiler):
        """Test chunk creation for small data that doesn't need chunking"""
        processor = ChunkedDataProcessor(mock_profiler)
        
        # Create small DataFrame
        data = pd.DataFrame({
            'open': np.random.randn(100),
            'high': np.random.randn(100),
            'low': np.random.randn(100),
            'close': np.random.randn(100)
        })
        
        chunks = list(processor.create_chunks(data, chunk_size=1000))
        
        assert len(chunks) == 1
        chunk_data, metadata = chunks[0]
        assert len(chunk_data) == 100
        assert metadata['total_chunks'] == 1
        assert metadata['chunk_id'] == 0
    
    def test_create_chunks_large_data(self, mock_profiler):
        """Test chunk creation for large data that needs chunking"""
        processor = ChunkedDataProcessor(mock_profiler, overlap_size=10)
        
        # Create large DataFrame
        data = pd.DataFrame({
            'open': np.random.randn(1000),
            'high': np.random.randn(1000),
            'low': np.random.randn(1000),
            'close': np.random.randn(1000)
        })
        
        chunks = list(processor.create_chunks(data, chunk_size=300))
        
        # Should have multiple chunks
        assert len(chunks) > 1
        
        # Check first chunk
        first_chunk, first_meta = chunks[0]
        assert not first_meta['has_leading_overlap']
        
        # Check middle chunk
        if len(chunks) > 2:
            middle_chunk, middle_meta = chunks[1]
            assert middle_meta['has_leading_overlap']
            assert middle_meta['has_trailing_overlap']
    
    def test_merge_chunk_results_single_chunk(self, mock_profiler):
        """Test merging results from single chunk"""
        processor = ChunkedDataProcessor(mock_profiler)
        
        result_df = pd.DataFrame({'value': [1, 2, 3, 4, 5]})
        metadata = {'chunk_id': 0, 'overlap_size': 0}
        
        chunk_results = [(result_df, metadata)]
        merged = processor.merge_chunk_results(chunk_results)
        
        pd.testing.assert_frame_equal(merged, result_df)
    
    def test_merge_chunk_results_multiple_chunks(self, mock_profiler):
        """Test merging results from multiple chunks with overlap"""
        processor = ChunkedDataProcessor(mock_profiler)
        
        # First chunk
        chunk1 = pd.DataFrame({'value': [1, 2, 3, 4, 5]})
        meta1 = {'chunk_id': 0, 'overlap_size': 2}
        
        # Second chunk with overlap
        chunk2 = pd.DataFrame({'value': [4, 5, 6, 7, 8]})
        meta2 = {'chunk_id': 1, 'overlap_size': 2}
        
        chunk_results = [(chunk1, meta1), (chunk2, meta2)]
        merged = processor.merge_chunk_results(chunk_results)
        
        # Should remove overlap from second chunk
        expected = pd.DataFrame({'value': [1, 2, 3, 4, 5, 6, 7, 8]})
        expected.index = range(len(expected))
        
        pd.testing.assert_frame_equal(merged, expected)


class TestGPUMemoryManager:
    """Test comprehensive GPU memory management"""
    
    @pytest.fixture
    def sample_data(self):
        """Create sample OHLCV data for testing"""
        size = 10000
        return pd.DataFrame({
            'open': np.random.uniform(100, 105, size),
            'high': np.random.uniform(104, 110, size),
            'low': np.random.uniform(95, 101, size),
            'close': np.random.uniform(99, 106, size),
            'volume': np.random.randint(1000, 10000, size)
        })
    
    @patch('src.technical_indicators.gpu_memory_manager.GPUMemoryProfiler')
    def test_init_with_memory_pool(self, mock_profiler_class):
        """Test initialization with memory pool optimization"""
        mock_profiler = Mock()
        mock_profiler.gpu_available = True
        mock_profiler.cupy_module = Mock()
        mock_profiler_class.return_value = mock_profiler
        
        manager = GPUMemoryManager(enable_memory_pool=True)
        
        assert manager.enable_memory_pool
        assert manager.profiler == mock_profiler
    
    @patch('src.technical_indicators.gpu_memory_manager.GPUMemoryProfiler')
    def test_should_use_chunking_no_gpu(self, mock_profiler_class, sample_data):
        """Test chunking decision when GPU not available"""
        mock_profiler = Mock()
        mock_profiler.gpu_available = False
        mock_profiler_class.return_value = mock_profiler
        
        manager = GPUMemoryManager()
        
        result = manager.should_use_chunking(sample_data)
        assert result is False
    
    @patch('src.technical_indicators.gpu_memory_manager.GPUMemoryProfiler')
    def test_should_use_chunking_fits_in_memory(self, mock_profiler_class, sample_data):
        """Test chunking decision when data fits in memory"""
        mock_profiler = Mock()
        mock_profiler.gpu_available = True
        mock_profiler.can_fit_in_memory.return_value = True
        mock_profiler_class.return_value = mock_profiler
        
        manager = GPUMemoryManager()
        
        result = manager.should_use_chunking(sample_data)
        assert result is False
    
    @patch('src.technical_indicators.gpu_memory_manager.GPUMemoryProfiler')
    def test_should_use_chunking_exceeds_memory(self, mock_profiler_class, sample_data):
        """Test chunking decision when data exceeds memory"""
        mock_profiler = Mock()
        mock_profiler.gpu_available = True
        mock_profiler.can_fit_in_memory.return_value = False
        mock_profiler.estimate_computation_memory.return_value = 1000000000
        mock_profiler_class.return_value = mock_profiler
        
        manager = GPUMemoryManager()
        
        result = manager.should_use_chunking(sample_data)
        assert result is True
    
    @patch('src.technical_indicators.gpu_memory_manager.GPUMemoryProfiler')
    def test_process_with_memory_management_no_chunking(self, mock_profiler_class, sample_data):
        """Test processing without chunking"""
        mock_profiler = Mock()
        mock_profiler_class.return_value = mock_profiler
        
        manager = GPUMemoryManager()
        manager.should_use_chunking = Mock(return_value=False)
        
        # Mock computation function
        def mock_computation(data):
            return data.copy()
        
        with patch.object(manager.profiler, 'memory_monitor'):
            result = manager.process_with_memory_management(
                sample_data, mock_computation
            )
            
        pd.testing.assert_frame_equal(result, sample_data)
    
    @patch('src.technical_indicators.gpu_memory_manager.GPUMemoryProfiler')
    def test_process_with_memory_management_with_chunking(self, mock_profiler_class, sample_data):
        """Test processing with chunking"""
        mock_profiler = Mock()
        mock_profiler_class.return_value = mock_profiler
        
        manager = GPUMemoryManager()
        manager.should_use_chunking = Mock(return_value=True)
        
        # Mock the processor to return chunks
        mock_chunks = [
            (sample_data.iloc[:5000], {'chunk_id': 0, 'total_chunks': 2}),
            (sample_data.iloc[4950:], {'chunk_id': 1, 'total_chunks': 2})  # Overlap
        ]
        manager.processor.create_chunks = Mock(return_value=iter(mock_chunks))
        
        # Mock merge function
        manager.processor.merge_chunk_results = Mock(return_value=sample_data)
        
        def mock_computation(data):
            return data.copy()
        
        with patch.object(manager.profiler, 'memory_monitor'):
            result = manager.process_with_memory_management(
                sample_data, mock_computation
            )
        
        # Should have called merge_chunk_results
        manager.processor.merge_chunk_results.assert_called_once()
        pd.testing.assert_frame_equal(result, sample_data)
    
    @patch('src.technical_indicators.gpu_memory_manager.GPUMemoryProfiler')
    def test_get_memory_statistics_no_gpu(self, mock_profiler_class):
        """Test memory statistics when GPU not available"""
        mock_profiler = Mock()
        mock_profiler.gpu_available = False
        mock_profiler.get_memory_info.return_value = None
        mock_profiler_class.return_value = mock_profiler
        
        manager = GPUMemoryManager()
        
        stats = manager.get_memory_statistics()
        
        assert stats['gpu_available'] is False
        assert stats['memory_info'] is None
        assert 'chunking_strategy' in stats
    
    @patch('src.technical_indicators.gpu_memory_manager.GPUMemoryProfiler')
    def test_get_memory_statistics_with_gpu(self, mock_profiler_class):
        """Test memory statistics with GPU"""
        mock_profiler = Mock()
        mock_profiler.gpu_available = True
        mock_profiler_class.return_value = mock_profiler
        
        manager = GPUMemoryManager()
        
        memory_info = GPUMemoryInfo(
            total_memory=16000000000,
            free_memory=8000000000,
            used_memory=8000000000,
            utilization=0.5,
            device_name='RTX 4080',
            compute_capability=(8, 6)
        )
        manager.profiler.get_memory_info.return_value = memory_info
        
        stats = manager.get_memory_statistics()
        
        assert stats['gpu_available'] is True
        assert stats['memory_utilization_pct'] == 50.0
        assert stats['free_memory_gb'] == 8.0
        assert stats['total_memory_gb'] == 16.0
        assert stats['device_name'] == 'RTX 4080'
    
    @patch('src.technical_indicators.gpu_memory_manager.GPUMemoryProfiler')
    def test_clear_gpu_cache_no_gpu(self, mock_profiler_class):
        """Test clearing cache when GPU not available"""
        mock_profiler = Mock()
        mock_profiler.gpu_available = False
        mock_profiler_class.return_value = mock_profiler
        
        manager = GPUMemoryManager()
        
        # Should not raise exception
        manager.clear_gpu_cache()
    
    @patch('src.technical_indicators.gpu_memory_manager.GPUMemoryProfiler')
    def test_clear_gpu_cache_with_gpu(self, mock_profiler_class):
        """Test clearing cache with GPU"""
        mock_profiler = Mock()
        mock_profiler.gpu_available = True
        mock_profiler_class.return_value = mock_profiler
        
        manager = GPUMemoryManager()
        
        mock_memory_pool = Mock()
        manager.profiler.cupy_module = Mock()
        manager.profiler.cupy_module.cuda.MemoryPool.return_value = mock_memory_pool
        
        manager.clear_gpu_cache()
        
        mock_memory_pool.free_all_blocks.assert_called_once()
    
    @patch('src.technical_indicators.gpu_memory_manager.GPUMemoryProfiler')
    def test_memory_managed_context(self, mock_profiler_class):
        """Test memory managed context manager"""
        mock_profiler = Mock()
        mock_profiler.gpu_available = True
        mock_profiler_class.return_value = mock_profiler
        
        manager = GPUMemoryManager()
        
        mock_memory_pool = Mock()
        manager.profiler.cupy_module = Mock()
        manager.profiler.cupy_module.cuda.MemoryPool.return_value = mock_memory_pool
        
        with patch.object(manager.profiler, 'memory_monitor') as mock_monitor:
            mock_monitor.return_value.__enter__ = Mock()
            mock_monitor.return_value.__exit__ = Mock()
            
            with manager.memory_managed_context("Test Operation") as ctx:
                assert ctx == manager
            
            # Should have cleaned up memory
            mock_memory_pool.free_all_blocks.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])