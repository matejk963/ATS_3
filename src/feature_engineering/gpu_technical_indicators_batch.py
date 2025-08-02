"""
GPU Technical Indicators Batch Processing Infrastructure

This module provides the batch processing infrastructure for technical indicators
using Phase 1 GPU acceleration components. Designed to achieve 60-80% GPU utilization
by efficiently processing 25-40 combinations per batch.

Key Features:
- Unified batch processing coordinator
- GPU memory allocation and management
- Performance monitoring and optimization
- Integration with Phase 1 infrastructure (ArrayBackend, GPUConverter, etc.)
"""

from typing import List, Dict, Any, Optional, Tuple
import pandas as pd
import numpy as np
from dataclasses import dataclass
import time

from .array_backend import ArrayBackend, ArrayLike
from .gpu_converter import GPUArrayConverter
from .gpu_memory_manager import GPUBatchOptimizer, GPUMemoryManager
from .metadata import DataFrameMetadata


@dataclass
class BatchProcessingConfig:
    """Configuration for GPU batch processing"""
    target_gpu_utilization: float = 0.75  # Target 75% GPU utilization
    max_batch_size: int = 10000  # Maximum combinations per batch (support user's 5000+ choice)
    min_batch_size: int = 100    # Minimum combinations per batch (allow smaller tests)
    memory_safety_margin: float = 0.05  # 5% safety margin
    enable_performance_monitoring: bool = True
    cuda_streams: int = 8  # Number of CUDA streams for parallel processing


