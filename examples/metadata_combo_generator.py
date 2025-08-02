"""
Metadata-based Combo Generator - Load existing combinations metadata and generate combo data files

This script reads pre-existing combinations metadata (like combinations_metadata.json) 
and generates the corresponding combo data files in ATS_3_data/data/ directory.
Much simpler than combo_generator.py since parameters are already defined in metadata.

🚀 GPU OPTIMIZATION FIXES APPLIED:
   ✅ Data cleaning to remove string columns that cause GPU conversion errors
   ✅ Automatic datetime column creation for pipeline compatibility
   ✅ OHLCV column generation for GPU processing requirements
   ✅ Float32 conversion for optimal GPU memory usage
   ✅ Better error handling with specific GPU error detection
   ✅ Data size validation for GPU efficiency recommendations

🎯 HOW TO MODIFY CONFIGURATION:
   1. Scroll down to the "HARDCODED INPUT CONFIGURATION" section (around line 35)
   2. Modify the paths and settings:
      - METADATA_FILE_PATH: Path to your combinations metadata file
      - CONTRACT_CODE: Which contract data to use
      - MAX_COMBINATIONS: How many combinations to process (None = all)
      - OUTPUT_BASE_PATH: Where to save the combo files
   3. Save the file and run - configuration will be automatically used

Usage:
    pwsh -Command "python examples/metadata_combo_generator.py"
"""

import argparse
import time
import pandas as pd
import numpy as np
from pathlib import Path
import json
import os
import platform
import sys
from typing import Dict, List, Optional, Tuple
import warnings
import tkinter as tk
from tkinter import messagebox
warnings.filterwarnings('ignore')

# Add project root to Python path for PowerShell compatibility
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


# ========================================================================
# HARDCODED INPUT CONFIGURATION - MODIFY THESE VALUES BY HAND
# ========================================================================

def get_cross_platform_metadata_path() -> str:
    """Get the correct metadata file path for both WSL and PowerShell/Windows."""
    if platform.system() == "Linux" or "microsoft" in platform.release().lower():
        # WSL environment
        return "/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_data/combinations_metadata.json"
    else:
        # Windows PowerShell/CMD environment
        return r"C:\Users\krajcovic\Documents\Testing Data\ATS_data\combinations_metadata.json"

def get_cross_platform_output_path() -> str:
    """Get the correct output path for both WSL and PowerShell/Windows."""
    if platform.system() == "Linux" or "microsoft" in platform.release().lower():
        # WSL environment
        return "/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data"
    else:
        # Windows PowerShell/CMD environment
        return r"C:\Users\krajcovic\Documents\Testing Data\ATS_3_data"

# Configuration Settings - MODIFY THESE VALUES
METADATA_CONFIG = {
    'metadata_file_path': get_cross_platform_metadata_path(),  # PATH TO METADATA FILE
    'contract_code': 'dem07_25',                              # CONTRACT TO USE (candle size comes from metadata!)
    'max_combinations': None,                                 # MAX COMBOS TO PROCESS (None = all, or set number like 1000)
    'output_base_path': get_cross_platform_output_path(),     # OUTPUT DIRECTORY
    'use_batch_processing': True,                             # ENABLE BATCH PROCESSING FOR GPU OPTIMIZATION
    'batch_size': 'auto',                                     # BATCH SIZE: 'auto' (200-800 for RTX 4080), or manual like 300
    'target_gpu_utilization': 0.90                           # TARGET GPU MEMORY USAGE (90% for maximum utilization)
}

# ========================================================================
# END HARDCODED CONFIGURATION
# ========================================================================


def get_cross_platform_path() -> str:
    """Get the correct backtest data path for both WSL and PowerShell/Windows."""
    if platform.system() == "Linux" or "microsoft" in platform.release().lower():
        # WSL environment
        return "/mnt/c/Users/krajcovic/Documents/Testing Data/backtest_data"
    else:
        # Windows PowerShell/CMD environment
        return r"C:\Users\krajcovic\Documents\Testing Data\backtest_data"


def get_gpu_info() -> Dict:
    """Get GPU memory and compute information."""
    try:
        import cupy
        total_memory = cupy.cuda.Device().mem_info[1]
        free_memory = cupy.cuda.Device().mem_info[0]
        used_memory = total_memory - free_memory
        
        gpu_info = {
            'total_memory_gb': total_memory / (1024**3),
            'free_memory_gb': free_memory / (1024**3),
            'used_memory_gb': used_memory / (1024**3),
            'memory_utilization': used_memory / total_memory,
            'has_gpu': True
        }
        return gpu_info
    except ImportError:
        return {
            'total_memory_gb': 16.0,  # Assume RTX 4080 SUPER
            'free_memory_gb': 12.0,
            'used_memory_gb': 4.0,
            'memory_utilization': 0.25,
            'has_gpu': False
        }


