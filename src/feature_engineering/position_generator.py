"""GPU-accelerated position signal generator for trading strategies.

This module combines market bias classifications with price position analysis
to generate actionable trading signals using GPU acceleration.
"""

from dataclasses import dataclass
from typing import Optional, Union
import numpy as np
import cupy as cp

from .array_backend import ArrayBackend


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


class GPUPositionGenerator:
    """GPU-accelerated position signal generator.
    
    Combines bias classifications (-2 to +2) with price position metrics
    to generate trading signals: Long (1), Short (-1), or No Position (0).
    """
    
    def __init__(self, array_backend: ArrayBackend, 
                 threshold_config: Optional[ThresholdConfig] = None):
        """Initialize position generator with GPU backend.
        
        Args:
            array_backend: GPU array management system
            threshold_config: Configurable thresholds per bias class
        """
        self.backend = array_backend
        self.threshold_config = threshold_config or ThresholdConfig()
    
    def compute_position_signals(self, 
                               bias_numeric: Union[np.ndarray, cp.ndarray],
                               price_position: Union[np.ndarray, cp.ndarray],
                               threshold_config: Optional[ThresholdConfig] = None) -> cp.ndarray:
        """Generate position signals using vectorized GPU operations.
        
        Args:
            bias_numeric: Market sentiment classification (-2 to +2)
            price_position: Normalized price position (0 to 1)
            threshold_config: Optional custom thresholds
            
        Returns:
            Position signals as GPU array (-1, 0, 1)
        """
        # Convert inputs to GPU arrays
        bias_gpu = self.backend.asarray(bias_numeric)
        price_gpu = self.backend.asarray(price_position)
        
        # Use provided config or instance default
        config = threshold_config or self.threshold_config
        
        # Initialize position signals to 0 (no position)
        signals = cp.zeros_like(bias_gpu, dtype=cp.int32)
        
        # Handle NaN values - set to no position
        nan_mask = cp.isnan(bias_gpu) | cp.isnan(price_gpu)
        
        # Create masks for each bias class
        strong_bullish_mask = (bias_gpu == 2) & ~nan_mask
        bullish_mask = (bias_gpu == 1) & ~nan_mask
        neutral_mask = (bias_gpu == 0) & ~nan_mask
        bearish_mask = (bias_gpu == -1) & ~nan_mask
        strong_bearish_mask = (bias_gpu == -2) & ~nan_mask
        
        # Apply decision logic for each bias class
        
        # Strong Bullish (2): Long only when price < 0.35
        signals = cp.where(
            strong_bullish_mask & (price_gpu < config.strong_bullish_buy),
            1,  # Long
            signals
        )
        
        # Bullish (1): Long when price < 0.2, Short when price > 0.9
        signals = cp.where(
            bullish_mask & (price_gpu < config.bullish_buy),
            1,  # Long
            signals
        )
        signals = cp.where(
            bullish_mask & (price_gpu > config.bullish_sell),
            -1,  # Short
            signals
        )
        
        # Neutral (0): Long when price < 0.2, Short when price > 0.9
        signals = cp.where(
            neutral_mask & (price_gpu < config.neutral_buy),
            1,  # Long
            signals
        )
        signals = cp.where(
            neutral_mask & (price_gpu > config.neutral_sell),
            -1,  # Short
            signals
        )
        
        # Bearish (-1): Long when price < 0.1, Short when price > 0.8
        signals = cp.where(
            bearish_mask & (price_gpu < config.bearish_buy),
            1,  # Long
            signals
        )
        signals = cp.where(
            bearish_mask & (price_gpu > config.bearish_sell),
            -1,  # Short
            signals
        )
        
        # Strong Bearish (-2): Short only when price > 0.65
        signals = cp.where(
            strong_bearish_mask & (price_gpu > config.strong_bearish_sell),
            -1,  # Short
            signals
        )
        
        return signals