# Phase 1.1.2: Parameter Combination Logic

## Overview
**Dependencies**: Phase 1.1.1 completed  
**Track**: Parameter Logic (Track A)

This micro-phase implements the core combination generation logic for bias and strategy thresholds, building upon the helper functions from Phase 1.1.1.

## Objectives
1. Implement bias threshold combination generation
2. Implement strategy threshold combination generation
3. Add combination count estimation function
4. Write comprehensive tests for combination generators

## Implementation Steps

### Step 1: Extend Parameter Combinations File

Add to `src/gpu_parallel_processing/parameter_combinations.py`:

```python
# Add these imports at the top
import itertools

# Add after existing constants section

# ============================================================================
# THRESHOLD CONFIGURATION GENERATORS
# ============================================================================

# Bias classifier thresholds using symmetric pairs
BIAS_THRESHOLD_RANGES = {
    'macd_line_pairs': generate_symmetric_pairs(2.5, 0.5),        # 5 pairs: (-2.5,2.5) to (-0.5,0.5)
    'macd_histogram_pairs': generate_symmetric_pairs(1.25, 0.25)  # 5 pairs: (-1.25,1.25) to (-0.25,0.25)
}

# Strategy thresholds - neutral values + bias adjustments
NEUTRAL_STRATEGY_RANGES = {
    'buy_values': frange(0.2, 0.4, 0.1),    # [0.2, 0.3]
    'sell_values': frange(0.7, 0.9, 0.1)    # [0.7, 0.8]
}

BIAS_ADJUSTMENT_RANGES = {
    'buy_adjustment_bullish': [0.0],                                # No adjustment for bullish
    'buy_adjustment_strong_bullish': frange(0.05, 0.15, 0.05),     # [0.05, 0.1]
    'buy_adjustment_bearish': frange(-0.10, -0.04, 0.05),          # [-0.1, -0.05]
    'sell_adjustment_bearish': [0.0],                               # No adjustment for bearish
    'sell_adjustment_strong_bearish': frange(-0.10, -0.04, 0.05),  # [-0.1, -0.05]
    'sell_adjustment_bullish': frange(0.05, 0.16, 0.05),           # [0.05, 0.1, 0.15]
}


def generate_bias_threshold_combinations() -> List[Dict]:
    """
    Generate all bias threshold combinations from MACD line and histogram pairs.
    
    Creates Cartesian product of MACD line thresholds and histogram thresholds.
    Each combination defines the boundaries for bias classification.
    
    Returns:
        List of bias threshold dictionaries with keys:
        - macd_line_lower: Lower bound for MACD line (negative)
        - macd_line_upper: Upper bound for MACD line (positive)
        - macd_histogram_lower: Lower bound for MACD histogram (negative)
        - macd_histogram_upper: Upper bound for MACD histogram (positive)
        
    Example:
        >>> combinations = generate_bias_threshold_combinations()
        >>> len(combinations)  # 5 * 5 = 25 combinations
        25
        >>> combinations[0]
        {
            'macd_line_lower': -2.5,
            'macd_line_upper': 2.5,
            'macd_histogram_lower': -1.25,
            'macd_histogram_upper': 1.25
        }
    """
    bias_combinations = []
    
    for macd_line_pair, macd_hist_pair in itertools.product(
        BIAS_THRESHOLD_RANGES['macd_line_pairs'],
        BIAS_THRESHOLD_RANGES['macd_histogram_pairs']
    ):
        bias_combination = {
            'macd_line_lower': macd_line_pair[0],       # Negative value
            'macd_line_upper': macd_line_pair[1],       # Positive value
            'macd_histogram_lower': macd_hist_pair[0],  # Negative value
            'macd_histogram_upper': macd_hist_pair[1]   # Positive value
        }
        bias_combinations.append(bias_combination)
    
    return bias_combinations


def generate_strategy_threshold_combinations() -> List[Dict]:
    """
    Generate all strategy threshold combinations from neutral values and bias adjustments.
    
    Creates Cartesian product of:
    - Neutral buy/sell thresholds
    - Bias adjustments for different market conditions
    
    Strategy thresholds define when to generate buy/sell signals based on bias classification.
    
    Returns:
        List of strategy threshold dictionaries with keys:
        - neutral_buy: Base buy threshold for neutral bias
        - neutral_sell: Base sell threshold for neutral bias  
        - bullish_buy_adjust: Adjustment for bullish bias buy signals
        - strong_bullish_buy_adjust: Adjustment for strong bullish bias
        - bearish_buy_adjust: Adjustment for bearish bias buy signals
        - bearish_sell_adjust: Adjustment for bearish bias sell signals
        - strong_bearish_sell_adjust: Adjustment for strong bearish bias
        - bullish_sell_adjust: Adjustment for bullish bias sell signals
        
    Example:
        >>> combinations = generate_strategy_threshold_combinations()
        >>> len(combinations)  # 2 * 2 * 1 * 2 * 2 * 1 * 2 * 3 = 96 combinations
        96
        >>> combinations[0]
        {
            'neutral_buy': 0.2,
            'neutral_sell': 0.7,
            'bullish_buy_adjust': 0.0,
            'strong_bullish_buy_adjust': 0.05,
            'bearish_buy_adjust': -0.1,
            'bearish_sell_adjust': 0.0,
            'strong_bearish_sell_adjust': -0.1,
            'bullish_sell_adjust': 0.05
        }
    """
    strategy_combinations = []
    
    # Generate Cartesian product of all strategy parameters
    for (neutral_buy, neutral_sell, buy_adj_bullish, buy_adj_strong_bullish, 
         buy_adj_bearish, sell_adj_bearish, sell_adj_strong_bearish, 
         sell_adj_bullish) in itertools.product(
        NEUTRAL_STRATEGY_RANGES['buy_values'],
        NEUTRAL_STRATEGY_RANGES['sell_values'],
        BIAS_ADJUSTMENT_RANGES['buy_adjustment_bullish'],
        BIAS_ADJUSTMENT_RANGES['buy_adjustment_strong_bullish'],
        BIAS_ADJUSTMENT_RANGES['buy_adjustment_bearish'],
        BIAS_ADJUSTMENT_RANGES['sell_adjustment_bearish'],
        BIAS_ADJUSTMENT_RANGES['sell_adjustment_strong_bearish'],
        BIAS_ADJUSTMENT_RANGES['sell_adjustment_bullish']
    ):
        strategy_combination = {
            'neutral_buy': neutral_buy,
            'neutral_sell': neutral_sell,
            'bullish_buy_adjust': buy_adj_bullish,
            'strong_bullish_buy_adjust': buy_adj_strong_bullish,
            'bearish_buy_adjust': buy_adj_bearish,
            'bearish_sell_adjust': sell_adj_bearish,
            'strong_bearish_sell_adjust': sell_adj_strong_bearish,
            'bullish_sell_adjust': sell_adj_bullish
        }
        strategy_combinations.append(strategy_combination)
    
    return strategy_combinations


def validate_bias_thresholds(bias_combo: Dict) -> bool:
    """
    Validate bias threshold combination for logical consistency.
    
    Args:
        bias_combo: Bias threshold combination dictionary
        
    Returns:
        True if valid, False otherwise
        
    Validation Rules:
    - Lower bounds must be negative
    - Upper bounds must be positive  
    - Upper bounds must be greater than corresponding lower bounds
    - MACD line thresholds should be larger than histogram thresholds
    """
    try:
        macd_lower = bias_combo['macd_line_lower']
        macd_upper = bias_combo['macd_line_upper']
        hist_lower = bias_combo['macd_histogram_lower']
        hist_upper = bias_combo['macd_histogram_upper']
        
        # Check sign constraints
        if macd_lower >= 0 or hist_lower >= 0:
            return False
        if macd_upper <= 0 or hist_upper <= 0:
            return False
            
        # Check ordering constraints
        if macd_lower >= macd_upper or hist_lower >= hist_upper:
            return False
            
        # Check magnitude relationships (MACD line should have larger thresholds)
        if abs(macd_lower) < abs(hist_lower) or abs(macd_upper) < abs(hist_upper):
            return False
            
        return True
        
    except (KeyError, TypeError):
        return False


def validate_strategy_thresholds(strategy_combo: Dict) -> bool:
    """
    Validate strategy threshold combination for logical consistency.
    
    Args:
        strategy_combo: Strategy threshold combination dictionary
        
    Returns:
        True if valid, False otherwise
        
    Validation Rules:
    - Neutral buy must be less than neutral sell
    - All threshold values must be between 0 and 1
    - Bullish adjustments should generally be positive or zero
    - Bearish adjustments should generally be negative or zero
    """
    try:
        neutral_buy = strategy_combo['neutral_buy']
        neutral_sell = strategy_combo['neutral_sell']
        
        # Basic range checks
        if not (0 <= neutral_buy <= 1 and 0 <= neutral_sell <= 1):
            return False
            
        # Buy must be less than sell
        if neutral_buy >= neutral_sell:
            return False
            
        # Check adjustment ranges (all should be reasonable adjustments)
        adjustments = [
            strategy_combo['bullish_buy_adjust'],
            strategy_combo['strong_bullish_buy_adjust'],
            strategy_combo['bearish_buy_adjust'],
            strategy_combo['bearish_sell_adjust'],
            strategy_combo['strong_bearish_sell_adjust'],
            strategy_combo['bullish_sell_adjust']
        ]
        
        # All adjustments should be reasonable (between -0.5 and +0.5)
        if not all(-0.5 <= adj <= 0.5 for adj in adjustments):
            return False
            
        return True
        
    except (KeyError, TypeError):
        return False


def get_combination_counts() -> Dict[str, int]:
    """
    Calculate combination counts for each component without generating them.
    
    Returns:
        Dictionary with counts for each combination type
    """
    # Calculate bias threshold combinations
    bias_count = (len(BIAS_THRESHOLD_RANGES['macd_line_pairs']) * 
                  len(BIAS_THRESHOLD_RANGES['macd_histogram_pairs']))
    
    # Calculate strategy threshold combinations
    strategy_count = (len(NEUTRAL_STRATEGY_RANGES['buy_values']) *
                     len(NEUTRAL_STRATEGY_RANGES['sell_values']) *
                     len(BIAS_ADJUSTMENT_RANGES['buy_adjustment_bullish']) *
                     len(BIAS_ADJUSTMENT_RANGES['buy_adjustment_strong_bullish']) *
                     len(BIAS_ADJUSTMENT_RANGES['buy_adjustment_bearish']) *
                     len(BIAS_ADJUSTMENT_RANGES['sell_adjustment_bearish']) *
                     len(BIAS_ADJUSTMENT_RANGES['sell_adjustment_strong_bearish']) *
                     len(BIAS_ADJUSTMENT_RANGES['sell_adjustment_bullish']))
    
    # Calculate total parameter combinations (partial - missing full cartesian product)
    base_combinations = (len(CONTRACTS) *
                        len(PREDICTOR_GRANULARITIES['atr_macd_granularities']) *
                        len(PREDICTOR_GRANULARITIES['swing_granularities']) *
                        len(MACD_CONFIGS) *
                        len(ATR_LOOKBACKS) *
                        len(STOP_LOSS_RANGES) *
                        len(SL_TP_RATIOS))
    
    total_combinations = base_combinations * bias_count * strategy_count
    
    return {
        'bias_combinations': bias_count,
        'strategy_combinations': strategy_count,
        'base_parameter_combinations': base_combinations,
        'total_combinations_estimate': total_combinations,
        'contracts': len(CONTRACTS),
        'granularity_combinations': len(PREDICTOR_GRANULARITIES['atr_macd_granularities']) * len(PREDICTOR_GRANULARITIES['swing_granularities']),
        'macd_configs': len(MACD_CONFIGS),
        'atr_lookbacks': len(ATR_LOOKBACKS),
        'stop_loss_configs': len(STOP_LOSS_RANGES) * len(SL_TP_RATIOS)
    }


if __name__ == "__main__":
    # Quick test of combination logic
    print("Testing combination generation...")
    
    bias_combos = generate_bias_threshold_combinations()
    strategy_combos = generate_strategy_threshold_combinations()
    counts = get_combination_counts()
    
    print(f"Generated {len(bias_combos)} bias combinations")
    print(f"Generated {len(strategy_combos)} strategy combinations")
    print(f"Combination counts: {counts}")
    
    # Validate first few combinations
    valid_bias = sum(1 for combo in bias_combos[:5] if validate_bias_thresholds(combo))
    valid_strategy = sum(1 for combo in strategy_combos[:5] if validate_strategy_thresholds(combo))
    
    print(f"✅ Bias validation: {valid_bias}/5 valid")
    print(f"✅ Strategy validation: {valid_strategy}/5 valid")
    print("✅ Parameter combination logic ready!")
```

