# GPU-Accelerated Parallel Combination Generation Implementation Plan

## Overview

This document outlines the implementation plan for creating a GPU-accelerated parallel combination generation system that leverages the existing ATS_3 Feature Engineering pipeline to process massive parameter combinations efficiently.

## Context: Existing GPU Infrastructure

### ATS_3 Feature Engineering System
Based on the Feature Engineering Manual, we have a production-ready GPU-accelerated pipeline:

**Key Components Available**:
- `UnifiedTechnicalIndicatorsPipeline`: Complete Phases 3-6 processing
- GPU-optimized memory management (RTX 4080 SUPER: 98% utilization)
- Unlimited scalability through intelligent chunking
- Performance: 1,500+ points/second sustained throughput

**Processing Phases**:
1. **Phase 3**: Technical Indicators (MACD, ATR, Swing Points)
2. **Phase 4**: Feature Engineering (Normalization, Price Position)
3. **Phase 5**: Bias Classification (-2 to +2 market sentiment)
4. **Phase 6**: Position Signals (-1, 0, 1 trading signals)

## GPU-Based Parallel Architecture

### 1. Hardcoded Parameter Configuration (Exact Legacy Format)

**Parameter Definition** (Edit these constants to configure sweep):
```python
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
def generate_symmetric_pairs(max_value, step):
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
def frange(start, stop, step):
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
```

**Cartesian Product Generation** (Exact Legacy Logic):
```python
import itertools

def generate_all_parameter_combinations():
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
```

**GPU Batch Processing**:
```python
class GPUCombinationProcessor:
    def __init__(self, gpu_memory_threshold=0.95):
        self.pipeline = UnifiedTechnicalIndicatorsPipeline(
            chunk_size=2000000,  # Optimized for RTX 4080 SUPER
            memory_threshold=gpu_memory_threshold
        )
        self.contract_data_cache = {}
    
    def process_contract_combinations(self, contract_data, combinations_batch):
        """Process multiple parameter combinations for single contract on GPU"""
        results = []
        
        for combo in combinations_batch:
            # Convert legacy ATS_2 parameters to ATS_3 format
            ats3_params = self._convert_legacy_parameters(combo)
            
            # Process with GPU-accelerated pipeline
            result = self.pipeline.compute_all_indicators_features_bias_and_positions(
                data=contract_data,
                candle_granularity=combo['predictor_granularities']['atr_macd'],
                macd_params=ats3_params['macd_params'],
                atr_period=combo['atr_lookback'],
                bias_thresholds=ats3_params['bias_thresholds'],
                position_thresholds=ats3_params['position_thresholds']
            )
            
            # Add metadata for compatibility
            result['combo_id'] = combo['combo_id']
            result['contract'] = combo['contract']
            result['date_range'] = combo['date_range']
            result['predictor_granularities'] = combo['predictor_granularities']
            result['stop_loss'] = combo['stop_loss']
            result['sl_tp_ratio'] = combo['sl_tp_ratio']
            result['tp_value'] = combo['tp_value']
            
            results.append({
                'combo_id': combo['combo_id'],
                'result_data': result,
                'metadata': combo
            })
        
        return results
    
    def _convert_legacy_parameters(self, legacy_combo):
        """Convert legacy ATS_2 parameter format to ATS_3 ThresholdConfig format"""
        from src.feature_engineering.bias_classifier import ThresholdConfig as BiasThresholdConfig
        from src.feature_engineering.position_generator import ThresholdConfig as PositionThresholdConfig
        
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
```

### 2. Memory-Optimized Data Management

**Smart Contract Data Caching**:
```python
class ContractDataManager:
    def __init__(self, max_cached_contracts=3):
        self.data_cache = {}
        self.max_cached_contracts = max_cached_contracts
        self.access_order = []
    
    def load_contract_data(self, contract_path):
        """Load and cache contract data with LRU eviction"""
        if contract_path in self.data_cache:
            self._update_access(contract_path)
            return self.data_cache[contract_path]
        
        # Load data
        data = pd.read_parquet(contract_path)
        
        # Cache management
        if len(self.data_cache) >= self.max_cached_contracts:
            self._evict_lru()
        
        self.data_cache[contract_path] = data
        self.access_order.append(contract_path)
        return data
```

