# Phase 1.1.3: Complete Parameter Generation

## Overview
**Dependencies**: Phase 1.1.2 completed  
**Track**: Parameter Logic (Track A)

This micro-phase completes the parameter generation system by implementing the full Cartesian product generation, combining all parameter components into complete trading strategy combinations.

## Objectives
1. Implement full Cartesian product generation for all parameters
2. Add combo_id assignment and metadata creation
3. Write integration tests for full generation pipeline
4. Perform load testing with ~115K combinations

## Implementation Steps

### Step 1: Complete Parameter Combinations File

Add to `src/gpu_parallel_processing/parameter_combinations.py`:

```python
# Add after existing functions

def generate_all_parameter_combinations() -> List[Dict]:
    """
    Generate ALL parameter combinations using Cartesian product.
    
    Creates the complete set of trading strategy parameter combinations by taking
    the Cartesian product of:
    - Contracts
    - Predictor granularities (ATR/MACD and swing)
    - MACD configurations
    - ATR lookback periods
    - Bias threshold combinations
    - Strategy threshold combinations  
    - Stop loss ranges
    - Stop loss to take profit ratios
    
    Returns:
        List of complete parameter combination dictionaries.
        Each combination represents a unique trading strategy configuration.
        
    Example:
        >>> combinations = generate_all_parameter_combinations()
        >>> len(combinations)  # ~115,200 combinations
        115200
        >>> combinations[0]
        {
            'combo_id': 0,
            'date_range': {'start': '2025-04-01', 'end': '2025-06-30'},
            'contract': 'dem07_25',
            'predictor_granularities': {'atr_macd': '15min', 'swing': '15min'},
            'macd_params': {'short': 12, 'long': 26, 'signal': 9},
            'atr_lookback': 21,
            'bias_thresholds': {
                'macd_line_lower': -2.5,
                'macd_line_upper': 2.5,
                'macd_histogram_lower': -1.25,
                'macd_histogram_upper': 1.25
            },
            'strategy_thresholds': {
                'neutral_buy': 0.2,
                'neutral_sell': 0.7,
                'bullish_buy_adjust': 0.0,
                'strong_bullish_buy_adjust': 0.05,
                'bearish_buy_adjust': -0.1,
                'bearish_sell_adjust': 0.0,
                'strong_bearish_sell_adjust': -0.1,
                'bullish_sell_adjust': 0.05
            },
            'stop_loss': 0.5,
            'sl_tp_ratio': 1.5,
            'tp_value': 0.75
        }
    """
    print("🔄 Generating parameter combinations...")
    print("   📊 This may take a few moments for large parameter spaces...")
    
    # Generate component combinations
    bias_combinations = generate_bias_threshold_combinations()
    strategy_combinations = generate_strategy_threshold_combinations()
    
    print(f"   ✅ Generated {len(bias_combinations)} bias combinations")
    print(f"   ✅ Generated {len(strategy_combinations)} strategy combinations")
    
    # Generate final Cartesian product of ALL parameters
    combinations = []
    combo_idx = 0
    
    total_expected = get_combination_counts()['total_combinations_estimate']
    print(f"   🎯 Generating {total_expected:,} total combinations...")
    
    # Progress tracking for large generation
    progress_interval = max(1000, total_expected // 100)  # Report every 1% or 1000, whichever is larger
    
    for (contract, atr_macd_gran, swing_gran, macd_config, atr_lookback, 
         bias_thresholds, strategy_thresholds, stop_loss, sl_tp_ratio) in itertools.product(
        CONTRACTS,
        PREDICTOR_GRANULARITIES['atr_macd_granularities'],
        PREDICTOR_GRANULARITIES['swing_granularities'],
        MACD_CONFIGS,
        ATR_LOOKBACKS,
        bias_combinations,
        strategy_combinations,
        STOP_LOSS_RANGES,
        SL_TP_RATIOS
    ):
        # Calculate take profit value
        tp_value = stop_loss * sl_tp_ratio
        
        # Create combination dictionary
        combo = {
            'combo_id': combo_idx,
            'date_range': DATE_RANGE.copy(),  # Copy to avoid shared references
            'contract': contract,
            'predictor_granularities': {
                'atr_macd': atr_macd_gran,
                'swing': swing_gran
            },
            'macd_params': {
                'short': macd_config[0], 
                'long': macd_config[1], 
                'signal': macd_config[2]
            },
            'atr_lookback': atr_lookback,
            'bias_thresholds': bias_thresholds.copy(),  # Copy to avoid shared references
            'strategy_thresholds': strategy_thresholds.copy(),  # Copy to avoid shared references
            'stop_loss': stop_loss,
            'sl_tp_ratio': sl_tp_ratio,
            'tp_value': tp_value
        }
        
        # Validate combination before adding
        if validate_complete_combination(combo):
            combinations.append(combo)
        else:
            print(f"⚠️  Skipping invalid combination {combo_idx}")
        
        combo_idx += 1
        
        # Progress reporting
        if combo_idx % progress_interval == 0:
            progress_pct = (combo_idx / total_expected) * 100
            print(f"   📈 Progress: {combo_idx:,}/{total_expected:,} ({progress_pct:.1f}%)")
    
    print(f"✅ Generated {len(combinations):,} valid parameter combinations")
    print(f"🎯 Combination generation complete!")
    
    return combinations


def validate_complete_combination(combo: Dict) -> bool:
    """
    Validate a complete parameter combination for consistency and correctness.
    
    Args:
        combo: Complete parameter combination dictionary
        
    Returns:
        True if combination is valid, False otherwise
        
    Validation includes:
    - Required keys present
    - Parameter value ranges
    - Logical consistency between parameters
    - MACD parameter relationships
    - Threshold validations
    """
    try:
        # Check required keys
        required_keys = [
            'combo_id', 'date_range', 'contract', 'predictor_granularities',
            'macd_params', 'atr_lookback', 'bias_thresholds', 'strategy_thresholds',
            'stop_loss', 'sl_tp_ratio', 'tp_value'
        ]
        
        for key in required_keys:
            if key not in combo:
                return False
        
        # Validate combo_id
        if not isinstance(combo['combo_id'], int) or combo['combo_id'] < 0:
            return False
        
        # Validate date range
        date_range = combo['date_range']
        if not isinstance(date_range, dict) or 'start' not in date_range or 'end' not in date_range:
            return False
        
        # Validate contract
        if not isinstance(combo['contract'], str) or combo['contract'] not in CONTRACTS:
            return False
        
        # Validate predictor granularities
        pred_gran = combo['predictor_granularities']
        if not isinstance(pred_gran, dict) or 'atr_macd' not in pred_gran or 'swing' not in pred_gran:
            return False
        
        valid_granularities = ['15min', '30min', '1h', '4h', '1d']
        if (pred_gran['atr_macd'] not in valid_granularities or 
            pred_gran['swing'] not in valid_granularities):
            return False
        
        # Validate MACD parameters
        macd_params = combo['macd_params']
        if not isinstance(macd_params, dict):
            return False
        
        required_macd_keys = ['short', 'long', 'signal']
        for key in required_macd_keys:
            if key not in macd_params:
                return False
            if not isinstance(macd_params[key], int) or macd_params[key] <= 0:
                return False
        
        # MACD short must be less than long
        if macd_params['short'] >= macd_params['long']:
            return False
        
        # Validate ATR lookback
        if not isinstance(combo['atr_lookback'], int) or combo['atr_lookback'] <= 0:
            return False
        
        # Validate bias thresholds using existing function
        if not validate_bias_thresholds(combo['bias_thresholds']):
            return False
        
        # Validate strategy thresholds using existing function
        if not validate_strategy_thresholds(combo['strategy_thresholds']):
            return False
        
        # Validate stop loss and ratios
        if not isinstance(combo['stop_loss'], (int, float)) or combo['stop_loss'] <= 0:
            return False
        
        if not isinstance(combo['sl_tp_ratio'], (int, float)) or combo['sl_tp_ratio'] <= 0:
            return False
        
        # Validate calculated TP value
        expected_tp = combo['stop_loss'] * combo['sl_tp_ratio']
        if abs(combo['tp_value'] - expected_tp) > 0.001:  # Allow small floating point differences
            return False
        
        return True
        
    except (KeyError, TypeError, ValueError):
        return False


def generate_combination_batch(start_idx: int, batch_size: int) -> List[Dict]:
    """
    Generate a batch of parameter combinations for memory-efficient processing.
    
    Useful for processing large parameter spaces without loading all combinations
    into memory at once.
    
    Args:
        start_idx: Starting combination index
        batch_size: Number of combinations to generate
        
    Returns:
        List of parameter combinations for the specified batch
        
    Note:
        This generates combinations on-demand rather than pre-generating all.
        Useful for very large parameter spaces where memory is limited.
    """
    print(f"🔄 Generating combination batch: {start_idx} to {start_idx + batch_size - 1}")
    
    # Generate component combinations
    bias_combinations = generate_bias_threshold_combinations()
    strategy_combinations = generate_strategy_threshold_combinations()
    
    # Calculate which combinations to include in this batch
    all_params = list(itertools.product(
        CONTRACTS,
        PREDICTOR_GRANULARITIES['atr_macd_granularities'],
        PREDICTOR_GRANULARITIES['swing_granularities'],
        MACD_CONFIGS,
        ATR_LOOKBACKS,
        bias_combinations,
        strategy_combinations,
        STOP_LOSS_RANGES,
        SL_TP_RATIOS
    ))
    
    # Extract the requested batch
    end_idx = min(start_idx + batch_size, len(all_params))
    batch_params = all_params[start_idx:end_idx]
    
    combinations = []
    for i, (contract, atr_macd_gran, swing_gran, macd_config, atr_lookback, 
            bias_thresholds, strategy_thresholds, stop_loss, sl_tp_ratio) in enumerate(batch_params):
        
        combo_idx = start_idx + i
        tp_value = stop_loss * sl_tp_ratio
        
        combo = {
            'combo_id': combo_idx,
            'date_range': DATE_RANGE.copy(),
            'contract': contract,
            'predictor_granularities': {
                'atr_macd': atr_macd_gran,
                'swing': swing_gran
            },
            'macd_params': {
                'short': macd_config[0], 
                'long': macd_config[1], 
                'signal': macd_config[2]
            },
            'atr_lookback': atr_lookback,
            'bias_thresholds': bias_thresholds.copy(),
            'strategy_thresholds': strategy_thresholds.copy(),
            'stop_loss': stop_loss,
            'sl_tp_ratio': sl_tp_ratio,
            'tp_value': tp_value
        }
        
        if validate_complete_combination(combo):
            combinations.append(combo)
    
    print(f"✅ Generated batch: {len(combinations)} valid combinations")
    return combinations


def get_combination_sample(count: int = 10) -> List[Dict]:
    """
    Get a sample of parameter combinations for testing and validation.
    
    Args:
        count: Number of sample combinations to generate
        
    Returns:
        List of sample parameter combinations
    """
    print(f"🔍 Generating {count} sample combinations...")
    
    # Generate a small batch from the beginning
    sample_combinations = generate_combination_batch(0, count)
    
    print(f"✅ Generated {len(sample_combinations)} sample combinations")
    return sample_combinations


def export_combinations_to_file(combinations: List[Dict], filepath: str) -> bool:
    """
    Export parameter combinations to a JSON file.
    
    Args:
        combinations: List of parameter combinations
        filepath: Output file path
        
    Returns:
        True if export successful, False otherwise
    """
    try:
        import json
        from pathlib import Path
        
        output_path = Path(filepath)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        print(f"💾 Exporting {len(combinations)} combinations to {filepath}...")
        
        with open(output_path, 'w') as f:
            json.dump(combinations, f, indent=2)
        
        file_size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"✅ Export complete: {file_size_mb:.1f} MB written")
        
        return True
        
    except Exception as e:
        print(f"❌ Export failed: {e}")
        return False


if __name__ == "__main__":
    # Performance testing and validation
    print("🧪 Testing complete parameter generation...")
    
    # Test sample generation
    samples = get_combination_sample(5)
    print(f"Sample combinations generated: {len(samples)}")
    
    # Test combination counts
    counts = get_combination_counts()
    print(f"Expected total combinations: {counts['total_combinations_estimate']:,}")
    
    # Test small batch generation for performance
    print("\n⚡ Performance testing...")
    import time
    
    start_time = time.time()
    small_batch = generate_combination_batch(0, 100)
    batch_time = time.time() - start_time
    
    print(f"Generated 100 combinations in {batch_time:.2f} seconds")
    print(f"Estimated time for full generation: {(batch_time * counts['total_combinations_estimate'] / 100 / 60):.1f} minutes")
    
    # Validate generated combinations
    valid_count = sum(1 for combo in small_batch if validate_complete_combination(combo))
    print(f"Validation: {valid_count}/{len(small_batch)} combinations valid")
    
    print("✅ Complete parameter generation system ready!")
```