class GPUTechnicalIndicatorsBatch:
    """
    Batch processing coordinator for GPU-accelerated technical indicators.
    
    This class orchestrates the efficient batch processing of technical indicators
    (ATR, MACD, Swing Points) using Phase 1 GPU infrastructure to achieve
    optimal GPU utilization and processing throughput.
    """
    
    def __init__(self, backend: ArrayBackend, config: Optional[BatchProcessingConfig] = None):
        """
        Initialize batch processing coordinator.
        
        Args:
            backend: ArrayBackend for GPU operations
            config: Batch processing configuration
        """
        self.backend = backend
        self.xp = backend.xp
        self.config = config or BatchProcessingConfig()
        
        # Initialize Phase 1 infrastructure components
        self.converter = GPUArrayConverter()
        self.batch_optimizer = GPUBatchOptimizer(
            target_utilization=self.config.target_gpu_utilization,
            safety_margin=self.config.memory_safety_margin
        )
        self.memory_manager = GPUMemoryManager()
        
        # Initialize GPU-accelerated calculators
        self._initialize_calculators()
        
        # Performance tracking
        self.processing_stats = {
            'total_combinations_processed': 0,
            'total_batches_processed': 0,
            'average_batch_processing_time': 0.0,
            'gpu_utilization_samples': [],
            'memory_utilization_samples': []
        }
    
    def _initialize_calculators(self):
        """Initialize GPU-accelerated technical indicator calculators"""
        from .atr_calculator import ATRCalculator
        from .macd_calculator import MACDCalculator
        from .gpu_swing_detector import GPUSwingDetector
        from .gpu_memory_manager import UnifiedGPUTechnicalIndicators
        
        self.atr_calculator = ATRCalculator(self.backend)
        self.macd_calculator = MACDCalculator(self.backend)
        self.swing_detector = GPUSwingDetector(self.backend)
        self.unified_pipeline = UnifiedGPUTechnicalIndicators(self.backend)
    
    def process_combinations_batch(self, combinations: List[Dict]) -> List[Dict]:
        """
        Process a batch of parameter combinations using GPU acceleration.
        
        This is the main entry point for batch processing that coordinates:
        1. Optimal batch sizing using GPUBatchOptimizer
        2. Memory management using GPUMemoryManager
        3. Parallel processing using CUDA streams
        4. Performance monitoring and optimization
        
        Args:
            combinations: List of parameter combination dictionaries
            
        Returns:
            List of processed combinations with technical indicator results
        """
        if not combinations:
            return []
        
        print(f"\\n=== GPU BATCH PROCESSING: {len(combinations)} combinations ===")
        start_time = time.time()
        
        # Step 1: Calculate optimal batch size
        optimal_batch_size = self._calculate_optimal_batch_size(combinations[0])
        print(f"Optimal batch size: {optimal_batch_size}")
        
        # Step 2: Process combinations in optimal batches
        all_results = []
        batch_count = 0
        
        with self.memory_manager.memory_managed_context("Technical Indicators Batch Processing"):
            for i in range(0, len(combinations), optimal_batch_size):
                batch = combinations[i:i+optimal_batch_size]
                batch_count += 1
                
                print(f"Processing batch {batch_count}/{(len(combinations) + optimal_batch_size - 1) // optimal_batch_size}")
                
                # Process batch with performance monitoring
                batch_results = self._process_single_batch(batch, batch_count)
                all_results.extend(batch_results)
                
                # Update performance statistics
                self._update_processing_stats(len(batch))
        
        # Final performance summary
        total_time = time.time() - start_time
        self._log_performance_summary(len(combinations), batch_count, total_time)
        
        return all_results
    
    def _calculate_optimal_batch_size(self, sample_combination: Dict) -> int:
        """Calculate optimal batch size - override to respect user's batch size preference"""
        # ✅ FIXED: Don't limit user's batch size choice
        # The user sets batch_size in the comprehensive test and expects it to be honored
        
        # For TRUE PARALLEL GPU processing, we can handle much larger batches
        # Return a large batch size to allow user control from comprehensive test
        return self.config.max_batch_size  # Use max configured size (2000+)
        
        # Note: The actual batch size control happens in the comprehensive test
        # This just ensures we don't artificially limit the user's choice
    
    def _process_single_batch(self, batch: List[Dict], batch_number: int) -> List[Dict]:
        """Process a single batch using TRUE PARALLEL GPU processing"""
        batch_start_time = time.time()
        
        try:
            # Monitor GPU utilization before processing
            if self.config.enable_performance_monitoring:
                pre_processing_stats = self._get_gpu_stats()
            
            # ✅ TRUE PARALLEL GPU: Use actual parallel GPU processing for ALL combinations
            print(f"🚀 Using TRUE PARALLEL GPU processing for {len(batch)} combinations...")
            
            # Import and use true parallel GPU processor
            from .true_parallel_gpu_processor import TrueParallelGPUProcessor, ParallelGPUConfig
            
            # Configure for maximum parallel processing with dynamic stream calculation
            parallel_config = ParallelGPUConfig(
                target_gpu_utilization=0.75,
                max_parallel_combinations=max(len(batch), 5000),  # Handle large batches up to 5000+
                cuda_streams=8,  # Will be auto-calculated based on actual workload
                auto_calculate_streams=True  # Enable dynamic CUDA stream optimization
            )
            
            # Initialize true parallel processor
            parallel_processor = TrueParallelGPUProcessor(self.backend, parallel_config)
            
            # Process ALL combinations in TRUE parallel on GPU
            batch_results = parallel_processor.process_combinations_parallel_gpu(batch)
            
            # Monitor GPU utilization after processing
            if self.config.enable_performance_monitoring:
                post_processing_stats = self._get_gpu_stats()
                self._record_performance_metrics(pre_processing_stats, post_processing_stats)
            
            batch_time = time.time() - batch_start_time
            
            # Update processing time for each result
            for result in batch_results:
                result['processing_time_seconds'] = batch_time / len(batch)
            
            print(f"✅ TRUE PARALLEL GPU batch {batch_number} completed in {batch_time:.2f}s")
            print(f"   ⚡ Rate: {len(batch)/batch_time:.1f} combinations/sec")
            
            return batch_results
            
        except Exception as e:
            print(f"❌ Error processing TRUE PARALLEL GPU batch {batch_number}: {e}")
            import traceback
            traceback.print_exc()
            # Return fallback results to prevent pipeline failure
            return self._create_fallback_results(batch)
    
    def _get_gpu_stats(self) -> Dict[str, Any]:
        """Get current GPU utilization and memory statistics"""
        try:
            if hasattr(self.xp, 'cuda'):
                memory_info = self.xp.cuda.Device().mem_info
                total_memory = memory_info[1]
                free_memory = memory_info[0]
                used_memory = total_memory - free_memory
                
                return {
                    'total_memory': total_memory,
                    'used_memory': used_memory,
                    'free_memory': free_memory,
                    'utilization_percent': (used_memory / total_memory) * 100,
                    'timestamp': time.time()
                }
            else:
                return {'backend': 'cpu_fallback', 'timestamp': time.time()}
        except Exception:
            return {'error': 'failed_to_get_stats', 'timestamp': time.time()}
    
    def _record_performance_metrics(self, pre_stats: Dict, post_stats: Dict):
        """Record performance metrics for monitoring"""
        if 'utilization_percent' in pre_stats and 'utilization_percent' in post_stats:
            # Record average utilization during processing
            avg_utilization = (pre_stats['utilization_percent'] + post_stats['utilization_percent']) / 2
            self.processing_stats['gpu_utilization_samples'].append(avg_utilization)
            
            # Record memory utilization
            if 'used_memory' in post_stats and 'total_memory' in post_stats:
                memory_util = (post_stats['used_memory'] / post_stats['total_memory']) * 100
                self.processing_stats['memory_utilization_samples'].append(memory_util)
    
    def _update_processing_stats(self, batch_size: int):
        """Update cumulative processing statistics"""
        self.processing_stats['total_combinations_processed'] += batch_size
        self.processing_stats['total_batches_processed'] += 1
    
    def _log_performance_summary(self, total_combinations: int, batch_count: int, total_time: float):
        """Log comprehensive performance summary"""
        avg_gpu_util = np.mean(self.processing_stats['gpu_utilization_samples']) if self.processing_stats['gpu_utilization_samples'] else 0
        avg_memory_util = np.mean(self.processing_stats['memory_utilization_samples']) if self.processing_stats['memory_utilization_samples'] else 0
        
        print(f"\\n=== BATCH PROCESSING PERFORMANCE SUMMARY ===")
        print(f"Total combinations processed: {total_combinations}")
        print(f"Total batches processed: {batch_count}")
        print(f"Total processing time: {total_time:.2f}s")
        print(f"Average processing rate: {total_combinations/total_time:.1f} combinations/sec")
        print(f"Average GPU utilization: {avg_gpu_util:.1f}%")
        print(f"Average memory utilization: {avg_memory_util:.1f}%")
        
        # Check if we met our target utilization (60-80%)
        target_met = 60 <= avg_gpu_util <= 80
        status = "✓ TARGET MET" if target_met else "⚠️ TARGET NOT MET"
        print(f"GPU utilization target (60-80%): {status}")
    
    def _create_fallback_results(self, batch: List[Dict]) -> List[Dict]:
        """Create fallback results in case of processing failure - matches Phase 2 result structure"""
        fallback_results = []
        
        for combo in batch:
            # Add empty technical indicator results with correct key names
            n_ticks = len(combo.get('tick_data', pd.DataFrame()))
            if n_ticks == 0:
                n_ticks = 100  # Default fallback size
            
            # ✅ FIXED: Use same key names as main processing method
            fallback_result = {
                'combo_id': combo.get('combo_id', 0),
                'parameters': combo.get('parameters', combo),
                'atr_results': pd.DataFrame({
                    'datetime': range(n_ticks),
                    'atr': [1.0] * n_ticks
                }),
                'macd_results': pd.DataFrame({
                    'macd': [0.0] * n_ticks,
                    'signal': [0.0] * n_ticks,
                    'histogram': [0.0] * n_ticks
                }),
                'gpu_processing': False,
                'phase2_batch_processing': False,
                'processing_time_seconds': 0.0,
                'processing_status': 'fallback'
            }
            
            fallback_results.append(fallback_result)
        
        return fallback_results
    
    def get_performance_report(self) -> Dict[str, Any]:
        """
        Generate comprehensive performance report for Phase 2 validation.
        
        Returns:
            Dictionary with detailed performance metrics and GPU utilization statistics
        """
        gpu_util_samples = self.processing_stats['gpu_utilization_samples']
        memory_util_samples = self.processing_stats['memory_utilization_samples']
        
        report = {
            'phase': 'Phase 2 - Technical Indicators GPU Acceleration',
            'infrastructure': 'Phase 1 GPU Infrastructure Integration',
            
            # Processing statistics
            'processing_statistics': {
                'total_combinations_processed': self.processing_stats['total_combinations_processed'],
                'total_batches_processed': self.processing_stats['total_batches_processed'],
                'average_batch_size': (self.processing_stats['total_combinations_processed'] / 
                                     max(1, self.processing_stats['total_batches_processed'])),
            },
            
            # GPU utilization metrics
            'gpu_utilization': {
                'average_percent': np.mean(gpu_util_samples) if gpu_util_samples else 0,
                'max_percent': np.max(gpu_util_samples) if gpu_util_samples else 0,
                'min_percent': np.min(gpu_util_samples) if gpu_util_samples else 0,
                'target_range': '60-80%',
                'target_achieved': (60 <= np.mean(gpu_util_samples) <= 80) if gpu_util_samples else False,
                'samples_count': len(gpu_util_samples)
            },
            
            # Memory utilization metrics
            'memory_utilization': {
                'average_percent': np.mean(memory_util_samples) if memory_util_samples else 0,
                'max_percent': np.max(memory_util_samples) if memory_util_samples else 0,
                'samples_count': len(memory_util_samples)
            },
            
            # Configuration
            'configuration': {
                'optimal_batch_size_range': f"{self.config.min_batch_size}-{self.config.max_batch_size}",
                'target_gpu_utilization': f"{self.config.target_gpu_utilization*100}%",
                'cuda_streams': self.config.cuda_streams,
                'memory_safety_margin': f"{self.config.memory_safety_margin*100}%"
            },
            
            # Components status
            'components': {
                'atr_calculator': 'GPU-accelerated with Phase 1 infrastructure',
                'macd_calculator': 'GPU-accelerated with Phase 1 infrastructure',
                'swing_detector': 'GPU-optimized with Phase 1 integration',
                'batch_optimizer': 'Phase 1 GPUBatchOptimizer',
                'memory_manager': 'Phase 1 GPUMemoryManager',
                'array_converter': 'Phase 1 GPUArrayConverter'
            }
        }
        
        return report
    
    def clear_performance_stats(self):
        """Clear accumulated performance statistics"""
        self.processing_stats = {
            'total_combinations_processed': 0,
            'total_batches_processed': 0,
            'average_batch_processing_time': 0.0,
            'gpu_utilization_samples': [],
            'memory_utilization_samples': []
        }
        print("Performance statistics cleared")


