# Phase 6 Implementation Plan: GPU-Accelerated Position Signal Generation

## Overview

Phase 6 builds upon the bias classification from Phase 5 by combining market sentiment (bias) with price position analysis to generate actionable trading signals. This phase transforms abstract market bias into concrete position recommendations while maintaining GPU acceleration throughout.

## Core Objective

Create a GPU-accelerated position signal generator that:
- Combines bias classifications (-2 to +2) with price position metrics
- Applies threshold-based logic specific to each bias class
- Outputs discrete trading signals: Long (1), Short (-1), or No Position (0)
- Maintains zero-copy GPU operations for seamless pipeline integration

## Technical Requirements

### Input Dependencies
1. **From Phase 5**:
   - `bias_numeric`: Market sentiment classification (-2 to +2)
   - Full bias classification arrays on GPU

2. **From Phase 4**:
   - `price_position_in_range`: Normalized price position (0 to 1)
   - All normalized features on GPU

3. **From Phase 3**:
   - Raw technical indicators for reference
   - Swing high/low data for price range calculation

### Output Deliverables
- `position_signal`: Primary output (-1, 0, 1) as GPU array
- Maintain all arrays on GPU for downstream processing

## Implementation Architecture

### 1. Core Components

#### GPUPositionGenerator Class
```python
class GPUPositionGenerator:
    def __init__(self, array_backend: ArrayBackend, threshold_config: Optional[ThresholdConfig] = None):
        """
        Initialize position generator with GPU backend.
        
        Args:
            array_backend: GPU array management system
            threshold_config: Configurable thresholds per bias class
        """
```

#### ThresholdConfig Structure
```python
@dataclass
class ThresholdConfig:
    """Position generation thresholds for each bias class."""
    strong_bullish_buy: float = 0.35
    bullish_buy: float = 0.2
    bullish_sell: float = 0.9
    neutral_buy: float = 0.2
    neutral_sell: float = 0.9
    bearish_buy: float = 0.1
    bearish_sell: float = 0.8
    strong_bearish_sell: float = 0.65
```

### 2. Algorithm Implementation

#### Decision Matrix (Legacy-Compatible)
Based on the legacy `assign_position_signal` function:

| Bias Class | Buy Threshold | Sell Threshold | Logic |
|------------|---------------|----------------|-------|
| Strong Bullish (2) | < 0.35 | None | Long only when price low |
| Bullish (1) | < 0.2 | > 0.9 | Favor long, short at extremes |
| Neutral (0) | < 0.2 | > 0.9 | Balanced approach |
| Bearish (-1) | < 0.1 | > 0.8 | Favor short, long at extremes |
| Strong Bearish (-2) | None | > 0.65 | Short only when price high |

#### GPU Vectorized Implementation
```python
def compute_position_signals(self, 
                           bias_numeric: cp.ndarray,
                           price_position: cp.ndarray,
                           threshold_config: Optional[ThresholdConfig] = None) -> cp.ndarray:
    """
    Generate position signals using vectorized GPU operations.
    
    Implementation approach:
    1. Create boolean masks for each bias class
    2. Apply threshold logic using CuPy's where operations
    3. Combine results without loops or transfers
    """
```

### 3. Pipeline Integration

#### Extend UnifiedTechnicalIndicatorsPipeline
```python
def compute_all_indicators_features_bias_and_positions(
    self,
    data: pd.DataFrame,
    bias_thresholds: Optional[BiasThresholdConfig] = None,
    position_thresholds: Optional[PositionThresholdConfig] = None
) -> pd.DataFrame:
    """
    Complete Phase 3 + 4 + 5 + 6 pipeline.
    Adds position_signal column to output.
    """
```

## Implementation Steps

### Phase 6A: Core Position Generator
1. **Create base structure**
   - Set up `src/feature_engineering/position_generator.py`
   - Define ThresholdConfig dataclass
   - Implement GPUPositionGenerator class skeleton

2. **Implement decision logic**
   - Port legacy threshold logic to GPU
   - Create vectorized boolean masking operations
   - Handle edge cases (NaN, out-of-range values)

3. **Write comprehensive tests**
   - Unit tests for each bias class
   - Edge case testing
   - Performance benchmarks

### Phase 6B: Pipeline Integration
1. **Extend unified pipeline**
   - Add position generation method
   - Ensure GPU array flow
   - Update return DataFrame structure

2. **Integration testing**
   - Test full Phase 3-6 pipeline
   - Verify data flow and shapes
   - Performance testing

3. **Documentation and examples**
   - Usage examples
   - Configuration guide
   - Performance optimization tips

## Testing Strategy

### Unit Tests
- Test each bias class independently
- Verify threshold boundaries
- Test NaN and edge case handling
- Validate output ranges (-1, 0, 1)

### Integration Tests
- Full pipeline execution (Phases 3-6)
- Large dataset performance
- Memory usage validation
- GPU utilization metrics

### Validation Tests
- Compare with legacy implementation
- Statistical distribution analysis
- Signal quality metrics

## Performance Targets

- **Overhead**: < 0.05 seconds on Phase 5 output
- **Throughput**: Match Phase 5 speed (1,600+ points/second)
- **Memory**: Minimal additional allocation
- **GPU Utilization**: Maintain 85%+ utilization

## Risk Mitigation

### Technical Risks
1. **Threshold Sensitivity**
   - Solution: Configurable thresholds with validation
   - Default to proven legacy values

2. **GPU Memory**
   - Solution: Reuse existing arrays where possible
   - Implement chunking if needed

3. **Numerical Precision**
   - Solution: Use float32 consistently
   - Add epsilon for boundary comparisons

### Implementation Risks
1. **Legacy Compatibility**
   - Solution: Exact replication of logic first
   - Optimization only after validation

2. **Integration Complexity**
   - Solution: Incremental integration
   - Comprehensive testing at each step

## Success Criteria

1. **Functional Requirements**
   - ✅ Generates position signals matching legacy logic
   - ✅ Maintains GPU acceleration throughout
   - ✅ Integrates seamlessly with Phase 5

2. **Performance Requirements**
   - ✅ < 0.05s overhead on Phase 5
   - ✅ Handles 100K+ rows efficiently
   - ✅ No memory leaks

3. **Quality Requirements**
   - ✅ 100% test coverage on critical paths
   - ✅ Clear documentation
   - ✅ Production-ready error handling


## Next Steps After Phase 6

1. **Strategy Execution**: Implement trade execution logic
2. **Risk Management**: Position sizing and portfolio management
3. **Performance Analytics**: Real-time strategy metrics
4. **Production Deployment**: Live trading integration