"""
Script 1: combo_generator.py - GPU Pipeline Combo Generator

Primary combo data generator with HARDCODED parameter configuration that you can modify by hand.
All trading parameters are defined as constants at the top of this file for easy customization.

🎯 HOW TO MODIFY PARAMETERS:
   1. Scroll down to the "HARDCODED INPUT PARAMETERS" section (around line 26)
   2. Modify the lists and dictionaries to change trading behavior:
      - MACD_VARIATIONS: Add/remove/modify MACD parameter combinations
      - ATR_PERIODS: Change ATR lookback period options
      - BIAS_MULTIPLIERS: Adjust bias classification sensitivity
      - NEUTRAL_BUY_BASES: Modify trading threshold options
      - STOP_LOSS_VALUES & STOP_LOSS_TO_TAKE_PROFIT_RATIOS: Risk management
      - SAMPLE_DATA_CONFIG: Change synthetic data characteristics
   3. Save the file and run - parameters will be automatically used

💡 TIP: The script displays all current parameter values when you run it,
        making it easy to see what you're working with.

Usage:
    pwsh -Command "python examples/combo_generator.py --count 1000"
    pwsh -Command "python examples/combo_generator.py --fraction 0.25"
    pwsh -Command "python examples/combo_generator.py --count 500 --config custom_params.json"
"""

import argparse
import time
import pandas as pd
import numpy as np
from pathlib import Path
import json
import itertools
import random
import os
import platform
import sys
from typing import Dict, List, Tuple, Optional, Union
import warnings
import tkinter as tk
from tkinter import messagebox
warnings.filterwarnings('ignore')

# Add project root to Python path for PowerShell compatibility
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


# ========================================================================
# HARDCODED INPUT PARAMETERS - MODIFY THESE VALUES BY HAND
# ========================================================================

# MACD Parameter Variations (Short EMA, Long EMA, Signal Period)
MACD_VARIATIONS = [
    {'short': 8, 'long': 21, 'signal': 5},
    {'short': 12, 'long': 26, 'signal': 9},    # Standard MACD
    {'short': 5, 'long': 35, 'signal': 5},
    {'short': 19, 'long': 39, 'signal': 9},
    {'short': 6, 'long': 18, 'signal': 6},
    {'short': 10, 'long': 30, 'signal': 8},
    {'short': 15, 'long': 45, 'signal': 12},
    {'short': 7, 'long': 24, 'signal': 7},
    {'short': 9, 'long': 27, 'signal': 10},
    {'short': 11, 'long': 33, 'signal': 11}
]

# ATR Lookback Period Options
ATR_PERIODS = [21]

# Bias Threshold Ranges - Symmetric pairs matching ATS_2 strategy_parameter_sweep.py
def generate_symmetric_pairs(max_value, step):
    """Generate symmetric pairs from max_value down to step, e.g., (-2.5,2.5), (-2,2), etc."""
    pairs = []
    current = max_value
    while current >= step:
        pairs.append((-current, current))
        current -= step
    return pairs

BIAS_THRESHOLD_RANGES = {
    'macd_line_pairs': generate_symmetric_pairs(2.5, 0.5),        # [(-2.5,2.5), (-2,2), (-1.5,1.5), (-1,1), (-0.5,0.5)]
    'macd_histogram_pairs': generate_symmetric_pairs(1.25, 0.25)  # [(-1.25,1.25), (-1,1), (-0.75,0.75), (-0.5,0.5), (-0.25,0.25)]
}

# Strategy Trading Thresholds - Proportional Buy/Sell System
NEUTRAL_BUY_BASES = [0.10, 0.15, 0.20, 0.25, 0.30]  # Base buy threshold options
# NEUTRAL_SELL is calculated as (1.0 - neutral_buy_base) for proportional thresholds
# This ensures buy + sell = 1.0 for balanced trading:
#   0.10 buy → 0.90 sell
#   0.15 buy → 0.85 sell  
#   0.20 buy → 0.80 sell
#   0.25 buy → 0.75 sell
#   0.30 buy → 0.70 sell

