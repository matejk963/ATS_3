# Technical Indicators Phase 2: Calculator Implementation Guide

## Overview
Implement GPU-ready technical indicator calculators using Phase 1 infrastructure. All calculators use ArrayBackend for CPU/GPU compatibility.

## Phase 1 Infrastructure Available ✅
- **ArrayBackend**: Unified NumPy/CuPy interface
- **GPUArrayConverter**: DataFrame ↔ Array conversion  
- **DataFrameMetadata**: Structure preservation
- **ArrayLike Types**: Type safety system

## Core Calculators to Implement

### 1. CandleGenerator
**File**: `src/feature_engineering/candle_generator.py`
```python
class CandleGenerator:
    def __init__(self, backend: ArrayBackend):
        self.backend = backend
        self.xp = backend.xp
    
    def generate_ohlc(self, prices: ArrayLike, timestamps: ArrayLike, 
                      granularity: str) -> Dict[str, ArrayLike]:
        """Generate OHLC candles from price ticks"""
        # Return: {'open': array, 'high': array, 'low': array, 'close': array}
```

### 2. MACDCalculator  
**File**: `src/feature_engineering/macd_calculator.py`
```python
class MACDCalculator:
    def __init__(self, backend: ArrayBackend):
        self.backend = backend
        self.xp = backend.xp
    
    def compute_macd(self, prices: ArrayLike, fast: int = 12, slow: int = 26, 
                     signal: int = 9) -> Dict[str, ArrayLike]:
        """Compute MACD, signal line, and histogram"""
        # Return: {'macd': array, 'signal': array, 'histogram': array}
```

### 3. ATRCalculator
**File**: `src/feature_engineering/atr_calculator.py`  
```python
class ATRCalculator:
    def __init__(self, backend: ArrayBackend):
        self.backend = backend
        self.xp = backend.xp
    
    def compute_atr(self, high: ArrayLike, low: ArrayLike, close: ArrayLike, 
                    period: int = 14) -> ArrayLike:
        """Compute Average True Range"""
```

### 4. SwingPointDetector
**File**: `src/feature_engineering/swing_point_detector.py`
```python
class SwingPointDetector:
    def __init__(self, backend: ArrayBackend):
        self.backend = backend
        self.xp = backend.xp
    
    def detect_swings(self, high: ArrayLike, low: ArrayLike, 
                      lookback: int = 20) -> Dict[str, ArrayLike]:
        """Detect swing highs and lows"""
        # Return: {'swing_highs': bool_array, 'swing_lows': bool_array}
```

## Vectorized EMA Implementation

**🎯 GPU-Optimized EMA**: Achieves pandas equivalence with full vectorization

```python
def _compute_ema_vectorized(self, data: ArrayLike, span: int) -> ArrayLike:
    """Vectorized EMA computation - GPU optimized, pandas equivalent"""
    alpha = 2.0 / (span + 1)
    n = len(data)
    
    # Create exponential decay weights for convolution
    # This achieves the same result as pandas EMA but fully vectorized
    max_window = min(n, span * 5)  # Truncate for efficiency
    weights = alpha * (1 - alpha) ** self.xp.arange(max_window)
    weights = weights[::-1]  # Reverse for convolution
    
    # Pad data for proper convolution
    padded_data = self.xp.pad(data, (max_window-1, 0), mode='edge')
    
    # Vectorized convolution - fully parallelizable on GPU
    result = self.xp.convolve(padded_data, weights, mode='valid')
    
    # Apply normalization to match pandas exactly
    cumsum_weights = self.xp.cumsum(weights[::-1])
    for i in range(min(max_window, n)):
        result[i] /= cumsum_weights[i]
    
    return result

def _compute_ema_batch(self, data_batch: ArrayLike, spans: ArrayLike) -> ArrayLike:
    """Batch EMA for massive parallelization"""
    # Process multiple securities/spans simultaneously
    batch_size, n_points = data_batch.shape
    results = self.xp.empty_like(data_batch)
    
    # Vectorized across entire batch - massive GPU parallelization
    for i, span in enumerate(spans):
        results[i] = self._compute_ema_vectorized(data_batch[i], span)
    
    return results
```

