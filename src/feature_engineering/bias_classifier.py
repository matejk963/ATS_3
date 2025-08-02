"""
Phase 5: GPU-Accelerated Bias Classification System

This module implements the bias classification system that transforms normalized MACD
indicators into actionable market sentiment classifications using GPU acceleration.

Core Features:
- GPU-accelerated vectorized operations using CuPy
- Decision Logic Matrix implementation for bias determination
- Integration with Phase 3/4 ArrayBackend infrastructure
- Configurable threshold system for different market conditions

The system classifies market bias on a 5-class scale:
- Strong Bearish (-2): Very negative sentiment - only short positions
- Bearish (-1): Negative sentiment - conservative long, aggressive short
- Neutral (0): No clear bias - balanced approach
- Bullish (1): Positive sentiment - aggressive long, conservative short  
- Strong Bullish (2): Very positive sentiment - only long positions
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Union, Any
import logging

from .array_backend import ArrayBackend

logger = logging.getLogger(__name__)


@dataclass
class ThresholdConfig:
    """
    Configuration for bias classification thresholds.
    
    These thresholds determine the boundaries between Bearish/Neutral/Bullish
    classifications for both MACD line and MACD histogram components.
    
    Default values are calibrated based on extensive backtesting with normalized
    MACD indicators from Phase 4 feature engineering.
    """
    macd_line_lower: float = -0.1      # Below this = Bearish MACD
    macd_line_upper: float = 0.1       # Above this = Bullish MACD
    macd_histogram_lower: float = -0.05 # Below this = Bearish Histogram
    macd_histogram_upper: float = 0.05  # Above this = Bullish Histogram
    
    def __post_init__(self):
        """Validate configuration after initialization"""
        self.validate()
    
    def validate(self) -> bool:
        """
        Validate threshold configuration for logical consistency.
        
        Ensures:
        - Lower thresholds are less than upper thresholds
        - Thresholds create meaningful separation between classes
        
        Returns:
            bool: True if configuration is valid
            
        Raises:
            ValueError: If configuration is invalid
        """
        if self.macd_line_lower >= self.macd_line_upper:
            raise ValueError(
                f"macd_line_lower ({self.macd_line_lower}) must be less than "
                f"macd_line_upper ({self.macd_line_upper})"
            )
        
        if self.macd_histogram_lower >= self.macd_histogram_upper:
            raise ValueError(
                f"macd_histogram_lower ({self.macd_histogram_lower}) must be less than "
                f"macd_histogram_upper ({self.macd_histogram_upper})"
            )
        
        return True


class GPUBiasClassifier:
    """
    GPU-accelerated bias classification engine.
    
    Transforms normalized MACD indicators into market bias classifications using
    vectorized GPU operations and the Decision Logic Matrix.
    
    The classifier operates in three stages:
    1. Component Classification: Classify MACD line and histogram individually
    2. Decision Matrix Application: Combine components using lookup matrix
    3. Bias Assignment: Generate final bias numeric and string classifications
    """
    
    def __init__(self, 
                 array_backend: ArrayBackend,
                 thresholds: Optional[ThresholdConfig] = None):
        """
        Initialize GPU bias classifier.
        
        Args:
            array_backend: ArrayBackend instance for GPU operations
            thresholds: Threshold configuration (uses defaults if None)
        """
        self.array_backend = array_backend
        self.thresholds = thresholds or ThresholdConfig()
        
        # Validate threshold configuration
        self.thresholds.validate()
        
        # Get array namespace (CuPy for GPU operations)
        self.xp = array_backend.xp
        
        logger.info(f"🎯 [BIAS CLASSIFIER] Initialized with GPU acceleration")
        logger.info(f"📊 [THRESHOLDS] MACD: [{self.thresholds.macd_line_lower:.3f}, {self.thresholds.macd_line_upper:.3f}]")
        logger.info(f"📈 [THRESHOLDS] Histogram: [{self.thresholds.macd_histogram_lower:.3f}, {self.thresholds.macd_histogram_upper:.3f}]")
    
    def classify_components_gpu(self, 
                               macd_norm: Union[np.ndarray, Any], 
                               macd_hist_norm: Union[np.ndarray, Any]) -> Tuple[Any, Any]:
        """
        Classify MACD line and histogram components individually using GPU vectorization.
        
        Args:
            macd_norm: Normalized MACD line values (GPU array)
            macd_hist_norm: Normalized MACD histogram values (GPU array)
            
        Returns:
            Tuple of (macd_class, hist_class) arrays with classifications:
            - -1: Bearish
            -  0: Neutral  
            -  1: Bullish
        """
        # Ensure arrays are on GPU
        if not hasattr(macd_norm, '__array_namespace__') or macd_norm.__array_namespace__() != self.xp:
            macd_norm = self.xp.asarray(macd_norm, dtype=self.xp.float32)
        if not hasattr(macd_hist_norm, '__array_namespace__') or macd_hist_norm.__array_namespace__() != self.xp:
            macd_hist_norm = self.xp.asarray(macd_hist_norm, dtype=self.xp.float32)
        
        # Validate input shapes
        if macd_norm.shape != macd_hist_norm.shape:
            raise ValueError(f"Input arrays must have the same shape. "
                           f"macd_norm: {macd_norm.shape}, macd_hist_norm: {macd_hist_norm.shape}")
        
        # Handle NaN values by replacing with 0 (Neutral classification)
        macd_norm = self.xp.nan_to_num(macd_norm, nan=0.0)
        macd_hist_norm = self.xp.nan_to_num(macd_hist_norm, nan=0.0)
        
        # Vectorized MACD line classification
        macd_class = self.xp.zeros_like(macd_norm, dtype=self.xp.int8)
        macd_class[macd_norm < self.thresholds.macd_line_lower] = -1  # Bearish
        macd_class[macd_norm > self.thresholds.macd_line_upper] = 1   # Bullish
        # Neutral (0) is already set by zeros_like
        
        # Vectorized MACD histogram classification  
        hist_class = self.xp.zeros_like(macd_hist_norm, dtype=self.xp.int8)
        hist_class[macd_hist_norm < self.thresholds.macd_histogram_lower] = -1  # Bearish
        hist_class[macd_hist_norm > self.thresholds.macd_histogram_upper] = 1   # Bullish
        # Neutral (0) is already set by zeros_like
        
        return macd_class, hist_class
    
    def apply_decision_matrix_gpu(self, 
                                 macd_class: Any, 
                                 hist_class: Any) -> Any:
        """
        Apply Decision Logic Matrix to combine MACD and histogram classifications.
        
        Decision Matrix (Legacy Compatible):
        | MACD / MACD Hist | Bearish(-1) | Neutral(0) | Bullish(1) |
        |------------------|-------------|------------|------------|
        | Bearish(-1)      | -2          | -1         | 0          |
        | Neutral(0)       | -1          | 0          | 1          |
        | Bullish(1)       | 0           | 1          | 2          |
        
        Args:
            macd_class: MACD line classifications (-1, 0, 1)
            hist_class: MACD histogram classifications (-1, 0, 1)
            
        Returns:
            Final bias classifications (-2, -1, 0, 1, 2)
        """
        # Initialize with Neutral (0)
        bias_numeric = self.xp.zeros_like(macd_class, dtype=self.xp.int8)
        
        # Apply Decision Logic Matrix using vectorized boolean indexing
        # This maintains EXACT legacy logic while using GPU acceleration
        
        # Strong Bearish (-2): Bearish MACD + Bearish Histogram
        bias_numeric[(macd_class == -1) & (hist_class == -1)] = -2
        
        # Bearish (-1): 
        # - Bearish MACD + Neutral Histogram
        # - Neutral MACD + Bearish Histogram
        bias_numeric[(macd_class == -1) & (hist_class == 0)] = -1
        bias_numeric[(macd_class == 0) & (hist_class == -1)] = -1
        
        # Neutral (0): 
        # - Bearish MACD + Bullish Histogram
        # - Neutral MACD + Neutral Histogram  
        # - Bullish MACD + Bearish Histogram
        bias_numeric[(macd_class == -1) & (hist_class == 1)] = 0
        bias_numeric[(macd_class == 0) & (hist_class == 0)] = 0
        bias_numeric[(macd_class == 1) & (hist_class == -1)] = 0
        
        # Bullish (1):
        # - Neutral MACD + Bullish Histogram
        # - Bullish MACD + Neutral Histogram
        bias_numeric[(macd_class == 0) & (hist_class == 1)] = 1
        bias_numeric[(macd_class == 1) & (hist_class == 0)] = 1
        
        # Strong Bullish (2): Bullish MACD + Bullish Histogram
        bias_numeric[(macd_class == 1) & (hist_class == 1)] = 2
        
        return bias_numeric
    
    def compute_bias_classification(self, 
                                   macd_norm: Union[np.ndarray, Any], 
                                   macd_hist_norm: Union[np.ndarray, Any]) -> Any:
        """
        Complete bias classification pipeline using GPU acceleration.
        
        This is the main entry point that orchestrates the full classification process:
        1. Component classification of MACD line and histogram
        2. Decision matrix application to determine final bias
        3. Return GPU-accelerated bias classifications
        
        Args:
            macd_norm: Normalized MACD line values from Phase 4 feature engineering
            macd_hist_norm: Normalized MACD histogram values from Phase 4
            
        Returns:
            GPU array with bias classifications (-2, -1, 0, 1, 2)
        """
        # Step 1: Classify individual components
        macd_class, hist_class = self.classify_components_gpu(macd_norm, macd_hist_norm)
        
        # Step 2: Apply decision matrix to get final bias
        bias_numeric = self.apply_decision_matrix_gpu(macd_class, hist_class)
        
        return bias_numeric
    
    def integrate_with_pipeline(self, 
                               feature_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Integration interface for unified pipeline.
        
        Takes feature data dictionary from Phase 4 and adds bias classification results.
        
        Args:
            feature_data: Dictionary containing 'macd_norm' and 'macd_hist_norm' GPU arrays
            
        Returns:
            Enhanced dictionary with bias classification results added
        """
        # Extract required features
        macd_norm = feature_data['macd_norm']
        macd_hist_norm = feature_data['macd_hist_norm']
        
        # Compute component classifications
        macd_class, hist_class = self.classify_components_gpu(macd_norm, macd_hist_norm)
        
        # Compute final bias classification
        bias_numeric = self.compute_bias_classification(macd_norm, macd_hist_norm)
        
        # Add results to feature data
        feature_data['macd_line_class_numeric'] = macd_class
        feature_data['macd_histogram_class_numeric'] = hist_class
        feature_data['bias_numeric'] = bias_numeric
        
        return feature_data


