#!/usr/bin/env python3
r"""
Comprehensive Parameter Combinations Test Using Real Market Data
================================================================

This script creates and processes 1,250 parameter combinations using the corrected Phase 2 GPU pipeline.
It demonstrates the GPU-accelerated technical indicators (ATR and MACD) in action with real market data.

Parameter Space:
- Candle Granularity: [5, 10, 15, 20, 25] minutes (5 options)
- ATR Periods: [14, 21] (2 options)  
- MACD Parameters: se=[8,9,10,11,12], le=[16,20,26,32,38], signal=[6,9,12,15,18] (5×5×5=125 options)
- Total: 5 × 2 × 125 = 1,250 combinations

Output: Saves results to C:\Users\krajcovic\Documents\Testing Data\ATS_3_data\interim_test
"""

import pandas as pd
import numpy as np
import sys
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
import json
from typing import List, Dict, Tuple
import warnings
warnings.filterwarnings('ignore')

# Add source paths based on execution environment
def setup_project_paths():
    """Setup project import paths based on execution environment"""
    import os
    import sys
    from pathlib import Path
    
    # Get the actual project root (where this script is located relative to sandbox/experiments/)
    current_file = Path(__file__).resolve()
    project_root = current_file.parent.parent.parent  # Go up from sandbox/experiments/ to project root
    
    # Add project paths for imports
    src_path = project_root / "src"
    utilities_path = project_root / "source_repos" / "EnergyTrading" / "Python" / "Utilities"
    
    # Convert to strings and add to sys.path if they exist
    if src_path.exists():
        sys.path.insert(0, str(src_path))
        print(f"✓ Added src path: {src_path}")
    else:
        print(f"⚠️  Src path not found: {src_path}")
    
    if utilities_path.exists():
        sys.path.insert(0, str(utilities_path))
        print(f"✓ Added utilities path: {utilities_path}")
    
    # Also add project root to ensure relative imports work
    sys.path.insert(0, str(project_root))
    print(f"✓ Added project root: {project_root}")

# Setup paths
setup_project_paths()

def detect_environment_and_get_paths():
    """Detect if running in WSL or PowerShell and return appropriate paths"""
    import platform
    import sys
    import subprocess
    
    # PRIMARY: WSL detection (Linux environment with Windows access)
    if os.path.exists('/mnt/c/') and os.name == 'posix':
        # Running in WSL - use WSL paths
        print("🐧 Detected WSL environment")
        data_path = Path("/mnt/c/Users/krajcovic/Documents/Testing Data/backtest_data/dem07_25_tr_ba_data.parquet")
        output_path = Path("/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data/interim_test")
        return data_path, output_path, "WSL"
    
    # SECONDARY: Windows native environment
    elif os.name == 'nt' or sys.platform.startswith('win') or platform.system() == 'Windows':
        # Running in Windows PowerShell/CMD
        print("🪟 Detected Windows PowerShell environment")  
        data_path = Path(r"C:\Users\krajcovic\Documents\Testing Data\backtest_data\dem07_25_tr_ba_data.parquet")
        output_path = Path(r"C:\Users\krajcovic\Documents\Testing Data\ATS_3_data\interim_test")
        return data_path, output_path, "Windows"
    
    else:
        # Default fallback to WSL since we know the file exists there
        print("⚠️  Environment unclear, defaulting to WSL paths")
        data_path = Path("/mnt/c/Users/krajcovic/Documents/Testing Data/backtest_data/dem07_25_tr_ba_data.parquet")
        output_path = Path("/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data/interim_test")
        return data_path, output_path, "WSL"

def setup_output_directory():
    """Create output directory structure based on detected environment"""
    print("🗂️  Setting up output directories...")
    
    _, output_base, env_type = detect_environment_and_get_paths()
    print(f"📁 Using {env_type} paths: {output_base}")
    
    # Create subdirectories
    directories = [
        output_base,
        output_base / "atr_results",
        output_base / "macd_results", 
        output_base / "combinations_metadata",
        output_base / "performance_logs"
    ]
    
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        print(f"✓ Created: {directory}")
    
    return output_base