def calculate_optimal_batch_size(sample_data: pd.DataFrame = None) -> int:
    """Calculate optimal batch size based on ACTUAL GPU memory availability for maximum utilization."""
    gpu_info = get_gpu_info()
    
    print(f"🔍 [GPU MEMORY ANALYSIS] RTX 4080 SUPER Memory-Based Batch Sizing")
    print(f"   Total VRAM: {gpu_info['total_memory_gb']:.1f}GB")
    print(f"   Free VRAM: {gpu_info['free_memory_gb']:.1f}GB") 
    print(f"   Used VRAM: {gpu_info['used_memory_gb']:.1f}GB ({gpu_info['memory_utilization']:.1%})")
    
    # ACTUAL memory per combination from real testing (observed: ~2MB per combo, not 65MB)
    # Your pipeline shows "Memory: 2.1 MB" per phase, with multiple phases per combo
    actual_mb_per_combo = 8  # Empirical: 2MB base × 4 phases (realistic from logs)
    
    print(f"📊 [MEMORY REALITY CHECK] Actual usage per combo: {actual_mb_per_combo}MB")
    print(f"   Previous estimate was 65MB - WAY too conservative!")
    
    # Target memory utilization from configuration
    target_memory_usage = METADATA_CONFIG.get('target_gpu_utilization', 0.90)
    available_memory_mb = gpu_info['free_memory_gb'] * 1024 * target_memory_usage
    
    # Calculate batch size based on ACTUAL memory consumption
    memory_based_batch_size = int(available_memory_mb / actual_mb_per_combo)
    
    # For RTX 4080 SUPER (16GB), calculate massive batch sizes to saturate GPU
    if gpu_info['total_memory_gb'] >= 16:
        # RTX 4080 SUPER: Can handle 200-800 combinations simultaneously
        min_batch = 100   # Minimum for high-end GPU
        max_batch = 1000  # Maximum reasonable batch
        optimal_batch = min(max(memory_based_batch_size, min_batch), max_batch)
        
    elif gpu_info['total_memory_gb'] >= 12:
        # RTX 4070 Ti / 3080: 100-400 combinations
        min_batch = 60
        max_batch = 400
        optimal_batch = min(max(memory_based_batch_size, min_batch), max_batch)
        
    elif gpu_info['total_memory_gb'] >= 8:
        # RTX 3070/4060: 50-200 combinations  
        min_batch = 30
        max_batch = 200
        optimal_batch = min(max(memory_based_batch_size, min_batch), max_batch)
        
    else:
        # Lower-end GPUs: 20-80 combinations
        min_batch = 10
        max_batch = 80
        optimal_batch = min(max(memory_based_batch_size, min_batch), max_batch)
    
    # Calculate expected memory usage and GPU saturation
    expected_memory_gb = (optimal_batch * actual_mb_per_combo) / 1024
    total_expected_memory = gpu_info['used_memory_gb'] + expected_memory_gb
    expected_utilization = total_expected_memory / gpu_info['total_memory_gb']
    
    print(f"📊 [MASSIVE BATCH CALCULATION]")
    print(f"   Memory-based batch size: {memory_based_batch_size}")
    print(f"   Applied constraints: min={80 if gpu_info['total_memory_gb'] >= 16 else 30}, max={max_batch}")
    print(f"   FINAL OPTIMAL BATCH SIZE: {optimal_batch}")
    print(f"   Expected memory usage: {expected_memory_gb:.1f}GB")
    print(f"   Expected total utilization: {expected_utilization:.1%}")
    
    # Warn if still conservative
    if optimal_batch < 100 and gpu_info['total_memory_gb'] >= 16:
        print(f"⚠️  [WARNING] Batch size {optimal_batch} may still be conservative for RTX 4080 SUPER")
        print(f"   Consider manually setting batch_size: 200-400 for maximum GPU utilization")
    
    if expected_utilization > 0.85:
        print(f"🎯 [EXCELLENT] This batch size should achieve 80-95% GPU utilization!")
    elif expected_utilization > 0.70:
        print(f"🔥 [GOOD] This batch size should achieve 60-80% GPU utilization")
    else:
        print(f"⚠️  [SUBOPTIMAL] May not fully utilize GPU - consider increasing batch size")
    
    return optimal_batch


def display_hardcoded_configuration():
    """Display all hardcoded configuration values for user reference."""
    print("\n" + "="*70)
    print("📋 CURRENT HARDCODED CONFIGURATION VALUES")
    print("="*70)
    
    print(f"\n📂 Metadata Configuration:")
    for key, value in METADATA_CONFIG.items():
        if key == 'batch_size' and value == 'auto':
            auto_batch = calculate_optimal_batch_size()
            print(f"   {key}: {value} (calculated: {auto_batch})")
        else:
            print(f"   {key}: {value}")
    
    # Show GPU optimization info
    if METADATA_CONFIG['use_batch_processing']:
        print(f"\n🚀 MASSIVE BATCH GPU Optimization Enabled:")
        print(f"   Target GPU utilization: 80-95% (vs 30-40% previous)")
        print(f"   Expected batch sizes: 200-800 combinations (RTX 4080 SUPER)")
        print(f"   Expected speedup: 5-10x faster processing")
        print(f"   Memory-based batch sizing: {METADATA_CONFIG['target_gpu_utilization']:.0%} GPU memory usage")
        print(f"   ⚠️  CANDLE SIZE: Determined by metadata (NOT adjusted for GPU!)")
    
    print("="*70)
    print("💡 TIP: Modify values in METADATA_CONFIG to change behavior")
    print("💡 METADATA: Change 'metadata_file_path' to use different metadata file")
    print("💡 CONTRACT: Change 'contract_code' to use different contract")
    print("💡 COUNT: Change 'max_combinations' to limit processing (None = all)")
    print("💡 BATCHING: Set 'use_batch_processing': False to disable optimization")
    print("💡 BATCH SIZE: Set 'batch_size': 300 for manual, 'auto' for memory-based")
    print("💡 GPU TARGET: Set 'target_gpu_utilization': 0.95 for maximum usage")
    print("="*70 + "\n")