# Position Signal Threshold Adjustments - Multiple Options (Legacy Pattern)
# All adjustment arrays have same length (4 options) for balanced combinatorial generation
# LOGIC: Buy thresholds - lower = more aggressive, Sell thresholds - higher = more aggressive
POSITION_ADJUSTMENTS = {
    'strong_bullish_buy_adjustments': [0.0, 0.05, 0.1, 0.15],        # Added to neutral_buy (positive = less aggressive than bullish)
    'bullish_buy_adjustments': [-0.05, 0.0, 0.05, 0.1],             # Added to neutral_buy (can be more/less aggressive than neutral)
    'bearish_buy_adjustments': [-0.15, -0.1, -0.05, 0.0],           # Added to neutral_buy for bearish conditions (negative = more aggressive)
    'strong_bearish_sell_adjustments': [-0.15, -0.1, -0.05, 0.0],   # Added to neutral_sell (negative = more aggressive than bearish)
    'bearish_sell_adjustments': [-0.1, -0.05, 0.0, 0.05],           # Added to neutral_sell (can be more/less aggressive than neutral)
    'bullish_sell_adjustments': [0.0, 0.05, 0.1, 0.15]              # Added to neutral_sell for bullish conditions (positive = less aggressive)
}

# Risk Management Parameters
STOP_LOSS_VALUES = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
STOP_LOSS_TO_TAKE_PROFIT_RATIOS = [1.0, 1.2, 1.5, 1.8, 2.0, 2.2]

# Removed SAMPLE_DATA_CONFIG - Real data only

# Removed TIME_SETTINGS and PROCESSING_CONFIG - were only used for synthetic data


def get_cross_platform_path() -> str:
    """Get the correct backtest data path for both WSL and PowerShell/Windows."""
    if platform.system() == "Linux" or "microsoft" in platform.release().lower():
        # WSL environment
        return "/mnt/c/Users/krajcovic/Documents/Testing Data/backtest_data"
    else:
        # Windows PowerShell/CMD environment
        return r"C:\Users\krajcovic\Documents\Testing Data\backtest_data"


# Real Data Configuration - MODIFY THIS TO CHANGE CONTRACT
REAL_DATA_CONFIG = {
    'contract_code': 'dem07_25',         # CONTRACT TO USE: dem07_25, dem08_25, etc.
    'backtest_data_dir': get_cross_platform_path()
}

# Combination Generation Settings - MODIFY THESE TO CHANGE RUN SIZE
COMBINATION_CONFIG = {
    'use_count': True,                   # Set to True for exact count, False for fraction
    'count': 1000,                        # EXACT NUMBER: How many combinations to run
    'fraction': 0.1                      # FRACTION: What percentage to run (0.0-1.0)
    # NOTE: Only one of count/fraction will be used based on 'use_count' flag
}

# ========================================================================
# END HARDCODED PARAMETERS
# ========================================================================


def load_real_contract_data(contract_code: str) -> pd.DataFrame:
    """Load real contract data from backtest_data directory using contract code."""
    print(f"📂 Loading real contract data for: {contract_code}")
    
    # Build path from contract code using hardcoded config
    backtest_data_dir = REAL_DATA_CONFIG['backtest_data_dir']
    contract_file = f"{contract_code}_tr_ba_data.parquet"
    contract_path = f"{backtest_data_dir}/{contract_file}"
    
    try:
        # Load tick data
        tick_data = pd.read_parquet(contract_path)
        print(f"✅ Loaded real data: {len(tick_data):,} rows")
        print(f"   File: {contract_file}")
        print(f"   Columns: {list(tick_data.columns)}")
        
        # Set datetime index if not already set - FIXED LOGIC
        if not isinstance(tick_data.index, pd.DatetimeIndex):
            if 'datetime' in tick_data.columns:
                tick_data = tick_data.set_index('datetime')
                print(f"✅ Set datetime column as index")
            else:
                # Only create fake dates if truly no datetime info exists
                print(f"⚠️  No datetime column found - creating synthetic timestamps")
                tick_data.index = pd.date_range('2024-01-01', periods=len(tick_data), freq='1min')
        else:
            print(f"✅ Using existing DatetimeIndex from file")
        
        print(f"   Date range: {tick_data.index.min()} to {tick_data.index.max()}")
        
        # Convert tick data to OHLCV candles (15-minute)
        print("🔄 Converting tick data to 15-minute OHLCV format...")
        
        ohlcv_data = tick_data['price'].resample('15T').agg({
            'open': 'first',
            'high': 'max', 
            'low': 'min',
            'close': 'last'
        }).dropna()
        
        # Add volume
        if 'volume' in tick_data.columns:
            volume_data = tick_data['volume'].resample('15T').sum()
            ohlcv_data['volume'] = volume_data.fillna(1500)
        else:
            ohlcv_data['volume'] = np.random.exponential(1500, len(ohlcv_data))
        
        # Reset index and format for pipeline
        result = ohlcv_data.reset_index()
        result.rename(columns={'index': 'Datetime'}, inplace=True)
        
        print(f"✅ Converted to OHLCV: {result.shape}")
        return result
        
    except Exception as e:
        error_msg = f"❌ CRITICAL ERROR: Failed to load contract data '{contract_code}'\n\n"
        error_msg += f"Expected file: {contract_path}\n"
        error_msg += f"Error: {str(e)}\n\n"
        error_msg += "📂 Please ensure the contract data file exists in the backtest_data directory.\n"
        error_msg += f"Required format: {contract_code}_tr_ba_data.parquet"
        
        print(error_msg)
        
        # Show messagebox error
        try:
            root = tk.Tk()
            root.withdraw()  # Hide the main window
            messagebox.showerror(
                "Missing Contract Data", 
                f"Cannot find contract data file:\n{contract_path}\n\n"
                f"Please ensure '{contract_code}_tr_ba_data.parquet' exists in:\n"
                f"{REAL_DATA_CONFIG['backtest_data_dir']}"
            )
            root.destroy()
        except Exception:
            pass  # If GUI not available, just print error
        
        return None


