#!/usr/bin/env python3
"""
Windows Path 1000 Combination Test with Individual Combo Data
Saves all data to actual Windows C: drive and creates detailed data for each combination.
"""

import pandas as pd
import numpy as np
import sys
import time
from pathlib import Path
from typing import List, Dict
import json
import os

# Add source paths
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root / "src"))
sys.path.append(str(project_root / "source_repos" / "EnergyTrading" / "Python" / "Utilities"))
sys.path.append(str(project_root / "source_repos" / "EnergyTrading" / "Python"))

# Import legacy implementations
try:
    from predictors_tools import (
        compute_realtime_atr,
        compute_realtime_macd,
        detect_swing_points
    )
    LEGACY_FUNCTIONS_AVAILABLE = True
    print("✅ Legacy functions imported successfully")
except ImportError as e:
    print(f"❌ Could not import legacy functions: {e}")
    LEGACY_FUNCTIONS_AVAILABLE = False
    sys.exit(1)

# Import fixed GPU implementations
from feature_engineering.atr_calculator import ATRCalculator
from feature_engineering.macd_calculator import MACDCalculator  
from feature_engineering.swing_point_detector import SwingPointDetector
from feature_engineering.array_backend import ArrayBackend
from gpu_parallel_processing import generate_combination_batch


def setup_windows_directories():
    """Setup Windows C: drive directories for saving results"""
    # Use actual Windows paths
    base_dir = Path("/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data")
    data_dir = base_dir / "data"
    individual_combos_dir = base_dir / "individual_combinations"
    
    # Create directories if they don't exist
    data_dir.mkdir(parents=True, exist_ok=True)
    individual_combos_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"📁 Windows C: drive base directory: {base_dir}")
    print(f"📁 Data directory: {data_dir}")
    print(f"📁 Individual combinations directory: {individual_combos_dir}")
    
    return data_dir, base_dir, individual_combos_dir


def create_test_data():
    """Create comprehensive test data"""
    print("📊 Creating comprehensive test data...")
    
    np.random.seed(42)
    n_periods = 8000
    dates = pd.date_range('2024-01-01 09:00', periods=n_periods, freq='1min')
    prices = 100 + np.cumsum(np.random.normal(0, 0.1, n_periods))
    
    trades_df = pd.DataFrame({
        'datetime': dates,
        'price': prices,
        'nanotime': range(n_periods),
        'tradeid': range(1000, 1000 + n_periods)
    })
    
    # Create historical candles
    trades_indexed = trades_df.set_index('datetime')
    candles = trades_indexed.groupby(pd.Grouper(freq='1h')).agg({
        'price': ['first', 'max', 'min', 'last']
    }).dropna()
    candles.columns = ['open', 'high', 'low', 'close']
    historical_candles = candles.reset_index()
    
    print(f"✅ Created {len(trades_df)} trade records and {len(historical_candles)} historical candles")
    
    return trades_df, historical_candles


