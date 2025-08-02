# Swing Points Implementation Fix: State-Tracking Algorithm Alignment

**Date**: July 29, 2025  
**Priority**: 🔴 **CRITICAL**  
**Feature**: Swing Points Detection (Highs and Lows)  
**Objective**: Replace rolling window approach with legacy state-tracking algorithm  

---

## 🚨 Critical Issue Confirmed

**Problem**: Current GPU swing points implementation uses rolling window/vectorized approach, but legacy production uses complex state-tracking with dynamic recalculation.

**Impact**: **2.9% match rate for highs, 2.2% match rate for lows** - confirmed algorithmic mismatch through analysis.

**Root Cause**: Phase 2 implementation prioritized GPU optimization over algorithm accuracy.

---

## 📋 Phase 2 Development History

### Original Implementation (January 2025)
**Phase 2 Files**: 
- **Implementation Guide**: `/docs/development/feature_engineering/PHASE_2_IMPLEMENTATION.md`
- **Handoff Document**: `/docs/development/feature_engineering/PHASE_2_HANDOFF.md`
- **Phase 2.1 Enhancement**: `/docs/development/feature_engineering/PHASE_2.1_IMPLEMENTATION.md`
- **Phase 2.2 Legacy Attempt**: `/docs/development/feature_engineering/PHASE_2.2_HANDOFF.md`
- **Current Implementation**: `/src/feature_engineering/swing_point_detector.py`

**Phase 2 Claims** (INCORRECT):
- ✅ "Swing point detection fully vectorized (Phase 2.1) - 13x speedup"
- ✅ "Legacy algorithm validation complete (Phase 2.2) - production compatibility"
- ✅ "Numerical equivalence with both original and production legacy algorithms"

**Phase 2.1 Vectorized Algorithm Used**:
```python
# Rolling window approach for GPU optimization
def _detect_swing_highs_vectorized(self, high: ArrayLike, lookback: int) -> ArrayLike:
    # Create rolling max for each position using centered windows
    rolling_max = rolling_window_max(high, window_size, self.backend, center=True)
    rolling_min = rolling_window_min(high, window_size, self.backend, center=True)
    
    # Vectorized conditions
    is_local_max = (high == rolling_max)
    has_variation = (rolling_max - rolling_min) > 1e-10
    
    # Point-in-time evaluation without state tracking
    return is_local_max & has_variation & boundary_mask
```

**Phase 2.2 Legacy Compatibility Attempt**:
- **File Created**: `/src/feature_engineering/legacy_swing_detector.py`
- **Claim**: "Legacy ATS_2 compatible algorithm"
- **Reality**: Likely compared against wrong legacy function or simplified version

**Why Phase 2 Was Wrong**:
- Used rolling window approach instead of state-tracking
- Point-in-time evaluation instead of dynamic recalculation
- No forward propagation of swing values
- Missing complex slice-based logic for opposite swing recalculation
- Optimized for GPU performance rather than algorithm accuracy

---

## 🎯 Required Legacy Algorithm

**Source**: `/source_repos/EnergyTrading/Python/Utilities/predictors_tools.py`  
**Function**: `detect_swing_points()` (lines 18-83)

### Algorithm Breakdown:

#### Initialization (lines 39-50)
```python
df = ohlc_df.copy().reset_index()
df['min'] = np.nan
df['max'] = np.nan

# First candle initialization
if idx == 0:
    last_min = [idx, l]      # [index, value] of last minimum
    last_min2 = [idx, l]     # Previous minimum for recalculation  
    last_max = [idx, h]      # [index, value] of last maximum
    last_max2 = [idx, h]     # Previous maximum for recalculation
    df.at[idx, 'min'] = l
    df.at[idx, 'max'] = h
```
**Purpose**: Initialize state variables and set first values.

#### State-Tracking Loop (lines 42-79)
```python
for idx, row in df.iterrows():
    o, h, l, c = row['open'], row[high_col], row[low_col], row['close']
    # ... initialization code above ...
    
    last_max_idx_diff = idx - last_max[0]
    last_min_idx_diff = idx - last_min[0]
```
**Purpose**: Track time since last extreme for recalculation logic.

