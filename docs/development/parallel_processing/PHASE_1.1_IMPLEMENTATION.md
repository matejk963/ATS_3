# GPU-Accelerated Parallel Processing - Phase 1.1: Core Infrastructure Implementation

## Overview

Sub-Phase 1.1 establishes the foundational infrastructure for GPU-accelerated parameter combination processing. This phase implements the core data management and parameter generation components that serve as the foundation for all subsequent processing phases.

## Sub-Phase Structure

- **Phase 1.1**: Core Infrastructure (Foundation) ← **Current Phase**
- **Phase 1.2**: GPU Processing Core
- **Phase 1.3**: Main Processing Engine  
- **Phase 1.4**: Integration & Testing

## Phase 1.1 Components

### 1. Parameter Combinations Module (`src/gpu_parallel_processing/parameter_combinations.py`)
### 2. Contract Data Manager (`src/gpu_parallel_processing/contract_data_manager.py`)

## Implementation Guide

### Component 1: Parameter Combinations Module

**File**: `src/gpu_parallel_processing/parameter_combinations.py`

**Purpose**: Generate and manage parameter combinations using hardcoded ranges with Cartesian product logic.

#### Key Features:
- Hardcoded parameter configuration
- Cartesian product generation for ~115,200 combinations
- Parameter validation
- Legacy ATS_2 format compatibility
- Combination count estimation

#### Implementation Steps:

##### Step 1.1.1: Create Base Structure
```python
"""
Hardcoded parameter configuration and Cartesian product generation
for massive parameter combination processing.
"""

import itertools
from typing import List, Dict, Tuple

# ============================================================================
# PARAMETER CONFIGURATION SECTION - Edit to customize parameter sweep
# ============================================================================
```

##### Step 1.1.2: Define Parameter Ranges
```python
# 1. DATE RANGE - Single date range for all combinations
DATE_RANGE = {'start': '2025-04-01', 'end': '2025-06-30'}

# 2. CONTRACTS - List of contract codes (power/gas markets)
CONTRACTS = [
    'dem07_25',  # Germany power/gas July 2025 → dem07_25_tr_ba_data.parquet
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
```

##### Step 1.1.3: Define Threshold Generation Functions
```python
def generate_symmetric_pairs(max_value: float, step: float) -> List[Tuple[float, float]]:
    """Generate symmetric pairs: (-2.5,2.5), (-2,2), etc."""
    pairs = []
    current = max_value
    while current >= step:
        pairs.append((-current, current))
        current -= step
    return pairs

def frange(start: float, stop: float, step: float) -> List[float]:
    """Generate float range"""
    values = []
    current = start
    while current < stop:
        values.append(round(current, 2))
        current += step
    return values
```

##### Step 1.1.4: Define Threshold Ranges
```python
# 6. BIAS CLASSIFIER THRESHOLDS - Symmetric pairs
BIAS_THRESHOLD_RANGES = {
    'macd_line_pairs': generate_symmetric_pairs(2.5, 0.5),        # 5 pairs
    'macd_histogram_pairs': generate_symmetric_pairs(1.25, 0.25)  # 5 pairs
}

# 7. STRATEGY THRESHOLDS - Neutral + bias adjustments
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
```

##### Step 1.1.5: Implement Main Generation Functions
```python
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

### Component 2: Contract Data Manager

**File**: `src/gpu_parallel_processing/contract_data_manager.py`

**Purpose**: Efficient contract data loading with LRU caching for memory management during massive processing.

#### Key Features:
- LRU cache with configurable size
- Automatic file path resolution
- Data validation
- Cache performance metrics
- Memory-efficient eviction

#### Implementation Steps:

##### Step 1.1.6: Create Base Class Structure
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
```

##### Step 1.1.7: Implement Core Loading Logic
```python
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
```

##### Step 1.1.8: Implement Support Methods
```python
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

## Testing Strategy for Phase 1.1

### Unit Tests

#### Test File: `tests/test_parameter_combinations.py`
```python
import pytest
from src.gpu_parallel_processing.parameter_combinations import (
    generate_all_parameter_combinations,
    get_combination_count_estimate,
    generate_symmetric_pairs,
    frange
)

def test_symmetric_pairs_generation():
    """Test symmetric pair generation function"""
    pairs = generate_symmetric_pairs(2.0, 0.5)
    expected = [(-2.0, 2.0), (-1.5, 1.5), (-1.0, 1.0), (-0.5, 0.5)]
    assert pairs == expected

def test_frange_generation():
    """Test float range generation"""
    values = frange(0.1, 0.4, 0.1)
    expected = [0.1, 0.2, 0.3]
    assert values == expected

def test_combination_count_estimate():
    """Test combination count calculation"""
    estimated_count = get_combination_count_estimate()
    assert estimated_count > 0
    assert isinstance(estimated_count, int)