def load_real_market_data():
    """Load real market data from parquet file using environment-appropriate paths"""
    print("📈 Loading real market data...")
    
    data_path, _, env_type = detect_environment_and_get_paths()
    print(f"📁 Using {env_type} data path: {data_path}")
    
    if not data_path.exists():
        raise FileNotFoundError(
            f"❌ Real market data file not found: {data_path}\n"
            f"Please ensure the file exists at the correct path for your environment:\n"
            f"  - WSL: /mnt/c/Users/krajcovic/Documents/Testing Data/backtest_data/dem07_25_tr_ba_data.parquet\n"
            f"  - PowerShell: C:\\Users\\krajcovic\\Documents\\Testing Data\\backtest_data\\dem07_25_tr_ba_data.parquet"
        )
    
    # Load real data
    print("⏳ Loading parquet file...")
    df = pd.read_parquet(data_path)
    print(f"✅ Successfully loaded {len(df):,} records from {data_path.name}")
    print(f"📊 Columns available: {list(df.columns)}")
    
    # Validate required columns
    if 'price' not in df.columns:
        raise ValueError(f"❌ Required 'price' column not found. Available columns: {list(df.columns)}")
    
    # Display data info
    print(f"📅 Date range: {df.index.min()} to {df.index.max()}")
    print(f"💰 Price range: ${df['price'].min():.2f} - ${df['price'].max():.2f}")
    print(f"📈 Price std dev: ${df['price'].std():.2f}")
    
    return df

def generate_parameter_combinations():
    """Generate all 1,250 parameter combinations"""
    print("🔧 Generating parameter combinations...")
    
    # Parameter spaces
    candle_granularities = range(5,61,5)  # minutes
    atr_periods = range(7,21,1)
    macd_se = range(8,15,1)  # Short EMA periods
    macd_le = range(16,51,1)  # Long EMA periods
    macd_signal = range(6,31,1)  # Signal periods

    combinations = []
    combo_id = 0
    
    for granularity in candle_granularities:
        for atr_period in atr_periods:
            for se in macd_se:
                for le in macd_le:
                    for signal in macd_signal:
                        combinations.append({
                            'combo_id': combo_id,
                            'candle_granularity': f'{granularity}min',
                            'atr_period': atr_period,
                            'macd_params': {
                                'se': se,
                                'le': le,
                                'signal': signal
                            },
                            'granularity_minutes': granularity
                        })
                        combo_id += 1
    
    print(f"✓ Generated {len(combinations):,} parameter combinations")
    print(f"✓ Sample combination: {combinations[0]}")
    print(f"✓ Last combination: {combinations[-1]}")
    
    return combinations

def check_gpu_availability():
    """Check if GPU backend is available before starting the test"""
    try:
        from src.feature_engineering.array_backend import ArrayBackend
        backend = ArrayBackend(backend='cupy')
        print(f"✅ GPU backend available: {backend.backend}")
        device = backend.xp.cuda.Device()
        print(f"🎮 GPU device: {device.id}")
        free_mem, total_mem = backend.xp.cuda.Device().mem_info
        print(f"💾 GPU memory: {total_mem / 1e9:.1f}GB total, {free_mem / 1e9:.1f}GB free")
        return True
    except Exception as e:
        print(f"❌ GPU backend not available: {e}")
        print("🔧 Please ensure CUDA and CuPy are properly installed for GPU acceleration")
        return False

