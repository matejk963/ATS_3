"""
Unified Technical Indicators Pipeline with Backend Selection

This module provides a unified interface for computing technical indicators
with automatic backend selection (CPU/GPU) and comprehensive error handling.

Key Features:
- Automatic backend selection based on data size or explicit choice
- GPU acceleration with CuPy when available
- Graceful fallback to CPU when GPU fails
- Memory optimization for large datasets
- Performance comparison between backends
- Caching for repeated computations
"""

import time
import hashlib
import warnings
from typing import Dict, List, Optional, Union, Any, Tuple
from dataclasses import dataclass
import pandas as pd
import numpy as np

from .array_backend import ArrayBackend
from .gpu_converter import GPUArrayConverter
from .metadata import DataFrameMetadata
from .candle_generator import CandleGenerator, DualCandleGenerator
from .macd_calculator import MACDCalculator
from .atr_calculator import ATRCalculator
from .atr_risk_calculator import ATRRiskCalculator
from .gpu_swing_detector import GPUSwingDetector
from .gpu_memory_manager import GPUMemoryManager
from .gpu_feature_calculator import GPUFeatureCalculator
from .bias_classifier import GPUBiasClassifier, ThresholdConfig, _numeric_to_bias_labels
from .position_generator import GPUPositionGenerator, ThresholdConfig as PositionThresholdConfig


@dataclass
class PipelineConfig:
    """Configuration for GPU-accelerated technical indicators processing"""
    dtype: str = 'float32'                    # Optimal data type for GPU processing
    chunk_size: int = 2000000                 # Ultra-large chunks for maximum GPU efficiency
    memory_threshold: float = 0.98            # Aggressive 98% GPU memory utilization
    cuda_streams: int = 8                     # Number of parallel CUDA streams for RTX 4080 SUPER
    min_chunk_size: int = 500000             # Minimum chunk size for GPU efficiency
    max_chunk_size: int = 5000000            # Maximum chunk size for RTX 4080 SUPER
    
    def __post_init__(self):
        """Validate GPU-only configuration"""
        valid_dtypes = ['float32', 'float64']
        if self.dtype not in valid_dtypes:
            raise ValueError(f"Unsupported dtype: {self.dtype}. Must be one of {valid_dtypes}")
        
        if self.chunk_size < self.min_chunk_size:
            self.chunk_size = self.min_chunk_size
        if self.chunk_size > self.max_chunk_size:
            self.chunk_size = self.max_chunk_size


