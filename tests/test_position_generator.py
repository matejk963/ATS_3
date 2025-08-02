"""Unit tests for the GPU-accelerated position signal generator."""

import pytest
import numpy as np
import cupy as cp
from typing import Optional
from dataclasses import dataclass

from src.feature_engineering.array_backend import ArrayBackend
from src.feature_engineering.position_generator import (
    ThresholdConfig,
    GPUPositionGenerator
)


class TestThresholdConfig:
    """Test ThresholdConfig dataclass."""
    
    def test_default_values(self):
        """Test that ThresholdConfig has correct default values."""
        config = ThresholdConfig()
        
        # Strong bullish thresholds
        assert config.strong_bullish_buy == 0.35
        
        # Bullish thresholds
        assert config.bullish_buy == 0.2
        assert config.bullish_sell == 0.9
        
        # Neutral thresholds
        assert config.neutral_buy == 0.2
        assert config.neutral_sell == 0.9
        
        # Bearish thresholds
        assert config.bearish_buy == 0.1
        assert config.bearish_sell == 0.8
        
        # Strong bearish thresholds
        assert config.strong_bearish_sell == 0.65
    
    def test_custom_values(self):
        """Test creating ThresholdConfig with custom values."""
        config = ThresholdConfig(
            strong_bullish_buy=0.4,
            bullish_buy=0.25,
            bullish_sell=0.85
        )
        
        assert config.strong_bullish_buy == 0.4
        assert config.bullish_buy == 0.25
        assert config.bullish_sell == 0.85
        # Others should keep defaults
        assert config.neutral_buy == 0.2