def validate_atr_with_individual_data(trades_df: pd.DataFrame, historical_candles: pd.DataFrame, 
                                     combinations: List[Dict], data_dir: Path, individual_dir: Path):
    """Validate ATR and save individual combination data"""
    print("\n🔧 ATR VALIDATION WITH INDIVIDUAL COMBO DATA")
    print("=" * 60)
    
    start_time = time.time()
    
    # Initialize GPU implementation
    backend = ArrayBackend()
    atr_calc = ATRCalculator(backend)
    
    # Store all results for each combination
    all_combo_results = []
    individual_files_created = []
    
    print(f"🔄 Processing {len(combinations)} ATR combinations with individual data saving...")
    
    for i, combo in enumerate(combinations):
        combo_start_time = time.time()
        atr_period = combo.get('atr_lookback', 21)
        combo_id = combo['combo_id']
        
        try:
            # Use reasonable subset for each combo
            test_trades = trades_df.head(800)
            
            # GPU implementation
            gpu_start = time.time()
            gpu_result = atr_calc.compute_atr(
                trades_df=test_trades,
                historical_candles=historical_candles,
                atr_period=atr_period,
                price_col='price',
                datetime_col='datetime',
                candle_granularity='1h'
            )
            gpu_time = time.time() - gpu_start
            
            # Legacy implementation
            legacy_start = time.time()
            legacy_result = compute_realtime_atr(
                trades_df=test_trades,
                historical_candles=historical_candles,
                atr_period=atr_period,
                price_col='price',
                datetime_col='datetime',
                candle_granularity='1h'
            )
            legacy_time = time.time() - legacy_start
            
            # Compare results
            match_rate = 0.0
            data_points = 0
            if len(gpu_result) > 0 and len(legacy_result) > 0:
                gpu_atr = gpu_result['atr'].values
                legacy_atr = legacy_result['atr'].values
                
                min_len = min(len(gpu_atr), len(legacy_atr))
                data_points = min_len
                matches = np.isclose(gpu_atr[:min_len], legacy_atr[:min_len], rtol=1e-8, atol=1e-10)
                match_rate = np.mean(matches) * 100
                
                # Save individual combination data
                combo_data = pd.DataFrame({
                    'trade_index': range(min_len),
                    'gpu_atr': gpu_atr[:min_len],
                    'legacy_atr': legacy_atr[:min_len],
                    'difference': gpu_atr[:min_len] - legacy_atr[:min_len],
                    'match': matches
                })
                
                # Add combination metadata
                combo_data['combo_id'] = combo_id
                combo_data['atr_period'] = atr_period
                combo_data['match_rate'] = match_rate
                
                # Save individual file
                individual_file = individual_dir / f"atr_combo_{combo_id:04d}_period_{atr_period}.parquet"
                combo_data.to_parquet(individual_file, index=False)
                individual_files_created.append(str(individual_file))
            
            combo_processing_time = time.time() - combo_start_time
            
            # Store summary for this combination
            combo_summary = {
                'combo_id': combo_id,
                'atr_period': atr_period,
                'match_rate': match_rate,
                'gpu_processing_time': gpu_time,
                'legacy_processing_time': legacy_time,
                'total_combo_time': combo_processing_time,
                'data_points': data_points,
                'contract': combo.get('contract', 'unknown'),
                'individual_file': str(individual_file) if data_points > 0 else None
            }
            all_combo_results.append(combo_summary)
            
            # Progress reporting
            if (i + 1) % 100 == 0:
                elapsed = time.time() - start_time
                print(f"   Progress: {i+1}/{len(combinations)} - Avg match: {np.mean([r['match_rate'] for r in all_combo_results]):.2f}% - Time: {elapsed:.1f}s")
            
        except Exception as e:
            error_summary = {
                'combo_id': combo_id,
                'atr_period': atr_period,
                'match_rate': 0.0,
                'gpu_processing_time': 0.0,
                'legacy_processing_time': 0.0,
                'total_combo_time': 0.0,
                'data_points': 0,
                'error': str(e),
                'individual_file': None
            }
            all_combo_results.append(error_summary)
    
    total_time = time.time() - start_time
    
    # Save comprehensive ATR results
    atr_summary_df = pd.DataFrame(all_combo_results)
    atr_summary_file = data_dir / "atr_all_combinations_summary.parquet"
    atr_summary_df.to_parquet(atr_summary_file, index=False)
    
    # Calculate statistics
    successful_combos = [r for r in all_combo_results if r['match_rate'] > 0]
    avg_match_rate = np.mean([r['match_rate'] for r in successful_combos]) if successful_combos else 0
    perfect_matches = len([r for r in successful_combos if r['match_rate'] >= 99.9])
    
    print(f"\n📊 ATR Results:")
    print(f"   Total combinations: {len(combinations)}")
    print(f"   Successful comparisons: {len(successful_combos)}")
    print(f"   Average match rate: {avg_match_rate:.4f}%")
    print(f"   Perfect matches (≥99.9%): {perfect_matches}")
    print(f"   Individual files created: {len(individual_files_created)}")
    print(f"   Processing time: {total_time:.2f}s")
    print(f"   Summary file: {atr_summary_file}")
    
    return {
        'total_time': total_time,
        'avg_match_rate': avg_match_rate,
        'successful_comparisons': len(successful_combos),
        'perfect_matches': perfect_matches,
        'individual_files': individual_files_created,
        'summary_file': str(atr_summary_file)
    }