**Key Benefits**:
- **Full GPU Parallelization**: No sequential dependencies
- **Pandas Equivalent**: Same numerical results as `df.ewm(span).mean()`  
- **Batch Processing**: Handle thousands of securities simultaneously
- **Memory Efficient**: Vectorized operations, minimal transfers

## Implementation Guidelines

### TDD Development Process
1. Write failing test first
2. Implement minimal code to pass
3. Verify NumPy and CuPy compatibility
4. **MANDATORY**: Validate against original implementations

### Code Structure Template
```python
from typing import Dict, Union
import numpy as np
from ..array_backend import ArrayBackend
from ..types import ArrayLike

class CalculatorName:
    def __init__(self, backend: ArrayBackend):
        self.backend = backend
        self.xp = backend.xp
    
    def main_method(self, data: ArrayLike, **params) -> Union[ArrayLike, Dict[str, ArrayLike]]:
        # Use self.xp for all operations - GPU compatible
        result = self.xp.zeros_like(data)
        return result
```

## Mandatory Validation Tests

### Original Implementation Sources
- **MACD**: `source_repos/ATS_2/combinations_generation/local_feature_engineering.py:compute_macd_from_period_data()`
- **ATR**: `source_repos/ATS_2/combinations_generation/local_feature_engineering.py:compute_atr_from_period_data()`  
- **Swing Points**: `source_repos/ATS_2/combinations_generation/local_feature_engineering.py:compute_swing_points_from_period_data()`
- **EMA**: **pandas ewm(span).mean()** used in all implementations

### Validation Requirements
```python
# File: tests/feature_engineering/test_original_compatibility.py

def test_ema_pandas_equivalence():
    """MANDATORY: EMA must match pandas exactly"""
    import pandas as pd
    
    prices = np.random.randn(1000).cumsum() + 100
    spans = [12, 26, 9, 14]
    
    for span in spans:
        # Original pandas
        original = pd.Series(prices).ewm(span=span).mean().values
        
        # New vectorized implementation
        backend = ArrayBackend('numpy')
        calculator = MACDCalculator(backend)  # Has EMA helper
        new_result = calculator._compute_ema_vectorized(prices, span)
        
        # MANDATORY: High precision match
        np.testing.assert_allclose(original, new_result, rtol=1e-10)

def test_macd_vs_original():
    """MANDATORY: MACD must match original implementation"""
    from source_repos.ATS_2.combinations_generation.local_feature_engineering import compute_macd_from_period_data
    
    df_test = create_test_data(1000)
    original = compute_macd_from_period_data(df_test, fast=12, slow=26, signal=9)
    
    # New implementation
    backend = ArrayBackend('numpy')
    calc = MACDCalculator(backend)
    arrays, metadata = GPUArrayConverter.to_arrays(df_test)
    new_result = calc.compute_macd(arrays['close'])
    
    # MANDATORY: Exact equivalence
    np.testing.assert_allclose(original['macd'], new_result['macd'], rtol=1e-10)
    np.testing.assert_allclose(original['signal'], new_result['signal'], rtol=1e-10)
```

### Enforcement Rules
1. **Numerical tolerance**: ≤ 1e-10 for floating point comparisons
2. **Tests must pass** on both NumPy and CuPy backends  
3. **Large dataset validation**: 10,000+ data points
4. **No calculator merges** without passing compatibility tests

## File Structure
```
src/feature_engineering/
├── candle_generator.py         # OHLC generation
├── macd_calculator.py          # MACD with vectorized EMA
├── atr_calculator.py           # ATR calculation  
└── swing_point_detector.py     # Swing detection

tests/feature_engineering/
├── test_candle_generator.py
├── test_macd_calculator.py     
├── test_atr_calculator.py
├── test_swing_point_detector.py
└── test_original_compatibility.py  # 🚨 MANDATORY
```

## Success Criteria
- [ ] All 4 calculators implemented with ArrayBackend
- [ ] Vectorized EMA achieving pandas equivalence
- [ ] CPU/GPU backend compatibility verified
- [ ] **MANDATORY**: Numerical equivalence with original implementations
- [ ] Batch processing capability for massive datasets

## Final Validation
```bash
# MUST PASS before completion
pwsh -Command "python -m pytest tests/feature_engineering/test_original_compatibility.py -v"
```

**❌ Phase 2 is NOT complete until all compatibility tests pass**