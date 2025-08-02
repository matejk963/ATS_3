"""
Tests for async processing pipeline with parallel GPU workers and concurrent I/O
"""

import pytest
import asyncio
import time
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
import pandas as pd
import numpy as np

from src.gpu_parallel_processing.async_processing_pipeline import (
    AsyncProcessingPipeline, 
    ProcessingTask, 
    ProcessingResult
)

class TestProcessingTask:
    """Test ProcessingTask dataclass"""
    
    def test_processing_task_creation(self):
        """Test ProcessingTask creation with default values"""
        contract_data = pd.DataFrame({'close': [100, 101, 102]})
        combination = {'combo_id': 1, 'param1': 10, 'param2': 20}
        
        task = ProcessingTask(
            task_id="test_task_1",
            combo_id=1,
            contract_data=contract_data,
            combination=combination
        )
        
        assert task.task_id == "test_task_1"
        assert task.combo_id == 1
        assert task.priority == 1
        assert task.attempts == 0
        assert task.max_attempts == 3
        assert task.created_at is not None
        assert isinstance(task.contract_data, pd.DataFrame)
    
    def test_processing_task_with_custom_values(self):
        """Test ProcessingTask with custom values"""
        contract_data = pd.DataFrame({'close': [100, 101, 102]})
        combination = {'combo_id': 2, 'param1': 15}
        created_time = time.time()
        
        task = ProcessingTask(
            task_id="test_task_2",
            combo_id=2,
            contract_data=contract_data,
            combination=combination,
            priority=2,
            created_at=created_time,
            attempts=1,
            max_attempts=5
        )
        
        assert task.priority == 2
        assert task.created_at == created_time
        assert task.attempts == 1
        assert task.max_attempts == 5

class TestProcessingResult:
    """Test ProcessingResult dataclass"""
    
    def test_successful_result_creation(self):
        """Test creating successful processing result"""
        result_data = pd.DataFrame({'signal': [1, 0, -1]})
        metadata = {'param1': 10, 'processing_stats': {}}
        memory_stats = {'gpu_memory_used': 1024}
        
        result = ProcessingResult(
            task_id="test_task_1",
            combo_id=1,
            success=True,
            result_data=result_data,
            metadata=metadata,
            processing_time=1.5,
            worker_id="GPU-0",
            memory_stats=memory_stats
        )
        
        assert result.success is True
        assert result.combo_id == 1
        assert result.processing_time == 1.5
        assert result.worker_id == "GPU-0"
        assert result.error_message is None
        assert isinstance(result.result_data, pd.DataFrame)
    
    def test_failed_result_creation(self):
        """Test creating failed processing result"""
        result = ProcessingResult(
            task_id="test_task_2",
            combo_id=2,
            success=False,
            processing_time=0.5,
            error_message="GPU memory error",
            worker_id="GPU-1"
        )
        
        assert result.success is False
        assert result.error_message == "GPU memory error"
        assert result.result_data is None
        assert result.metadata is None

