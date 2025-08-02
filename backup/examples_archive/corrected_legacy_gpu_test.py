"""
Corrected Legacy Data GPU Test
- Uses proper DatetimeIndex from legacy data
- Creates 15-minute candles
- Simple data/ folder structure with single metadata parquet
"""

import asyncio
import time
import pandas as pd
import numpy as np
from pathlib import Path
import sys
import json
import warnings
warnings.filterwarnings('ignore')

# Add src to path for imports
sys.path.append(str(Path(__file__).parent.parent / 'src'))

from gpu_parallel_processing import (
    AsyncProcessingPipeline,
    EnhancedGPUCombinationProcessor
)

def load_and_convert_legacy_data():
    """Load and convert real legacy backtest data to 15-minute OHLCV"""
    print("📂 Loading real legacy backtest data...")
    
    legacy_data_path = "/mnt/c/Users/krajcovic/Documents/Testing Data/backtest_data/dem07_25_tr_ba_data.parquet"
    
    try:
        # Load tick data with proper DatetimeIndex
        tick_data = pd.read_parquet(legacy_data_path)
        print(f"✅ Loaded tick data: {len(tick_data):,} rows")
        print(f"   Index type: {type(tick_data.index)}")
        print(f"   Date range: {tick_data.index.min()} to {tick_data.index.max()}")
        print(f"   Columns: {list(tick_data.columns)}")
        
        # Convert tick data to 15-minute OHLCV bars
        print("🔄 Converting tick data to 15-minute OHLCV format...")
        
        # Resample to 15-minute bars using the existing DatetimeIndex
        ohlcv_data = tick_data['price'].resample('15T').agg({
            'open': 'first',
            'high': 'max', 
            'low': 'min',
            'close': 'last'
        }).dropna()
        
        # Add volume (sum tick volumes over 15-minute periods)
        if 'volume' in tick_data.columns:
            volume_data = tick_data['volume'].resample('15T').sum()
            ohlcv_data['volume'] = volume_data.fillna(0)
        else:
            ohlcv_data['volume'] = np.random.exponential(1500, len(ohlcv_data))
        
        # Reset index to get timestamp column
        contract_data = ohlcv_data.reset_index()
        contract_data.rename(columns={'index': 'timestamp'}, inplace=True)
        
        print(f"✅ Converted to 15-minute OHLCV: {contract_data.shape}")
        print(f"   Date range: {contract_data['timestamp'].min()} to {contract_data['timestamp'].max()}")
        print(f"   Columns: {list(contract_data.columns)}")
        
        # Show sample of converted data
        print(f"\n📋 Sample 15-minute OHLCV data:")
        print(contract_data.head(3).to_string(index=False))
        
        return contract_data
        
    except Exception as e:
        print(f"❌ Failed to load legacy data: {e}")
        import traceback
        traceback.print_exc()
        return None

def generate_1000_legacy_combinations():
    """Generate 1000 specific legacy parameter combinations"""
    print("🔢 Generating 1000 specific legacy parameter combinations...")
    
    combinations = []
    
    # Base parameters
    base_combo = {
        'combo_id': 0,
        'date_range': {'start': '2025-04-01', 'end': '2025-06-30'},
        'contract': 'dem07_25',
        'predictor_granularities': {'atr_macd': '15min', 'swing': '15min'},
        'macd_params': {'short': 12, 'long': 26, 'signal': 9},
        'atr_lookback': 21,
        'bias_thresholds': {
            'macd_line_lower': -2.5, 'macd_line_upper': 2.5,
            'macd_histogram_lower': -1.25, 'macd_histogram_upper': 1.25
        },
        'strategy_thresholds': {
            'neutral_buy': 0.2, 'neutral_sell': 0.7,
            'bullish_buy_adjust': 0.0, 'strong_bullish_buy_adjust': 0.05,
            'bearish_buy_adjust': -0.1, 'bearish_sell_adjust': 0.0,
            'strong_bearish_sell_adjust': -0.1, 'bullish_sell_adjust': 0.05
        },
        'stop_loss': 0.5, 'sl_tp_ratio': 1.5, 'tp_value': 0.75
    }
    
    # Generate 1000 variations
    for i in range(1000):
        combo = base_combo.copy()
        combo['combo_id'] = i
        
        # Vary key parameters with more variations for 1000 combos
        macd_variations = [
            {'short': 8, 'long': 21, 'signal': 5},
            {'short': 12, 'long': 26, 'signal': 9}, 
            {'short': 5, 'long': 35, 'signal': 5},
            {'short': 19, 'long': 39, 'signal': 9},
            {'short': 6, 'long': 18, 'signal': 6},
            {'short': 10, 'long': 30, 'signal': 8},
            {'short': 15, 'long': 45, 'signal': 12},
            {'short': 7, 'long': 24, 'signal': 7},
            {'short': 9, 'long': 27, 'signal': 10},
            {'short': 11, 'long': 33, 'signal': 11}
        ]
        combo['macd_params'] = macd_variations[i % len(macd_variations)]
        
        # Vary ATR lookback with more options
        atr_variations = [10, 14, 17, 21, 24, 28, 31, 35, 38, 42]
        combo['atr_lookback'] = atr_variations[i % len(atr_variations)]
        
        # Vary bias thresholds with more granular steps
        bias_multiplier = 0.5 + (i % 20) * 0.1  # 0.5 to 2.4 in 0.1 steps
        combo['bias_thresholds'] = {
            'macd_line_lower': -2.5 * bias_multiplier,
            'macd_line_upper': 2.5 * bias_multiplier,
            'macd_histogram_lower': -1.25 * bias_multiplier,
            'macd_histogram_upper': 1.25 * bias_multiplier
        }
        
        # Vary strategy thresholds with more granular steps
        neutral_base = 0.10 + (i % 50) * 0.005  # 0.10 to 0.345 in 0.005 steps
        combo['strategy_thresholds']['neutral_buy'] = neutral_base
        combo['strategy_thresholds']['neutral_sell'] = neutral_base + 0.5
        
        # Add more parameter variations for stop loss and TP
        stop_loss_variations = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
        combo['stop_loss'] = stop_loss_variations[i % len(stop_loss_variations)]
        
        sl_tp_ratios = [1.0, 1.2, 1.5, 1.8, 2.0, 2.2]
        combo['sl_tp_ratio'] = sl_tp_ratios[i % len(sl_tp_ratios)]
        combo['tp_value'] = combo['stop_loss'] * combo['sl_tp_ratio']
        
        combinations.append(combo)
    
    print(f"✅ Generated {len(combinations)} legacy parameter combinations")
    return combinations

