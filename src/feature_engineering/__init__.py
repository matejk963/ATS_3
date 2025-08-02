"""
Phase 4 Feature Engineering Pipeline
GPU-Accelerated feature engineering extending Phase 3 technical indicators

Implements EXACT ATS_2 legacy feature engineering formulas:
- macd_norm = macd / atr
- macd_hist_norm = hist / atr  
- price_range = swing_high - swing_low
- price_position = (price - swing_low) / price_range
"""

from .gpu_feature_calculator import GPUFeatureCalculator
from .normalization_engine import NormalizationEngine
from .position_calculator import PositionCalculator

__all__ = [
    'GPUFeatureCalculator',
    'NormalizationEngine', 
    'PositionCalculator'
]