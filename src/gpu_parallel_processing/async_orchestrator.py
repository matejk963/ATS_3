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
            batch_size = max(10, int(base_batch_size // 1.5))
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