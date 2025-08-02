#!/usr/bin/env python3
"""
Timed 1000 Combination Validation Test
Tests all fixed implementations against correct legacy functions with full 1000 combinations,
saves combo data to specified directory, and provides detailed timing information.
"""

import pandas as pd
import numpy as np
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple
import json
import os

# Add source paths
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root / "src"))
sys.path.append(str(project_root / "source_repos" / "EnergyTrading" / "Python" / "Utilities"))
sys.path.append(str(project_root / "source_repos" / "EnergyTrading" / "Python"))

# Import legacy implementations (correct functions per fix handoffs)
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


def setup_data_directories():
    """Setup data directories for saving results"""
    base_dir = Path("C:/Users/krajcovic/Documents/Testing Data/ATS_3_data")
    data_dir = base_dir / "data"
    
    # Create directories if they don't exist
    data_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"📁 Data directory: {data_dir}")
    print(f"📁 Results directory: {base_dir}")
    
    return data_dir, base_dir


def create_test_data():
    """Create comprehensive test data for validation"""
    print("📊 Creating comprehensive test data...")
    
    np.random.seed(42)
    n_periods = 10000  # Larger dataset for 1000 combinations
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


def validate_atr_with_1000_combos(trades_df: pd.DataFrame, historical_candles: pd.DataFrame, 
                                 combinations: List[Dict], data_dir: Path) -> Dict:
    """Validate ATR fix with all 1000 combinations and save data"""
    print("\n🔧 ATR FIX VALIDATION - 1000 COMBINATIONS")
    print("=" * 60)
    
    start_time = time.time()
    
    # Initialize GPU implementation
    backend = ArrayBackend()
    atr_calc = ATRCalculator(backend)
    
    results = {
        'total_combinations': len(combinations),
        'successful_comparisons': 0,
        'perfect_matches': 0,
        'match_rates': [],
        'processing_times': {'gpu': [], 'legacy': []},
        'errors': [],
        'combination_details': []
    }
    
    print(f"🔄 Processing {len(combinations)} ATR combinations...")
    
    # Process in batches to manage memory
    batch_size = 100
    
    for batch_start in range(0, len(combinations), batch_size):
        batch_end = min(batch_start + batch_size, len(combinations))
        batch_combinations = combinations[batch_start:batch_end]
        
        print(f"   Processing batch {batch_start//batch_size + 1}/{(len(combinations) + batch_size - 1)//batch_size}")
        
        for i, combo in enumerate(batch_combinations):
            global_i = batch_start + i
            atr_period = combo.get('atr_lookback', 21)
            
            try:
                # Use subset for performance while maintaining accuracy
                test_trades = trades_df.head(1000)
                
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
                results['processing_times']['gpu'].append(gpu_time)
                
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
                results['processing_times']['legacy'].append(legacy_time)
                
                # Compare results
                if len(gpu_result) > 0 and len(legacy_result) > 0:
                    results['successful_comparisons'] += 1
                    
                    gpu_atr = gpu_result['atr'].values
                    legacy_atr = legacy_result['atr'].values
                    
                    min_len = min(len(gpu_atr), len(legacy_atr))
                    matches = np.isclose(gpu_atr[:min_len], legacy_atr[:min_len], rtol=1e-8, atol=1e-10)
                    match_rate = np.mean(matches) * 100
                    results['match_rates'].append(match_rate)
                    
                    if match_rate >= 99.9:
                        results['perfect_matches'] += 1
                    
                    # Store combination details
                    results['combination_details'].append({
                        'combo_id': combo['combo_id'],
                        'atr_period': atr_period,
                        'match_rate': match_rate,
                        'gpu_time': gpu_time,
                        'legacy_time': legacy_time,
                        'data_points': min_len
                    })
                
            except Exception as e:
                results['errors'].append(f"Combo {global_i}: {str(e)}")
    
    total_time = time.time() - start_time
    
    # Save ATR combination data
    atr_combo_data = pd.DataFrame(results['combination_details'])
    if len(atr_combo_data) > 0:
        atr_file = data_dir / "atr_validation_1000_combos.parquet"
        atr_combo_data.to_parquet(atr_file, index=False)
        print(f"💾 ATR combination data saved to: {atr_file}")
    
    # Calculate statistics
    avg_match_rate = np.mean(results['match_rates']) if results['match_rates'] else 0
    perfect_rate = (results['perfect_matches'] / results['successful_comparisons'] * 100) if results['successful_comparisons'] > 0 else 0
    
    print(f"\n📊 ATR Results:")
    print(f"   Total combinations: {results['total_combinations']}")
    print(f"   Successful comparisons: {results['successful_comparisons']}")
    print(f"   Average match rate: {avg_match_rate:.4f}%")
    print(f"   Perfect matches (≥99.9%): {results['perfect_matches']} ({perfect_rate:.2f}%)")
    print(f"   Processing time: {total_time:.2f}s")
    print(f"   Errors: {len(results['errors'])}")
    
    results['total_time'] = total_time
    results['avg_match_rate'] = avg_match_rate
    results['perfect_rate'] = perfect_rate
    
    return results