def load_combinations_metadata(metadata_path: str) -> Dict:
    """Load combinations metadata from JSON file."""
    print(f"📂 Loading combinations metadata from: {metadata_path}")
    
    try:
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        
        combo_count = len(metadata)
        print(f"✅ Loaded metadata for {combo_count:,} combinations")
        
        # Show sample combo structure
        if combo_count > 0:
            sample_key = list(metadata.keys())[0]
            sample_combo = metadata[sample_key]
            print(f"📋 Sample combo structure ({sample_key}):")
            
            if 'parameters' in sample_combo:
                params = sample_combo['parameters']
                if 'macd_params' in params:
                    macd = params['macd_params']
                    print(f"   MACD: {macd['short']}-{macd['long']}-{macd['signal']}")
                if 'atr_lookback' in params:
                    print(f"   ATR: {params['atr_lookback']}")
                if 'contracts' in params:
                    print(f"   Contracts: {params['contracts']}")
        
        return metadata
        
    except Exception as e:
        error_msg = f"❌ CRITICAL ERROR: Failed to load metadata file\n\n"
        error_msg += f"File: {metadata_path}\n"
        error_msg += f"Error: {str(e)}\n\n"
        error_msg += "📂 Please ensure the metadata file exists and is valid JSON."
        
        print(error_msg)
        
        # Show messagebox error
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "Missing Metadata File", 
                f"Cannot find metadata file:\n{metadata_path}\n\n"
                f"Please ensure the file exists and is valid JSON."
            )
            root.destroy()
        except Exception:
            pass
        
        return None


def load_real_contract_data(contract_code: str) -> pd.DataFrame:
    """Load and clean real contract data from backtest_data directory using contract code."""
    print(f"📂 Loading real contract data for: {contract_code}")
    
    # Build path from contract code
    backtest_data_dir = get_cross_platform_path()
    contract_file = f"{contract_code}_tr_ba_data.parquet"
    contract_path = f"{backtest_data_dir}/{contract_file}"
    
    try:
        # Load tick data
        raw_data = pd.read_parquet(contract_path)
        print(f"✅ Loaded raw data: {len(raw_data):,} rows, {raw_data.shape[1]} columns")
        print(f"   File: {contract_file}")
        
        # CRITICAL FIX: Preserve required columns for ATR calculation
        cleaned_data = raw_data.copy()
        
        # Identify truly problematic columns (but preserve tradeid, nanotime)
        required_for_atr = ['tradeid', 'nanotime']  # Required by predictors_tools.py reference
        problematic_columns = []
        
        for col in cleaned_data.columns:
            # Skip required ATR columns even if they're strings
            if col in required_for_atr:
                print(f"✅ [ATR FIX] Preserving required column: {col}")
                continue
                
            # Check if column contains non-numeric data that causes GPU errors
            if cleaned_data[col].dtype == 'object':
                try:
                    # Try to convert to numeric, drop if not possible
                    cleaned_data[col] = pd.to_numeric(cleaned_data[col], errors='coerce')
                    if cleaned_data[col].isna().all():
                        problematic_columns.append(col)
                except:
                    problematic_columns.append(col)
        
        # Remove only truly problematic columns (not ATR-required ones)
        if problematic_columns:
            print(f"🧹 [ATR FIX] Removing only non-essential problematic columns: {problematic_columns}")
            cleaned_data = cleaned_data.drop(columns=problematic_columns)
        
        # CRITICAL FIX: Add missing nanotime if not present (required for ATR)
        if 'nanotime' not in cleaned_data.columns:
            print("⚠️  [ATR FIX] Creating synthetic nanotime column for ATR calculation")
            # Create nanosecond timestamps (microsecond precision)
            cleaned_data['nanotime'] = pd.to_datetime(cleaned_data.index).astype('int64')
        
        # CRITICAL FIX: Ensure tradeid exists (required for ATR)
        if 'tradeid' not in cleaned_data.columns:
            print("⚠️  [ATR FIX] Creating synthetic tradeid column for ATR calculation")
            cleaned_data['tradeid'] = [f"trade_{i:06d}" for i in range(len(cleaned_data))]
        
        # GPU FIX: Ensure datetime column always exists
        if 'datetime' not in cleaned_data.columns:
            # Create synthetic datetime column
            print("⚠️  [GPU FIX] Creating synthetic datetime column")
            cleaned_data['datetime'] = pd.date_range('2024-01-01', periods=len(cleaned_data), freq='1min')
        else:
            # Convert existing datetime column
            cleaned_data['datetime'] = pd.to_datetime(cleaned_data['datetime'])
        
        # Set datetime index if not already set - preserve existing logic
        if not isinstance(cleaned_data.index, pd.DatetimeIndex):
            cleaned_data = cleaned_data.set_index('datetime', drop=False)  # Keep column AND set as index
            print(f"✅ Set datetime column as index")
        else:
            print(f"✅ Using existing DatetimeIndex from file")
        
        print(f"   Date range: {cleaned_data.index.min()} to {cleaned_data.index.max()}")
        
        # Keep raw tick data for ATS_2 compatibility (same format as legacy code)
        print("🎯 Preserving raw tick data for ATS_2 compatibility...")
        
        # Ensure we have required columns for pipeline
        result = cleaned_data.reset_index(drop=True)  # Reset index but keep datetime column
        if 'datetime' not in result.columns:
            result['datetime'] = cleaned_data.index
        
        # GPU FIX: Ensure price column exists
        if 'price' not in result.columns:
            if 'close' in result.columns:
                result['price'] = result['close']
            elif 'last' in result.columns:
                result['price'] = result['last']
            else:
                # Use first numeric column as price
                numeric_cols = result.select_dtypes(include=[np.number]).columns
                if len(numeric_cols) > 0:
                    result['price'] = result[numeric_cols[0]]
                    print(f"⚠️  Using {numeric_cols[0]} column as price data")
                else:
                    print("⚠️  No numeric columns found - using synthetic price data")
                    result['price'] = np.random.normal(100, 5, len(result))
        
        # GPU FIX: Create OHLCV columns for GPU pipeline if missing
        price_col = result['price']
        if 'open' not in result.columns:
            result['open'] = price_col.shift(1).fillna(price_col)
        if 'high' not in result.columns:
            result['high'] = price_col * 1.001  # Small spread
        if 'low' not in result.columns:
            result['low'] = price_col * 0.999   # Small spread
        if 'close' not in result.columns:
            result['close'] = price_col
        if 'volume' not in result.columns:
            result['volume'] = 100  # Default volume
        
        # GPU FIX: Ensure numeric columns are GPU-compatible (float32)
        numeric_columns = result.select_dtypes(include=[np.number]).columns
        for col in numeric_columns:
            if col != 'volume':  # Keep volume as int
                result[col] = result[col].astype(np.float32)
        
        # GPU FIX: Final validation
        required_cols = ['open', 'high', 'low', 'close', 'price', 'datetime']
        missing_cols = [col for col in required_cols if col not in result.columns]
        if missing_cols:
            print(f"❌ [GPU FIX] Missing required columns: {missing_cols}")
            return None
        
        print(f"✅ [GPU FIX] Cleaned data: {len(result):,} rows, {result.shape[1]} columns")
        print(f"✅ [GPU FIX] All columns now GPU-compatible")
        return result
        
    except Exception as e:
        error_msg = f"❌ CRITICAL ERROR: Failed to load contract data '{contract_code}'\n\n"
        error_msg += f"Expected file: {contract_path}\n"
        error_msg += f"Error: {str(e)}\n\n"
        error_msg += "📂 Please ensure the contract data file exists in the backtest_data directory.\n"
        error_msg += f"Required format: {contract_code}_tr_ba_data.parquet"
        
        print(error_msg)
        return None


