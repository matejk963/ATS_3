# GPU-Accelerated Parallel Combination Generation - Phase 1 Complete Implementation Guide

## Overview

Phase 1 establishes the core GPU processing foundation for massive parameter combination generation using the existing ATS_3 Feature Engineering pipeline. This phase creates the essential infrastructure to convert hardcoded parameter ranges into processed trading signals at scale.

## Table of Contents

1. [ATS_3 Integration Components](#ats_3-integration-components)
2. [Phase 1 Deliverables](#phase-1-deliverables)
3. [Core Implementation Architecture](#core-implementation-architecture)
4. [Legacy Parameter Mapping Reference](#legacy-parameter-mapping-reference)
5. [GPU Processing Integration](#gpu-processing-integration)
6. [File Structure and Organization](#file-structure-and-organization)
7. [Performance Expectations](#performance-expectations)
8. [Implementation Validation](#implementation-validation)
9. [Error Handling and Monitoring](#error-handling-and-monitoring)
10. [Testing Strategy](#testing-strategy)

## ATS_3 Integration Components

### 1. UnifiedTechnicalIndicatorsPipeline

**Location**: `src/feature_engineering/unified_pipeline.py`

**Key Method**: `compute_all_indicators_features_bias_and_positions()`
- **Purpose**: Complete Phases 3-6 processing pipeline
- **Input**: DataFrame with OHLCV data + configuration parameters
- **Output**: DataFrame with indicators + features + bias + position signals
- **GPU**: Utilizes RTX 4080 SUPER with 98% memory targeting

**Method Signature**:
```python
def compute_all_indicators_features_bias_and_positions(self,
                                                     data: pd.DataFrame,
                                                     bias_thresholds: Optional[ThresholdConfig] = None,
                                                     position_thresholds: Optional[PositionThresholdConfig] = None,
                                                     candle_granularity: str = '15min',
                                                     macd_params: Dict = None,
                                                     atr_period: int = 14,
                                                     swing_lookback: int = 20) -> pd.DataFrame
```

**Configuration**:
```python
# Initialize pipeline
pipeline = UnifiedTechnicalIndicatorsPipeline(
    chunk_size=2000000,        # 2M points for RTX 4080 SUPER
    memory_threshold=0.98      # 98% GPU memory utilization
)
```

### 2. ThresholdConfig Classes

**Bias Classification Thresholds** (`src/feature_engineering/bias_classifier.py`):
```python
@dataclass
class ThresholdConfig:
    macd_line_lower: float = -0.1      # Below = Bearish MACD
    macd_line_upper: float = 0.1       # Above = Bullish MACD
    macd_histogram_lower: float = -0.05 # Below = Bearish Histogram
    macd_histogram_upper: float = 0.05  # Above = Bullish Histogram
```

**Position Signal Thresholds** (`src/feature_engineering/position_generator.py`):
```python
@dataclass
class ThresholdConfig:
    strong_bullish_buy: float = 0.35
    bullish_buy: float = 0.2
    bullish_sell: float = 0.9
    neutral_buy: float = 0.2
    neutral_sell: float = 0.9
    bearish_buy: float = 0.1
    bearish_sell: float = 0.8
    strong_bearish_sell: float = 0.65
```

### 3. ArrayBackend System

**Location**: `src/feature_engineering/array_backend.py`

**Purpose**: GPU/CPU array management with automatic backend selection
- Handles CuPy ↔ NumPy conversions
- Manages GPU memory efficiently
- Provides unified interface for array operations

**Key Methods**:
```python
backend = ArrayBackend(backend='cupy')  # Force GPU usage
gpu_array = backend.asarray(cpu_data)   # CPU → GPU
cpu_array = backend.to_cpu(gpu_array)   # GPU → CPU
```

## Phase 1 Deliverables

### 1. `src/gpu_parallel_processing/gpu_combination_generator.py`

**Primary Class**: `GPUCombinationProcessor`

```python
"""
GPU-accelerated parameter combination processor that integrates with 
ATS_3 Feature Engineering pipeline for massive-scale processing.
"""

import time
import pandas as pd
from typing import List, Dict, Optional
from pathlib import Path

from src.feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline
from src.feature_engineering.bias_classifier import ThresholdConfig as BiasThresholdConfig
from src.feature_engineering.position_generator import ThresholdConfig as PositionThresholdConfig


class GPUCombinationProcessor:
    """
    GPU-accelerated processor for parameter combinations using ATS_3 pipeline.
    
    Coordinates GPU pipeline processing for parameter combinations, converts legacy 
    ATS_2 parameter format to ATS_3 format, and manages batch processing with 
    memory optimization.
    """
    
    def __init__(self, gpu_memory_threshold: float = 0.95):
        """
        Initialize GPU combination processor.
        
        Args:
            gpu_memory_threshold: Target GPU memory utilization (0.95 = 95%)
        """
        self.pipeline = UnifiedTechnicalIndicatorsPipeline(
            chunk_size=2000000,  # Optimized for RTX 4080 SUPER
            memory_threshold=gpu_memory_threshold
        )
        self.gpu_threshold = gpu_memory_threshold
        
    def process_contract_combinations(self, 
                                    contract_data: pd.DataFrame, 
                                    combinations_batch: List[Dict]) -> List[Dict]:
        """
        Process multiple parameter combinations for single contract on GPU.
        
        Args:
            contract_data: Contract OHLCV data loaded from parquet
            combinations_batch: List of parameter combinations to process
            
        Returns:
            List of results with combo_id, result_data, and metadata
        """
        results = []
        
        for combo in combinations_batch:
            # Convert legacy parameters to ATS_3 format
            ats3_params = self._convert_legacy_parameters(combo)
            
            # Validate combination parameters
            if not self._validate_combination_parameters(combo):
                print(f"⚠️  Skipping invalid combination {combo['combo_id']}")
                continue
            
            try:
                # Process with GPU-accelerated pipeline
                result = self.pipeline.compute_all_indicators_features_bias_and_positions(
                    data=contract_data,
                    candle_granularity=combo['predictor_granularities']['atr_macd'],
                    macd_params=ats3_params['macd_params'],
                    atr_period=combo['atr_lookback'],
                    bias_thresholds=ats3_params['bias_thresholds'],
                    position_thresholds=ats3_params['position_thresholds']
                )
                
                # Create result with metadata
                result_with_metadata = self._create_result_metadata(combo, result)
                results.append(result_with_metadata)
                
            except Exception as e:
                print(f"❌ Failed to process combination {combo['combo_id']}: {e}")
                continue
        
        return results
    
    def _convert_legacy_parameters(self, legacy_combo: Dict) -> Dict:
        """Convert legacy ATS_2 parameter format to ATS_3 ThresholdConfig format."""
        
        # Convert MACD parameters (legacy uses 'short'/'long', ATS_3 uses 'fast'/'slow')
        macd_params = {
            'fast': legacy_combo['macd_params']['short'],
            'slow': legacy_combo['macd_params']['long'],
            'signal': legacy_combo['macd_params']['signal']
        }
        
        # Convert bias thresholds
        bias_thresholds = BiasThresholdConfig(
            macd_line_lower=legacy_combo['bias_thresholds']['macd_line_lower'],
            macd_line_upper=legacy_combo['bias_thresholds']['macd_line_upper'],
            macd_histogram_lower=legacy_combo['bias_thresholds']['macd_histogram_lower'],
            macd_histogram_upper=legacy_combo['bias_thresholds']['macd_histogram_upper']
        )
        
        # Convert strategy thresholds to position thresholds
        strategy = legacy_combo['strategy_thresholds']
        position_thresholds = PositionThresholdConfig(
            strong_bullish_buy=strategy['neutral_buy'] + strategy['strong_bullish_buy_adjust'],
            bullish_buy=strategy['neutral_buy'] + strategy['bullish_buy_adjust'],
            neutral_buy=strategy['neutral_buy'],
            bearish_buy=strategy['neutral_buy'] + strategy['bearish_buy_adjust'],
            strong_bearish_sell=strategy['neutral_sell'] + strategy['strong_bearish_sell_adjust'],
            bearish_sell=strategy['neutral_sell'] + strategy['bearish_sell_adjust'],
            neutral_sell=strategy['neutral_sell'],
            bullish_sell=strategy['neutral_sell'] + strategy['bullish_sell_adjust']
        )
        
        return {
            'macd_params': macd_params,
            'bias_thresholds': bias_thresholds,
            'position_thresholds': position_thresholds
        }
    
    def _validate_combination_parameters(self, combo: Dict) -> bool:
        """Validate combination parameters before processing."""
        required_keys = [
            'combo_id', 'contract', 'macd_params', 'atr_lookback',
            'bias_thresholds', 'strategy_thresholds', 'predictor_granularities'
        ]
        
        for key in required_keys:
            if key not in combo:
                print(f"❌ Missing required parameter: {key}")
                return False
        
        # Validate MACD parameters
        macd = combo['macd_params']
        if not all(isinstance(macd[k], int) and macd[k] > 0 for k in ['short', 'long', 'signal']):
            print(f"❌ Invalid MACD parameters: {macd}")
            return False
        
        if macd['short'] >= macd['long']:
            print(f"❌ MACD short ({macd['short']}) must be < long ({macd['long']})")
            return False
        
        return True
    
    def _create_result_metadata(self, combo: Dict, result_data: pd.DataFrame) -> Dict:
        """Create result structure with metadata for compatibility."""
        return {
            'combo_id': combo['combo_id'],
            'result_data': result_data,
            'metadata': {
                'contract': combo['contract'],
                'date_range': combo['date_range'],
                'predictor_granularities': combo['predictor_granularities'],
                'macd_params': combo['macd_params'],
                'atr_lookback': combo['atr_lookback'],
                'bias_thresholds': combo['bias_thresholds'],
                'strategy_thresholds': combo['strategy_thresholds'],
                'stop_loss': combo['stop_loss'],
                'sl_tp_ratio': combo['sl_tp_ratio'],
                'tp_value': combo['tp_value']
            }
        }
```

### 2. `src/gpu_parallel_processing/contract_data_manager.py`

**Primary Class**: `ContractDataManager`

```python
"""
Contract data loading and caching system with LRU eviction for efficient
memory management during massive parameter combination processing.
"""

import pandas as pd
from typing import Dict, Optional, List
from pathlib import Path
import time


class ContractDataManager:
    """
    Efficient contract data loader with LRU caching for GPU processing.
    
    Manages contract data files with memory-efficient caching, LRU eviction,
    and automatic contract file path resolution.
    """
    
    def __init__(self, max_cached_contracts: int = 3, data_directory: str = "data"):
        """
        Initialize contract data manager.
        
        Args:
            max_cached_contracts: Maximum number of contracts to cache simultaneously
            data_directory: Base directory for contract data files
        """
        self.data_cache: Dict[str, pd.DataFrame] = {}
        self.access_order: List[str] = []
        self.max_cached_contracts = max_cached_contracts
        self.data_directory = Path(data_directory)
        
        # Access tracking for LRU
        self.access_times: Dict[str, float] = {}
        self.cache_hits = 0
        self.cache_misses = 0
    
    def load_contract_data(self, contract_code: str) -> pd.DataFrame:
        """
        Load and cache contract data with LRU eviction.
        
        Args:
            contract_code: Contract identifier (e.g., 'dem07_25')
            
        Returns:
            DataFrame with contract OHLCV data
        """
        # Check cache first
        if contract_code in self.data_cache:
            self._update_access(contract_code)
            self.cache_hits += 1
            print(f"📋 Cache HIT: {contract_code} (hits: {self.cache_hits}, misses: {self.cache_misses})")
            return self.data_cache[contract_code]
        
        # Cache miss - load from file
        self.cache_misses += 1
        contract_path = self._resolve_contract_path(contract_code)
        
        print(f"📂 Loading contract data: {contract_path}")
        data = pd.read_parquet(contract_path)
        
        # Validate data
        if not self._validate_contract_data(data):
            raise ValueError(f"Invalid contract data in {contract_path}")
        
        # Cache management - evict LRU if needed
        if len(self.data_cache) >= self.max_cached_contracts:
            self._evict_lru()
        
        # Cache the data
        self.data_cache[contract_code] = data
        self.access_times[contract_code] = time.time()
        self.access_order.append(contract_code)
        
        print(f"✅ Contract loaded: {len(data):,} candles from {contract_code}")
        print(f"📊 Cache status: {len(self.data_cache)}/{self.max_cached_contracts} contracts cached")
        
        return data
    
    def get_cached_data(self, contract_code: str) -> Optional[pd.DataFrame]:
        """Get cached data without loading from file."""
        if contract_code in self.data_cache:
            self._update_access(contract_code)
            return self.data_cache[contract_code]
        return None
    
    def _resolve_contract_path(self, contract_code: str) -> Path:
        """Resolve contract code to file path."""
        contract_file = f"{contract_code}_tr_ba_data.parquet"
        contract_path = self.data_directory / contract_file
        
        if not contract_path.exists():
            raise FileNotFoundError(f"Contract data file not found: {contract_path}")
        
        return contract_path
    
    def _validate_contract_data(self, data: pd.DataFrame) -> bool:
        """Validate contract data structure and content."""
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        
        # Check required columns
        missing_columns = [col for col in required_columns if col not in data.columns]
        if missing_columns:
            print(f"❌ Missing required columns: {missing_columns}")
            return False
        
        # Check data types
        numeric_columns = ['open', 'high', 'low', 'close', 'volume']
        for col in numeric_columns:
            if not pd.api.types.is_numeric_dtype(data[col]):
                print(f"❌ Non-numeric data in column: {col}")
                return False
        
        # Check for reasonable data ranges
        if len(data) == 0:
            print(f"❌ Empty dataset")
            return False
        
        if data[['open', 'high', 'low', 'close']].min().min() <= 0:
            print(f"❌ Invalid price data (≤ 0)")
            return False
        
        return True
    
    def _update_access(self, contract_code: str) -> None:
        """Update access time and order for LRU tracking."""
        self.access_times[contract_code] = time.time()
        if contract_code in self.access_order:
            self.access_order.remove(contract_code)
        self.access_order.append(contract_code)
    
    def _evict_lru(self) -> None:
        """Evict least recently used contract from cache."""
        if not self.access_order:
            return
        
        # Find LRU contract
        lru_contract = min(self.data_cache.keys(), key=lambda x: self.access_times[x])
        
        # Remove from cache
        del self.data_cache[lru_contract]
        del self.access_times[lru_contract]
        self.access_order.remove(lru_contract)
        
        print(f"🗑️  Evicted LRU contract: {lru_contract}")
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache performance statistics."""
        total_requests = self.cache_hits + self.cache_misses
        hit_rate = (self.cache_hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'hit_rate_percent': round(hit_rate, 1),
            'cached_contracts': len(self.data_cache)
        }
```

### 3. `src/gpu_parallel_processing/gpu_batch_optimizer.py`

**Primary Class**: `GPUBatchOptimizer`

```python
"""
GPU batch size optimization for efficient memory utilization during
massive parameter combination processing.
"""

import cupy as cp
import psutil
from typing import Dict, Tuple
import math


class GPUBatchOptimizer:
    """
    GPU-aware batch size optimization for RTX 4080 SUPER processing.
    
    Calculates optimal batch sizes based on GPU memory, data size, and
    parameter complexity to maximize GPU utilization while preventing OOM.
    """
    
    def __init__(self, target_gpu_utilization: float = 0.95):
        """
        Initialize GPU batch optimizer.
        
        Args:
            target_gpu_utilization: Target GPU memory utilization (0.95 = 95%)
        """
        self.target_utilization = target_gpu_utilization
        self.gpu_info = self._get_gpu_info()
        
    def calculate_optimal_batch_size(self, 
                                   data_size: int, 
                                   parameter_complexity: int = 1) -> int:
        """
        Calculate optimal batch size based on GPU memory and data size.
        
        Args:
            data_size: Number of data points in contract dataset
            parameter_complexity: Complexity multiplier for parameter processing
            
        Returns:
            Optimal number of combinations per batch
        """
        # Estimate memory per combination
        memory_per_combo = self.estimate_memory_per_combination(data_size, parameter_complexity)
        
        # Get available GPU memory
        available_memory_mb = self._get_available_gpu_memory()
        target_memory_mb = available_memory_mb * self.target_utilization
        
        # Calculate batch size
        combinations_per_batch = max(1, int(target_memory_mb / memory_per_combo))
        
        # Apply safety limits
        min_batch_size = 1
        max_batch_size = 1000  # Reasonable upper limit for RTX 4080 SUPER
        
        optimal_batch_size = max(min_batch_size, min(combinations_per_batch, max_batch_size))
        
        print(f"🚀 GPU Batch Optimization:")
        print(f"   📊 Data size: {data_size:,} points")
        print(f"   💾 Available GPU memory: {available_memory_mb:.1f} MB")
        print(f"   🎯 Target memory usage: {target_memory_mb:.1f} MB ({self.target_utilization*100:.0f}%)")
        print(f"   📏 Memory per combination: {memory_per_combo:.1f} MB")
        print(f"   🔢 Optimal batch size: {optimal_batch_size} combinations")
        
        return optimal_batch_size
    
    def estimate_memory_per_combination(self, 
                                      data_points: int, 
                                      parameter_complexity: int = 1) -> float:
        """
        Estimate GPU memory usage per parameter combination.
        
        Args:
            data_points: Number of data points in dataset
            parameter_complexity: Complexity multiplier
            
        Returns:
            Estimated memory usage in MB per combination
        """
        # Base memory calculation for OHLCV data
        base_columns = 8  # open, high, low, close, volume + computed indicators
        bytes_per_float32 = 4
        base_memory_mb = (data_points * base_columns * bytes_per_float32) / (1024 * 1024)
        
        # Feature engineering overhead (Phase 3-6 processing)
        # MACD, ATR, Swing Points, Features, Bias, Positions
        feature_overhead_multiplier = 2.5
        
        # GPU processing overhead (temporary arrays, computations)
        gpu_overhead_multiplier = 1.5
        
        # Parameter complexity factor
        complexity_multiplier = 1.0 + (parameter_complexity - 1) * 0.2
        
        total_memory_mb = (base_memory_mb * 
                          feature_overhead_multiplier * 
                          gpu_overhead_multiplier * 
                          complexity_multiplier)
        
        return total_memory_mb
    
    def _get_available_gpu_memory(self) -> float:
        """Get available GPU memory in MB."""
        try:
            # Get current GPU memory info
            mempool = cp.get_default_memory_pool()
            used_bytes = mempool.used_bytes()
            
            # Get total GPU memory (RTX 4080 SUPER has 16GB)
            total_memory_bytes = self.gpu_info['total_memory']
            available_bytes = total_memory_bytes - used_bytes
            
            available_mb = available_bytes / (1024 * 1024)
            return max(0, available_mb)
            
        except Exception as e:
            print(f"⚠️  Could not get GPU memory info: {e}")
            # Fallback to conservative estimate
            return 12000  # 12GB conservative estimate for RTX 4080 SUPER
    
    def _get_gpu_info(self) -> Dict[str, int]:
        """Get GPU hardware information."""
        try:
            # Get GPU memory info
            device = cp.cuda.Device()
            total_memory = device.mem_info[1]  # Total GPU memory in bytes
            
            return {
                'total_memory': total_memory,
                'device_id': device.id,
                'compute_capability': device.compute_capability
            }
            
        except Exception as e:
            print(f"⚠️  Could not get GPU info: {e}")
            # Fallback for RTX 4080 SUPER
            return {
                'total_memory': 16 * 1024 * 1024 * 1024,  # 16GB in bytes
                'device_id': 0,
                'compute_capability': (8, 9)  # RTX 4080 SUPER compute capability
            }
    
    def _monitor_gpu_utilization(self) -> Dict[str, float]:
        """Monitor current GPU utilization metrics."""
        try:
            mempool = cp.get_default_memory_pool()
            used_bytes = mempool.used_bytes()
            total_bytes = self.gpu_info['total_memory']
            
            memory_utilization = (used_bytes / total_bytes) * 100
            available_memory_gb = (total_bytes - used_bytes) / (1024**3)
            
            return {
                'memory_utilization_percent': memory_utilization,
                'available_memory_gb': available_memory_gb,
                'used_memory_gb': used_bytes / (1024**3),
                'total_memory_gb': total_bytes / (1024**3)
            }
            
        except Exception as e:
            print(f"⚠️  GPU monitoring error: {e}")
            return {
                'memory_utilization_percent': 0.0,
                'available_memory_gb': 16.0,
                'used_memory_gb': 0.0,
                'total_memory_gb': 16.0
            }
```

### 4. `src/gpu_parallel_processing/parameter_combinations.py`

**Hardcoded Parameter Configuration and Generation**

```python
"""
Hardcoded parameter configuration and Cartesian product generation
for massive parameter combination processing.
"""

import itertools
from typing import List, Dict


# ============================================================================
# PARAMETER CONFIGURATION SECTION - Edit to customize parameter sweep
# ============================================================================

# 1. DATE RANGE - Single date range for all combinations
DATE_RANGE = {'start': '2025-04-01', 'end': '2025-06-30'}

# 2. CONTRACTS - List of contract codes (power/gas markets)
CONTRACTS = [
    'dem07_25',  # Germany power/gas July 2025 → dem07_25_tr_ba_data.parquet
    # Add more power/gas contracts as needed:
    # 'dem08_25',  # Germany August 2025 → dem08_25_tr_ba_data.parquet  
    # 'fra07_25',  # France July 2025 → fra07_25_tr_ba_data.parquet
    # 'gbr07_25',  # Great Britain July 2025 → gbr07_25_tr_ba_data.parquet
]

# 3. PREDICTOR GRANULARITY CONFIGURATIONS
PREDICTOR_GRANULARITIES = {
    'atr_macd_granularities': ['15min', '30min', '1h', '4h'],
    'swing_granularities': ['15min', '30min', '1h', '4h']
}

# 4. MACD CONFIGURATIONS - List of (short, long, signal) tuples
MACD_CONFIGS = [
    (12, 26, 9),
    (8, 21, 5),
    (19, 39, 9)
]

# 5. ATR LOOKBACK PERIODS
ATR_LOOKBACKS = [21]

# 6. BIAS CLASSIFIER THRESHOLDS - Symmetric pairs
def generate_symmetric_pairs(max_value: float, step: float) -> List[Tuple[float, float]]:
    """Generate symmetric pairs: (-2.5,2.5), (-2,2), etc."""
    pairs = []
    current = max_value
    while current >= step:
        pairs.append((-current, current))
        current -= step
    return pairs

BIAS_THRESHOLD_RANGES = {
    'macd_line_pairs': generate_symmetric_pairs(2.5, 0.5),        # 5 pairs
    'macd_histogram_pairs': generate_symmetric_pairs(1.25, 0.25)  # 5 pairs
}

# 7. STRATEGY THRESHOLDS - Neutral + bias adjustments
def frange(start: float, stop: float, step: float) -> List[float]:
    """Generate float range"""
    values = []
    current = start
    while current < stop:
        values.append(round(current, 2))
        current += step
    return values

NEUTRAL_STRATEGY_RANGES = {
    'buy_values': frange(0.2, 0.4, 0.1),    # [0.2, 0.3]
    'sell_values': frange(0.7, 0.9, 0.1)    # [0.7, 0.8]
}

BIAS_ADJUSTMENT_RANGES = {
    'buy_adjustment_bullish': [0.0],
    'buy_adjustment_strong_bullish': frange(0.05, 0.15, 0.05),  # [0.05, 0.1]
    'buy_adjustment_bearish': frange(-0.10, -0.04, 0.05),       # [-0.1, -0.05]
    'sell_adjustment_bearish': [0.0],
    'sell_adjustment_strong_bearish': frange(-0.10, -0.04, 0.05), # [-0.1, -0.05]
    'sell_adjustment_bullish': frange(0.05, 0.16, 0.05),        # [0.05, 0.1, 0.15]
}

# 8. STOP LOSS AND RATIOS
STOP_LOSS_RANGES = [0.5, 1.0, 1.5]  # 3 options
SL_TP_RATIOS = [1.5, 2.0]           # 2 options

# TOTAL COMBINATIONS CALCULATION:
# 1 contract × 4 × 4 × 3 × 1 × (5×5) × (2×2×1×2×2×1×2×3) × 3 × 2 = ~115,200 combinations
# (Scales with number of contracts in CONTRACTS list - add more power/gas contracts as needed)


def generate_all_parameter_combinations() -> List[Dict]:
    """Generate ALL parameter combinations using Cartesian product (legacy compatible)"""
    
    # Generate bias threshold combinations
    bias_combinations = []
    for macd_line_pair, macd_hist_pair in itertools.product(
        BIAS_THRESHOLD_RANGES['macd_line_pairs'],
        BIAS_THRESHOLD_RANGES['macd_histogram_pairs']
    ):
        bias_combinations.append({
            'macd_line_lower': macd_line_pair[0],
            'macd_line_upper': macd_line_pair[1],
            'macd_histogram_lower': macd_hist_pair[0],
            'macd_histogram_upper': macd_hist_pair[1]
        })
    
    # Generate strategy threshold combinations  
    strategy_combinations = []
    for neutral_buy in NEUTRAL_STRATEGY_RANGES['buy_values']:
        for neutral_sell in NEUTRAL_STRATEGY_RANGES['sell_values']:
            for buy_adj_bullish in BIAS_ADJUSTMENT_RANGES['buy_adjustment_bullish']:
                for buy_adj_strong_bullish in BIAS_ADJUSTMENT_RANGES['buy_adjustment_strong_bullish']:
                    for buy_adj_bearish in BIAS_ADJUSTMENT_RANGES['buy_adjustment_bearish']:
                        for sell_adj_bearish in BIAS_ADJUSTMENT_RANGES['sell_adjustment_bearish']:
                            for sell_adj_strong_bearish in BIAS_ADJUSTMENT_RANGES['sell_adjustment_strong_bearish']:
                                for sell_adj_bullish in BIAS_ADJUSTMENT_RANGES['sell_adjustment_bullish']:
                                    strategy_combinations.append({
                                        'neutral_buy': neutral_buy,
                                        'neutral_sell': neutral_sell,
                                        'bullish_buy_adjust': buy_adj_bullish,
                                        'strong_bullish_buy_adjust': buy_adj_strong_bullish,
                                        'bearish_buy_adjust': buy_adj_bearish,
                                        'bearish_sell_adjust': sell_adj_bearish,
                                        'strong_bearish_sell_adjust': sell_adj_strong_bearish,
                                        'bullish_sell_adjust': sell_adj_bullish
                                    })
    
    # Generate final Cartesian product of ALL parameters
    combinations = []
    combo_idx = 0
    
    for contract, atr_macd_gran, swing_gran, macd_config, atr_lookback, bias_thresholds, strategy_thresholds, stop_loss, sl_tp_ratio in itertools.product(
        CONTRACTS,
        PREDICTOR_GRANULARITIES['atr_macd_granularities'],
        PREDICTOR_GRANULARITIES['swing_granularities'],
        MACD_CONFIGS,
        ATR_LOOKBACKS,
        bias_combinations,
        strategy_combinations,
        STOP_LOSS_RANGES,
        SL_TP_RATIOS
    ):
        tp_value = stop_loss * sl_tp_ratio
        combo = {
            'date_range': DATE_RANGE,
            'contract': contract,  # Single contract string
            'predictor_granularities': {
                'atr_macd': atr_macd_gran,
                'swing': swing_gran
            },
            'macd_params': {'short': macd_config[0], 'long': macd_config[1], 'signal': macd_config[2]},
            'atr_lookback': atr_lookback,
            'bias_thresholds': bias_thresholds,
            'strategy_thresholds': strategy_thresholds,
            'stop_loss': stop_loss,
            'sl_tp_ratio': sl_tp_ratio,
            'tp_value': tp_value,
            'combo_id': combo_idx
        }
        combinations.append(combo)
        combo_idx += 1
    
    print(f"Generated {len(combinations)} total parameter combinations")
    return combinations


def get_combination_count_estimate() -> int:
    """Get estimated number of combinations without generating them."""
    # Calculate combination count using parameter ranges
    contract_count = len(CONTRACTS)
    atr_macd_granularity_count = len(PREDICTOR_GRANULARITIES['atr_macd_granularities'])
    swing_granularity_count = len(PREDICTOR_GRANULARITIES['swing_granularities'])
    macd_config_count = len(MACD_CONFIGS)
    atr_lookback_count = len(ATR_LOOKBACKS)
    bias_threshold_count = (len(BIAS_THRESHOLD_RANGES['macd_line_pairs']) * 
                           len(BIAS_THRESHOLD_RANGES['macd_histogram_pairs']))
    
    # Strategy combinations calculation
    strategy_count = (len(NEUTRAL_STRATEGY_RANGES['buy_values']) *
                     len(NEUTRAL_STRATEGY_RANGES['sell_values']) *
                     len(BIAS_ADJUSTMENT_RANGES['buy_adjustment_bullish']) *
                     len(BIAS_ADJUSTMENT_RANGES['buy_adjustment_strong_bullish']) *
                     len(BIAS_ADJUSTMENT_RANGES['buy_adjustment_bearish']) *
                     len(BIAS_ADJUSTMENT_RANGES['sell_adjustment_bearish']) *
                     len(BIAS_ADJUSTMENT_RANGES['sell_adjustment_strong_bearish']) *
                     len(BIAS_ADJUSTMENT_RANGES['sell_adjustment_bullish']))
    
    stop_loss_count = len(STOP_LOSS_RANGES)
    sl_tp_ratio_count = len(SL_TP_RATIOS)
    
    total_combinations = (contract_count * atr_macd_granularity_count * swing_granularity_count *
                         macd_config_count * atr_lookback_count * bias_threshold_count *
                         strategy_count * stop_loss_count * sl_tp_ratio_count)
    
    return total_combinations
```

## Legacy Parameter Mapping Reference

### MACD Parameter Conversion
```python
# Legacy ATS_2 format
legacy_macd = {'short': 12, 'long': 26, 'signal': 9}

# ATS_3 format
ats3_macd = {'fast': 12, 'slow': 26, 'signal': 9}
```

### Bias Threshold Conversion
```python
# Legacy format
legacy_bias = {
    'macd_line_lower': -1.5,
    'macd_line_upper': 1.5,
    'macd_histogram_lower': -0.75,
    'macd_histogram_upper': 0.75
}

# ATS_3 ThresholdConfig
from src.feature_engineering.bias_classifier import ThresholdConfig as BiasThresholdConfig
bias_config = BiasThresholdConfig(
    macd_line_lower=legacy_bias['macd_line_lower'],
    macd_line_upper=legacy_bias['macd_line_upper'],
    macd_histogram_lower=legacy_bias['macd_histogram_lower'],
    macd_histogram_upper=legacy_bias['macd_histogram_upper']
)
```

### Strategy Threshold Conversion
```python
# Legacy strategy thresholds
legacy_strategy = {
    'neutral_buy': 0.2,
    'neutral_sell': 0.8,
    'bullish_buy_adjust': 0.0,
    'strong_bullish_buy_adjust': 0.1,
    'bearish_buy_adjust': -0.05,
    'bearish_sell_adjust': 0.0,
    'strong_bearish_sell_adjust': -0.1,
    'bullish_sell_adjust': 0.15
}

# ATS_3 PositionThresholdConfig
from src.feature_engineering.position_generator import ThresholdConfig as PositionThresholdConfig
position_config = PositionThresholdConfig(
    strong_bullish_buy=legacy_strategy['neutral_buy'] + legacy_strategy['strong_bullish_buy_adjust'],
    bullish_buy=legacy_strategy['neutral_buy'] + legacy_strategy['bullish_buy_adjust'],
    neutral_buy=legacy_strategy['neutral_buy'],
    bearish_buy=legacy_strategy['neutral_buy'] + legacy_strategy['bearish_buy_adjust'],
    strong_bearish_sell=legacy_strategy['neutral_sell'] + legacy_strategy['strong_bearish_sell_adjust'],
    bearish_sell=legacy_strategy['neutral_sell'] + legacy_strategy['bearish_sell_adjust'],
    neutral_sell=legacy_strategy['neutral_sell'],
    bullish_sell=legacy_strategy['neutral_sell'] + legacy_strategy['bullish_sell_adjust']
)
```

## GPU Processing Integration

### Expected Parameter Combination Structure

### Input Combination Format (Legacy ATS_2)
```python
combination = {
    'date_range': {'start': '2025-04-01', 'end': '2025-06-30'},
    'contract': 'dem07_25',  # Contract code only
    'predictor_granularities': {
        'atr_macd': '15min',     # Used for candle_granularity
        'swing': '15min'         # For swing detection (if needed)
    },
    'macd_params': {'short': 12, 'long': 26, 'signal': 9},
    'atr_lookback': 21,
    'bias_thresholds': {
        'macd_line_lower': -1.5,
        'macd_line_upper': 1.5,
        'macd_histogram_lower': -0.75,
        'macd_histogram_upper': 0.75
    },
    'strategy_thresholds': {
        'neutral_buy': 0.2,
        'neutral_sell': 0.8,
        'bullish_buy_adjust': 0.0,
        'strong_bullish_buy_adjust': 0.1,
        'bearish_buy_adjust': -0.05,
        'bearish_sell_adjust': 0.0,
        'strong_bearish_sell_adjust': -0.1,
        'bullish_sell_adjust': 0.15
    },
    'stop_loss': 1.0,
    'sl_tp_ratio': 2.0,
    'tp_value': 2.0,
    'combo_id': 12345
}
```

### Contract Data File Resolution
```python
contract_code = 'dem07_25'
contract_file_path = f'data/{contract_code}_tr_ba_data.parquet'
# Results in: 'data/dem07_25_tr_ba_data.parquet'
```

### Expected Output Structure
```python
result = {
    'combo_id': 12345,
    'result_data': pd.DataFrame,  # Processed indicators + features + bias + positions
    'metadata': {
        'contract': 'dem07_25',
        'date_range': {'start': '2025-04-01', 'end': '2025-06-30'},
        'predictor_granularities': {'atr_macd': '15min', 'swing': '15min'},
        'stop_loss': 1.0,
        'sl_tp_ratio': 2.0,
        'tp_value': 2.0,
        # ... all original combination parameters
    }
}
```

## File Structure and Organization

### Directory Structure
```
src/gpu_parallel_processing/
├── __init__.py
├── gpu_combination_generator.py    # Main GPU orchestrator (GPUCombinationProcessor)
├── contract_data_manager.py        # Contract data loading/caching (ContractDataManager)
├── gpu_batch_optimizer.py          # GPU memory-aware batch optimization (GPUBatchOptimizer)
└── parameter_combinations.py       # Hardcoded parameter configuration and generation

combinations_output/           # Output directory
├── combo_000000.parquet
├── combo_000001.parquet
├── combo_000002.parquet
└── ...
```

### File Naming and Storage Conventions

### Result File Naming
```python
combo_id = 12345
output_file = f'combo_{combo_id:06d}.parquet'
# Results in: 'combo_012345.parquet'
```

## Performance Expectations

### Basic GPU Processing Targets
- **Combination Processing Rate**: 20-50 combinations/minute
- **GPU Utilization**: 85-95% sustained
- **Memory Efficiency**: Process 1.5-2M data points per batch
- **Contract Data Caching**: 3 contracts in memory simultaneously

### Scalability Baseline
- **Small Scale**: 1,000 combinations
- **Medium Scale**: 10,000 combinations  
- **Large Scale**: 50,000 combinations

### Resource Requirements
- **GPU Memory**: 14-15GB usage on RTX 4080 SUPER (95% utilization)
- **System RAM**: 8-16GB for contract data caching
- **Storage**: ~2-5MB per combination result file

### GPU Memory Management Guidelines

### Memory Estimation
```python
# Base memory calculation
data_points = len(contract_data)
base_memory_mb = (data_points * 4 * 8) / (1024 * 1024)  # float32 * 8 columns
processing_overhead = base_memory_mb * 1.5              # Feature engineering overhead

# RTX 4080 SUPER specifications
available_gpu_memory_gb = 16
target_utilization = 0.95
target_memory_mb = available_gpu_memory_gb * 1024 * target_utilization

# Batch size calculation
combinations_per_batch = max(1, int(target_memory_mb / processing_overhead))
```

### Memory Cleanup Pattern
```python
import gc
import cupy as cp

# Aggressive GPU memory cleanup between batches
gc.collect()                                    # Python garbage collection
cp.get_default_memory_pool().free_all_blocks()  # CuPy memory pool cleanup
cp.cuda.Device().synchronize()                  # Wait for GPU operations
```

## Error Handling and Monitoring

### Batch Processing Error Handling
```python
try:
    batch_results = gpu_processor.process_contract_combinations(
        contract_data, combinations_batch
    )
    # Save results atomically
    save_batch_results_atomically(batch_results)
    
except Exception as e:
    print(f"❌ Batch processing failed: {e}")
    # Save failed batch info for retry
    save_failed_batch_info(batch_start, batch_end, str(e))
    continue  # Skip to next batch
```

### GPU Memory Error Recovery
```python
try:
    # Process combination
    result = pipeline.compute_all_indicators_features_bias_and_positions(...)
except RuntimeError as e:
    if "CUDA out of memory" in str(e):
        # Reduce batch size and retry
        new_batch_size = max(1, current_batch_size // 2)
        print(f"🔄 GPU OOM - reducing batch size to {new_batch_size}")
        # Retry with smaller batch
    else:
        raise e
```

### Performance Monitoring Template

### Processing Rate Tracking
```python
import time

# Track batch processing performance
batch_start_time = time.time()
batch_results = process_combinations_batch(combinations_batch)
batch_time = time.time() - batch_start_time

# Calculate throughput
combinations_processed = len(combinations_batch)
throughput_per_minute = combinations_processed / batch_time * 60

print(f"✅ Batch complete: {combinations_processed} combinations in {batch_time:.1f}s")
print(f"📈 Throughput: {throughput_per_minute:.1f} combinations/minute")
```

### GPU Utilization Monitoring
```python
import cupy as cp

# Monitor GPU memory usage
mempool = cp.get_default_memory_pool()
used_bytes = mempool.used_bytes()
total_bytes = mempool.total_bytes()
utilization = (used_bytes / total_bytes) * 100 if total_bytes > 0 else 0

print(f"🖥️  GPU Memory: {utilization:.1f}% ({used_bytes/1024**3:.1f}GB / {total_bytes/1024**3:.1f}GB)")
```

## Implementation Validation

### Phase 1 Success Criteria

**Functional Requirements**:
1. ✅ Generate parameter combinations from hardcoded ranges
2. ✅ Load and cache contract data efficiently 
3. ✅ Process combinations through ATS_3 GPU pipeline
4. ✅ Convert legacy parameters to ATS_3 format correctly
5. ✅ Save results in compatible `.parquet` format

**Performance Requirements**:
1. ✅ Achieve 20+ combinations/minute processing rate
2. ✅ Maintain 85%+ GPU utilization during processing
3. ✅ Handle 1,000+ combinations without memory issues
4. ✅ Cache and reuse contract data across combinations

**Quality Requirements**:
1. ✅ Preserve exact legacy parameter format compatibility
2. ✅ Maintain result data integrity and completeness
3. ✅ Provide comprehensive error handling and logging
4. ✅ Generate results compatible with existing analysis tools

## Testing Strategy

### Unit Test Structure
```python
def test_parameter_conversion():
    """Test legacy → ATS_3 parameter conversion"""
    legacy_combo = {...}  # Example legacy combination
    converted = convert_legacy_parameters(legacy_combo)
    
    assert converted['macd_params']['fast'] == legacy_combo['macd_params']['short']
    assert isinstance(converted['bias_thresholds'], BiasThresholdConfig)
    assert isinstance(converted['position_thresholds'], PositionThresholdConfig)

def test_combination_processing():
    """Test end-to-end combination processing"""
    test_data = load_test_contract_data()
    test_combo = create_test_combination()
    
    result = gpu_processor.process_contract_combinations(test_data, [test_combo])
    
    assert len(result) == 1
    assert 'combo_id' in result[0]
    assert isinstance(result[0]['result_data'], pd.DataFrame)
```

### Integration Test Pattern
```python
def test_full_pipeline_integration():
    """Test complete Phase 1 pipeline with real data"""
    # Load real contract data
    contract_data = pd.read_parquet('data/dem07_25_tr_ba_data.parquet')
    
    # Generate small combination set
    combinations = generate_test_combinations(count=5)
    
    # Process through pipeline
    processor = GPUCombinationProcessor()
    results = processor.process_contract_combinations(contract_data, combinations)
    
    # Validate results
    assert len(results) == 5
    for result in results:
        validate_result_structure(result)
        validate_result_data_quality(result['result_data'])
```

### Validation Tests
- Compare results against legacy ATS_2 outputs
- Verify parameter combinations completeness
- Confirm GPU utilization and performance metrics
- Test with production-scale contract data

## Next Steps to Phase 2

Phase 1 establishes the foundation for massive-scale GPU processing. Phase 2 will build upon this foundation with:

1. **Advanced GPU Memory Management**: Sophisticated memory profiling and optimization
2. **Asynchronous File I/O**: Parallel result writing to eliminate I/O bottlenecks
3. **Intelligent Combination Scheduling**: Priority-based combination processing
4. **GPU Performance Monitoring**: Real-time utilization tracking and optimization

The Phase 1 implementation provides the core infrastructure needed to process thousands of parameter combinations efficiently while maintaining exact legacy compatibility and leveraging the full power of the ATS_3 GPU-accelerated feature engineering pipeline.