def test_combination_structure():
    """Test that generated combinations have correct structure"""
    combinations = generate_all_parameter_combinations()
    
    assert len(combinations) > 0
    
    # Test first combination structure
    combo = combinations[0]
    required_keys = [
        'date_range', 'contract', 'predictor_granularities', 
        'macd_params', 'atr_lookback', 'bias_thresholds',
        'strategy_thresholds', 'stop_loss', 'sl_tp_ratio', 
        'tp_value', 'combo_id'
    ]
    
    for key in required_keys:
        assert key in combo
    
    # Test parameter types
    assert isinstance(combo['combo_id'], int)
    assert isinstance(combo['contract'], str)
    assert isinstance(combo['macd_params'], dict)
    assert isinstance(combo['bias_thresholds'], dict)
```

#### Test File: `tests/test_contract_data_manager.py`
```python
import pytest
import pandas as pd
import tempfile
from pathlib import Path
from src.gpu_parallel_processing.contract_data_manager import ContractDataManager

@pytest.fixture
def test_data_manager():
    """Create test data manager with temporary directory"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield ContractDataManager(max_cached_contracts=2, data_directory=temp_dir)

@pytest.fixture
def sample_contract_data():
    """Create sample contract data for testing"""
    return pd.DataFrame({
        'open': [100.0, 101.0, 102.0],
        'high': [105.0, 106.0, 107.0],
        'low': [95.0, 96.0, 97.0],
        'close': [103.0, 104.0, 105.0],
        'volume': [1000, 1100, 1200]
    })

def test_cache_hit_miss_tracking(test_data_manager, sample_contract_data):
    """Test cache hit/miss tracking"""
    # Create test file
    test_file = Path(test_data_manager.data_directory) / "test01_tr_ba_data.parquet"
    sample_contract_data.to_parquet(test_file)
    
    # First load should be cache miss
    data1 = test_data_manager.load_contract_data("test01")
    assert test_data_manager.cache_misses == 1
    assert test_data_manager.cache_hits == 0
    
    # Second load should be cache hit
    data2 = test_data_manager.load_contract_data("test01")
    assert test_data_manager.cache_misses == 1
    assert test_data_manager.cache_hits == 1

def test_lru_eviction(test_data_manager, sample_contract_data):
    """Test LRU eviction mechanism"""
    # Create test files
    for i in range(3):
        test_file = Path(test_data_manager.data_directory) / f"test{i:02d}_tr_ba_data.parquet"
        sample_contract_data.to_parquet(test_file)
    
    # Load 3 contracts (exceeds max_cached_contracts=2)
    test_data_manager.load_contract_data("test00")
    test_data_manager.load_contract_data("test01")
    test_data_manager.load_contract_data("test02")  # Should trigger eviction
    
    # Check that only 2 contracts are cached
    assert len(test_data_manager.data_cache) == 2
    assert "test00" not in test_data_manager.data_cache  # Should be evicted (LRU)

def test_data_validation(test_data_manager):
    """Test data validation logic"""
    # Test with invalid data (missing columns)
    invalid_data = pd.DataFrame({'invalid_col': [1, 2, 3]})
    assert not test_data_manager._validate_contract_data(invalid_data)
    
    # Test with valid data
    valid_data = pd.DataFrame({
        'open': [100.0, 101.0],
        'high': [105.0, 106.0],
        'low': [95.0, 96.0],
        'close': [103.0, 104.0],
        'volume': [1000, 1100]
    })
    assert test_data_manager._validate_contract_data(valid_data)
```

## File Structure

```
src/gpu_parallel_processing/
├── __init__.py
├── parameter_combinations.py       # ← Phase 1.1 Component 1
└── contract_data_manager.py        # ← Phase 1.1 Component 2

tests/
├── test_parameter_combinations.py  # ← Phase 1.1 Tests
└── test_contract_data_manager.py   # ← Phase 1.1 Tests
```

## Success Criteria for Phase 1.1

### Functional Requirements:
1. ✅ Generate parameter combinations from hardcoded ranges (~115,200 total)
2. ✅ Load and cache contract data with LRU eviction
3. ✅ Validate parameter combinations and data integrity
4. ✅ Provide efficient file path resolution
5. ✅ Track cache performance metrics

### Testing Requirements:
1. ✅ Unit tests for all core functions with 90%+ coverage
2. ✅ Integration tests with real contract data files
3. ✅ Performance tests for combination generation
4. ✅ Memory efficiency tests for data caching

### Quality Requirements:
1. ✅ Maintain legacy ATS_2 parameter format compatibility
2. ✅ Provide comprehensive error handling and validation
3. ✅ Generate consistent, reproducible parameter combinations
4. ✅ Efficient memory usage for contract data management

## Next Steps to Phase 1.2

Upon successful completion of Phase 1.1, Phase 1.2 will implement:
- **GPU Batch Optimizer** for memory-aware processing
- **Legacy Parameter Conversion** for ATS_2 → ATS_3 mapping
- **GPU utilization monitoring** and optimization algorithms

Phase 1.1 provides the essential data management foundation needed for all subsequent GPU processing phases.