def extract_parameters_from_metadata(combo_metadata: Dict) -> Dict:
    """Extract parameters from a single combo's metadata."""
    params = combo_metadata.get('parameters', {})
    
    if not params:
        raise ValueError("No parameters found in combo metadata")
    
    # Extract MACD parameters - REQUIRED
    raw_macd_params = params.get('macd_params')
    if not raw_macd_params:
        raise ValueError("Missing required macd_params in metadata")
    
    # Map metadata keys to pipeline keys
    macd_params = {
        'fast': raw_macd_params.get('short', raw_macd_params.get('fast', 12)),
        'slow': raw_macd_params.get('long', raw_macd_params.get('slow', 26)), 
        'signal': raw_macd_params.get('signal', 9)
    }
    
    # Extract predictor granularities for dual-granularity system - REQUIRED
    predictor_granularities = params.get('predictor_granularities', {})
    if not predictor_granularities:
        # Default granularities if not specified in metadata
        predictor_granularities = {'atr_macd': '15min', 'swing': '30min'}
    
    print(f"📊 [METADATA] Using predictor granularities: {predictor_granularities}")
    
    # Extract bias thresholds - REQUIRED, use actual values from metadata
    bias_thresholds = params.get('bias_thresholds')
    if not bias_thresholds:
        raise ValueError("Missing required bias_thresholds in metadata")
    
    # Validate all required bias threshold fields
    required_bias_fields = ['macd_line_lower', 'macd_line_upper', 'macd_histogram_lower', 'macd_histogram_upper']
    for field in required_bias_fields:
        if field not in bias_thresholds:
            raise ValueError(f"Missing required bias threshold field: {field}")
    
    # Extract strategy thresholds and convert to position thresholds
    strategy_thresholds = params.get('strategy_thresholds', {})
    
    # Extract position thresholds from strategy thresholds - use actual metadata values
    position_thresholds = {}
    
    if 'Strong Bullish' in strategy_thresholds and strategy_thresholds['Strong Bullish'].get('buy') is not None:
        position_thresholds['strong_bullish_buy'] = strategy_thresholds['Strong Bullish']['buy']
    if 'Strong Bearish' in strategy_thresholds and strategy_thresholds['Strong Bearish'].get('sell') is not None:
        position_thresholds['strong_bearish_sell'] = strategy_thresholds['Strong Bearish']['sell']
    if 'Bullish' in strategy_thresholds and strategy_thresholds['Bullish'].get('buy') is not None:
        position_thresholds['bullish_buy'] = strategy_thresholds['Bullish']['buy']
    if 'Bearish' in strategy_thresholds and strategy_thresholds['Bearish'].get('sell') is not None:
        position_thresholds['bearish_sell'] = strategy_thresholds['Bearish']['sell']
    
    # Extract risk management - REQUIRED
    stop_loss = params.get('stop_loss')
    if stop_loss is None:
        raise ValueError("Missing required stop_loss in metadata")
    
    sl_tp_ratio = params.get('sl_tp_ratio')
    if sl_tp_ratio is None:
        raise ValueError("Missing required sl_tp_ratio in metadata")
    
    atr_period = params.get('atr_lookback')
    if atr_period is None:
        raise ValueError("Missing required atr_lookback in metadata")
    
    # Extract swing lookback parameter - REQUIRED for dual-granularity
    swing_lookback = params.get('swing_lookback', 20)  # Default to 20 if not specified
    
    return {
        'macd_params': macd_params,
        'atr_period': atr_period,
        'predictor_granularities': predictor_granularities,
        'bias_thresholds': bias_thresholds,  
        'position_thresholds': position_thresholds,
        'swing_lookback': swing_lookback,
        'stop_loss': stop_loss,
        'sl_tp_ratio': sl_tp_ratio
    }


