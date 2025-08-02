"""
Simple 1000 Combination Test - Based on working windows_path_1000_combo_test.py
Generates 1000 combinations and saves combo data with metadata
"""

import time
import pandas as pd
import numpy as np
from pathlib import Path
import sys
import json
from typing import List, Dict
import warnings
warnings.filterwarnings('ignore')

# Add src to path for imports
sys.path.append(str(Path(__file__).parent.parent / 'src'))

from feature_engineering.array_backend import ArrayBackend
from feature_engineering.atr_calculator import ATRCalculator
from feature_engineering.macd_calculator import MACDCalculator

# Add legacy functions path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root / "source_repos" / "EnergyTrading" / "Python" / "Utilities"))

from predictors_tools import compute_realtime_atr, compute_realtime_macd

def generate_test_data():
    """Generate test data in same format as working test"""
    print("📂 Generating test data...")
    
    # Create realistic price data over 3 months
    np.random.seed(42)
    n_ticks = 10000
    
    # Generate datetime index
    start_date = pd.Timestamp('2025-04-01 10:00:00')
    dates = pd.date_range(start=start_date, periods=n_ticks, freq='30s')
    
    # Generate realistic price walk
    base_price = 77.5
    price_changes = np.random.normal(0, 0.05, n_ticks)
    prices = base_price + np.cumsum(price_changes)
    
    # Create trades DataFrame
    trades_df = pd.DataFrame({
        'datetime': dates,
        'price': prices
    })
    
    # Create hourly candles for historical data
    trades_indexed = trades_df.set_index('datetime')
    candles = trades_indexed.groupby(pd.Grouper(freq='1h')).agg({
        'price': ['first', 'max', 'min', 'last']
    }).dropna()
    candles.columns = ['open', 'high', 'low', 'close']
    historical_candles = candles.reset_index()
    
    print(f"✅ Created {len(trades_df)} trade records and {len(historical_candles)} historical candles")
    
    return trades_df, historical_candles

def generate_1000_combinations():
    """Generate 1000 parameter combinations"""
    print("🔢 Generating 1000 parameter combinations...")
    
    combinations = []
    
    for i in range(1000):
        combo = {
            'combo_id': i,
            'atr_lookback': 10 + (i % 40),      # 10-49
            'macd_short': 5 + (i % 15),         # 5-19
            'macd_long': 20 + (i % 30),         # 20-49
            'macd_signal': 5 + (i % 10)         # 5-14
        }
        combinations.append(combo)
    
    print(f"✅ Generated {len(combinations)} combinations")
    return combinations

def validate_atr_and_save_combo_data(trades_df: pd.DataFrame, historical_candles: pd.DataFrame, 
                                    combinations: List[Dict], data_dir: Path):
    """Validate ATR and save individual combination data"""
    print("\n🔧 ATR VALIDATION WITH COMBO DATA SAVING")
    print("=" * 60)
    
    start_time = time.time()
    
    # Initialize GPU implementation
    backend = ArrayBackend()
    atr_calc = ATRCalculator(backend)
    
    all_results = []
    files_created = []
    
    print(f"🔄 Processing {len(combinations)} ATR combinations...")
    
    for i, combo in enumerate(combinations):
        combo_start_time = time.time()
        atr_period = combo['atr_lookback']
        combo_id = combo['combo_id']
        
        try:
            # Use subset for processing (same as working test)
            test_trades = trades_df.head(800)
            
            # GPU implementation
            gpu_result = atr_calc.compute_atr(
                trades_df=test_trades,
                historical_candles=historical_candles,
                atr_period=atr_period,
                price_col='price',
                datetime_col='datetime',
                candle_granularity='1h'
            )
            
            # Legacy implementation (correct function)
            legacy_result = compute_realtime_atr(
                trades_df=test_trades,
                historical_candles=historical_candles,
                atr_period=atr_period,
                price_col='price',
                datetime_col='datetime',
                candle_granularity='1h'
            )
            
            # Compare results
            gpu_values = gpu_result['atr'].dropna()
            legacy_values = legacy_result['atr'].dropna()
            
            min_len = min(len(gpu_values), len(legacy_values))
            if min_len > 0:
                gpu_subset = gpu_values.iloc[:min_len]
                legacy_subset = legacy_values.iloc[:min_len]
                
                differences = np.abs(gpu_subset - legacy_subset)
                max_diff = differences.max()
                matches = differences <= 1e-10
                match_rate = (matches.sum() / len(matches)) * 100
            else:
                match_rate = 0.0
                max_diff = float('inf')
            
            # Create combo data with ATR features
            combo_data = gpu_result.copy()
            combo_data['combo_id'] = combo_id
            combo_data['atr_period'] = atr_period
            
            # Save to combo file
            combo_file = data_dir / f"combo_{combo_id:03d}.parquet"
            combo_data.to_parquet(combo_file, index=False)
            files_created.append(combo_file)
            
            combo_time = time.time() - combo_start_time
            
            result = {
                'combo_id': combo_id,
                'atr_period': atr_period,
                'match_rate': match_rate,
                'max_difference': max_diff,
                'processing_time': combo_time,
                'result_shape': combo_data.shape,
                'gpu_atr_mean': gpu_values.mean() if len(gpu_values) > 0 else 0,
                'legacy_atr_mean': legacy_values.mean() if len(legacy_values) > 0 else 0
            }
            all_results.append(result)
            
            if (i + 1) % 100 == 0:
                avg_match = np.mean([r['match_rate'] for r in all_results[-100:]])
                print(f"✅ Processed {i + 1:3d}/1000 ATR combinations - Avg match rate: {avg_match:.2f}%")
                
        except Exception as e:
            print(f"❌ Error processing ATR combo {combo_id}: {e}")
            continue
    
    processing_time = time.time() - start_time
    print(f"\n✅ ATR Processing complete: {len(files_created)} combo files created in {processing_time:.2f}s")
    return all_results

