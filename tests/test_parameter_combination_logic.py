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
            'macd_line_upper': -2.0,  # Upper bound smaller than lower bound
            'macd_histogram_lower': -1.0,
            'macd_histogram_upper': 1.0
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