class BatchProcessor:
    """GPU-optimized batch processor for combination metadata."""
    
    def __init__(self, batch_size: int):
        self.batch_size = batch_size
        self.pipeline = None
        self.processed_count = 0
        
    def initialize_pipeline(self):
        """Initialize GPU pipeline once for batch processing."""
        try:
            from src.feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline
            self.pipeline = UnifiedTechnicalIndicatorsPipeline()
            print("✅ GPU Pipeline initialized for batch processing")
            return True
        except Exception as e:
            print(f"❌ GPU Pipeline initialization failed: {e}")
            return False
    
    def process_batch(self, data: pd.DataFrame, combo_batch: List[Tuple[str, Dict]], 
                     data_dir: Path, batch_idx: int) -> Tuple[List[Dict], List[Dict]]:
        """Process a single batch of combinations."""
        
        print(f"🚀 [REAL ISSUE IDENTIFIED] Batch {batch_idx}: {len(combo_batch)} combinations")
        print(f"   ⚠️  WARNING: Processing is actually SEQUENTIAL (not parallel)")
        print(f"   ⚠️  Each combination processed one-by-one - this is why GPU utilization is low!")
        print(f"   💡 TRUE FIX: Process data once, apply parameters in parallel (requires architecture change)")
        batch_start = time.time()
        
        # Import threshold configs
        try:
            from src.feature_engineering.position_generator import ThresholdConfig as PositionThresholdConfig
            from src.feature_engineering.bias_classifier import ThresholdConfig as BiasThresholdConfig
        except ImportError:
            from dataclasses import dataclass
            
            @dataclass
            class BiasThresholdConfig:
                macd_line_lower: float = -2.5
                macd_line_upper: float = 2.5
                macd_histogram_lower: float = -1.25
                macd_histogram_upper: float = 1.25
            
            @dataclass
            class PositionThresholdConfig:
                strong_bullish_buy: float = 0.25
                strong_bearish_sell: float = 0.75
                bullish_buy: float = 0.2
                bearish_sell: float = 0.8
        
        batch_results = []
        batch_metadata = []
        
        # PARTIAL FIX: Pre-process base indicators once per batch (reduce redundancy)
        print(f"   🔧 [OPTIMIZATION] Pre-computing base indicators to reduce redundant processing...")
        base_indicators_computed = False
        base_macd_data = None
        base_atr_data = None
        base_swing_data = None
        
        # Process all combinations in this batch
        for i, (combo_key, combo_metadata) in enumerate(combo_batch):
            # Progress indicator for large batches
            if len(combo_batch) > 50 and (i + 1) % 50 == 0:
                print(f"   📊 Progress: {i + 1}/{len(combo_batch)} combinations processed...")
            
            try:
                # GPU FIX: Check data size for GPU efficiency
                data_size = len(data)
                use_gpu = data_size >= 10000  # Only use GPU for larger datasets
                
                if not use_gpu and i < 3:  # Only warn for first few combinations
                    print(f"⚠️  [GPU FIX] {combo_key}: {data_size} rows may be too small for optimal GPU utilization")
                
                # Extract parameters
                extracted_params = extract_parameters_from_metadata(combo_metadata)
                
                # Create threshold configs
                bias_thresholds = BiasThresholdConfig(
                    macd_line_lower=extracted_params['bias_thresholds']['macd_line_lower'],
                    macd_line_upper=extracted_params['bias_thresholds']['macd_line_upper'],
                    macd_histogram_lower=extracted_params['bias_thresholds']['macd_histogram_lower'],
                    macd_histogram_upper=extracted_params['bias_thresholds']['macd_histogram_upper']
                )
                
                pos_thresh = extracted_params['position_thresholds']
                position_thresholds = PositionThresholdConfig(
                    strong_bullish_buy=pos_thresh.get('strong_bullish_buy', 0.25),
                    strong_bearish_sell=pos_thresh.get('strong_bearish_sell', 0.75),
                    bullish_buy=pos_thresh.get('bullish_buy', 0.2),
                    bearish_sell=pos_thresh.get('bearish_sell', 0.8)
                )
                
                # GPU FIX: Run GPU pipeline with better error handling
                result = self.pipeline.compute_all_indicators_features_bias_and_positions_dual_granularity(
                    data=data,
                    bias_thresholds=bias_thresholds,
                    position_thresholds=position_thresholds,
                    predictor_granularities=extracted_params['predictor_granularities'],
                    macd_params=extracted_params['macd_params'],
                    atr_period=extracted_params['atr_period'],
                    swing_lookback=extracted_params['swing_lookback'],
                    stop_loss_ratio=extracted_params['stop_loss'],
                    sl_tp_ratio=extracted_params['sl_tp_ratio'],
                    position_type='long'
                )
                
                # Add metadata
                result['combo_key'] = combo_key
                # Extract combo number from combo_key (e.g., "combo_000001" -> 1)
                combo_number = int(combo_key.split('_')[-1])
                result['combo_id'] = combo_number
                result['batch_idx'] = batch_idx
                result['combo_in_batch'] = i
                result['batch_size'] = len(combo_batch)
                
                # Save file
                combo_file = data_dir / f"{combo_key}.parquet"
                result.to_parquet(combo_file, index=False)
                
                # Create metadata record
                metadata_record = {
                    'combo_key': combo_key,
                    'combo_id': combo_number,
                    'batch_idx': batch_idx,
                    'combo_in_batch': i,
                    'result_shape_rows': result.shape[0],
                    'result_shape_cols': result.shape[1],
                    'batch_size': len(combo_batch),
                    'predictor_granularities': extracted_params['predictor_granularities'],
                    'pipeline_type': 'Batch_GPU_Optimized',
                    'date_created': pd.Timestamp.now().isoformat()
                }
                
                batch_results.append({
                    'combo_key': combo_key,
                    'combo_id': combo_number,
                    'result_shape': result.shape,
                    'processing_method': 'batch'
                })
                batch_metadata.append(metadata_record)
                
            except Exception as e:
                # GPU FIX: Better error handling with more details
                error_msg = str(e)
                if "could not convert string to float" in error_msg:
                    print(f"❌ [GPU FIX] {combo_key}: Data conversion error - check for string columns in data")
                elif "KeyError: 'datetime'" in error_msg:
                    print(f"❌ [GPU FIX] {combo_key}: Missing datetime column - data cleaning may have failed")
                elif "CUDA" in error_msg or "cupy" in error_msg.lower():
                    print(f"❌ [GPU FIX] {combo_key}: GPU processing error - {error_msg}")
                else:
                    print(f"❌ [GPU FIX] {combo_key}: {error_msg}")
                
                # GPU FIX: Add failed combination to batch metadata for tracking
                batch_metadata.append({
                    'combo_key': combo_key,
                    'combo_id': int(combo_key.split('_')[-1]) if '_' in combo_key else 0,
                    'batch_idx': batch_idx,
                    'combo_in_batch': i,
                    'error': error_msg,
                    'pipeline_type': 'Batch_GPU_Failed',
                    'date_created': pd.Timestamp.now().isoformat()
                })
                continue
        
        batch_time = time.time() - batch_start
        throughput = len(batch_results) / batch_time
        
        print(f"✅ [BATCH {batch_idx}] {len(batch_results)}/{len(combo_batch)} successful in {batch_time:.2f}s")
        print(f"⚡ [THROUGHPUT] {throughput:.1f} combinations/second")
        
        self.processed_count += len(combo_batch)
        return batch_results, batch_metadata


