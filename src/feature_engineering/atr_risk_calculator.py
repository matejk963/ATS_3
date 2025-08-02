"""
ATR-Based Risk Management Calculator

Provides ATR-based stop loss and take profit calculations as a core feature 
engineering component with CPU/GPU compatibility.
"""

from typing import Union, Tuple
import numpy as np
from .array_backend import ArrayBackend, ArrayLike


class ATRRiskCalculator:
    """
    ATR-based risk management calculator with backend compatibility.
    
    Calculates stop loss and take profit distances and levels based on Average True Range (ATR)
    values and user-defined risk ratios.
    
    Mathematical Formulas:
    - Stop Loss Distance = ATR × Stop Loss Ratio
    - Take Profit Distance = ATR × Stop Loss Ratio × SL/TP Ratio
    
    For Position Levels:
    - Long Position: Stop Loss = Entry - Distance, Take Profit = Entry + Distance
    - Short Position: Stop Loss = Entry + Distance, Take Profit = Entry - Distance
    """
    
    def __init__(self, backend: ArrayBackend):
        """
        Initialize ATR risk calculator with ArrayBackend for CPU/GPU compatibility.
        
        Args:
            backend: ArrayBackend instance for CPU/GPU array operations
        """
        self.backend = backend
    
    def compute_stop_loss_distance(self, atr: ArrayLike, stop_loss_ratio: float) -> ArrayLike:
        """
        Calculate stop loss distance = ATR × stop_loss_ratio
        
        Args:
            atr: Array of ATR values
            stop_loss_ratio: Multiplier for ATR to determine stop loss distance (0.3-0.8)
            
        Returns:
            Array of stop loss distances in price units
            
        Example:
            ATR = 2.5, stop_loss_ratio = 0.5 → stop_loss_distance = 1.25
        """
        atr_array = self.backend.asarray(atr)
        return self.backend.multiply(atr_array, stop_loss_ratio)
    
    def compute_take_profit_distance(self, atr: ArrayLike, stop_loss_ratio: float, 
                                   sl_tp_ratio: float) -> ArrayLike:
        """
        Calculate take profit distance = ATR × stop_loss_ratio × sl_tp_ratio
        
        Args:
            atr: Array of ATR values
            stop_loss_ratio: Multiplier for ATR to determine stop loss distance (0.3-0.8)
            sl_tp_ratio: Ratio of take profit to stop loss distance (1.0-2.2)
            
        Returns:
            Array of take profit distances in price units
            
        Example:
            ATR = 2.5, stop_loss_ratio = 0.5, sl_tp_ratio = 1.5 → take_profit_distance = 1.875
        """
        atr_array = self.backend.asarray(atr)
        # Calculate: atr * stop_loss_ratio * sl_tp_ratio
        stop_loss_distance = self.backend.multiply(atr_array, stop_loss_ratio)
        return self.backend.multiply(stop_loss_distance, sl_tp_ratio)
    
    def compute_risk_distances(self, atr: ArrayLike, stop_loss_ratio: float, 
                             sl_tp_ratio: float) -> Tuple[ArrayLike, ArrayLike]:
        """
        Compute both stop loss and take profit distances together for efficiency.
        
        Args:
            atr: Array of ATR values
            stop_loss_ratio: Multiplier for ATR to determine stop loss distance (0.3-0.8)
            sl_tp_ratio: Ratio of take profit to stop loss distance (1.0-2.2)
            
        Returns:
            Tuple of (stop_loss_distances, take_profit_distances)
        """
        atr_array = self.backend.asarray(atr)
        
        # Calculate stop loss distance
        stop_loss_distance = self.backend.multiply(atr_array, stop_loss_ratio)
        
        # Calculate take profit distance
        take_profit_distance = self.backend.multiply(stop_loss_distance, sl_tp_ratio)
        
        return stop_loss_distance, take_profit_distance
    
    def compute_risk_levels(self, entry_price: ArrayLike, atr: ArrayLike,
                          stop_loss_ratio: float, sl_tp_ratio: float,
                          position_type: str = 'long') -> Tuple[ArrayLike, ArrayLike]:
        """
        Compute actual stop loss and take profit price levels.
        
        Args:
            entry_price: Array of entry prices
            atr: Array of ATR values
            stop_loss_ratio: Multiplier for ATR to determine stop loss distance (0.3-0.8)
            sl_tp_ratio: Ratio of take profit to stop loss distance (1.0-2.2)
            position_type: 'long' or 'short' position type
            
        Returns:
            Tuple of (stop_loss_levels, take_profit_levels)
            
        Example:
            entry_price = 100.0, ATR = 2.0, stop_loss_ratio = 0.5, sl_tp_ratio = 1.5
            For long: stop_loss = 99.0, take_profit = 101.5
            For short: stop_loss = 101.0, take_profit = 98.5
        """
        if position_type not in ['long', 'short']:
            raise ValueError(f"position_type must be 'long' or 'short', got '{position_type}'")
        
        entry_array = self.backend.asarray(entry_price)
        
        # Get risk distances
        stop_loss_distance, take_profit_distance = self.compute_risk_distances(
            atr, stop_loss_ratio, sl_tp_ratio
        )
        
        if position_type == 'long':
            # Long position: Stop loss below entry, take profit above entry
            stop_loss_level = self.backend.subtract(entry_array, stop_loss_distance)
            take_profit_level = self.backend.add(entry_array, take_profit_distance)
        else:  # position_type == 'short'
            # Short position: Stop loss above entry, take profit below entry
            stop_loss_level = self.backend.add(entry_array, stop_loss_distance)
            take_profit_level = self.backend.subtract(entry_array, take_profit_distance)
        
        return stop_loss_level, take_profit_level
    
    def validate_risk_parameters(self, stop_loss_ratio: float, sl_tp_ratio: float) -> None:
        """
        Validate risk management parameters.
        
        Args:
            stop_loss_ratio: Should be positive (typically 0.3-0.8)
            sl_tp_ratio: Should be positive (typically 1.0-2.2)
            
        Raises:
            ValueError: If parameters are invalid
        """
        if stop_loss_ratio <= 0:
            raise ValueError(f"stop_loss_ratio must be positive, got {stop_loss_ratio}")
        
        if sl_tp_ratio <= 0:
            raise ValueError(f"sl_tp_ratio must be positive, got {sl_tp_ratio}")
        
        # Optional warnings for typical ranges
        if stop_loss_ratio > 1.0:
            import warnings
            warnings.warn(f"stop_loss_ratio {stop_loss_ratio} is unusually high (typical range: 0.3-0.8)")
        
        if sl_tp_ratio > 3.0:
            import warnings
            warnings.warn(f"sl_tp_ratio {sl_tp_ratio} is unusually high (typical range: 1.0-2.2)")