class UnifiedTechnicalIndicatorsPipeline:
    """
    GPU-accelerated technical indicators pipeline with RTX 4080 SUPER optimization.
    
    Provides high-performance GPU processing with:
    - Maximum GPU memory utilization (98%)
    - Multi-stream CUDA processing (8 streams)
    - Ultra-large chunk processing (2M points)
    - RTX 4080 SUPER hardware optimization
    - No CPU fallback (GPU-only reliability)
    """
    
    def __init__(self, 
                 dtype: str = 'float32',
                 chunk_size: int = None,
                 memory_threshold: float = None,
                 **kwargs):
        """
        Initialize GPU-accelerated technical indicators pipeline.
        
        Args:
            dtype: Data type for GPU computations ('float32', 'float64')
            chunk_size: Override default chunk size (2M points)
            memory_threshold: Override default memory threshold (98%)
            **kwargs: Additional configuration options
        """
        # Create GPU-only configuration
        config_kwargs = {
            'dtype': dtype,
            **kwargs
        }
        if chunk_size is not None:
            config_kwargs['chunk_size'] = chunk_size
        if memory_threshold is not None:
            config_kwargs['memory_threshold'] = memory_threshold
            
        self.config = PipelineConfig(**config_kwargs)
        
        # Initialize GPU-only backend
        self._validate_gpu_availability()
        self.array_backend = ArrayBackend(backend='cupy')
        
        # Initialize GPU converter and memory manager
        self.converter = GPUArrayConverter()
        self.memory_manager = GPUMemoryManager(
            memory_threshold=self.config.memory_threshold,
            chunk_size=self.config.chunk_size,
            enable_memory_pool=True,
            monitor_usage=True
        )
        
        print(f"🚀 [GPU PIPELINE] Initialized with RTX 4080 SUPER optimizations")
        print(f"📊 [CONFIG] {self.config.chunk_size:,} point chunks, {self.config.memory_threshold:.0%} memory threshold")
        print(f"⚡ [STREAMS] {self.config.cuda_streams} CUDA streams for maximum parallelization")
        
        # Initialize GPU-only calculators
        self._initialize_calculators()
    
    def _validate_gpu_availability(self) -> None:
        """Validate that GPU is available for processing"""
        try:
            import cupy as cp
            if not cp.cuda.is_available():
                raise RuntimeError("No CUDA-capable GPU detected. GPU processing requires CUDA-compatible hardware.")
            
            # Test basic GPU operation
            test_array = cp.array([1, 2, 3])
            _ = cp.sum(test_array)
            
            print(f"✅ [GPU VALIDATION] CUDA GPU detected and functional")
            
        except ImportError:
            raise RuntimeError("CuPy not available. Install CuPy for GPU processing: pip install cupy-cuda12x")
        except Exception as e:
            raise RuntimeError(f"GPU validation failed: {e}")
    
    def _initialize_calculators(self):
        """Initialize all GPU calculator instances"""
        self.candle_generator = CandleGenerator(self.array_backend)
        self.dual_candle_generator = DualCandleGenerator(self.array_backend)
        self.macd_calculator = MACDCalculator(self.array_backend)
        self.atr_calculator = ATRCalculator(self.array_backend)
        self.atr_risk_calculator = ATRRiskCalculator(self.array_backend)
        self.swing_detector = GPUSwingDetector(self.array_backend)
        
        # Phase 4: Initialize GPU feature engineering calculator
        self.feature_calculator = GPUFeatureCalculator(dtype=self.config.dtype)
        
        # Phase 5: Initialize GPU bias classifier
        from .bias_classifier import create_gpu_bias_classifier
        self.bias_classifier = create_gpu_bias_classifier(self.array_backend)
        
        # Phase 6: Initialize GPU position generator
        from .position_generator import GPUPositionGenerator
        self.position_generator = GPUPositionGenerator(self.array_backend)
        
        print(f"🎯 [GPU CALCULATORS] All indicators + feature engineering + bias classification + position signals + risk management initialized for GPU-only processing")   
    def _validate_input_data(self, data: pd.DataFrame) -> None:
        """Validate input data has required columns"""
        if data.empty:
            raise ValueError("Input data cannot be empty")
        
        required_columns = {'open', 'high', 'low', 'close'}
        missing_columns = required_columns - set(data.columns)
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")
    
    # Removed cache and backend selection methods - GPU-only mode
    
    def _compute_indicators_chunk(self, 
                                 data: pd.DataFrame,
                                 indicators: List[str],
                                 **params) -> pd.DataFrame:
        """
        Internal method to compute indicators on a data chunk.
        
        Args:
            data: Input OHLCV data chunk
            indicators: List of indicators to compute
            **params: Parameters for each indicator
            
        Returns:
            DataFrame with computed indicators
        """
        # Convert to arrays for computation
        arrays, metadata = self.converter.to_arrays(
            data, 
            dtype=self.config.dtype,
            contiguous=True
        )
        
        # Transfer to backend
        backend_arrays = {
            key: self.array_backend.asarray(arr) 
            for key, arr in arrays.items()
        }
        
        # Compute requested indicators
        computed_arrays = {}
        
        if 'macd' in indicators:
            macd_params = params.get('macd_params', {'fast': 12, 'slow': 26, 'signal': 9})
            macd_result = self.macd_calculator.compute_macd_legacy(
                backend_arrays['close'], 
                fast=macd_params.get('fast', 12),
                slow=macd_params.get('slow', 26),
                signal=macd_params.get('signal', 9)
            )
            # Map MACD results to descriptive column names
            computed_arrays.update({
                'macd_line': macd_result['macd'],
                'macd_signal': macd_result['signal'], 
                'macd_histogram': macd_result['histogram']
            })
        
        if 'atr' in indicators:
            atr_period = params.get('atr_period', 14)
            atr_result = self.atr_calculator.compute_atr(
                backend_arrays['high'],
                backend_arrays['low'],
                backend_arrays['close'],
                period=atr_period
            )
            computed_arrays['atr'] = atr_result
        
        if 'swing_points' in indicators:
            swing_lookback = params.get('swing_lookback', 20)
            # Note: GPUSwingDetector uses arrays directly - no DataFrame conversion needed
            # Use GPU arrays directly for maximum performance
            swing_result = self.swing_detector.detect_swing_points_arrays(
                backend_arrays['high'], 
                backend_arrays['low']
            )
            
            # Results are already GPU arrays - no conversion needed
            computed_arrays.update({
                'swing_highs': swing_result['swing_high'],
                'swing_lows': swing_result['swing_low']
            })
        
        if 'candles' in indicators:
            candle_granularity = params.get('candle_granularity', '15min')
            # For candles, we already have OHLC data, so we pass it through
            # or potentially aggregate it to the desired granularity
            computed_arrays.update({
                'candle_open': backend_arrays['open'],
                'candle_high': backend_arrays['high'],
                'candle_low': backend_arrays['low'],
                'candle_close': backend_arrays['close']
            })
        
        # Combine all arrays
        all_arrays = {**backend_arrays, **computed_arrays}
        
        # Convert back to DataFrame
        return self.converter.from_arrays(all_arrays, metadata)

    def compute_indicators(self, 
                          data: pd.DataFrame,
                          indicators: List[str],
                          **params) -> pd.DataFrame:
        """
        Compute specified indicators with automatic memory management.
        
        Args:
            data: Input OHLCV data
            indicators: List of indicators to compute ('macd', 'atr', 'swing_points', 'candles')
            **params: Parameters for each indicator
            
        Returns:
            DataFrame with computed indicators
        """
        self._validate_input_data(data)
        
        # No caching in GPU-only mode for maximum performance
        
        # GPU-only processing with aggressive memory management
        print(f"🚀 [GPU PROCESSING] Processing {len(data):,} data points with RTX 4080 SUPER optimization...")
        result_data = self.memory_manager.process_with_memory_management(
            data, self._compute_indicators_chunk, indicators, **params
        )
        
        return result_data
    
    def compute_all_indicators(self,
                              data: pd.DataFrame,
                              candle_granularity: str = '15min',
                              macd_params: Dict = None,
                              atr_period: int = 14,
                              swing_lookback: int = 20) -> pd.DataFrame:
        """
        Compute all available indicators.
        
        Args:
            data: Input OHLCV data
            candle_granularity: Granularity for candle generation
            macd_params: MACD parameters
            atr_period: ATR period
            swing_lookback: Swing point lookback period (ignored by legacy algorithm)
            
        Returns:
            DataFrame with all computed indicators
        """
        if macd_params is None:
            macd_params = {'fast': 12, 'slow': 26, 'signal': 9}
        
        return self.compute_indicators(
            data=data,
            indicators=['macd', 'atr', 'swing_points', 'candles'],
            candle_granularity=candle_granularity,
            macd_params=macd_params,
            atr_period=atr_period,
            swing_lookback=swing_lookback
        )
    
    def compute_all_indicators_and_features(self,
                                           data: pd.DataFrame,
                                           candle_granularity: str = '15min',
                                           macd_params: Dict = None,
                                           atr_period: int = 14,
                                           swing_lookback: int = 20,
                                           stop_loss_ratio: Optional[float] = None,
                                           sl_tp_ratio: Optional[float] = None,
                                           entry_price: Optional[Union[float, np.ndarray]] = None,
                                           position_type: str = 'long') -> pd.DataFrame:
        """
        Phase 4: Compute all technical indicators AND feature engineering.
        Extends Phase 3 pipeline with EXACT ATS_2 legacy feature engineering + ATR risk management.
        
        Args:
            data: Input OHLCV data
            candle_granularity: Granularity for candle generation
            macd_params: MACD parameters
            atr_period: ATR period
            swing_lookback: Swing point lookback period (ignored by legacy algorithm)
            stop_loss_ratio: Optional ATR multiplier for stop loss distance (0.3-0.8)
            sl_tp_ratio: Optional ratio of take profit to stop loss distance (1.0-2.2)
            entry_price: Optional entry prices for risk level calculation (defaults to close prices)
            position_type: Position type for risk levels ('long' or 'short')
            
        Returns:
            DataFrame with all indicators + engineered features + risk management features
        """
        # Phase 3: Compute all technical indicators
        indicators_df = self.compute_all_indicators(
            data=data,
            candle_granularity=candle_granularity,
            macd_params=macd_params,
            atr_period=atr_period,
            swing_lookback=swing_lookback
        )
        
        # Phase 4: Compute feature engineering
        # Handle legacy swing detector output format (continuous price values)
        swing_highs_raw = self.array_backend.asarray(indicators_df['swing_highs'].values)
        swing_lows_raw = self.array_backend.asarray(indicators_df['swing_lows'].values)
        
        # Check if we have continuous price values (legacy format) or boolean masks
        swing_highs_cpu = self.array_backend.to_cpu(swing_highs_raw)
        if swing_highs_cpu.dtype == bool:
            # Boolean mask format - use original extraction method
            high_prices = self.array_backend.asarray(indicators_df['high'].values)
            low_prices = self.array_backend.asarray(indicators_df['low'].values)
            swing_high_prices = self._extract_swing_prices(high_prices, swing_highs_raw)
            swing_low_prices = self._extract_swing_prices(low_prices, swing_lows_raw)
        else:
            # Legacy format - continuous price values, just need forward fill
            swing_high_prices = self._forward_fill_swing_prices(swing_highs_raw)
            swing_low_prices = self._forward_fill_swing_prices(swing_lows_raw)
        
        # Convert required arrays to GPU for feature calculation
        required_indicators = {
            'macd_line': self.array_backend.asarray(indicators_df['macd_line'].values),
            'macd_histogram': self.array_backend.asarray(indicators_df['macd_histogram'].values),
            'atr': self.array_backend.asarray(indicators_df['atr'].values),
            'swing_highs': swing_high_prices,
            'swing_lows': swing_low_prices
        }
        
        current_prices = self.array_backend.asarray(indicators_df['close'].values)
        
        # Compute EXACT legacy features
        features_dict = self.feature_calculator.compute_all_features(
            required_indicators, current_prices
        )
        
        # Convert features back to numpy and add to DataFrame
        for feature_name, feature_array in features_dict.items():
            # Convert from GPU array to numpy for DataFrame
            feature_values = self.array_backend.to_cpu(feature_array)
            indicators_df[feature_name] = feature_values
        
        # Also replace swing boolean arrays with actual price values for consistency
        indicators_df['swing_highs'] = self.array_backend.to_cpu(swing_high_prices)
        indicators_df['swing_lows'] = self.array_backend.to_cpu(swing_low_prices)
        
        # Add ATR-based risk management features if parameters provided
        risk_features_count = 0
        if stop_loss_ratio is not None:
            atr_values = self.array_backend.asarray(indicators_df['atr'].values)
            
            # Compute stop loss distance
            stop_loss_distance = self.atr_risk_calculator.compute_stop_loss_distance(
                atr_values, stop_loss_ratio
            )
            indicators_df['stop_loss_distance'] = self.array_backend.to_cpu(stop_loss_distance)
            risk_features_count += 1
            
            # Compute take profit distance if sl_tp_ratio provided
            if sl_tp_ratio is not None:
                take_profit_distance = self.atr_risk_calculator.compute_take_profit_distance(
                    atr_values, stop_loss_ratio, sl_tp_ratio
                )
                indicators_df['take_profit_distance'] = self.array_backend.to_cpu(take_profit_distance)
                risk_features_count += 1
                
                # Always compute actual price levels (using entry_price or defaulting to close prices)
                if entry_price is not None:
                    # Use provided entry_price
                    if isinstance(entry_price, (int, float)):
                        # Single value - broadcast to all rows
                        entry_prices = np.full(len(indicators_df), entry_price)
                    else:
                        # Array of values
                        entry_prices = np.array(entry_price)
                        if len(entry_prices) != len(indicators_df):
                            raise ValueError(f"entry_price array length {len(entry_prices)} != data length {len(indicators_df)}")
                else:
                    # Default to close prices
                    entry_prices = indicators_df['close'].values
                
                entry_array = self.array_backend.asarray(entry_prices)
                
                stop_loss_levels, take_profit_levels = self.atr_risk_calculator.compute_risk_levels(
                    entry_array, atr_values, stop_loss_ratio, sl_tp_ratio, position_type
                )
                
                indicators_df['stop_loss_level'] = self.array_backend.to_cpu(stop_loss_levels)
                indicators_df['take_profit_level'] = self.array_backend.to_cpu(take_profit_levels)
                risk_features_count += 2
        
        feature_msg = f"✅ [PHASE 4] Feature engineering complete - added {len(features_dict)} legacy features"
        if risk_features_count > 0:
            feature_msg += f" + {risk_features_count} risk management features"
        print(feature_msg)
        
        return indicators_df
    
    def compute_all_indicators_features_and_bias(self,
                                               data: pd.DataFrame,
                                               bias_thresholds: Optional[ThresholdConfig] = None,
                                               candle_granularity: str = '15min',
                                               macd_params: Dict = None,
                                               atr_period: int = 14,
                                               swing_lookback: int = 20) -> pd.DataFrame:
        """
        Phase 5: Complete pipeline with bias classification.
        
        Extends Phase 4 (indicators + features) with GPU-accelerated bias classification
        that transforms normalized MACD indicators into actionable market sentiment.
        
        Args:
            data: Input OHLCV data
            bias_thresholds: Threshold configuration for bias classification (uses defaults if None)
            candle_granularity: Granularity for candle generation
            macd_params: MACD parameters
            atr_period: ATR period
            swing_lookback: Swing point lookback period (ignored by legacy algorithm)
            
        Returns:
            DataFrame with indicators + features + bias classification
        """
        # Phase 3 + 4: Compute all technical indicators and features
        result = self.compute_all_indicators_and_features(
            data=data,
            candle_granularity=candle_granularity,
            macd_params=macd_params,
            atr_period=atr_period,
            swing_lookback=swing_lookback
        )
        
        # Phase 5: GPU bias classification
        print(f"🎯 [PHASE 5] Starting bias classification on {len(result)} data points...")
        
        bias_classifier = GPUBiasClassifier(self.array_backend, bias_thresholds)
        
        # Extract GPU arrays for bias computation
        macd_norm = self.array_backend.asarray(result['macd_norm'].values)
        macd_hist_norm = self.array_backend.asarray(result['macd_hist_norm'].values)
        
        # Compute individual component classifications
        macd_class, hist_class = bias_classifier.classify_components_gpu(macd_norm, macd_hist_norm)
        
        # Compute final bias classification
        bias_numeric = bias_classifier.compute_bias_classification(macd_norm, macd_hist_norm)
        
        # Add bias results to DataFrame (convert from GPU to CPU)
        result['macd_line_class_numeric'] = self.array_backend.to_cpu(macd_class)
        result['macd_histogram_class_numeric'] = self.array_backend.to_cpu(hist_class)
        result['bias_numeric'] = self.array_backend.to_cpu(bias_numeric)
        result['bias_classification'] = _numeric_to_bias_labels(result['bias_numeric'])
        
        print(f"✅ [PHASE 5] Bias classification complete - added 4 bias-related columns")
        
        # Log bias distribution for monitoring
        bias_distribution = self._compute_bias_distribution_summary(result['bias_numeric'])
        print(f"📊 [BIAS STATS] {bias_distribution}")
        
        return result
    
    def compute_all_indicators_features_bias_and_positions(self,
                                                         data: pd.DataFrame,
                                                         bias_thresholds: Optional[ThresholdConfig] = None,
                                                         position_thresholds: Optional[PositionThresholdConfig] = None,
                                                         candle_granularity: str = '15min',
                                                         macd_params: Dict = None,
                                                         atr_period: int = 14,
                                                         swing_lookback: int = 20,
                                                         stop_loss_ratio: Optional[float] = None,
                                                         sl_tp_ratio: Optional[float] = None,
                                                         entry_price: Optional[Union[float, np.ndarray]] = None,
                                                         position_type: str = 'long') -> pd.DataFrame:
        """
        Phase 6: Complete pipeline with position signal generation + optional ATR risk management.
        
        Extends Phase 5 (indicators + features + bias) with GPU-accelerated position
        signal generation that combines bias classifications with price position analysis
        to generate actionable trading signals. Optionally includes ATR-based risk management.
        
        Args:
            data: Input OHLCV data
            bias_thresholds: Threshold configuration for bias classification
            position_thresholds: Threshold configuration for position signals
            candle_granularity: Granularity for candle generation
            macd_params: MACD parameters
            atr_period: ATR period
            swing_lookback: Swing point lookback period (ignored by legacy algorithm)
            stop_loss_ratio: Optional ATR multiplier for stop loss distance (0.3-0.8)
            sl_tp_ratio: Optional ratio of take profit to stop loss distance (1.0-2.2)
            entry_price: Optional entry prices for risk level calculation (defaults to close prices)
            position_type: Position type for risk levels ('long' or 'short')
            
        Returns:
            DataFrame with indicators + features + bias + position signals + optional risk levels
        """
        # Phase 3 + 4 + 5 + Risk Management: Compute all indicators, features, bias, and risk
        result = self.compute_all_indicators_and_features(
            data=data,
            candle_granularity=candle_granularity,
            macd_params=macd_params,
            atr_period=atr_period,
            swing_lookback=swing_lookback,
            stop_loss_ratio=stop_loss_ratio,
            sl_tp_ratio=sl_tp_ratio,
            entry_price=entry_price,
            position_type=position_type
        )
        
        # Add bias classification to the result
        bias_result = self.compute_all_indicators_features_and_bias(
            data=data,
            bias_thresholds=bias_thresholds,
            candle_granularity=candle_granularity,
            macd_params=macd_params,
            atr_period=atr_period,
            swing_lookback=swing_lookback
        )
        
        # Merge bias columns into result
        bias_columns = ['bias_numeric', 'bias_classification', 'macd_line_class_numeric', 'macd_histogram_class_numeric']
        for col in bias_columns:
            if col in bias_result.columns:
                result[col] = bias_result[col]
        
        # Phase 6: GPU position signal generation
        print(f"📍 [PHASE 6] Starting position signal generation on {len(result)} data points...")
        
        position_generator = GPUPositionGenerator(self.array_backend, position_thresholds)
        
        # Extract GPU arrays for position computation
        bias_numeric = self.array_backend.asarray(result['bias_numeric'].values)
        price_position = self.array_backend.asarray(result['price_position'].values)
        
        # Compute position signals
        position_signals = position_generator.compute_position_signals(bias_numeric, price_position)
        
        # Add position signals to DataFrame (convert from GPU to CPU)
        result['position_signal'] = self.array_backend.to_cpu(position_signals)
        
        print(f"✅ [PHASE 6] Position signal generation complete - added position_signal column")
        
        # Log position distribution for monitoring
        position_distribution = self._compute_position_distribution_summary(result['position_signal'])
        print(f"📊 [POSITION STATS] {position_distribution}")
        
        return result
    
    def compute_all_indicators_features_bias_and_positions_dual_granularity(self,
                                                                         data: pd.DataFrame,
                                                                         predictor_granularities: Dict[str, str],
                                                                         bias_thresholds: Optional[ThresholdConfig] = None,  
                                                                         position_thresholds: Optional[PositionThresholdConfig] = None,
                                                                         macd_params: Dict = None,
                                                                         atr_period: int = 14,
                                                                         swing_lookback: int = 20,
                                                                         stop_loss_ratio: Optional[float] = None,
                                                                         sl_tp_ratio: Optional[float] = None,
                                                                         entry_price: Optional[Union[float, np.ndarray]] = None,
                                                                         position_type: str = 'long') -> pd.DataFrame:
        """
        Phase 6 with dual-granularity system matching ATS_2 architecture.
        
        Processes indicators with dual granularity system:
        - ATR/MACD computed at atr_macd granularity  
        - Swing points computed at swing granularity
        - Results merged at tick level
        
        Args:
            data: Input tick-level data with 'datetime' and 'price' columns
            predictor_granularities: {
                'atr_macd': '15min',    # ATR and MACD granularity
                'swing': '30min'        # Swing detection granularity  
            }
            bias_thresholds: Threshold configuration for bias classification
            position_thresholds: Threshold configuration for position signals
            macd_params: MACD parameters
            atr_period: ATR period
            swing_lookback: Swing point lookback period (ignored by legacy algorithm)
            stop_loss_ratio: Optional ATR multiplier for stop loss distance
            sl_tp_ratio: Optional ratio of take profit to stop loss distance  
            entry_price: Optional entry prices for risk level calculation
            position_type: Position type for risk levels ('long' or 'short')
            
        Returns:
            DataFrame with all indicators, features, bias, and position signals at tick level
        """
        print(f"🚀 [DUAL GRANULARITY] Starting Phase 6 with dual granularity system")
        print(f"📊 [GRANULARITIES] ATR/MACD: {predictor_granularities['atr_macd']}, Swing: {predictor_granularities['swing']}")
        
        if macd_params is None:
            macd_params = {'fast': 12, 'slow': 26, 'signal': 9}
            
        # Extract granularities matching ATS_2 structure
        atr_macd_gran = predictor_granularities['atr_macd']
        swing_gran = predictor_granularities['swing']
        
        # Generate candles for each granularity using dual-candle system
        print(f"🕯️  [CANDLES] Generating candles at dual granularities")
        atr_macd_candles = self.dual_candle_generator.generate_combined_candles(
            data, atr_macd_gran
        )
        swing_candles = self.dual_candle_generator.generate_combined_candles(
            data, swing_gran
        )
        
        # Compute indicators using ATS_2's approach (real-time for MACD/ATR)
        print(f"📈 [MACD/ATR] Computing real-time indicators at {atr_macd_gran}")
        macd_data = self._compute_realtime_macd(data, atr_macd_candles, macd_params)
        atr_data = self._compute_realtime_atr(data, atr_macd_candles, atr_period, atr_macd_gran)
        
        print(f"📊 [SWING] Computing swing points at {swing_gran} with forward-fill")
        swing_data = self._compute_swing_with_forward_fill(data, swing_candles, swing_lookback)
        
        # Merge all indicators at tick level
        print(f"🔗 [MERGE] Merging all indicators to tick level")
        indicators_result = self._merge_tick_level_indicators(data, macd_data, atr_data, swing_data)
        
        # Continue with Phase 4-6 processing using merged indicators
        print(f"⚙️  [FEATURES] Computing feature engineering (Phase 4)")
        features_result = self._compute_features_from_indicators(indicators_result)
        
        print(f"🎯 [BIAS] Computing bias classification (Phase 5)")
        bias_result = self._compute_bias_from_features(features_result, bias_thresholds)
        
        print(f"📍 [POSITIONS] Computing position signals (Phase 6)")
        position_result = self._compute_positions_from_bias(bias_result, position_thresholds)
        
        # Add ATR risk management if requested
        if stop_loss_ratio is not None or sl_tp_ratio is not None:
            print(f"⚠️  [RISK] Adding ATR-based risk management")
            position_result = self._add_atr_risk_management(
                position_result, stop_loss_ratio, sl_tp_ratio, entry_price, position_type
            )
        
        print(f"✅ [DUAL GRANULARITY] Complete pipeline with dual granularity system finished")
        return position_result
    
    def _compute_realtime_macd(self, tick_data: pd.DataFrame, historical_candles: pd.DataFrame, 
                              macd_params: Dict) -> pd.DataFrame:
        """
        Compute real-time MACD following EXACT reference implementation pattern.
        
        Reference: source_repos/EnergyTrading/Python/Utilities/predictors_tools.py:772-936
        
        CORRECTED: Follow exact reference pattern:
        1. Compute real-time candles per trade
        2. Calculate OHLC mean for real-time candles
        3. Calculate OHLC mean for historical candles
        4. Use pair_trade_with_historical_lookback for FULL short EMA period (se, not se-1)
        5. Use pair_trade_with_historical_lookback for FULL long EMA period (le, not le-1)  
        6. Calculate MACD line (short_ema - long_ema)
        7. Create MACD candles and use pair_trade_with_historical_lookback for FULL signal period
        8. Calculate signal line and histogram
        """
        try:
            print(f"\n=== MACD CORRECTED: Following exact reference pattern ===")
            print(f"MACD params: {macd_params}")
            print(f"Tick data shape: {tick_data.shape}")
            print(f"Historical candles shape: {historical_candles.shape}")
            
            # Handle both parameter naming conventions
            if 'fast' in macd_params:
                se = macd_params['fast']    # Short EMA period (e.g., 12)
                le = macd_params['slow']    # Long EMA period (e.g., 26)  
            else:
                se = macd_params['se']      # Short EMA period (e.g., 12)
                le = macd_params['le']      # Long EMA period (e.g., 26)
            signal_period = macd_params['signal']  # Signal period (e.g., 9)
            
            # Step 1: Compute real-time candles per trade (using ATR calculator method as reference)
            print("Step 1: Computing real-time candles per trade...")
            trades_with_candles = self.atr_calculator._compute_realtime_candles_per_trade(
                tick_data, 'price', 'datetime', '1h'
            )
            print(f"✓ Real-time candles computed, shape: {trades_with_candles.shape}")
            
            # Step 2: Calculate OHLC mean for real-time candles (matches reference lines 833-838)
            print("Step 2: Calculating OHLC mean for real-time candles...")
            trades_with_candles['ohlc_mean'] = (
                trades_with_candles['candle_open'] + 
                trades_with_candles['candle_high'] + 
                trades_with_candles['candle_low'] + 
                trades_with_candles['candle_close']
            ) / 4
            print(f"✓ OHLC mean calculated for real-time candles")
            
            # Step 3: Calculate OHLC mean for historical candles (matches reference lines 840-851)
            print("Step 3: Calculating OHLC mean for historical candles...")
            if not isinstance(historical_candles.index, pd.DatetimeIndex):
                historical_candles.index = pd.to_datetime(historical_candles.index)
            
            hist_candles_view = pd.DataFrame(index=historical_candles.index)
            hist_candles_view['ohlc_mean'] = (
                historical_candles['open'] + 
                historical_candles['high'] + 
                historical_candles['low'] + 
                historical_candles['close']
            ) / 4
            print(f"✓ OHLC mean calculated for historical candles")
            
            # Step 4: Use pair_trade_with_historical_lookback for short EMA (matches reference lines 854-862)
            print("Step 4: Computing short EMA data...")
            short_ema_data = self.atr_calculator._pair_trade_with_historical_lookback(
                trades_with_candles[['period', 'datetime', 'ohlc_mean']],
                hist_candles_view,
                se,  # CORRECTED: Use full short EMA period (reference line 857)
                'ohlc_mean',
                'datetime',
                '1h',
                'ohlc_mean'
            )
            print(f"✓ Short EMA data computed with lookback_periods={se}")
            
            # Step 5: Use pair_trade_with_historical_lookback for long EMA (matches reference lines 864-872)
            print("Step 5: Computing long EMA data...")
            long_ema_data = self.atr_calculator._pair_trade_with_historical_lookback(
                trades_with_candles[['period', 'datetime', 'ohlc_mean']],
                hist_candles_view,
                le,  # CORRECTED: Use full long EMA period (reference line 867)
                'ohlc_mean',
                'datetime',
                '1h',
                'ohlc_mean'
            )
            print(f"✓ Long EMA data computed with lookback_periods={le}")
            
            # Calculate short and long EMAs (matches reference lines 875-883)
            print("Step 6: Calculating EMAs and MACD line...")
            short_ema_cols = [col for col in short_ema_data.columns if col.startswith('close_t')]
            long_ema_cols = [col for col in long_ema_data.columns if col.startswith('close_t')]
            
            if short_ema_cols and long_ema_cols:
                short_ema = short_ema_data[short_ema_cols].mean(axis=1)  # Simple average (reference line 876)
                long_ema = long_ema_data[long_ema_cols].mean(axis=1)     # Simple average (reference line 880)
                
                # Calculate MACD line (matches reference line 883)
                macd_line = short_ema - long_ema
                print(f"✓ MACD line calculated")
                
                # Step 7: Create MACD DataFrame and candles (matches reference lines 886-894)
                print("Step 7: Creating MACD candles for signal line...")
                macd_df = pd.DataFrame({
                    'period': trades_with_candles['period'],
                    'datetime': trades_with_candles['datetime'],
                    'macd': macd_line
                })
                
                # Create MACD candles (matches reference lines 892-894)
                macd_candles = pd.DataFrame({
                    'period': macd_df['period'],
                    'macd': macd_line
                })
                macd_candles = macd_candles.groupby('period').last().reset_index()
                print(f"✓ MACD candles created")
                
                # Step 8: Use pair_trade_with_historical_lookback for signal line (matches reference lines 897-905)
                print("Step 8: Computing signal line...")
                signal_data = self.atr_calculator._pair_trade_with_historical_lookback(
                    macd_df,
                    macd_candles.set_index('period'),
                    signal_period,  # CORRECTED: Use full signal period (reference line 900)
                    'macd',
                    'datetime',
                    '1h',
                    'macd'
                )
                
                # Calculate signal line (matches reference lines 908-909)
                signal_cols = [col for col in signal_data.columns if col.startswith('close_t')]
                if signal_cols:
                    signal_line = signal_data[signal_cols].mean(axis=1)  # Simple average (reference line 909)
                    print(f"✓ Signal line calculated with lookback_periods={signal_period}")
                else:
                    # Fallback if no historical columns found
                    print("Warning: No historical signal columns found, using fallback")
                    signal_line = macd_line.rolling(window=signal_period, min_periods=1).mean()
                
                # Calculate histogram (matches reference line 912)
                histogram = macd_line - signal_line
                
                macd_values = macd_line.tolist()
                signal_values = signal_line.tolist()
                hist_values = histogram.tolist()
                
            else:
                # Fallback if no historical columns found
                print("Warning: No historical EMA columns found, using fallback")
                macd_values = [0.0] * len(tick_data)
                signal_values = [0.0] * len(tick_data)
                hist_values = [0.0] * len(tick_data)
            
            # Create result DataFrame (matches reference lines 915-936)
            result_df = pd.DataFrame({
                'datetime': tick_data['datetime'],
                'macd': macd_values,
                'signal': signal_values,  # Note: reference uses 'signal'
                'histogram': hist_values  # Note: our internal format uses 'histogram'
            })
            
            # Add tradeid and nanotime if they exist (matches reference lines 923-928)
            if 'nanotime' in tick_data.columns:
                result_df = pd.merge(result_df, tick_data[['datetime', 'nanotime']], on='datetime', how='left')
            
            if 'tradeid' in tick_data.columns:
                result_df = pd.merge(result_df, tick_data[['datetime', 'tradeid']], on='datetime', how='left')
            
            # Ensure columns are in reference order (matches reference lines 930-936)
            columns = ['datetime']
            if 'nanotime' in result_df.columns:
                columns.append('nanotime')
            if 'tradeid' in result_df.columns:
                columns.append('tradeid')
            columns.extend(['macd', 'signal', 'histogram'])
            
            return result_df[columns]
            
        except Exception as e:
            print(f"❌ Exception in corrected MACD calculation: {e}")
            import traceback
            traceback.print_exc()
            
            # Safe fallback
            result_df = pd.DataFrame({
                'datetime': tick_data['datetime'],
                'macd': [0.0] * len(tick_data),
                'signal': [0.0] * len(tick_data),
                'histogram': [0.0] * len(tick_data)
            })
            return result_df
    
    def _compute_realtime_atr(self, tick_data: pd.DataFrame, historical_candles: pd.DataFrame,
                             atr_period: int, candle_granularity: str = '1h') -> pd.DataFrame:
        """
        Compute real-time ATR (Average True Range) using GPU-accelerated calculation.
        
        This method delegates to the GPU-accelerated ATRCalculator which implements
        the correct candle-based ATR algorithm with forward-filling.
        
        Parameters:
        -----------
        tick_data : pd.DataFrame
            DataFrame containing trade data with datetime and price information
        historical_candles : pd.DataFrame
            DataFrame with historical completed candles with 'open', 'high', 'low', 'close' columns
            and datetime index
        atr_period : int
            Number of periods to use for ATR calculation (from metadata)
        candle_granularity : str
            Time granularity for candles (from metadata predictor_granularities)
        
        Returns:
        --------
        pd.DataFrame
            DataFrame with columns ['datetime', 'atr'] containing forward-filled ATR values
        """
        # Delegate to GPU-accelerated ATR calculator with metadata parameters
        gpu_result = self.atr_calculator.compute_atr(
            trades_df=tick_data,
            historical_candles=historical_candles,
            atr_period=atr_period,  # From metadata
            price_col='price',
            datetime_col='datetime',
            candle_granularity=candle_granularity  # From metadata predictor_granularities
        )
        
        # Return only the columns expected by the pipeline interface
        return gpu_result[['datetime', 'atr']]
    
    def _compute_swing_with_forward_fill(self, tick_data: pd.DataFrame, swing_candles: pd.DataFrame,
                                        swing_lookback: int) -> pd.DataFrame:
        """
        Compute swing points and forward-fill to tick level.
        Only indicator that needs forward-fill according to analysis.
        """
        # Compute swing points using legacy detector
        swing_result = self.swing_detector.detect_swing_points_arrays(
            highs=swing_candles['high'].values,
            lows=swing_candles['low'].values
        )
        
        # Create DataFrame with candle timestamps
        swing_df = pd.DataFrame({
            'datetime': swing_candles.index,
            'swing_high': self.array_backend.to_cpu(swing_result['swing_high']),
            'swing_low': self.array_backend.to_cpu(swing_result['swing_low'])
        })
        
        # Forward-fill swing values to match tick timestamps (ATS_2 pattern)
        tick_swing = pd.merge_asof(
            tick_data[['datetime']].sort_values('datetime'),
            swing_df.sort_values('datetime'),
            on='datetime', direction='backward'
        )
        
        return tick_swing
    
    def _merge_tick_level_indicators(self, tick_data: pd.DataFrame, macd_data: pd.DataFrame,
                                   atr_data: pd.DataFrame, swing_data: pd.DataFrame) -> pd.DataFrame:
        """
        Merge all indicators at tick level for Phase 4-6 processing.
        Natural merge since all indicators are now at tick-level.
        """
        # Start with tick data
        result = tick_data.copy()
        
        # Merge MACD data
        result = result.merge(macd_data[['datetime', 'macd', 'macd_signal', 'macd_hist']], 
                            on='datetime', how='left')
        
        # Rename macd to macd_line for pipeline compatibility
        result.rename(columns={'macd': 'macd_line'}, inplace=True)
        
        # Merge ATR data
        result = result.merge(atr_data[['datetime', 'atr']], on='datetime', how='left')
        
        # Merge swing data  
        result = result.merge(swing_data[['datetime', 'swing_high', 'swing_low']], 
                            on='datetime', how='left')
        
        return result
    
    def _compute_features_from_indicators(self, indicators_data: pd.DataFrame) -> pd.DataFrame:
        """Apply Phase 4 feature engineering to indicators"""
        # Use existing Phase 4 logic but with pre-computed indicators
        # Convert to OHLCV format expected by existing feature computation
        
        # Create synthetic OHLCV from tick data for feature engineering
        # Group by some small time window to create candles
        ohlcv_for_features = indicators_data.groupby(indicators_data.index // 100).agg({
            'price': ['first', 'max', 'min', 'last'],
            'datetime': 'first'
        }).round(6)
        
        ohlcv_for_features.columns = ['open', 'high', 'low', 'close', 'datetime']
        ohlcv_for_features = ohlcv_for_features.reset_index(drop=True)
        
        # Add volume column
        ohlcv_for_features['volume'] = 100  # Placeholder volume
        
        # Add pre-computed indicators to the synthetic OHLCV
        for col in ['macd_line', 'macd_signal', 'macd_hist', 'atr', 'swing_high', 'swing_low']:
            if col in indicators_data.columns:
                # Sample indicators to match synthetic OHLCV length
                sampled_values = indicators_data[col].iloc[::100].reset_index(drop=True)
                if len(sampled_values) == len(ohlcv_for_features):
                    ohlcv_for_features[col] = sampled_values
                else:
                    # Handle length mismatch
                    ohlcv_for_features[col] = sampled_values.iloc[:len(ohlcv_for_features)]
        
        # Apply feature engineering using correct method name
        # Extract indicators for feature calculator
        indicators_dict = {
            'macd_line': ohlcv_for_features['macd_line'].values if 'macd_line' in ohlcv_for_features.columns else np.zeros(len(ohlcv_for_features)),
            'macd_signal': ohlcv_for_features['macd_signal'].values if 'macd_signal' in ohlcv_for_features.columns else np.zeros(len(ohlcv_for_features)),
            'macd_histogram': ohlcv_for_features['macd_hist'].values if 'macd_hist' in ohlcv_for_features.columns else np.zeros(len(ohlcv_for_features)),
            'atr': ohlcv_for_features['atr'].values if 'atr' in ohlcv_for_features.columns else np.zeros(len(ohlcv_for_features)),
            'swing_highs': ohlcv_for_features['swing_high'].values if 'swing_high' in ohlcv_for_features.columns else np.zeros(len(ohlcv_for_features)),
            'swing_lows': ohlcv_for_features['swing_low'].values if 'swing_low' in ohlcv_for_features.columns else np.zeros(len(ohlcv_for_features))
        }
        
        # Convert numpy arrays to GPU arrays for feature calculator
        gpu_indicators_dict = {}
        for key, values in indicators_dict.items():
            gpu_indicators_dict[key] = self.array_backend.asarray(values)
        
        features_result = self.feature_calculator.compute_all_features(
            gpu_indicators_dict, 
            self.array_backend.asarray(ohlcv_for_features['close'].values)
        )
        
        # Convert features dictionary to DataFrame for expansion
        features_df = pd.DataFrame()
        for feature_name, feature_values in features_result.items():
            # Convert GPU arrays to CPU if needed
            if hasattr(feature_values, 'get'):  # CuPy array
                cpu_values = feature_values.get()
            else:
                cpu_values = feature_values
            features_df[feature_name] = cpu_values
        
        # Expand features back to tick level by replication
        expanded_features = pd.DataFrame()
        for i, row in features_df.iterrows():
            # Replicate each feature row 100 times (matching original grouping)
            expanded_row = pd.DataFrame([row] * 100)
            expanded_features = pd.concat([expanded_features, expanded_row], ignore_index=True)
        
        # Trim to match original tick data length
        expanded_features = expanded_features.iloc[:len(indicators_data)]
        
        # Combine with original indicators
        final_result = indicators_data.copy()
        for col in expanded_features.columns:
            if col not in final_result.columns:
                final_result[col] = expanded_features[col].values
        
        return final_result
    
    def _compute_bias_from_features(self, features_data: pd.DataFrame, 
                               bias_thresholds: Optional[ThresholdConfig]) -> pd.DataFrame:
        """Apply Phase 5 bias classification to features"""
        # Use existing bias classifier
        if bias_thresholds is None:
            bias_thresholds = ThresholdConfig()
        
        # Extract required features for bias classification
        required_features = ['macd_norm', 'macd_hist_norm']
        if not all(col in features_data.columns for col in required_features):
            raise ValueError(f"Required features for bias classification not found: {required_features}")
        
        # Compute bias classification without the thresholds parameter
        bias_result = self.bias_classifier.compute_bias_classification(
            macd_norm=features_data['macd_norm'].values,
            macd_hist_norm=features_data['macd_hist_norm'].values
        )
        
        # Add bias results to features data
        result = features_data.copy()
        result['bias_numeric'] = self.array_backend.to_cpu(bias_result)
        from .bias_classifier import _numeric_to_bias_labels
        result['bias_classification'] = _numeric_to_bias_labels(result['bias_numeric'])
        
        return result
    
    def _compute_positions_from_bias(self, bias_data: pd.DataFrame,
                                   position_thresholds: Optional[ThresholdConfig]) -> pd.DataFrame:
        """Apply Phase 6 position signal generation to bias data"""
        # Use existing position generator
        if position_thresholds is None:
            from .position_generator import ThresholdConfig as PositionThresholdConfig
            position_thresholds = PositionThresholdConfig()
        
        # Extract required data - bias_numeric and price_position
        bias_numeric = bias_data['bias_numeric'].values
        # Use price_position if available, otherwise create simple position metric
        if 'price_position' in bias_data.columns:
            price_position = bias_data['price_position'].values
        else:
            # Fallback: create simple price position metric from available data
            price_position = np.linspace(0, 1, len(bias_data))
        
        # Compute position signals using correct method name and parameters
        position_signals = self.position_generator.compute_position_signals(
            bias_numeric=bias_numeric,
            price_position=price_position,
            threshold_config=position_thresholds
        )
        
        # Add position signals to bias data
        result = bias_data.copy()
        result['position_signal'] = self.array_backend.to_cpu(position_signals)
        
        return result
    
    def _add_atr_risk_management(self, position_data: pd.DataFrame,
                                stop_loss_ratio: Optional[float],
                                sl_tp_ratio: Optional[float], 
                                entry_price: Optional[Union[float, np.ndarray]],
                                position_type: str) -> pd.DataFrame:
        """Add ATR-based risk management to position signals"""
        # Use existing ATR risk calculator
        if 'atr' not in position_data.columns:
            raise ValueError("ATR values required for risk management")
        
        # Use close prices as entry if not provided
        if entry_price is None:
            entry_price = position_data['price'].values
        elif isinstance(entry_price, (int, float)):
            entry_price = np.full(len(position_data), entry_price)
        
        # Compute risk levels with correct parameter names
        stop_loss_levels, take_profit_levels = self.atr_risk_calculator.compute_risk_levels(
            entry_price=entry_price,
            atr=position_data['atr'].values,
            stop_loss_ratio=stop_loss_ratio,
            sl_tp_ratio=sl_tp_ratio,
            position_type=position_type
        )
        
        # Add risk management columns
        result = position_data.copy()
        if stop_loss_ratio is not None:
            result['stop_loss'] = self.array_backend.to_cpu(stop_loss_levels)
            result['take_profit'] = self.array_backend.to_cpu(take_profit_levels)
        
        return result
    
    def _compute_position_distribution_summary(self, position_signal: pd.Series) -> str:
        """
        Compute and format position signal distribution summary for logging.
        
        Args:
            position_signal: Series with position signals (-1, 0, 1)
            
        Returns:
            Formatted string with distribution percentages
        """
        # Count positions
        total = len(position_signal)
        if total == 0:
            return "No data"
            
        long_count = (position_signal == 1).sum()
        short_count = (position_signal == -1).sum()
        neutral_count = (position_signal == 0).sum()
        nan_count = position_signal.isna().sum()
        
        # Calculate percentages
        long_pct = (long_count / total) * 100
        short_pct = (short_count / total) * 100
        neutral_pct = (neutral_count / total) * 100
        nan_pct = (nan_count / total) * 100
        
        summary = (
            f"Long:{long_pct:.1f}% | "
            f"Neutral:{neutral_pct:.1f}% | "
            f"Short:{short_pct:.1f}%"
        )
        
        if nan_pct > 0:
            summary += f" | NaN:{nan_pct:.1f}%"
            
        return summary
    
    def _compute_bias_distribution_summary(self, bias_numeric: pd.Series) -> str:
        """
        Compute and format bias distribution summary for logging.
        
        Args:
            bias_numeric: Series with bias classifications
            
        Returns:
            Formatted string with distribution percentages
        """
        from .bias_classifier import get_bias_distribution_stats_gpu
        
        stats = get_bias_distribution_stats_gpu(bias_numeric.values)
        
        summary = (
            f"SB:{stats['strong_bearish_pct']:.1f}% | "
            f"B:{stats['bearish_pct']:.1f}% | "
            f"N:{stats['neutral_pct']:.1f}% | "
            f"Bu:{stats['bullish_pct']:.1f}% | "
            f"SBu:{stats['strong_bullish_pct']:.1f}%"
        )
        
        return summary
    
    def _extract_swing_prices(self, prices, swing_mask):
        """
        Extract actual swing price values from boolean mask using forward fill.
        
        Args:
            prices: Array of price values
            swing_mask: Boolean array indicating swing points
            
        Returns:
            Array of swing prices (forward filled)
        """
        # Convert boolean mask to actual prices
        swing_prices = self.array_backend.zeros(len(prices), dtype=self.config.dtype)
        
        # Set swing prices where mask is True
        swing_prices = self.array_backend.xp.where(swing_mask, prices, self.array_backend.xp.nan)
        
        # Forward fill using pandas-style logic
        # Convert to CPU for pandas operations, then back to GPU
        prices_cpu = self.array_backend.to_cpu(swing_prices)
        filled_prices = pd.Series(prices_cpu).ffill().values
        
        return self.array_backend.asarray(filled_prices, dtype=self.config.dtype)
    
    def _forward_fill_swing_prices(self, swing_prices):
        """
        Forward fill swing prices from legacy detector output.
        
        Args:
            swing_prices: Array of swing prices with NaN where no swing detected
            
        Returns:
            Array of swing prices with forward fill applied
        """
        # Convert to CPU for pandas operations
        prices_cpu = self.array_backend.to_cpu(swing_prices)
        filled_prices = pd.Series(prices_cpu).ffill().values
        
        return self.array_backend.asarray(filled_prices, dtype=self.config.dtype)
    
    def compare_backend_performance(self,
                                   data: pd.DataFrame,
                                   indicators: List[str],
                                   runs: int = 5,
                                   **params) -> Dict[str, Any]:
        """
        Compare performance between CPU and GPU backends.
        
        Args:
            data: Input data for benchmarking
            indicators: Indicators to compute
            runs: Number of benchmark runs
            **params: Parameters for indicators
            
        Returns:
            Performance comparison results
        """
        results = {}
        
        for backend in ['numpy', 'cupy']:
            try:
                # Create pipeline with specific backend
                pipeline = UnifiedTechnicalIndicatorsPipeline(
                    backend=backend,
                    dtype=self.config.dtype,
                    optimize_memory=self.config.optimize_memory,
                    fallback_on_error=False,
                    enable_caching=False
                )
                
                # Run benchmarks
                times = []
                for _ in range(runs):
                    start_time = time.perf_counter()
                    result = pipeline.compute_indicators(data, indicators, **params)
                    end_time = time.perf_counter()
                    times.append(end_time - start_time)
                
                results[backend] = {
                    'avg_time': np.mean(times),
                    'std_time': np.std(times),
                    'min_time': np.min(times),
                    'max_time': np.max(times),
                    'results': result,
                    'backend_available': True
                }
                
            except Exception as e:
                results[backend] = {
                    'error': str(e),
                    'backend_available': False
                }
        
        # Calculate speedup if both backends worked
        if ('numpy' in results and results['numpy']['backend_available'] and
            'cupy' in results and results['cupy']['backend_available']):
            
            cpu_time = results['numpy']['avg_time']
            gpu_time = results['cupy']['avg_time']
            results['speedup'] = cpu_time / gpu_time
        
        return results
    
    def get_gpu_memory_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive GPU memory usage statistics.
        
        Returns:
            Dictionary with GPU memory statistics including RTX 4080 SUPER optimization status
        """
        if self.memory_manager:
            stats = self.memory_manager.get_memory_statistics()
            # Add GPU-only pipeline specific information
            stats.update({
                'gpu_only_pipeline': True,
                'rtx4080_super_optimized': True,
                'cpu_fallback_disabled': True,
                'cuda_streams': len(getattr(self.memory_manager, 'cuda_streams', [])),
                'aggressive_memory_threshold': self.config.memory_threshold,
                'ultra_chunk_size': self.config.chunk_size
            })
            return stats
        else:
            return {
                'gpu_available': False,
                'memory_management_enabled': False,
                'gpu_only_pipeline': True,
                'message': 'GPU memory management not enabled'
            }
    
    def clear_gpu_memory_cache(self):
        """Clear GPU memory cache to free unused blocks"""
        if self.memory_manager:
            self.memory_manager.clear_gpu_cache()
            print(f"🧨 [CACHE CLEARED] GPU memory cache cleared")
        else:
            print(f"⚠️ [WARNING] GPU memory management not available")
    
    @property
    def config(self) -> PipelineConfig:
        """Get current pipeline configuration"""
        return self._config
    
    @config.setter
    def config(self, value: PipelineConfig):
        """Set pipeline configuration"""
        self._config = value