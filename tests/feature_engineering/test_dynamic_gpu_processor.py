"""
Tests for Dynamic GPU Resource Management
Following Phase 3.2 implementation recommendations for adaptive batch sizing and GPU utilization optimization.
"""
import pytest
import numpy as np
import pandas as pd
from unittest.mock import Mock, patch, MagicMock
import cupy as cp


class TestDynamicGPUBatchProcessor:
    """Test suite for DynamicGPUBatchProcessor class"""
    
    def test_initialization_with_default_targets(self):
        """Test DynamicGPUBatchProcessor initializes with default target utilization values"""
        # This test will fail initially - we need to implement the class
        from src.feature_engineering.dynamic_gpu_processor import DynamicGPUBatchProcessor
        
        processor = DynamicGPUBatchProcessor()
        
        assert processor.target_memory_usage == 0.80
        assert processor.target_core_usage == 0.85
        assert processor.current_batch_size == 10000
        assert processor.pipeline is not None

    def test_initialization_with_custom_targets(self):
        """Test DynamicGPUBatchProcessor initializes with custom target values"""
        from src.feature_engineering.dynamic_gpu_processor import DynamicGPUBatchProcessor
        
        processor = DynamicGPUBatchProcessor(target_memory_usage=0.90, target_core_usage=0.95)
        
        assert processor.target_memory_usage == 0.90
        assert processor.target_core_usage == 0.95

    @patch('pynvml.nvmlInit')
    @patch('pynvml.nvmlDeviceGetHandleByIndex')
    @patch('pynvml.nvmlDeviceGetMemoryInfo')
    def test_calculate_optimal_batch_size(self, mock_memory_info, mock_get_handle, mock_init):
        """Test optimal batch size calculation based on GPU memory availability"""
        from src.feature_engineering.dynamic_gpu_processor import DynamicGPUBatchProcessor
        
        # Mock GPU memory info
        mock_memory = Mock()
        mock_memory.total = 17179869184  # 16GB in bytes
        mock_memory_info.return_value = mock_memory
        
        processor = DynamicGPUBatchProcessor(target_memory_usage=0.80)
        
        optimal_size = processor.calculate_optimal_batch_size(100000)
        
        expected_available_memory = 17179869184 * 0.80
        expected_batch_size = int(expected_available_memory / 42)  # 42 bytes per point
        expected_batch_size = min(max(expected_batch_size, 1000), 100000)
        
        assert optimal_size == expected_batch_size

    @patch('pynvml.nvmlInit')
    @patch('pynvml.nvmlDeviceGetHandleByIndex')
    def test_process_with_dynamic_batching(self, mock_get_handle, mock_init):
        """Test dynamic batching processes data with automatically adjusted batch sizes"""
        from src.feature_engineering.dynamic_gpu_processor import DynamicGPUBatchProcessor
        
        # Create sample data
        data = pd.DataFrame({
            'open': np.random.random(50000),
            'high': np.random.random(50000),
            'low': np.random.random(50000),
            'close': np.random.random(50000),
            'volume': np.random.randint(1000, 10000, 50000)
        })
        
        processor = DynamicGPUBatchProcessor()
        
        # Mock the pipeline and its methods
        processor.pipeline = Mock()
        processor.pipeline.compute_indicators.return_value = {'macd': np.random.random(10000), 'atr': np.random.random(10000)}
        
        # Mock calculate_optimal_batch_size to return a fixed size
        processor.calculate_optimal_batch_size = Mock(return_value=10000)
        processor._monitor_and_adjust = Mock()
        processor._combine_results = Mock(return_value={'macd': np.random.random(50000), 'atr': np.random.random(50000)})
        
        result = processor.process_with_dynamic_batching(data)
        
        # Verify the pipeline was called with batches
        assert processor.pipeline.compute_indicators.call_count == 5  # 50000 / 10000 = 5 batches
        assert processor._monitor_and_adjust.call_count == 5
        assert result is not None

    @patch('pynvml.nvmlDeviceGetMemoryInfo')
    @patch('pynvml.nvmlDeviceGetUtilizationRates')
    def test_monitor_and_adjust_increases_batch_size(self, mock_util, mock_memory, setup_processor):
        """Test monitoring increases batch size when GPU utilization is below target"""
        from src.feature_engineering.dynamic_gpu_processor import DynamicGPUBatchProcessor
        
        processor = DynamicGPUBatchProcessor(target_memory_usage=0.80)
        processor.current_batch_size = 10000
        processor.gpu_handle = Mock()
        
        # Mock low utilization
        mock_memory_info = Mock()
        mock_memory_info.used = 5000000000  # 5GB used
        mock_memory_info.total = 17179869184  # 16GB total (used/total = 0.29, below 0.80 * 0.9 = 0.72)
        mock_memory.return_value = mock_memory_info
        
        mock_util_rates = Mock()
        mock_util_rates.gpu = 50  # 50% core utilization
        mock_util.return_value = mock_util_rates
        
        processor._monitor_and_adjust()
        
        # Batch size should increase
        assert processor.current_batch_size == 11000  # 10000 * 1.1

    @patch('pynvml.nvmlDeviceGetMemoryInfo')
    @patch('pynvml.nvmlDeviceGetUtilizationRates')
    def test_monitor_and_adjust_decreases_batch_size(self, mock_util, mock_memory, setup_processor):
        """Test monitoring decreases batch size when GPU utilization exceeds target"""
        from src.feature_engineering.dynamic_gpu_processor import DynamicGPUBatchProcessor
        
        processor = DynamicGPUBatchProcessor(target_memory_usage=0.80)
        processor.current_batch_size = 10000
        processor.gpu_handle = Mock()
        
        # Mock high utilization
        mock_memory_info = Mock()
        mock_memory_info.used = 15000000000  # 15GB used
        mock_memory_info.total = 17179869184  # 16GB total (used/total = 0.87, above 0.80)
        mock_memory.return_value = mock_memory_info
        
        mock_util_rates = Mock()
        mock_util_rates.gpu = 95  # 95% core utilization
        mock_util.return_value = mock_util_rates
        
        processor._monitor_and_adjust()
        
        # Batch size should decrease
        assert processor.current_batch_size == 9000  # 10000 * 0.9

    @pytest.fixture
    def setup_processor(self):
        """Setup processor with mocked GPU components"""
        with patch('pynvml.nvmlInit'), \
             patch('pynvml.nvmlDeviceGetHandleByIndex'):
            from src.feature_engineering.dynamic_gpu_processor import DynamicGPUBatchProcessor
            return DynamicGPUBatchProcessor()


