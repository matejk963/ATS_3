# GPU-Accelerated Parallel Processing - Phase 1.2.2: Asynchronous Processing Pipeline

## Overview

Phase 1.2.2 builds on Phase 1.2.1's memory management to implement **asynchronous processing with parallel execution**. This phase eliminates I/O bottlenecks and enables concurrent processing of multiple parameter combinations while writing results to disk simultaneously.

## Problem Context

**Current Limitation (After Phase 1.2.1)**:
- Processing combinations sequentially (one at a time)
- GPU idle during result writing to disk
- Cannot overlap combination processing with file I/O
- Single-threaded approach limits throughput

**Phase 1.2.2 Solution**:
- Parallel processing of multiple combinations simultaneously
- Asynchronous result writing (non-blocking I/O)
- Producer-consumer pattern with processing queues
- Background workers for sustained throughput

## Phase 1.2.2 Deliverables

### 1. Asynchronous Processing Pipeline
**Implementation Location**: `src/gpu_parallel_processing/async_processing_pipeline.py`

```python
"""
Asynchronous processing pipeline for parallel GPU combination processing
with non-blocking I/O and concurrent result handling.
"""

import asyncio
import concurrent.futures
import threading
import queue
import time
import json
from typing import List, Dict, Optional, Callable, AsyncGenerator
from dataclasses import dataclass, asdict
from pathlib import Path
import pandas as pd

@dataclass
class ProcessingTask:
    """Task for GPU processing queue"""
    task_id: str
    combo_id: int
    contract_data: pd.DataFrame
    combination: Dict
    priority: int = 1
    created_at: float = None
    attempts: int = 0
    max_attempts: int = 3
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()

@dataclass
class ProcessingResult:
    """Result from GPU processing"""
    task_id: str
    combo_id: int
    success: bool
    result_data: Optional[pd.DataFrame] = None
    metadata: Optional[Dict] = None
    processing_time: float = 0.0
    error_message: Optional[str] = None
    worker_id: Optional[str] = None
    memory_stats: Optional[Dict] = None
    
class AsyncProcessingPipeline:
    """
    Asynchronous pipeline for parallel GPU processing with concurrent I/O.
    
    Features:
    - Parallel GPU workers processing combinations simultaneously
    - Asynchronous result writing to prevent I/O blocking
    - Producer-consumer pattern with intelligent queuing
    - Background monitoring and error handling
    """
    
    def __init__(self,
                 max_gpu_workers: int = 3,
                 max_io_workers: int = 2,
                 task_queue_size: int = 50,
                 result_buffer_size: int = 20,
                 output_directory: str = "combinations_output"):
        """
        Initialize async processing pipeline.
        
        Args:
            max_gpu_workers: Number of parallel GPU processing workers
            max_io_workers: Number of parallel I/O workers for result writing
            task_queue_size: Maximum tasks in processing queue
            result_buffer_size: Results buffered before batch writing
            output_directory: Directory for combination results
        """
        self.max_gpu_workers = max_gpu_workers
        self.max_io_workers = max_io_workers
        self.task_queue_size = task_queue_size
        self.result_buffer_size = result_buffer_size
        self.output_directory = Path(output_directory)
        self.output_directory.mkdir(exist_ok=True)
        
        # Async processing queues
        self.task_queue = None  # Will be initialized in async context
        self.result_queue = None
        self.io_queue = None
        
        # Thread pools for blocking operations
        self.gpu_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_gpu_workers,
            thread_name_prefix="GPU-Worker"
        )
        self.io_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_io_workers,
            thread_name_prefix="IO-Worker"
        )
        
        # Pipeline statistics
        self.pipeline_stats = {
            'tasks_submitted': 0,
            'tasks_completed': 0,
            'tasks_failed': 0,
            'tasks_retried': 0,
            'results_written': 0,
            'pipeline_start_time': None,
            'total_processing_time': 0.0,
            'total_io_time': 0.0,
            'concurrent_tasks_peak': 0
        }
        
        # Result buffering for batch I/O
        self.result_buffer = []
        self.buffer_lock = threading.Lock()
        
        # Pipeline control
        self.pipeline_active = False
        self.shutdown_requested = False
        
        print(f"🚀 Async Pipeline initialized: {max_gpu_workers} GPU workers, {max_io_workers} I/O workers")
    
    async def process_combinations_async(self,
                                       gpu_processor,
                                       combinations: List[Dict],
                                       contract_data: pd.DataFrame,
                                       progress_callback: Optional[Callable] = None,
                                       error_callback: Optional[Callable] = None) -> AsyncGenerator[ProcessingResult, None]:
        """
        Process combinations asynchronously with parallel execution.
        
        Args:
            gpu_processor: Enhanced GPU processor from Phase 1.2.1
            combinations: List of parameter combinations to process
            contract_data: Contract OHLCV data (shared across combinations)
            progress_callback: Optional progress update callback
            error_callback: Optional error handling callback
            
        Yields:
            ProcessingResult objects as they complete
        """
        # Initialize async queues
        await self._initialize_queues()
        
        self.pipeline_active = True
        self.pipeline_stats['pipeline_start_time'] = time.time()
        
        print(f"🔄 Starting async processing: {len(combinations)} combinations")
        
        try:
            # Start background workers
            gpu_workers = [
                asyncio.create_task(
                    self._gpu_worker(gpu_processor, f"GPU-{i}")
                ) for i in range(self.max_gpu_workers)
            ]
            
            io_workers = [
                asyncio.create_task(
                    self._io_worker(f"IO-{i}")
                ) for i in range(self.max_io_workers)
            ]
            
            # Submit all tasks
            task_submission = asyncio.create_task(
                self._submit_tasks(combinations, contract_data)
            )
            
            # Process results as they arrive
            processed_count = 0
            total_combinations = len(combinations)
            active_tasks = {}
            
            while processed_count < total_combinations:
                try:
                    # Wait for next result with timeout
                    result = await asyncio.wait_for(
                        self.result_queue.get(), 
                        timeout=2.0
                    )
                    
                    processed_count += 1
                    
                    # Update statistics
                    if result.success:
                        self.pipeline_stats['tasks_completed'] += 1
                    else:
                        self.pipeline_stats['tasks_failed'] += 1
                        
                        # Handle retry logic
                        if result.task_id in active_tasks:
                            task = active_tasks[result.task_id]
                            if task.attempts < task.max_attempts:
                                task.attempts += 1
                                await self.task_queue.put(task)
                                self.pipeline_stats['tasks_retried'] += 1
                                processed_count -= 1  # Don't count as completed yet
                                print(f"🔄 Retrying task {result.task_id} (attempt {task.attempts})")
                                continue
                    
                    # Call callbacks
                    if progress_callback:
                        progress = processed_count / total_combinations
                        progress_callback(progress, result)
                    
                    if not result.success and error_callback:
                        error_callback(result)
                    
                    # Queue result for writing
                    if result.success:
                        await self.io_queue.put(result)
                    
                    # Clean up active task tracking
                    if result.task_id in active_tasks:
                        del active_tasks[result.task_id]
                    
                    yield result
                    
                except asyncio.TimeoutError:
                    # Check if we're done or need to wait longer
                    if task_submission.done() and self.task_queue.empty():
                        # Give a bit more time for final results
                        try:
                            result = await asyncio.wait_for(
                                self.result_queue.get(), 
                                timeout=5.0
                            )
                            processed_count += 1
                            yield result
                        except asyncio.TimeoutError:
                            print("⏰ Timeout waiting for final results")
                            break
                    
                    # Update concurrent task peak
                    current_concurrent = len(active_tasks)
                    self.pipeline_stats['concurrent_tasks_peak'] = max(
                        self.pipeline_stats['concurrent_tasks_peak'],
                        current_concurrent
                    )
        
        finally:
            # Cleanup
            await self._shutdown_workers(gpu_workers + io_workers)
            self.pipeline_active = False
            
            # Final statistics
            total_time = time.time() - self.pipeline_stats['pipeline_start_time']
            print(f"✅ Async processing complete: {processed_count}/{total_combinations} in {total_time:.1f}s")
    
    async def _initialize_queues(self) -> None:
        """Initialize async queues for pipeline."""
        self.task_queue = asyncio.Queue(maxsize=self.task_queue_size)
        self.result_queue = asyncio.Queue(maxsize=self.result_buffer_size * 2)
        self.io_queue = asyncio.Queue(maxsize=self.result_buffer_size)
    
    async def _submit_tasks(self, combinations: List[Dict], contract_data: pd.DataFrame) -> None:
        """Submit processing tasks to queue."""
        for combo in combinations:
            task = ProcessingTask(
                task_id=f"task_{combo['combo_id']}",
                combo_id=combo['combo_id'],
                contract_data=contract_data,
                combination=combo,
                priority=1  # Could be adjusted based on combination complexity
            )
            
            await self.task_queue.put(task)
            self.pipeline_stats['tasks_submitted'] += 1
        
        print(f"📝 Submitted {len(combinations)} tasks to processing queue")
    
    async def _gpu_worker(self, gpu_processor, worker_id: str) -> None:
        """GPU worker for processing combinations."""
        processed_by_worker = 0
        
        while self.pipeline_active and not self.shutdown_requested:
            try:
                # Get task with timeout
                task = await asyncio.wait_for(
                    self.task_queue.get(),
                    timeout=3.0
                )
                
                # Process in thread pool to avoid blocking event loop
                start_time = time.time()
                loop = asyncio.get_event_loop()
                
                try:
                    # Process single combination
                    results = await loop.run_in_executor(
                        self.gpu_executor,
                        gpu_processor.process_contract_combinations_sustained,
                        task.contract_data,
                        [task.combination],
                        False  # Disable monitoring for async processing
                    )
                    
                    processing_time = time.time() - start_time
                    processed_by_worker += 1
                    
                    if results and len(results) > 0:
                        result_data = results[0]
                        
                        # Create successful result
                        result = ProcessingResult(
                            task_id=task.task_id,
                            combo_id=task.combo_id,
                            success=True,
                            result_data=result_data['result_data'],
                            metadata=result_data['metadata'],
                            processing_time=processing_time,
                            worker_id=worker_id,
                            memory_stats=result_data['metadata'].get('memory_stats', {})
                        )
                    else:
                        # No results returned
                        result = ProcessingResult(
                            task_id=task.task_id,
                            combo_id=task.combo_id,
                            success=False,
                            processing_time=processing_time,
                            error_message="No results returned from processor",
                            worker_id=worker_id
                        )
                    
                    print(f"🚀 {worker_id}: Combo {task.combo_id} processed in {processing_time:.2f}s")
                    
                except Exception as e:
                    processing_time = time.time() - start_time
                    
                    result = ProcessingResult(
                        task_id=task.task_id,
                        combo_id=task.combo_id,
                        success=False,
                        processing_time=processing_time,
                        error_message=str(e),
                        worker_id=worker_id
                    )
                    
                    print(f"❌ {worker_id}: Combo {task.combo_id} failed: {e}")
                
                # Update pipeline statistics
                self.pipeline_stats['total_processing_time'] += processing_time
                
                # Send result
                await self.result_queue.put(result)
                
            except asyncio.TimeoutError:
                # No tasks available, continue waiting
                continue
            except asyncio.CancelledError:
                print(f"🛑 {worker_id} cancelled ({processed_by_worker} combinations processed)")
                break
            except Exception as e:
                print(f"⚠️  {worker_id} error: {e}")
    
    async def _io_worker(self, worker_id: str) -> None:
        """I/O worker for writing results to disk."""
        written_by_worker = 0
        
        while self.pipeline_active and not self.shutdown_requested:
            try:
                # Get result to write
                result = await asyncio.wait_for(
                    self.io_queue.get(),
                    timeout=5.0
                )
                
                # Write in thread pool to avoid blocking
                start_time = time.time()
                loop = asyncio.get_event_loop()
                
                try:
                    await loop.run_in_executor(
                        self.io_executor,
                        self._write_result_to_disk,
                        result
                    )
                    
                    io_time = time.time() - start_time
                    written_by_worker += 1
                    self.pipeline_stats['results_written'] += 1
                    self.pipeline_stats['total_io_time'] += io_time
                    
                    if written_by_worker % 10 == 0:
                        print(f"💾 {worker_id}: {written_by_worker} results written")
                    
                except Exception as e:
                    print(f"❌ {worker_id}: Failed to write combo {result.combo_id}: {e}")
                
            except asyncio.TimeoutError:
                # No results to write, continue waiting
                continue
            except asyncio.CancelledError:
                print(f"🛑 {worker_id} cancelled ({written_by_worker} results written)")
                break
            except Exception as e:
                print(f"⚠️  {worker_id} error: {e}")
    
    def _write_result_to_disk(self, result: ProcessingResult) -> None:
        """Write processing result to disk (blocking operation)."""
        try:
            # Write result data
            result_file = self.output_directory / f"combo_{result.combo_id:06d}.parquet"
            result.result_data.to_parquet(result_file, index=False)
            
            # Write metadata
            metadata_file = self.output_directory / f"combo_{result.combo_id:06d}_metadata.json"
            with open(metadata_file, 'w') as f:
                # Convert result to serializable format
                metadata = {
                    'combo_id': result.combo_id,
                    'processing_time': result.processing_time,
                    'worker_id': result.worker_id,
                    'memory_stats': result.memory_stats,
                    'combination_metadata': result.metadata
                }
                json.dump(metadata, f, indent=2, default=str)
            
        except Exception as e:
            raise Exception(f"Failed to write result files: {e}")
    
    async def _shutdown_workers(self, workers: List[asyncio.Task]) -> None:
        """Gracefully shutdown worker tasks."""
        print("🛑 Shutting down async workers...")
        
        self.shutdown_requested = True
        
        # Cancel all workers
        for worker in workers:
            worker.cancel()
        
        # Wait for workers to finish with timeout
        try:
            await asyncio.wait_for(
                asyncio.gather(*workers, return_exceptions=True),
                timeout=10.0
            )
        except asyncio.TimeoutError:
            print("⚠️  Some workers did not shutdown gracefully")
        
        print("✅ Worker shutdown complete")
    
    def get_pipeline_statistics(self) -> Dict:
        """Get comprehensive pipeline performance statistics."""
        if self.pipeline_stats['pipeline_start_time']:
            total_runtime = time.time() - self.pipeline_stats['pipeline_start_time']
        else:
            total_runtime = 0
        
        completed = self.pipeline_stats['tasks_completed']
        failed = self.pipeline_stats['tasks_failed']
        total_submitted = self.pipeline_stats['tasks_submitted']
        
        return {
            'tasks_submitted': total_submitted,
            'tasks_completed': completed,
            'tasks_failed': failed,
            'tasks_retried': self.pipeline_stats['tasks_retried'],
            'success_rate_percent': (completed / max(1, completed + failed)) * 100,
            'results_written': self.pipeline_stats['results_written'],
            'pipeline_runtime_seconds': total_runtime,
            'total_processing_time_seconds': self.pipeline_stats['total_processing_time'],
            'total_io_time_seconds': self.pipeline_stats['total_io_time'],
            'concurrent_tasks_peak': self.pipeline_stats['concurrent_tasks_peak'],
            'average_processing_time': self.pipeline_stats['total_processing_time'] / max(1, completed),
            'throughput_combinations_per_minute': (completed / max(0.01, total_runtime)) * 60,
            'gpu_efficiency_percent': (self.pipeline_stats['total_processing_time'] / 
                                     max(0.01, total_runtime * self.max_gpu_workers)) * 100,
            'io_efficiency_percent': (self.pipeline_stats['total_io_time'] / 
                                    max(0.01, total_runtime * self.max_io_workers)) * 100
        }
    
    def cleanup(self) -> None:
        """Clean up pipeline resources."""
        print("🛑 Cleaning up Async Processing Pipeline...")
        
        # Shutdown thread pools
        self.gpu_executor.shutdown(wait=True)
        self.io_executor.shutdown(wait=True)
        
        # Clear queues and buffers
        with self.buffer_lock:
            self.result_buffer.clear()
        
        self.pipeline_active = False
        print("✅ Async Pipeline cleanup complete")
```

