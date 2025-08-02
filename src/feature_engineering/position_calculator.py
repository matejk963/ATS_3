"""
Position Calculator - EXACT ATS_2 Legacy Implementation
Implements complete_memory_solution.py lines 159-160 price position calculation

EXACT LEGACY FORMULAS:
- price_range = swing_high - swing_low (line 159)
- price_position = (price - swing_low) / price_range (line 160)
"""

import cupy as cp


class PositionCalculator:
    """GPU-accelerated position calculation matching EXACT ATS_2 legacy logic"""
    
    def calculate_legacy_position(self, current_prices, swing_highs, swing_lows):
        """
        GPU-vectorized EXACT legacy price position calculation
        
        EXACT LEGACY LOGIC - Two-step process:
        1. price_range = swing_high - swing_low
        2. price_position = (price - swing_low) / price_range
        
        Args:
            current_prices: Current price array (temp['price'])
            swing_highs: Array of swing high values (temp['swing_high'])
            swing_lows: Array of swing low values (temp['swing_low'])
            
        Returns:
            tuple: (price_range, price_position) arrays matching legacy output
        """
        # Step 1: EXACT legacy formula (line 159)
        # temp['price_range'] = temp['swing_high'] - temp['swing_low']
        price_range = swing_highs - swing_lows
        
        # Handle division by zero (when swing_high == swing_low)
        price_range_safe = cp.where(price_range == 0, cp.finfo(cp.float32).eps, price_range)
        
        # Step 2: EXACT legacy formula (line 160)  
        # temp['price_position'] = (temp['price'] - temp['swing_low']) / temp['price_range']
        price_position = (current_prices - swing_lows) / price_range_safe
        
        # Ensure results are float32 for consistency
        price_range = price_range.astype(cp.float32)
        price_position = price_position.astype(cp.float32)
        
        return price_range, price_position