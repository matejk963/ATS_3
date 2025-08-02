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
    SL_TP_RATIOS,
    BIAS_THRESHOLD_RANGES,
    BIAS_THRESHOLD_DEFAULTS,
    NEUTRAL_STRATEGY_RANGES,
    BIAS_ADJUSTMENT_RANGES,
    POSITION_THRESHOLD_DEFAULTS
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
        
        with pytest.raises(ValueError, match="step must be positive"):
            generate_symmetric_pairs(2.0, 0.0)


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


class TestBiasThresholdRanges:
    """Test bias classification threshold configurations."""
    
    def test_bias_threshold_ranges_structure(self):
        """Test bias threshold ranges have correct structure."""
        assert isinstance(BIAS_THRESHOLD_RANGES, dict)
        assert 'macd_line_pairs' in BIAS_THRESHOLD_RANGES
        assert 'macd_histogram_pairs' in BIAS_THRESHOLD_RANGES
        
        # Check that ranges are lists of tuples
        for key, pairs in BIAS_THRESHOLD_RANGES.items():
            assert isinstance(pairs, list)
            for pair in pairs:
                assert isinstance(pair, tuple)
                assert len(pair) == 2
                assert pair[0] < 0 and pair[1] > 0  # Symmetric pairs
                assert abs(pair[0]) == abs(pair[1])  # Truly symmetric
    
    def test_bias_threshold_defaults(self):
        """Test bias threshold default values."""
        assert isinstance(BIAS_THRESHOLD_DEFAULTS, dict)
        required_keys = ['macd_line_lower', 'macd_line_upper', 'macd_histogram_lower', 'macd_histogram_upper']
        
        for key in required_keys:
            assert key in BIAS_THRESHOLD_DEFAULTS
            assert isinstance(BIAS_THRESHOLD_DEFAULTS[key], (int, float))
        
        # Check logical relationships
        assert BIAS_THRESHOLD_DEFAULTS['macd_line_lower'] < BIAS_THRESHOLD_DEFAULTS['macd_line_upper']
        assert BIAS_THRESHOLD_DEFAULTS['macd_histogram_lower'] < BIAS_THRESHOLD_DEFAULTS['macd_histogram_upper']


class TestNeutralStrategyRanges:
    """Test neutral strategy position threshold ranges."""
    
    def test_neutral_strategy_ranges_structure(self):
        """Test neutral strategy ranges have correct structure."""
        assert isinstance(NEUTRAL_STRATEGY_RANGES, dict)
        assert 'buy_values' in NEUTRAL_STRATEGY_RANGES
        assert 'sell_values' in NEUTRAL_STRATEGY_RANGES
        
        # Check that values are lists of floats
        for key, values in NEUTRAL_STRATEGY_RANGES.items():
            assert isinstance(values, list)
            assert len(values) > 0
            assert all(isinstance(val, (int, float)) for val in values)
            assert all(0.0 <= val <= 1.0 for val in values)  # Position values should be [0,1]
    
    def test_neutral_strategy_logic(self):
        """Test that buy values are lower than sell values (logical trading behavior)."""
        buy_values = NEUTRAL_STRATEGY_RANGES['buy_values']
        sell_values = NEUTRAL_STRATEGY_RANGES['sell_values']
        
        # Buy thresholds should generally be lower than sell thresholds
        max_buy = max(buy_values)
        min_sell = min(sell_values)
        assert max_buy < min_sell, "Buy thresholds should be lower than sell thresholds"