### 2. High-Level Async Orchestrator  
**Implementation Location**: `src/gpu_parallel_processing/async_orchestrator.py`

```python
"""
High-level orchestrator for async GPU processing pipeline with
monitoring, error handling, and adaptive scaling.
"""

import asyncio
import time
from typing import List, Dict, Optional, Callable
from pathlib import Path
import pandas as pd

from .async_processing_pipeline import AsyncProcessingPipeline, ProcessingResult
from .enhanced_gpu_processor import EnhancedGPUCombinationProcessor
from .contract_data_manager import ContractDataManager

class AsyncGPUOrchestrator:
    """
    High-level orchestrator for async GPU combination processing.
    
    Coordinates multiple components:
    - Contract data management
    - GPU processing with memory management  
    - Async pipeline execution
    - Progress monitoring and error handling
    """
    
    def __init__(self,
                 max_gpu_workers: int = 3,
                 max_io_workers: int = 2, 
                 gpu_memory_pool_gb: float = 14.0,
                 output_directory: str = "combinations_output",
                 data_directory: str = "data"):
        """
        Initialize orchestrator.
        
        Args:
            max_gpu_workers: Parallel GPU processing workers
            max_io_workers: Parallel I/O workers
            gpu_memory_pool_gb: GPU memory pool size
            output_directory: Output directory for results
            data_directory: Directory containing contract data
        """
        self.max_gpu_workers = max_gpu_workers
        self.max_io_workers = max_io_workers
        
        # Initialize components
        self.contract_manager = ContractDataManager(
            max_cached_contracts=5,
            data_directory=data_directory
        )
        
        self.gpu_processor = EnhancedGPUCombinationProcessor(
            gpu_memory_pool_gb=gpu_memory_pool_gb,
            processing_chunk_size=2000000
        )
        
        self.async_pipeline = AsyncProcessingPipeline(
            max_gpu_workers=max_gpu_workers,
            max_io_workers=max_io_workers,
            output_directory=output_directory
        )
        
        # Orchestrator statistics
        self.orchestrator_stats = {
            'batches_processed': 0,
            'total_combinations_processed': 0,
            'total_runtime': 0.0,
            'contracts_loaded': 0,
            'errors_encountered': 0
        }
        
        print(f"🎭 Async GPU Orchestrator initialized with {max_gpu_workers} GPU workers")
    
    async def process_contract_combinations(self,
                                          contract_code: str,
                                          combinations: List[Dict],
                                          batch_size: Optional[int] = None,
                                          progress_callback: Optional[Callable] = None) -> Dict:
        """
        Process all combinations for a single contract asynchronously.
        
        Args:
            contract_code: Contract identifier (e.g., 'dem07_25')
            combinations: List of parameter combinations to process
            batch_size: Optional batch size for processing (auto-calculated if None)
            progress_callback: Optional progress callback
            
        Returns:
            Processing summary with statistics
        """
        start_time = time.time()
        
        print(f"🎯 Processing {len(combinations)} combinations for contract {contract_code}")
        
        try:
            # Load contract data
            print(f"📂 Loading contract data: {contract_code}")
            contract_data = self.contract_manager.load_contract_data(contract_code)
            self.orchestrator_stats['contracts_loaded'] += 1
            
            print(f"✅ Contract loaded: {len(contract_data):,} candles")
            
            # Determine optimal batch size if not provided
            if batch_size is None:
                batch_size = self._calculate_optimal_batch_size(
                    len(contract_data), 
                    len(combinations)
                )
            
            print(f"🔢 Processing in batches of {batch_size} combinations")
            
            # Process in batches
            all_results = []
            total_successful = 0
            total_failed = 0
            
            for batch_start in range(0, len(combinations), batch_size):
                batch_end = min(batch_start + batch_size, len(combinations))
                batch_combinations = combinations[batch_start:batch_end]
                
                print(f"🔄 Processing batch {batch_start//batch_size + 1}: "
                      f"combinations {batch_start}-{batch_end-1}")
                
                # Process batch asynchronously
                batch_results = []
                batch_successful = 0
                batch_failed = 0
                
                async for result in self.async_pipeline.process_combinations_async(
                    self.gpu_processor,
                    batch_combinations,
                    contract_data,
                    self._create_batch_progress_callback(progress_callback, batch_start, len(combinations))
                ):
                    batch_results.append(result)
                    if result.success:
                        batch_successful += 1
                    else:
                        batch_failed += 1
                        self.orchestrator_stats['errors_encountered'] += 1
                
                all_results.extend(batch_results)
                total_successful += batch_successful
                total_failed += batch_failed
                
                # Batch summary
                batch_success_rate = (batch_successful / len(batch_combinations)) * 100
                print(f"✅ Batch complete: {batch_successful}/{len(batch_combinations)} successful "
                      f"({batch_success_rate:.1f}% success rate)")
                
                self.orchestrator_stats['batches_processed'] += 1
                
                # Brief pause between batches for memory cleanup
                await asyncio.sleep(0.5)
            
            # Final statistics
            runtime = time.time() - start_time
            self.orchestrator_stats['total_combinations_processed'] += len(combinations)
            self.orchestrator_stats['total_runtime'] += runtime
            
            success_rate = (total_successful / len(combinations)) * 100
            throughput = total_successful / (runtime / 60)  # per minute
            
            # Get detailed statistics
            pipeline_stats = self.async_pipeline.get_pipeline_statistics()
            gpu_stats = self.gpu_processor.get_processing_stats()
            contract_stats = self.contract_manager.get_cache_stats()
            
            summary = {
                'contract_code': contract_code,
                'total_combinations': len(combinations),
                'successful_combinations': total_successful,
                'failed_combinations': total_failed,
                'success_rate_percent': success_rate,
                'processing_time_seconds': runtime,
                'throughput_per_minute': throughput,
                'batches_processed': self.orchestrator_stats['batches_processed'],
                'pipeline_stats': pipeline_stats,
                'gpu_stats': gpu_stats,
                'contract_stats': contract_stats,
                'orchestrator_stats': self.orchestrator_stats.copy()
            }
            
            print(f"🎉 Contract processing complete: {total_successful}/{len(combinations)} "
                  f"({success_rate:.1f}% success) in {runtime:.1f}s "
                  f"({throughput:.1f} combinations/min)")
            
            return summary
            
        except Exception as e:
            runtime = time.time() - start_time
            self.orchestrator_stats['errors_encountered'] += 1
            
            error_summary = {
                'contract_code': contract_code,
                'error': str(e),
                'processing_time_seconds': runtime,
                'successful_combinations': 0,
                'failed_combinations': len(combinations),
                'success_rate_percent': 0.0
            }
            
            print(f"❌ Contract processing failed after {runtime:.1f}s: {e}")
            return error_summary
    
    async def process_multiple_contracts(self,
                                       contract_combinations: Dict[str, List[Dict]],
                                       progress_callback: Optional[Callable] = None) -> Dict[str, Dict]:
        """
        Process combinations for multiple contracts sequentially.
        
        Args:
            contract_combinations: Dict mapping contract codes to combinations
            progress_callback: Optional progress callback
            
        Returns:
            Dict mapping contract codes to processing summaries
        """
        print(f"🌐 Processing {len(contract_combinations)} contracts")
        
        results = {}
        total_combinations = sum(len(combos) for combos in contract_combinations.values())
        processed_combinations = 0
        
        for contract_code, combinations in contract_combinations.items():
            print(f"\n📊 Starting contract {contract_code}: {len(combinations)} combinations")
            
            # Create contract-specific progress callback
            def contract_progress_callback(progress: float, result: ProcessingResult):
                nonlocal processed_combinations
                if result.success:
                    processed_combinations += 1
                
                overall_progress = processed_combinations / total_combinations
                
                if progress_callback:
                    progress_callback({
                        'contract': contract_code,
                        'contract_progress': progress,
                        'overall_progress': overall_progress,
                        'processed_combinations': processed_combinations,
                        'total_combinations': total_combinations,
                        'current_result': result
                    })
            
            # Process contract
            contract_result = await self.process_contract_combinations(
                contract_code,
                combinations,
                progress_callback=contract_progress_callback
            )
            
            results[contract_code] = contract_result
        
        print(f"\n🎊 Multi-contract processing complete: {len(results)} contracts processed")
        return results
    
    def _calculate_optimal_batch_size(self, 
                                    data_length: int, 
                                    total_combinations: int) -> int:
        """Calculate optimal batch size based on data size and combination count."""
        # Base batch size on memory constraints and processing efficiency
        base_batch_size = max(10, min(100, total_combinations // 10))
        
        # Adjust based on data size (larger data = smaller batches)
        if data_length > 1000000:  # > 1M candles
            batch_size = max(5, base_batch_size // 2)
        elif data_length > 500000:  # > 500K candles
            batch_size = max(10, base_batch_size // 1.5)
        else:
            batch_size = base_batch_size
        
        # Ensure we don't exceed worker capacity
        max_reasonable_batch = self.max_gpu_workers * 10
        batch_size = min(batch_size, max_reasonable_batch)
        
        return int(batch_size)
    
    def _create_batch_progress_callback(self,
                                      user_callback: Optional[Callable],
                                      batch_offset: int,
                                      total_combinations: int) -> Optional[Callable]:
        """Create progress callback that accounts for batch offset."""
        if user_callback is None:
            return None
        
        def batch_progress_callback(batch_progress: float, result: ProcessingResult):
            # Calculate overall progress
            combinations_before_batch = batch_offset
            combinations_in_current_batch = result.combo_id - batch_offset if result.combo_id >= batch_offset else 0
            total_completed = combinations_before_batch + combinations_in_current_batch
            
            overall_progress = total_completed / total_combinations
            
            user_callback(overall_progress, result)
        
        return batch_progress_callback
    
    def get_orchestrator_statistics(self) -> Dict:
        """Get comprehensive orchestrator statistics."""
        return {
            'orchestrator_stats': self.orchestrator_stats.copy(),
            'pipeline_stats': self.async_pipeline.get_pipeline_statistics(),
            'gpu_stats': self.gpu_processor.get_processing_stats(),
            'contract_cache_stats': self.contract_manager.get_cache_stats()
        }
    
    async def cleanup(self) -> None:
        """Clean up all orchestrator resources."""
        print("🛑 Cleaning up Async GPU Orchestrator...")
        
        # Cleanup components
        self.async_pipeline.cleanup()
        self.gpu_processor.cleanup()
        
        print("✅ Orchestrator cleanup complete")
```

