# Phase 1.1.1: Basic Parameter Infrastructure

## Overview
**Dependencies**: None  
**Track**: Parameter Logic (Track A)

This micro-phase establishes the foundational infrastructure for parameter generation, including directory structure, helper functions, and basic parameter constants.

## Objectives
1. Create proper directory structure and module initialization
2. Implement utility functions for parameter range generation
3. Define hardcoded parameter constants
4. Write comprehensive tests for helper functions

## Implementation Steps

### Step 1: Create Directory Structure
```bash
# Create directory structure
mkdir -p src/gpu_parallel_processing
mkdir -p tests
```

### Step 2: Initialize Module (`src/gpu_parallel_processing/__init__.py`)
```python
"""
GPU-accelerated parallel processing module for massive parameter combination generation.

This module provides components for:
- Parameter combination generation and management
- Contract data loading and caching
- GPU batch optimization
- Memory-efficient processing coordination
"""

__version__ = "1.0.0"
__author__ = "ATS_3 Development Team"

# Module imports will be added as components are implemented
```

### Step 3: Create Basic Parameter File (`src/gpu_parallel_processing/parameter_combinations.py`)
```python
"""
Hardcoded parameter configuration and utility functions for massive 
parameter combination generation.

Phase 1.1.1: Basic parameter infrastructure with helper functions.
"""

from typing import List, Tuple


def generate_symmetric_pairs(max_value: float, step: float) -> List[Tuple[float, float]]:
    """
    Generate symmetric pairs for threshold parameters.
    
    Creates pairs like: (-2.5, 2.5), (-2.0, 2.0), (-1.5, 1.5), etc.
    
    Args:
        max_value: Maximum absolute value for pairs
        step: Step size for decreasing values
        
    Returns:
        List of symmetric (negative, positive) tuples
        
    Examples:
        >>> generate_symmetric_pairs(2.0, 0.5)
        [(-2.0, 2.0), (-1.5, 1.5), (-1.0, 1.0), (-0.5, 0.5)]
    """
    if max_value <= 0:
        raise ValueError("max_value must be positive")
    if step <= 0:
        raise ValueError("step must be positive")
    if step > max_value:
        raise ValueError("step cannot be larger than max_value")
    
    pairs = []
    current = max_value
    
    while current >= step:
        pairs.append((-current, current))
        current -= step
    
    return pairs


def frange(start: float, stop: float, step: float) -> List[float]:
    """
    Generate float range with specified step size.
    
    Similar to range() but works with floats and includes proper rounding.
    
    Args:
        start: Starting value (inclusive)
        stop: Stopping value (exclusive)
        step: Step size
        
    Returns:
        List of float values rounded to 2 decimal places
        
    Examples:
        >>> frange(0.1, 0.4, 0.1)
        [0.1, 0.2, 0.3]
        >>> frange(0.2, 0.9, 0.1)
        [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    """
    if step <= 0:
        raise ValueError("step must be positive")
    if start >= stop:
        raise ValueError("start must be less than stop")
    
    values = []
    current = start
    
    while current < stop:
        values.append(round(current, 2))
        current += step
    
    return values


# ============================================================================
# PARAMETER CONFIGURATION CONSTANTS
# ============================================================================

# Date range for all combinations
DATE_RANGE = {
    'start': '2025-04-01',
    'end': '2025-06-30'
}

# Contract codes for power/gas markets
CONTRACTS = [
    'dem07_25',  # Germany power/gas July 2025 → dem07_25_tr_ba_data.parquet
    # Additional contracts can be added here:
    # 'dem08_25',  # Germany August 2025
    # 'fra07_25',  # France July 2025  
    # 'gbr07_25',  # Great Britain July 2025
]

# Predictor granularity configurations
PREDICTOR_GRANULARITIES = {
    'atr_macd_granularities': ['15min', '30min', '1h', '4h'],
    'swing_granularities': ['15min', '30min', '1h', '4h']
}

# MACD configurations: (short, long, signal) tuples
MACD_CONFIGS = [
    (12, 26, 9),    # Standard MACD
    (8, 21, 5),     # Fast MACD
    (19, 39, 9)     # Slow MACD
]

# ATR lookback periods
ATR_LOOKBACKS = [21]

# Stop loss and take profit ratios
STOP_LOSS_RANGES = [0.5, 1.0, 1.5]  # 3 options
SL_TP_RATIOS = [1.5, 2.0]           # 2 options


def get_basic_parameter_info() -> dict:
    """
    Get basic information about parameter configuration.
    
    Returns:
        Dictionary with parameter counts and basic statistics
    """
    return {
        'total_contracts': len(CONTRACTS),
        'atr_macd_granularities': len(PREDICTOR_GRANULARITIES['atr_macd_granularities']),
        'swing_granularities': len(PREDICTOR_GRANULARITIES['swing_granularities']),
        'macd_configs': len(MACD_CONFIGS),
        'atr_lookbacks': len(ATR_LOOKBACKS),
        'stop_loss_ranges': len(STOP_LOSS_RANGES),
        'sl_tp_ratios': len(SL_TP_RATIOS),
        'date_range': DATE_RANGE
    }


if __name__ == "__main__":
    # Quick test of helper functions
    print("Testing helper functions...")
    
    print("Symmetric pairs (2.0, 0.5):", generate_symmetric_pairs(2.0, 0.5))
    print("Float range (0.1, 0.4, 0.1):", frange(0.1, 0.4, 0.1))
    print("Parameter info:", get_basic_parameter_info())
    
    print("✅ Basic parameter infrastructure ready!")
```