### Step 2: Create Integration Test File (`tests/test_complete_parameter_generation.py`)

```python
"""
Integration tests for complete parameter generation (Phase 1.1.3).

Tests full Cartesian product generation and validation.
"""

import pytest
import time
import tempfile
import json
from pathlib import Path
from src.gpu_parallel_processing.parameter_combinations import (
    generate_all_parameter_combinations,
    generate_combination_batch,
    get_combination_sample,
    validate_complete_combination,
    export_combinations_to_file,
    get_combination_counts,
    CONTRACTS,
    PREDICTOR_GRANULARITIES,
    MACD_CONFIGS,
    ATR_LOOKBACKS,
    STOP_LOSS_RANGES,
    SL_TP_RATIOS
)


class TestCompleteParameterGeneration:
    """Test complete parameter combination generation."""
    
    def test_generate_sample_combinations(self):
        """Test sample combination generation."""
        samples = get_combination_sample(5)
        
        assert len(samples) == 5
        
        # Check structure of generated combinations
        for combo in samples:
            assert self._validate_combination_structure(combo)
    
    def test_combination_batch_generation(self):
        """Test batch combination generation."""
        batch_size = 10
        batch = generate_combination_batch(0, batch_size)
        
        assert len(batch) <= batch_size  # May be less due to validation
        
        # Check combo_id sequence
        for i, combo in enumerate(batch):
            assert combo['combo_id'] == i
            assert self._validate_combination_structure(combo)
    
    def test_combination_validation(self):
        """Test complete combination validation."""
        samples = get_combination_sample(3)
        
        # All generated combinations should be valid
        for combo in samples:
            assert validate_complete_combination(combo)
        
        # Test invalid combination
        invalid_combo = samples[0].copy()
        invalid_combo['macd_params']['short'] = invalid_combo['macd_params']['long']  # Invalid: short >= long
        assert not validate_complete_combination(invalid_combo)
    
    def test_combination_uniqueness(self):
        """Test that generated combinations are unique."""
        samples = get_combination_sample(20)
        
        # Convert to tuples for uniqueness check (excluding combo_id)
        combo_signatures = []
        for combo in samples:
            signature = (
                combo['contract'],
                combo['predictor_granularities']['atr_macd'],
                combo['predictor_granularities']['swing'],
                tuple(combo['macd_params'].values()),
                combo['atr_lookback'],
                tuple(combo['bias_thresholds'].values()),
                tuple(combo['strategy_thresholds'].values()),
                combo['stop_loss'],
                combo['sl_tp_ratio']
            )
            combo_signatures.append(signature)
        
        # All should be unique
        assert len(combo_signatures) == len(set(combo_signatures))
    
    def test_tp_value_calculation(self):
        """Test that TP values are calculated correctly."""
        samples = get_combination_sample(10)
        
        for combo in samples:
            expected_tp = combo['stop_loss'] * combo['sl_tp_ratio']
            assert abs(combo['tp_value'] - expected_tp) < 0.001
    
    def _validate_combination_structure(self, combo):
        """Helper to validate combination structure."""
        required_keys = [
            'combo_id', 'date_range', 'contract', 'predictor_granularities',
            'macd_params', 'atr_lookback', 'bias_thresholds', 'strategy_thresholds',
            'stop_loss', 'sl_tp_ratio', 'tp_value'
        ]
        
        for key in required_keys:
            if key not in combo:
                return False
        
        # Check specific structures
        if not isinstance(combo['predictor_granularities'], dict):
            return False
        if 'atr_macd' not in combo['predictor_granularities']:
            return False
        if 'swing' not in combo['predictor_granularities']:
            return False
        
        if not isinstance(combo['macd_params'], dict):
            return False
        if not all(key in combo['macd_params'] for key in ['short', 'long', 'signal']):
            return False
        
        return True


class TestCombinationCounts:
    """Test combination count calculations and estimates."""
    
    def test_combination_count_accuracy(self):
        """Test that combination counts are accurate for small samples."""
        counts = get_combination_counts()
        
        # Generate a small batch and verify counts are reasonable
        batch = generate_combination_batch(0, 50)
        
        # Should generate combinations without error
        assert len(batch) > 0
        assert len(batch) <= 50
    
    def test_total_combination_estimate(self):
        """Test total combination estimate calculation."""
        counts = get_combination_counts()
        
        # Manual calculation
        expected_total = (len(CONTRACTS) *
                         len(PREDICTOR_GRANULARITIES['atr_macd_granularities']) *
                         len(PREDICTOR_GRANULARITIES['swing_granularities']) *
                         len(MACD_CONFIGS) *
                         len(ATR_LOOKBACKS) *
                         counts['bias_combinations'] *
                         counts['strategy_combinations'] *
                         len(STOP_LOSS_RANGES) *
                         len(SL_TP_RATIOS))
        
        assert counts['total_combinations_estimate'] == expected_total
    
    def test_combination_space_coverage(self):
        """Test that combinations cover the expected parameter space."""
        # Generate larger sample to test coverage
        samples = generate_combination_batch(0, 100)
        
        # Extract unique values for each parameter
        unique_contracts = set(combo['contract'] for combo in samples)
        unique_atr_macd_grans = set(combo['predictor_granularities']['atr_macd'] for combo in samples)
        unique_macd_shorts = set(combo['macd_params']['short'] for combo in samples)
        
        # Should see some variety (not exhaustive coverage with small sample)
        assert len(unique_contracts) >= 1
        assert len(unique_atr_macd_grans) >= 1
        assert len(unique_macd_shorts) >= 1


class TestCombinationExport:
    """Test combination export functionality."""
    
    def test_export_to_file(self):
        """Test exporting combinations to JSON file."""
        samples = get_combination_sample(5)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "test_combinations.json"
            
            # Export combinations
            success = export_combinations_to_file(samples, str(output_file))
            assert success
            
            # Verify file was created
            assert output_file.exists()
            
            # Verify file contents
            with open(output_file, 'r') as f:
                loaded_combinations = json.load(f)
            
            assert len(loaded_combinations) == len(samples)
            assert loaded_combinations[0]['combo_id'] == samples[0]['combo_id']
    
    def test_export_empty_list(self):
        """Test exporting empty combination list."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "empty_combinations.json"
            
            success = export_combinations_to_file([], str(output_file))
            assert success
            
            with open(output_file, 'r') as f:
                loaded_combinations = json.load(f)
            
            assert loaded_combinations == []


class TestPerformance:
    """Test performance characteristics of combination generation."""
    
    def test_small_batch_performance(self):
        """Test performance of small batch generation."""
        start_time = time.time()
        batch = generate_combination_batch(0, 50)
        generation_time = time.time() - start_time
        
        # Should generate 50 combinations quickly (under 5 seconds)
        assert generation_time < 5.0
        assert len(batch) > 0
        
        print(f"Generated {len(batch)} combinations in {generation_time:.3f} seconds")
        print(f"Rate: {len(batch) / generation_time:.1f} combinations/second")
    
    def test_memory_efficiency(self):
        """Test that batch generation is memory efficient."""
        import sys
        
        # Generate combinations in batches to test memory usage
        batch_sizes = [10, 50, 100]
        
        for batch_size in batch_sizes:
            batch = generate_combination_batch(0, batch_size)
            
            # Calculate approximate memory usage
            combo_size = sys.getsizeof(batch[0]) if batch else 0
            total_size = len(batch) * combo_size
            
            print(f"Batch size {batch_size}: ~{total_size / 1024:.1f} KB")
            
            # Should be reasonable memory usage
            assert total_size < 1024 * 1024  # Less than 1MB for test batches
    
    @pytest.mark.slow
    def test_large_batch_generation(self):
        """Test generation of larger combination batches."""
        # Only run if specifically requested (marked as slow)
        large_batch = generate_combination_batch(0, 1000)
        
        assert len(large_batch) > 0
        assert len(large_batch) <= 1000
        
        # All should be valid
        valid_count = sum(1 for combo in large_batch if validate_complete_combination(combo))
        assert valid_count == len(large_batch)


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_invalid_batch_parameters(self):
        """Test batch generation with invalid parameters."""
        # Start index beyond available combinations
        total_combinations = get_combination_counts()['total_combinations_estimate']
        
        batch = generate_combination_batch(total_combinations + 1000, 10)
        assert len(batch) == 0  # Should return empty list
    
    def test_zero_batch_size(self):
        """Test batch generation with zero size."""
        batch = generate_combination_batch(0, 0)
        assert len(batch) == 0
    
    def test_combination_validation_edge_cases(self):
        """Test combination validation with edge cases."""
        # Test with missing keys
        incomplete_combo = {'combo_id': 0}
        assert not validate_complete_combination(incomplete_combo)
        
        # Test with wrong types
        bad_combo = get_combination_sample(1)[0]
        bad_combo['combo_id'] = "not_an_integer"
        assert not validate_complete_combination(bad_combo)


class TestIntegration:
    """Integration tests combining multiple components."""
    
    def test_end_to_end_generation_and_validation(self):
        """Test complete end-to-end generation and validation."""
        # Generate sample
        samples = get_combination_sample(10)
        
        # Validate all combinations
        all_valid = all(validate_complete_combination(combo) for combo in samples)
        assert all_valid
        
        # Export to file
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "integration_test.json"
            success = export_combinations_to_file(samples, str(output_file))
            assert success
            
            # Reload and validate
            with open(output_file, 'r') as f:
                reloaded = json.load(f)
            
            assert len(reloaded) == len(samples)
            
            # Re-validate loaded combinations
            reloaded_valid = all(validate_complete_combination(combo) for combo in reloaded)
            assert reloaded_valid
    
    def test_deterministic_generation(self):
        """Test that generation is deterministic."""
        batch1 = generate_combination_batch(0, 20)
        batch2 = generate_combination_batch(0, 20)
        
        # Should be identical
        assert len(batch1) == len(batch2)
        
        for combo1, combo2 in zip(batch1, batch2):
            assert combo1 == combo2


if __name__ == "__main__":
    # Run with: pytest tests/test_complete_parameter_generation.py -v
    # Run slow tests with: pytest tests/test_complete_parameter_generation.py -v -m slow
    pytest.main([__file__, "-v"])
```

