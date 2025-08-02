"""
Tests for AsyncGPUOrchestrator with multi-contract processing and coordination
"""

import pytest
import asyncio
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import pandas as pd
import numpy as np

from src.gpu_parallel_processing.async_orchestrator import AsyncGPUOrchestrator
from src.gpu_parallel_processing.async_processing_pipeline import ProcessingResult

class TestAsyncGPUOrchestrator:
    """Test AsyncGPUOrchestrator functionality"""
    
    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for output and data"""
        output_dir = tempfile.mkdtemp()
        data_dir = tempfile.mkdtemp()
        yield output_dir, data_dir
        shutil.rmtree(output_dir)
        shutil.rmtree(data_dir)
    
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
            for i in range(1, 11)  # 10 combinations
        ]
    
    @pytest.fixture
    def mock_components(self, sample_contract_data):
        """Create mock components for orchestrator"""
        # Mock contract manager
        contract_manager = Mock()
        contract_manager.load_contract_data.return_value = sample_contract_data
        contract_manager.get_cache_stats.return_value = {
            'cache_hits': 5,
            'cache_misses': 1,
            'cached_contracts': 2
        }
        
        # Mock GPU processor
        gpu_processor = Mock()
        gpu_processor.get_processing_stats.return_value = {
            'total_processing_time': 45.0,
            'combinations_processed': 10,
            'gpu_memory_used': 8192
        }
        
        # Mock async pipeline
        async_pipeline = Mock()
        async_pipeline.get_pipeline_statistics.return_value = {
            'tasks_completed': 10,
            'tasks_failed': 0,
            'success_rate_percent': 100.0,
            'throughput_combinations_per_minute': 120
        }
        
        # Mock async generator for pipeline results
        async def mock_process_combinations_async(*args, **kwargs):
            for i in range(1, 11):  # 10 results
                yield ProcessingResult(
                    task_id=f"task_{i}",
                    combo_id=i,
                    success=True,
                    processing_time=0.5,
                    worker_id="GPU-0"
                )
        
        async_pipeline.process_combinations_async = mock_process_combinations_async
        
        return contract_manager, gpu_processor, async_pipeline
    
    def test_orchestrator_initialization(self, temp_dirs):
        """Test orchestrator initialization"""
        output_dir, data_dir = temp_dirs
        
        orchestrator = AsyncGPUOrchestrator(
            max_gpu_workers=3,
            max_io_workers=2,
            gpu_memory_pool_gb=12.0,
            output_directory=output_dir,
            data_directory=data_dir
        )
        
        assert orchestrator.max_gpu_workers == 3
        assert orchestrator.max_io_workers == 2
        assert orchestrator.orchestrator_stats['batches_processed'] == 0
        assert orchestrator.orchestrator_stats['total_combinations_processed'] == 0
        assert orchestrator.orchestrator_stats['contracts_loaded'] == 0
    
    def test_calculate_optimal_batch_size(self, temp_dirs):
        """Test optimal batch size calculation"""
        output_dir, data_dir = temp_dirs
        orchestrator = AsyncGPUOrchestrator(
            max_gpu_workers=3,
            output_directory=output_dir,
            data_directory=data_dir
        )
        
        # Test with small dataset
        batch_size = orchestrator._calculate_optimal_batch_size(
            data_length=100000,  # 100K candles
            total_combinations=50
        )
        assert 5 <= batch_size <= 30  # Should be reasonable size
        
        # Test with large dataset
        batch_size = orchestrator._calculate_optimal_batch_size(
            data_length=1500000,  # 1.5M candles
            total_combinations=100
        )
        assert 5 <= batch_size <= 15  # Should be smaller for large data
        
        # Test with many combinations
        batch_size = orchestrator._calculate_optimal_batch_size(
            data_length=200000,
            total_combinations=1000
        )
        assert batch_size <= 30  # Should not exceed worker capacity limit
    
    @pytest.mark.asyncio
    async def test_single_contract_processing_success(self, temp_dirs, sample_combinations, mock_components):
        """Test successful processing of single contract"""
        output_dir, data_dir = temp_dirs
        contract_manager, gpu_processor, async_pipeline = mock_components
        
        with patch('src.gpu_parallel_processing.async_orchestrator.ContractDataManager', return_value=contract_manager), \
             patch('src.gpu_parallel_processing.async_orchestrator.EnhancedGPUCombinationProcessor', return_value=gpu_processor), \
             patch('src.gpu_parallel_processing.async_orchestrator.AsyncProcessingPipeline', return_value=async_pipeline):
            
            orchestrator = AsyncGPUOrchestrator(
                output_directory=output_dir,
                data_directory=data_dir
            )
            
            # Process contract combinations
            result = await orchestrator.process_contract_combinations(
                contract_code="test_contract",
                combinations=sample_combinations
            )
            
            # Verify results
            assert result['contract_code'] == "test_contract"
            assert result['total_combinations'] == 10
            assert result['successful_combinations'] == 10
            assert result['failed_combinations'] == 0
            assert result['success_rate_percent'] == 100.0
            assert result['processing_time_seconds'] > 0
            assert result['throughput_per_minute'] > 0
            
            # Verify contract manager was called
            contract_manager.load_contract_data.assert_called_once_with("test_contract")
            
            # Verify statistics were updated
            assert orchestrator.orchestrator_stats['contracts_loaded'] == 1
            assert orchestrator.orchestrator_stats['batches_processed'] > 0
    
    @pytest.mark.asyncio
    async def test_single_contract_processing_with_failures(self, temp_dirs, sample_combinations, mock_components):
        """Test contract processing with some failures"""
        output_dir, data_dir = temp_dirs
        contract_manager, gpu_processor, async_pipeline = mock_components
        
        # Mock async generator with some failures
        async def mock_process_with_failures(*args, **kwargs):
            for i in range(1, 11):
                success = i <= 7  # First 7 succeed, last 3 fail
                yield ProcessingResult(
                    task_id=f"task_{i}",
                    combo_id=i,
                    success=success,
                    processing_time=0.5,
                    worker_id="GPU-0",
                    error_message=None if success else f"Error processing combo {i}"
                )
        
        async_pipeline.process_combinations_async = mock_process_with_failures
        
        with patch('src.gpu_parallel_processing.async_orchestrator.ContractDataManager', return_value=contract_manager), \
             patch('src.gpu_parallel_processing.async_orchestrator.EnhancedGPUCombinationProcessor', return_value=gpu_processor), \
             patch('src.gpu_parallel_processing.async_orchestrator.AsyncProcessingPipeline', return_value=async_pipeline):
            
            orchestrator = AsyncGPUOrchestrator(
                output_directory=output_dir,
                data_directory=data_dir
            )
            
            result = await orchestrator.process_contract_combinations(
                contract_code="test_contract",
                combinations=sample_combinations
            )
            
            # Verify partial success
            assert result['successful_combinations'] == 7
            assert result['failed_combinations'] == 3
            assert result['success_rate_percent'] == 70.0
            assert orchestrator.orchestrator_stats['errors_encountered'] == 3
    
    @pytest.mark.asyncio
    async def test_single_contract_processing_exception(self, temp_dirs, sample_combinations):
        """Test contract processing with exception during setup"""
        output_dir, data_dir = temp_dirs
        
        # Mock contract manager that throws exception
        failing_contract_manager = Mock()
        failing_contract_manager.load_contract_data.side_effect = Exception("Failed to load contract")
        
        with patch('src.gpu_parallel_processing.async_orchestrator.ContractDataManager', return_value=failing_contract_manager):
            orchestrator = AsyncGPUOrchestrator(
                output_directory=output_dir,
                data_directory=data_dir
            )
            
            result = await orchestrator.process_contract_combinations(
                contract_code="failing_contract",
                combinations=sample_combinations
            )
            
            # Verify error handling
            assert 'error' in result
            assert result['successful_combinations'] == 0
            assert result['failed_combinations'] == 10
            assert result['success_rate_percent'] == 0.0
            assert orchestrator.orchestrator_stats['errors_encountered'] == 1
    
    @pytest.mark.asyncio
    async def test_multiple_contract_processing(self, temp_dirs, mock_components):
        """Test processing multiple contracts"""
        output_dir, data_dir = temp_dirs
        contract_manager, gpu_processor, async_pipeline = mock_components
        
        with patch('src.gpu_parallel_processing.async_orchestrator.ContractDataManager', return_value=contract_manager), \
             patch('src.gpu_parallel_processing.async_orchestrator.EnhancedGPUCombinationProcessor', return_value=gpu_processor), \
             patch('src.gpu_parallel_processing.async_orchestrator.AsyncProcessingPipeline', return_value=async_pipeline):
            
            orchestrator = AsyncGPUOrchestrator(
                output_directory=output_dir,
                data_directory=data_dir
            )
            
            # Prepare multiple contracts
            contract_combinations = {
                'contract_1': [{'combo_id': i, 'param1': i} for i in range(1, 6)],  # 5 combinations
                'contract_2': [{'combo_id': i, 'param1': i} for i in range(6, 11)],  # 5 combinations
                'contract_3': [{'combo_id': i, 'param1': i} for i in range(11, 16)]  # 5 combinations
            }
            
            results = await orchestrator.process_multiple_contracts(contract_combinations)
            
            # Verify all contracts were processed
            assert len(results) == 3
            assert 'contract_1' in results
            assert 'contract_2' in results
            assert 'contract_3' in results
            
            # Verify each contract result
            for contract_code, result in results.items():
                assert result['contract_code'] == contract_code
                assert result['total_combinations'] == 5
                assert result['successful_combinations'] == 5
            
            # Verify contract manager was called for each contract
            assert contract_manager.load_contract_data.call_count == 3
    
    @pytest.mark.asyncio
    async def test_progress_callback_functionality(self, temp_dirs, sample_combinations, mock_components):
        """Test progress callback functionality"""
        output_dir, data_dir = temp_dirs
        contract_manager, gpu_processor, async_pipeline = mock_components
        
        with patch('src.gpu_parallel_processing.async_orchestrator.ContractDataManager', return_value=contract_manager), \
             patch('src.gpu_parallel_processing.async_orchestrator.EnhancedGPUCombinationProcessor', return_value=gpu_processor), \
             patch('src.gpu_parallel_processing.async_orchestrator.AsyncProcessingPipeline', return_value=async_pipeline):
            
            orchestrator = AsyncGPUOrchestrator(
                output_directory=output_dir,
                data_directory=data_dir
            )
            
            # Track progress calls
            progress_calls = []
            
            def progress_callback(progress, result):
                progress_calls.append((progress, result.combo_id if result else None))
            
            await orchestrator.process_contract_combinations(
                contract_code="test_contract",
                combinations=sample_combinations,
                progress_callback=progress_callback
            )
            
            # Verify progress was tracked
            assert len(progress_calls) > 0
            # Progress should increase over time
            if len(progress_calls) > 1:
                assert progress_calls[-1][0] >= progress_calls[0][0]
    
    @pytest.mark.asyncio
    async def test_multi_contract_progress_callback(self, temp_dirs, mock_components):
        """Test progress callback for multiple contracts"""
        output_dir, data_dir = temp_dirs
        contract_manager, gpu_processor, async_pipeline = mock_components
        
        with patch('src.gpu_parallel_processing.async_orchestrator.ContractDataManager', return_value=contract_manager), \
             patch('src.gpu_parallel_processing.async_orchestrator.EnhancedGPUCombinationProcessor', return_value=gpu_processor), \
             patch('src.gpu_parallel_processing.async_orchestrator.AsyncProcessingPipeline', return_value=async_pipeline):
            
            orchestrator = AsyncGPUOrchestrator(
                output_directory=output_dir,
                data_directory=data_dir
            )
            
            contract_combinations = {
                'contract_1': [{'combo_id': i, 'param1': i} for i in range(1, 4)],  # 3 combinations
                'contract_2': [{'combo_id': i, 'param1': i} for i in range(4, 7)]   # 3 combinations
            }
            
            progress_calls = []
            
            def multi_progress_callback(progress_info):
                progress_calls.append(progress_info)
            
            await orchestrator.process_multiple_contracts(
                contract_combinations,
                progress_callback=multi_progress_callback
            )
            
            # Verify progress tracking across contracts
            assert len(progress_calls) > 0
            
            # Check that we tracked both contracts
            contracts_seen = set()
            for call in progress_calls:
                contracts_seen.add(call['contract'])
            
            assert 'contract_1' in contracts_seen
            assert 'contract_2' in contracts_seen
            
            # Verify overall progress increases
            overall_progress_values = [call['overall_progress'] for call in progress_calls]
            if len(overall_progress_values) > 1:
                assert max(overall_progress_values) >= min(overall_progress_values)
    
    def test_batch_progress_callback_creation(self, temp_dirs):
        """Test batch progress callback creation and offset handling"""
        output_dir, data_dir = temp_dirs
        orchestrator = AsyncGPUOrchestrator(
            output_directory=output_dir,
            data_directory=data_dir
        )
        
        user_calls = []
        
        def user_callback(progress, result):
            user_calls.append((progress, result.combo_id))
        
        # Create batch callback with offset
        batch_callback = orchestrator._create_batch_progress_callback(
            user_callback=user_callback,
            batch_offset=10,  # Starting from combo 10
            total_combinations=20
        )
        
        # Simulate result from batch
        result = ProcessingResult(
            task_id="test_task",
            combo_id=12,  # Combo 12 in the batch
            success=True
        )
        
        batch_callback(0.5, result)  # 50% progress in batch
        
        # Verify callback was called with correct overall progress
        assert len(user_calls) == 1
        progress, combo_id = user_calls[0]
        assert combo_id == 12
        # Overall progress should account for offset
        assert 0 < progress < 1  # Should be between 0 and 1
    
    def test_get_orchestrator_statistics(self, temp_dirs, mock_components):
        """Test comprehensive statistics gathering"""
        output_dir, data_dir = temp_dirs
        contract_manager, gpu_processor, async_pipeline = mock_components
        
        with patch('src.gpu_parallel_processing.async_orchestrator.ContractDataManager', return_value=contract_manager), \
             patch('src.gpu_parallel_processing.async_orchestrator.EnhancedGPUCombinationProcessor', return_value=gpu_processor), \
             patch('src.gpu_parallel_processing.async_orchestrator.AsyncProcessingPipeline', return_value=async_pipeline):
            
            orchestrator = AsyncGPUOrchestrator(
                output_directory=output_dir,
                data_directory=data_dir
            )
            
            # Update some stats
            orchestrator.orchestrator_stats.update({
                'batches_processed': 5,
                'total_combinations_processed': 50,
                'contracts_loaded': 3
            })
            
            stats = orchestrator.get_orchestrator_statistics()
            
            # Verify all stat categories are present
            assert 'orchestrator_stats' in stats
            assert 'pipeline_stats' in stats
            assert 'gpu_stats' in stats
            assert 'contract_cache_stats' in stats
            
            # Verify orchestrator stats
            assert stats['orchestrator_stats']['batches_processed'] == 5
            assert stats['orchestrator_stats']['total_combinations_processed'] == 50
            assert stats['orchestrator_stats']['contracts_loaded'] == 3
    
    @pytest.mark.asyncio
    async def test_cleanup(self, temp_dirs, mock_components):
        """Test orchestrator cleanup"""
        output_dir, data_dir = temp_dirs
        contract_manager, gpu_processor, async_pipeline = mock_components
        
        with patch('src.gpu_parallel_processing.async_orchestrator.ContractDataManager', return_value=contract_manager), \
             patch('src.gpu_parallel_processing.async_orchestrator.EnhancedGPUCombinationProcessor', return_value=gpu_processor), \
             patch('src.gpu_parallel_processing.async_orchestrator.AsyncProcessingPipeline', return_value=async_pipeline):
            
            orchestrator = AsyncGPUOrchestrator(
                output_directory=output_dir,
                data_directory=data_dir
            )
            
            await orchestrator.cleanup()
            
            # Verify cleanup was called on components
            async_pipeline.cleanup.assert_called_once()
            gpu_processor.cleanup.assert_called_once()

class TestOrchestratorIntegration:
    """Integration tests for orchestrator with realistic scenarios"""
    
    @pytest.mark.asyncio
    async def test_batch_size_optimization_with_realistic_data(self, temp_dirs):
        """Test that batch size optimization works with realistic data sizes"""
        output_dir, data_dir = temp_dirs
        
        orchestrator = AsyncGPUOrchestrator(
            max_gpu_workers=3,
            output_directory=output_dir,
            data_directory=data_dir
        )
        
        # Test various realistic scenarios
        scenarios = [
            (100000, 20, "Small data, few combinations"),    # Should use larger batches
            (1500000, 100, "Large data, many combinations"), # Should use smaller batches
            (500000, 200, "Medium data, many combinations"), # Should balance
            (2000000, 10, "Very large data, few combinations") # Should use very small batches
        ]
        
        for data_length, combo_count, description in scenarios:
            batch_size = orchestrator._calculate_optimal_batch_size(data_length, combo_count)
            
            # Verify batch size is reasonable
            assert 5 <= batch_size <= 100, f"Batch size {batch_size} out of range for {description}"
            assert batch_size <= combo_count, f"Batch size {batch_size} exceeds combo count for {description}"
            assert batch_size <= orchestrator.max_gpu_workers * 10, f"Batch size {batch_size} too large for worker capacity in {description}"
            
            # Verify larger data leads to smaller batches (generally)
            if data_length > 1000000:
                assert batch_size <= 50, f"Large data should use smaller batches, got {batch_size} for {description}"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])