"""
GPU-accelerated parallel processing module for massive parameter combination generation.

This module provides components for:
- Parameter combination generation and management
- Contract data loading and caching  
- GPU batch optimization (Phase 1.2+)
- Memory-efficient processing coordination

Phase 1.1 Complete Implementation:
- Parameter generation with ~115K combinations
- LRU-cached contract data management
- Memory-efficient batch processing
- Comprehensive validation and testing

Phase 1.2.1 Complete Implementation:
- Advanced GPU memory pool with intelligent reuse
- Sustained processing without memory fragmentation
- Memory pressure detection and handling
- Enhanced combination processor with memory management

Phase 1.2.2 Complete Implementation:
- Asynchronous processing pipeline with parallel GPU workers
- Producer-consumer pattern with intelligent task queuing
- Concurrent I/O operations preventing GPU blocking
- High-level orchestrator for multi-contract processing
"""

__version__ = "1.2.2"
__author__ = "ATS_3 Development Team"

# Import main components
from .parameter_combinations import (
    generate_all_parameter_combinations,
    generate_combination_batch,
    get_combination_sample,
    validate_complete_combination,
    export_combinations_to_file,
    get_combination_counts,
    CONTRACTS,
    DATE_RANGE
)

from .contract_data_manager import (
    ContractDataManager,
    ValidationResult
)

# Integration classes (defined below)
from .integration import (
    Phase1Integration,
    IntegrationValidator
)

# Phase 1.2.1: Advanced Memory Management
from .advanced_memory_manager import (
    AdvancedGPUMemoryPool,
    MemoryBlock,
    MemoryStats
)

from .enhanced_gpu_processor import (
    EnhancedGPUCombinationProcessor
)

# Phase 1.2.2: Asynchronous Processing Pipeline
from .async_processing_pipeline import (
    AsyncProcessingPipeline,
    ProcessingTask,
    ProcessingResult
)

from .async_orchestrator import (
    AsyncGPUOrchestrator
)

__all__ = [
    # Parameter generation
    'generate_all_parameter_combinations',
    'generate_combination_batch', 
    'get_combination_sample',
    'validate_complete_combination',
    'export_combinations_to_file',
    'get_combination_counts',
    'CONTRACTS',
    'DATE_RANGE',
    
    # Data management
    'ContractDataManager',
    'ValidationResult',
    
    # Integration
    'Phase1Integration',
    'IntegrationValidator',
    
    # Phase 1.2.1: Advanced Memory Management
    'AdvancedGPUMemoryPool',
    'MemoryBlock', 
    'MemoryStats',
    'EnhancedGPUCombinationProcessor',
    
    # Phase 1.2.2: Asynchronous Processing Pipeline
    'AsyncProcessingPipeline',
    'ProcessingTask',
    'ProcessingResult',
    'AsyncGPUOrchestrator'
]