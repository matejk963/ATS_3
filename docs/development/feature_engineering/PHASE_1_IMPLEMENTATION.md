# Technical Indicators Phase 1: GPU-Ready Infrastructure Implementation

## Overview
Phase 1 focuses on building the foundational GPU-ready infrastructure components that will enable seamless CPU/GPU array processing while maintaining DataFrame compatibility. This phase implements the core abstractions without touching existing indicator logic.

## Phase 1 Components

### 1. DataFrameMetadata Class
**Purpose**: Preserve DataFrame structure information for reconstruction after array processing.

**Implementation Location**: `src/feature_engineering/metadata.py`

```python
@dataclass
class DataFrameMetadata:
    """Stores DataFrame information for reconstruction"""
    index: pd.Index
    columns: List[str]
    dtypes: Dict[str, np.dtype]
    
    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> 'DataFrameMetadata':
        """Extract metadata from DataFrame"""
        return cls(
            index=df.index.copy(),
            columns=df.columns.tolist(),
            dtypes=df.dtypes.to_dict()
        )
        
    def reconstruct(self, data: Dict[str, np.ndarray]) -> pd.DataFrame:
        """Rebuild DataFrame from arrays using stored metadata"""
        df = pd.DataFrame(data, index=self.index)
        for col, dtype in self.dtypes.items():
            if col in df.columns:
                df[col] = df[col].astype(dtype)
        return df
```

**Key Features**:
- Preserves index, column names, and data types
- Enables exact DataFrame reconstruction
- Minimal memory overhead

### 2. ArrayBackend Abstraction Layer
**Purpose**: Unified interface for NumPy/CuPy operations with runtime backend selection.

**Implementation Location**: `src/feature_engineering/array_backend.py`

```python
from typing import Union
import numpy as np

# Union type for arrays that work on both CPU and GPU
ArrayLike = Union[np.ndarray, 'cupy.ndarray']

class ArrayBackend:
    """Unified interface for NumPy/CuPy operations"""
    
    def __init__(self, backend: str = 'numpy'):
        """Initialize with 'numpy' or 'cupy' backend"""
        self.backend = backend
        self.xp = self._get_array_module()
        
    def _get_array_module(self):
        """Get appropriate array module"""
        if self.backend == 'cupy':
            try:
                import cupy as cp
                return cp
            except ImportError:
                print("CuPy not available, falling back to NumPy")
                return np
        return np
        
    def asarray(self, data, dtype='float32') -> ArrayLike:
        """Convert to appropriate array type"""
        return self.xp.asarray(data, dtype=dtype)
        
    def to_cpu(self, arr: ArrayLike) -> np.ndarray:
        """Transfer array to CPU"""
        if hasattr(arr, 'get'):  # CuPy array
            return arr.get()
        return np.asarray(arr)
    
    def zeros(self, shape, dtype='float32') -> ArrayLike:
        """Create zeros array"""
        return self.xp.zeros(shape, dtype=dtype)
    
    def ones(self, shape, dtype='float32') -> ArrayLike:
        """Create ones array"""
        return self.xp.ones(shape, dtype=dtype)
    
    def empty(self, shape, dtype='float32') -> ArrayLike:
        """Create empty array"""
        return self.xp.empty(shape, dtype=dtype)
```

**Key Features**:
- Runtime backend selection (NumPy/CuPy)
- Automatic fallback to NumPy if CuPy unavailable
- Unified API for common array operations
- GPU memory transfer methods

### 3. GPUArrayConverter
**Purpose**: Convert between DataFrames and GPU-optimized arrays with memory layout optimization.

**Implementation Location**: `src/feature_engineering/gpu_converter.py`

```python
from typing import Dict, Tuple
import numpy as np
import pandas as pd
from .metadata import DataFrameMetadata
from .array_backend import ArrayLike

class GPUArrayConverter:
    """Convert DataFrame ↔ Arrays with GPU compatibility"""
    
    @staticmethod
    def to_arrays(df: pd.DataFrame, dtype: str = 'float32', 
                  contiguous: bool = True) -> Tuple[Dict[str, np.ndarray], DataFrameMetadata]:
        """Convert DataFrame to GPU-optimized arrays + metadata"""
        arrays = {}
        for col in df.columns:
            arr = df[col].values.astype(dtype)
            if contiguous:
                arr = np.ascontiguousarray(arr)
            arrays[col] = arr
        metadata = DataFrameMetadata.from_dataframe(df)
        return arrays, metadata
        
    @staticmethod
    def from_arrays(arrays: Dict[str, ArrayLike], metadata: DataFrameMetadata) -> pd.DataFrame:
        """Reconstruct DataFrame from arrays (CPU or GPU)"""
        # Convert GPU arrays back to CPU if needed
        cpu_arrays = {}
        for key, arr in arrays.items():
            if hasattr(arr, 'get'):  # CuPy array
                cpu_arrays[key] = arr.get()
            else:
                cpu_arrays[key] = arr
        return metadata.reconstruct(cpu_arrays)
    
    @staticmethod
    def optimize_for_gpu(arrays: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        """Optimize array memory layout for GPU transfer"""
        optimized = {}
        for key, arr in arrays.items():
            # Ensure C-contiguous layout
            if not arr.flags.c_contiguous:
                arr = np.ascontiguousarray(arr)
            # Ensure float32 dtype for GPU efficiency
            if arr.dtype != np.float32:
                arr = arr.astype(np.float32)
            optimized[key] = arr
        return optimized
```