### Step 4: Create Test File (`tests/test_parameter_combinations_basic.py`)
```python
"""
Unit tests for basic parameter infrastructure (Phase 1.1.1).

Tests helper functions and basic parameter constants.
"""

import pytest
from src.gpu_parallel_processing.parameter_combinations import (
    generate_symmetric_pairs,
    frange,
    get_basic_parameter_info,
    DATE_RANGE,
    CONTRACTS,
    PREDICTOR_GRANULARITIES,
    MACD_CONFIGS,
    ATR_LOOKBACKS,
    STOP_LOSS_RANGES,
    SL_TP_RATIOS
)


class TestSymmetricPairs:
    """Test symmetric pair generation function."""
    
    def test_basic_symmetric_pairs(self):
        """Test basic symmetric pair generation."""
        pairs = generate_symmetric_pairs(2.0, 0.5)
        expected = [(-2.0, 2.0), (-1.5, 1.5), (-1.0, 1.0), (-0.5, 0.5)]
        assert pairs == expected
    
    def test_single_pair(self):
        """Test generation of single pair."""
        pairs = generate_symmetric_pairs(1.0, 1.0)
        expected = [(-1.0, 1.0)]
        assert pairs == expected
    
    def test_step_larger_than_max(self):
        """Test when step is larger than max_value."""
        pairs = generate_symmetric_pairs(0.5, 1.0)
        expected = []  # No pairs should be generated
        assert pairs == expected
    
    def test_edge_cases(self):
        """Test edge cases for symmetric pairs."""
        # Very small values
        pairs = generate_symmetric_pairs(0.1, 0.1)
        assert pairs == [(-0.1, 0.1)]
        
        # Multiple steps
        pairs = generate_symmetric_pairs(1.0, 0.25)
        expected = [(-1.0, 1.0), (-0.75, 0.75), (-0.5, 0.5), (-0.25, 0.25)]
        assert pairs == expected
    
    def test_invalid_parameters(self):
        """Test error handling for invalid parameters."""
        with pytest.raises(ValueError, match="max_value must be positive"):
            generate_symmetric_pairs(-1.0, 0.5)
        
        with pytest.raises(ValueError, match="step must be positive"):
            generate_symmetric_pairs(2.0, -0.5)
        
        with pytest.raises(ValueError, match="step cannot be larger than max_value"):
            generate_symmetric_pairs(1.0, 2.0)


class TestFRange:
    """Test float range generation function."""
    
    def test_basic_frange(self):
        """Test basic float range generation."""
        values = frange(0.1, 0.4, 0.1)
        expected = [0.1, 0.2, 0.3]
        assert values == expected
    
    def test_larger_range(self):
        """Test larger float range."""
        values = frange(0.2, 0.9, 0.1)
        expected = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
        assert values == expected
    
    def test_step_not_exact_divisor(self):
        """Test when step doesn't divide range evenly."""
        values = frange(0.0, 1.0, 0.3)
        expected = [0.0, 0.3, 0.6, 0.9]
        assert values == expected
    
    def test_rounding_precision(self):
        """Test that values are properly rounded to 2 decimal places."""
        values = frange(0.05, 0.16, 0.05)
        expected = [0.05, 0.1, 0.15]  # Should handle floating point precision
        assert values == expected
    
    def test_single_value(self):
        """Test range that produces single value."""
        values = frange(0.5, 0.6, 0.1)
        expected = [0.5]
        assert values == expected
    
    def test_invalid_parameters(self):
        """Test error handling for invalid parameters."""
        with pytest.raises(ValueError, match="step must be positive"):
            frange(0.0, 1.0, -0.1)
        
        with pytest.raises(ValueError, match="start must be less than stop"):
            frange(1.0, 0.5, 0.1)


class TestParameterConstants:
    """Test parameter constant definitions."""
    
    def test_date_range_structure(self):
        """Test date range has correct structure."""
        assert isinstance(DATE_RANGE, dict)
        assert 'start' in DATE_RANGE
        assert 'end' in DATE_RANGE
        assert DATE_RANGE['start'] < DATE_RANGE['end']
    
    def test_contracts_list(self):
        """Test contracts list is properly defined."""
        assert isinstance(CONTRACTS, list)
        assert len(CONTRACTS) > 0
        assert all(isinstance(contract, str) for contract in CONTRACTS)
        assert 'dem07_25' in CONTRACTS
    
    def test_predictor_granularities(self):
        """Test predictor granularities structure."""
        assert isinstance(PREDICTOR_GRANULARITIES, dict)
        assert 'atr_macd_granularities' in PREDICTOR_GRANULARITIES
        assert 'swing_granularities' in PREDICTOR_GRANULARITIES
        
        # Check that each contains valid granularities
        valid_granularities = ['15min', '30min', '1h', '4h', '1d']
        for granularity_list in PREDICTOR_GRANULARITIES.values():
            assert all(gran in valid_granularities for gran in granularity_list)
    
    def test_macd_configs(self):
        """Test MACD configurations are valid."""
        assert isinstance(MACD_CONFIGS, list)
        assert len(MACD_CONFIGS) > 0
        
        for config in MACD_CONFIGS:
            assert isinstance(config, tuple)
            assert len(config) == 3
            short, long, signal = config
            assert isinstance(short, int) and short > 0
            assert isinstance(long, int) and long > 0
            assert isinstance(signal, int) and signal > 0
            assert short < long  # Short period must be less than long period
    
    def test_atr_lookbacks(self):
        """Test ATR lookback periods."""
        assert isinstance(ATR_LOOKBACKS, list)
        assert len(ATR_LOOKBACKS) > 0
        assert all(isinstance(period, int) and period > 0 for period in ATR_LOOKBACKS)
    
    def test_stop_loss_and_ratios(self):
        """Test stop loss and ratio configurations."""
        assert isinstance(STOP_LOSS_RANGES, list)
        assert isinstance(SL_TP_RATIOS, list)
        assert len(STOP_LOSS_RANGES) > 0
        assert len(SL_TP_RATIOS) > 0
        
        # All values should be positive numbers
        assert all(isinstance(sl, (int, float)) and sl > 0 for sl in STOP_LOSS_RANGES)
        assert all(isinstance(ratio, (int, float)) and ratio > 0 for ratio in SL_TP_RATIOS)


class TestParameterInfo:
    """Test parameter information function."""
    
    def test_parameter_info_structure(self):
        """Test that parameter info returns correct structure."""
        info = get_basic_parameter_info()
        
        required_keys = [
            'total_contracts', 'atr_macd_granularities', 'swing_granularities',
            'macd_configs', 'atr_lookbacks', 'stop_loss_ranges', 'sl_tp_ratios',
            'date_range'
        ]
        
        for key in required_keys:
            assert key in info
    
    def test_parameter_counts(self):
        """Test that parameter counts are correct."""
        info = get_basic_parameter_info()
        
        assert info['total_contracts'] == len(CONTRACTS)
        assert info['atr_macd_granularities'] == len(PREDICTOR_GRANULARITIES['atr_macd_granularities'])
        assert info['swing_granularities'] == len(PREDICTOR_GRANULARITIES['swing_granularities'])
        assert info['macd_configs'] == len(MACD_CONFIGS)
        assert info['atr_lookbacks'] == len(ATR_LOOKBACKS)
        assert info['stop_loss_ranges'] == len(STOP_LOSS_RANGES)
        assert info['sl_tp_ratios'] == len(SL_TP_RATIOS)
        assert info['date_range'] == DATE_RANGE


# Integration test
def test_helper_functions_integration():
    """Test that helper functions work together correctly."""
    # Generate some threshold pairs
    macd_pairs = generate_symmetric_pairs(2.5, 0.5)
    histogram_pairs = generate_symmetric_pairs(1.25, 0.25)
    
    # Generate some float ranges
    buy_values = frange(0.2, 0.4, 0.1)
    sell_values = frange(0.7, 0.9, 0.1)
    
    # Verify we can use these in combination
    assert len(macd_pairs) > 0
    assert len(histogram_pairs) > 0
    assert len(buy_values) > 0
    assert len(sell_values) > 0
    
    # Verify all values are properly typed
    for pair in macd_pairs:
        assert isinstance(pair, tuple)
        assert len(pair) == 2
        assert isinstance(pair[0], float)
        assert isinstance(pair[1], float)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

### Step 5: Validation Script (`validate_phase_1_1_1.py`)
```python
"""
Validation script for Phase 1.1.1 completion.

Run this script to verify that Phase 1.1.1 is properly implemented.
"""