class TestGPUPositionGenerator:
    """Test GPUPositionGenerator class."""
    
    @pytest.fixture
    def backend(self):
        """Create ArrayBackend instance."""
        return ArrayBackend()
    
    @pytest.fixture
    def generator(self, backend):
        """Create GPUPositionGenerator instance."""
        return GPUPositionGenerator(backend)
    
    def test_initialization(self, backend):
        """Test position generator initialization."""
        generator = GPUPositionGenerator(backend)
        assert generator.backend == backend
        assert isinstance(generator.threshold_config, ThresholdConfig)
    
    def test_initialization_with_custom_config(self, backend):
        """Test initialization with custom threshold config."""
        custom_config = ThresholdConfig(strong_bullish_buy=0.4)
        generator = GPUPositionGenerator(backend, custom_config)
        assert generator.threshold_config.strong_bullish_buy == 0.4
    
    def test_strong_bullish_position_signal(self, generator):
        """Test position signals for strong bullish bias (2)."""
        # Strong bullish: Long only when price < 0.35
        bias_numeric = cp.array([2, 2, 2, 2])
        price_position = cp.array([0.2, 0.35, 0.5, 0.8])
        
        signals = generator.compute_position_signals(bias_numeric, price_position)
        
        expected = cp.array([1, 0, 0, 0])  # Long, No position, No position, No position
        assert cp.array_equal(signals, expected)
    
    def test_bullish_position_signal(self, generator):
        """Test position signals for bullish bias (1)."""
        # Bullish: Long when price < 0.2, Short when price > 0.9
        bias_numeric = cp.array([1, 1, 1, 1, 1])
        price_position = cp.array([0.1, 0.2, 0.5, 0.9, 0.95])
        
        signals = generator.compute_position_signals(bias_numeric, price_position)
        
        expected = cp.array([1, 0, 0, 0, -1])  # Long, No position, No position, No position, Short
        assert cp.array_equal(signals, expected)
    
    def test_neutral_position_signal(self, generator):
        """Test position signals for neutral bias (0)."""
        # Neutral: Long when price < 0.2, Short when price > 0.9
        bias_numeric = cp.array([0, 0, 0, 0, 0])
        price_position = cp.array([0.1, 0.2, 0.5, 0.9, 0.95])
        
        signals = generator.compute_position_signals(bias_numeric, price_position)
        
        expected = cp.array([1, 0, 0, 0, -1])  # Long, No position, No position, No position, Short
        assert cp.array_equal(signals, expected)
    
    def test_bearish_position_signal(self, generator):
        """Test position signals for bearish bias (-1)."""
        # Bearish: Long when price < 0.1, Short when price > 0.8
        bias_numeric = cp.array([-1, -1, -1, -1, -1])
        price_position = cp.array([0.05, 0.1, 0.5, 0.8, 0.9])
        
        signals = generator.compute_position_signals(bias_numeric, price_position)
        
        expected = cp.array([1, 0, 0, 0, -1])  # Long, No position, No position, No position, Short
        assert cp.array_equal(signals, expected)
    
    def test_strong_bearish_position_signal(self, generator):
        """Test position signals for strong bearish bias (-2)."""
        # Strong bearish: Short only when price > 0.65
        bias_numeric = cp.array([-2, -2, -2, -2])
        price_position = cp.array([0.2, 0.65, 0.7, 0.9])
        
        signals = generator.compute_position_signals(bias_numeric, price_position)
        
        expected = cp.array([0, 0, -1, -1])  # No position, No position, Short, Short
        assert cp.array_equal(signals, expected)
    
    def test_mixed_bias_signals(self, generator):
        """Test position signals with mixed bias values."""
        bias_numeric = cp.array([2, 1, 0, -1, -2])
        price_position = cp.array([0.2, 0.15, 0.95, 0.85, 0.8])
        
        signals = generator.compute_position_signals(bias_numeric, price_position)
        
        expected = cp.array([1, 1, -1, -1, -1])  # Based on each bias logic
        assert cp.array_equal(signals, expected)
    
    def test_edge_cases_nan_handling(self, generator):
        """Test handling of NaN values."""
        bias_numeric = cp.array([1, cp.nan, 1, 1])
        price_position = cp.array([0.1, 0.1, cp.nan, 0.1])
        
        signals = generator.compute_position_signals(bias_numeric, price_position)
        
        # NaN inputs should result in 0 (no position)
        assert signals[1] == 0
        assert signals[2] == 0
        # Valid inputs should work normally
        assert signals[0] == 1
        assert signals[3] == 1
    
    def test_out_of_range_price_position(self, generator):
        """Test handling of out-of-range price positions."""
        bias_numeric = cp.array([1, 1, 1, 1])
        price_position = cp.array([-0.1, 0.5, 1.1, 2.0])
        
        signals = generator.compute_position_signals(bias_numeric, price_position)
        
        # Out of range should be treated as extremes
        assert signals[0] == 1  # Below 0 treated as very low
        assert signals[2] == -1  # Above 1 treated as very high
        assert signals[3] == -1  # Above 1 treated as very high
    
    def test_custom_thresholds(self, backend):
        """Test position generation with custom thresholds."""
        custom_config = ThresholdConfig(
            strong_bullish_buy=0.5,
            bullish_buy=0.3,
            bullish_sell=0.8
        )
        generator = GPUPositionGenerator(backend, custom_config)
        
        # Test with custom thresholds
        bias_numeric = cp.array([2, 2, 1, 1])
        price_position = cp.array([0.4, 0.5, 0.25, 0.85])
        
        signals = generator.compute_position_signals(bias_numeric, price_position)
        
        expected = cp.array([1, 0, 1, -1])  # Based on custom thresholds
        assert cp.array_equal(signals, expected)
    
    def test_large_array_performance(self, generator):
        """Test performance with large arrays."""
        # Create large arrays
        size = 100000
        bias_numeric = cp.random.randint(-2, 3, size=size)
        price_position = cp.random.uniform(0, 1, size=size)
        
        # Should complete without errors
        signals = generator.compute_position_signals(bias_numeric, price_position)
        
        # Verify output shape and values
        assert signals.shape == (size,)
        assert cp.all(cp.isin(signals, cp.array([-1, 0, 1])))
    
    def test_numpy_array_input(self, generator):
        """Test that numpy arrays are properly converted."""
        # Use numpy arrays as input
        bias_numeric = np.array([2, 1, 0, -1, -2])
        price_position = np.array([0.2, 0.15, 0.95, 0.85, 0.8])
        
        signals = generator.compute_position_signals(bias_numeric, price_position)
        
        # Should return CuPy array
        assert isinstance(signals, cp.ndarray)
        expected = cp.array([1, 1, -1, -1, -1])
        assert cp.array_equal(signals, expected)