**Key Features**:
- Memory layout optimization (C-contiguous arrays)
- Dtype standardization (float32 for GPU efficiency)
- Automatic GPU↔CPU array conversion
- Metadata preservation during conversion

### 4. ArrayLike Type Definitions
**Purpose**: Type system supporting both NumPy and CuPy arrays.

**Implementation Location**: `src/feature_engineering/types.py`

```python
from typing import Union, Protocol, runtime_checkable
import numpy as np

# Union type for arrays that work on both CPU and GPU
ArrayLike = Union[np.ndarray, 'cupy.ndarray']

@runtime_checkable
class ArrayProtocol(Protocol):
    """Protocol for array-like objects"""
    shape: tuple
    dtype: np.dtype
    
    def __array__(self) -> np.ndarray:
        """Convert to NumPy array"""
        ...
    
    def astype(self, dtype) -> 'ArrayProtocol':
        """Convert dtype"""
        ...

def is_gpu_array(arr: ArrayLike) -> bool:
    """Check if array is on GPU (CuPy array)"""
    return hasattr(arr, 'get')

def ensure_cpu_array(arr: ArrayLike) -> np.ndarray:
    """Ensure array is on CPU"""
    if is_gpu_array(arr):
        return arr.get()
    return np.asarray(arr)

def validate_array_compatibility(arr1: ArrayLike, arr2: ArrayLike) -> bool:
    """Validate that two arrays are compatible for operations"""
    return (
        arr1.shape == arr2.shape and
        type(arr1) == type(arr2) and  # Same backend (NumPy/CuPy)
        arr1.dtype == arr2.dtype
    )
```

**Key Features**:
- Type safety for CPU/GPU arrays
- Runtime type checking
- Array compatibility validation
- GPU detection utilities

## Phase 1 Implementation Checklist

### Core Infrastructure
- [ ] Create `src/feature_engineering/` package structure
- [ ] Implement `DataFrameMetadata` class with tests
- [ ] Implement `ArrayBackend` abstraction with NumPy/CuPy support
- [ ] Implement `GPUArrayConverter` with memory optimization
- [ ] Define `ArrayLike` types and validation utilities

### Testing Infrastructure  
- [ ] Create test suite for `DataFrameMetadata` reconstruction
- [ ] Create test suite for `ArrayBackend` with mock CuPy
- [ ] Create test suite for `GPUArrayConverter` round-trip conversion
- [ ] Create performance benchmarks for array conversion
- [ ] Create memory usage validation tests

### Integration Points
- [ ] Create factory functions for backend selection
- [ ] Implement configuration system for backend preferences
- [ ] Create validation utilities for array operations
- [ ] Implement error handling and fallback mechanisms

## File Structure
```
src/feature_engineering/
├── __init__.py
├── metadata.py          # DataFrameMetadata class
├── array_backend.py     # ArrayBackend abstraction
├── gpu_converter.py     # GPUArrayConverter class
├── types.py            # ArrayLike types and utilities
└── config.py           # Configuration and factory functions

tests/feature_engineering/
├── test_metadata.py
├── test_array_backend.py
├── test_gpu_converter.py
├── test_types.py
└── test_integration.py
```

## Usage Example (Phase 1)
```python
from src.feature_engineering import ArrayBackend, GPUArrayConverter, DataFrameMetadata

# Initialize backend
backend = ArrayBackend('numpy')  # or 'cupy' for GPU

# Convert DataFrame to arrays
converter = GPUArrayConverter()
arrays, metadata = converter.to_arrays(df, dtype='float32', contiguous=True)

# Transfer to selected backend
backend_arrays = {key: backend.asarray(arr) for key, arr in arrays.items()}

# Perform operations (placeholder for Phase 2)
# ... array operations using backend.xp ...

# Reconstruct DataFrame
result_df = converter.from_arrays(backend_arrays, metadata)
```

## Success Criteria
- [ ] All DataFrame→Array→DataFrame conversions preserve data integrity
- [ ] Backend switching works seamlessly between NumPy and CuPy
- [ ] Memory layout is optimized for GPU transfer (C-contiguous, float32)
- [ ] Type system properly handles both CPU and GPU arrays
- [ ] Performance overhead is minimal (<5% for conversion operations)

## Next Phase Integration
Phase 1 components will be consumed by Phase 2 calculator implementations:
- `CandleGenerator(backend)`
- `MACDCalculator(backend)` 
- `ATRCalculator(backend)`
- `SwingPointDetector(backend)`

This infrastructure ensures all Phase 2 calculators are immediately GPU-ready while maintaining full CPU compatibility.