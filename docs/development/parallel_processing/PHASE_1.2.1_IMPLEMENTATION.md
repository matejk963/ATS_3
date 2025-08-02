# GPU-Accelerated Parallel Processing - Phase 1.2.1: Advanced Memory Management

## Overview

Phase 1.2.1 focuses on **solving GPU memory limitations** that prevent scaling beyond small batches. This phase implements sophisticated GPU memory management to handle massive parameter combination processing without out-of-memory errors.

## Problem Context

**Current Phase 1 Limitation**:
- Processing fails after ~50-100 combinations due to GPU memory fragmentation
- Manual memory cleanup required between batches
- No memory reuse or optimization
- Cannot predict memory requirements for different parameter combinations

**Phase 1.2.1 Solution**:
- Intelligent memory pool management with reuse
- Automatic fragmentation detection and cleanup
- Predictive memory allocation based on data patterns
- Memory pressure handling with graceful degradation

## Phase 1.2.1 Deliverables

### 1. Advanced GPU Memory Pool Manager
**Implementation Location**: `src/gpu_parallel_processing/advanced_memory_manager.py`

```python
"""
Advanced GPU Memory Pool Manager for sustained high-throughput processing
without memory fragmentation or allocation failures.
"""

import cupy as cp
import threading
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict, deque
import numpy as np

@dataclass
class MemoryBlock:
    """Represents a memory block in the GPU pool"""
    size_bytes: int
    shape: Tuple[int, ...]
    dtype: str
    is_free: bool
    allocation_time: float
    last_access_time: float
    usage_count: int = 0
    cupy_array: Optional[cp.ndarray] = None

@dataclass 
class MemoryStats:
    """Memory pool statistics for monitoring and optimization"""
    total_allocations: int = 0
    total_deallocations: int = 0
    peak_usage_bytes: int = 0
    current_usage_bytes: int = 0
    fragmentation_ratio: float = 0.0
    allocation_failures: int = 0
    successful_reuses: int = 0
    defragmentation_count: int = 0

class AdvancedGPUMemoryPool:
    """
    Advanced GPU memory pool optimized for technical indicator processing.
    
    Manages memory blocks for OHLCV data, indicator arrays, and feature arrays
    with intelligent reuse and automatic cleanup.
    """
    
    def __init__(self, 
                 max_pool_size_gb: float = 14.0,
                 fragmentation_threshold: float = 0.25):
        """
        Initialize advanced memory pool.
        
        Args:
            max_pool_size_gb: Maximum GPU memory to use (leave 2GB for system)
            fragmentation_threshold: Trigger cleanup when fragmentation exceeds this
        """
        self.max_pool_size = int(max_pool_size_gb * 1024**3)
        self.fragmentation_threshold = fragmentation_threshold
        
        # Memory block management
        self.free_blocks: Dict[str, List[MemoryBlock]] = defaultdict(list)
        self.allocated_blocks: Dict[int, MemoryBlock] = {}
        self.stats = MemoryStats()
        
        # Size pattern learning for predictive allocation
        self.common_shapes: Dict[Tuple, int] = defaultdict(int)
        self.allocation_history: deque = deque(maxlen=500)
        
        # Thread safety for multi-worker access
        self.lock = threading.RLock()
        
        # Background maintenance
        self.maintenance_active = True
        self.maintenance_thread = threading.Thread(
            target=self._background_maintenance, 
            daemon=True
        )
        self.maintenance_thread.start()
        
        print(f"🚀 GPU Memory Pool initialized: {max_pool_size_gb:.1f}GB max")
    
    def get_array(self, shape: Tuple[int, ...], dtype: str = 'float32') -> cp.ndarray:
        """
        Get GPU array from pool or allocate new one.
        
        Args:
            shape: Required array shape (e.g., (100000, 5) for OHLCV data)
            dtype: Data type (float32 for GPU efficiency)
            
        Returns:
            CuPy array ready for technical indicator processing
        """
        with self.lock:
            # Create key for matching arrays
            array_key = self._create_array_key(shape, dtype)
            size_bytes = self._calculate_array_size(shape, dtype)
            
            # Try to reuse existing block
            reused_block = self._find_reusable_block(array_key, size_bytes)
            if reused_block:
                return self._activate_block(reused_block)
            
            # Check if we need memory cleanup before allocation
            if self._needs_memory_cleanup(size_bytes):
                self._cleanup_memory(size_bytes)
            
            # Allocate new block
            new_block = self._allocate_new_block(shape, dtype, size_bytes)
            if new_block:
                return self._activate_block(new_block)
            
            # Allocation failed - try emergency cleanup
            self._emergency_cleanup()
            new_block = self._allocate_new_block(shape, dtype, size_bytes)
            if new_block:
                return self._activate_block(new_block)
            
            # Complete failure
            self.stats.allocation_failures += 1
            raise RuntimeError(f"GPU memory allocation failed: {size_bytes/1024**2:.1f}MB for shape {shape}")
    
    def return_array(self, arr: cp.ndarray) -> None:
        """
        Return array to pool for reuse.
        
        Args:
            arr: CuPy array to return to pool
        """
        with self.lock:
            arr_id = id(arr)
            if arr_id in self.allocated_blocks:
                block = self.allocated_blocks[arr_id]
                
                # Mark as free and update access time
                block.is_free = True
                block.last_access_time = time.time()
                block.usage_count += 1
                
                # Add to appropriate free pool
                array_key = self._create_array_key(block.shape, block.dtype)
                self.free_blocks[array_key].append(block)
                
                # Remove from allocated tracking
                del self.allocated_blocks[arr_id]
                
                self.stats.total_deallocations += 1
                self.stats.current_usage_bytes -= block.size_bytes
    
    def _find_reusable_block(self, array_key: str, size_bytes: int) -> Optional[MemoryBlock]:
        """Find suitable block for reuse."""
        # Exact match first (most efficient)
        if array_key in self.free_blocks and self.free_blocks[array_key]:
            block = self.free_blocks[array_key].pop(0)
            self.stats.successful_reuses += 1
            return block
        
        # Look for compatible larger blocks
        for key, blocks in self.free_blocks.items():
            if blocks:
                block = blocks[0]
                # Check if block is large enough and not too wasteful
                if (block.size_bytes >= size_bytes and 
                    block.size_bytes <= size_bytes * 1.5):  # Max 50% waste
                    blocks.pop(0)
                    self.stats.successful_reuses += 1
                    return block
        
        return None
    
    def _allocate_new_block(self, shape: Tuple[int, ...], dtype: str, size_bytes: int) -> Optional[MemoryBlock]:
        """Allocate new GPU memory block."""
        try:
            # Create CuPy array
            cupy_array = cp.zeros(shape, dtype=dtype)
            
            # Create memory block
            block = MemoryBlock(
                size_bytes=size_bytes,
                shape=shape,
                dtype=dtype,
                is_free=False,
                allocation_time=time.time(),
                last_access_time=time.time(),
                cupy_array=cupy_array
            )
            
            # Update statistics
            self.stats.total_allocations += 1
            self.stats.current_usage_bytes += size_bytes
            self.stats.peak_usage_bytes = max(self.stats.peak_usage_bytes, 
                                            self.stats.current_usage_bytes)
            
            # Record allocation pattern
            self.common_shapes[shape] += 1
            self.allocation_history.append({
                'timestamp': time.time(),
                'shape': shape,
                'dtype': dtype,
                'size_bytes': size_bytes
            })
            
            return block
            
        except cp.cuda.memory.OutOfMemoryError:
            return None
    
    def _activate_block(self, block: MemoryBlock) -> cp.ndarray:
        """Activate memory block for use."""
        block.is_free = False
        block.last_access_time = time.time()
        
        # Track as allocated
        self.allocated_blocks[id(block.cupy_array)] = block
        self.stats.current_usage_bytes += block.size_bytes
        
        # Zero out array for clean state
        block.cupy_array.fill(0)
        
        return block.cupy_array
    
    def _needs_memory_cleanup(self, required_bytes: int) -> bool:
        """Check if memory cleanup is needed before allocation."""
        available_bytes = self.max_pool_size - self.stats.current_usage_bytes
        return available_bytes < required_bytes * 1.2  # 20% buffer
    
    def _cleanup_memory(self, required_bytes: int) -> None:
        """Clean up memory to make space for allocation."""
        # Remove old unused blocks first (LRU)
        current_time = time.time()
        freed_bytes = 0
        
        for array_key in list(self.free_blocks.keys()):
            blocks = self.free_blocks[array_key]
            
            # Sort by last access time (oldest first)
            blocks.sort(key=lambda b: b.last_access_time)
            
            while blocks and freed_bytes < required_bytes:
                block = blocks.pop(0)
                freed_bytes += block.size_bytes
                self.stats.current_usage_bytes -= block.size_bytes
                
                # Force garbage collection of CuPy array
                del block.cupy_array
                del block
            
            # Remove empty array key
            if not blocks:
                del self.free_blocks[array_key]
        
        print(f"🧹 Memory cleanup: {freed_bytes/1024**2:.1f}MB freed")
    
    def _emergency_cleanup(self) -> None:
        """Emergency memory cleanup - clear everything possible."""
        print("🚨 Emergency GPU memory cleanup...")
        
        # Clear all free blocks
        total_freed = 0
        for blocks in self.free_blocks.values():
            for block in blocks:
                total_freed += block.size_bytes
                del block.cupy_array
                del block
        
        self.free_blocks.clear()
        self.stats.current_usage_bytes = sum(
            block.size_bytes for block in self.allocated_blocks.values()
        )
        
        # Force GPU memory pool cleanup
        cp.get_default_memory_pool().free_all_blocks()
        
        print(f"🗑️  Emergency cleanup: {total_freed/1024**2:.1f}MB freed")
    
    def _background_maintenance(self) -> None:
        """Background thread for memory pool maintenance."""
        while self.maintenance_active:
            try:
                time.sleep(30)  # Run every 30 seconds
                
                with self.lock:
                    # Calculate fragmentation
                    self._update_fragmentation_stats()
                    
                    # Defragment if needed
                    if self.stats.fragmentation_ratio > self.fragmentation_threshold:
                        self._defragment_memory()
                    
                    # Clean up very old unused blocks
                    self._cleanup_old_blocks()
                    
            except Exception as e:
                print(f"⚠️  Memory maintenance error: {e}")
    
    def _update_fragmentation_stats(self) -> None:
        """Update memory fragmentation statistics."""
        if not self.free_blocks:
            self.stats.fragmentation_ratio = 0.0
            return
        
        # Calculate total free memory
        total_free_bytes = sum(
            sum(block.size_bytes for block in blocks)
            for blocks in self.free_blocks.values()
        )
        
        # Find largest contiguous block
        largest_block_bytes = max(
            max(block.size_bytes for block in blocks) if blocks else 0
            for blocks in self.free_blocks.values()
        )
        
        # Fragmentation = 1 - (largest_block / total_free)
        if total_free_bytes > 0:
            self.stats.fragmentation_ratio = 1.0 - (largest_block_bytes / total_free_bytes)
        else:
            self.stats.fragmentation_ratio = 0.0
    
    def _defragment_memory(self) -> None:
        """Defragment memory by consolidating similar-sized blocks."""
        print("🔧 Defragmenting GPU memory pool...")
        
        consolidated_count = 0
        
        # Group blocks by similar sizes for potential consolidation
        for array_key, blocks in self.free_blocks.items():
            if len(blocks) > 1:
                # Keep only most recently used blocks of each size
                blocks.sort(key=lambda b: b.last_access_time, reverse=True)
                
                # Remove older duplicate blocks
                while len(blocks) > 2:  # Keep max 2 blocks per size
                    old_block = blocks.pop()
                    self.stats.current_usage_bytes -= old_block.size_bytes
                    del old_block.cupy_array
                    del old_block
                    consolidated_count += 1
        
        self.stats.defragmentation_count += 1
        print(f"✅ Defragmentation complete: {consolidated_count} blocks consolidated")
    
    def _cleanup_old_blocks(self) -> None:
        """Clean up blocks that haven't been used recently."""
        current_time = time.time()
        old_threshold = 300  # 5 minutes
        
        cleaned_count = 0
        for array_key in list(self.free_blocks.keys()):
            blocks = self.free_blocks[array_key]
            
            # Remove blocks older than threshold
            new_blocks = []
            for block in blocks:
                if current_time - block.last_access_time > old_threshold:
                    self.stats.current_usage_bytes -= block.size_bytes
                    del block.cupy_array
                    del block
                    cleaned_count += 1
                else:
                    new_blocks.append(block)
            
            if new_blocks:
                self.free_blocks[array_key] = new_blocks
            else:
                del self.free_blocks[array_key]
        
        if cleaned_count > 0:
            print(f"🧽 Cleaned {cleaned_count} old memory blocks")
    
    def _create_array_key(self, shape: Tuple[int, ...], dtype: str) -> str:
        """Create unique key for array matching."""
        return f"{shape}_{dtype}"
    
    def _calculate_array_size(self, shape: Tuple[int, ...], dtype: str) -> int:
        """Calculate memory size for array in bytes."""
        element_count = np.prod(shape)
        dtype_size = np.dtype(dtype).itemsize
        return int(element_count * dtype_size)
    
    def get_memory_stats(self) -> Dict:
        """Get comprehensive memory pool statistics."""
        with self.lock:
            free_blocks_count = sum(len(blocks) for blocks in self.free_blocks.values())
            allocated_blocks_count = len(self.allocated_blocks)
            
            # Top 5 most common shapes
            common_shapes = dict(sorted(self.common_shapes.items(), 
                                      key=lambda x: x[1], reverse=True)[:5])
            
            return {
                'current_usage_gb': self.stats.current_usage_bytes / 1024**3,
                'peak_usage_gb': self.stats.peak_usage_bytes / 1024**3,
                'max_pool_size_gb': self.max_pool_size / 1024**3,
                'utilization_percent': (self.stats.current_usage_bytes / self.max_pool_size) * 100,
                'fragmentation_ratio': self.stats.fragmentation_ratio,
                'total_allocations': self.stats.total_allocations,
                'total_deallocations': self.stats.total_deallocations,
                'allocation_failures': self.stats.allocation_failures,
                'successful_reuses': self.stats.successful_reuses,
                'defragmentation_count': self.stats.defragmentation_count,
                'free_blocks_count': free_blocks_count,
                'allocated_blocks_count': allocated_blocks_count,
                'common_shapes': common_shapes,
                'reuse_efficiency_percent': (self.stats.successful_reuses / max(1, self.stats.total_allocations)) * 100
            }
    
    def cleanup(self) -> None:
        """Clean up memory pool resources."""
        print("🛑 Shutting down GPU memory pool...")
        
        self.maintenance_active = False
        if self.maintenance_thread.is_alive():
            self.maintenance_thread.join(timeout=5)
        
        with self.lock:
            # Clean up all blocks
            total_cleaned = 0
            
            # Free blocks
            for blocks in self.free_blocks.values():
                for block in blocks:
                    if block.cupy_array is not None:
                        del block.cupy_array
                    total_cleaned += 1
            
            # Allocated blocks
            for block in self.allocated_blocks.values():
                if block.cupy_array is not None:
                    del block.cupy_array
                total_cleaned += 1
            
            self.free_blocks.clear()
            self.allocated_blocks.clear()
            
            # Force CuPy memory pool cleanup
            cp.get_default_memory_pool().free_all_blocks()
            
            print(f"✅ Memory pool cleanup complete: {total_cleaned} blocks freed")
```