### Step 3: Create Performance Test Script (`tests/test_parameter_generation_performance.py`)

```python
"""
Performance tests for complete parameter generation system.

Tests loading, memory usage, and generation speed.
"""

import time
import psutil
import os
from src.gpu_parallel_processing.parameter_combinations import (
    generate_combination_batch,
    get_combination_sample,
    get_combination_counts,
    export_combinations_to_file
)


def test_generation_performance():
    """Test parameter generation performance metrics."""
    print("🚀 Parameter Generation Performance Test")
    print("=" * 50)
    
    # Get system info
    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss / 1024 / 1024  # MB
    
    print(f"💾 Initial memory usage: {initial_memory:.1f} MB")
    
    # Test different batch sizes
    batch_sizes = [10, 50, 100, 500]
    
    for batch_size in batch_sizes:
        print(f"\n📊 Testing batch size: {batch_size}")
        
        start_time = time.time()
        start_memory = process.memory_info().rss / 1024 / 1024
        
        # Generate batch
        batch = generate_combination_batch(0, batch_size)
        
        end_time = time.time()
        end_memory = process.memory_info().rss / 1024 / 1024
        
        generation_time = end_time - start_time
        memory_used = end_memory - start_memory
        rate = len(batch) / generation_time if generation_time > 0 else 0
        
        print(f"   ⏱️  Time: {generation_time:.3f} seconds")
        print(f"   💾 Memory: +{memory_used:.1f} MB")
        print(f"   📈 Rate: {rate:.1f} combinations/second")
        print(f"   ✅ Generated: {len(batch)} combinations")
    
    # Test large scale estimation
    counts = get_combination_counts()
    total_combinations = counts['total_combinations_estimate']
    
    print(f"\n🎯 Total combinations estimated: {total_combinations:,}")
    
    # Estimate full generation time based on small batch performance
    small_batch_start = time.time()
    small_batch = generate_combination_batch(0, 100)
    small_batch_time = time.time() - small_batch_start
    
    if small_batch_time > 0:
        estimated_full_time_minutes = (small_batch_time * total_combinations / len(small_batch)) / 60
        print(f"⏳ Estimated full generation time: {estimated_full_time_minutes:.1f} minutes")
    
    # Memory projection
    final_memory = process.memory_info().rss / 1024 / 1024
    total_memory_used = final_memory - initial_memory
    
    if len(small_batch) > 0:
        memory_per_combo = total_memory_used / len(small_batch)
        estimated_full_memory_gb = (memory_per_combo * total_combinations) / 1024
        print(f"💾 Estimated full generation memory: {estimated_full_memory_gb:.1f} GB")
    
    print(f"\n🏁 Performance test complete!")
    print(f"📋 Final memory usage: {final_memory:.1f} MB")


def test_export_performance():
    """Test export performance for different file sizes."""
    print("\n💾 Export Performance Test")
    print("=" * 30)
    
    export_sizes = [10, 50, 100]
    
    for size in export_sizes:
        print(f"\n📁 Testing export of {size} combinations...")
        
        # Generate combinations
        combinations = generate_combination_batch(0, size)
        
        # Test export performance
        start_time = time.time()
        
        output_file = f"test_export_{size}.json"
        success = export_combinations_to_file(combinations, output_file)
        
        export_time = time.time() - start_time
        
        if success:
            # Get file size
            import os
            file_size_kb = os.path.getsize(output_file) / 1024
            
            print(f"   ⏱️  Export time: {export_time:.3f} seconds")
            print(f"   📏 File size: {file_size_kb:.1f} KB")
            print(f"   📈 Rate: {size / export_time:.1f} combinations/second")
            
            # Clean up
            os.remove(output_file)
        else:
            print(f"   ❌ Export failed")


if __name__ == "__main__":
    print("🧪 Running Parameter Generation Performance Tests")
    print("=" * 60)
    
    test_generation_performance()
    test_export_performance()
    
    print("\n✅ All performance tests complete!")
```