def validate_macd_and_update_combo_data(trades_df: pd.DataFrame, historical_candles: pd.DataFrame, 
                                       combinations: List[Dict], data_dir: Path):
    """Validate MACD and update existing combo files"""
    print("\n🔧 MACD VALIDATION AND COMBO DATA UPDATE")
    print("=" * 60)
    
    start_time = time.time()
    
    # Initialize GPU implementation
    backend = ArrayBackend()
    macd_calc = MACDCalculator(backend)
    
    all_results = []
    
    print(f"🔄 Processing {len(combinations)} MACD combinations...")
    
    for i, combo in enumerate(combinations):
        combo_start_time = time.time()
        combo_id = combo['combo_id']
        
        try:
            # Use subset for processing
            test_trades = trades_df.head(800)
            
            # GPU implementation
            gpu_result = macd_calc.compute_macd(
                trades_df=test_trades,
                historical_candles=historical_candles,
                short_period=combo['macd_short'],
                long_period=combo['macd_long'],
                signal_period=combo['macd_signal'],
                price_col='price',
                datetime_col='datetime',
                candle_granularity='1h'
            )
            
            # Legacy implementation (correct function)
            legacy_result = compute_realtime_macd(
                trades_df=test_trades,
                historical_candles=historical_candles,
                short_period=combo['macd_short'],
                long_period=combo['macd_long'],
                signal_period=combo['macd_signal'],
                price_col='price',
                datetime_col='datetime',
                candle_granularity='1h'
            )
            
            # Compare MACD line
            gpu_macd = gpu_result['macd_line'].dropna()
            legacy_macd = legacy_result['macd_line'].dropna()
            
            min_len = min(len(gpu_macd), len(legacy_macd))
            if min_len > 0:
                gpu_subset = gpu_macd.iloc[:min_len]
                legacy_subset = legacy_macd.iloc[:min_len]
                
                differences = np.abs(gpu_subset - legacy_subset)
                matches = differences <= 1e-10
                match_rate = (matches.sum() / len(matches)) * 100
            else:
                match_rate = 0.0
            
            # Update existing combo file with MACD features
            combo_file = data_dir / f"combo_{combo_id:03d}.parquet"
            if combo_file.exists():
                combo_data = pd.read_parquet(combo_file)
                combo_data['macd_line'] = gpu_result.get('macd_line', np.nan)
                combo_data['macd_signal'] = gpu_result.get('macd_signal', np.nan)
                combo_data['macd_histogram'] = gpu_result.get('macd_histogram', np.nan)
                combo_data['macd_short'] = combo['macd_short']
                combo_data['macd_long'] = combo['macd_long']
                combo_data['macd_signal_period'] = combo['macd_signal']
                combo_data.to_parquet(combo_file, index=False)
            
            combo_time = time.time() - combo_start_time
            
            result = {
                'combo_id': combo_id,
                'macd_short': combo['macd_short'],
                'macd_long': combo['macd_long'],
                'macd_signal_period': combo['macd_signal'],
                'match_rate': match_rate,
                'processing_time': combo_time
            }
            all_results.append(result)
            
            if (i + 1) % 100 == 0:
                avg_match = np.mean([r['match_rate'] for r in all_results[-100:]])
                print(f"✅ Processed {i + 1:3d}/1000 MACD combinations - Avg match rate: {avg_match:.2f}%")
                
        except Exception as e:
            print(f"❌ Error processing MACD combo {combo_id}: {e}")
            continue
    
    processing_time = time.time() - start_time
    print(f"\n✅ MACD Processing complete in {processing_time:.2f}s")
    return all_results

