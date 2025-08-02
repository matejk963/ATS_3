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