def validate_macd_with_individual_data(trades_df: pd.DataFrame, historical_candles: pd.DataFrame,
                                      combinations: List[Dict], data_dir: Path, individual_dir: Path):
    """Validate MACD and save individual combination data"""
    print("\n🔧 MACD VALIDATION WITH INDIVIDUAL COMBO DATA")
    print("=" * 60)
    
    start_time = time.time()
    
    # Initialize GPU implementation
    backend = ArrayBackend()
    macd_calc = MACDCalculator(backend)
    
    all_combo_results = []
    individual_files_created = []
    
    print(f"🔄 Processing {len(combinations)} MACD combinations with individual data saving...")
    
    for i, combo in enumerate(combinations):
        combo_start_time = time.time()
        macd_params = combo.get('macd_params', {'short': 12, 'long': 26, 'signal': 9})
        combo_id = combo['combo_id']
        
        try:
            test_trades = trades_df.head(800)
            
            # GPU implementation
            gpu_start = time.time()
            gpu_result = macd_calc.compute_macd(
                trades_df=test_trades,
                historical_candles=historical_candles,
                se=macd_params['short'],
                le=macd_params['long'],
                signal_period=macd_params['signal'],
                price_col='price',
                datetime_col='datetime',
                candle_granularity='1h'
            )
            gpu_time = time.time() - gpu_start
            
            # Legacy implementation
            legacy_start = time.time()
            legacy_result = compute_realtime_macd(
                trades_df=test_trades,
                historical_candles=historical_candles,
                se=macd_params['short'],
                le=macd_params['long'],
                signal_period=macd_params['signal'],
                price_col='price',
                datetime_col='datetime',
                candle_granularity='1h'
            )
            legacy_time = time.time() - legacy_start
            
            # Compare results
            macd_rate = signal_rate = hist_rate = overall_rate = 0.0
            data_points = 0
            
            if len(gpu_result) > 0 and len(legacy_result) > 0:
                min_len = min(len(gpu_result), len(legacy_result))
                data_points = min_len
                
                # Compare all MACD components
                macd_matches = np.isclose(gpu_result['macd'].values[:min_len],
                                        legacy_result['macd'].values[:min_len], rtol=1e-8, atol=1e-10)
                signal_matches = np.isclose(gpu_result['signal'].values[:min_len],
                                          legacy_result['signal'].values[:min_len], rtol=1e-8, atol=1e-10)
                hist_col = 'hist' if 'hist' in legacy_result.columns else 'histogram'
                hist_matches = np.isclose(gpu_result['histogram'].values[:min_len],
                                        legacy_result[hist_col].values[:min_len], rtol=1e-8, atol=1e-10)
                
                macd_rate = np.mean(macd_matches) * 100
                signal_rate = np.mean(signal_matches) * 100
                hist_rate = np.mean(hist_matches) * 100
                overall_rate = (macd_rate + signal_rate + hist_rate) / 3
                
                # Save individual combination data
                combo_data = pd.DataFrame({
                    'trade_index': range(min_len),
                    'gpu_macd': gpu_result['macd'].values[:min_len],
                    'legacy_macd': legacy_result['macd'].values[:min_len],
                    'gpu_signal': gpu_result['signal'].values[:min_len],
                    'legacy_signal': legacy_result['signal'].values[:min_len],
                    'gpu_histogram': gpu_result['histogram'].values[:min_len],
                    'legacy_histogram': legacy_result[hist_col].values[:min_len],
                    'macd_match': macd_matches,
                    'signal_match': signal_matches,
                    'histogram_match': hist_matches
                })
                
                # Add combination metadata
                combo_data['combo_id'] = combo_id
                combo_data['macd_short'] = macd_params['short']
                combo_data['macd_long'] = macd_params['long']
                combo_data['macd_signal_period'] = macd_params['signal']
                combo_data['overall_match_rate'] = overall_rate
                
                # Save individual file
                individual_file = individual_dir / f"macd_combo_{combo_id:04d}_params_{macd_params['short']}_{macd_params['long']}_{macd_params['signal']}.parquet"
                combo_data.to_parquet(individual_file, index=False)
                individual_files_created.append(str(individual_file))
            
            combo_processing_time = time.time() - combo_start_time
            
            # Store summary for this combination
            combo_summary = {
                'combo_id': combo_id,
                'macd_short': macd_params['short'],
                'macd_long': macd_params['long'],
                'macd_signal_period': macd_params['signal'],
                'macd_match_rate': macd_rate,
                'signal_match_rate': signal_rate,
                'histogram_match_rate': hist_rate,
                'overall_match_rate': overall_rate,
                'gpu_processing_time': gpu_time,
                'legacy_processing_time': legacy_time,
                'total_combo_time': combo_processing_time,
                'data_points': data_points,
                'contract': combo.get('contract', 'unknown'),
                'individual_file': str(individual_file) if data_points > 0 else None
            }
            all_combo_results.append(combo_summary)
            
            # Progress reporting
            if (i + 1) % 100 == 0:
                elapsed = time.time() - start_time
                avg_overall = np.mean([r['overall_match_rate'] for r in all_combo_results if r['overall_match_rate'] > 0])
                print(f"   Progress: {i+1}/{len(combinations)} - Avg match: {avg_overall:.2f}% - Time: {elapsed:.1f}s")
            
        except Exception as e:
            error_summary = {
                'combo_id': combo_id,
                'macd_short': macd_params['short'],
                'macd_long': macd_params['long'],
                'macd_signal_period': macd_params['signal'],
                'macd_match_rate': 0.0,
                'signal_match_rate': 0.0,
                'histogram_match_rate': 0.0,
                'overall_match_rate': 0.0,
                'gpu_processing_time': 0.0,
                'legacy_processing_time': 0.0,
                'total_combo_time': 0.0,
                'data_points': 0,
                'error': str(e),
                'individual_file': None
            }
            all_combo_results.append(error_summary)
    
    total_time = time.time() - start_time
    
    # Save comprehensive MACD results
    macd_summary_df = pd.DataFrame(all_combo_results)
    macd_summary_file = data_dir / "macd_all_combinations_summary.parquet"
    macd_summary_df.to_parquet(macd_summary_file, index=False)
    
    # Calculate statistics
    successful_combos = [r for r in all_combo_results if r['overall_match_rate'] > 0]
    avg_overall_rate = np.mean([r['overall_match_rate'] for r in successful_combos]) if successful_combos else 0
    perfect_matches = len([r for r in successful_combos if r['overall_match_rate'] >= 99.9])
    
    print(f"\n📊 MACD Results:")
    print(f"   Total combinations: {len(combinations)}")
    print(f"   Successful comparisons: {len(successful_combos)}")
    print(f"   Average overall match rate: {avg_overall_rate:.4f}%")
    print(f"   Perfect matches (≥99.9%): {perfect_matches}")
    print(f"   Individual files created: {len(individual_files_created)}")
    print(f"   Processing time: {total_time:.2f}s")
    print(f"   Summary file: {macd_summary_file}")
    
    return {
        'total_time': total_time,
        'avg_match_rate': avg_overall_rate,
        'successful_comparisons': len(successful_combos),
        'perfect_matches': perfect_matches,
        'individual_files': individual_files_created,
        'summary_file': str(macd_summary_file)
    }