### Step 2: Create Test File (`tests/test_parameter_combination_logic.py`)

```python
"""
Unit tests for parameter combination logic (Phase 1.1.2).

Tests bias and strategy threshold combination generation.
"""

import pytest
from src.gpu_parallel_processing.parameter_combinations import (
    generate_bias_threshold_combinations,
    generate_strategy_threshold_combinations,
    validate_bias_thresholds,
    validate_strategy_thresholds,
    get_combination_counts,
    BIAS_THRESHOLD_RANGES,
    NEUTRAL_STRATEGY_RANGES,
    BIAS_ADJUSTMENT_RANGES
)


class TestBiasThresholdCombinations:
    """Test bias threshold combination generation."""
    
    def test_generate_bias_combinations(self):
        """Test basic bias combination generation."""
        combinations = generate_bias_threshold_combinations()
        
        # Should have 5 * 5 = 25 combinations
        expected_count = (len(BIAS_THRESHOLD_RANGES['macd_line_pairs']) * 
                         len(BIAS_THRESHOLD_RANGES['macd_histogram_pairs']))
        assert len(combinations) == expected_count
        
        # Check structure of first combination
        combo = combinations[0]
        required_keys = [
            'macd_line_lower', 'macd_line_upper',
            'macd_histogram_lower', 'macd_histogram_upper'
        ]
        for key in required_keys:
            assert key in combo
            assert isinstance(combo[key], float)
    
    def test_bias_combination_values(self):
        """Test that bias combinations have correct value relationships."""
        combinations = generate_bias_threshold_combinations()
        
        for combo in combinations:
            # Lower bounds should be negative
            assert combo['macd_line_lower'] < 0
            assert combo['macd_histogram_lower'] < 0
            
            # Upper bounds should be positive
            assert combo['macd_line_upper'] > 0
            assert combo['macd_histogram_upper'] > 0
            
            # Symmetric pairs
            assert combo['macd_line_lower'] == -combo['macd_line_upper']
            assert combo['macd_histogram_lower'] == -combo['macd_histogram_upper']
    
    def test_bias_combination_uniqueness(self):
        """Test that all bias combinations are unique."""
        combinations = generate_bias_threshold_combinations()
        
        # Convert to tuples for set comparison
        combo_tuples = [
            (combo['macd_line_lower'], combo['macd_line_upper'],
             combo['macd_histogram_lower'], combo['macd_histogram_upper'])
            for combo in combinations
        ]
        
        # All should be unique
        assert len(combo_tuples) == len(set(combo_tuples))


class TestStrategyThresholdCombinations:
    """Test strategy threshold combination generation."""
    
    def test_generate_strategy_combinations(self):
        """Test basic strategy combination generation."""
        combinations = generate_strategy_threshold_combinations()
        
        # Calculate expected count
        expected_count = (len(NEUTRAL_STRATEGY_RANGES['buy_values']) *
                         len(NEUTRAL_STRATEGY_RANGES['sell_values']) *
                         len(BIAS_ADJUSTMENT_RANGES['buy_adjustment_bullish']) *
                         len(BIAS_ADJUSTMENT_RANGES['buy_adjustment_strong_bullish']) *
                         len(BIAS_ADJUSTMENT_RANGES['buy_adjustment_bearish']) *
                         len(BIAS_ADJUSTMENT_RANGES['sell_adjustment_bearish']) *
                         len(BIAS_ADJUSTMENT_RANGES['sell_adjustment_strong_bearish']) *
                         len(BIAS_ADJUSTMENT_RANGES['sell_adjustment_bullish']))
        
        assert len(combinations) == expected_count
        
        # Check structure of first combination
        combo = combinations[0]
        required_keys = [
            'neutral_buy', 'neutral_sell',
            'bullish_buy_adjust', 'strong_bullish_buy_adjust', 'bearish_buy_adjust',
            'bearish_sell_adjust', 'strong_bearish_sell_adjust', 'bullish_sell_adjust'
        ]
        for key in required_keys:
            assert key in combo
            assert isinstance(combo[key], float)
    
    def test_strategy_combination_ranges(self):
        """Test that strategy combinations have values in expected ranges."""
        combinations = generate_strategy_threshold_combinations()
        
        for combo in combinations:
            # Neutral values should be in expected ranges
            assert combo['neutral_buy'] in NEUTRAL_STRATEGY_RANGES['buy_values']
            assert combo['neutral_sell'] in NEUTRAL_STRATEGY_RANGES['sell_values']
            
            # Buy should be less than sell
            assert combo['neutral_buy'] < combo['neutral_sell']
            
            # Adjustments should be in expected ranges
            assert combo['bullish_buy_adjust'] in BIAS_ADJUSTMENT_RANGES['buy_adjustment_bullish']
            assert combo['strong_bullish_buy_adjust'] in BIAS_ADJUSTMENT_RANGES['buy_adjustment_strong_bullish']
            assert combo['bearish_buy_adjust'] in BIAS_ADJUSTMENT_RANGES['buy_adjustment_bearish']
            assert combo['bearish_sell_adjust'] in BIAS_ADJUSTMENT_RANGES['sell_adjustment_bearish']
            assert combo['strong_bearish_sell_adjust'] in BIAS_ADJUSTMENT_RANGES['sell_adjustment_strong_bearish']
            assert combo['bullish_sell_adjust'] in BIAS_ADJUSTMENT_RANGES['sell_adjustment_bullish']
    
    def test_strategy_combination_uniqueness(self):
        """Test that all strategy combinations are unique."""
        combinations = generate_strategy_threshold_combinations()
        
        # Convert to tuples for set comparison
        combo_tuples = [
            (combo['neutral_buy'], combo['neutral_sell'],
             combo['bullish_buy_adjust'], combo['strong_bullish_buy_adjust'],
             combo['bearish_buy_adjust'], combo['bearish_sell_adjust'],
             combo['strong_bearish_sell_adjust'], combo['bullish_sell_adjust'])
            for combo in combinations
        ]
        
        # All should be unique
        assert len(combo_tuples) == len(set(combo_tuples))


class TestBiasThresholdValidation:
    """Test bias threshold validation function."""
    
    def test_valid_bias_thresholds(self):
        """Test validation of valid bias thresholds."""
        valid_combo = {
            'macd_line_lower': -2.0,
            'macd_line_upper': 2.0,
            'macd_histogram_lower': -1.0,
            'macd_histogram_upper': 1.0
        }
        assert validate_bias_thresholds(valid_combo) == True
    
    def test_invalid_bias_thresholds_wrong_signs(self):
        """Test validation rejects wrong signs."""
        # Positive lower bound
        invalid_combo1 = {
            'macd_line_lower': 2.0,
            'macd_line_upper': 2.0,
            'macd_histogram_lower': -1.0,
            'macd_histogram_upper': 1.0
        }
        assert validate_bias_thresholds(invalid_combo1) == False
        
        # Negative upper bound
        invalid_combo2 = {
            'macd_line_lower': -2.0,
            'macd_line_upper': -2.0,
            'macd_histogram_lower': -1.0,
            'macd_histogram_upper': 1.0
        }
        assert validate_bias_thresholds(invalid_combo2) == False
    
    def test_invalid_bias_thresholds_wrong_ordering(self):
        """Test validation rejects wrong ordering."""
        invalid_combo = {
            'macd_line_lower': -1.0,
            'macd_line_upper': 2.0,
            'macd_histogram_lower': -2.0,  # Histogram should be smaller magnitude
            'macd_histogram_upper': 2.0
        }
        assert validate_bias_thresholds(invalid_combo) == False
    
    def test_invalid_bias_thresholds_missing_keys(self):
        """Test validation rejects missing keys."""
        invalid_combo = {
            'macd_line_lower': -2.0,
            'macd_line_upper': 2.0
            # Missing histogram keys
        }
        assert validate_bias_thresholds(invalid_combo) == False


class TestStrategyThresholdValidation:
    """Test strategy threshold validation function."""
    
    def test_valid_strategy_thresholds(self):
        """Test validation of valid strategy thresholds."""
        valid_combo = {
            'neutral_buy': 0.3,
            'neutral_sell': 0.7,
            'bullish_buy_adjust': 0.0,
            'strong_bullish_buy_adjust': 0.1,
            'bearish_buy_adjust': -0.05,
            'bearish_sell_adjust': 0.0,
            'strong_bearish_sell_adjust': -0.1,
            'bullish_sell_adjust': 0.15
        }
        assert validate_strategy_thresholds(valid_combo) == True
    
    def test_invalid_strategy_thresholds_wrong_ordering(self):
        """Test validation rejects buy >= sell."""
        invalid_combo = {
            'neutral_buy': 0.8,  # Buy higher than sell
            'neutral_sell': 0.7,
            'bullish_buy_adjust': 0.0,
            'strong_bullish_buy_adjust': 0.1,
            'bearish_buy_adjust': -0.05,
            'bearish_sell_adjust': 0.0,
            'strong_bearish_sell_adjust': -0.1,
            'bullish_sell_adjust': 0.15
        }
        assert validate_strategy_thresholds(invalid_combo) == False
    
    def test_invalid_strategy_thresholds_out_of_range(self):
        """Test validation rejects values outside [0,1]."""
        invalid_combo = {
            'neutral_buy': -0.1,  # Negative value
            'neutral_sell': 0.7,
            'bullish_buy_adjust': 0.0,
            'strong_bullish_buy_adjust': 0.1,
            'bearish_buy_adjust': -0.05,
            'bearish_sell_adjust': 0.0,
            'strong_bearish_sell_adjust': -0.1,
            'bullish_sell_adjust': 0.15
        }
        assert validate_strategy_thresholds(invalid_combo) == False
    
    def test_invalid_strategy_thresholds_extreme_adjustments(self):
        """Test validation rejects extreme adjustments."""
        invalid_combo = {
            'neutral_buy': 0.3,
            'neutral_sell': 0.7,
            'bullish_buy_adjust': 0.0,
            'strong_bullish_buy_adjust': 0.8,  # Too large adjustment
            'bearish_buy_adjust': -0.05,
            'bearish_sell_adjust': 0.0,
            'strong_bearish_sell_adjust': -0.1,
            'bullish_sell_adjust': 0.15
        }
        assert validate_strategy_thresholds(invalid_combo) == False


class TestCombinationCounts:
    """Test combination count calculation."""
    
    def test_combination_counts_structure(self):
        """Test that combination counts return correct structure."""
        counts = get_combination_counts()
        
        required_keys = [
            'bias_combinations', 'strategy_combinations', 'base_parameter_combinations',
            'total_combinations_estimate', 'contracts', 'granularity_combinations',
            'macd_configs', 'atr_lookbacks', 'stop_loss_configs'
        ]
        
        for key in required_keys:
            assert key in counts
            assert isinstance(counts[key], int)
            assert counts[key] > 0
    
    def test_combination_counts_accuracy(self):
        """Test that combination counts match actual generation."""
        counts = get_combination_counts()
        
        # Generate actual combinations and compare counts
        bias_combos = generate_bias_threshold_combinations()
        strategy_combos = generate_strategy_threshold_combinations()
        
        assert counts['bias_combinations'] == len(bias_combos)
        assert counts['strategy_combinations'] == len(strategy_combos)
    
    def test_total_combination_estimate(self):
        """Test that total combination estimate is reasonable."""
        counts = get_combination_counts()
        
        # Should be product of all individual counts
        expected_total = (counts['base_parameter_combinations'] * 
                         counts['bias_combinations'] * 
                         counts['strategy_combinations'])
        
        assert counts['total_combinations_estimate'] == expected_total
        
        # Should be a large number (hundreds of thousands)
        assert counts['total_combinations_estimate'] > 50000


class TestIntegration:
    """Integration tests for combination logic."""
    
    def test_generated_combinations_are_valid(self):
        """Test that generated combinations pass validation."""
        bias_combos = generate_bias_threshold_combinations()
        strategy_combos = generate_strategy_threshold_combinations()
        
        # All bias combinations should be valid
        valid_bias_count = sum(1 for combo in bias_combos if validate_bias_thresholds(combo))
        assert valid_bias_count == len(bias_combos)
        
        # All strategy combinations should be valid  
        valid_strategy_count = sum(1 for combo in strategy_combos if validate_strategy_thresholds(combo))
        assert valid_strategy_count == len(strategy_combos)
    
    def test_combination_determinism(self):
        """Test that combination generation is deterministic."""
        # Generate combinations twice
        bias_combos1 = generate_bias_threshold_combinations()
        bias_combos2 = generate_bias_threshold_combinations()
        
        strategy_combos1 = generate_strategy_threshold_combinations()
        strategy_combos2 = generate_strategy_threshold_combinations()
        
        # Should be identical
        assert bias_combos1 == bias_combos2
        assert strategy_combos1 == strategy_combos2
    
    def test_combination_coverage(self):
        """Test that combinations cover expected parameter space."""
        bias_combos = generate_bias_threshold_combinations()
        strategy_combos = generate_strategy_threshold_combinations()
        
        # Extract unique values for each parameter
        unique_macd_line_lowers = set(combo['macd_line_lower'] for combo in bias_combos)
        unique_neutral_buys = set(combo['neutral_buy'] for combo in strategy_combos)
        
        # Should cover all values from parameter ranges
        expected_macd_lowers = set(pair[0] for pair in BIAS_THRESHOLD_RANGES['macd_line_pairs'])
        expected_neutral_buys = set(NEUTRAL_STRATEGY_RANGES['buy_values'])
        
        assert unique_macd_line_lowers == expected_macd_lowers
        assert unique_neutral_buys == expected_neutral_buys


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

### Step 3: Create Validation Script (`validate_phase_1_1_2.py`)

```python
"""
Validation script for Phase 1.1.2 completion.

Run this script to verify that Phase 1.1.2 is properly implemented.
"""