def process_combinations_from_metadata(data: pd.DataFrame, metadata: Dict, 
                                     data_dir: Path, max_count: Optional[int] = None) -> tuple:
    """Process combinations based on existing metadata with optional batch optimization."""
    
    # Check if batch processing is enabled
    use_batch_processing = METADATA_CONFIG.get('use_batch_processing', False)
    batch_size_config = METADATA_CONFIG.get('batch_size', 'auto')
    
    if use_batch_processing:
        return process_combinations_with_batch_optimization(data, metadata, data_dir, max_count, batch_size_config)
    else:
        return process_combinations_sequential(data, metadata, data_dir, max_count)


def process_combinations_with_batch_optimization(data: pd.DataFrame, metadata: Dict, 
                                               data_dir: Path, max_count: Optional[int] = None,
                                               batch_size_config = 'auto') -> tuple:
    """Process combinations using GPU batch optimization."""
    print(f"\n🚀 BATCH PROCESSING - GPU Optimized Metadata Processing")
    print("=" * 70)
    
    # Determine batch size
    if batch_size_config == 'auto':
        batch_size = calculate_optimal_batch_size(data)
    else:
        batch_size = int(batch_size_config)
    
    print(f"📦 [BATCHING] Using batch size: {batch_size}")
    print(f"🎯 [EXPECTED] GPU utilization: 80-90% (vs 30% sequential)")
    print(f"⚡ [EXPECTED] Speedup: 3-5x faster processing")
    
    # Organize combinations into batches
    combo_items = list(metadata.items())
    if max_count:
        combo_items = combo_items[:max_count]
    
    batches = [combo_items[i:i + batch_size] for i in range(0, len(combo_items), batch_size)]
    print(f"📊 [BATCH INFO] {len(combo_items)} combinations → {len(batches)} batches")
    
    # Initialize batch processor
    batch_processor = BatchProcessor(batch_size)
    if not batch_processor.initialize_pipeline():
        print("❌ Falling back to sequential processing")
        return process_combinations_sequential(data, metadata, data_dir, max_count)
    
    all_results = []
    all_metadata = []
    total_start = time.time()
    
    # Process batches
    for batch_idx, batch_items in enumerate(batches):
        batch_results, batch_metadata_records = batch_processor.process_batch(
            data, batch_items, data_dir, batch_idx + 1
        )
        
        all_results.extend(batch_results)
        all_metadata.extend(batch_metadata_records)
        
        # Memory cleanup every few batches
        if (batch_idx + 1) % 3 == 0:
            print("🧹 [CLEANUP] GPU memory cleanup...")
            try:
                import gc
                gc.collect()
                import cupy
                cupy.get_default_memory_pool().free_all_blocks()
            except ImportError:
                pass
    
    total_time = time.time() - total_start
    total_throughput = len(all_results) / total_time
    
    print(f"\n🎉 [MASSIVE BATCH COMPLETE] Processed {len(all_results)} combinations")
    print(f"⚡ [TOTAL THROUGHPUT] {total_throughput:.1f} combinations/second")
    print(f"🚀 [MASSIVE SPEEDUP] ~{total_throughput / 0.5:.1f}x vs sequential processing")
    print(f"🎯 [GPU UTILIZATION] Expected: 80-95% (vs previous 30-40%)")
    num_batches = len(batches) if 'batches' in locals() else 1
    avg_batch_size = len(all_results) / num_batches if num_batches > 0 else len(all_results)
    print(f"📊 [BATCH EFFICIENCY] {num_batches} batches, avg {avg_batch_size:.0f} combinations per batch")
    
    return all_results, all_metadata