# Import for threshold configurations (using simulated approach)
try:
    from src.feature_engineering.position_generator import ThresholdConfig as PositionThresholdConfig
    from src.feature_engineering.bias_classifier import ThresholdConfig as BiasThresholdConfig
except ImportError:
    # Create mock threshold configs if imports fail
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


# Removed create_sample_ohlcv_data - Real data only


def get_default_parameter_ranges() -> Dict:
    """Get parameter ranges from hardcoded configurations."""
    print("Building parameter ranges from hardcoded constants...")
    
    # Extract unique values from MACD variations
    macd_shorts = sorted(list(set(var['short'] for var in MACD_VARIATIONS)))
    macd_longs = sorted(list(set(var['long'] for var in MACD_VARIATIONS)))
    macd_signals = sorted(list(set(var['signal'] for var in MACD_VARIATIONS)))
    
    # Generate bias threshold combinations from symmetric pairs
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
    
    param_ranges = {
        'macd_short': macd_shorts,               # From MACD_VARIATIONS
        'macd_long': macd_longs,                 # From MACD_VARIATIONS
        'macd_signal': macd_signals,             # From MACD_VARIATIONS
        'atr_period': ATR_PERIODS,               # Direct from hardcoded ATR_PERIODS
        'bias_thresholds': bias_combinations,    # Generated from symmetric pairs
        'neutral_buy_base': NEUTRAL_BUY_BASES,   # Direct from hardcoded NEUTRAL_BUY_BASES
        'strong_bullish_buy_adj': POSITION_ADJUSTMENTS['strong_bullish_buy_adjustments'],
        'strong_bearish_sell_adj': POSITION_ADJUSTMENTS['strong_bearish_sell_adjustments'],
        'bullish_buy_adj': POSITION_ADJUSTMENTS['bullish_buy_adjustments'],
        'bearish_sell_adj': POSITION_ADJUSTMENTS['bearish_sell_adjustments'],
        'bearish_buy_adj': POSITION_ADJUSTMENTS['bearish_buy_adjustments'],
        'bullish_sell_adj': POSITION_ADJUSTMENTS['bullish_sell_adjustments'],
        'stop_loss': STOP_LOSS_VALUES,           # Direct from hardcoded STOP_LOSS_VALUES
        'sl_tp_ratio': STOP_LOSS_TO_TAKE_PROFIT_RATIOS  # Direct from hardcoded ratios
    }
    
    print(f"✅ Parameter ranges built from hardcoded constants:")
    for param, values in param_ranges.items():
        if param == 'bias_thresholds':
            print(f"   {param}: {len(values)} combinations")
        else:
            print(f"   {param}: {len(values)} options {values}")
    
    return param_ranges