import sys
from pathlib import Path

def validate_phase_1_1_1():
    """Validate Phase 1.1.1 implementation."""
    print("🔍 Validating Phase 1.1.1: Basic Parameter Infrastructure...")
    
    success = True
    
    # Check directory structure
    required_dirs = [
        Path("src/gpu_parallel_processing"),
        Path("tests")
    ]
    
    for dir_path in required_dirs:
        if not dir_path.exists():
            print(f"❌ Missing directory: {dir_path}")
            success = False
        else:
            print(f"✅ Directory exists: {dir_path}")
    
    # Check required files
    required_files = [
        Path("src/gpu_parallel_processing/__init__.py"),
        Path("src/gpu_parallel_processing/parameter_combinations.py"),
        Path("tests/test_parameter_combinations_basic.py")
    ]
    
    for file_path in required_files:
        if not file_path.exists():
            print(f"❌ Missing file: {file_path}")
            success = False
        else:
            print(f"✅ File exists: {file_path}")
    
    # Test imports
    try:
        from src.gpu_parallel_processing.parameter_combinations import (
            generate_symmetric_pairs,
            frange,
            get_basic_parameter_info
        )
        print("✅ All imports successful")
    except ImportError as e:
        print(f"❌ Import error: {e}")
        success = False
    
    # Test helper functions
    try:
        pairs = generate_symmetric_pairs(2.0, 0.5)
        assert len(pairs) == 4
        
        values = frange(0.1, 0.4, 0.1)
        assert len(values) == 3
        
        info = get_basic_parameter_info()
        assert isinstance(info, dict)
        
        print("✅ Helper functions working correctly")
    except Exception as e:
        print(f"❌ Helper function error: {e}")
        success = False
    
    # Run tests
    try:
        import subprocess
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "tests/test_parameter_combinations_basic.py", 
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
        print("\n🎉 Phase 1.1.1 validation PASSED!")
        print("Ready to proceed to Phase 1.1.2: Parameter Combination Logic")
        return True
    else:
        print("\n❌ Phase 1.1.1 validation FAILED!")
        print("Please fix the issues before proceeding.")
        return False