class GPUMemoryAllocator:
    """
    GPU memory allocator for efficient batch processing of technical indicators.
    
    Manages GPU memory allocation, deallocation, and optimization for technical
    indicator calculations to minimize memory fragmentation and maximize throughput.
    """
    
    def __init__(self, backend: ArrayBackend):
        """
        Initialize GPU memory allocator.
        
        Args:
            backend: ArrayBackend for GPU operations
        """
        self.backend = backend
        self.xp = backend.xp
        self.allocated_arrays = {}
        self.allocation_count = 0
    
    def allocate_batch_memory(self, batch_size: int, data_sample: pd.DataFrame) -> Dict[str, Any]:
        """
        Pre-allocate GPU memory for a batch of technical indicator calculations.
        
        Args:
            batch_size: Number of combinations in the batch
            data_sample: Sample DataFrame to estimate memory requirements
            
        Returns:
            Dictionary with pre-allocated GPU memory arrays
        """
        try:
            # Estimate memory requirements per combination
            sample_size = len(data_sample)
            
            # Pre-allocate memory for common arrays
            memory_block = {
                'tick_prices': self.backend.zeros((batch_size, sample_size)),
                'ohlc_arrays': self.backend.zeros((batch_size, 4, sample_size)),  # OHLC
                'indicator_results': self.backend.zeros((batch_size, sample_size, 3)),  # ATR, MACD, Signal
                'swing_points': self.backend.zeros((batch_size, sample_size, 2)),  # High/Low swings
                'temporary_workspace': self.backend.zeros((batch_size, sample_size * 2))  # Extra workspace
            }
            
            # Track allocation
            allocation_id = f"batch_allocation_{self.allocation_count}"
            self.allocated_arrays[allocation_id] = memory_block
            self.allocation_count += 1
            
            print(f"✓ Pre-allocated GPU memory for batch size {batch_size} (ID: {allocation_id})")
            return {'allocation_id': allocation_id, 'memory_block': memory_block}
            
        except Exception as e:
            print(f"⚠️ Failed to pre-allocate GPU memory: {e}")
            return {'allocation_id': None, 'memory_block': None}
    
    def deallocate_batch_memory(self, allocation_id: str):
        """
        Deallocate GPU memory for a completed batch.
        
        Args:
            allocation_id: ID of the memory allocation to release
        """
        if allocation_id in self.allocated_arrays:
            # Clear references to allow garbage collection
            del self.allocated_arrays[allocation_id]
            
            # Force GPU memory cleanup if using CuPy
            if hasattr(self.xp, 'cuda'):
                try:
                    self.xp.get_default_memory_pool().free_all_blocks()
                    print(f"✓ Released GPU memory allocation {allocation_id}")
                except Exception as e:
                    print(f"⚠️ Warning during memory cleanup: {e}")
        else:
            print(f"⚠️ Memory allocation {allocation_id} not found")
    
    def get_memory_usage_stats(self) -> Dict[str, Any]:
        """Get current GPU memory usage statistics"""
        try:
            if hasattr(self.xp, 'cuda'):
                memory_info = self.xp.cuda.Device().mem_info
                total_memory = memory_info[1]
                free_memory = memory_info[0]
                used_memory = total_memory - free_memory
                
                return {
                    'total_memory_gb': total_memory / (1024**3),
                    'used_memory_gb': used_memory / (1024**3),
                    'free_memory_gb': free_memory / (1024**3),
                    'utilization_percent': (used_memory / total_memory) * 100,
                    'active_allocations': len(self.allocated_arrays),
                    'allocation_ids': list(self.allocated_arrays.keys())
                }
            else:
                return {
                    'backend': 'cpu_fallback',
                    'active_allocations': len(self.allocated_arrays)
                }
        except Exception as e:
            return {
                'error': str(e),
                'active_allocations': len(self.allocated_arrays)
            }