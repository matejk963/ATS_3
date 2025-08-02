# ATR-Based Stop Loss and Take Profit Calculation Context

## Overview
This document provides the necessary context for implementing proper ATR-based stop loss and take profit calculations as a core feature in the unified technical indicators pipeline.

## Implementation Approach

### Pipeline Integration Strategy
Instead of modifying `combo_generator.py`, integrate ATR-based risk management as a **core feature engineering component** in the main pipeline architecture:

1. **Create `ATRRiskCalculator`** - New calculator class in `src/feature_engineering/`
2. **Integrate into `UnifiedTechnicalIndicatorsPipeline`** - Add as standard feature like MACD, ATR, etc.
3. **Add to pipeline computation methods** - Include in `compute_all_indicators_and_features()` 

### Current Implementation Issue in Combo Generator

#### Problem
The current `combo_generator.py` implementation computes ATR values but does not use them to calculate actual stop loss and take profit distances. Instead, it only stores the ratio parameters.

**Current Code (Lines 392, 475, 477):**
```python
# Computes ATR correctly
result['atr'] = price_range.rolling(window=combo['atr_period'], min_periods=1).mean()

# Stores ratio parameters only - NOT actual distances
result['stop_loss'] = combo['stop_loss']  # Just the ratio (0.3-0.8)
result['take_profit'] = combo['stop_loss'] * combo['sl_tp_ratio']  # Just ratios multiplied
```

#### Expected Behavior
The pipeline should compute actual stop loss and take profit distances by multiplying ATR with the input ratios.

## Input Parameters

### Stop Loss Ratios
```python
STOP_LOSS_VALUES = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]  # ATR multipliers
```

### Stop Loss to Take Profit Ratios
```python
STOP_LOSS_TO_TAKE_PROFIT_RATIOS = [1.0, 1.2, 1.5, 1.8, 2.0, 2.2]  # TP = SL * ratio
```

### Parameter Usage in Combinations
Each combination receives:
- `combo['stop_loss']`: One value from STOP_LOSS_VALUES (e.g., 0.5)
- `combo['sl_tp_ratio']`: One value from STOP_LOSS_TO_TAKE_PROFIT_RATIOS (e.g., 1.5)
- `combo['atr_period']`: ATR calculation window (e.g., 21)

## Pipeline Implementation Requirements

### ATRRiskCalculator Class Structure
```python
class ATRRiskCalculator:
    def __init__(self, backend: ArrayBackend):
        """Initialize with ArrayBackend for CPU/GPU compatibility"""
        
    def compute_stop_loss_distance(self, atr: ArrayLike, stop_loss_ratio: float) -> ArrayLike:
        """Calculate stop loss distance = ATR × stop_loss_ratio"""
        
    def compute_take_profit_distance(self, atr: ArrayLike, stop_loss_ratio: float, 
                                   sl_tp_ratio: float) -> ArrayLike:
        """Calculate take profit distance = ATR × stop_loss_ratio × sl_tp_ratio"""
        
    def compute_risk_distances(self, atr: ArrayLike, stop_loss_ratio: float, 
                             sl_tp_ratio: float) -> Tuple[ArrayLike, ArrayLike]:
        """Compute both distances together for efficiency"""
        
    def compute_risk_levels(self, entry_price: ArrayLike, atr: ArrayLike,
                          stop_loss_ratio: float, sl_tp_ratio: float,
                          position_type: str = 'long') -> Tuple[ArrayLike, ArrayLike]:
        """Compute actual price levels for stop loss and take profit"""
```

### Integration into UnifiedTechnicalIndicatorsPipeline
```python
# In _initialize_calculators():
self.atr_risk_calculator = ATRRiskCalculator(self.backend)

# In compute_all_indicators_and_features():
# Add risk management features after ATR calculation
if 'stop_loss_distance' in requested_features:
    result['stop_loss_distance'] = self.atr_risk_calculator.compute_stop_loss_distance(
        result['atr'], config.stop_loss_ratio
    )
    
if 'take_profit_distance' in requested_features:
    result['take_profit_distance'] = self.atr_risk_calculator.compute_take_profit_distance(
        result['atr'], config.stop_loss_ratio, config.sl_tp_ratio
    )
```

### Combo Generator Integration (Secondary)
Once pipeline features are available, combo generator can use them:

```python
# Replace line 475-477 with pipeline feature calls:
result['stop_loss_distance'] = pipeline.compute_feature('stop_loss_distance', 
                                                       config={'stop_loss_ratio': combo['stop_loss']})
result['take_profit_distance'] = pipeline.compute_feature('take_profit_distance',
                                                         config={'stop_loss_ratio': combo['stop_loss'],
                                                                'sl_tp_ratio': combo['sl_tp_ratio']})
```