if __name__ == "__main__":
    validate_phase_1_1_1()
```

## Success Criteria for Phase 1.1.1

### Functional Requirements:
- ✅ Directory structure created (`src/gpu_parallel_processing/`, `tests/`)
- ✅ Helper functions implemented (`generate_symmetric_pairs`, `frange`)
- ✅ Parameter constants defined (contracts, granularities, MACD configs, etc.)
- ✅ Module initialization with proper imports

### Testing Requirements:
- ✅ Comprehensive unit tests for helper functions
- ✅ Edge case testing and error handling
- ✅ Parameter validation tests
- ✅ Integration tests for helper function combinations

### Quality Requirements:
- ✅ Proper docstrings and type hints
- ✅ Error handling for invalid inputs
- ✅ Code follows PEP 8 standards
- ✅ Test coverage > 90%

## Next Steps
Upon successful validation of Phase 1.1.1, proceed to **Phase 1.1.2: Parameter Combination Logic** which will build upon these helper functions to implement the actual combination generation algorithms.

## TDD Cycle for Phase 1.1.1
1. **RED**: Write failing tests first (test_parameter_combinations_basic.py)
2. **GREEN**: Implement minimal code to pass tests (parameter_combinations.py)
3. **REFACTOR**: Improve code quality while keeping tests green
4. **VALIDATE**: Run validation script to confirm completion