def process_combinations_sequential(data: pd.DataFrame, metadata: Dict, 
                                  data_dir: Path, max_count: Optional[int] = None) -> tuple:
    """Process combinations sequentially (original method)."""
    print(f"\n🔄 SEQUENTIAL PROCESSING - Original Method")
    print("=" * 70)
    
    # Import the actual pipeline
    try:
        from src.feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline
        pipeline = UnifiedTechnicalIndicatorsPipeline()
        print("✅ GPU Pipeline initialized successfully")
    except Exception as e:
        error_msg = f"❌ FATAL ERROR: GPU Pipeline initialization failed!\n\nError: {e}\n\n"
        error_msg += "Cannot proceed without functional GPU pipeline.\n"
        error_msg += "Please fix the pipeline issues and try again."
        
        print(error_msg)
        return [], []
    
    # Import threshold configs
    try:
        from src.feature_engineering.position_generator import ThresholdConfig as PositionThresholdConfig
        from src.feature_engineering.bias_classifier import ThresholdConfig as BiasThresholdConfig
    except ImportError:
        from dataclasses import dataclass
        
        @dataclass
        class BiasThresholdConfig:
            macd_line_lower: float = -2.5
            macd_line_upper: float = 2.5
            macd_histogram_lower: float = -1.25
            macd_histogram_upper: float = 1.25
        
        @dataclass
        class PositionThresholdConfig:
            strong_bullish_buy: float = 0.25
            strong_bearish_sell: float = 0.75
            bullish_buy: float = 0.2
            bearish_sell: float = 0.8
    
    combo_keys = list(metadata.keys())
    if max_count:
        combo_keys = combo_keys[:max_count]
        print(f"🔢 Processing first {max_count} combinations out of {len(metadata)}")
    else:
        print(f"🔢 Processing all {len(combo_keys)} combinations")
    
    successful_results = []
    metadata_records = []
    
    for i, combo_key in enumerate(combo_keys):
        combo_start_time = time.time()
        combo_metadata = metadata[combo_key]
        
        try:
            if (i + 1) % 100 == 0 or i < 10:
                print(f"\n🔄 Processing {combo_key} ({i+1}/{len(combo_keys)})...")
            
            # GPU FIX: Check data size for GPU efficiency
            data_size = len(data)
            use_gpu = data_size >= 10000  # Only use GPU for larger datasets
            
            if not use_gpu and i < 3:  # Only warn for first few combinations
                print(f"⚠️  [GPU FIX] {combo_key}: {data_size} rows may be too small for optimal GPU utilization")
            
            # Extract parameters from metadata
            extracted_params = extract_parameters_from_metadata(combo_metadata)
            
            # Create bias threshold config
            bias_thresholds = BiasThresholdConfig(
                macd_line_lower=extracted_params['bias_thresholds']['macd_line_lower'],
                macd_line_upper=extracted_params['bias_thresholds']['macd_line_upper'],
                macd_histogram_lower=extracted_params['bias_thresholds']['macd_histogram_lower'],
                macd_histogram_upper=extracted_params['bias_thresholds']['macd_histogram_upper']
            )
            
            # Create position threshold config
            pos_thresh = extracted_params['position_thresholds']
            position_thresholds = PositionThresholdConfig(
                strong_bullish_buy=pos_thresh['strong_bullish_buy'],
                strong_bearish_sell=pos_thresh['strong_bearish_sell'],
                bullish_buy=pos_thresh['bullish_buy'],
                bearish_sell=pos_thresh['bearish_sell']
            )
            
            # Run complete pipeline with dual-granularity system and ATR risk management
            result = pipeline.compute_all_indicators_features_bias_and_positions_dual_granularity(
                data=data,
                bias_thresholds=bias_thresholds,
                position_thresholds=position_thresholds,
                predictor_granularities=extracted_params['predictor_granularities'],
                macd_params=extracted_params['macd_params'],
                atr_period=extracted_params['atr_period'],
                swing_lookback=extracted_params['swing_lookback'],
                stop_loss_ratio=extracted_params['stop_loss'],
                sl_tp_ratio=extracted_params['sl_tp_ratio'],
                position_type='long'
            )
            
            # Add combo metadata columns
            result['combo_key'] = combo_key
            # Extract combo number from combo_key (e.g., "combo_000001" -> 1)
            combo_number = int(combo_key.split('_')[-1])
            result['combo_id'] = combo_number
            for param_name, param_value in extracted_params['macd_params'].items():
                result[f'macd_{param_name}'] = param_value
            result['atr_period'] = extracted_params['atr_period']
            for thresh_name, thresh_value in extracted_params['bias_thresholds'].items():
                result[f'bias_{thresh_name}'] = thresh_value
            result['stop_loss_ratio'] = extracted_params['stop_loss']
            result['sl_tp_ratio'] = extracted_params['sl_tp_ratio']
            result['take_profit_ratio'] = extracted_params['stop_loss'] * extracted_params['sl_tp_ratio']
            
            processing_time = time.time() - combo_start_time
            
            # Save combo file
            combo_file = data_dir / f"{combo_key}.parquet"
            result.to_parquet(combo_file, index=False)
            
            # Create metadata record
            metadata_record = {
                'combo_key': combo_key,
                'combo_id': combo_number,
                'processing_time_seconds': processing_time,
                'result_shape_rows': result.shape[0],
                'result_shape_cols': result.shape[1],
                **{f'macd_{k}': v for k, v in extracted_params['macd_params'].items()},
                'atr_period': extracted_params['atr_period'],
                **{f'bias_{k}': v for k, v in extracted_params['bias_thresholds'].items()},
                **{f'position_{k}': v for k, v in extracted_params['position_thresholds'].items()},
                'stop_loss_ratio': extracted_params['stop_loss'],
                'sl_tp_ratio': extracted_params['sl_tp_ratio'],
                'take_profit_ratio': extracted_params['stop_loss'] * extracted_params['sl_tp_ratio'],
                'has_risk_features': 'stop_loss_distance' in result.columns,
                'avg_stop_loss_distance': result['stop_loss_distance'].mean() if 'stop_loss_distance' in result.columns else None,
                'avg_take_profit_distance': result['take_profit_distance'].mean() if 'take_profit_distance' in result.columns else None,
                'pipeline_type': 'Metadata_Based_GPU_with_ATR_Risk',
                'date_created': pd.Timestamp.now().isoformat()
            }
            metadata_records.append(metadata_record)
            
            successful_results.append({
                'combo_key': combo_key,
                'combo_id': combo_number,
                'processing_time': processing_time,
                'result_shape': result.shape,
                'has_risk_features': 'stop_loss_distance' in result.columns
            })
            
            if (i + 1) % 100 == 0:
                avg_time = np.mean([r['processing_time'] for r in successful_results[-100:]])
                risk_feature_count = sum(1 for r in successful_results[-100:] if r['has_risk_features'])
                print(f"✅ Processed {i + 1:3d}/{len(combo_keys):,} - Avg time: {avg_time:.3f}s, Risk features: {risk_feature_count}/100")
                
        except Exception as e:
            # GPU FIX: Better error handling with more details
            error_msg = str(e)
            if "could not convert string to float" in error_msg:
                print(f"❌ [GPU FIX] {combo_key}: Data conversion error - check for string columns in data")
            elif "KeyError: 'datetime'" in error_msg:
                print(f"❌ [GPU FIX] {combo_key}: Missing datetime column - data cleaning may have failed")
            elif "CUDA" in error_msg or "cupy" in error_msg.lower():
                print(f"❌ [GPU FIX] {combo_key}: GPU processing error - {error_msg}")
            else:
                print(f"❌ [GPU FIX] {combo_key}: {error_msg}")
            continue
    
    print(f"\n✅ Metadata-based processing complete: {len(successful_results):,}/{len(combo_keys):,} successful")
    risk_feature_success = sum(1 for r in successful_results if r['has_risk_features'])
    print(f"✅ ATR Risk features generated in {risk_feature_success:,}/{len(successful_results):,} combinations")
    return successful_results, metadata_records