class TestAsyncProcessingPipeline:
    """Test AsyncProcessingPipeline functionality"""
    
    @pytest.fixture
    def temp_output_dir(self):
        """Create temporary output directory"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def sample_contract_data(self):
        """Create sample contract data"""
        return pd.DataFrame({
            'open': np.random.random(1000) * 100,
            'high': np.random.random(1000) * 100,
            'low': np.random.random(1000) * 100,
            'close': np.random.random(1000) * 100,
            'volume': np.random.random(1000) * 1000
        })
    
    @pytest.fixture
    def sample_combinations(self):
        """Create sample parameter combinations"""
        return [
            {'combo_id': i, 'param1': i * 10, 'param2': i * 20}
            for i in range(1, 6)
        ]
    
    @pytest.fixture
    def mock_gpu_processor(self):
        """Create mock GPU processor"""
        processor = Mock()
        processor.process_contract_combinations_sustained = Mock(return_value=[{
            'result_data': pd.DataFrame({'signal': [1, 0, -1]}),
            'metadata': {'param1': 10, 'memory_stats': {'gpu_memory': 1024}}
        }])
        return processor
    
    def test_pipeline_initialization(self, temp_output_dir):
        """Test pipeline initialization"""
        pipeline = AsyncProcessingPipeline(
            max_gpu_workers=2,
            max_io_workers=1,
            task_queue_size=10,
            result_buffer_size=5,
            output_directory=temp_output_dir
        )
        
        assert pipeline.max_gpu_workers == 2
        assert pipeline.max_io_workers == 1
        assert pipeline.task_queue_size == 10
        assert pipeline.result_buffer_size == 5
        assert pipeline.output_directory == Path(temp_output_dir)
        assert pipeline.pipeline_active is False
        assert pipeline.shutdown_requested is False
    
    @pytest.mark.asyncio
    async def test_queue_initialization(self, temp_output_dir):
        """Test async queue initialization"""
        pipeline = AsyncProcessingPipeline(output_directory=temp_output_dir)
        
        await pipeline._initialize_queues()
        
        assert pipeline.task_queue is not None
        assert pipeline.result_queue is not None
        assert pipeline.io_queue is not None
        assert pipeline.task_queue.maxsize == pipeline.task_queue_size
    
    @pytest.mark.asyncio
    async def test_task_submission(self, temp_output_dir, sample_contract_data, sample_combinations):
        """Test task submission to queue"""
        pipeline = AsyncProcessingPipeline(output_directory=temp_output_dir)
        await pipeline._initialize_queues()
        
        await pipeline._submit_tasks(sample_combinations, sample_contract_data)
        
        assert pipeline.pipeline_stats['tasks_submitted'] == len(sample_combinations)
        assert pipeline.task_queue.qsize() == len(sample_combinations)
        
        # Verify first task
        task = await pipeline.task_queue.get()
        assert task.combo_id == 1
        assert task.task_id == "task_1"
        assert isinstance(task.contract_data, pd.DataFrame)
    
    def test_write_result_to_disk(self, temp_output_dir):
        """Test writing results to disk"""
        pipeline = AsyncProcessingPipeline(output_directory=temp_output_dir)
        
        result_data = pd.DataFrame({'signal': [1, 0, -1], 'price': [100, 101, 102]})
        result = ProcessingResult(
            task_id="test_task_1",
            combo_id=1,
            success=True,
            result_data=result_data,
            metadata={'param1': 10},
            processing_time=1.5,
            worker_id="GPU-0",
            memory_stats={'gpu_memory': 1024}
        )
        
        pipeline._write_result_to_disk(result)
        
        # Check files were created
        result_file = Path(temp_output_dir) / "combo_000001.parquet"
        metadata_file = Path(temp_output_dir) / "combo_000001_metadata.json"
        
        assert result_file.exists()
        assert metadata_file.exists()
        
        # Verify content
        loaded_data = pd.read_parquet(result_file)
        assert len(loaded_data) == 3
        assert 'signal' in loaded_data.columns
        
        import json
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
        assert metadata['combo_id'] == 1
        assert metadata['processing_time'] == 1.5
        assert metadata['worker_id'] == "GPU-0"
    
    @pytest.mark.asyncio
    async def test_small_batch_processing(self, temp_output_dir, sample_contract_data, mock_gpu_processor):
        """Test processing small batch of combinations"""
        pipeline = AsyncProcessingPipeline(
            max_gpu_workers=2,
            max_io_workers=1,
            output_directory=temp_output_dir
        )
        
        # Create small set of combinations
        combinations = [
            {'combo_id': 1, 'param1': 10},
            {'combo_id': 2, 'param1': 20}
        ]
        
        results = []
        async for result in pipeline.process_combinations_async(
            mock_gpu_processor,
            combinations,
            sample_contract_data
        ):
            results.append(result)
        
        assert len(results) == 2
        assert all(isinstance(r, ProcessingResult) for r in results)
        assert all(r.success for r in results)
        
        # Verify statistics
        stats = pipeline.get_pipeline_statistics()
        assert stats['tasks_completed'] == 2
        assert stats['tasks_failed'] == 0
        assert stats['success_rate_percent'] == 100.0
    
    @pytest.mark.asyncio
    async def test_error_handling_and_retry(self, temp_output_dir, sample_contract_data):
        """Test error handling and retry mechanism"""
        # Create mock processor that fails initially
        failing_processor = Mock()
        call_count = 0
        
        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # Fail first 2 calls
                raise Exception("GPU processing failed")
            else:  # Succeed on retry
                return [{
                    'result_data': pd.DataFrame({'signal': [1]}),
                    'metadata': {'memory_stats': {}}
                }]
        
        failing_processor.process_contract_combinations_sustained = Mock(side_effect=side_effect)
        
        pipeline = AsyncProcessingPipeline(
            max_gpu_workers=1,
            max_io_workers=1,
            output_directory=temp_output_dir
        )
        
        combinations = [{'combo_id': 1, 'param1': 10}]
        
        results = []
        async for result in pipeline.process_combinations_async(
            failing_processor,
            combinations,
            sample_contract_data
        ):
            results.append(result)
        
        # Should eventually succeed after retries
        stats = pipeline.get_pipeline_statistics()
        assert stats['tasks_retried'] > 0
    
    def test_get_pipeline_statistics(self, temp_output_dir):
        """Test pipeline statistics calculation"""
        pipeline = AsyncProcessingPipeline(output_directory=temp_output_dir)
        
        # Set some test statistics
        pipeline.pipeline_stats.update({
            'tasks_submitted': 10,
            'tasks_completed': 8,
            'tasks_failed': 2,
            'tasks_retried': 1,
            'results_written': 8,
            'pipeline_start_time': time.time() - 60,  # 1 minute ago
            'total_processing_time': 45.0,
            'total_io_time': 10.0,
            'concurrent_tasks_peak': 3
        })
        
        stats = pipeline.get_pipeline_statistics()
        
        assert stats['tasks_submitted'] == 10
        assert stats['tasks_completed'] == 8
        assert stats['tasks_failed'] == 2
        assert stats['success_rate_percent'] == 80.0
        assert stats['average_processing_time'] == 45.0 / 8
        assert stats['throughput_combinations_per_minute'] > 0
        assert 0 <= stats['gpu_efficiency_percent'] <= 200  # Can exceed 100% with multiple workers
        assert 0 <= stats['io_efficiency_percent'] <= 200
    
    def test_cleanup(self, temp_output_dir):
        """Test pipeline cleanup"""
        pipeline = AsyncProcessingPipeline(output_directory=temp_output_dir)
        
        # Verify executors are running
        assert not pipeline.gpu_executor._shutdown
        assert not pipeline.io_executor._shutdown
        
        pipeline.cleanup()
        
        # Verify cleanup
        assert pipeline.gpu_executor._shutdown
        assert pipeline.io_executor._shutdown
        assert pipeline.pipeline_active is False
        assert len(pipeline.result_buffer) == 0

@pytest.mark.asyncio
async def test_pipeline_performance_characteristics():
    """Test that pipeline shows performance characteristics of async processing"""
    # This test verifies the pipeline can handle concurrent operations
    # without detailed GPU processor integration
    
    import tempfile
    import shutil
    temp_output_dir = tempfile.mkdtemp()
    
    try:
        pipeline = AsyncProcessingPipeline(
            max_gpu_workers=2,
            max_io_workers=1,
            output_directory=temp_output_dir
        )
        
        # Mock processor with realistic timing
        mock_processor = Mock()
        
        async def mock_process(*args, **kwargs):
            await asyncio.sleep(0.1)  # Simulate processing time
            return [{
                'result_data': pd.DataFrame({'signal': [1, 0]}),
                'metadata': {'memory_stats': {}}
            }]
        
        # Use run_in_executor simulation
        original_run_in_executor = asyncio.get_event_loop().run_in_executor
        
        def mock_run_in_executor(executor, func, *args, **kwargs):
            if func == mock_processor.process_contract_combinations_sustained:
                return mock_process()
            return original_run_in_executor(executor, func, *args, **kwargs)
    
        with patch.object(asyncio.get_event_loop(), 'run_in_executor', side_effect=mock_run_in_executor):
            mock_processor.process_contract_combinations_sustained = Mock()
            
            contract_data = pd.DataFrame({'close': [100, 101, 102]})
            combinations = [{'combo_id': i, 'param1': i * 10} for i in range(1, 5)]
            
            start_time = time.time()
            
            results = []
            async for result in pipeline.process_combinations_async(
                mock_processor,
                combinations,
                contract_data
            ):
                results.append(result)
            
            end_time = time.time()
            
            # With 2 workers and 4 combinations, should process faster than sequential
            # Sequential would take ~0.4s (4 * 0.1s), parallel should be ~0.2s (2 batches * 0.1s)
            processing_time = end_time - start_time
            
            assert len(results) == 4
            assert all(r.success for r in results)
            
            # Verify concurrent execution benefits (allowing for overhead)
            assert processing_time < 0.35  # Should be significantly faster than sequential
            
            stats = pipeline.get_pipeline_statistics()
            assert stats['tasks_completed'] == 4
            assert stats['concurrent_tasks_peak'] >= 1
    
    finally:
        shutil.rmtree(temp_output_dir)

if __name__ == "__main__":
    pytest.main([__file__, "-v"])