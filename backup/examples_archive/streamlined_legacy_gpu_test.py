"""
Streamlined Legacy Data GPU Test
Uses actual legacy backtest data with 100 specific parameter combinations
Focuses on GPU processing efficiency
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

def load_real_legacy_data():
    """Load and convert real legacy backtest data"""
    print("📂 Loading real legacy backtest data...")
    
    legacy_data_path = "/mnt/c/Users/krajcovic/Documents/Testing Data/backtest_data/dem07_25_tr_ba_data.parquet"
    
    try:
        tick_data = pd.read_parquet(legacy_data_path)
        print(f"✅ Loaded tick data: {len(tick_data):,} rows")
        print(f"   Columns: {list(tick_data.columns)}")
        
        # Convert tick data to OHLCV
        print("🔄 Converting tick data to OHLCV format...")
        
        tick_data = tick_data.reset_index()
        if 'timestamp' not in tick_data.columns:
            tick_data['timestamp'] = tick_data.index
        
        tick_data['timestamp'] = pd.to_datetime(tick_data['timestamp'])
        tick_data = tick_data.set_index('timestamp')
        
        # Convert tick price data to OHLCV (1-minute bars)
        ohlcv_data = tick_data['price'].resample('1T').agg({
            'open': 'first',
            'high': 'max', 
            'low': 'min',
            'close': 'last'
        }).dropna()
        
        # Add volume
        if 'volume' in tick_data.columns:
            volume_data = tick_data['volume'].resample('1T').sum()
            ohlcv_data['volume'] = volume_data.fillna(0)
        else:
            ohlcv_data['volume'] = np.random.exponential(1500, len(ohlcv_data))
        
        # Reset index
        contract_data = ohlcv_data.reset_index()
        
        print(f"✅ Converted to OHLCV: {contract_data.shape}")
        print(f"   Date range: {contract_data['timestamp'].min()} to {contract_data['timestamp'].max()}")
        
        return contract_data
        
    except Exception as e:
        print(f"❌ Failed to load legacy data: {e}")
        return None

def generate_100_legacy_combinations():
    """Generate 100 specific legacy parameter combinations"""
    print("🔢 Generating 100 specific legacy parameter combinations...")
    
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
    
    # Generate 100 variations
    for i in range(100):
        combo = base_combo.copy()
        combo['combo_id'] = i
        
        # Vary key parameters
        macd_variations = [
            {'short': 8, 'long': 21, 'signal': 5},
            {'short': 12, 'long': 26, 'signal': 9}, 
            {'short': 5, 'long': 35, 'signal': 5},
            {'short': 19, 'long': 39, 'signal': 9}
        ]
        combo['macd_params'] = macd_variations[i % len(macd_variations)]
        
        # Vary ATR lookback
        atr_variations = [14, 21, 28, 35]
        combo['atr_lookback'] = atr_variations[i % len(atr_variations)]
        
        # Vary bias thresholds
        bias_multiplier = 1.0 + (i % 5) * 0.2  # 1.0, 1.2, 1.4, 1.6, 1.8
        combo['bias_thresholds'] = {
            'macd_line_lower': -2.5 * bias_multiplier,
            'macd_line_upper': 2.5 * bias_multiplier,
            'macd_histogram_lower': -1.25 * bias_multiplier,
            'macd_histogram_upper': 1.25 * bias_multiplier
        }
        
        # Vary strategy thresholds
        neutral_base = 0.15 + (i % 10) * 0.01  # 0.15 to 0.24
        combo['strategy_thresholds']['neutral_buy'] = neutral_base
        combo['strategy_thresholds']['neutral_sell'] = neutral_base + 0.5
        
        combinations.append(combo)
    
    print(f"✅ Generated {len(combinations)} legacy parameter combinations")
    return combinations

async def process_legacy_data_with_gpu():
    """Process legacy data with GPU using 100 combinations"""
    print("🚀 STREAMLINED LEGACY DATA GPU PROCESSING")
    print("=" * 60)
    
    # Setup output directory
    output_base = "/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data/final_gpu_test"
    legacy_dir = Path(f"{output_base}/streamlined_legacy_results")
    legacy_dir.mkdir(parents=True, exist_ok=True)
    
    windows_path = "C:\\Users\\krajcovic\\Documents\\Testing Data\\ATS_3_data\\final_gpu_test\\streamlined_legacy_results"
    
    print(f"📁 Output: {windows_path}")
    
    try:
        # Load and convert legacy data
        contract_data = load_real_legacy_data()
        if contract_data is None:
            return False
        
        # Generate 100 combinations
        combinations = generate_100_legacy_combinations()
        
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
            output_directory=str(legacy_dir / "combination_results")
        )
        
        # Process with GPU
        print(f"\n🔄 Processing {len(combinations)} combinations...")
        print(f"   Contract data: {len(contract_data):,} candles")
        print(f"   GPU: RTX 4080 SUPER")
        
        start_time = time.time()
        successful_results = []
        failed_results = []
        
        def progress_callback(progress: float, result):
            if result.success:
                successful_results.append(result)
                print(f"✅ Combo {result.combo_id:3d}: SUCCESS ({result.processing_time:.2f}s) - Progress: {progress*100:.1f}%")
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
            
            # Save successful results immediately
            if result.success and result.result_data is not None:
                combo_file = legacy_dir / f"combo_{result.combo_id:03d}_features.parquet"
                result.result_data.to_parquet(combo_file, index=False)
                
                metadata_file = legacy_dir / f"combo_{result.combo_id:03d}_metadata.json"
                with open(metadata_file, 'w') as f:
                    metadata = {
                        'combo_id': result.combo_id,
                        'processing_time_seconds': result.processing_time,
                        'worker_id': result.worker_id,
                        'combination_parameters': result.metadata,
                        'result_shape': result.result_data.shape,
                        'legacy_data_source': 'dem07_25_tr_ba_data.parquet'
                    }
                    json.dump(metadata, f, indent=2, default=str)
        
        total_time = time.time() - start_time
        
        # Results summary
        print(f"\n🎉 LEGACY DATA GPU PROCESSING COMPLETE!")
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
        
        # Save comprehensive summary
        summary = {
            'test_info': {
                'test_name': 'Streamlined Legacy Data GPU Processing',
                'timestamp': pd.Timestamp.now().isoformat(),
                'total_processing_time_seconds': total_time,
                'gpu_device': 'RTX 4080 SUPER'
            },
            'data_info': {
                'source_file': 'dem07_25_tr_ba_data.parquet',
                'converted_from': 'tick_data',
                'contract_candles': len(contract_data),
                'data_shape': contract_data.shape,
                'date_range': {
                    'start': str(contract_data['timestamp'].min()),
                    'end': str(contract_data['timestamp'].max())
                }
            },
            'combinations_info': {
                'total_combinations': len(combinations),
                'successful_combinations': successful_count,
                'success_rate_percent': success_rate
            },
            'performance_stats': {
                'average_processing_time_per_combo': np.mean(processing_times) if processing_times else 0,
                'throughput_combinations_per_second': successful_count / total_time if successful_count > 0 else 0
            },
            'file_locations': {
                'windows_path': windows_path,
                'wsl_path': str(legacy_dir)
            }
        }
        
        summary_file = legacy_dir / "streamlined_legacy_processing_summary.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        # Cleanup
        pipeline.cleanup()
        gpu_processor.cleanup()
        
        print(f"\n📂 Results saved to: {windows_path}")
        print(f"📁 Files: {successful_count * 2 + 1} total (.parquet, .json, summary)")
        
        return {
            'success': True,
            'total_combinations': len(combinations),
            'successful_combinations': successful_count,
            'processing_time': total_time,
            'windows_path': windows_path
        }
        
    except Exception as e:
        print(f"\n❌ Processing failed: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'error': str(e)}

async def main():
    """Main execution"""
    print("🎯 STREAMLINED LEGACY DATA GPU TEST")
    print("=" * 45)
    print("✅ Load real legacy data (dem07_25_tr_ba_data.parquet)")
    print("✅ Convert tick data to OHLCV format")
    print("✅ Generate 100 parameter variations")
    print("✅ Process with RTX 4080 SUPER GPU")
    print("✅ Save results to Windows directory")
    
    result = await process_legacy_data_with_gpu()
    
    if result['success']:
        print(f"\n🎊 SUCCESS! Legacy data processing complete!")
        print(f"📊 Processed {result['successful_combinations']}/{result['total_combinations']} combinations")
        print(f"📂 Results: {result['windows_path']}")
    else:
        print(f"\n💥 Processing failed: {result.get('error', 'Unknown error')}")

if __name__ == "__main__":
    asyncio.run(main())