### 2. Enhanced GPU Combination Processor with Memory Management
**Implementation Location**: `src/gpu_parallel_processing/enhanced_gpu_processor.py`

```python
"""
Enhanced GPU Combination Processor with advanced memory management
for sustained high-throughput parameter combination processing.
"""

import time
import pandas as pd
from typing import List, Dict, Optional
from .advanced_memory_manager import AdvancedGPUMemoryPool
from src.feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline
from src.feature_engineering.bias_classifier import ThresholdConfig as BiasThresholdConfig
from src.feature_engineering.position_generator import ThresholdConfig as PositionThresholdConfig

class EnhancedGPUCombinationProcessor:
    """
    Enhanced GPU processor with advanced memory management for
    sustained processing of massive parameter combinations.
    """
    
    def __init__(self, 
                 gpu_memory_pool_gb: float = 14.0,
                 processing_chunk_size: int = 2000000):
        """
        Initialize enhanced processor with memory management.
        
        Args:
            gpu_memory_pool_gb: GPU memory pool size
            processing_chunk_size: Chunk size for pipeline processing
        """
        # Initialize advanced memory pool
        self.memory_pool = AdvancedGPUMemoryPool(
            max_pool_size_gb=gpu_memory_pool_gb,
            fragmentation_threshold=0.25
        )
        
        # Initialize pipeline with memory-aware settings
        self.pipeline = UnifiedTechnicalIndicatorsPipeline(
            chunk_size=processing_chunk_size,
            memory_threshold=0.92  # Leave room for memory pool
        )
        
        # Processing statistics
        self.processing_stats = {
            'combinations_processed': 0,
            'total_processing_time': 0.0,
            'memory_pressure_events': 0,
            'successful_combinations': 0,
            'failed_combinations': 0
        }
        
        print(f"🚀 Enhanced GPU Processor initialized with {gpu_memory_pool_gb:.1f}GB memory pool")
    
    def process_contract_combinations_sustained(self,
                                              contract_data: pd.DataFrame,
                                              combinations_batch: List[Dict],
                                              enable_memory_monitoring: bool = True) -> List[Dict]:
        """
        Process combinations with sustained memory management.
        
        Args:
            contract_data: Contract OHLCV data
            combinations_batch: Parameter combinations to process
            enable_memory_monitoring: Whether to monitor memory during processing
            
        Returns:
            List of processing results with metadata
        """
        results = []
        batch_start_time = time.time()
        
        print(f"🔄 Processing batch: {len(combinations_batch)} combinations")
        
        for i, combo in enumerate(combinations_batch):
            combo_start_time = time.time()
            
            try:
                # Memory monitoring before processing
                if enable_memory_monitoring:
                    self._monitor_memory_before_processing()
                
                # Convert parameters and validate
                ats3_params = self._convert_legacy_parameters(combo)
                if not self._validate_combination_parameters(combo):
                    print(f"⚠️  Skipping invalid combination {combo['combo_id']}")
                    self.processing_stats['failed_combinations'] += 1
                    continue
                
                # Process with memory-managed pipeline
                result_data = self._process_combination_with_memory_management(
                    contract_data, combo, ats3_params
                )
                
                # Create result with metadata
                result = self._create_result_with_memory_stats(combo, result_data)
                results.append(result)
                
                # Update statistics
                combo_time = time.time() - combo_start_time
                self.processing_stats['combinations_processed'] += 1
                self.processing_stats['successful_combinations'] += 1  
                self.processing_stats['total_processing_time'] += combo_time
                
                # Progress reporting
                if (i + 1) % 10 == 0:
                    progress = (i + 1) / len(combinations_batch) * 100
                    avg_time = combo_time
                    eta_minutes = (len(combinations_batch) - i - 1) * avg_time / 60
                    
                    print(f"📊 Progress: {progress:.1f}% ({i+1}/{len(combinations_batch)}) "
                          f"| Avg: {avg_time:.2f}s | ETA: {eta_minutes:.1f}min")
                    
                    # Memory stats
                    if enable_memory_monitoring:
                        memory_stats = self.memory_pool.get_memory_stats()
                        print(f"💾 Memory: {memory_stats['utilization_percent']:.1f}% used, "
                              f"{memory_stats['reuse_efficiency_percent']:.1f}% reuse efficiency")
                
            except Exception as e:
                combo_time = time.time() - combo_start_time
                self.processing_stats['failed_combinations'] += 1
                self.processing_stats['total_processing_time'] += combo_time
                
                print(f"❌ Combination {combo['combo_id']} failed after {combo_time:.2f}s: {e}")
                
                # Handle memory pressure
                if "out of memory" in str(e).lower():
                    self.processing_stats['memory_pressure_events'] += 1
                    self._handle_memory_pressure()
                
                continue
        
        batch_time = time.time() - batch_start_time
        success_rate = (self.processing_stats['successful_combinations'] / 
                       len(combinations_batch) * 100) if combinations_batch else 0
        
        print(f"✅ Batch complete: {len(results)} successful, {success_rate:.1f}% success rate, "
              f"{batch_time:.1f}s total")
        
        return results
    
    def _process_combination_with_memory_management(self,
                                                  contract_data: pd.DataFrame,
                                                  combo: Dict,
                                                  ats3_params: Dict) -> pd.DataFrame:
        """Process single combination with memory management."""
        
        # Pre-allocate arrays for processing if possible
        data_shape = (len(contract_data), 5)  # OHLCV
        
        try:
            # Get managed arrays for intermediate processing
            temp_array = self.memory_pool.get_array(data_shape, 'float32')
            
            # Process through pipeline
            result_data = self.pipeline.compute_all_indicators_features_bias_and_positions(
                data=contract_data,
                candle_granularity=combo['predictor_granularities']['atr_macd'],
                macd_params=ats3_params['macd_params'],
                atr_period=combo['atr_lookback'],
                bias_thresholds=ats3_params['bias_thresholds'],
                position_thresholds=ats3_params['position_thresholds']
            )
            
            # Return temporary array to pool
            self.memory_pool.return_array(temp_array)
            
            return result_data
            
        except Exception as e:
            # Ensure array is returned even on failure
            if 'temp_array' in locals():
                self.memory_pool.return_array(temp_array)
            raise e
    
    def _monitor_memory_before_processing(self) -> None:
        """Monitor memory state before processing combination."""
        memory_stats = self.memory_pool.get_memory_stats()
        
        # Warn if memory utilization is high
        if memory_stats['utilization_percent'] > 85:
            print(f"⚠️  High memory usage: {memory_stats['utilization_percent']:.1f}%")
        
        # Trigger cleanup if fragmentation is high
        if memory_stats['fragmentation_ratio'] > 0.3:
            print(f"🔧 High fragmentation detected: {memory_stats['fragmentation_ratio']:.2f}")
    
    def _handle_memory_pressure(self) -> None:
        """Handle memory pressure situations."""
        print("🚨 Handling memory pressure...")
        
        # Get current memory stats
        memory_stats = self.memory_pool.get_memory_stats()
        print(f"💾 Before cleanup: {memory_stats['utilization_percent']:.1f}% used")
        
        # Force memory cleanup
        import gc
        import cupy as cp
        
        gc.collect()
        cp.get_default_memory_pool().free_all_blocks() 
        
        # Wait for cleanup to complete
        time.sleep(1)
        
        # Check results
        memory_stats = self.memory_pool.get_memory_stats()
        print(f"✅ After cleanup: {memory_stats['utilization_percent']:.1f}% used")
    
    def _convert_legacy_parameters(self, legacy_combo: Dict) -> Dict:
        """Convert legacy parameters to ATS_3 format (from Phase 1)."""
        macd_params = {
            'fast': legacy_combo['macd_params']['short'],
            'slow': legacy_combo['macd_params']['long'], 
            'signal': legacy_combo['macd_params']['signal']
        }
        
        bias_thresholds = BiasThresholdConfig(
            macd_line_lower=legacy_combo['bias_thresholds']['macd_line_lower'],
            macd_line_upper=legacy_combo['bias_thresholds']['macd_line_upper'],
            macd_histogram_lower=legacy_combo['bias_thresholds']['macd_histogram_lower'],
            macd_histogram_upper=legacy_combo['bias_thresholds']['macd_histogram_upper']
        )
        
        strategy = legacy_combo['strategy_thresholds']
        position_thresholds = PositionThresholdConfig(
            strong_bullish_buy=strategy['neutral_buy'] + strategy['strong_bullish_buy_adjust'],
            bullish_buy=strategy['neutral_buy'] + strategy['bullish_buy_adjust'],
            neutral_buy=strategy['neutral_buy'],
            bearish_buy=strategy['neutral_buy'] + strategy['bearish_buy_adjust'],
            strong_bearish_sell=strategy['neutral_sell'] + strategy['strong_bearish_sell_adjust'],
            bearish_sell=strategy['neutral_sell'] + strategy['bearish_sell_adjust'],
            neutral_sell=strategy['neutral_sell'],
            bullish_sell=strategy['neutral_sell'] + strategy['bullish_sell_adjust']
        )
        
        return {
            'macd_params': macd_params,
            'bias_thresholds': bias_thresholds,
            'position_thresholds': position_thresholds
        }
    
    def _validate_combination_parameters(self, combo: Dict) -> bool:
        """Validate combination parameters (from Phase 1)."""
        required_keys = [
            'combo_id', 'contract', 'macd_params', 'atr_lookback',
            'bias_thresholds', 'strategy_thresholds', 'predictor_granularities'
        ]
        
        for key in required_keys:
            if key not in combo:
                return False
        
        macd = combo['macd_params']
        if not all(isinstance(macd[k], int) and macd[k] > 0 for k in ['short', 'long', 'signal']):
            return False
        
        if macd['short'] >= macd['long']:
            return False
        
        return True
    
    def _create_result_with_memory_stats(self, combo: Dict, result_data: pd.DataFrame) -> Dict:
        """Create result with memory statistics."""
        memory_stats = self.memory_pool.get_memory_stats()
        
        return {
            'combo_id': combo['combo_id'],
            'result_data': result_data,
            'metadata': {
                'contract': combo['contract'],
                'date_range': combo['date_range'],
                'predictor_granularities': combo['predictor_granularities'],
                'macd_params': combo['macd_params'],
                'atr_lookback': combo['atr_lookback'],
                'bias_thresholds': combo['bias_thresholds'],
                'strategy_thresholds': combo['strategy_thresholds'],
                'stop_loss': combo['stop_loss'],
                'sl_tp_ratio': combo['sl_tp_ratio'],
                'tp_value': combo['tp_value'],
                'memory_stats': {
                    'peak_memory_gb': memory_stats['peak_usage_gb'],
                    'processing_memory_gb': memory_stats['current_usage_gb'],
                    'reuse_efficiency': memory_stats['reuse_efficiency_percent']
                }
            }
        }
    
    def get_processing_stats(self) -> Dict:
        """Get comprehensive processing statistics."""
        memory_stats = self.memory_pool.get_memory_stats()
        
        avg_processing_time = (self.processing_stats['total_processing_time'] / 
                             max(1, self.processing_stats['combinations_processed']))
        
        return {
            'combinations_processed': self.processing_stats['combinations_processed'],
            'successful_combinations': self.processing_stats['successful_combinations'],
            'failed_combinations': self.processing_stats['failed_combinations'],
            'success_rate_percent': (self.processing_stats['successful_combinations'] / 
                                   max(1, self.processing_stats['combinations_processed']) * 100),
            'average_processing_time_seconds': avg_processing_time,
            'estimated_throughput_per_hour': 3600 / avg_processing_time if avg_processing_time > 0 else 0,
            'memory_pressure_events': self.processing_stats['memory_pressure_events'],
            'memory_stats': memory_stats
        }
    
    def cleanup(self) -> None:
        """Clean up processor resources."""
        print("🛑 Cleaning up Enhanced GPU Processor...")
        self.memory_pool.cleanup()
        print("✅ Enhanced GPU Processor cleanup complete")
```