**GPU Memory Optimization**:
```python
class GPUBatchOptimizer:
    def __init__(self, target_gpu_utilization=0.95):
        self.target_utilization = target_gpu_utilization
        self.pipeline = None
    
    def calculate_optimal_batch_size(self, data_size, parameter_complexity):
        """Calculate optimal batch size based on GPU memory and data size"""
        # Estimate memory per combination
        base_memory_mb = (data_size * 4 * 8) / (1024 * 1024)  # float32 * 8 columns
        processing_overhead = base_memory_mb * 1.5  # Feature engineering overhead
        
        # Get available GPU memory
        available_memory_mb = self._get_available_gpu_memory()
        target_memory_mb = available_memory_mb * self.target_utilization
        
        # Calculate batch size
        combinations_per_batch = max(1, int(target_memory_mb / processing_overhead))
        return combinations_per_batch
```

### 2. Massive-Scale GPU Processing Architecture

**Core Processing Workflow** (Handles 100,000+ combinations efficiently):
```python
class GPUMassiveParallelCombinationGenerator:
    def __init__(self, output_directory="combinations_output/", target_gpu_utilization=0.98):
        self.gpu_processor = GPUCombinationProcessor(gpu_memory_threshold=target_gpu_utilization)
        self.data_manager = ContractDataManager()
        self.batch_optimizer = GPUBatchOptimizer(target_gpu_utilization=target_gpu_utilization)
        self.output_dir = Path(output_directory)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Performance tracking
        self.processed_combinations = 0
        self.start_time = None
        
    def process_massive_parameter_sweep(self, contract_data_path=None):
        """Main entry point for processing 100,000+ parameter combinations"""
        self.start_time = time.time()
        
        # Generate ALL parameter combinations using Cartesian product
        print("🔄 Generating parameter combinations using Cartesian product...")
        all_combinations = generate_all_parameter_combinations()
        total_combinations = len(all_combinations)
        
        print(f"📊 Total combinations to process: {total_combinations:,}")
        print(f"📈 Estimated processing time (GPU): {total_combinations/60:.1f} - {total_combinations/100:.1f} minutes")
        
        # Group combinations by contract for efficient processing
        combinations_by_contract = {}
        for combo in all_combinations:
            contract = combo['contract']
            if contract not in combinations_by_contract:
                combinations_by_contract[contract] = []
            combinations_by_contract[contract].append(combo)
        
        print(f"📊 Processing {len(combinations_by_contract)} contracts:")
        for contract, combos in combinations_by_contract.items():
            print(f"   📈 {contract}: {len(combos):,} combinations")
        
        # Process each contract separately (optimizes data loading)
        total_processed = 0
        for contract, contract_combinations in combinations_by_contract.items():
            print(f"\n🔄 Processing contract: {contract}")
            
            # Load contract-specific data (contract code + _tr_ba_data suffix)
            contract_data_path = f"data/{contract}_tr_ba_data.parquet"
            contract_data = self.data_manager.load_contract_data(contract_data_path)
        
            print(f"📋 Contract data loaded: {len(contract_data):,} candles from {contract_data_path}")
            
            # Calculate optimal batch size for this contract
            optimal_batch_size = self.batch_optimizer.calculate_massive_batch_size(
                data_size=len(contract_data),
                total_combinations=len(contract_combinations),
                available_gpu_memory_gb=16  # RTX 4080 SUPER
            )
            
            print(f"🚀 GPU batch size optimized: {optimal_batch_size} combinations per batch")
            print(f"🔢 Contract batches: {math.ceil(len(contract_combinations) / optimal_batch_size)}")
            
            # Process this contract's combinations in GPU-optimized batches
            self._process_combinations_in_massive_batches(
                contract_data, contract_combinations, optimal_batch_size
            )
            
            total_processed += len(contract_combinations)
            print(f"✅ Contract {contract} complete: {len(contract_combinations):,} combinations processed")
            print(f"📊 Overall progress: {total_processed:,}/{total_combinations:,} ({total_processed/total_combinations*100:.1f}%)")
        
        # Final summary
        total_time = time.time() - self.start_time
        throughput = total_combinations / total_time * 60  # combinations per minute
        print(f"✅ Processing complete!")
        print(f"⏱️  Total time: {total_time/60:.1f} minutes")
        print(f"📈 Throughput: {throughput:.1f} combinations/minute")
        print(f"💾 Output files: {self.output_dir}/combo_{{000000-{total_combinations-1:06d}}}.parquet")
    
    def _process_combinations_in_massive_batches(self, contract_data, all_combinations, batch_size):
        """Process combinations in large GPU-optimized batches with progress tracking"""
        total_combinations = len(all_combinations)
        
        for batch_start in range(0, total_combinations, batch_size):
            batch_end = min(batch_start + batch_size, total_combinations)
            combinations_batch = all_combinations[batch_start:batch_end]
            current_batch = (batch_start // batch_size) + 1
            total_batches = math.ceil(total_combinations / batch_size)
            
            print(f"🔄 Processing batch {current_batch}/{total_batches}: combinations {batch_start+1:,}-{batch_end:,}")
            
            # GPU batch processing with memory monitoring
            batch_start_time = time.time()
            try:
                batch_results = self.gpu_processor.process_contract_combinations(
                    contract_data, combinations_batch
                )
                
                # Save results with atomic writes
                self._save_batch_results_atomically(batch_results)
                
                # Update progress tracking
                self.processed_combinations += len(combinations_batch)
                batch_time = time.time() - batch_start_time
                current_throughput = len(combinations_batch) / batch_time * 60
                
                print(f"✅ Batch {current_batch} complete: {len(combinations_batch)} combinations in {batch_time:.1f}s ({current_throughput:.1f}/min)")
                print(f"📊 Progress: {self.processed_combinations:,}/{total_combinations:,} ({self.processed_combinations/total_combinations*100:.1f}%)")
                
            except Exception as e:
                print(f"❌ Batch {current_batch} failed: {e}")
                # Save failed batch info for retry
                self._save_failed_batch_info(batch_start, batch_end, str(e))
                continue
            
            # Aggressive GPU memory cleanup between batches
            self._cleanup_gpu_memory_aggressively()
            
            # Brief pause to prevent GPU thermal issues during massive processing
            if current_batch % 10 == 0:  # Every 10 batches
                time.sleep(1)
                print(f"🌡️  GPU cooling pause after {current_batch} batches")
    
    def _save_batch_results_atomically(self, batch_results):
        """Save batch results with atomic writes to prevent corruption during massive processing"""
        for result in batch_results:
            combo_id = result['combo_id']
            output_path = self.output_dir / f"combo_{combo_id:06d}.parquet"
            temp_path = self.output_dir / f"combo_{combo_id:06d}.parquet.tmp"
            
            try:
                # Write to temporary file first
                result['result_data'].to_parquet(temp_path, compression='snappy')
                # Atomic rename to final file
                temp_path.rename(output_path)
            except Exception as e:
                print(f"❌ Failed to save combo_{combo_id:06d}: {e}")
                if temp_path.exists():
                    temp_path.unlink()  # Clean up temp file
    
    def _cleanup_gpu_memory_aggressively(self):
        """Aggressive GPU memory cleanup for massive processing"""
        import gc
        import cupy as cp
        
        gc.collect()  # Python garbage collection
        cp.get_default_memory_pool().free_all_blocks()  # CuPy memory pool cleanup
        cp.cuda.Device().synchronize()  # Wait for GPU operations to complete
```