def create_gpu_bias_classifier(array_backend: ArrayBackend, 
                              **threshold_kwargs) -> GPUBiasClassifier:
    """
    Factory function to create GPU bias classifier with custom thresholds.
    
    Args:
        array_backend: ArrayBackend instance for GPU operations
        **threshold_kwargs: Keyword arguments for ThresholdConfig
        
    Returns:
        Configured GPUBiasClassifier instance
    """
    if threshold_kwargs:
        thresholds = ThresholdConfig(**threshold_kwargs)
    else:
        thresholds = None
    
    return GPUBiasClassifier(array_backend, thresholds)


def validate_gpu_bias_output(bias_arrays: Dict[str, Any]) -> bool:
    """
    Validate bias classification output arrays.
    
    Args:
        bias_arrays: Dictionary containing bias classification results
        
    Returns:
        bool: True if output is valid, False otherwise
    """
    required_keys = ['bias_numeric']
    
    # Check required keys exist
    for key in required_keys:
        if key not in bias_arrays:
            logger.error(f"Missing required key: {key}")
            return False
    
    # Validate bias_numeric range
    bias_numeric = bias_arrays['bias_numeric']
    if hasattr(bias_numeric, 'min') and hasattr(bias_numeric, 'max'):
        min_val = float(bias_numeric.min())
        max_val = float(bias_numeric.max())
        
        if min_val < -2 or max_val > 2:
            logger.error(f"bias_numeric values out of range [-2, 2]: [{min_val}, {max_val}]")
            return False
    
    return True


