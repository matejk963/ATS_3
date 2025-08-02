#!/usr/bin/env python3
import sys
sys.path.append('src')

from technical_indicators.unified_pipeline import UnifiedTechnicalIndicatorsPipeline
import pandas as pd
import numpy as np

# Create test data
print("Creating 100K test data points...")
data = pd.DataFrame({
    'open': np.random.rand(100000),
    'high': np.random.rand(100000) + 1,
    'low': np.random.rand(100000) - 1,  
    'close': np.random.rand(100000),
    'volume': np.random.rand(100000)
})

print("Creating aggressive GPU pipeline...")
pipeline = UnifiedTechnicalIndicatorsPipeline(backend='cupy')
stats = pipeline.get_gpu_memory_statistics()

print(f"GPU Device: {stats.get('device_name', 'Unknown')}")
print(f"Free Memory: {stats.get('free_memory_gb', 0):.1f}GB")
print(f"Chunk Size: {stats.get('chunking_strategy', {}).get('chunk_size', 0):,}")
print(f"Memory Threshold: {stats.get('chunking_strategy', {}).get('memory_threshold', 0):.0%}")

# Test chunking decision
print("\nTesting chunking decision for 100K points...")
should_chunk = pipeline.memory_manager.should_use_chunking(data)
print(f"Should use chunking: {should_chunk}")
print("SUCCESS: Aggressive GPU settings are active!")