# Technical Indicators NumPy Development Plan

## Overview
This document outlines the development process for refactoring technical indicators from pandas-based implementation to numpy-based calculations. The focus is on core computation of candles and indicators using NumPy with the ability to reconstruct DataFrames.

## Core Objective
- **Current State**: Technical indicators use pandas DataFrames and Series
- **Target State**: Core calculations performed using NumPy arrays with GPU-ready architecture
- **Key Requirements**: 
  - Ability to reconstruct DataFrames with preserved metadata
  - GPU parallelization compatibility (NumPy/CuPy interoperability)
  - Memory layout optimization for efficient GPU transfers

## GPU-Ready Architecture

### Core Components
```
┌─────────────────────────────────────────┐
│           DataFrame Interface           │  ← Input/Output
├─────────────────────────────────────────┤
│         Metadata Management            │  ← Index/column preservation
├─────────────────────────────────────────┤
│        Array Abstraction Layer         │  ← NumPy/CuPy compatibility
├─────────────────────────────────────────┤
│          Computation Engine            │  ← GPU-ready calculations
└─────────────────────────────────────────┘
```

### Processing Flow
```python
DataFrame Input
    ↓
Extract Arrays + Metadata (with memory optimization)
    ↓
Array Backend Selection (NumPy/CuPy)
    ↓
GPU-Ready Calculations (Candles, MACD, ATR, Swing Points)
    ↓
Reconstruct DataFrame (with preserved metadata)
    ↓
DataFrame Output (with computed indicators)
```

## Core Components

### 1. Metadata Management
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

### 2. GPU-Ready Array Converter
```python
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
```

### 3. Array Abstraction Layer
```python
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
        if hasattr(arr, 'get'):
            return arr.get()
        return np.asarray(arr)

# Union type for arrays that work on both CPU and GPU
ArrayLike = Union[np.ndarray, 'cupy.ndarray']
```

### 4. GPU-Ready Calculators

```python
class CandleGenerator:
    """Generate OHLC candles with GPU support"""
    
    def __init__(self, backend: ArrayBackend):
        self.backend = backend
        self.xp = backend.xp
    
    def generate_ohlc(self, prices: ArrayLike, timestamps: ArrayLike, 
                      granularity: str) -> Dict[str, ArrayLike]:
        """Generate OHLC candles from price ticks (CPU or GPU)"""
        # Use self.xp instead of np for GPU compatibility
        # Implementation using backend.xp operations...
        
class MACDCalculator:
    """MACD calculation with GPU support"""
    
    def __init__(self, backend: ArrayBackend):
        self.backend = backend
        self.xp = backend.xp
    
    def compute_macd(self, prices: ArrayLike, se: int = 12, le: int = 26, 
                     cont: int = 9) -> Dict[str, ArrayLike]:
        """Compute MACD, signal, and histogram (CPU or GPU)"""
        # Use self.xp for all array operations
        # Implementation using backend.xp operations...

class ATRCalculator:
    """ATR calculation with GPU support"""
    
    def __init__(self, backend: ArrayBackend):
        self.backend = backend
        self.xp = backend.xp
    
    def compute_atr(self, high: ArrayLike, low: ArrayLike, close: ArrayLike, 
                    period: int = 14) -> ArrayLike:
        """Compute Average True Range (CPU or GPU)"""
        # Use self.xp for all array operations
        # Implementation using backend.xp operations...

class SwingPointDetector:
    """Swing point detection with GPU support"""
    
    def __init__(self, backend: ArrayBackend):
        self.backend = backend
        self.xp = backend.xp
    
    def detect_swings(self, high: ArrayLike, low: ArrayLike, 
                      lookback: int = 20) -> Dict[str, ArrayLike]:
        """Detect swing highs and lows (CPU or GPU)"""
        # Use self.xp for all array operations
        # Implementation using backend.xp operations...
```

## Implementation Plan

### Phase 1: GPU-Ready Infrastructure
- [ ] DataFrameMetadata class
- [ ] GPUArrayConverter with memory optimization
- [ ] ArrayBackend abstraction layer
- [ ] ArrayLike type definitions and validation

### Phase 2: GPU-Compatible Calculators
- [ ] CandleGenerator with ArrayBackend
- [ ] MACDCalculator with ArrayBackend
- [ ] ATRCalculator with ArrayBackend  
- [ ] SwingPointDetector with ArrayBackend

### Phase 3: GPU Integration & Testing
- [ ] Unified pipeline with backend selection
- [ ] CPU/GPU performance comparison
- [ ] Memory transfer optimization
- [ ] Error handling and fallback mechanisms

## Usage Example

```python
# Initialize backend (CPU or GPU)
backend = ArrayBackend('cupy')  # or 'numpy' for CPU

# Convert DataFrame to GPU-optimized arrays
converter = GPUArrayConverter()
arrays, metadata = converter.to_arrays(df, dtype='float32', contiguous=True)

# Transfer arrays to GPU if using CuPy
gpu_arrays = {key: backend.asarray(arr) for key, arr in arrays.items()}

# Initialize calculators with backend
candle_gen = CandleGenerator(backend)
macd_calc = MACDCalculator(backend)
atr_calc = ATRCalculator(backend)

# Generate candles (on GPU if backend is CuPy)
candles = candle_gen.generate_ohlc(gpu_arrays['price'], gpu_arrays['datetime'], '15min')

# Compute indicators (on GPU if backend is CuPy)
macd_data = macd_calc.compute_macd(candles['close'])
atr_data = atr_calc.compute_atr(candles['high'], candles['low'], candles['close'])

# Combine results
result_arrays = {**gpu_arrays, **candles, **macd_data, 'atr': atr_data}

# Reconstruct DataFrame (automatically transfers from GPU to CPU)
result_df = converter.from_arrays(result_arrays, metadata)
```

## GPU Preparation Benefits
- **Performance**: 2-5x CPU speedup + potential 10-50x GPU acceleration
- **Memory**: Optimized memory layout for efficient GPU transfers
- **Scalability**: GPU batch processing capability for large datasets
- **Future-Proof**: Ready for immediate GPU deployment when needed

## Key Requirements for GPU Readiness
- **Array Abstraction**: Unified interface for NumPy/CuPy operations
- **Memory Optimization**: Contiguous arrays with appropriate dtypes (float32)
- **Backend Flexibility**: Runtime selection between CPU/GPU processing
- **Numerical Accuracy**: Consistent results across CPU and GPU backends
- **Error Handling**: Graceful fallback from GPU to CPU when needed

## Critical GPU Preparation Elements
1. **ArrayLike Type System**: Support both np.ndarray and cupy.ndarray
2. **Memory Layout**: Ensure C-contiguous arrays for optimal GPU transfer
3. **Dtype Standardization**: Use float32 for GPU efficiency
4. **Backend Abstraction**: Calculators work with any array backend
5. **Transfer Optimization**: Minimize CPU-GPU data movement

This plan ensures the technical indicators are immediately ready for GPU parallelization while maintaining full CPU compatibility and DataFrame reconstruction capability.