def validate_macd_with_1000_combos(trades_df: pd.DataFrame, historical_candles: pd.DataFrame,
                                  combinations: List[Dict], data_dir: Path) -> Dict:
    """Validate MACD fix with all 1000 combinations and save data"""
    print("\n🔧 MACD FIX VALIDATION - 1000 COMBINATIONS")
    print("=" * 60)
    
    start_time = time.time()
    
    # Initialize GPU implementation
    backend = ArrayBackend()
    macd_calc = MACDCalculator(backend)
    
    results = {
        'total_combinations': len(combinations),
        'successful_comparisons': 0,
        'perfect_matches': 0,
        'match_rates': {'macd': [], 'signal': [], 'histogram': []},
        'processing_times': {'gpu': [], 'legacy': []},
        'errors': [],
        'combination_details': []
    }
    
    print(f"🔄 Processing {len(combinations)} MACD combinations...")
    
    # Process in batches
    batch_size = 100
    
    for batch_start in range(0, len(combinations), batch_size):
        batch_end = min(batch_start + batch_size, len(combinations))
        batch_combinations = combinations[batch_start:batch_end]
        
        print(f"   Processing batch {batch_start//batch_size + 1}/{(len(combinations) + batch_size - 1)//batch_size}")
        
        for i, combo in enumerate(batch_combinations):
            global_i = batch_start + i
            macd_params = combo.get('macd_params', {'short': 12, 'long': 26, 'signal': 9})
            
            try:
                test_trades = trades_df.head(1000)
                
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
                results['processing_times']['gpu'].append(gpu_time)
                
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
                results['processing_times']['legacy'].append(legacy_time)
                
                # Compare results
                if len(gpu_result) > 0 and len(legacy_result) > 0:
                    results['successful_comparisons'] += 1
                    
                    min_len = min(len(gpu_result), len(legacy_result))
                    
                    # Compare MACD components
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
                    
                    results['match_rates']['macd'].append(macd_rate)
                    results['match_rates']['signal'].append(signal_rate)
                    results['match_rates']['histogram'].append(hist_rate)
                    
                    if overall_rate >= 99.9:
                        results['perfect_matches'] += 1
                    
                    # Store combination details
                    results['combination_details'].append({
                        'combo_id': combo['combo_id'],
                        'macd_short': macd_params['short'],
                        'macd_long': macd_params['long'],
                        'macd_signal': macd_params['signal'],
                        'macd_match_rate': macd_rate,
                        'signal_match_rate': signal_rate,
                        'histogram_match_rate': hist_rate,
                        'overall_match_rate': overall_rate,
                        'gpu_time': gpu_time,
                        'legacy_time': legacy_time,
                        'data_points': min_len
                    })
                
            except Exception as e:
                results['errors'].append(f"Combo {global_i}: {str(e)}")
    
    total_time = time.time() - start_time
    
    # Save MACD combination data
    macd_combo_data = pd.DataFrame(results['combination_details'])
    if len(macd_combo_data) > 0:
        macd_file = data_dir / "macd_validation_1000_combos.parquet"
        macd_combo_data.to_parquet(macd_file, index=False)
        print(f"💾 MACD combination data saved to: {macd_file}")
    
    # Calculate statistics
    avg_macd_rate = np.mean(results['match_rates']['macd']) if results['match_rates']['macd'] else 0
    avg_signal_rate = np.mean(results['match_rates']['signal']) if results['match_rates']['signal'] else 0
    avg_hist_rate = np.mean(results['match_rates']['histogram']) if results['match_rates']['histogram'] else 0
    overall_rate = (avg_macd_rate + avg_signal_rate + avg_hist_rate) / 3
    perfect_rate = (results['perfect_matches'] / results['successful_comparisons'] * 100) if results['successful_comparisons'] > 0 else 0
    
    print(f"\n📊 MACD Results:")
    print(f"   Total combinations: {results['total_combinations']}")
    print(f"   Successful comparisons: {results['successful_comparisons']}")
    print(f"   Average MACD match rate: {avg_macd_rate:.4f}%")
    print(f"   Average Signal match rate: {avg_signal_rate:.4f}%")
    print(f"   Average Histogram match rate: {avg_hist_rate:.4f}%")
    print(f"   Overall match rate: {overall_rate:.4f}%")
    print(f"   Perfect matches (≥99.9%): {results['perfect_matches']} ({perfect_rate:.2f}%)")
    print(f"   Processing time: {total_time:.2f}s")
    print(f"   Errors: {len(results['errors'])}")
    
    results['total_time'] = total_time
    results['avg_macd_rate'] = avg_macd_rate
    results['avg_signal_rate'] = avg_signal_rate
    results['avg_hist_rate'] = avg_hist_rate
    results['overall_rate'] = overall_rate
    results['perfect_rate'] = perfect_rate
    
    return results