def display_hardcoded_parameters():
    """Display all hardcoded parameters for user reference."""
    print("\n" + "="*70)
    print("📋 CURRENT HARDCODED PARAMETER VALUES")
    print("="*70)
    
    print(f"\n🎯 MACD Variations ({len(MACD_VARIATIONS)} combinations):")
    for i, var in enumerate(MACD_VARIATIONS):
        marker = " ← Standard" if var == {'short': 12, 'long': 26, 'signal': 9} else ""
        print(f"   {i+1:2d}. Short: {var['short']:2d}, Long: {var['long']:2d}, Signal: {var['signal']:2d}{marker}")
    
    print(f"\n📊 ATR Periods ({len(ATR_PERIODS)} options):")
    print(f"   {ATR_PERIODS}")
    
    print(f"\n⚖️  Bias Configuration:")
    print(f"   MACD Line Pairs ({len(BIAS_THRESHOLD_RANGES['macd_line_pairs'])} options): {BIAS_THRESHOLD_RANGES['macd_line_pairs']}")
    print(f"   MACD Histogram Pairs ({len(BIAS_THRESHOLD_RANGES['macd_histogram_pairs'])} options): {BIAS_THRESHOLD_RANGES['macd_histogram_pairs']}")
    total_bias_combos = len(BIAS_THRESHOLD_RANGES['macd_line_pairs']) * len(BIAS_THRESHOLD_RANGES['macd_histogram_pairs'])
    print(f"   Total Bias Combinations: {total_bias_combos}")
    
    print(f"\n💹 Strategy Thresholds:")
    print(f"   Neutral Buy Bases ({len(NEUTRAL_BUY_BASES)} options): {NEUTRAL_BUY_BASES}")
    print(f"   Proportional Sell Calculation: sell = 1.0 - buy")
    print(f"   Examples: 0.10 buy → 0.90 sell, 0.20 buy → 0.80 sell, 0.25 buy → 0.75 sell")
    
    print(f"\n🎯 Position Adjustments (Legacy Pattern):")
    for adj_type, values in POSITION_ADJUSTMENTS.items():
        print(f"   {adj_type}: {len(values)} options {values}")
    
    print(f"\n🛡️  Risk Management:")
    print(f"   Stop Loss Values ({len(STOP_LOSS_VALUES)} options): {STOP_LOSS_VALUES}")
    print(f"   SL/TP Ratios ({len(STOP_LOSS_TO_TAKE_PROFIT_RATIOS)} options): {STOP_LOSS_TO_TAKE_PROFIT_RATIOS}")
    
# Removed sample data config display - Real data only
    
# Removed TIME_SETTINGS and PROCESSING_CONFIG display - were only used for synthetic data
    
    print(f"\n📊 Real Data Config:")
    for key, value in REAL_DATA_CONFIG.items():
        print(f"   {key}: {value}")
    
    print(f"\n🔢 Combination Config:")
    for key, value in COMBINATION_CONFIG.items():
        print(f"   {key}: {value}")
    
    mode = "EXACT COUNT" if COMBINATION_CONFIG['use_count'] else "FRACTION"
    active_value = COMBINATION_CONFIG['count'] if COMBINATION_CONFIG['use_count'] else COMBINATION_CONFIG['fraction']
    print(f"   Active Mode: {mode} = {active_value}")
    
    print("="*70)
    print("💡 TIP: Modify values at the top of this script to change behavior")
    print("💡 CONTRACT: Change REAL_DATA_CONFIG['contract_code'] to use different contract")
    print("💡 COMBINATIONS: Change COMBINATION_CONFIG values to control run size")
    print("="*70 + "\n")


def load_parameter_config(config_path: Optional[str] = None) -> Dict:
    """Load parameter ranges from config file or use hardcoded defaults."""
    if config_path and Path(config_path).exists():
        print(f"Loading custom parameter config from: {config_path}")
        with open(config_path, 'r') as f:
            return json.load(f)
    else:
        print("Using hardcoded parameter ranges")
        return get_default_parameter_ranges()