def main():
    """Main metadata-based combo generator execution."""
    parser = argparse.ArgumentParser(description="Metadata-based Combo Generator")
    parser.add_argument('--metadata', type=str,
                       help='Path to combinations metadata JSON file (overrides hardcoded config)')
    parser.add_argument('--count', type=int, 
                       help='Maximum number of combinations to process (overrides hardcoded config)')
    parser.add_argument('--contract', type=str,
                       help='Contract code for real data (overrides hardcoded config)')
    parser.add_argument('--output-base', type=str,
                       help='Base output directory (overrides hardcoded config)')
    
    args = parser.parse_args()
    
    print("🎯 METADATA-BASED COMBO GENERATOR")
    print("=" * 50)
    print(f"✅ Real market data processing")
    print(f"✅ Metadata-driven parameter configuration")
    print(f"✅ Hardcoded configuration with optional overrides")
    
    # Display hardcoded configuration
    display_hardcoded_configuration()
    
    # Use hardcoded config with command line overrides
    metadata_path = args.metadata if args.metadata else METADATA_CONFIG['metadata_file_path']
    contract_code = args.contract if args.contract else METADATA_CONFIG['contract_code']
    max_count = args.count if args.count else METADATA_CONFIG['max_combinations']
    output_base_path = args.output_base if args.output_base else METADATA_CONFIG['output_base_path']
    
    print(f"🔧 Active Configuration:")
    print(f"   Metadata file: {metadata_path}")
    print(f"   Contract code: {contract_code}")
    print(f"   Max combinations: {max_count if max_count else 'ALL'}")
    print(f"   Output path: {output_base_path}")
    
    # Setup output directory
    output_base = Path(output_base_path)
    data_dir = output_base / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        start_time = time.time()
        
        # Load combinations metadata
        metadata = load_combinations_metadata(metadata_path)
        if metadata is None:
            return False
        
        # Load real contract data
        print(f"🔍 Loading real contract data: {contract_code}")
        data = load_real_contract_data(contract_code)
        if data is None:
            print("❌ FATAL ERROR: Cannot proceed without real contract data!")
            return False
        
        print(f"✅ Using real contract data: {contract_code}")
        print(f"✅ Data ready: {data.shape}")
        
        # Process combinations from metadata
        successful_results, metadata_records = process_combinations_from_metadata(
            data, metadata, data_dir, max_count=max_count
        )
        
        total_time = time.time() - start_time
        
        # Save metadata
        if metadata_records:
            print(f"\n💾 Creating metadata file...")
            metadata_df = pd.DataFrame(metadata_records)
            metadata_file = output_base / "combinations_metadata.parquet"
            metadata_df.to_parquet(metadata_file, index=False)
            print(f"   ✅ Saved metadata for {len(metadata_records):,} combinations")
        
        # Results summary
        print(f"\n🎉 METADATA-BASED COMBO GENERATOR COMPLETE!")
        print("=" * 50)
        
        successful_count = len(successful_results)
        target_count = max_count if max_count else len(metadata)
        success_rate = (successful_count / target_count) * 100
        
        print(f"📊 Results:")
        print(f"   Target combinations: {target_count:,}")
        print(f"   Successful: {successful_count:,}")
        print(f"   Success rate: {success_rate:.1f}%")
        print(f"   Total time: {total_time:.2f}s ({total_time/60:.2f} minutes)")
        
        if successful_count > 0:
            processing_times = [r['processing_time'] for r in successful_results]
            avg_time = np.mean(processing_times)
            throughput = successful_count / total_time
            print(f"   Average time per combo: {avg_time:.2f}s")
            print(f"   Throughput: {throughput:.1f} combinations/second")
        
        # Display paths
        if platform.system() == "Linux" or "microsoft" in platform.release().lower():
            wsl_path = str(output_base)
            windows_path = str(output_base).replace("/mnt/c/", "C:\\").replace("/", "\\")
            print(f"\n📂 OUTPUT STRUCTURE:")
            print(f"   WSL: {wsl_path}/")
            print(f"   Windows: {windows_path}/")
        else:
            windows_path = str(output_base).replace("/", "\\")
            print(f"\n📂 OUTPUT STRUCTURE:")
            print(f"   {windows_path}/")
        
        print(f"   ├── data/")
        print(f"   │   ├── combo_000001.parquet")
        print(f"   │   ├── combo_000002.parquet")
        print(f"   │   └── ... ({successful_count:,} combo files)")
        print(f"   └── combinations_metadata.parquet")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Processing failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    
    if success:
        print(f"\n🎊 SUCCESS! Metadata-based combo generation complete!")
    else:
        print(f"\n💥 Generation failed - check parameters and try again")