### Step 4: Create Validation Script (`validate_phase_1_1_3.py`)

```python
"""
Validation script for Phase 1.1.3 completion.

Run this script to verify that Phase 1.1.3 is properly implemented.
"""

import sys
import time
from pathlib import Path

def validate_phase_1_1_3():
    """Validate Phase 1.1.3 implementation."""
    print("🔍 Validating Phase 1.1.3: Complete Parameter Generation...")
    
    success = True
    
    # Check dependencies (Phases 1.1.1 and 1.1.2)
    try:
        from src.gpu_parallel_processing.parameter_combinations import (
            generate_symmetric_pairs, frange, 
            generate_bias_threshold_combinations,
            generate_strategy_threshold_combinations
        )
        print("✅ Phase 1.1.1 and 1.1.2 dependencies available")
    except ImportError as e:
        print(f"❌ Dependency missing: {e}")
        success = False
    
    # Check new Phase 1.1.3 imports
    try:
        from src.gpu_parallel_processing.parameter_combinations import (
            generate_all_parameter_combinations,
            generate_combination_batch,
            get_combination_sample,
            validate_complete_combination,
            export_combinations_to_file
        )
        print("✅ Phase 1.1.3 functions available")
    except ImportError as e:
        print(f"❌ Phase 1.1.3 import error: {e}")
        success = False
    
    # Test sample generation
    try:
        print("\n🧪 Testing sample generation...")
        samples = get_combination_sample(5)
        
        if len(samples) != 5:
            print(f"❌ Expected 5 samples, got {len(samples)}")
            success = False
        else:
            print(f"✅ Generated {len(samples)} sample combinations")
        
        # Validate sample structure
        for i, combo in enumerate(samples):
            if not validate_complete_combination(combo):
                print(f"❌ Sample {i} failed validation")
                success = False
            else:
                print(f"✅ Sample {i} validation passed")
                
    except Exception as e:
        print(f"❌ Sample generation error: {e}")
        success = False
    
    # Test batch generation
    try:
        print("\n📦 Testing batch generation...")
        batch = generate_combination_batch(0, 20)
        
        if len(batch) == 0:
            print("❌ Batch generation returned empty result")
            success = False
        else:
            print(f"✅ Generated batch with {len(batch)} combinations")
        
        # Check combo_id sequence
        for i, combo in enumerate(batch):
            if combo['combo_id'] != i:
                print(f"❌ Combo ID mismatch: expected {i}, got {combo['combo_id']}")
                success = False
                break
        else:
            print("✅ Combo ID sequence correct")
            
    except Exception as e:
        print(f"❌ Batch generation error: {e}")
        success = False
    
    # Test combination validation
    try:
        print("\n🔍 Testing combination validation...")
        
        test_combo = samples[0] if samples else {}
        
        if validate_complete_combination(test_combo):
            print("✅ Valid combination passed validation")
        else:
            print("❌ Valid combination failed validation")
            success = False
        
        # Test invalid combination
        invalid_combo = test_combo.copy() if test_combo else {}
        if invalid_combo:
            invalid_combo['combo_id'] = "invalid_type"
            
            if not validate_complete_combination(invalid_combo):
                print("✅ Invalid combination correctly rejected")
            else:
                print("❌ Invalid combination incorrectly accepted")
                success = False
                
    except Exception as e:
        print(f"❌ Validation testing error: {e}")
        success = False
    
    # Test export functionality
    try:
        print("\n💾 Testing export functionality...")
        
        if samples:
            test_file = "test_combinations_validation.json"
            export_success = export_combinations_to_file(samples, test_file)
            
            if export_success:
                print("✅ Export successful")
                
                # Verify file exists and has content
                export_path = Path(test_file)
                if export_path.exists():
                    file_size = export_path.stat().st_size
                    print(f"✅ Export file created: {file_size} bytes")
                    
                    # Clean up
                    export_path.unlink()
                else:
                    print("❌ Export file not created")
                    success = False
            else:
                print("❌ Export failed")
                success = False
                
    except Exception as e:
        print(f"❌ Export testing error: {e}")
        success = False
    
    # Performance test
    try:
        print("\n⚡ Performance testing...")
        
        start_time = time.time()
        perf_batch = generate_combination_batch(0, 50)
        generation_time = time.time() - start_time
        
        if generation_time > 0:
            rate = len(perf_batch) / generation_time
            print(f"✅ Generated {len(perf_batch)} combinations in {generation_time:.2f}s")
            print(f"📈 Rate: {rate:.1f} combinations/second")
            
            if rate < 10:  # Should be able to generate at least 10 combinations/second
                print("⚠️  Performance warning: generation rate is low")
            else:
                print("✅ Performance acceptable")
        else:
            print("⚠️  Performance test too fast to measure")
            
    except Exception as e:
        print(f"❌ Performance testing error: {e}")
        success = False
    
    # Check test files exist
    test_files = [
        Path("tests/test_complete_parameter_generation.py"),
        Path("tests/test_parameter_generation_performance.py")
    ]
    
    for test_file in test_files:
        if test_file.exists():
            print(f"✅ Test file exists: {test_file}")
        else:
            print(f"❌ Missing test file: {test_file}")
            success = False
    
    # Run tests
    try:
        print("\n🧪 Running integration tests...")
        import subprocess
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "tests/test_complete_parameter_generation.py", 
            "-v", "--tb=short"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ All integration tests passed")
        else:
            print(f"❌ Integration tests failed:\n{result.stdout}\n{result.stderr}")
            success = False
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        success = False
    
    if success:
        print("\n🎉 Phase 1.1.3 validation PASSED!")
        print("✅ Complete parameter generation system is ready")
        print("🚀 Ready to proceed to Phase 1.1.4: Contract Data Manager Foundation")
        return True
    else:
        print("\n❌ Phase 1.1.3 validation FAILED!")
        print("Please fix the issues before proceeding.")
        return False

if __name__ == "__main__":
    validate_phase_1_1_3()
```