## Implementation Phases

### Phase 1: GPU Pipeline Integration

**Deliverables**:
- `src/gpu_parallel_processing/gpu_combination_generator.py`
- `src/gpu_parallel_processing/contract_data_manager.py`
- `src/gpu_parallel_processing/gpu_batch_optimizer.py`

**Key Components**:
1. Integration with existing `UnifiedTechnicalIndicatorsPipeline`
2. Contract-based data loading and caching
3. GPU memory-aware batch sizing
4. Basic combination parameter management

### Phase 2: Performance Optimization

**Deliverables**:
- `src/gpu_parallel_processing/gpu_memory_manager.py`
- `src/gpu_parallel_processing/async_file_writer.py`
- `src/gpu_parallel_processing/combination_scheduler.py`

**Key Components**:
1. Advanced GPU memory management
2. Asynchronous file I/O operations
3. Intelligent combination scheduling
4. GPU performance monitoring

### Phase 3: Scalability & Monitoring

**Deliverables**:
- `src/gpu_parallel_processing/gpu_performance_monitor.py`
- `src/gpu_parallel_processing/progress_tracker.py`
- `src/gpu_parallel_processing/resource_monitor.py`

**Key Components**:
1. Real-time GPU utilization tracking
2. Progress reporting and checkpointing
3. System resource monitoring
4. Bottleneck identification and optimization

