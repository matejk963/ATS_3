# Phase 3.1 Implementation: Legacy-Compatible Swing Detection

## Problem Statement

**Current Issue**: ATS_3 Phase 3 swing detection uses a `lookback` parameter-based algorithm that differs from the original ATS_2 legacy implementation.

**Legacy Algorithm**: The original `detect_swing_points()` in `predictors_tools.py` uses an **iterative extreme-tracking algorithm** without any lookback parameter - it's purely candle-dependent.

**Required Fix**: Replace current swing detection with vectorized, GPU-ready version of the legacy algorithm to maintain exact ATS_2 compatibility.

## Legacy Algorithm Analysis

### Original Algorithm Logic

**Reference Function**: `detect_swing_points()` in `/source_repos/ATS_2/EnergyTrading/Python/Utilities/predictors_tools.py` (lines 18-83)

The legacy algorithm works as follows:

1. **Initialize**: First candle sets both `swing_high` and `swing_low` to current high/low
2. **Track Extremes**: Maintain `last_max`, `last_min` (and backup `last_max2`, `last_min2`)
3. **New High Logic**:
   - If current high > last high → update max
   - If gap exists (`last_max_idx_diff > 1`) → recalculate opposite swing (find min in between)
4. **New Low Logic**:
   - If current low < last low → update min  
   - If gap exists (`last_min_idx_diff > 1`) → recalculate opposite swing (find max in between)
5. **Forward Propagate**: Each candle gets the current swing high/low values

### Key Characteristics
- **No lookback parameter** - purely data-driven
- **Continuous values** - every candle has swing_high and swing_low values
- **Adaptive ranges** - swing ranges adjust based on actual price action
- **Sequential dependency** - each candle depends on previous state

## Implementation Requirements

### Technical Specifications

**Input**: OHLC candle data (open, high, low, close)
**Output**: 
- `swing_high`: Current swing high price for each candle
- `swing_low`: Current swing low price for each candle

**Algorithm Properties**:
- No parameters needed (purely candle-dependent)
- Produces continuous price values (not boolean masks)
- GPU-vectorized implementation required
- Must integrate with existing Phase 3 pipeline

### Vectorization Challenge

**Sequential Nature**: The legacy algorithm is inherently sequential - each iteration depends on previous state.

**Vectorization Strategy Options**:
1. **Scan Operations**: Use GPU scan/prefix operations to propagate state
2. **Chunked Processing**: Process in parallel chunks with boundary handling
3. **State Machine**: Vectorize state transitions using GPU conditionals

### Integration Requirements

**Pipeline Compatibility**:
- Must work with existing `UnifiedTechnicalIndicatorsPipeline`
- Use `ArrayBackend` for CPU/GPU compatibility
- Output format compatible with Phase 4 feature engineering
- No breaking changes to existing interfaces

**Performance Targets**:
- Maintain GPU acceleration throughout
- <0.1s overhead on Phase 3 pipeline
- Handle millions of candles efficiently

## Implementation Plan

### Phase 3.1 Deliverables

1. **New Swing Detector**: `LegacySwingPointDetector` class
   - Implement vectorized version of `predictors_tools.py` algorithm
   - GPU-accelerated using CuPy operations
   - No lookback parameter dependency

2. **Pipeline Integration**: Modify `UnifiedTechnicalIndicatorsPipeline`
   - Replace current `SwingPointDetector` with `LegacySwingPointDetector`
   - Maintain backward compatibility
   - Update method signatures to remove `swing_lookback` parameter

3. **Comprehensive Testing**:
   - Unit tests comparing against original `predictors_tools.py`
   - Performance benchmarks on GPU
   - Integration tests with Phase 4 pipeline

### Success Criteria

**Correctness**: 
- **Exact match with legacy algorithm**: Must produce identical results to `detect_swing_points()` function in `/source_repos/ATS_2/EnergyTrading/Python/Utilities/predictors_tools.py` (lines 18-83)
- Continuous swing values for every candle
- Proper extreme tracking and recalculation logic

**Performance**:
- GPU acceleration maintained
- No significant overhead added to Phase 3
- Scales to millions of candles

**Compatibility**:
- Seamless integration with Phase 4-6 pipelines
- price_position calculation works correctly
- All existing tests pass

## Next Steps

1. **Algorithm Study**: Detailed analysis of vectorization approach for sequential algorithm
2. **Implementation**: Create `LegacySwingPointDetector` with GPU vectorization
3. **Testing**: Comprehensive validation against legacy implementation
4. **Integration**: Update pipeline and remove lookback dependencies
5. **Validation**: End-to-end testing of complete feature engineering pipeline

## Impact Assessment

**Breaking Changes**: 
- Remove `swing_lookback` parameter from pipeline methods
- Change swing output from boolean masks to continuous price values

**Benefits**:
- Exact ATS_2 legacy compatibility
- More accurate price_position calculations  
- Algorithm matches original design intent
- Eliminates arbitrary lookback parameter selection

**Risks**:
- Vectorization complexity for sequential algorithm
- Potential performance impact if vectorization is inefficient
- Integration testing required across all phases

---

**Priority**: High - Required for exact legacy compatibility
**Timeline**: Immediate implementation needed to fix Phase 3 swing detection
**Dependencies**: Must complete before Phase 4-6 validation