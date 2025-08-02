"""
Corrected Legacy Data GPU Test - 1000 Combinations
- Uses proper DatetimeIndex from legacy data
- Creates hourly candles
- Simple data/ folder structure with metadata parquet
- Processes 1000 parameter combinations
"""

import asyncio
import time
import pandas as pd
import numpy as np
from pathlib import Path
import sys
import json
import warnings
from typing import List, Dict
warnings.filterwarnings('ignore')

# Add src to path for imports
sys.path.append(str(Path(__file__).parent.parent / 'src'))

# Import the feature engineering modules
from feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline
from feature_engineering.array_backend import ArrayBackend
from feature_engineering.atr_calculator import ATRCalculator
from feature_engineering.macd_calculator import MACDCalculator

# Add legacy functions path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root / "source_repos" / "EnergyTrading" / "Python" / "Utilities"))

from predictors_tools import compute_realtime_atr, compute_realtime_macd

def load_and_convert_legacy_data():
    """Load and convert real legacy backtest data to hourly OHLCV"""
    print("📂 Loading real legacy backtest data...")
    
    legacy_data_path = "/mnt/c/Users/krajcovic/Documents/Testing Data/backtest_data/dem07_25_tr_ba_data.parquet"
    
    try:
        # Load tick data with proper DatetimeIndex
        tick_data = pd.read_parquet(legacy_data_path)
        print(f"✅ Loaded tick data: {len(tick_data):,} rows")
        print(f"   Index type: {type(tick_data.index)}")
        print(f"   Date range: {tick_data.index.min()} to {tick_data.index.max()}")
        print(f"   Columns: {list(tick_data.columns)}")
        
        # Convert tick data to hourly OHLCV bars
        print("🔄 Converting tick data to hourly OHLCV format...")
        
        # Resample to hourly bars using the existing DatetimeIndex
        ohlcv_data = tick_data['price'].resample('1h').agg({
            'open': 'first',
            'high': 'max', 
            'low': 'min',
            'close': 'last'
        }).dropna()
        
        # Add volume (sum tick volumes over hourly periods)
        if 'volume' in tick_data.columns:
            volume_data = tick_data['volume'].resample('1h').sum()
            ohlcv_data['volume'] = volume_data.fillna(0)
        else:
            ohlcv_data['volume'] = np.random.exponential(1500, len(ohlcv_data))
        
        # Reset index to get timestamp column
        contract_data = ohlcv_data.reset_index()
        contract_data.rename(columns={'index': 'timestamp'}, inplace=True)
        
        # Also create trades format for validation
        trades_data = tick_data[['price']].reset_index()
        trades_data.rename(columns={'datetime': 'datetime'}, inplace=True)
        
        print(f"✅ Converted to hourly OHLCV: {contract_data.shape}")
        print(f"   Date range: {contract_data['timestamp'].min()} to {contract_data['timestamp'].max()}")
        print(f"   Columns: {list(contract_data.columns)}")
        
        # Show sample of converted data
        print(f"\n📋 Sample hourly OHLCV data:")
        print(contract_data.head(3).to_string(index=False))
        
        return contract_data, trades_data
        
    except Exception as e:
        print(f"❌ Failed to load legacy data: {e}")
        import traceback
        traceback.print_exc()
        return None, None

def generate_1000_combinations():
    """Generate 1000 parameter combinations"""
    print("🔢 Generating 1000 parameter combinations...")
    
    combinations = []
    
    for i in range(1000):
        # More diverse parameter variations
        combo = {
            'combo_id': i,
            'atr_lookback': 10 + (i % 40),  # 10-49
            'macd_short': 5 + (i % 15),     # 5-19
            'macd_long': 20 + (i % 30),     # 20-49
            'macd_signal': 5 + (i % 10)     # 5-14
        }
        combinations.append(combo)
    
    print(f"✅ Generated {len(combinations)} combinations")
    return combinations

def validate_atr_with_legacy(trades_df: pd.DataFrame, historical_candles: pd.DataFrame, 
                            combinations: List[Dict], data_dir: Path):
    """Validate ATR against legacy functions and save combo data"""
    print("\n🔧 ATR VALIDATION WITH COMBO DATA SAVING")
    print("=" * 60)
    
    # Initialize GPU implementation
    backend = ArrayBackend()
    atr_calc = ATRCalculator(backend)
    
    all_results = []
    files_created = []
    
    for i, combo in enumerate(combinations):
        combo_start_time = time.time()
        atr_period = combo['atr_lookback']
        combo_id = combo['combo_id']
        
        try:
            # Use subset for processing
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
            
            # Legacy implementation
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
            
            # Save combo data with features
            combo_data = gpu_result.copy()
            combo_data['combo_id'] = combo_id
            combo_data['atr_period'] = atr_period
            
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
                print(f"✅ Processed {i + 1:3d}/1000 combinations - Match rate: {match_rate:.2f}%")
                
        except Exception as e:
            print(f"❌ Error processing combo {combo_id}: {e}")
            continue
    
    print(f"\n✅ ATR Processing complete: {len(files_created)} combo files created")
    return all_results

