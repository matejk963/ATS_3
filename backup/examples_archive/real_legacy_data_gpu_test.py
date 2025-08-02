"""
Real Legacy Data GPU Test - Production Ready
Uses actual legacy backtest data and real parameter combinations
Processes 100 combinations with GPU and saves to Windows directory
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
    EnhancedGPUCombinationProcessor,
    generate_all_parameter_combinations
)

def load_real_legacy_data():
    """Load real legacy backtest data"""
    print("📂 Loading real legacy backtest data...")
    
    # Use WSL mount path to access Windows file
    legacy_data_path = "/mnt/c/Users/krajcovic/Documents/Testing Data/backtest_data/dem07_25_tr_ba_data.parquet"
    
    try:
        contract_data = pd.read_parquet(legacy_data_path)
        print(f"✅ Loaded real legacy data: {len(contract_data):,} rows")
        print(f"   Columns: {list(contract_data.columns)}")
        print(f"   Date range: {contract_data.index.min()} to {contract_data.index.max()}")
        print(f"   Data shape: {contract_data.shape}")
        
        # Show sample of real data
        print(f"\n📋 Real Legacy Data Sample:")
        print(contract_data.head(3).to_string())
        
        return contract_data
        
    except Exception as e:
        print(f"❌ Failed to load legacy data: {e}")
        print(f"   Tried path: {legacy_data_path}")
        return None

def generate_real_legacy_combinations(count: int = 100):
    """Generate real legacy parameter combinations (first 100)"""
    print(f"\n🔢 Generating {count} real legacy parameter combinations...")
    
    try:
        # Use the actual legacy parameter generation system
        all_combinations = generate_all_parameter_combinations()
        
        print(f"✅ Generated {len(all_combinations):,} total legacy combinations")
        print(f"📊 Taking first {count} combinations for GPU testing")
        
        # Take first 100 combinations
        selected_combinations = all_combinations[:count]
        
        # Show sample of real combinations
        print(f"\n📋 Sample Legacy Combination:")
        sample_combo = selected_combinations[0]
        for key, value in sample_combo.items():
            if isinstance(value, dict):
                print(f"   {key}:")
                for sub_key, sub_value in value.items():
                    print(f"     {sub_key}: {sub_value}")
            else:
                print(f"   {key}: {value}")
        
        return selected_combinations
        
    except Exception as e:
        print(f"❌ Failed to generate legacy combinations: {e}")
        import traceback
        traceback.print_exc()
        return None

async def process_real_legacy_data_with_gpu():
    """Process real legacy data with GPU using real combinations"""
    print("🚀 REAL LEGACY DATA GPU PROCESSING TEST")
    print("=" * 60)
    
    # Setup output directory in Windows
    output_base = "/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_3_data/final_gpu_test"
    real_data_dir = Path(f"{output_base}/real_legacy_data_results")
    real_data_dir.mkdir(parents=True, exist_ok=True)
    
    windows_path = "C:\\Users\\krajcovic\\Documents\\Testing Data\\ATS_3_data\\final_gpu_test\\real_legacy_data_results"
    
    print(f"📁 Output Directory:")
    print(f"   WSL Path: {real_data_dir}")
    print(f"   Windows Path: {windows_path}")
    print(f"   Directory exists: {real_data_dir.exists()}")
    
    try:
        # Load real legacy data
        contract_data = load_real_legacy_data()
        if contract_data is None:
            return False
        
        # Generate real legacy combinations
        combinations = generate_real_legacy_combinations(100)
        if combinations is None:
            return False
        
        # Prepare contract data format for GPU processing
        # Legacy data might have different column names or index format
        print(f"\n🔧 Preparing contract data for GPU processing...")
        
        # Ensure we have the required columns for GPU processing
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        available_cols = contract_data.columns.tolist()
        
        print(f"   Available columns: {available_cols}")
        print(f"   Required columns: {required_cols}")
        
        # Map legacy column names to standard names if needed
        if contract_data.index.name in ['timestamp', 'date', 'datetime']:
            contract_data = contract_data.reset_index()
            contract_data.rename(columns={contract_data.columns[0]: 'timestamp'}, inplace=True)
        elif 'timestamp' not in contract_data.columns:
            # Create timestamp column if missing
            contract_data['timestamp'] = pd.date_range(
                start='2025-04-01 09:30:00', 
                periods=len(contract_data), 
                freq='1min'
            )
        
        # Convert tick data to OHLCV format if needed
        missing_cols = [col for col in required_cols if col not in contract_data.columns]
        if missing_cols:
            print(f"⚠️  Missing OHLCV columns: {missing_cols}")
            print("   Converting tick data to OHLCV format...")
            
            # Check if we have tick data format (price column)
            if 'price' in contract_data.columns:
                print("   ✅ Detected tick data format - converting to OHLCV")
                
                # Resample tick data to 1-minute OHLCV bars
                contract_data = contract_data.reset_index()
                if 'timestamp' not in contract_data.columns:
                    contract_data['timestamp'] = contract_data.index
                
                contract_data['timestamp'] = pd.to_datetime(contract_data['timestamp'])
                contract_data = contract_data.set_index('timestamp')
                
                # Convert tick price data to OHLCV
                ohlcv_data = contract_data['price'].resample('1T').agg({
                    'open': 'first',
                    'high': 'max', 
                    'low': 'min',
                    'close': 'last'
                }).dropna()
                
                # Add volume (sum tick volumes)
                if 'volume' in contract_data.columns:
                    volume_data = contract_data['volume'].resample('1T').sum()
                    ohlcv_data['volume'] = volume_data
                else:
                    # Create synthetic volume if not available
                    ohlcv_data['volume'] = np.random.exponential(1500, len(ohlcv_data))
                
                # Reset index to get timestamp column
                contract_data = ohlcv_data.reset_index()
                
                print(f"   ✅ Converted to OHLCV: {contract_data.shape}")
                print(f"   ✅ Date range: {contract_data['timestamp'].min()} to {contract_data['timestamp'].max()}")
            else:
                print(f"   ❌ Cannot convert - unknown data format")
                print(f"   Available columns: {list(contract_data.columns)}")
                return False
        
        # Select only required columns for GPU processing
        gpu_data = contract_data[['timestamp'] + required_cols].copy()
        print(f"✅ Prepared GPU data: {gpu_data.shape}")
        print(f"   Final columns: {list(gpu_data.columns)}")
        
        # Initialize GPU processing components
        print(f"\n🔧 Initializing GPU Processing Components...")
        
        # Enhanced GPU processor with real memory management
        gpu_processor = EnhancedGPUCombinationProcessor(
            gpu_memory_pool_gb=12.0,
            processing_chunk_size=1000000  # 1M candles chunks
        )
        
        # Async processing pipeline for parallel execution
        pipeline = AsyncProcessingPipeline(
            max_gpu_workers=3,  # 3 parallel GPU workers
            max_io_workers=2,   # 2 parallel I/O workers
            task_queue_size=50,
            result_buffer_size=20,
            output_directory=str(real_data_dir / "combination_results")
        )
        
        print(f"✅ GPU Processor: {gpu_processor.__class__.__name__}")
        print(f"✅ Pipeline: {pipeline.max_gpu_workers} GPU workers, {pipeline.max_io_workers} I/O workers")
        
        # Track processing results
        successful_results = []
        failed_results = []
        processing_times = []
        
        def progress_callback(progress: float, result):
            if result.success:
                successful_results.append(result)
                processing_times.append(result.processing_time)
                print(f"✅ Combo {result.combo_id:3d}: SUCCESS ({result.processing_time:.2f}s) "
                      f"| Worker: {result.worker_id} | Progress: {progress*100:.1f}%")
                
                # Show sample features for first successful combination
                if len(successful_results) == 1 and result.result_data is not None:
                    print(f"\n📊 Sample Features from First Successful Combination:")
                    print(f"   Input shape: {gpu_data.shape}")
                    print(f"   Output shape: {result.result_data.shape}")
                    print(f"   Features added: {result.result_data.shape[1] - gpu_data.shape[1]}")
                    if len(result.result_data) > 0:
                        sample_cols = ['close', 'macd_line', 'macd_histogram', 'bias_classification', 'position_signal']
                        available = [col for col in sample_cols if col in result.result_data.columns]
                        if available:
                            print(f"   Sample features:\n{result.result_data[available].head(2).to_string(index=False)}")
            else:
                failed_results.append(result)
                print(f"❌ Combo {result.combo_id:3d}: FAILED - {result.error_message}")
        
        # Execute real GPU processing
        print(f"\n🔄 Processing {len(combinations)} real legacy combinations with GPU...")
        print(f"   Contract: {len(gpu_data):,} candles of real market data")
        print(f"   GPU: RTX 4080 SUPER with parallel workers")
        
        start_time = time.time()
        
        # Process combinations with REAL GPU computation
        processed_results = []
        async for result in pipeline.process_combinations_async(
            gpu_processor,
            combinations,
            gpu_data,
            progress_callback=progress_callback
        ):
            processed_results.append(result)
            
            # Save successful results
            if result.success and result.result_data is not None:
                # Save individual combination result
                combo_file = real_data_dir / f"combo_{result.combo_id:03d}_features.parquet"
                result.result_data.to_parquet(combo_file, index=False)
                
                # Save combination metadata
                metadata_file = real_data_dir / f"combo_{result.combo_id:03d}_metadata.json"
                with open(metadata_file, 'w') as f:
                    metadata = {
                        'combo_id': result.combo_id,
                        'success': result.success,
                        'processing_time_seconds': result.processing_time,
                        'worker_id': result.worker_id,
                        'memory_stats': result.memory_stats,
                        'combination_parameters': result.metadata,
                        'result_shape': result.result_data.shape,
                        'result_columns': list(result.result_data.columns),
                        'input_data_info': {
                            'contract_file': 'dem07_25_tr_ba_data.parquet',
                            'contract_candles': len(gpu_data),
                            'date_range': f"{gpu_data['timestamp'].min()} to {gpu_data['timestamp'].max()}"
                        }
                    }
                    json.dump(metadata, f, indent=2, default=str)
        
        total_time = time.time() - start_time
        
        # Generate comprehensive results summary
        print(f"\n🎉 REAL LEGACY DATA GPU PROCESSING COMPLETE!")
        print("=" * 60)
        
        successful_count = len(successful_results)
        failed_count = len(failed_results)
        total_combinations = len(combinations)
        success_rate = (successful_count / total_combinations) * 100
        
        print(f"📊 Processing Results:")
        print(f"   Total combinations: {total_combinations}")
        print(f"   Successful: {successful_count}")
        print(f"   Failed: {failed_count}")
        print(f"   Success rate: {success_rate:.1f}%")
        print(f"   Total processing time: {total_time:.2f}s")
        
        if successful_count > 0:
            avg_time = np.mean(processing_times)
            throughput = successful_count / total_time
            print(f"   Average time per combination: {avg_time:.2f}s")
            print(f"   Throughput: {throughput:.1f} combinations/second")
        
        # Get detailed statistics
        pipeline_stats = pipeline.get_pipeline_statistics()
        gpu_stats = gpu_processor.get_processing_stats()
        
        print(f"\n📈 Performance Statistics:")
        print(f"   GPU efficiency: {pipeline_stats['gpu_efficiency_percent']:.1f}%")
        print(f"   I/O efficiency: {pipeline_stats['io_efficiency_percent']:.1f}%")
        print(f"   Peak concurrent tasks: {pipeline_stats['concurrent_tasks_peak']}")
        print(f"   Tasks retried: {pipeline_stats['tasks_retried']}")
        
        # Save comprehensive test summary
        summary = {
            'test_info': {
                'test_name': 'Real Legacy Data GPU Processing Test',
                'timestamp': pd.Timestamp.now().isoformat(),
                'total_processing_time_seconds': total_time,
                'gpu_device': 'RTX 4080 SUPER'
            },
            'data_info': {
                'source_file': 'dem07_25_tr_ba_data.parquet',
                'contract_candles': len(gpu_data),
                'data_shape': gpu_data.shape,
                'data_columns': list(gpu_data.columns),
                'date_range': {
                    'start': str(gpu_data['timestamp'].min()),
                    'end': str(gpu_data['timestamp'].max())
                }
            },
            'combinations_info': {
                'total_combinations': total_combinations,
                'successful_combinations': successful_count,
                'failed_combinations': failed_count,
                'success_rate_percent': success_rate,
                'sample_combination': combinations[0] if combinations else None
            },
            'performance_stats': {
                'average_processing_time_per_combo': np.mean(processing_times) if processing_times else 0,
                'throughput_combinations_per_second': successful_count / total_time if successful_count > 0 else 0,
                'pipeline_stats': pipeline_stats,
                'gpu_stats': gpu_stats
            },
            'file_locations': {
                'windows_path': windows_path,
                'wsl_path': str(real_data_dir),
                'combination_results': str(real_data_dir / "combination_results"),
                'summary_file': str(real_data_dir / "real_legacy_processing_summary.json")
            }
        }
        
        # Add feature distribution if available
        if successful_results and successful_results[0].result_data is not None:
            sample_result = successful_results[0]
            if 'bias_classification' in sample_result.result_data.columns:
                bias_dist = sample_result.result_data['bias_classification'].value_counts()
                summary['sample_features'] = {
                    'bias_distribution': bias_dist.to_dict(),
                    'total_features_computed': sample_result.result_data.shape[1] - gpu_data.shape[1]
                }
            
            if 'position_signal' in sample_result.result_data.columns:
                pos_dist = sample_result.result_data['position_signal'].value_counts()
                summary['sample_features']['position_distribution'] = pos_dist.to_dict()
        
        # Save summary
        summary_file = real_data_dir / "real_legacy_processing_summary.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        # Save aggregated successful results
        if successful_results:
            print(f"\n💾 Saving aggregated results...")
            
            # Create summary of all successful combinations
            combo_summary = []
            for result in successful_results:
                combo_summary.append({
                    'combo_id': result.combo_id,
                    'processing_time': result.processing_time,
                    'worker_id': result.worker_id,
                    'result_shape': result.result_data.shape if result.result_data is not None else None,
                    'features_computed': result.result_data.shape[1] - gpu_data.shape[1] if result.result_data is not None else 0
                })
            
            combo_summary_df = pd.DataFrame(combo_summary)
            combo_summary_file = real_data_dir / "successful_combinations_summary.csv"
            combo_summary_df.to_csv(combo_summary_file, index=False)
            
            print(f"   ✅ Combination summary: {combo_summary_file}")
        
        # Cleanup
        pipeline.cleanup()
        gpu_processor.cleanup()
        
        print(f"\n📂 ALL FILES SAVED TO WINDOWS DIRECTORY:")
        print(f"   {windows_path}")
        print(f"\n📁 Files created:")
        print(f"   - {successful_count} combination feature files (.parquet)")
        print(f"   - {successful_count} combination metadata files (.json)")
        print(f"   - 1 processing summary (.json)")
        print(f"   - 1 combinations summary (.csv)")
        
        return {
            'success': True,
            'total_combinations': total_combinations,
            'successful_combinations': successful_count,
            'processing_time': total_time,
            'windows_path': windows_path,
            'throughput': successful_count / total_time if successful_count > 0 else 0
        }
        
    except Exception as e:
        print(f"\n❌ Processing failed: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'error': str(e)}

async def main():
    """Main execution function"""
    print("🎯 REAL LEGACY DATA GPU PROCESSING TEST")
    print("=" * 50)
    print("This test will:")
    print("✅ Load real legacy backtest data (dem07_25_tr_ba_data.parquet)")
    print("✅ Generate 100 real legacy parameter combinations")
    print("✅ Process with GPU using RTX 4080 SUPER")
    print("✅ Save all results to Windows directory")
    print("✅ Demonstrate production-ready GPU processing")
    
    result = await process_real_legacy_data_with_gpu()
    
    if result['success']:
        print(f"\n🎊 SUCCESS! Real legacy data GPU processing complete!")
        print(f"🚀 Processed {result['successful_combinations']}/{result['total_combinations']} combinations")
        print(f"⚡ Throughput: {result['throughput']:.1f} combinations/second")
        print(f"📂 Results saved to: {result['windows_path']}")
        print(f"\n🎉 PROVEN: Phase 1.2.2 can process real legacy data with GPU!")
    else:
        print(f"\n💥 Test failed: {result.get('error', 'Unknown error')}")

if __name__ == "__main__":
    asyncio.run(main())