#### New High Detection & Opposite Swing Recalculation (lines 54-66)
```python
if last_max[1] < h:  # New high found
    df.at[idx, 'max'] = h
    if last_max_idx_diff > 1:  # Gap since last high - recalculate swing low
        last_max2 = last_max
        last_max = [idx, h]
        
        # CRITICAL: Recalculate swing low from slice between highs
        slice_low = df.loc[last_max2[0]: last_max[0], low_col]
        new_min = slice_low.min()
        new_min_idx = slice_low.idxmin()
        last_min2 = last_min
        last_min = [new_min_idx, new_min]
        df.at[idx, 'min'] = new_min
    else:
        last_max = [idx, h]  # Update without recalculation
```
**CRITICAL**: When new high found, recalculates swing low from data between previous highs.

#### New Low Detection & Opposite Swing Recalculation (lines 67-79)
```python
if last_min[1] > l:  # New low found
    df.at[idx, 'min'] = l
    if last_min_idx_diff > 1:  # Gap since last low - recalculate swing high
        last_min2 = last_min
        last_min = [idx, l]
        
        # CRITICAL: Recalculate swing high from slice between lows
        slice_high = df.loc[last_min2[0]: last_min[0], high_col]
        new_max = slice_high.max()
        new_max_idx = slice_high.idxmax()
        last_max2 = last_max
        last_max = [new_max_idx, new_max]
        df.at[idx, 'max'] = new_max
    else:
        last_min = [idx, l]  # Update without recalculation
```
**CRITICAL**: When new low found, recalculates swing high from data between previous lows.

#### Result Generation (lines 80-83)
```python
result = pd.DataFrame({'swing_high': df['max'].values,
                       'swing_low':  df['min'].values},
                      index=ohlc_df.index)
return result
```
**Purpose**: Create final result with forward-propagated values.

### Key Characteristics:
- **State-tracking**: Maintains `last_min`, `last_min2`, `last_max`, `last_max2` variables
- **Dynamic recalculation**: When new extreme found, recalculates opposite swing from slice
- **Forward propagation**: Values persist until new extremes detected
- **Complex logic**: Different behavior based on time gaps between extremes
- **Index management**: Careful tracking of positions for slice operations

---

## 🛠️ Implementation Requirements

### Current File to Replace:
**File**: `/src/feature_engineering/swing_point_detector.py`

### New Method Signature:
```python
def detect_swings(self, ohlc_df: pd.DataFrame, high_col: str = 'high', 
                  low_col: str = 'low') -> pd.DataFrame:
    """
    Detect swing points matching predictors_tools.detect_swing_points()
    
    Args:
        ohlc_df: DataFrame with OHLC data, must have columns 'open', 'high', 'low', 'close'
        high_col: Name of the column containing high prices (default: 'high')
        low_col: Name of the column containing low prices (default: 'low')
    
    Returns:
        DataFrame with 'swing_high' and 'swing_low' columns, indexed same as input
        
    Note: This uses state-tracking with dynamic recalculation, NOT rolling windows
    """
```

### Implementation Steps:
1. **State variable initialization**: Set up tracking variables for extremes
2. **Iterative processing**: Loop through each OHLC row (cannot be fully vectorized)
3. **New extreme detection**: Check for new highs/lows against current state
4. **Dynamic recalculation**: When gap exists, recalculate opposite swing from slice
5. **State updates**: Maintain current and previous extreme positions
6. **Forward propagation**: Ensure values persist until new extremes
7. **ArrayBackend compatibility**: Adapt for GPU where possible
8. **Return format** matching legacy exactly

### 🚀 **CRITICAL**: GPU Usability & Vectorization Requirements

**Reference**: Phase 2 vectorization achievements documented in:
- **Phase 2.1 Implementation**: `/docs/development/feature_engineering/PHASE_2.1_IMPLEMENTATION.md` - "Swing point detection fully vectorized - 13x speedup"
- **Phase 2 Handoff**: `/docs/development/feature_engineering/PHASE_2_HANDOFF.md` - "All components optimized for ArrayBackend compatibility"