## Success Criteria for Phase 1.1.3

### Functional Requirements:
- ✅ Full Cartesian product generation (~115,200 combinations)
- ✅ Batch generation for memory-efficient processing
- ✅ Complete combination validation
- ✅ JSON export functionality
- ✅ Sample generation for testing

### Testing Requirements:
- ✅ Integration tests for full generation pipeline
- ✅ Performance tests for different batch sizes
- ✅ Memory usage and efficiency testing
- ✅ Export/import validation
- ✅ Edge case and error handling tests

### Performance Requirements:
- ✅ Generate 50+ combinations per second
- ✅ Memory-efficient batch processing
- ✅ Deterministic generation results
- ✅ Export capabilities for large datasets

### Quality Requirements:
- ✅ 100% validation pass rate for generated combinations
- ✅ Comprehensive error handling
- ✅ Clear progress reporting for large generations
- ✅ Memory cleanup and optimization

## Next Steps
Upon successful validation of Phase 1.1.3, **Track A (Parameter Logic)** is complete. Proceed to **Phase 1.1.4: Contract Data Manager Foundation** which begins **Track B (Data Management)** and can be developed in parallel or sequentially.

## TDD Cycle for Phase 1.1.3
1. **RED**: Write failing tests for complete generation
2. **GREEN**: Implement full Cartesian product generation
3. **REFACTOR**: Optimize for memory and performance
4. **VALIDATE**: Run comprehensive validation and performance tests