def get_bias_distribution_stats_gpu(bias_numeric: Any) -> Dict[str, float]:
    """
    Compute bias distribution statistics from GPU array.
    
    Args:
        bias_numeric: GPU array with bias classifications
        
    Returns:
        Dictionary with distribution statistics
    """
    # Convert to CPU for counting if needed
    if hasattr(bias_numeric, '__array_namespace__'):
        # Assume CuPy array, convert to numpy
        import cupy as cp
        if isinstance(bias_numeric, cp.ndarray):
            bias_cpu = cp.asnumpy(bias_numeric)
        else:
            bias_cpu = bias_numeric
    else:
        bias_cpu = bias_numeric
    
    total_count = len(bias_cpu)
    
    if total_count == 0:
        return {'total_count': 0}
    
    # Count each classification
    strong_bearish_count = np.sum(bias_cpu == -2)
    bearish_count = np.sum(bias_cpu == -1)
    neutral_count = np.sum(bias_cpu == 0)
    bullish_count = np.sum(bias_cpu == 1)
    strong_bullish_count = np.sum(bias_cpu == 2)
    
    # Calculate percentages
    stats = {
        'strong_bearish_pct': (strong_bearish_count / total_count) * 100,
        'bearish_pct': (bearish_count / total_count) * 100,
        'neutral_pct': (neutral_count / total_count) * 100,
        'bullish_pct': (bullish_count / total_count) * 100,
        'strong_bullish_pct': (strong_bullish_count / total_count) * 100,
        'total_count': total_count
    }
    
    return stats


def _numeric_to_bias_labels(bias_numeric: Union[np.ndarray, Any]) -> Union[np.ndarray, pd.Series]:
    """
    Convert numeric bias classifications to string labels.
    
    Args:
        bias_numeric: Array of numeric bias values (-2 to 2)
        
    Returns:
        Array of string labels
    """
    # Define mapping
    label_map = {
        -2: 'Strong Bearish',
        -1: 'Bearish', 
        0: 'Neutral',
        1: 'Bullish',
        2: 'Strong Bullish'
    }
    
    # Convert to numpy if needed
    if hasattr(bias_numeric, '__array_namespace__'):
        import cupy as cp
        if isinstance(bias_numeric, cp.ndarray):
            bias_array = cp.asnumpy(bias_numeric)
        else:
            bias_array = bias_numeric
    else:
        bias_array = np.asarray(bias_numeric)
    
    # Map numeric values to labels
    labels = np.array([label_map.get(val, 'Unknown') for val in bias_array])
    
    return labels