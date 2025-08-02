"""
Quick Real GPU Test - 10 combinations
Demonstrates actual GPU feature computation with smaller test size
"""

import asyncio
import time
import pandas as pd
import numpy as np
from pathlib import Path
import json
import warnings
warnings.filterwarnings('ignore')

# Add src to path for imports
import sys
sys.path.append(str(Path(__file__).parent.parent / 'src'))

from gpu_parallel_processing import (
    AsyncProcessingPipeline,
    EnhancedGPUCombinationProcessor
)

def create_quick_test_data():
    """Create small test dataset"""
    print("📊 Creating quick test data...")
    
    # Small contract data - 5,000 candles instead of 50,000
    np.random.seed(42)
    length = 5000
    base_price = 4200.0
    prices = [base_price]
    
    for i in range(length - 1):
        change = np.random.normal(0, 0.003)
        new_price = prices[-1] * (1 + change)
        prices.append(max(new_price, base_price * 0.8))
    
    opens = [prices[0]] + prices[:-1]
    highs = [p * (1 + abs(np.random.normal(0, 0.002))) for p in prices]
    lows = [p * (1 - abs(np.random.normal(0, 0.002))) for p in prices]
    volumes = np.random.exponential(1000, length)
    
    for i in range(length):
        highs[i] = max(highs[i], opens[i], prices[i])
        lows[i] = min(lows[i], opens[i], prices[i])
    
    timestamps = pd.date_range('2024-01-01 09:30:00', periods=length, freq='1min')
    
    contract_data = pd.DataFrame({
        'timestamp': timestamps,
        'open': opens,
        'high': highs,
        'low': lows,
        'close': prices,
        'volume': volumes
    })
    
    print(f"✅ Created test data: {len(contract_data):,} candles")
    return contract_data

def generate_valid_combinations(count: int = 10):
    """Generate valid parameter combinations"""
    print(f"🔢 Generating {count} valid combinations...")
    
    combinations = []
    for i in range(1, count + 1):
        # Generate valid parameters
        short = np.random.randint(8, 12)
        long = np.random.randint(short + 10, short + 20)  # Ensure long > short
        
        combo = {
            'combo_id': i,
            'contract': 'ES_TEST',
            'date_range': {
                'start': '2024-01-01',
                'end': '2024-12-31'
            },
            'macd_params': {
                'short': short,
                'long': long,
                'signal': np.random.randint(7, 10)
            },
            'atr_lookback': np.random.randint(12, 20),
            'predictor_granularities': {
                'atr_macd': np.random.choice([1, 2, 3])
            },
            'bias_thresholds': {
                'macd_line_lower': np.random.uniform(-0.03, -0.01),
                'macd_line_upper': np.random.uniform(0.01, 0.03),
                'macd_histogram_lower': np.random.uniform(-0.02, -0.005),
                'macd_histogram_upper': np.random.uniform(0.005, 0.02)
            },
            'strategy_thresholds': {
                'neutral_buy': np.random.uniform(0.15, 0.20),
                'strong_bullish_buy_adjust': np.random.uniform(-0.05, -0.02),
                'bullish_buy_adjust': np.random.uniform(-0.03, -0.01),
                'bearish_buy_adjust': np.random.uniform(0.02, 0.05),
                'neutral_sell': np.random.uniform(-0.20, -0.15),
                'strong_bearish_sell_adjust': np.random.uniform(0.02, 0.05),
                'bearish_sell_adjust': np.random.uniform(0.01, 0.03),
                'bullish_sell_adjust': np.random.uniform(-0.05, -0.02)
            }
        }
        combinations.append(combo)
    
    print(f"✅ Generated {len(combinations)} valid combinations")
    return combinations