def main():
    """Run Windows path 1000 combination test with individual combo data"""
    print("🚀 WINDOWS PATH 1000 COMBINATION TEST WITH INDIVIDUAL COMBO DATA")
    print("=" * 90)
    print("Saving all data to actual Windows C: drive with detailed individual combination data")
    print("=" * 90)
    
    if not LEGACY_FUNCTIONS_AVAILABLE:
        print("❌ CANNOT RUN VALIDATION")
        return
    
    # Setup Windows directories
    data_dir, results_dir, individual_dir = setup_windows_directories()
    
    # Overall timing
    overall_start_time = time.time()
    
    # Create test data
    trades_data, historical_candles = create_test_data()
    
    # Generate 1000 combinations
    print(f"\n📋 Generating 1000 parameter combinations...")
    combo_start = time.time()
    combinations = generate_combination_batch(start_idx=0, batch_size=1000)
    combo_time = time.time() - combo_start
    print(f"✅ Generated {len(combinations)} combinations in {combo_time:.2f}s")
    
    # Save combinations with full metadata to Windows C: drive
    combo_df = pd.DataFrame(combinations)
    combo_file = results_dir / "parameter_combinations_1000_full_metadata.parquet"
    combo_df.to_parquet(combo_file, index=False)
    print(f"💾 Full parameter combinations saved to Windows C: drive: {combo_file}")
    
    # Process ATR with individual data
    print(f"\n⏱️  STARTING ATR VALIDATION WITH INDIVIDUAL DATA SAVING")
    atr_results = validate_atr_with_individual_data(trades_data, historical_candles, combinations, data_dir, individual_dir)
    
    # Process MACD with individual data
    print(f"\n⏱️  STARTING MACD VALIDATION WITH INDIVIDUAL DATA SAVING")
    macd_results = validate_macd_with_individual_data(trades_data, historical_candles, combinations, data_dir, individual_dir)
    
    total_time = time.time() - overall_start_time
    
    # Create comprehensive summary
    print("\n" + "=" * 90)
    print("⏱️  FINAL TIMING AND RESULTS SUMMARY")
    print("=" * 90)
    
    print(f"Combination Generation:  {combo_time:.2f}s")
    print(f"ATR Validation:          {atr_results['total_time']:.2f}s")
    print(f"MACD Validation:         {macd_results['total_time']:.2f}s")
    print(f"TOTAL TIME:              {total_time:.2f}s ({total_time/60:.2f} minutes)")
    
    print(f"\n📊 VALIDATION RESULTS:")
    print(f"ATR:  {atr_results['avg_match_rate']:.4f}% avg match ({atr_results['perfect_matches']}/{atr_results['successful_comparisons']} perfect)")
    print(f"MACD: {macd_results['avg_match_rate']:.4f}% avg match ({macd_results['perfect_matches']}/{macd_results['successful_comparisons']} perfect)")
    
    print(f"\n📁 FILES CREATED ON WINDOWS C: DRIVE:")
    print(f"Base directory: {results_dir}")
    print(f"   - parameter_combinations_1000_full_metadata.parquet")
    print(f"Data directory: {data_dir}")
    print(f"   - atr_all_combinations_summary.parquet")
    print(f"   - macd_all_combinations_summary.parquet")
    print(f"Individual combinations directory: {individual_dir}")
    print(f"   - {len(atr_results['individual_files'])} ATR individual files")
    print(f"   - {len(macd_results['individual_files'])} MACD individual files")
    print(f"   - Total individual files: {len(atr_results['individual_files']) + len(macd_results['individual_files'])}")
    
    # Save final summary to Windows C: drive
    final_summary = {
        "test_metadata": {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_combinations": 1000,
            "total_processing_time_seconds": total_time,
            "total_processing_time_minutes": total_time / 60,
            "windows_save_location": str(results_dir)
        },
        "timing_breakdown": {
            "combination_generation_seconds": combo_time,
            "atr_validation_seconds": atr_results['total_time'],
            "macd_validation_seconds": macd_results['total_time']
        },
        "validation_results": {
            "atr_avg_match_rate": atr_results['avg_match_rate'],
            "atr_perfect_matches": atr_results['perfect_matches'],
            "macd_avg_match_rate": macd_results['avg_match_rate'],
            "macd_perfect_matches": macd_results['perfect_matches']
        },
        "files_created": {
            "base_directory": str(results_dir),
            "data_directory": str(data_dir),
            "individual_directory": str(individual_dir),
            "total_individual_files": len(atr_results['individual_files']) + len(macd_results['individual_files']),
            "atr_individual_files": len(atr_results['individual_files']),
            "macd_individual_files": len(macd_results['individual_files'])
        }
    }
    
    # Save to Windows C: drive
    summary_file = results_dir / "windows_1000_combo_final_summary.json"
    with open(summary_file, 'w') as f:
        json.dump(final_summary, f, indent=2, default=str)
    
    summary_txt_file = results_dir / "windows_1000_combo_final_summary.txt"
    with open(summary_txt_file, 'w') as f:
        f.write("WINDOWS 1000 COMBINATION TEST - FINAL SUMMARY\n")
        f.write("=" * 90 + "\n")
        f.write(f"Total Processing Time: {total_time:.2f}s ({total_time/60:.2f} minutes)\n")
        f.write(f"ATR Average Match Rate: {atr_results['avg_match_rate']:.4f}%\n")
        f.write(f"MACD Average Match Rate: {macd_results['avg_match_rate']:.4f}%\n")
        f.write(f"Total Individual Files Created: {len(atr_results['individual_files']) + len(macd_results['individual_files'])}\n")
        f.write(f"Windows Save Location: {results_dir}\n")
        f.write(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    print(f"\n💾 Final summary saved to Windows C: drive:")
    print(f"   JSON: {summary_file}")
    print(f"   Text: {summary_txt_file}")
    
    print(f"\n🎉 SUCCESS: 1000 combinations processed and saved to Windows C: drive!")
    print(f"   Processing time: {total_time:.2f}s ({total_time/60:.2f} minutes)")
    print(f"   Individual combo data files: {len(atr_results['individual_files']) + len(macd_results['individual_files'])}")
    print(f"   All data saved to: {results_dir}")


if __name__ == "__main__":
    main()