## Phase 1.2.1 Implementation Checklist

### Core Memory Management
- [ ] Implement `AdvancedGPUMemoryPool` with intelligent allocation
- [ ] Add memory block reuse system with usage tracking
- [ ] Create fragmentation detection and defragmentation
- [ ] Implement LRU eviction for memory pressure handling

### Enhanced Processing
- [ ] Create `EnhancedGPUCombinationProcessor` with memory awareness
- [ ] Add sustained processing capabilities for large batches
- [ ] Implement memory monitoring during combination processing
- [ ] Create memory pressure detection and handling

### Memory Optimization
- [ ] Add predictive allocation based on usage patterns
- [ ] Implement background memory maintenance thread
- [ ] Create memory statistics tracking and reporting
- [ ] Add emergency cleanup mechanisms

### Testing & Validation
- [ ] Test sustained processing of 1,000+ combinations
- [ ] Validate memory reuse efficiency (>70% target)
- [ ] Test memory pressure handling and recovery
- [ ] Benchmark memory fragmentation prevention

## Success Criteria

### Memory Management
- [ ] Process 1,000+ combinations without memory errors
- [ ] Achieve >70% memory reuse efficiency
- [ ] Maintain <25% memory fragmentation under load
- [ ] Handle memory pressure with <5% performance impact

### Processing Performance  
- [ ] Sustain processing rate throughout large batches
- [ ] Reduce memory-related failures to <1%
- [ ] Maintain processing speed within 10% of peak throughout batch
- [ ] Successfully process batches 10x larger than Phase 1

Phase 1.2.1 establishes the memory management foundation required for the advanced features in Phase 1.2.2 (Asynchronous Processing) and Phase 1.2.3 (Performance Monitoring).