**GPU Optimization Strategy** (Hybrid Approach):
1. **Preserve ArrayBackend Integration**: Use `self.backend` for array operations where possible
2. **Vectorize Slice Operations**: Use GPU-accelerated `.min()/.max()/.idxmin()/.idxmax()` for recalculation
3. **Batch Array Updates**: Vectorize forward-propagation of swing values
4. **Memory-Efficient State**: Use GPU arrays for swing value storage (`self.backend.full()`)
5. **Hybrid CPU/GPU**: State-tracking on CPU, mathematical operations on GPU
6. **Chunked Processing**: Process large datasets in GPU-memory-sized chunks

**Performance Targets** (realistic expectations):
- **GPU Acceleration**: >5x speedup vs pure CPU (limited by sequential nature)
- **Memory Efficiency**: Handle >100k candle datasets without memory overflow
- **Selective Vectorization**: GPU operations for slice calculations, CPU for state logic
- **ArrayBackend Compatibility**: Seamless switching between CPU/GPU backends

**Note**: Unlike MACD/ATR, swing points cannot achieve full vectorization due to state-tracking requirements, but GPU acceleration is still possible for mathematical operations.

### Core Implementation Logic:
```python
def detect_swings(self, ohlc_df: pd.DataFrame, high_col: str = 'high', 
                  low_col: str = 'low') -> pd.DataFrame:
    """State-tracking swing detection"""
    df = ohlc_df.copy().reset_index()
    df['min'] = self.backend.full(len(df), np.nan)
    df['max'] = self.backend.full(len(df), np.nan)
    
    # State variables
    last_min = None
    last_min2 = None  
    last_max = None
    last_max2 = None
    
    for idx in range(len(df)):
        row = df.iloc[idx]
        h, l = row[high_col], row[low_col]
        
        if idx == 0:
            # Initialize state
            last_min = [idx, l]
            last_min2 = [idx, l]
            last_max = [idx, h]
            last_max2 = [idx, h]
            df.at[idx, 'min'] = l
            df.at[idx, 'max'] = h
            continue
            
        # Check for new high
        if last_max[1] < h:
            self._handle_new_high(df, idx, h, last_max, last_max2, last_min, last_min2, low_col)
            
        # Check for new low  
        if last_min[1] > l:
            self._handle_new_low(df, idx, l, last_min, last_min2, last_max, last_max2, high_col)
    
    # Create result DataFrame
    result = pd.DataFrame({
        'swing_high': df['max'].values,
        'swing_low': df['min'].values
    }, index=ohlc_df.index)
    
    return result
```

### Helper Functions Required:
```python
def _handle_new_high(self, df, idx, h, last_max, last_max2, last_min, last_min2, low_col):
    """Handle new high detection and opposite swing recalculation"""
    
def _handle_new_low(self, df, idx, l, last_min, last_min2, last_max, last_max2, high_col):
    """Handle new low detection and opposite swing recalculation"""
    
def _recalculate_swing_from_slice(self, df, start_idx, end_idx, col, operation):
    """Recalculate swing value from data slice"""
```

---

## 🧪 Testing & Validation

### Test Implementation:
**Create**: `/examples/swing_comparison_test.py`

**Expected Results Before Fix**:
- **Swing Highs**: ~2.9% match rate (from analysis report)
- **Swing Lows**: ~2.2% match rate (from analysis report)
- **Pattern**: GPU shows dynamic values, legacy shows forward-filled patterns

**Test Methodology**:
1. Load identical test data used in legacy comparison
2. Run current GPU rolling window implementation
3. Run legacy `detect_swing_points()` function  
4. Compare results with detailed pattern analysis
5. **Expected Result**: Confirm low match rates and different patterns

**Test Data**:
- **Source**: `/Testing Data/backtest_data/dem07_25_tr_ba_data.parquet`
- **Parameters**: Default swing detection (no lookback parameter in legacy)
- **Format**: OHLC candles → swing high/low detection