class TestContinuousIndicatorProcessor:
    """Test suite for ContinuousIndicatorProcessor class"""
    
    def test_initialization(self):
        """Test ContinuousIndicatorProcessor initializes correctly"""
        from src.feature_engineering.dynamic_gpu_processor import ContinuousIndicatorProcessor
        
        processor = ContinuousIndicatorProcessor(target_gpu_usage=0.85)
        
        assert processor.target_gpu_usage == 0.85
        assert processor.processing_queue == []
        assert processor.gpu_keep_alive is True

    def test_process_streaming_data_with_mock_stream(self):
        """Test streaming data processing with mock data stream"""
        from src.feature_engineering.dynamic_gpu_processor import ContinuousIndicatorProcessor
        
        # Mock data stream
        mock_data_stream = [
            pd.DataFrame({'close': np.random.random(1000)}) for _ in range(3)
        ]
        
        processor = ContinuousIndicatorProcessor()
        processor.batch_processor = Mock()
        processor.batch_processor.process_with_dynamic_batching.return_value = {'result': 'processed'}
        
        # Process the stream by consuming a limited number of results
        stream_generator = processor.process_streaming_data(iter(mock_data_stream))
        results = []
        for i, result in enumerate(stream_generator):
            results.append(result)
            if i >= 2:  # Only take 3 results to avoid infinite loop
                break
        
        # Verify processing was called and results returned
        assert processor.batch_processor.process_with_dynamic_batching.call_count == 3
        assert len(results) == 3


class TestAdaptiveRealTimeProcessor:
    """Test suite for AdaptiveRealTimeProcessor class"""
    
    def test_initialization(self):
        """Test AdaptiveRealTimeProcessor initializes with correct components"""
        from src.feature_engineering.dynamic_gpu_processor import AdaptiveRealTimeProcessor
        
        processor = AdaptiveRealTimeProcessor(target_memory_usage=0.85, target_core_usage=0.90)
        
        assert processor.batch_processor is not None
        assert processor.performance_monitor is not None

    def test_process_live_feed_processes_data_chunks(self):
        """Test live feed processing handles market data streams correctly"""
        from src.feature_engineering.dynamic_gpu_processor import AdaptiveRealTimeProcessor
        
        # Mock market data stream
        mock_market_data = [
            pd.DataFrame({'close': np.random.random(500)}) for _ in range(2)
        ]
        
        processor = AdaptiveRealTimeProcessor()
        processor.batch_processor = Mock()
        processor.batch_processor.create_optimal_batches.return_value = [
            pd.DataFrame({'close': np.random.random(250)}) for _ in range(2)
        ]
        processor.batch_processor.process_with_dynamic_batching.return_value = {'result': 'processed'}
        processor.performance_monitor = Mock()
        
        # Consume the generator to trigger processing
        results = list(processor.process_live_feed(mock_market_data))
        
        # Verify processing components were called
        assert processor.batch_processor.create_optimal_batches.call_count == 2
        assert processor.batch_processor.process_with_dynamic_batching.call_count == 4  # 2 chunks * 2 batches each
        assert processor.performance_monitor.log_utilization.call_count == 4
        assert len(results) == 4  # 2 chunks * 2 batches each