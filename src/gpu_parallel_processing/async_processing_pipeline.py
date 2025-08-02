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
                    
                    if processed_by_worker % 10 == 0:
                        print(f"🚀 {worker_id}: {processed_by_worker} combinations processed")
                    
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