def validate_macd_with_legacy(trades_df: pd.DataFrame, historical_candles: pd.DataFrame, 
                             combinations: List[Dict], data_dir: Path):
    """Validate MACD against legacy functions"""
    print("\n🔧 MACD VALIDATION")
    print("=" * 60)
    
    # Initialize GPU implementation
    backend = ArrayBackend()
    macd_calc = MACDCalculator(backend)
    
    all_results = []
    
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
            
            # Legacy implementation
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
            
            # Update combo data with MACD features
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
                print(f"✅ Processed {i + 1:3d}/1000 combinations - Match rate: {match_rate:.2f}%")
                
        except Exception as e:
            print(f"❌ Error processing MACD combo {combo_id}: {e}")
            continue
    
    print(f"\n✅ MACD Processing complete")
    return all_results

async def process_1000_combinations():
    """Process 1000 combinations with GPU validation"""
    print("🚀 1000 COMBINATION GPU PROCESSING WITH VALIDATION")
    print("=" * 70)
    
    # Setup output directory
    output_base = "/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data"
    data_dir = Path(f"{output_base}/data")
    data_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"📁 Output Directory: {data_dir}")
    
    try:
        # Load and convert legacy data
        contract_data, trades_data = load_and_convert_legacy_data()
        if contract_data is None or trades_data is None:
            return False
        
        # Generate 1000 combinations
        combinations = generate_1000_combinations()
        
        start_time = time.time()
        
        # Validate ATR and create combo files
        atr_results = validate_atr_with_legacy(trades_data, contract_data, combinations, data_dir)
        
        # Validate MACD and update combo files
        macd_results = validate_macd_with_legacy(trades_data, contract_data, combinations, data_dir)
        
        total_time = time.time() - start_time
        
        # Create metadata
        metadata_records = []
        for i, combo in enumerate(combinations):
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
        
        # Calculate averages
        avg_atr_match = np.mean([r.get('match_rate', 0) for r in atr_results])
        avg_macd_match = np.mean([r.get('match_rate', 0) for r in macd_results])
        
        # Results summary
        print(f"\n🎉 1000 COMBINATION PROCESSING COMPLETE!")
        print("=" * 60)
        print(f"📊 Results:")
        print(f"   Total combinations: {len(combinations)}")
        print(f"   Total processing time: {total_time:.2f}s ({total_time/60:.2f} minutes)")
        print(f"   ATR average match rate: {avg_atr_match:.4f}%")
        print(f"   MACD average match rate: {avg_macd_match:.4f}%")
        print(f"   Combo files created: {len(list(data_dir.glob('combo_*.parquet')))}")
        
        # Save summary
        summary = {
            'test_metadata': {
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'total_combinations': len(combinations),
                'total_processing_time_seconds': total_time,
                'total_processing_time_minutes': total_time / 60,
                'data_directory': str(data_dir)
            },
            'validation_results': {
                'atr_avg_match_rate': avg_atr_match,
                'macd_avg_match_rate': avg_macd_match,
                'combo_files_created': len(list(data_dir.glob('combo_*.parquet')))
            }
        }
        
        with open(Path(output_base) / "1000_combo_summary.json", 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        return True
        
    except Exception as e:
        print(f"\n❌ Processing failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Main execution"""
    print("🎯 1000 COMBINATION LEGACY DATA GPU TEST")
    print("=" * 50)
    print("✅ Load real legacy data with proper DatetimeIndex")
    print("✅ Convert to hourly OHLCV candles")
    print("✅ Generate 1000 parameter variations")
    print("✅ Validate against correct legacy functions")
    print("✅ Save combo datasets with metadata")
    
    success = await process_1000_combinations()
    
    if success:
        print(f"\n🎊 SUCCESS! 1000 combination processing complete!")
        print(f"📂 Results saved to: C:\\Users\\krajcovic\\Documents\\Testing Data\\ATS_3_data")
    else:
        print(f"\n💥 Processing failed")

if __name__ == "__main__":
    asyncio.run(main())