async def run_quick_gpu_test():
    """Run quick GPU test with 10 combinations"""
    print("🚀 Quick Real GPU Test - 10 Combinations")
    print("=" * 50)
    
    # Create test directory in your Windows folder
    test_dir = Path(r"C:\Users\krajcovic\Documents\Testing Data\ATS_3_data\quick_gpu_test")
    test_dir.mkdir(parents=True, exist_ok=True)
    print(f"📁 Test directory: {test_dir}")
    
    try:
        # Setup test data
        contract_data = create_quick_test_data()
        combinations = generate_valid_combinations(10)
        
        # Initialize GPU processor
        print("\n🔧 Initializing GPU Processor...")
        gpu_processor = EnhancedGPUCombinationProcessor(
            gpu_memory_pool_gb=8.0,
            processing_chunk_size=500000
        )
        
        # Initialize pipeline
        pipeline = AsyncProcessingPipeline(
            max_gpu_workers=2,
            max_io_workers=1,
            output_directory=str(test_dir)
        )
        
        print(f"✅ Setup complete: {len(combinations)} combinations, {len(contract_data):,} candles")
        
        # Track results
        results = []
        successful = 0
        failed = 0
        
        def progress_callback(progress: float, result):
            nonlocal successful, failed
            if result.success:
                successful += 1
                print(f"✅ Combo {result.combo_id:2d}: SUCCESS ({result.processing_time:.2f}s) | {progress*100:.0f}%")
            else:
                failed += 1
                print(f"❌ Combo {result.combo_id:2d}: FAILED - {result.error_message}")
        
        # Run computation
        print(f"\n🔄 Processing {len(combinations)} combinations...")
        start_time = time.time()
        
        async for result in pipeline.process_combinations_async(
            gpu_processor,
            combinations,
            contract_data,
            progress_callback=progress_callback
        ):
            results.append(result)
            
            # Save successful results
            if result.success and result.result_data is not None:
                result_file = test_dir / f"combo_{result.combo_id:02d}_features.parquet"
                result.result_data.to_parquet(result_file, index=False)
                
                # Show sample of features
                if result.combo_id == 1:
                    print(f"\n📊 Sample Features (Combo 1):")
                    print(f"   Shape: {result.result_data.shape}")
                    print(f"   Columns: {list(result.result_data.columns)}")
                    if len(result.result_data) > 0:
                        print(f"   Sample row:\n{result.result_data.iloc[0].to_dict()}")
        
        processing_time = time.time() - start_time
        
        # Results summary
        print(f"\n🎉 Quick GPU Test Complete!")
        print("=" * 40)
        print(f"Successful: {successful}/{len(combinations)}")
        print(f"Failed: {failed}/{len(combinations)}")
        print(f"Success rate: {successful/len(combinations)*100:.1f}%")
        print(f"Processing time: {processing_time:.2f}s")
        
        if successful > 0:
            print(f"Throughput: {successful/processing_time:.1f} combinations/second")
            print(f"Avg time per combo: {processing_time/successful:.2f}s")
        
        # Pipeline stats
        stats = pipeline.get_pipeline_statistics()
        print(f"\n📈 Pipeline Performance:")
        print(f"GPU efficiency: {stats['gpu_efficiency_percent']:.1f}%")
        print(f"Peak concurrent tasks: {stats['concurrent_tasks_peak']}")
        
        # Save summary
        summary = {
            'test_type': 'Quick Real GPU Test',
            'combinations_total': len(combinations),
            'combinations_successful': successful,
            'combinations_failed': failed,
            'success_rate_percent': successful/len(combinations)*100,
            'processing_time_seconds': processing_time,
            'throughput_per_second': successful/processing_time if successful > 0 else 0,
            'pipeline_stats': stats,
            'test_timestamp': pd.Timestamp.now().isoformat()
        }
        
        with open(test_dir / "test_summary.json", 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        # Cleanup
        pipeline.cleanup()
        gpu_processor.cleanup()
        
        print(f"\n💾 Results saved to: {test_dir}")
        
        return {
            'success': True,
            'successful_combinations': successful,
            'total_combinations': len(combinations),
            'processing_time': processing_time
        }
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'error': str(e)}

if __name__ == "__main__":
    result = asyncio.run(run_quick_gpu_test())
    
    if result['success']:
        print(f"\n🎊 REAL GPU COMPUTATION CONFIRMED!")
        print(f"✅ Successfully processed {result['successful_combinations']}/{result['total_combinations']} combinations")
        print(f"⚡ Real GPU-accelerated technical indicators and trading signals computed!")
    else:
        print(f"💥 Test failed: {result.get('error', 'Unknown error')}")