def generate_parameter_combinations(param_ranges: Dict, count: Optional[int] = None, 
                                   fraction: Optional[float] = None) -> List[Dict]:
    """Generate parameter combinations based on count or fraction."""
    
    # Calculate total possible combinations
    total_possible = 1
    for param, values in param_ranges.items():
        total_possible *= len(values)
    
    print(f"Total possible combinations: {total_possible:,}")
    
    # Determine target count
    if count is not None:
        target_count = min(count, total_possible)
        print(f"Target count: {target_count:,} (absolute)")
    elif fraction is not None:
        target_count = int(total_possible * fraction)
        print(f"Target count: {target_count:,} ({fraction:.1%} of total)")
    else:
        raise ValueError("Must specify either count or fraction")
    
    # Generate combinations as generator to avoid memory issues
    param_names = list(param_ranges.keys())
    param_values = [param_ranges[name] for name in param_names]
    all_combinations_gen = itertools.product(*param_values)
    
    # Sample if needed
    if target_count < total_possible:
        print(f"Sampling {target_count:,} combinations from {total_possible:,} total")
        # Convert to list only for the selected subset
        all_combinations_list = []
        for i, combo in enumerate(all_combinations_gen):
            all_combinations_list.append(combo)
            if (i + 1) % 10000 == 0:  # Progress indicator
                print(f"   Generated {i + 1:,} combinations...")
            if len(all_combinations_list) >= min(target_count * 10, total_possible):  # Get more than needed for sampling
                break
        
        selected_combinations = random.sample(all_combinations_list, min(target_count, len(all_combinations_list)))
    else:
        # If we need all combinations, convert generator to list
        print(f"Converting all {total_possible:,} combinations to list...")
        selected_combinations = list(all_combinations_gen)
    
    # Convert to list of dictionaries
    combinations = []
    for i, combo_values in enumerate(selected_combinations):
        combo = {param_names[j]: combo_values[j] for j in range(len(param_names))}
        combo['combo_id'] = i
        combinations.append(combo)
    
    print(f"Generated {len(combinations):,} parameter combinations")
    return combinations


def create_bias_thresholds(bias_thresholds: Dict) -> BiasThresholdConfig:
    """Create bias threshold configuration using symmetric pairs."""
    return BiasThresholdConfig(
        macd_line_lower=bias_thresholds['macd_line_lower'],
        macd_line_upper=bias_thresholds['macd_line_upper'],
        macd_histogram_lower=bias_thresholds['macd_histogram_lower'],
        macd_histogram_upper=bias_thresholds['macd_histogram_upper']
    )


def create_position_thresholds(neutral_buy_base: float, strong_bullish_buy_adj: float = 0.05, 
                              strong_bearish_sell_adj: float = 0.05, bullish_buy_adj: float = 0.0, 
                              bearish_sell_adj: float = 0.0, bearish_buy_adj: float = 0.0, 
                              bullish_sell_adj: float = 0.05) -> PositionThresholdConfig:
    """Create position threshold configuration using proportional buy/sell thresholds with adjustments."""
    
    # Proportional sell threshold: 1.0 - buy_base (0.1 buy → 0.9 sell, 0.2 buy → 0.8 sell)
    neutral_sell_base = 1.0 - neutral_buy_base
    
    return PositionThresholdConfig(
        strong_bullish_buy=neutral_buy_base + strong_bullish_buy_adj,
        strong_bearish_sell=neutral_sell_base + strong_bearish_sell_adj,
        bullish_buy=neutral_buy_base + bullish_buy_adj,
        bearish_sell=neutral_sell_base + bearish_sell_adj
        # Note: bearish_buy_adj and bullish_sell_adj would be used if PositionThresholdConfig had those fields
    )


