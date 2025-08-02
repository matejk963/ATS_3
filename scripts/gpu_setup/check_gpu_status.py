#!/usr/bin/env python3
"""GPU Status Check Script"""

import sys
print(f"Python: {sys.version}")

try:
    import cupy as cp
    print(f"✅ CuPy Version: {cp.__version__}")
    
    # Test GPU availability
    gpu_count = cp.cuda.runtime.getDeviceCount()
    print(f"✅ GPU Devices: {gpu_count}")
    
    # Test basic operation
    test_array = cp.array([1, 2, 3, 4, 5])
    result = cp.sum(test_array)
    print(f"✅ GPU Computation: {result}")
    
    # Memory info
    free_mem, total_mem = cp.cuda.runtime.memGetInfo()
    print(f"✅ GPU Memory: {free_mem/1e9:.1f}GB free / {total_mem/1e9:.1f}GB total")
    
except ImportError as e:
    print(f"❌ CuPy not available: {e}")
except Exception as e:
    print(f"❌ GPU error: {e}")

# Check if validate_gpu_setup.py exists
import os
if os.path.exists('validate_gpu_setup.py'):
    print("✅ validate_gpu_setup.py found")
else:
    print("❌ validate_gpu_setup.py not found")