### Success Criteria:
- **Match Rate**: >95% with legacy `detect_swing_points()` (from ~3%)
- **Pattern Match**: Forward-filled behavior matching legacy exactly
- **Performance**: GPU acceleration where possible (>5x speedup vs pure CPU, limited by sequential algorithm)
- **Vectorization**: GPU operations for slice calculations, hybrid CPU/GPU approach
- **Memory Efficiency**: Handle >100k candle datasets without GPU memory overflow
- **Output Format**: Exact column structure matching legacy
- **Edge Cases**: Handle first candle, consecutive extremes correctly

---

## 📚 Reference Materials

### Legacy Algorithm:
- **Primary**: `/source_repos/EnergyTrading/Python/Utilities/predictors_tools.py:18-83`
- **Alternative Version**: Same file, lines 197-236 (commented out version for reference)

### Current Implementation:
- **Phase 2 Implementation**: `/src/feature_engineering/swing_point_detector.py`
- **Phase 2.1 Vectorization**: `/src/feature_engineering/rolling_ops.py`
- **Phase 2.2 Legacy Attempt**: `/src/feature_engineering/legacy_swing_detector.py`
- **Phase 2 Documentation**: `/docs/development/feature_engineering/PHASE_2_IMPLEMENTATION.md`
- **Phase 2.1 Handoff**: `/docs/development/feature_engineering/PHASE_2.1_IMPLEMENTATION.md`
- **Phase 2.2 Handoff**: `/docs/development/feature_engineering/PHASE_2.2_HANDOFF.md`

### Analysis Results:
- **Analysis Report**: `/analysis/reports/LEGACY_VS_GPU_COMPARISON_ANALYSIS.md`
- **Pattern Analysis**: GPU shows dynamic values vs legacy forward-filled patterns

### Supporting Infrastructure:
- **ArrayBackend**: `/src/feature_engineering/array_backend.py`
- **Pipeline Integration**: `/src/feature_engineering/unified_pipeline.py`

---

## ⚠️ Critical Implementation Notes

### Algorithm Complexity:
- **Not GPU-Friendly**: State-tracking with dynamic recalculation cannot be fully vectorized
- **Sequential Processing**: Must process candles in order, limits parallelization
- **Complex State Management**: Four state variables with interdependent updates
- **Index Management**: Careful slice operations require precise indexing
- **GPU Optimization Limited**: May need hybrid CPU/GPU approach

### Backward Compatibility:
- **Pipeline Integration**: Ensure unified_pipeline.py continues to work
- **Method Signature**: Should remain compatible (same input/output format)
- **Performance Impact**: Document performance reduction from sequential processing

### Implementation Challenges:
- **ArrayBackend Adaptation**: State-tracking may not benefit from GPU acceleration
- **Memory Management**: Large datasets may require chunked processing
- **Edge Cases**: First candle, single candle, consecutive extremes
- **Index Alignment**: Maintain proper DataFrame indexing throughout

### Documentation Updates:
- **Correct Phase 2 Claims**: Update all Phase 2 documentation to reflect incorrect implementations
- **Phase 2.1 Claims**: "13x speedup" achieved with wrong algorithm
- **Phase 2.2 Claims**: "Legacy compatibility" was incorrect
- **Architecture Update**: Document sequential processing limitations

---

## 🎯 Success Metrics

**Implementation Complete When**:
- [ ] New implementation achieves >95% match rate with legacy (from ~3%)
- [ ] Forward-filled pattern behavior matches legacy exactly
- [ ] All edge cases handled (first candle, consecutive extremes)
- [ ] Performance impact documented and minimized where possible
- [ ] Pipeline integration maintains backward compatibility
- [ ] Comprehensive test suite passes with new algorithm
- [ ] Documentation updated to correct all Phase 2 inaccuracies

**Deliverables**:
- Updated `/src/feature_engineering/swing_point_detector.py` with state-tracking algorithm
- New test file `/examples/swing_comparison_test.py` with validation
- Updated unified pipeline integration
- Corrected documentation for Phase 2, 2.1, and 2.2

---

**Performance Expectation**: This implementation will likely be slower than the Phase 2.1 vectorized version due to sequential processing requirements, but will be algorithmically correct.

---

*This fix addresses the swing points algorithmic mismatch with ~3% match rates. The state-tracking with dynamic recalculation is fundamentally different from rolling window approaches and cannot be fully vectorized while maintaining algorithm accuracy.*