def process_combinations_with_actual_gpu_pipeline(data: pd.DataFrame, combinations: List[Dict], 
                                                data_dir: Path) -> Tuple[List[Dict], List[Dict]]:
    """Process parameter combinations with the actual GPU pipeline including ATR risk management."""
    print(f"\n🚀 Processing {len(combinations):,} combinations with ACTUAL GPU PIPELINE + ATR Risk Management")
    print("=" * 70)
    print("✅ Using real UnifiedTechnicalIndicatorsPipeline with ATR risk features")
    
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
        
        # Show messagebox error
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "GPU Pipeline Error", 
                f"GPU Pipeline initialization failed:\n{e}\n\n"
                f"Please fix the pipeline and try again."
            )
            root.destroy()
        except Exception:
            pass
        
        return [], []
    
    successful_results = []
    metadata_records = []
    
    for i, combo in enumerate(combinations):
        combo_start_time = time.time()
        combo_id = combo['combo_id']
        
        try:
            if (i + 1) % 100 == 0 or i < 10:
                print(f"\n🔄 Processing combo {combo_id:3d}/{len(combinations):,}...")
                print(f"   MACD: {combo['macd_short']}-{combo['macd_long']}-{combo['macd_signal']}")
                print(f"   ATR: {combo['atr_period']}, Risk: SL={combo['stop_loss']}, TP={combo['sl_tp_ratio']}")
            
            # Create bias and position thresholds
            bias_thresholds = create_bias_thresholds(combo['bias_thresholds'])
            position_thresholds = create_position_thresholds(
                combo['neutral_buy_base'],
                strong_bullish_buy_adj=combo['strong_bullish_buy_adj'],
                strong_bearish_sell_adj=combo['strong_bearish_sell_adj'],
                bullish_buy_adj=combo['bullish_buy_adj'],
                bearish_sell_adj=combo['bearish_sell_adj'],
                bearish_buy_adj=combo['bearish_buy_adj'],
                bullish_sell_adj=combo['bullish_sell_adj']
            )
            
            # Create MACD parameters
            macd_params = {
                'fast': combo['macd_short'],
                'slow': combo['macd_long'], 
                'signal': combo['macd_signal']
            }
            
            # Run complete pipeline with ATR risk management
            result = pipeline.compute_all_indicators_features_bias_and_positions(
                data=data,
                bias_thresholds=bias_thresholds,
                position_thresholds=position_thresholds,
                macd_params=macd_params,
                atr_period=combo['atr_period'],
                # ATR Risk Management parameters
                stop_loss_ratio=combo['stop_loss'],
                sl_tp_ratio=combo['sl_tp_ratio'],
                position_type='long'  # Default to long positions
            )
            
            # Add combo metadata columns
            result['combo_id'] = combo_id
            result['macd_short'] = combo['macd_short']
            result['macd_long'] = combo['macd_long']
            result['macd_signal'] = combo['macd_signal']
            result['atr_period'] = combo['atr_period']
            result['bias_macd_line_lower'] = combo['bias_thresholds']['macd_line_lower']
            result['bias_macd_line_upper'] = combo['bias_thresholds']['macd_line_upper']
            result['bias_macd_histogram_lower'] = combo['bias_thresholds']['macd_histogram_lower']
            result['bias_macd_histogram_upper'] = combo['bias_thresholds']['macd_histogram_upper']
            result['neutral_buy_base'] = combo['neutral_buy_base']
            result['stop_loss_ratio'] = combo['stop_loss']
            result['sl_tp_ratio'] = combo['sl_tp_ratio']
            result['take_profit_ratio'] = combo['stop_loss'] * combo['sl_tp_ratio']
            
            processing_time = time.time() - combo_start_time
            
            # Save combo file
            combo_file = data_dir / f"combo_{combo_id:03d}.parquet"
            result.to_parquet(combo_file, index=False)
            
            # Create enhanced metadata record with actual risk calculations
            metadata_record = {
                'combo_id': combo_id,
                'processing_time_seconds': processing_time,
                'result_shape_rows': result.shape[0],
                'result_shape_cols': result.shape[1],
                'macd_short': combo['macd_short'],
                'macd_long': combo['macd_long'],
                'macd_signal': combo['macd_signal'],
                'atr_period': combo['atr_period'],
                'bias_macd_line_lower': bias_thresholds.macd_line_lower,
                'bias_macd_line_upper': bias_thresholds.macd_line_upper,
                'bias_macd_histogram_lower': bias_thresholds.macd_histogram_lower,
                'bias_macd_histogram_upper': bias_thresholds.macd_histogram_upper,
                'neutral_buy_base': combo['neutral_buy_base'],
                'position_strong_bullish_buy': position_thresholds.strong_bullish_buy,
                'position_strong_bearish_sell': position_thresholds.strong_bearish_sell,
                'position_bullish_buy': position_thresholds.bullish_buy,
                'position_bearish_sell': position_thresholds.bearish_sell,
                'stop_loss_ratio': combo['stop_loss'],
                'sl_tp_ratio': combo['sl_tp_ratio'],
                'take_profit_ratio': combo['stop_loss'] * combo['sl_tp_ratio'],
                # Enhanced with actual risk statistics
                'has_risk_features': 'stop_loss_distance' in result.columns,
                'avg_stop_loss_distance': result['stop_loss_distance'].mean() if 'stop_loss_distance' in result.columns else None,
                'avg_take_profit_distance': result['take_profit_distance'].mean() if 'take_profit_distance' in result.columns else None,
                'pipeline_type': 'Actual_GPU_with_ATR_Risk',
                'date_created': pd.Timestamp.now().isoformat()
            }
            metadata_records.append(metadata_record)
            
            successful_results.append({
                'combo_id': combo_id,
                'processing_time': processing_time,
                'result_shape': result.shape,
                'has_risk_features': 'stop_loss_distance' in result.columns
            })
            
            if (i + 1) % 100 == 0:
                avg_time = np.mean([r['processing_time'] for r in successful_results[-100:]])
                risk_feature_count = sum(1 for r in successful_results[-100:] if r['has_risk_features'])
                print(f"✅ Processed {i + 1:3d}/{len(combinations):,} - Avg time: {avg_time:.3f}s, Risk features: {risk_feature_count}/100")
                
        except Exception as e:
            print(f"❌ Error processing combo {combo_id}: {e}")
            continue
    
    print(f"\n✅ Actual GPU pipeline processing complete: {len(successful_results):,}/{len(combinations):,} successful")
    risk_feature_success = sum(1 for r in successful_results if r['has_risk_features'])
    print(f"✅ ATR Risk features generated in {risk_feature_success:,}/{len(successful_results):,} combinations")
    return successful_results, metadata_records