def main():
    """Main execution"""
    print("🎯 SIMPLE 1000 COMBINATION TEST")
    print("=" * 50)
    print("✅ Generate realistic test data")
    print("✅ Create 1000 parameter combinations")
    print("✅ Validate against correct legacy functions")
    print("✅ Save combo datasets with metadata")
    print()
    
    # Setup output directory
    output_base = "/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data"
    data_dir = Path(f"{output_base}/data")
    data_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"📁 Output Directory: {data_dir}")
    
    try:
        start_time = time.time()
        
        # Generate test data
        trades_df, historical_candles = generate_test_data()
        
        # Generate 1000 combinations
        combinations = generate_1000_combinations()
        
        # Validate ATR and create combo files
        atr_results = validate_atr_and_save_combo_data(trades_df, historical_candles, combinations, data_dir)
        
        # Validate MACD and update combo files
        macd_results = validate_macd_and_update_combo_data(trades_df, historical_candles, combinations, data_dir)
        
        total_time = time.time() - start_time
        
        # Create metadata
        metadata_records = []
        for combo in combinations:
            atr_result = next((r for r in atr_results if r['combo_id'] == combo['combo_id']), {})
            macd_result = next((r for r in macd_results if r['combo_id'] == combo['combo_id']), {})
            
            metadata_record = {
                'combo_id': combo['combo_id'],
                'atr_lookback': combo['atr_lookback'],
                'macd_short': combo['macd_short'],
                'macd_long': combo['macd_long'],
                'macd_signal': combo['macd_signal'],
                'atr_match_rate': atr_result.get('match_rate', 0.0),
                'macd_match_rate': macd_result.get('match_rate', 0.0),
                'atr_processing_time': atr_result.get('processing_time', 0.0),
                'macd_processing_time': macd_result.get('processing_time', 0.0),
                'result_shape_rows': atr_result.get('result_shape', (0, 0))[0],
                'result_shape_cols': atr_result.get('result_shape', (0, 0))[1]
            }
            metadata_records.append(metadata_record)
        
        # Save metadata
        if metadata_records:
            metadata_df = pd.DataFrame(metadata_records)
            metadata_file = Path(output_base) / "combinations_metadata.parquet"
            metadata_df.to_parquet(metadata_file, index=False)
            print(f"✅ Saved metadata for {len(metadata_records)} combinations")
        
        # Calculate statistics
        avg_atr_match = np.mean([r.get('match_rate', 0) for r in atr_results])
        avg_macd_match = np.mean([r.get('match_rate', 0) for r in macd_results])
        combo_files_created = len(list(data_dir.glob('combo_*.parquet')))
        
        # Results summary
        print(f"\n🎉 1000 COMBINATION TEST COMPLETE!")
        print("=" * 60)
        print(f"📊 Results:")
        print(f"   Total combinations: {len(combinations)}")
        print(f"   Total processing time: {total_time:.2f}s ({total_time/60:.2f} minutes)")
        print(f"   ATR average match rate: {avg_atr_match:.4f}%")
        print(f"   MACD average match rate: {avg_macd_match:.4f}%")
        print(f"   Combo files created: {combo_files_created}")
        
        # Save summary
        summary = {
            'test_metadata': {
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'total_combinations': len(combinations),
                'total_processing_time_seconds': total_time,
                'total_processing_time_minutes': total_time / 60,
                'windows_save_location': output_base
            },
            'validation_results': {
                'atr_avg_match_rate': avg_atr_match,
                'macd_avg_match_rate': avg_macd_match,
                'combo_files_created': combo_files_created
            },
            'files_created': {
                'base_directory': output_base,
                'data_directory': str(data_dir),
                'metadata_file': str(Path(output_base) / "combinations_metadata.parquet"),
                'combo_files': combo_files_created
            }
        }
        
        with open(Path(output_base) / "simple_1000_combo_summary.json", 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        print(f"\n🎊 SUCCESS! Results saved to: {output_base}")
        print(f"📂 Data files: {data_dir}")
        print(f"📋 Metadata: {Path(output_base) / 'combinations_metadata.parquet'}")
        print(f"📄 Summary: {Path(output_base) / 'simple_1000_combo_summary.json'}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Processing failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    if not success:
        sys.exit(1)