### Phase 4: Integration & Validation

**Deliverables**:
- `tests/gpu_parallel_processing/`
- `uat/gpu_parallel_processing/`
- Migration utilities from legacy system

**Key Components**:
1. Comprehensive GPU processing tests
2. Performance benchmark validation
3. Output compatibility verification
4. Legacy parameter conversion utilities

## Expected Performance Improvements

### Massive-Scale GPU Throughput

**Legacy Performance** (sequential CPU):
- ~1 combination per minute (CPU-bound)
- Total combinations: 115,200 (with 1 power/gas contract + current parameter ranges)
- Estimated time: ~80 days

**GPU-Accelerated Performance** (massive parallel):
- ~60-120 combinations per minute (GPU batch processing)
- Same 115,200+ combinations
- Estimated time: ~16-32 hours
- **Performance gain: 60-120x speedup**

**Power/Gas Contract Scalability**:
- **1 contract** (dem07_25): 115,200 combinations → ~16-32 hours
- **5 contracts** (dem07_25, dem08_25, fra07_25, etc.): 576,000 combinations → ~80-160 hours (3-7 days)
- **12 contracts** (full quarterly power/gas): 1,382,400 combinations → ~190-380 hours (8-16 days)
- **Legacy equivalent**: 80-960+ days for 12 power/gas contracts

### Resource Utilization

**GPU Optimization**:
- RTX 4080 SUPER: 95-98% utilization sustained
- Memory efficiency: Process 2M+ data points per batch
- Parallel feature engineering: All phases processed simultaneously

**Memory Management**:
- Contract data cached and reused across parameter combinations
- GPU memory automatically managed with 95% target utilization
- Minimal CPU memory footprint through GPU-centric processing

## Risk Mitigation

### 1. GPU Memory Exhaustion
**Risk**: Large datasets or too many combinations causing GPU OOM
**Mitigation**: 
- Dynamic batch size calculation based on available GPU memory
- Automatic memory cleanup between batches
- Graceful fallback to smaller batch sizes

### 2. GPU Hardware Failures
**Risk**: GPU crashes or thermal throttling during processing
**Mitigation**:
- Progress checkpointing every N combinations
- Automatic retry logic for failed batches
- GPU temperature monitoring with automatic throttling

### 3. Data Integrity Issues
**Risk**: Corrupted output files or incomplete processing
**Mitigation**:
- Atomic file writes with temporary files
- Output validation against expected schemas
- Comprehensive logging for debugging and recovery

## Implementation Notes