## Phase 1.2.2 Implementation Checklist

### Asynchronous Processing Pipeline
- [ ] Implement `AsyncProcessingPipeline` with parallel GPU workers
- [ ] Create producer-consumer pattern with task queues
- [ ] Add asynchronous result writing with I/O workers
- [ ] Implement error handling and retry mechanisms

### High-Level Orchestration
- [ ] Create `AsyncGPUOrchestrator` for coordinated processing
- [ ] Add batch processing with optimal sizing
- [ ] Implement multi-contract processing capabilities
- [ ] Create comprehensive progress monitoring

### Performance Optimization
- [ ] Add intelligent queue sizing and worker scaling
- [ ] Implement concurrent task tracking and statistics
- [ ] Create GPU/I/O efficiency monitoring
- [ ] Add adaptive batch sizing based on performance

### Testing & Validation
- [ ] Test concurrent processing of multiple combinations
- [ ] Validate async I/O prevents GPU blocking
- [ ] Test error handling and retry mechanisms
- [ ] Benchmark throughput improvements vs sequential processing

## Success Criteria

### Performance Targets
- [ ] Achieve 3-4x throughput improvement over sequential processing
- [ ] Maintain >90% GPU utilization during sustained processing
- [ ] Demonstrate I/O operations don't block GPU processing
- [ ] Process 1,000+ combinations with <5% failure rate

### Concurrency & Reliability
- [ ] Successfully process multiple combinations simultaneously
- [ ] Handle worker failures gracefully with task redistribution
- [ ] Maintain result integrity with concurrent I/O operations
- [ ] Demonstrate linear scaling with additional GPU workers

Phase 1.2.2 enables true parallel processing, setting the foundation for Phase 1.2.3's advanced monitoring and optimization capabilities.