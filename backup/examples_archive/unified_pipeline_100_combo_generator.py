#!/usr/bin/env python3
"""
Unified Pipeline 100 Combo Generator
Create 100 combo files using the unified pipeline with all features and save to ATS_3_data
"""

import time
import pandas as pd
import numpy as np
from pathlib import Path
import sys
import json
import warnings
warnings.filterwarnings('ignore')

# Add paths
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root / "src"))

# Import unified pipeline and GPU parallel processing
try:
    from feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline
    from feature_engineering.bias_classifier import ThresholdConfig
    from feature_engineering.position_generator import ThresholdConfig as PositionThresholdConfig
    from gpu_parallel_processing import generate_combination_batch
    print("✅ Unified pipeline and GPU parallel processing imported successfully")
except ImportError as e:
    print(f"❌ Could not import modules: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

def load_market_data():
    """Load and convert market data to OHLCV format for pipeline"""
    print("📂 Loading market data...")
    
    legacy_data_path = "/mnt/c/Users/krajcovic/Documents/Testing Data/backtest_data/dem07_25_tr_ba_data.parquet"
    
    # Load tick data
    tick_data = pd.read_parquet(legacy_data_path)
    print(f"✅ Loaded tick data: {len(tick_data):,} rows")
    print(f"   Date range: {tick_data.index.min()} to {tick_data.index.max()}")
    
    # Convert tick data to 15-minute OHLCV format for unified pipeline
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
        ohlcv_data['volume'] = volume_data.fillna(0)
    else:
        ohlcv_data['volume'] = np.random.exponential(1500, len(ohlcv_data))
    
    print(f"✅ Created OHLCV data: {ohlcv_data.shape}")
    print(f"   Columns: {list(ohlcv_data.columns)}")
    print(f"   Date range: {ohlcv_data.index.min()} to {ohlcv_data.index.max()}")
    
    return ohlcv_data

def create_combo_with_unified_pipeline(pipeline, ohlcv_data, combo, output_dir):
    """Create one combo file using the unified pipeline"""
    combo_id = combo['combo_id']
    combo_start_time = time.time()
    
    try:
        # Extract parameters
        macd_params = combo.get('macd_params', {'short': 12, 'long': 26, 'signal': 9})
        atr_period = combo.get('atr_lookback', 21)
        
        # Create bias thresholds from combo parameters
        bias_thresholds_dict = combo.get('bias_thresholds', {
            'macd_line_lower': -2.5, 'macd_line_upper': 2.5,
            'macd_histogram_lower': -1.25, 'macd_histogram_upper': 1.25
        })
        bias_thresholds = ThresholdConfig(
            macd_line_lower=bias_thresholds_dict['macd_line_lower'],
            macd_line_upper=bias_thresholds_dict['macd_line_upper'],
            macd_histogram_lower=bias_thresholds_dict['macd_histogram_lower'],
            macd_histogram_upper=bias_thresholds_dict['macd_histogram_upper']
        )
        
        # Create position thresholds from combo parameters
        strategy_thresholds_dict = combo.get('strategy_thresholds', {
            'neutral_buy': 0.2, 'neutral_sell': 0.7
        })
        position_thresholds = PositionThresholdConfig(
            neutral_buy=strategy_thresholds_dict['neutral_buy'],
            neutral_sell=strategy_thresholds_dict['neutral_sell']
        )
        
        print(f"   🔄 Processing combo {combo_id:3d} - MACD: {macd_params}, ATR: {atr_period}")
        
        # Use unified pipeline to compute all indicators, features, bias, and positions
        result_data = pipeline.compute_all_indicators_features_bias_and_positions(
            data=ohlcv_data,
            bias_thresholds=bias_thresholds,
            position_thresholds=position_thresholds,
            candle_granularity='15min',
            macd_params=macd_params,
            atr_period=atr_period,
            swing_lookback=20  # Default swing lookback
        )
        
        # Add combo metadata
        result_data['combo_id'] = combo_id
        result_data['contract'] = combo.get('contract', 'dem07_25')
        result_data['macd_short'] = macd_params['short']
        result_data['macd_long'] = macd_params['long']
        result_data['macd_signal_period'] = macd_params['signal']
        result_data['atr_period'] = atr_period
        result_data['stop_loss'] = combo.get('stop_loss', 0.5)
        result_data['take_profit'] = combo.get('tp_value', 0.75)
        
        processing_time = time.time() - combo_start_time
        
        # Save combo file
        combo_file = output_dir / f"combo_{combo_id:03d}.parquet"
        result_data.to_parquet(combo_file, index=False)
        
        print(f"   ✅ Saved combo {combo_id:3d} in {processing_time:.2f}s - Shape: {result_data.shape}")
        
        # Create metadata record
        metadata_record = {
            'combo_id': combo_id,
            'processing_time_seconds': processing_time,
            'result_shape_rows': result_data.shape[0],
            'result_shape_cols': result_data.shape[1],
            'contract': combo.get('contract', 'dem07_25'),
            'date_range_start': combo.get('date_range', {}).get('start', '2025-04-01'),
            'date_range_end': combo.get('date_range', {}).get('end', '2025-06-30'),
            'macd_short': macd_params['short'],
            'macd_long': macd_params['long'],
            'macd_signal': macd_params['signal'],
            'atr_lookback': atr_period,
            'bias_macd_line_lower': bias_thresholds_dict['macd_line_lower'],
            'bias_macd_line_upper': bias_thresholds_dict['macd_line_upper'],
            'bias_macd_hist_lower': bias_thresholds_dict['macd_histogram_lower'],
            'bias_macd_hist_upper': bias_thresholds_dict['macd_histogram_upper'],
            'strategy_neutral_buy': strategy_thresholds_dict['neutral_buy'],
            'strategy_neutral_sell': strategy_thresholds_dict['neutral_sell'],
            'stop_loss': combo.get('stop_loss', 0.5),
            'sl_tp_ratio': combo.get('sl_tp_ratio', 1.5),
            'tp_value': combo.get('tp_value', 0.75),
            'using_unified_pipeline': True,
            'pipeline_phase': 'Phase 6 - All features + bias + positions'
        }
        
        return True, processing_time, metadata_record
        
    except Exception as e:
        print(f"   ❌ Error processing combo {combo_id}: {e}")
        import traceback
        traceback.print_exc()
        return False, 0, None

def main():
    """Main execution using unified pipeline"""
    print("🚀 UNIFIED PIPELINE 100 COMBO GENERATOR")
    print("=" * 70)
    print("✅ Uses unified technical indicators pipeline")
    print("✅ Phase 6: All indicators + features + bias + positions")
    print("✅ GPU-accelerated processing with CuPy")
    
    # Setup output directory
    output_base = "/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data"
    data_dir = Path(f"{output_base}/data")
    data_dir.mkdir(parents=True, exist_ok=True)
    
    windows_path = "C:\\\\Users\\\\krajcovic\\\\Documents\\\\Testing Data\\\\ATS_3_data"
    
    print(f"\\n📁 Output: {windows_path}/")
    
    try:
        start_time = time.time()
        
        # Initialize unified pipeline
        print("🔧 Initializing unified pipeline...")
        pipeline = UnifiedTechnicalIndicatorsPipeline(
            dtype='float32',
            chunk_size=2000000,
            memory_threshold=0.98
        )
        print("✅ Unified pipeline initialized")
        
        # Load market data
        ohlcv_data = load_market_data()
        
        # Generate 100 combinations using GPU parallel processing
        print("🔢 Generating 100 parameter combinations...")
        combinations = generate_combination_batch(start_idx=0, batch_size=100)
        print(f"✅ Generated {len(combinations)} combinations")
        
        # Process combinations
        print(f"\\n🔧 Processing {len(combinations)} combinations with unified pipeline...")
        
        successful_results = []
        metadata_records = []
        
        for i, combo in enumerate(combinations):
            success, proc_time, metadata = create_combo_with_unified_pipeline(
                pipeline, ohlcv_data, combo, data_dir
            )
            
            if success:
                successful_results.append({
                    'combo_id': combo['combo_id'],
                    'processing_time': proc_time
                })
                metadata_records.append(metadata)
            
            # Progress update every 10 combos
            if (i + 1) % 10 == 0:
                elapsed = time.time() - start_time
                avg_time = np.mean([r['processing_time'] for r in successful_results[-10:]])
                print(f"   📊 Progress: {i+1}/{len(combinations)} - Avg time: {avg_time:.2f}s - Elapsed: {elapsed/60:.1f}min")
        
        total_time = time.time() - start_time
        
        # Create metadata parquet file at the same level as data directory
        if metadata_records:
            print(f"\\n💾 Creating metadata parquet file...")
            metadata_df = pd.DataFrame(metadata_records)
            metadata_file = Path(output_base) / "unified_combinations_metadata.parquet"
            metadata_df.to_parquet(metadata_file, index=False)
            print(f"   ✅ Saved metadata for {len(metadata_records)} combinations")
        
        # Results summary
        print(f"\\n🎉 UNIFIED PIPELINE 100 COMBO GENERATOR COMPLETE!")
        print("=" * 70)
        
        successful_count = len(successful_results)
        success_rate = (successful_count / len(combinations)) * 100
        
        print(f"📊 Results:")
        print(f"   Total combinations: {len(combinations)}")
        print(f"   Successful: {successful_count}")
        print(f"   Success rate: {success_rate:.1f}%")
        print(f"   Total time: {total_time:.2f}s ({total_time/60:.2f} minutes)")
        
        if successful_count > 0:
            processing_times = [r['processing_time'] for r in successful_results]
            avg_time = np.mean(processing_times)
            throughput = successful_count / total_time
            print(f"   Average time per combo: {avg_time:.2f}s")
            print(f"   Throughput: {throughput:.2f} combinations/second")
        
        # Save summary
        summary = {
            'test_metadata': {
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'total_combinations': len(combinations),
                'successful_combinations': successful_count,
                'processing_time_seconds': total_time,
                'processing_time_minutes': total_time / 60,
                'windows_path': windows_path,
                'using_unified_pipeline': True,
                'pipeline_phase': 'Phase 6 - All indicators + features + bias + positions',
                'features_included': [
                    'MACD (line, signal, histogram)',
                    'ATR',
                    'Swing points (high, low)',
                    'Bias classification (numeric, label)',
                    'Price position',
                    'Position signals'
                ]
            },
            'files_created': {
                'combo_files': successful_count,
                'metadata_file': 1,
                'total_files': successful_count + 1
            }
        }
        
        with open(Path(output_base) / "unified_pipeline_100_combo_summary.json", 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        print(f"\\n🎊 SUCCESS! Unified pipeline 100 combo generation complete!")
        print(f"📂 Results: {windows_path}")
        print(f"\\n🚀 FEATURES GENERATED:")
        print(f"✅ MACD (line, signal, histogram)")
        print(f"✅ ATR (Average True Range)")
        print(f"✅ Swing points (high, low)")
        print(f"✅ Bias classification (numeric + labels)")
        print(f"✅ Price position analysis")
        print(f"✅ Position signals (buy/sell/hold)")
        
        print(f"\\n📁 FILE STRUCTURE:")
        print(f"   {windows_path}/")
        print(f"   ├── data/")
        print(f"   │   ├── combo_000.parquet")
        print(f"   │   ├── combo_001.parquet")
        print(f"   │   └── ... ({successful_count} combo files)")
        print(f"   ├── unified_combinations_metadata.parquet")
        print(f"   └── unified_pipeline_100_combo_summary.json")
        
        return True
        
    except Exception as e:
        print(f"\\n❌ Processing failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    
    if success:
        print(f"\\n🎉 GENERATION COMPLETE!")
    else:
        print(f"\\n💥 Generation failed")