### File Structure
```
src/gpu_parallel_processing/
├── __init__.py
├── gpu_combination_generator.py    # Main GPU orchestrator
├── contract_data_manager.py        # Contract data loading/caching
├── gpu_batch_optimizer.py          # GPU memory-aware batch optimization
├── gpu_memory_manager.py           # Advanced GPU memory management
├── async_file_writer.py            # Asynchronous file operations
├── combination_scheduler.py        # Intelligent combination scheduling
├── gpu_performance_monitor.py      # GPU utilization tracking
├── progress_tracker.py             # Progress reporting and checkpointing
└── resource_monitor.py             # System resource monitoring
```

### Configuration Parameters
```python
GPU_PARALLEL_CONFIG = {
    'gpu_memory_threshold': 0.95,      # Target GPU memory utilization
    'max_batch_size': 1000,            # Maximum combinations per batch
    'checkpoint_interval': 500,         # Save progress every N combinations
    'retry_attempts': 3,               # Retry failed batches
    'contract_cache_size': 3,          # Number of contracts to cache
    'async_write_workers': 4,          # Parallel file writing threads
    'gpu_temperature_limit': 85,       # GPU thermal throttling threshold
    'memory_cleanup_threshold': 0.98   # Trigger cleanup at this usage
}
```

### Integration with Existing Infrastructure

1. **Feature Engineering Pipeline**: Direct integration with `UnifiedTechnicalIndicatorsPipeline`
2. **GPU Infrastructure**: Leverages existing `ArrayBackend`, `GPUMemoryManager`, and performance optimizations
3. **Output Compatibility**: Maintains exact legacy output format (`combo_{idx:06d}.parquet`)
4. **Parameter Systems**: Utilizes existing `ThresholdConfig` classes for bias and position thresholds

### Legacy Parameter Mapping

```python
# Complete Legacy ATS_2 → ATS_3 GPU parameter mapping
legacy_to_gpu_mapping = {
    # Core parameters
    'date_range': 'passed through unchanged',
    'contract': 'contract code only (e.g., dem07_25) - _tr_ba_data.parquet is auto-appended',
    'predictor_granularities.atr_macd': 'candle_granularity parameter',
    'predictor_granularities.swing': 'used for swing detection (if needed)',
    
    # MACD parameters (naming change)
    'macd_params.short': 'macd_params.fast',
    'macd_params.long': 'macd_params.slow',
    'macd_params.signal': 'macd_params.signal',
    'atr_lookback': 'atr_period',
    
    # Bias thresholds (direct mapping)
    'bias_thresholds.macd_line_lower': 'BiasThresholdConfig.macd_line_lower',
    'bias_thresholds.macd_line_upper': 'BiasThresholdConfig.macd_line_upper',
    'bias_thresholds.macd_histogram_lower': 'BiasThresholdConfig.macd_histogram_lower',
    'bias_thresholds.macd_histogram_upper': 'BiasThresholdConfig.macd_histogram_upper',
    
    # Strategy thresholds → Position thresholds (computed mapping)
    'strategy_thresholds.neutral_buy': 'base for PositionThresholdConfig buy thresholds',
    'strategy_thresholds.neutral_sell': 'base for PositionThresholdConfig sell thresholds',
    'strategy_thresholds.*_adjust': 'adjustments applied to neutral base values',
    
    # Stop loss parameters (metadata only - not used in ATS_3 processing)
    'stop_loss': 'metadata only',
    'sl_tp_ratio': 'metadata only',
    'tp_value': 'metadata only',
    'combo_id': 'combo_id (preserved for output naming)'
}

# Strategy threshold adjustment mapping
strategy_adjustment_mapping = {
    'strong_bullish_buy': 'neutral_buy + strong_bullish_buy_adjust',
    'bullish_buy': 'neutral_buy + bullish_buy_adjust', 
    'neutral_buy': 'neutral_buy + 0',
    'bearish_buy': 'neutral_buy + bearish_buy_adjust',
    'strong_bearish_sell': 'neutral_sell + strong_bearish_sell_adjust',
    'bearish_sell': 'neutral_sell + bearish_sell_adjust',
    'neutral_sell': 'neutral_sell + 0',
    'bullish_sell': 'neutral_sell + bullish_sell_adjust'
}
```