# Removed process_combinations_with_simulated_gpu_data - Real pipeline only


def main():
    """Main combo generator execution."""
    parser = argparse.ArgumentParser(description="GPU Pipeline Combo Generator")
    parser.add_argument('--count', type=int, help='Absolute number of combinations to generate')
    parser.add_argument('--fraction', type=float, help='Fraction of total combinations to generate (0.0-1.0)')
    parser.add_argument('--config', type=str, help='Path to custom parameter config JSON file')
# Removed --data-size parameter - Real data only
    parser.add_argument('--contract', type=str, help='Contract code for real data (e.g., "dem07_25")')
    
    # Get cross-platform default output path
    if platform.system() == "Linux" or "microsoft" in platform.release().lower():
        default_output = "/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data"
    else:
        default_output = r"C:\Users\krajcovic\Documents\Testing Data\ATS_3_data"
    
    parser.add_argument('--output-base', type=str, 
                       default=default_output,
                       help='Base output directory')
    
    args = parser.parse_args()
    
    # Validate arguments - Allow hardcoded config or command line override
    if args.count is not None and args.fraction is not None:
        print("❌ Cannot specify both --count and --fraction")
        return False
    
    if args.fraction is not None and (args.fraction <= 0 or args.fraction > 1):
        print("❌ Fraction must be between 0.0 and 1.0")
        return False
    
    # If no command line args, validate hardcoded config
    if args.count is None and args.fraction is None:
        if COMBINATION_CONFIG['use_count']:
            if COMBINATION_CONFIG['count'] <= 0:
                print(f"❌ Hardcoded count must be > 0, got: {COMBINATION_CONFIG['count']}")
                return False
        else:
            if COMBINATION_CONFIG['fraction'] <= 0 or COMBINATION_CONFIG['fraction'] > 1:
                print(f"❌ Hardcoded fraction must be between 0.0 and 1.0, got: {COMBINATION_CONFIG['fraction']}")
                return False
    
    print("🎯 GPU PIPELINE COMBO GENERATOR")
    print("=" * 50)
    print(f"✅ Real market data processing only")
    print(f"✅ Hardcoded parameter configuration")
    print(f"✅ Clean output organization")
    
    # Display all hardcoded parameters for user reference
    display_hardcoded_parameters()
    
    # Setup output directory
    output_base = Path(args.output_base)
    data_dir = output_base / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Display paths for both environments
    if platform.system() == "Linux" or "microsoft" in platform.release().lower():
        # WSL environment - show both paths
        wsl_path = str(output_base)
        windows_path = str(output_base).replace("/mnt/c/", "C:\\").replace("/", "\\")
        print(f"\n📁 Output Structure:")
        print(f"   WSL: {wsl_path}/")
        print(f"   Windows: {windows_path}/")
        print(f"   Data folder: data/")
        print(f"   Metadata: combinations_metadata.parquet")
    else:
        # Windows environment
        windows_path = str(output_base).replace("/", "\\")
        print(f"\n📁 Output Structure:")
        print(f"   Path: {windows_path}/")
        print(f"   Data folder: {windows_path}\\data\\")
        print(f"   Metadata: {windows_path}\\combinations_metadata.parquet")
    
    try:
        start_time = time.time()
        
        # Load parameter configuration
        param_ranges = load_parameter_config(args.config)
        
        # Generate parameter combinations - Use hardcoded config or command line override
        if args.count is not None or args.fraction is not None:
            # Command line override
            combinations = generate_parameter_combinations(
                param_ranges, 
                count=args.count, 
                fraction=args.fraction
            )
        else:
            # Use hardcoded COMBINATION_CONFIG
            if COMBINATION_CONFIG['use_count']:
                print(f"🔢 Using hardcoded count: {COMBINATION_CONFIG['count']}")
                combinations = generate_parameter_combinations(
                    param_ranges, 
                    count=COMBINATION_CONFIG['count'], 
                    fraction=None
                )
            else:
                print(f"🔢 Using hardcoded fraction: {COMBINATION_CONFIG['fraction']}")
                combinations = generate_parameter_combinations(
                    param_ranges, 
                    count=None, 
                    fraction=COMBINATION_CONFIG['fraction']
                )
        
        # Load real contract data - NO FALLBACK TO SYNTHETIC
        contract_to_use = args.contract if args.contract else REAL_DATA_CONFIG['contract_code']
        print(f"🔍 Loading real contract data: {contract_to_use}")
        
        data = load_real_contract_data(contract_to_use)
        if data is None:
            error_msg = f"❌ FATAL ERROR: Cannot proceed without real contract data!"
            print(error_msg)
            return False
        
        print(f"✅ Using real contract data: {contract_to_use}")
        print(f"✅ Data ready: {data.shape}")
        
        # Process combinations with actual GPU pipeline including ATR risk management
        successful_results, metadata_records = process_combinations_with_actual_gpu_pipeline(
            data, combinations, data_dir
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
        print(f"\n🎉 GPU COMBO GENERATOR COMPLETE!")
        print("=" * 50)
        
        successful_count = len(successful_results)
        success_rate = (successful_count / len(combinations)) * 100
        
        print(f"📊 Results:")
        print(f"   Target combinations: {len(combinations):,}")
        print(f"   Successful: {successful_count:,}")
        print(f"   Success rate: {success_rate:.1f}%")
        print(f"   Total time: {total_time:.2f}s ({total_time/60:.2f} minutes)")
        
        if successful_count > 0:
            processing_times = [r['processing_time'] for r in successful_results]
            avg_time = np.mean(processing_times)
            throughput = successful_count / total_time
            print(f"   Average time per combo: {avg_time:.2f}s")
            print(f"   Throughput: {throughput:.1f} combinations/second")
        
        # Final file structure - cross-platform display
        print(f"\n📂 CLEAN OUTPUT STRUCTURE:")
        if platform.system() == "Linux" or "microsoft" in platform.release().lower():
            print(f"   WSL: {wsl_path}/")
            print(f"   Windows: {windows_path}/")
        else:
            print(f"   {windows_path}/")
        print(f"   ├── data/")
        print(f"   │   ├── combo_000.parquet")
        print(f"   │   ├── combo_001.parquet")
        print(f"   │   └── ... ({successful_count:,} combo files)")
        print(f"   └── combinations_metadata.parquet")
        
        print(f"\n🚀 GPU Pipeline Features:")
        print(f"   ✅ Phase 3: Technical indicators (MACD, ATR, swing points)")  
        print(f"   ✅ Phase 4: Feature normalization and engineering")
        print(f"   ✅ Phase 5: Bias classification (-2 to +2 scale)")
        print(f"   ✅ Phase 6: Position signal generation (-1, 0, 1)")
        print(f"   ✅ ATR Risk Management: Stop loss/take profit distances & levels")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Processing failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    
    if success:
        print(f"\n🎊 SUCCESS! GPU combo generation complete!")
        # Display result path based on environment
        if platform.system() == "Linux" or "microsoft" in platform.release().lower():
            # WSL environment
            default_wsl = "/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data"
            default_win = "C:\\Users\\krajcovic\\Documents\\Testing Data\\ATS_3_data"
            print(f"📂 Results (WSL): {default_wsl}")
            print(f"📂 Results (Windows): {default_win}")
        else:
            # Windows environment
            default_win = "C:\\Users\\krajcovic\\Documents\\Testing Data\\ATS_3_data"
            print(f"📂 Results: {default_win}")
        print(f"\n🚀 READY FOR:")
        print(f"   Next: pwsh -Command \"python examples/legacy_generator.py\"")
        print(f"   Or: pwsh -Command \"python examples/combo_comparator.py\"")
    else:
        print(f"\n💥 Generation failed - check parameters and try again")