## Mathematical Formula

### Stop Loss Distance
```
Stop Loss Distance = ATR × Stop Loss Ratio
```
**Example:** ATR = 2.5, Stop Loss Ratio = 0.5 → Stop Loss Distance = 1.25

### Take Profit Distance
```
Take Profit Distance = ATR × Stop Loss Ratio × SL/TP Ratio
```
**Example:** ATR = 2.5, Stop Loss Ratio = 0.5, SL/TP Ratio = 1.5 → Take Profit Distance = 1.875

## Implementation Files and Context

### Primary Implementation Files
```
/mnt/c/Users/krajcovic/Documents/GitHub/ATS_3/src/feature_engineering/atr_risk_calculator.py  # New file
/mnt/c/Users/krajcovic/Documents/GitHub/ATS_3/src/feature_engineering/unified_pipeline.py     # Modify
/mnt/c/Users/krajcovic/Documents/GitHub/ATS_3/tests/test_atr_risk_calculator.py              # New tests
```

### Secondary Integration Files
```
/mnt/c/Users/krajcovic/Documents/GitHub/ATS_3/examples/combo_generator.py                    # Use pipeline features
```

### Pipeline Integration Points
- **UnifiedTechnicalIndicatorsPipeline._initialize_calculators()**: Add ATRRiskCalculator
- **UnifiedTechnicalIndicatorsPipeline.compute_all_indicators_and_features()**: Add risk features
- **PipelineConfig**: Add risk management configuration parameters

## Expected Pipeline Features

After implementation, the pipeline should provide these new features:
- `stop_loss_distance`: Actual stop loss distances in price units (ATR × stop_loss_ratio)
- `take_profit_distance`: Actual take profit distances in price units (ATR × stop_loss_ratio × sl_tp_ratio)
- `stop_loss_level`: Actual stop loss price levels (entry_price ± stop_loss_distance)
- `take_profit_level`: Actual take profit price levels (entry_price ± take_profit_distance)

These features will be available for:
- Direct use in trading strategies
- Integration into combo generator
- Backtesting and analysis
- Risk management calculations

## Validation Requirements

### Data Type Validation
- All distance values should be positive floats
- ATR values should be non-negative
- Distance calculations should handle NaN ATR values gracefully

### Logical Validation
```python
# Take profit should always be >= stop loss (when sl_tp_ratio >= 1.0)
assert (result['take_profit_distance'] >= result['stop_loss_distance']).all()

# Distances should be proportional to ATR
assert (result['stop_loss_distance'] / result['atr'] == combo['stop_loss']).all()
```

## Metadata Impact

### Metadata Records
The metadata should continue to store the input ratios for reference:
```python
metadata_record = {
    # ... existing fields ...
    'stop_loss': combo['stop_loss'],                    # Input ratio (0.3-0.8)
    'sl_tp_ratio': combo['sl_tp_ratio'],               # Input ratio (1.0-2.2)
    'take_profit': combo['stop_loss'] * combo['sl_tp_ratio'],  # Calculated ratio
    # ... existing fields ...
}
```

## Legacy Compatibility

### Legacy Function Comparison
The legacy implementation in `true_legacy_1000_combo_generator.py` also needs similar updates to maintain comparison accuracy between GPU and legacy pipelines.

### Reference Implementation
Check existing ATR usage patterns in:
- `src/feature_engineering/unified_pipeline.py`
- Legacy functions in `predictors_tools.py`

## Risk Management Context

### Trading Logic
- **Stop Loss Distance**: Maximum acceptable loss per trade (in price units)
- **Take Profit Distance**: Target profit per trade (in price units)
- **ATR-Based Sizing**: Ensures risk is proportional to market volatility

### Example Usage
```python
# For a trade entry at price 100.0 with ATR = 2.0, stop_loss = 0.5, sl_tp_ratio = 1.5:
entry_price = 100.0
atr_value = 2.0
stop_loss_distance = 1.0  # 2.0 * 0.5
take_profit_distance = 1.5  # 2.0 * 0.5 * 1.5

# Actual trade levels
stop_loss_price = entry_price - stop_loss_distance  # 99.0 (for long position)
take_profit_price = entry_price + take_profit_distance  # 101.5 (for long position)
```

## Implementation Priority and Strategy
- **Priority**: High - Critical for proper risk management calculations
- **Approach**: Feature engineering pipeline integration (not combo generator modification)
- **Dependencies**: 
  - ATR calculation already implemented in pipeline
  - ArrayBackend for CPU/GPU compatibility
- **Benefits**:
  - Reusable across all trading strategies
  - GPU-accelerated risk calculations
  - Consistent with existing pipeline architecture
  - Testable and maintainable