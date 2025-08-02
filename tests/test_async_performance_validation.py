"""
Performance validation tests for async processing pipeline
measuring throughput improvements and efficiency
"""

import pytest
import asyncio
import time
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch
import pandas as pd
import numpy as np

from src.gpu_parallel_processing.async_processing_pipeline import AsyncProcessingPipeline, ProcessingResult
from src.gpu_parallel_processing.async_orchestrator import AsyncGPUOrchestrator

class TestAsyncPerformanceValidation:
    """Performance validation tests for async processing"""
    
    @pytest.fixture
    def temp_output_dir(self):
        """Create temporary output directory"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def realistic_contract_data(self):
        """Create realistic contract data for performance testing"""
        return pd.DataFrame({
            'open': np.random.random(500000) * 100,     # 500K candles
            'high': np.random.random(500000) * 100,
            'low': np.random.random(500000) * 100,
            'close': np.random.random(500000) * 100,
            'volume': np.random.random(500000) * 1000
        })
    
    def create_mock_gpu_processor(self, processing_time: float = 0.1):
        """Create mock GPU processor with configurable processing time"""
        processor = Mock()
        
        def mock_process(*args, **kwargs):
            time.sleep(processing_time)  # Simulate processing time
            return [{
                'result_data': pd.DataFrame({
                    'signal': np.random.choice([-1, 0, 1], size=100),
                    'confidence': np.random.random(100)
                }),
                'metadata': {
                    'processing_time': processing_time,
                    'memory_stats': {'gpu_memory_used': 1024}
                }
            }]
        
        processor.process_contract_combinations_sustained = mock_process
        return processor
    
    @pytest.mark.asyncio
    async def test_parallel_vs_sequential_throughput(self, temp_output_dir, realistic_contract_data):
        """Test that async pipeline achieves better throughput than sequential processing"""
        # Test parameters
        num_combinations = 20
        processing_time_per_combo = 0.05  # 50ms per combination
        combinations = [{'combo_id': i, 'param1': i * 10} for i in range(1, num_combinations + 1)]
        
        mock_processor = self.create_mock_gpu_processor(processing_time_per_combo)
        
        # Test sequential processing (1 worker)
        sequential_pipeline = AsyncProcessingPipeline(
            max_gpu_workers=1,
            max_io_workers=1,
            output_directory=temp_output_dir
        )
        
        start_time = time.time()
        sequential_results = []
        async for result in sequential_pipeline.process_combinations_async(
            mock_processor,
            combinations,
            realistic_contract_data
        ):
            sequential_results.append(result)
        sequential_time = time.time() - start_time
        
        # Test parallel processing (4 workers)
        parallel_pipeline = AsyncProcessingPipeline(
            max_gpu_workers=4,
            max_io_workers=2,
            output_directory=temp_output_dir
        )
        
        start_time = time.time()
        parallel_results = []
        async for result in parallel_pipeline.process_combinations_async(
            mock_processor,
            combinations,
            realistic_contract_data
        ):
            parallel_results.append(result)
        parallel_time = time.time() - start_time
        
        # Verify both processed all combinations
        assert len(sequential_results) == num_combinations
        assert len(parallel_results) == num_combinations
        assert all(r.success for r in sequential_results)
        assert all(r.success for r in parallel_results)
        
        # Calculate throughput improvements
        sequential_throughput = num_combinations / sequential_time
        parallel_throughput = num_combinations / parallel_time
        throughput_improvement = parallel_throughput / sequential_throughput
        
        print(f"Sequential time: {sequential_time:.2f}s ({sequential_throughput:.1f} combos/s)")
        print(f"Parallel time: {parallel_time:.2f}s ({parallel_throughput:.1f} combos/s)")
        print(f"Throughput improvement: {throughput_improvement:.2f}x")
        
        # With 4 workers vs 1, we should see significant improvement
        # Allow for overhead, but should be at least 2x faster
        assert throughput_improvement >= 2.0, f"Expected at least 2x improvement, got {throughput_improvement:.2f}x"
        
        # Parallel processing should complete in roughly 1/4 the time (plus overhead)
        expected_parallel_time = sequential_time / 3.5  # Conservative estimate with overhead
        assert parallel_time <= expected_parallel_time * 1.5, f"Parallel processing took too long: {parallel_time:.2f}s vs expected ~{expected_parallel_time:.2f}s"
    
    @pytest.mark.asyncio
    async def test_gpu_utilization_efficiency(self, temp_output_dir, realistic_contract_data):
        """Test GPU utilization efficiency with different worker configurations"""
        combinations = [{'combo_id': i, 'param1': i * 10} for i in range(1, 25)]  # 24 combinations
        processing_time = 0.1  # 100ms per combination
        
        mock_processor = self.create_mock_gpu_processor(processing_time)
        
        # Test different worker configurations
        worker_configs = [
            (1, "Single worker"),
            (2, "Two workers"),
            (4, "Four workers"),
            (6, "Six workers")
        ]
        
        results = {}
        
        for num_workers, description in worker_configs:
            pipeline = AsyncProcessingPipeline(
                max_gpu_workers=num_workers,
                max_io_workers=max(1, num_workers // 2),
                output_directory=temp_output_dir
            )
            
            start_time = time.time()
            processed_results = []
            async for result in pipeline.process_combinations_async(
                mock_processor,
                combinations,
                realistic_contract_data
            ):
                processed_results.append(result)
            end_time = time.time()
            
            processing_time_total = end_time - start_time
            stats = pipeline.get_pipeline_statistics()
            
            results[num_workers] = {
                'description': description,
                'processing_time': processing_time_total,
                'throughput': len(combinations) / processing_time_total,
                'gpu_efficiency': stats['gpu_efficiency_percent'],
                'successful_combinations': len([r for r in processed_results if r.success])
            }
            
            print(f"{description}: {processing_time_total:.2f}s, "
                  f"GPU efficiency: {stats['gpu_efficiency_percent']:.1f}%, "
                  f"Throughput: {results[num_workers]['throughput']:.1f} combos/s")
        
        # Verify all configurations processed successfully
        for config in results.values():
            assert config['successful_combinations'] == len(combinations)
        
        # Verify throughput improvements with more workers
        single_worker_throughput = results[1]['throughput']
        two_worker_throughput = results[2]['throughput']
        four_worker_throughput = results[4]['throughput']
        
        # Should see improvement with more workers (allowing for diminishing returns)
        assert two_worker_throughput > single_worker_throughput * 1.5
        assert four_worker_throughput > single_worker_throughput * 2.5
        
        # GPU efficiency should be reasonable for all configurations
        for config in results.values():
            assert config['gpu_efficiency'] > 30, f"Low GPU efficiency: {config['gpu_efficiency']:.1f}%"
    
    @pytest.mark.asyncio
    async def test_io_concurrency_benefits(self, temp_output_dir, realistic_contract_data):
        """Test that concurrent I/O improves overall performance"""
        combinations = [{'combo_id': i, 'param1': i * 10} for i in range(1, 16)]  # 15 combinations
        mock_processor = self.create_mock_gpu_processor(0.05)  # Fast processing to highlight I/O
        
        # Test with single I/O worker
        single_io_pipeline = AsyncProcessingPipeline(
            max_gpu_workers=3,
            max_io_workers=1,
            output_directory=temp_output_dir
        )
        
        start_time = time.time()
        single_io_results = []
        async for result in single_io_pipeline.process_combinations_async(
            mock_processor,
            combinations,
            realistic_contract_data
        ):
            single_io_results.append(result)
        single_io_time = time.time() - start_time
        
        # Test with multiple I/O workers
        multi_io_pipeline = AsyncProcessingPipeline(
            max_gpu_workers=3,
            max_io_workers=3,
            output_directory=temp_output_dir
        )
        
        start_time = time.time()
        multi_io_results = []
        async for result in multi_io_pipeline.process_combinations_async(
            mock_processor,
            combinations,
            realistic_contract_data
        ):
            multi_io_results.append(result)
        multi_io_time = time.time() - start_time
        
        # Verify processing completed successfully
        assert len(single_io_results) == len(combinations)
        assert len(multi_io_results) == len(combinations)
        assert all(r.success for r in single_io_results)
        assert all(r.success for r in multi_io_results)
        
        # Get I/O statistics
        single_io_stats = single_io_pipeline.get_pipeline_statistics()
        multi_io_stats = multi_io_pipeline.get_pipeline_statistics()
        
        print(f"Single I/O worker: {single_io_time:.2f}s, I/O efficiency: {single_io_stats['io_efficiency_percent']:.1f}%")
        print(f"Multi I/O workers: {multi_io_time:.2f}s, I/O efficiency: {multi_io_stats['io_efficiency_percent']:.1f}%")
        
        # Multiple I/O workers should improve performance when I/O is a bottleneck
        improvement_ratio = single_io_time / multi_io_time
        assert improvement_ratio >= 1.1, f"Expected improvement with multiple I/O workers, got {improvement_ratio:.2f}x"
        
        # Verify all results were written to disk
        output_path = Path(temp_output_dir)
        result_files = list(output_path.glob("combo_*.parquet"))
        metadata_files = list(output_path.glob("combo_*_metadata.json"))
        
        assert len(result_files) >= len(combinations)  # Should have files for all successful combinations
        assert len(metadata_files) >= len(combinations)
    
    @pytest.mark.asyncio
    async def test_error_handling_performance_impact(self, temp_output_dir, realistic_contract_data):
        """Test that error handling and retries don't significantly impact performance"""
        combinations = [{'combo_id': i, 'param1': i * 10} for i in range(1, 21)]  # 20 combinations
        
        # Create processor that fails occasionally
        processor = Mock()
        call_count = 0
        
        def failing_process(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Fail every 5th call initially, then succeed on retry
            if call_count % 5 == 0 and call_count <= 20:
                raise Exception("Simulated processing failure")
            
            time.sleep(0.05)  # 50ms processing time
            return [{
                'result_data': pd.DataFrame({
                    'signal': np.random.choice([-1, 0, 1], size=50),
                }),
                'metadata': {'memory_stats': {}}
            }]
        
        processor.process_contract_combinations_sustained = failing_process
        
        pipeline = AsyncProcessingPipeline(
            max_gpu_workers=3,
            max_io_workers=2,
            output_directory=temp_output_dir
        )
        
        start_time = time.time()
        results = []
        async for result in pipeline.process_combinations_async(
            processor,
            combinations,
            realistic_contract_data
        ):
            results.append(result)
        end_time = time.time()
        
        processing_time = end_time - start_time
        stats = pipeline.get_pipeline_statistics()
        
        # Verify most combinations succeeded (some may fail after max retries)
        successful_results = [r for r in results if r.success]
        assert len(successful_results) >= len(combinations) * 0.8  # At least 80% success
        
        # Verify retries occurred
        assert stats['tasks_retried'] > 0, "Expected some retry attempts"
        
        # Performance should still be reasonable despite errors
        throughput = len(successful_results) / processing_time
        assert throughput > 5, f"Throughput too low with error handling: {throughput:.1f} combos/s"
        
        print(f"Error handling performance: {len(successful_results)}/{len(combinations)} successful, "
              f"{stats['tasks_retried']} retries, {throughput:.1f} combos/s")
    
    @pytest.mark.asyncio 
    async def test_orchestrator_batch_processing_efficiency(self, temp_output_dir):
        """Test orchestrator batch processing efficiency"""
        # Mock components for realistic performance testing
        contract_data = pd.DataFrame({
            'close': np.random.random(100000) * 100  # 100K candles
        })
        
        contract_manager = Mock()
        contract_manager.load_contract_data.return_value = contract_data
        contract_manager.get_cache_stats.return_value = {'cache_hits': 1}
        
        gpu_processor = Mock()
        gpu_processor.get_processing_stats.return_value = {'total_processing_time': 30}
        
        # Create many combinations to test batching
        combinations = [{'combo_id': i, 'param1': i * 10} for i in range(1, 101)]  # 100 combinations
        
        with patch('src.gpu_parallel_processing.async_orchestrator.ContractDataManager', return_value=contract_manager), \
             patch('src.gpu_parallel_processing.async_orchestrator.EnhancedGPUCombinationProcessor', return_value=gpu_processor):
            
            orchestrator = AsyncGPUOrchestrator(
                max_gpu_workers=4,
                max_io_workers=2,
                output_directory=temp_output_dir
            )
            
            # Mock the async pipeline to simulate realistic processing
            async def mock_batch_processing(*args, **kwargs):
                batch_combinations = args[1]  # Second argument is combinations
                for combo in batch_combinations:
                    await asyncio.sleep(0.01)  # 10ms per combination
                    yield ProcessingResult(
                        task_id=f"task_{combo['combo_id']}",
                        combo_id=combo['combo_id'],
                        success=True,
                        processing_time=0.01,
                        worker_id="GPU-0"
                    )
            
            orchestrator.async_pipeline.process_combinations_async = mock_batch_processing
            orchestrator.async_pipeline.get_pipeline_statistics = Mock(return_value={
                'tasks_completed': 100,
                'tasks_failed': 0,
                'success_rate_percent': 100.0,
                'throughput_combinations_per_minute': 600
            })
            
            start_time = time.time()
            result = await orchestrator.process_contract_combinations(
                contract_code="performance_test",
                combinations=combinations
            )
            end_time = time.time()
            
            processing_time = end_time - start_time
            
            # Verify all combinations were processed
            assert result['successful_combinations'] == 100
            assert result['failed_combinations'] == 0
            assert result['success_rate_percent'] == 100.0
            
            # Verify reasonable throughput
            throughput = result['successful_combinations'] / processing_time
            assert throughput > 50, f"Orchestrator throughput too low: {throughput:.1f} combos/s"
            
            # Verify batching occurred (should process in multiple batches)
            assert orchestrator.orchestrator_stats['batches_processed'] > 1
            
            print(f"Orchestrator performance: {result['successful_combinations']} combinations in {processing_time:.2f}s "
                  f"({throughput:.1f} combos/s) across {orchestrator.orchestrator_stats['batches_processed']} batches")

class TestPerformanceRegressionValidation:
    """Tests to validate performance doesn't regress over time"""
    
    @pytest.mark.asyncio
    async def test_minimum_throughput_requirements(self, temp_output_dir):
        """Test that minimum throughput requirements are met"""
        # Define minimum acceptable performance thresholds
        MIN_COMBINATIONS_PER_SECOND = 20  # Minimum acceptable throughput
        MAX_PROCESSING_TIME_PER_COMBO = 0.2  # Maximum 200ms per combination
        
        combinations = [{'combo_id': i, 'param1': i} for i in range(1, 31)]  # 30 combinations
        contract_data = pd.DataFrame({'close': np.random.random(50000) * 100})
        
        mock_processor = Mock()
        mock_processor.process_contract_combinations_sustained = Mock(return_value=[{
            'result_data': pd.DataFrame({'signal': [1, 0, -1]}),
            'metadata': {'memory_stats': {}}
        }])
        
        pipeline = AsyncProcessingPipeline(
            max_gpu_workers=3,
            max_io_workers=2,
            output_directory=temp_output_dir
        )
        
        start_time = time.time()
        results = []
        async for result in pipeline.process_combinations_async(
            mock_processor,
            combinations,
            contract_data
        ):
            results.append(result)
        end_time = time.time()
        
        processing_time = end_time - start_time
        successful_combinations = len([r for r in results if r.success])
        
        # Validate minimum performance requirements
        throughput = successful_combinations / processing_time
        avg_time_per_combo = processing_time / successful_combinations
        
        assert throughput >= MIN_COMBINATIONS_PER_SECOND, \
            f"Throughput below minimum: {throughput:.1f} < {MIN_COMBINATIONS_PER_SECOND} combos/s"
        
        assert avg_time_per_combo <= MAX_PROCESSING_TIME_PER_COMBO, \
            f"Average processing time too high: {avg_time_per_combo:.3f} > {MAX_PROCESSING_TIME_PER_COMBO}s"
        
        print(f"Performance validation passed: {throughput:.1f} combos/s, "
              f"{avg_time_per_combo:.3f}s per combo")

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])  # -s to see print output