## Success Metrics

1. **Performance**: 50-100x speedup in combination generation (8-16 hours vs 35 days)
2. **GPU Utilization**: Sustained 95-98% GPU utilization during processing
3. **Memory Efficiency**: Process 2M+ data points per batch with minimal memory overhead
4. **Reliability**: <0.1% failure rate with automatic retry and recovery
5. **Scalability**: Handle 100,000+ parameter combinations efficiently

## Usage Example

**Simple Setup and Execution**:
```python
# src/gpu_parallel_processing/gpu_combination_sweep.py

# 1. Edit parameter constants at top of file
DATE_RANGE = {'start': '2025-04-01', 'end': '2025-06-30'}
CONTRACTS = ['dem07_25']  # Power/gas contract codes only (_tr_ba_data.parquet auto-appended)
PREDICTOR_GRANULARITIES = {
    'atr_macd_granularities': ['15min', '30min', '1h'],
    'swing_granularities': ['15min', '30min', '1h']
}
MACD_CONFIGS = [(12, 26, 9), (8, 21, 5)]
# ... edit other parameter ranges as needed

# 2. Run massive GPU processing (automatically processes all contracts)
if __name__ == "__main__":
    # Initialize GPU processor
    gpu_generator = GPUMassiveParallelCombinationGenerator(
        output_directory="C:/Users/krajcovic/Documents/Testing Data/ATS_data/gpu_combinations",
        target_gpu_utilization=0.98
    )
    
    # Process all contracts and combinations with GPU acceleration
    gpu_generator.process_massive_parameter_sweep()
    
    # Expected output: 
    # ✅ Processing complete!
    # ⏱️  Total time: 22.3 minutes
    # 📈 Throughput: 86.2 combinations/minute
    # 💾 Output files: .../combo_{000000-115199}.parquet
```

**Expected Console Output**:
```
🔄 Generating parameter combinations using Cartesian product...
Generated 115,200 total parameter combinations
📊 Total combinations to process: 115,200
📈 Estimated processing time (GPU): 16.0 - 32.0 minutes
📊 Processing 1 contracts:
   📈 dem07_25: 115,200 combinations

🔄 Processing contract: dem07_25
📋 Contract data loaded: 1,763 candles from data/dem07_25_tr_ba_data.parquet
🚀 GPU batch size optimized: 150 combinations per batch
🔢 Contract batches: 768

🔄 Processing batch 1/768: combinations 1-150
✅ Batch 1 complete: 150 combinations in 2.1s (4285.7/min)
📊 Progress: 150/115,200 (0.1%)

🔄 Processing batch 2/768: combinations 151-300
✅ Batch 2 complete: 150 combinations in 1.8s (5000.0/min)
📊 Progress: 300/115,200 (0.3%)
...
🌡️  GPU cooling pause after 10 batches
...
✅ Contract dem07_25 complete: 115,200 combinations processed
📊 Overall progress: 115,200/115,200 (100.0%)

✅ Processing complete!
⏱️  Total time: 22.3 minutes
📈 Throughput: 86.2 combinations/minute  
💾 Output files: .../combo_{000000-115199}.parquet
```

## Next Steps

1. **Phase 1 Implementation**: Create GPU combination generator with exact legacy parameter format
2. **Cartesian Product Integration**: Implement `generate_all_parameter_combinations()` function
3. **GPU Batch Optimization**: Develop `calculate_massive_batch_size()` for 100,000+ combinations
4. **Performance Testing**: Validate 60-120x speedup targets with real datasets
5. **Massive Scale Testing**: Test with 500,000+ combinations for production readiness
6. **Legacy Compatibility**: Ensure exact output format and parameter mapping compatibility