import sys
from pathlib import Path

def validate_phase_1_1_2():
    """Validate Phase 1.1.2 implementation."""
    print("🔍 Validating Phase 1.1.2: Parameter Combination Logic...")
    
    success = True
    
    # Check dependencies (Phase 1.1.1)
    try:
        from src.gpu_parallel_processing.parameter_combinations import (
            generate_symmetric_pairs, frange, get_basic_parameter_info
        )
        print("✅ Phase 1.1.1 dependencies available")
    except ImportError as e:
        print(f"❌ Phase 1.1.1 dependency missing: {e}")
        success = False
    
    # Check new imports
    try:
        from src.gpu_parallel_processing.parameter_combinations import (
            generate_bias_threshold_combinations,
            generate_strategy_threshold_combinations,
            validate_bias_thresholds,
            validate_strategy_thresholds,
            get_combination_counts
        )
        print("✅ Phase 1.1.2 functions available")
    except ImportError as e:
        print(f"❌ Phase 1.1.2 import error: {e}")
        success = False
    
    # Test combination generation
    try:
        bias_combos = generate_bias_threshold_combinations()
        strategy_combos = generate_strategy_threshold_combinations()
        counts = get_combination_counts()
        
        print(f"✅ Generated {len(bias_combos)} bias combinations")
        print(f"✅ Generated {len(strategy_combos)} strategy combinations") 
        print(f"✅ Estimated {counts['total_combinations_estimate']:,} total combinations")
        
        # Check combination counts match expectations
        if len(bias_combos) != counts['bias_combinations']:
            print(f"❌ Bias combination count mismatch: {len(bias_combos)} vs {counts['bias_combinations']}")
            success = False
        
        if len(strategy_combos) != counts['strategy_combinations']:
            print(f"❌ Strategy combination count mismatch: {len(strategy_combos)} vs {counts['strategy_combinations']}")
            success = False
            
    except Exception as e:
        print(f"❌ Combination generation error: {e}")
        success = False
    
    # Test validation functions
    try:
        # Test with valid combinations
        valid_bias = {
            'macd_line_lower': -2.0,
            'macd_line_upper': 2.0,
            'macd_histogram_lower': -1.0,
            'macd_histogram_upper': 1.0
        }
        
        valid_strategy = {
            'neutral_buy': 0.3,
            'neutral_sell': 0.7,
            'bullish_buy_adjust': 0.0,
            'strong_bullish_buy_adjust': 0.1,
            'bearish_buy_adjust': -0.05,
            'bearish_sell_adjust': 0.0,
            'strong_bearish_sell_adjust': -0.1,
            'bullish_sell_adjust': 0.15
        }
        
        if not validate_bias_thresholds(valid_bias):
            print("❌ Valid bias threshold rejected")
            success = False
        
        if not validate_strategy_thresholds(valid_strategy):
            print("❌ Valid strategy threshold rejected")
            success = False
            
        print("✅ Validation functions working correctly")
        
    except Exception as e:
        print(f"❌ Validation function error: {e}")
        success = False
    
    # Check file exists
    test_file = Path("tests/test_parameter_combination_logic.py")
    if not test_file.exists():
        print(f"❌ Missing test file: {test_file}")
        success = False
    else:
        print(f"✅ Test file exists: {test_file}")
    
    # Run tests
    try:
        import subprocess
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "tests/test_parameter_combination_logic.py", 
            "-v"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ All tests passed")
        else:
            print(f"❌ Tests failed:\n{result.stdout}\n{result.stderr}")
            success = False
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        success = False
    
    if success:
        print("\n🎉 Phase 1.1.2 validation PASSED!")
        print("Ready to proceed to Phase 1.1.3: Complete Parameter Generation")
        return True
    else:
        print("\n❌ Phase 1.1.2 validation FAILED!")
        print("Please fix the issues before proceeding.")
        return False

if __name__ == "__main__":
    validate_phase_1_1_2()
```

## Success Criteria for Phase 1.1.2

### Functional Requirements:
- ✅ Bias threshold combination generation (25 combinations)
- ✅ Strategy threshold combination generation (96 combinations)
- ✅ Combination count estimation and validation
- ✅ Parameter validation functions

### Testing Requirements:
- ✅ Comprehensive unit tests for combination generators
- ✅ Validation function testing with edge cases
- ✅ Integration tests for combination coverage
- ✅ Determinism and uniqueness testing

### Quality Requirements:
- ✅ Proper input validation and error handling
- ✅ Combination logical consistency validation
- ✅ Performance optimization for large combination sets
- ✅ Clear documentation and type hints

## Next Steps
Upon successful validation of Phase 1.1.2, proceed to **Phase 1.1.3: Complete Parameter Generation** which will implement the full Cartesian product generation using the bias and strategy combinations created here.

## TDD Cycle for Phase 1.1.2
1. **RED**: Write failing tests for combination generation
2. **GREEN**: Implement combination logic to pass tests  
3. **REFACTOR**: Optimize combination generation performance
4. **VALIDATE**: Run validation script to confirm completion