class TestBiasAdjustmentRanges:
    """Test bias adjustment ranges for dynamic threshold modification."""
    
    def test_bias_adjustment_ranges_structure(self):
        """Test bias adjustment ranges have correct structure."""
        assert isinstance(BIAS_ADJUSTMENT_RANGES, dict)
        
        required_keys = [
            'buy_adjustment_bullish', 'buy_adjustment_strong_bullish', 'buy_adjustment_bearish',
            'sell_adjustment_bearish', 'sell_adjustment_strong_bearish', 'sell_adjustment_bullish'
        ]
        
        for key in required_keys:
            assert key in BIAS_ADJUSTMENT_RANGES
            assert isinstance(BIAS_ADJUSTMENT_RANGES[key], list)
            assert len(BIAS_ADJUSTMENT_RANGES[key]) > 0
            assert all(isinstance(val, (int, float)) for val in BIAS_ADJUSTMENT_RANGES[key])
    
    def test_bias_adjustment_logic(self):
        """Test logical relationships in bias adjustments."""
        # Bullish adjustments for buy should be non-negative (easier entry)
        buy_bullish = BIAS_ADJUSTMENT_RANGES['buy_adjustment_strong_bullish']
        assert all(val >= 0 for val in buy_bullish)
        
        # Bearish adjustments for buy should be non-positive (harder entry)
        buy_bearish = BIAS_ADJUSTMENT_RANGES['buy_adjustment_bearish']
        assert all(val <= 0 for val in buy_bearish)
        
        # Bearish adjustments for sell should be non-positive (easier exit)
        sell_bearish = BIAS_ADJUSTMENT_RANGES['sell_adjustment_strong_bearish']
        assert all(val <= 0 for val in sell_bearish)
        
        # Bullish adjustments for sell should be non-negative (harder exit)
        sell_bullish = BIAS_ADJUSTMENT_RANGES['sell_adjustment_bullish']
        assert all(val >= 0 for val in sell_bullish)


class TestPositionThresholdDefaults:
    """Test position threshold default configurations."""
    
    def test_position_threshold_defaults_structure(self):
        """Test position threshold defaults have correct structure."""
        assert isinstance(POSITION_THRESHOLD_DEFAULTS, dict)
        
        required_keys = [
            'strong_bullish_buy', 'bullish_buy', 'bullish_sell', 'neutral_buy',
            'neutral_sell', 'bearish_buy', 'bearish_sell', 'strong_bearish_sell'
        ]
        
        for key in required_keys:
            assert key in POSITION_THRESHOLD_DEFAULTS
            assert isinstance(POSITION_THRESHOLD_DEFAULTS[key], (int, float))
            assert 0.0 <= POSITION_THRESHOLD_DEFAULTS[key] <= 1.0
    
    def test_position_threshold_logic(self):
        """Test logical relationships in position thresholds."""
        defaults = POSITION_THRESHOLD_DEFAULTS
        
        # Buy thresholds should generally be lower than sell thresholds
        assert defaults['strong_bullish_buy'] < defaults['bullish_sell']
        assert defaults['bullish_buy'] < defaults['bullish_sell']
        assert defaults['neutral_buy'] < defaults['neutral_sell']
        assert defaults['bearish_buy'] < defaults['bearish_sell']
        
        # More aggressive conditions should have more extreme thresholds
        assert defaults['strong_bullish_buy'] >= defaults['bullish_buy']  # More aggressive buy entry
        assert defaults['strong_bearish_sell'] <= defaults['bearish_sell']  # More aggressive sell exit


class TestParameterInfo:
    """Test parameter information function."""
    
    def test_parameter_info_structure(self):
        """Test that parameter info returns correct structure."""
        info = get_basic_parameter_info()
        
        required_keys = [
            'total_contracts', 'atr_macd_granularities', 'swing_granularities',
            'macd_configs', 'atr_lookbacks', 'stop_loss_ranges', 'sl_tp_ratios',
            'bias_macd_line_pairs', 'bias_macd_histogram_pairs', 'neutral_buy_values', 
            'neutral_sell_values', 'bias_adjustment_combinations', 'date_range'
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
        assert info['bias_macd_line_pairs'] == len(BIAS_THRESHOLD_RANGES['macd_line_pairs'])
        assert info['bias_macd_histogram_pairs'] == len(BIAS_THRESHOLD_RANGES['macd_histogram_pairs'])
        assert info['neutral_buy_values'] == len(NEUTRAL_STRATEGY_RANGES['buy_values'])
        assert info['neutral_sell_values'] == len(NEUTRAL_STRATEGY_RANGES['sell_values'])
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