"""
GPU Feature Calculator - EXACT ATS_2 Legacy Implementation
Implements complete_memory_solution.py lines 157-160 feature engineering

EXACT LEGACY FORMULAS:
- temp['macd_norm'] = temp['macd'] / temp['atr']           # Line 157
- temp['macd_hist_norm'] = temp['hist'] / temp['atr']      # Line 158  
- temp['price_range'] = temp['swing_high'] - temp['swing_low']  # Line 159
- temp['price_position'] = (temp['price'] - temp['swing_low']) / temp['price_range']  # Line 160
"""

import cupy as cp
from .normalization_engine import NormalizationEngine
from .position_calculator import PositionCalculator


class GPUFeatureCalculator:
    """GPU-accelerated feature engineering matching EXACT ATS_2 legacy logic"""
    
    def __init__(self, dtype='float32'):
        self.dtype = getattr(cp, dtype)
        self.normalization_engine = NormalizationEngine()
        self.position_calculator = PositionCalculator()
        
    def compute_all_features(self, indicators_dict, current_prices):
        """
        Compute all trading features from Phase 3 indicators
        EXACT LEGACY IMPLEMENTATION from complete_memory_solution.py lines 157-160
        
        Args:
            indicators_dict: Output from Phase 3 unified pipeline
            current_prices: Current price array (OHLC close prices)
            
        Returns:
            dict: Features with EXACT legacy names and formulas
        """
        # Extract indicators
        macd_line = indicators_dict['macd_line']
        macd_histogram = indicators_dict['macd_histogram']
        atr_values = indicators_dict['atr']
        swing_highs = indicators_dict['swing_highs']
        swing_lows = indicators_dict['swing_lows']
        
        # EXACT LEGACY FORMULAS (complete_memory_solution.py lines 157-160):
        
        # Line 157: temp['macd_norm'] = temp['macd'] / temp['atr']
        macd_norm = self.legacy_normalize_macd(macd_line, atr_values)
        
        # Line 158: temp['macd_hist_norm'] = temp['hist'] / temp['atr']  
        macd_hist_norm = self.legacy_normalize_histogram(macd_histogram, atr_values)
        
        # Lines 159-160: Two-step price position calculation
        price_range, price_position = self.legacy_calculate_price_position(
            current_prices, swing_highs, swing_lows
        )
        
        return {
            'macd_norm': macd_norm,
            'macd_hist_norm': macd_hist_norm,
            'price_range': price_range,
            'price_position': price_position
        }
        
    def legacy_normalize_macd(self, macd_line, atr_values):
        """EXACT: macd_norm = macd / atr"""
        return self.normalization_engine.legacy_normalize_macd_by_atr(macd_line, atr_values)
        
    def legacy_normalize_histogram(self, macd_histogram, atr_values):
        """EXACT: macd_hist_norm = hist / atr"""
        return self.normalization_engine.legacy_normalize_histogram_by_atr(macd_histogram, atr_values)
        
    def legacy_calculate_price_position(self, prices, swing_highs, swing_lows):
        """
        EXACT LEGACY: price_position = (price - swing_low) / price_range
        where price_range = swing_high - swing_low
        """
        return self.position_calculator.calculate_legacy_position(prices, swing_highs, swing_lows)