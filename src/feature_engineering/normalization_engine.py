"""
Normalization Engine - EXACT ATS_2 Legacy Normalization
Implements complete_memory_solution.py lines 157-158 normalization formulas

EXACT LEGACY FORMULAS:
- macd_norm = macd / atr (line 157)
- macd_hist_norm = hist / atr (line 158)
"""

import cupy as cp


class NormalizationEngine:
    """GPU-accelerated normalization matching EXACT ATS_2 legacy logic"""
    
    def legacy_normalize_macd_by_atr(self, macd_values, atr_values):
        """
        GPU-vectorized EXACT legacy MACD normalization
        
        EXACT LEGACY: macd_norm = macd / atr
        Source: complete_memory_solution.py line 157
        
        Purpose: Make MACD values comparable across different volatility periods
        
        Returns:
            ndarray: macd_norm values (exact legacy naming)
        """
        # Handle division by zero with small epsilon to avoid inf
        atr_safe = cp.where(atr_values == 0, cp.finfo(cp.float32).eps, atr_values)
        
        # EXACT legacy formula: macd_norm = macd / atr
        macd_norm = macd_values / atr_safe
        
        return macd_norm.astype(cp.float32)
        
    def legacy_normalize_histogram_by_atr(self, macd_histogram, atr_values):
        """
        GPU-vectorized EXACT legacy MACD histogram normalization
        
        EXACT LEGACY: macd_hist_norm = hist / atr  
        Source: complete_memory_solution.py line 158
        
        Returns:
            ndarray: macd_hist_norm values (exact legacy naming)
        """
        # Handle division by zero with small epsilon to avoid inf
        atr_safe = cp.where(atr_values == 0, cp.finfo(cp.float32).eps, atr_values)
        
        # EXACT legacy formula: macd_hist_norm = hist / atr
        macd_hist_norm = macd_histogram / atr_safe
        
        return macd_hist_norm.astype(cp.float32)