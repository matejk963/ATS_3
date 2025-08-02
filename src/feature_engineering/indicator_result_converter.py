"""IndicatorResultConverter for converting technical indicator array outputs to DataFrames

This module provides specialized converters for different types of technical indicator
results, making it easy to convert array outputs back to pandas DataFrames with
proper column naming and metadata preservation.
"""

from typing import Dict, Union, Optional
import numpy as np
import pandas as pd
from .array_types import ArrayLike
from .gpu_converter import DataFrameMetadata


class IndicatorResultConverter:
    """Converter for technical indicator array results to DataFrames
    
    Provides specialized methods for different indicator types:
    - MACD: Multi-component results (macd, signal, histogram)
    - ATR: Single array results  
    - Candles: OHLC dictionary results
    - Swings: Boolean array results
    - Generic: Any dictionary of arrays
    """
    
    def __init__(self):
        """Initialize the converter"""
        pass
    
    def macd_to_dataframe(self, macd_result: Dict[str, ArrayLike], 
                         metadata: DataFrameMetadata,
                         prefix: str = "") -> pd.DataFrame:
        """Convert MACD result to DataFrame
        
        Args:
            macd_result: Dict with 'macd', 'signal', 'histogram' arrays
            metadata: Original DataFrame metadata for index/structure
            prefix: Optional prefix for column names (e.g., '15min_')
            
        Returns:
            DataFrame with MACD columns
        """
        # Validate input
        required_keys = ['macd', 'signal', 'histogram']
        if not all(key in macd_result for key in required_keys):
            raise ValueError(f"MACD result must contain keys: {required_keys}")
        
        # Convert arrays to CPU if needed
        cpu_arrays = self._ensure_cpu_arrays(macd_result)
        
        # Validate array lengths match
        lengths = [len(arr) for arr in cpu_arrays.values()]
        if not all(length == lengths[0] for length in lengths):
            raise ValueError("All MACD arrays must have the same length")
        
        # Validate metadata length matches
        if len(metadata.index) != lengths[0]:
            raise ValueError(f"Metadata length ({len(metadata.index)}) doesn't match array length ({lengths[0]})")
        
        # Create column names with prefix
        columns = [f"{prefix}macd", f"{prefix}signal", f"{prefix}histogram"]
        
        # Create DataFrame
        df_data = {
            columns[0]: cpu_arrays['macd'],
            columns[1]: cpu_arrays['signal'],
            columns[2]: cpu_arrays['histogram']
        }
        
        df = pd.DataFrame(df_data, index=metadata.index)
        return df
    
    def atr_to_dataframe(self, atr_result: ArrayLike,
                        metadata: DataFrameMetadata,
                        prefix: str = "") -> pd.DataFrame:
        """Convert ATR result to DataFrame
        
        Args:
            atr_result: Array of ATR values
            metadata: Original DataFrame metadata for index/structure  
            prefix: Optional prefix for column name (e.g., '14d_')
            
        Returns:
            DataFrame with single ATR column
        """
        # Convert to CPU if needed
        cpu_array = self._ensure_cpu_array(atr_result)
        
        # Validate metadata length matches
        if len(metadata.index) != len(cpu_array):
            raise ValueError(f"Metadata length ({len(metadata.index)}) doesn't match array length ({len(cpu_array)})")
        
        # Create column name with prefix
        column_name = f"{prefix}atr"
        
        # Create DataFrame
        df = pd.DataFrame({column_name: cpu_array}, index=metadata.index)
        return df
    
    def candles_to_dataframe(self, candle_result: Dict[str, ArrayLike],
                            metadata: DataFrameMetadata,
                            prefix: str = "") -> pd.DataFrame:
        """Convert candle result to DataFrame
        
        Args:
            candle_result: Dict with 'open', 'high', 'low', 'close' arrays
            metadata: DataFrame metadata for candle timeframe
            prefix: Optional prefix for column names (e.g., '5min_')
            
        Returns:
            DataFrame with OHLC columns
        """
        # Validate input
        required_keys = ['open', 'high', 'low', 'close']
        if not all(key in candle_result for key in required_keys):
            raise ValueError(f"Candle result must contain keys: {required_keys}")
        
        # Convert arrays to CPU if needed
        cpu_arrays = self._ensure_cpu_arrays(candle_result)
        
        # Validate array lengths match
        lengths = [len(arr) for arr in cpu_arrays.values()]
        if not all(length == lengths[0] for length in lengths):
            raise ValueError("All candle arrays must have the same length")
        
        # Validate metadata length matches
        if len(metadata.index) != lengths[0]:
            raise ValueError(f"Metadata length ({len(metadata.index)}) doesn't match array length ({lengths[0]})")
        
        # Create column names with prefix
        columns = [f"{prefix}open", f"{prefix}high", f"{prefix}low", f"{prefix}close"]
        
        # Create DataFrame
        df_data = {
            columns[0]: cpu_arrays['open'],
            columns[1]: cpu_arrays['high'],
            columns[2]: cpu_arrays['low'],
            columns[3]: cpu_arrays['close']
        }
        
        df = pd.DataFrame(df_data, index=metadata.index)
        return df
    
    def swings_to_dataframe(self, swing_result: Dict[str, ArrayLike],
                           metadata: DataFrameMetadata,
                           prefix: str = "") -> pd.DataFrame:
        """Convert swing points result to DataFrame
        
        Args:
            swing_result: Dict with 'swing_highs', 'swing_lows' boolean arrays
            metadata: Original DataFrame metadata for index/structure
            prefix: Optional prefix for column names (e.g., '20p_')
            
        Returns:
            DataFrame with boolean swing columns
        """
        # Validate input
        required_keys = ['swing_highs', 'swing_lows']
        if not all(key in swing_result for key in required_keys):
            raise ValueError(f"Swing result must contain keys: {required_keys}")
        
        # Convert arrays to CPU if needed
        cpu_arrays = self._ensure_cpu_arrays(swing_result)
        
        # Validate array lengths match
        lengths = [len(arr) for arr in cpu_arrays.values()]
        if not all(length == lengths[0] for length in lengths):
            raise ValueError("All swing arrays must have the same length")
        
        # Validate metadata length matches
        if len(metadata.index) != lengths[0]:
            raise ValueError(f"Metadata length ({len(metadata.index)}) doesn't match array length ({lengths[0]})")
        
        # Create column names with prefix
        columns = [f"{prefix}swing_highs", f"{prefix}swing_lows"]
        
        # Create DataFrame with explicit boolean dtype
        df_data = {
            columns[0]: cpu_arrays['swing_highs'].astype(bool),
            columns[1]: cpu_arrays['swing_lows'].astype(bool)
        }
        
        df = pd.DataFrame(df_data, index=metadata.index)
        return df
    
    def arrays_to_dataframe(self, arrays: Dict[str, ArrayLike],
                           metadata: DataFrameMetadata,
                           prefix: str = "") -> pd.DataFrame:
        """Convert generic dictionary of arrays to DataFrame
        
        Args:
            arrays: Dictionary mapping column names to arrays
            metadata: Original DataFrame metadata for index/structure
            prefix: Optional prefix for all column names
            
        Returns:
            DataFrame with all arrays as columns
        """
        if not arrays:
            # Return empty DataFrame with correct index
            return pd.DataFrame(index=metadata.index)
        
        # Convert arrays to CPU if needed
        cpu_arrays = self._ensure_cpu_arrays(arrays)
        
        # Validate array lengths match
        lengths = [len(arr) for arr in cpu_arrays.values()]
        if not all(length == lengths[0] for length in lengths):
            raise ValueError("All arrays must have the same length")
        
        # Validate metadata length matches (if arrays not empty)
        if lengths[0] > 0 and len(metadata.index) != lengths[0]:
            raise ValueError(f"Metadata length ({len(metadata.index)}) doesn't match array length ({lengths[0]})")
        
        # Create column names with prefix
        df_data = {}
        for key, array in cpu_arrays.items():
            column_name = f"{prefix}{key}"
            df_data[column_name] = array
        
        # Create DataFrame
        df = pd.DataFrame(df_data, index=metadata.index)
        return df
    
    def _ensure_cpu_arrays(self, arrays: Dict[str, ArrayLike]) -> Dict[str, np.ndarray]:
        """Convert dictionary of arrays to CPU arrays
        
        Args:
            arrays: Dictionary of ArrayLike objects (NumPy or CuPy)
            
        Returns:
            Dictionary of NumPy arrays
        """
        cpu_arrays = {}
        for key, arr in arrays.items():
            cpu_arrays[key] = self._ensure_cpu_array(arr)
        return cpu_arrays
    
    def _ensure_cpu_array(self, arr: ArrayLike) -> np.ndarray:
        """Convert single array to CPU array
        
        Args:
            arr: ArrayLike object (NumPy or CuPy)
            
        Returns:
            NumPy array
        """
        if hasattr(arr, 'get'):  # CuPy array
            return arr.get()
        return np.asarray(arr)