def prepare_data_for_combination(market_data: pd.DataFrame, combo: Dict) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Prepare tick data and historical candles for a specific combination"""
    
    # Convert granularity to pandas frequency
    granularity_minutes = combo['granularity_minutes']
    freq = f'{granularity_minutes}min'
    
    # Use the entire dataset
    sample_data = market_data.copy()
    
    # Ensure datetime index
    if not isinstance(sample_data.index, pd.DatetimeIndex):
        sample_data.index = pd.to_datetime(sample_data.index)
    
    # Create trades DataFrame (tick data)
    trades_df = sample_data.reset_index()
    trades_df = trades_df.rename(columns={'index': 'datetime'})
    
    # Add required columns
    trades_df['tradeid'] = [f'trade_{i:06d}' for i in range(len(trades_df))]
    trades_df['nanotime'] = [int(t.timestamp() * 1e9) for t in trades_df['datetime']]
    
    # Create historical candles
    # Use data before the last 100 records as "historical"
    historical_cutoff = len(sample_data) - 100
    # historical_data = sample_data.iloc[:historical_cutoff]
    historical_data = sample_data.copy()
    
    # Resample to create OHLC candles
    historical_candles = historical_data['price'].resample(freq).agg({
        'open': 'first',
        'high': 'max', 
        'low': 'min',
        'close': 'last'
    }).dropna()
    
    # Use last 100 records as current trades (simulate real-time processing)
    # current_trades = trades_df.iloc[historical_cutoff:].copy()
    current_trades = trades_df.copy()
    
    return current_trades, historical_candles

def process_combinations_batch_gpu(combinations_batch: List[Dict], market_data: pd.DataFrame, output_base: Path) -> List[Dict]:
    """Process multiple combinations using TRUE GPU batch processing from Phase 2"""
    
    batch_size = len(combinations_batch)
    print(f"    🚀 Processing {batch_size} combinations using TRUE GPU BATCH processor...")
    
    start_time = time.time()
    
    try:
        # Import the ACTUAL GPU batch processor from Phase 2
        from src.feature_engineering.gpu_technical_indicators_batch import GPUTechnicalIndicatorsBatch
        
        # Initialize the TRUE GPU batch processor with ArrayBackend
        from src.feature_engineering.array_backend import ArrayBackend
        backend = ArrayBackend(backend='cupy')
        
        print(f"    ⚡ Initializing TRUE GPU batch processor (Phase 2)...")
        gpu_batch_processor = GPUTechnicalIndicatorsBatch(backend)
        
        # Prepare combinations in the format expected by GPU batch processor
        prepared_combinations = []
        for combo in combinations_batch:
            trades_df, historical_candles = prepare_data_for_combination(market_data, combo)
            
            # Format combination for GPU batch processor
            combination_data = {
                'combo_id': combo['combo_id'],
                'parameters': combo,
                'tick_data': trades_df,
                'historical_candles': historical_candles,
                'atr_period': combo['atr_period'],
                'macd_params': combo['macd_params'],
                'candle_granularity': combo['candle_granularity']
            }
            prepared_combinations.append(combination_data)
        
        # Process ALL combinations in TRUE GPU batch mode (parallel processing on GPU)
        print(f"    🔥 Processing {batch_size} combinations with TRUE GPU batch processing...")
        gpu_batch_results = gpu_batch_processor.process_combinations_batch(prepared_combinations)
        
        # Convert GPU batch results to our expected format and save files
        results = []
        for i, batch_result in enumerate(gpu_batch_results):
            combo_id = batch_result.get('combo_id', i)
            
            try:
                # Extract results from GPU batch processing
                atr_result = batch_result['atr_results']
                macd_result = batch_result['macd_results']
                
                # Save results efficiently
                atr_file = output_base / "atr_results" / f"atr_combo_{combo_id:04d}.parquet"
                macd_file = output_base / "macd_results" / f"macd_combo_{combo_id:04d}.parquet"
                
                atr_result.to_parquet(atr_file)
                macd_result.to_parquet(macd_file)
                
                # Create summary with TRUE GPU batch processing info
                summary = {
                    'combo_id': combo_id,
                    'parameters': batch_result.get('parameters', combinations_batch[i]),
                    'processing_time_seconds': batch_result.get('processing_time_seconds', 0),
                    'backend_used': 'true_gpu_batch_processor_phase2',
                    'gpu_batch_processing': True,
                    'data_stats': {
                        'trades_count': len(atr_result),
                        'atr_records': len(atr_result),
                        'macd_records': len(macd_result)
                    },
                    'atr_stats': {
                        'min': float(atr_result['atr'].min()),
                        'max': float(atr_result['atr'].max()),
                        'mean': float(atr_result['atr'].mean()),
                        'std': float(atr_result['atr'].std())
                    },
                    'macd_stats': {
                        'macd_min': float(macd_result['macd'].min()),
                        'macd_max': float(macd_result['macd'].max()),
                        'signal_min': float(macd_result['signal'].min()),
                        'signal_max': float(macd_result['signal'].max()),
                        'histogram_min': float(macd_result['histogram'].min()),
                        'histogram_max': float(macd_result['histogram'].max())
                    },
                    'status': 'success',
                    'files': {
                        'atr_file': str(atr_file),
                        'macd_file': str(macd_file)
                    }
                }
                
                results.append(summary)
                print(f"    ✅ Combo {combo_id:04d} processed with TRUE GPU batch in batch mode")
                
            except Exception as e:
                error_summary = {
                    'combo_id': combo_id,
                    'parameters': combinations_batch[i] if i < len(combinations_batch) else {},
                    'processing_time_seconds': 0,
                    'status': 'error',
                    'error': str(e),
                    'backend_used': 'true_gpu_batch_processor_phase2'
                }
                results.append(error_summary)
                print(f"    ❌ Combo {combo_id:04d} failed in GPU batch: {str(e)[:100]}")
        
        batch_time = time.time() - start_time
        print(f"    🎯 TRUE GPU batch processing completed: {batch_size} combinations in {batch_time:.2f}s (avg: {batch_time/batch_size:.2f}s/combo)")
        
        return results
        
    except Exception as e:
        print(f"    ❌ TRUE GPU batch processing failed: {e}")
        import traceback
        traceback.print_exc()
        
        # Return error results for all combinations in batch
        return [{
            'combo_id': combo['combo_id'],
            'parameters': combo,
            'processing_time_seconds': time.time() - start_time,
            'status': 'error',
            'error': f"TRUE GPU batch processing failed: {str(e)}",
            'backend_used': 'true_gpu_batch_processor_phase2'
        } for combo in combinations_batch]

def run_comprehensive_test():
    """Run the comprehensive parameter combinations test with parallel GPU processing"""
    print("🚀 COMPREHENSIVE PARAMETER COMBINATIONS TEST")
    print("=" * 80)
    print(f"Test started at: {datetime.now()}")
    print()
    
    # Detect environment and show paths
    data_path, output_path, env_type = detect_environment_and_get_paths()
    print(f"🖥️  Environment: {env_type}")
    print(f"📥 Input data: {data_path}")
    print(f"📤 Output directory: {output_path}")
    print()
    
    # Check GPU availability before starting
    print("🔍 Checking GPU availability...")
    if not check_gpu_availability():
        raise RuntimeError("GPU backend required but not available. Cannot proceed with GPU-accelerated test.")
    print()
    
    # Setup
    output_base = setup_output_directory()
    market_data = load_real_market_data()
    combinations = generate_parameter_combinations()
    
    # ✅ SINGLE CONTROL POINT FOR BATCH SIZE
    batch_size = 5000  # 🎯 CHANGE THIS NUMBER TO CONTROL BATCH SIZE
    
    # Scale combinations to match or exceed batch size for testing
    test_combinations = combinations[:max(batch_size, 1000)]  # Process at least batch_size combinations
    
    print(f"🧪 TRUE PARALLEL GPU TEST: {len(test_combinations):,} combinations, {batch_size} per batch")
    print("🔥 Using TRUE PARALLEL GPU processing for maximum utilization")
    print()
    
    # Process combinations in parallel batches
    results = []
    successful_count = 0
    failed_count = 0
    
    print(f"📦 Batch Size Control: {batch_size} combinations per batch (TRUE PARALLEL GPU)")
    print()
    
    start_time = time.time()
    
    # Process in batches for maximum GPU utilization
    for batch_start in range(0, len(test_combinations), batch_size):
        batch_end = min(batch_start + batch_size, len(test_combinations))
        batch_combinations = test_combinations[batch_start:batch_end]
        
        print(f"🔄 Processing batch {batch_start//batch_size + 1}: combinations {batch_start} to {batch_end-1}")
        
        # Process batch in parallel on GPU using CUDA streams
        batch_results = process_combinations_batch_gpu(batch_combinations, market_data, output_base)
        results.extend(batch_results)
        
        # Update counters
        batch_successful = sum(1 for r in batch_results if r['status'] == 'success')
        batch_failed = len(batch_results) - batch_successful
        successful_count += batch_successful
        failed_count += batch_failed
        
        # Progress update
        elapsed = time.time() - start_time
        completed = batch_end
        avg_time = elapsed / completed
        remaining = avg_time * (len(test_combinations) - completed)
        
        print(f"    ✅ Batch completed: {batch_successful}/{len(batch_results)} successful")
        print(f"    📊 Overall progress: {completed}/{len(test_combinations)} ({(completed/len(test_combinations)*100):.1f}%)")
        print(f"    ⏱️  Average: {avg_time:.2f}s/combo, ETA: {remaining/60:.1f} minutes")
        print()
    
    total_time = time.time() - start_time
    
    # Save comprehensive results
    results_file = output_base / "combinations_metadata" / "comprehensive_results.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    # Create summary report
    summary_report = {
        'test_info': {
            'total_combinations_tested': len(test_combinations),
            'total_combinations_available': len(combinations),
            'test_date': datetime.now().isoformat(),
            'total_processing_time_seconds': total_time,
            'average_time_per_combination': total_time / len(test_combinations),
            'batch_size_used': batch_size,
            'parallel_processing': True
        },
        'results_summary': {
            'successful_combinations': successful_count,
            'failed_combinations': failed_count,
            'success_rate_percent': (successful_count / len(test_combinations)) * 100
        },
        'parameter_space': {
            'candle_granularities': [5, 10, 15, 20, 25],
            'atr_periods': [14, 21],
            'macd_se_values': [8, 9, 10, 11, 12],
            'macd_le_values': [16, 20, 26, 32, 38],
            'macd_signal_values': [6, 9, 12, 15, 18]
        },
        'environment_info': {
            'detected_environment': env_type,
            'input_data_path': str(data_path),
            'output_base_path': str(output_path)
        },
        'output_files': {
            'atr_results_folder': str(output_base / "atr_results"),
            'macd_results_folder': str(output_base / "macd_results"),
            'metadata_folder': str(output_base / "combinations_metadata")
        }
    }
    
    summary_file = output_base / "combinations_metadata" / "test_summary.json"
    with open(summary_file, 'w') as f:
        json.dump(summary_report, f, indent=2)
    
    # Final report
    print("\n" + "=" * 80)
    print("🎯 TEST COMPLETION SUMMARY")
    print("=" * 80)
    print(f"✅ Successfully processed: {successful_count:,} combinations")
    print(f"❌ Failed combinations: {failed_count:,}")
    print(f"📊 Success rate: {(successful_count/len(test_combinations)*100):.1f}%")
    print(f"⏱️  Total processing time: {total_time/60:.1f} minutes")
    print(f"⚡ Average time per combination: {total_time/len(test_combinations):.2f} seconds")
    print(f"🔥 Parallel batch processing with {batch_size} combinations per batch")
    print()
    print("📁 Output files saved to:")
    print(f"   • ATR Results: {output_base / 'atr_results'}")
    print(f"   • MACD Results: {output_base / 'macd_results'}")
    print(f"   • Metadata: {output_base / 'combinations_metadata'}")
    print()
    print("🔍 Key files:")
    print(f"   • Comprehensive results: {results_file}")
    print(f"   • Test summary: {summary_file}")
    print()
    
    if failed_count > 0:
        print("⚠️  Some combinations failed. Check the comprehensive results for error details.")
    else:
        print("🎉 All combinations processed successfully!")
    
    print(f"\nTest completed at: {datetime.now()}")
    
    return results, summary_report

def main():
    """Main function"""
    try:
        results, summary = run_comprehensive_test()
        return True
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)