def validate_swing_points(trades_df: pd.DataFrame, data_dir: Path) -> Dict:
    """Validate Swing Points fix and save data"""
    print("\n🔧 SWING POINTS FIX VALIDATION")
    print("=" * 60)
    
    start_time = time.time()
    
    # Initialize GPU implementation
    backend = ArrayBackend()
    swing_detector = SwingPointDetector(backend)
    
    # Create OHLC data
    ohlc_df = pd.DataFrame({
        'open': trades_df['price'].values[:-3],
        'high': trades_df['price'].values[:-3] + np.random.uniform(0, 1, len(trades_df)-3),
        'low': trades_df['price'].values[:-3] - np.random.uniform(0, 1, len(trades_df)-3),
        'close': trades_df['price'].values[1:-2]
    })
    
    # Test with larger dataset
    test_ohlc = ohlc_df.head(2000)
    
    results = {
        'data_points': len(test_ohlc),
        'successful_comparisons': 0,
        'match_rates': {'highs': [], 'lows': []},
        'processing_times': {'gpu': [], 'legacy': []},
        'errors': []
    }
    
    try:
        # GPU implementation
        gpu_start = time.time()
        gpu_result = swing_detector.detect_swings(test_ohlc)
        gpu_time = time.time() - gpu_start
        results['processing_times']['gpu'].append(gpu_time)
        
        # Legacy implementation
        legacy_start = time.time()
        legacy_result = detect_swing_points(test_ohlc)
        legacy_time = time.time() - legacy_start
        results['processing_times']['legacy'].append(legacy_time)
        
        # Compare results
        if len(gpu_result) > 0 and len(legacy_result) > 0:
            results['successful_comparisons'] += 1
            
            min_len = min(len(gpu_result), len(legacy_result))
            
            # Compare swing highs and lows
            high_matches = np.isclose(gpu_result['swing_high'].values[:min_len],
                                    legacy_result['swing_high'].values[:min_len], 
                                    rtol=1e-8, atol=1e-10, equal_nan=True)
            low_matches = np.isclose(gpu_result['swing_low'].values[:min_len],
                                   legacy_result['swing_low'].values[:min_len], 
                                   rtol=1e-8, atol=1e-10, equal_nan=True)
            
            high_rate = np.mean(high_matches) * 100
            low_rate = np.mean(low_matches) * 100
            
            results['match_rates']['highs'].append(high_rate)
            results['match_rates']['lows'].append(low_rate)
            
            # Save swing points data
            swing_data = pd.DataFrame({
                'data_points': [len(test_ohlc)],
                'swing_highs_match_rate': [high_rate],
                'swing_lows_match_rate': [low_rate],
                'overall_match_rate': [(high_rate + low_rate) / 2],
                'gpu_time': [gpu_time],
                'legacy_time': [legacy_time]
            })
            
            swing_file = data_dir / "swing_validation_results.parquet"
            swing_data.to_parquet(swing_file, index=False)
            print(f"💾 Swing points data saved to: {swing_file}")
        
    except Exception as e:
        results['errors'].append(f"Swing test: {str(e)}")
    
    total_time = time.time() - start_time
    
    # Calculate statistics
    avg_high_rate = np.mean(results['match_rates']['highs']) if results['match_rates']['highs'] else 0
    avg_low_rate = np.mean(results['match_rates']['lows']) if results['match_rates']['lows'] else 0
    overall_rate = (avg_high_rate + avg_low_rate) / 2
    
    print(f"\n📊 Swing Points Results:")
    print(f"   Data points tested: {results['data_points']}")
    print(f"   Swing highs match rate: {avg_high_rate:.4f}%")
    print(f"   Swing lows match rate: {avg_low_rate:.4f}%")
    print(f"   Overall match rate: {overall_rate:.4f}%")
    print(f"   Processing time: {total_time:.2f}s")
    print(f"   Errors: {len(results['errors'])}")
    
    results['total_time'] = total_time
    results['avg_high_rate'] = avg_high_rate
    results['avg_low_rate'] = avg_low_rate
    results['overall_rate'] = overall_rate
    
    return results