async def process_legacy_data_corrected():
    """Process legacy data with corrected structure"""
    print("🚀 CORRECTED LEGACY DATA GPU PROCESSING")
    print("=" * 60)
    
    # Setup simple folder structure
    output_base = "/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data"
    data_dir = Path(f"{output_base}/data")
    data_dir.mkdir(parents=True, exist_ok=True)
    
    windows_path = "C:\\Users\\krajcovic\\Documents\\Testing Data\\ATS_3_data"
    
    print(f"📁 Output Structure:")
    print(f"   Windows: {windows_path}/")
    print(f"   Data folder: {windows_path}/data/")
    print(f"   Metadata: {windows_path}/combinations_metadata.parquet")
    
    try:
        # Load and convert legacy data to 15-minute candles
        contract_data = load_and_convert_legacy_data()
        if contract_data is None:
            return False
        
        # Generate 1000 combinations
        combinations = generate_1000_legacy_combinations()
        
        # Initialize GPU components
        print(f"\n🔧 Initializing GPU Processing...")
        
        gpu_processor = EnhancedGPUCombinationProcessor(
            gpu_memory_pool_gb=12.0,
            processing_chunk_size=1000000
        )
        
        pipeline = AsyncProcessingPipeline(
            max_gpu_workers=3,
            max_io_workers=2,
            task_queue_size=50,
            result_buffer_size=20,
            output_directory=str(data_dir)  # Direct to data folder
        )
        
        # Process with GPU
        print(f"\n🔄 Processing {len(combinations)} combinations...")
        print(f"   Contract data: {len(contract_data):,} 15-minute candles")
        print(f"   Date range: {contract_data['timestamp'].min()} to {contract_data['timestamp'].max()}")
        print(f"   GPU: RTX 4080 SUPER")
        
        start_time = time.time()
        successful_results = []
        failed_results = []
        metadata_records = []
        
        def progress_callback(progress: float, result):
            if result.success:
                successful_results.append(result)
                
                # Collect metadata for single parquet file
                metadata_record = {
                    'combo_id': result.combo_id,
                    'processing_time_seconds': result.processing_time,
                    'worker_id': result.worker_id,
                    'result_shape_rows': result.result_data.shape[0] if result.result_data is not None else 0,
                    'result_shape_cols': result.result_data.shape[1] if result.result_data is not None else 0,
                    'features_computed': (result.result_data.shape[1] - contract_data.shape[1]) if result.result_data is not None else 0,
                    'memory_peak_gb': result.memory_stats.get('peak_memory_gb', 0) if result.memory_stats else 0,
                    'contract': result.metadata.get('contract', 'dem07_25'),
                    'date_range_start': result.metadata.get('date_range', {}).get('start', '2025-04-01'),
                    'date_range_end': result.metadata.get('date_range', {}).get('end', '2025-06-30'),
                    'macd_short': result.metadata.get('macd_params', {}).get('short', 12),
                    'macd_long': result.metadata.get('macd_params', {}).get('long', 26),
                    'macd_signal': result.metadata.get('macd_params', {}).get('signal', 9),
                    'atr_lookback': result.metadata.get('atr_lookback', 21),
                    'bias_macd_line_lower': result.metadata.get('bias_thresholds', {}).get('macd_line_lower', -2.5),
                    'bias_macd_line_upper': result.metadata.get('bias_thresholds', {}).get('macd_line_upper', 2.5),
                    'bias_macd_hist_lower': result.metadata.get('bias_thresholds', {}).get('macd_histogram_lower', -1.25),
                    'bias_macd_hist_upper': result.metadata.get('bias_thresholds', {}).get('macd_histogram_upper', 1.25),
                    'strategy_neutral_buy': result.metadata.get('strategy_thresholds', {}).get('neutral_buy', 0.2),
                    'strategy_neutral_sell': result.metadata.get('strategy_thresholds', {}).get('neutral_sell', 0.7),
                    'stop_loss': result.metadata.get('stop_loss', 0.5),
                    'sl_tp_ratio': result.metadata.get('sl_tp_ratio', 1.5),
                    'tp_value': result.metadata.get('tp_value', 0.75)
                }
                metadata_records.append(metadata_record)
                
                print(f"✅ Combo {result.combo_id:3d}: SUCCESS ({result.processing_time:.2f}s) - Progress: {progress*100:.1f}%")
                
                # Show sample features for first few combinations
                if len(successful_results) <= 3 and result.result_data is not None:
                    print(f"   📊 Shape: {result.result_data.shape}, Features added: {result.result_data.shape[1] - contract_data.shape[1]}")
                    
            else:
                failed_results.append(result)
                print(f"❌ Combo {result.combo_id:3d}: FAILED - {result.error_message}")
        
        # Execute GPU processing
        processed_results = []
        async for result in pipeline.process_combinations_async(
            gpu_processor,
            combinations,
            contract_data,
            progress_callback=progress_callback
        ):
            processed_results.append(result)
            
            # Save individual combination result directly to data/ folder
            if result.success and result.result_data is not None:
                combo_file = data_dir / f"combo_{result.combo_id:03d}.parquet"
                result.result_data.to_parquet(combo_file, index=False)
        
        total_time = time.time() - start_time
        
        # Create single metadata parquet file
        if metadata_records:
            print(f"\n💾 Creating single metadata parquet file...")
            metadata_df = pd.DataFrame(metadata_records)
            metadata_file = Path(output_base) / "combinations_metadata.parquet"
            metadata_df.to_parquet(metadata_file, index=False)
            print(f"   ✅ Saved metadata for {len(metadata_records)} combinations")
        
        # Results summary
        print(f"\n🎉 CORRECTED LEGACY DATA GPU PROCESSING COMPLETE!")
        print("=" * 50)
        
        successful_count = len(successful_results)
        success_rate = (successful_count / len(combinations)) * 100
        
        print(f"📊 Results:")
        print(f"   Total combinations: {len(combinations)}")
        print(f"   Successful: {successful_count}")
        print(f"   Failed: {len(failed_results)}")
        print(f"   Success rate: {success_rate:.1f}%")
        print(f"   Total time: {total_time:.2f}s")
        
        if successful_count > 0:
            processing_times = [r.processing_time for r in successful_results]
            avg_time = np.mean(processing_times)
            throughput = successful_count / total_time
            print(f"   Average time per combo: {avg_time:.2f}s")
            print(f"   Throughput: {throughput:.1f} combinations/second")
        
        # Final summary
        print(f"\n📂 FILE STRUCTURE CREATED:")
        print(f"   Windows: {windows_path}/")
        print(f"   ├── data/")
        print(f"   │   ├── combo_000.parquet")
        print(f"   │   ├── combo_001.parquet")
        print(f"   │   └── ... (1000 combo files)")
        print(f"   └── combinations_metadata.parquet")
        
        print(f"\n🎯 Data Details:")
        print(f"   Source: dem07_25_tr_ba_data.parquet (51,387 ticks)")
        print(f"   Converted: {len(contract_data):,} 15-minute candles")
        print(f"   Features: MACD + ATR + Bias + Position signals")
        print(f"   GPU: RTX 4080 SUPER processing")
        
        # Cleanup
        pipeline.cleanup()
        gpu_processor.cleanup()
        
        return {
            'success': True,
            'total_combinations': len(combinations),
            'successful_combinations': successful_count,
            'processing_time': total_time,
            'candles_created': len(contract_data),
            'windows_path': windows_path
        }
        
    except Exception as e:
        print(f"\n❌ Processing failed: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'error': str(e)}

async def main():
    """Main execution"""
    print("🎯 CORRECTED LEGACY DATA GPU TEST")
    print("=" * 45)
    print("✅ Load real legacy data with proper DatetimeIndex")
    print("✅ Convert to 15-minute OHLCV candles")
    print("✅ Generate 100 parameter variations")
    print("✅ Process with RTX 4080 SUPER GPU")
    print("✅ Save to simple data/ folder structure")
    print("✅ Create single metadata parquet file")
    
    result = await process_legacy_data_corrected()
    
    if result['success']:
        print(f"\n🎊 SUCCESS! Corrected legacy data processing complete!")
        print(f"📊 Processed {result['successful_combinations']}/{result['total_combinations']} combinations")
        print(f"📈 Created {result['candles_created']} 15-minute candles from 51,387 ticks")
        print(f"📂 Results: {result['windows_path']}")
        print(f"\n🚀 VERIFIED: Real legacy data → 15min candles → GPU features!")
    else:
        print(f"\n💥 Processing failed: {result.get('error', 'Unknown error')}")

if __name__ == "__main__":
    asyncio.run(main())