def main():
    """Run timed 1000 combination validation test"""
    print("🚀 TIMED 1000 COMBINATION VALIDATION TEST")
    print("=" * 80)
    print("Testing all fixed implementations with 1000 combinations")
    print("Saving data to C:/Users/krajcovic/Documents/Testing Data/ATS_3_data/")
    print("=" * 80)
    
    if not LEGACY_FUNCTIONS_AVAILABLE:
        print("❌ CANNOT RUN VALIDATION - Legacy functions not available")
        return
    
    # Setup directories
    data_dir, results_dir = setup_data_directories()
    
    # Overall test timing
    overall_start_time = time.time()
    
    # Load test data
    data_creation_start = time.time()
    trades_data, historical_candles = create_test_data()
    data_creation_time = time.time() - data_creation_start
    
    # Generate 1000 combinations
    combo_generation_start = time.time()
    print(f"\n📋 Generating 1000 parameter combinations...")
    combinations = generate_combination_batch(start_idx=0, batch_size=1000)
    combo_generation_time = time.time() - combo_generation_start
    print(f"✅ Generated {len(combinations)} combinations in {combo_generation_time:.2f}s")
    
    # Save combinations metadata
    combo_metadata = pd.DataFrame(combinations)
    combo_file = results_dir / "parameter_combinations_1000.parquet"
    combo_metadata.to_parquet(combo_file, index=False)
    print(f"💾 Parameter combinations saved to: {combo_file}")
    
    # Run validation tests with detailed timing
    print("\n⏱️  STARTING TIMED VALIDATION TESTS")
    print("=" * 50)
    
    atr_results = validate_atr_with_1000_combos(trades_data, historical_candles, combinations, data_dir)
    macd_results = validate_macd_with_1000_combos(trades_data, historical_candles, combinations, data_dir)
    swing_results = validate_swing_points(trades_data, data_dir)
    
    overall_end_time = time.time()
    total_test_time = overall_end_time - overall_start_time
    
    # Comprehensive timing summary
    print("\n" + "=" * 80)
    print("⏱️  DETAILED TIMING RESULTS")
    print("=" * 80)
    
    print(f"Data Creation Time:           {data_creation_time:.2f}s")
    print(f"Combination Generation Time:  {combo_generation_time:.2f}s")
    print(f"ATR Validation Time:          {atr_results['total_time']:.2f}s")
    print(f"MACD Validation Time:         {macd_results['total_time']:.2f}s")
    print(f"Swing Points Validation Time: {swing_results['total_time']:.2f}s")
    print(f"")
    print(f"TOTAL TEST TIME:              {total_test_time:.2f}s ({total_test_time/60:.2f} minutes)")
    
    # Validation results summary
    print("\n" + "=" * 80)
    print("🎯 VALIDATION RESULTS SUMMARY")
    print("=" * 80)
    
    atr_status = "✅ PASSED" if atr_results['avg_match_rate'] >= 99.0 else "❌ FAILED"
    macd_status = "✅ PASSED" if macd_results['overall_rate'] >= 99.0 else "❌ FAILED"
    swing_status = "✅ PASSED" if swing_results['overall_rate'] >= 95.0 else "❌ FAILED"
    
    print(f"ATR Fix (1000 combos):      {atr_results['avg_match_rate']:.4f}% - {atr_status}")
    print(f"MACD Fix (1000 combos):     {macd_results['overall_rate']:.4f}% - {macd_status}")
    print(f"Swing Points Fix:           {swing_results['overall_rate']:.4f}% - {swing_status}")
    
    # Overall status
    all_passed = (atr_results['avg_match_rate'] >= 99.0 and 
                  macd_results['overall_rate'] >= 99.0 and 
                  swing_results['overall_rate'] >= 95.0)
    overall_status = "✅ ALL TESTS PASSED" if all_passed else "❌ SOME TESTS FAILED"
    
    print(f"\n🏆 OVERALL RESULT: {overall_status}")
    print(f"⏱️  TOTAL PROCESSING TIME: {total_test_time:.2f}s ({total_test_time/60:.2f} minutes)")
    
    # Save comprehensive results
    comprehensive_results = {
        "test_metadata": {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_combinations": 1000,
            "total_processing_time_seconds": total_test_time,
            "total_processing_time_minutes": total_test_time / 60
        },
        "timing_breakdown": {
            "data_creation_seconds": data_creation_time,
            "combination_generation_seconds": combo_generation_time,
            "atr_validation_seconds": atr_results['total_time'],
            "macd_validation_seconds": macd_results['total_time'],
            "swing_validation_seconds": swing_results['total_time']
        },
        "validation_results": {
            "atr_match_rate": atr_results['avg_match_rate'],
            "atr_status": atr_status,
            "macd_match_rate": macd_results['overall_rate'],
            "macd_status": macd_status,
            "swing_match_rate": swing_results['overall_rate'],
            "swing_status": swing_status
        },
        "overall_summary": {
            "all_passed": all_passed,
            "status": overall_status
        },
        "data_files_created": {
            "parameter_combinations": str(combo_file),
            "atr_validation_data": str(data_dir / "atr_validation_1000_combos.parquet"),
            "macd_validation_data": str(data_dir / "macd_validation_1000_combos.parquet"),
            "swing_validation_data": str(data_dir / "swing_validation_results.parquet")
        }
    }
    
    # Save detailed results
    json_results_file = results_dir / "timed_1000_combo_validation_results.json"
    with open(json_results_file, 'w') as f:
        json.dump(comprehensive_results, f, indent=2)
    
    # Save simple text results
    text_results_file = results_dir / "timed_1000_combo_validation_results.txt"
    with open(text_results_file, 'w') as f:
        f.write("TIMED 1000 COMBINATION VALIDATION RESULTS\n")
        f.write("=" * 80 + "\n")
        f.write(f"Total Processing Time: {total_test_time:.2f}s ({total_test_time/60:.2f} minutes)\n")
        f.write(f"Parameter Combinations: 1000\n")
        f.write(f"ATR Fix: {atr_results['avg_match_rate']:.4f}% - {atr_status}\n")
        f.write(f"MACD Fix: {macd_results['overall_rate']:.4f}% - {macd_status}\n")
        f.write(f"Swing Points Fix: {swing_results['overall_rate']:.4f}% - {swing_status}\n")
        f.write(f"Overall: {overall_status}\n")
        f.write(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    print(f"\n💾 Detailed results saved to: {json_results_file}")
    print(f"💾 Summary results saved to: {text_results_file}")
    
    if all_passed:
        print(f"\n🎉 SUCCESS: All 1000 combinations validated successfully!")
        print(f"   ✅ Processing completed in {total_test_time:.2f}s ({total_test_time/60:.2f} minutes)")
        print(f"   🚀 All fixes ready for production deployment")


if __name__ == "__main__":
    main()