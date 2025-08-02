#!/usr/bin/env python3
"""
Comprehensive GPU Testing for Large Datasets
Tests all technical indicators (candles, MACD, ATR, swing points) with GPU memory management
"""

import sys
import time
import traceback
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from src.feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline

class LargeDatasetGPUTester:
    """Comprehensive testing of GPU implementation with large datasets"""
    
    def __init__(self):
        self.results = []
        self.test_sizes = [10000, 50000, 100000, 250000, 500000]
        self.indicators = ['candles', 'macd', 'atr', 'swing_points']
        
    def generate_large_dataset(self, size: int) -> pd.DataFrame:
        """Generate realistic large dataset for testing"""
        print(f"📊 Generating dataset with {size:,} data points...")
        
        # Generate realistic price data
        np.random.seed(42)  # For reproducible results
        
        # Create date range
        start_date = datetime(2020, 1, 1)
        dates = [start_date + timedelta(minutes=i) for i in range(size)]
        
        # Generate realistic OHLCV data with trends and volatility
        base_price = 100.0
        prices = []
        volume_base = 1000000
        
        for i in range(size):
            # Add trend and noise
            trend = 0.001 * (i / 1000)
            noise = np.random.normal(0, 0.02)
            price_change = trend + noise
            
            if i == 0:
                open_price = base_price
            else:
                open_price = prices[-1]['close']
            
            # Generate OHLC with realistic relationships
            close_price = open_price * (1 + price_change)
            high_price = max(open_price, close_price) * (1 + abs(np.random.normal(0, 0.01)))
            low_price = min(open_price, close_price) * (1 - abs(np.random.normal(0, 0.01)))
            
            # Generate volume with some correlation to price movement
            volume_multiplier = 1 + abs(price_change) * 5
            volume = int(volume_base * volume_multiplier * (1 + np.random.normal(0, 0.3)))
            
            prices.append({
                'timestamp': dates[i],
                'open': round(open_price, 2),
                'high': round(high_price, 2),
                'low': round(low_price, 2),
                'close': round(close_price, 2),
                'volume': max(volume, 1000)
            })
        
        df = pd.DataFrame(prices)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        print(f"✅ Generated dataset: {len(df):,} rows, Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")
        return df
    
    def test_gpu_availability(self):
        """Test GPU availability and setup"""
        print("\n🔍 Testing GPU Availability...")
        
        try:
            import cupy as cp
            print(f"✅ CuPy available: {cp.__version__}")
            
            # Test GPU device
            device = cp.cuda.Device()
            meminfo = cp.cuda.runtime.memGetInfo()
            total_memory = meminfo[1] / (1024**3)  # GB
            free_memory = meminfo[0] / (1024**3)   # GB
            
            print(f"✅ GPU Device: {device}")
            print(f"✅ Total GPU Memory: {total_memory:.2f} GB")
            print(f"✅ Free GPU Memory: {free_memory:.2f} GB")
            
            return True
            
        except ImportError:
            print("❌ CuPy not available - GPU testing will be skipped")
            return False
        except Exception as e:
            print(f"❌ GPU setup error: {e}")
            return False
    
    def test_indicator_on_dataset(self, dataset: pd.DataFrame, indicator: str, backend: str):
        """Test a specific indicator on dataset"""
        print(f"\n🧪 Testing {indicator.upper()} with {backend.upper()} backend...")
        print(f"   Dataset size: {len(dataset):,} data points")
        
        try:
            # Initialize pipeline with GPU memory management
            pipeline = UnifiedTechnicalIndicatorsPipeline(
                backend=backend,
                enable_gpu_memory_management=True if backend == 'cupy' else False,
                chunk_size=50000,
                memory_threshold=0.7,
                optimize_memory=True
            )
            
            # Get memory stats before processing
            if backend == 'cupy':
                initial_stats = pipeline.get_gpu_memory_statistics()
                print(f"   Initial GPU Memory: {initial_stats.get('free_memory_gb', 0):.2f}GB free")
            
            # Time the computation
            start_time = time.time()
            
            # Compute indicator
            result = pipeline.compute_indicators(
                data=dataset,
                indicators=[indicator]
            )
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            # Validate result
            if result is None or len(result) == 0:
                raise ValueError("Empty result returned")
            
            if indicator in result.columns:
                valid_values = result[indicator].notna().sum()
                print(f"✅ {indicator.upper()} computed successfully")
                print(f"   Processing time: {processing_time:.2f} seconds")
                print(f"   Valid values: {valid_values:,}/{len(result):,}")
                
                # Get memory stats after processing
                if backend == 'cupy':
                    final_stats = pipeline.get_gpu_memory_statistics()
                    print(f"   Final GPU Memory: {final_stats.get('free_memory_gb', 0):.2f}GB free")
                    
                    # Check if chunking was used
                    chunking_info = final_stats.get('chunking_strategy', {})
                    if chunking_info.get('chunks_processed', 0) > 1:
                        print(f"   Chunked processing: {chunking_info['chunks_processed']} chunks")
                
                return {
                    'indicator': indicator,
                    'backend': backend,
                    'dataset_size': len(dataset),
                    'processing_time': processing_time,
                    'valid_values': valid_values,
                    'success': True,
                    'error': None
                }
            else:
                raise ValueError(f"Indicator {indicator} not found in result")
                
        except Exception as e:
            error_msg = f"Error processing {indicator}: {str(e)}"
            print(f"❌ {error_msg}")
            print(f"   Traceback: {traceback.format_exc()}")
            
            return {
                'indicator': indicator,
                'backend': backend,
                'dataset_size': len(dataset),
                'processing_time': 0,
                'valid_values': 0,
                'success': False,
                'error': error_msg
            }
    
    def run_comprehensive_test(self):
        """Run comprehensive testing on all indicators and dataset sizes"""
        print("🚀 Starting Comprehensive GPU Testing for Large Datasets")
        print("=" * 80)
        
        # Test GPU availability
        gpu_available = self.test_gpu_availability()
        
        # Test each dataset size
        for size in self.test_sizes:
            print(f"\n📏 Testing Dataset Size: {size:,} data points")
            print("-" * 60)
            
            # Generate dataset
            dataset = self.generate_large_dataset(size)
            
            # Test each indicator
            for indicator in self.indicators:
                # Test with GPU if available
                if gpu_available:
                    gpu_result = self.test_indicator_on_dataset(dataset, indicator, 'cupy')
                    self.results.append(gpu_result)
                
                # Test with CPU for comparison
                cpu_result = self.test_indicator_on_dataset(dataset, indicator, 'numpy')
                self.results.append(cpu_result)
                
                # Compare performance if both succeeded
                if gpu_available and gpu_result['success'] and cpu_result['success']:
                    speedup = cpu_result['processing_time'] / gpu_result['processing_time']
                    print(f"   🏃 Speedup: {speedup:.2f}x (GPU vs CPU)")
        
        # Generate comprehensive report
        self.generate_test_report()
    
    def generate_test_report(self):
        """Generate comprehensive test report"""
        print("\n📊 COMPREHENSIVE TEST REPORT")
        print("=" * 80)
        
        if not self.results:
            print("❌ No test results to report")
            return
        
        # Convert results to DataFrame for analysis
        df_results = pd.DataFrame(self.results)
        
        # Overall success rate
        total_tests = len(df_results)
        successful_tests = len(df_results[df_results['success'] == True])
        success_rate = (successful_tests / total_tests) * 100
        
        print(f"📈 Overall Success Rate: {success_rate:.1f}% ({successful_tests}/{total_tests} tests)")
        
        # Performance by backend
        print(f"\n🎯 Performance by Backend:")
        for backend in df_results['backend'].unique():
            backend_results = df_results[df_results['backend'] == backend]
            backend_success = len(backend_results[backend_results['success'] == True])
            backend_total = len(backend_results)
            backend_rate = (backend_success / backend_total) * 100
            avg_time = backend_results[backend_results['success'] == True]['processing_time'].mean()
            
            print(f"   {backend.upper()}: {backend_rate:.1f}% success, {avg_time:.2f}s avg time")
        
        # Performance by dataset size
        print(f"\n📏 Performance by Dataset Size:")
        for size in sorted(df_results['dataset_size'].unique()):
            size_results = df_results[df_results['dataset_size'] == size]
            size_success = len(size_results[size_results['success'] == True])
            size_total = len(size_results)
            size_rate = (size_success / size_total) * 100
            
            print(f"   {size:,} points: {size_rate:.1f}% success ({size_success}/{size_total})")
            
            # Show GPU vs CPU comparison for this size
            gpu_times = size_results[(size_results['backend'] == 'cupy') & (size_results['success'] == True)]['processing_time']
            cpu_times = size_results[(size_results['backend'] == 'numpy') & (size_results['success'] == True)]['processing_time']
            
            if len(gpu_times) > 0 and len(cpu_times) > 0:
                avg_speedup = cpu_times.mean() / gpu_times.mean()
                print(f"      Average GPU speedup: {avg_speedup:.2f}x")
        
        # Performance by indicator
        print(f"\n🧮 Performance by Indicator:")
        for indicator in sorted(df_results['indicator'].unique()):
            indicator_results = df_results[df_results['indicator'] == indicator]
            indicator_success = len(indicator_results[indicator_results['success'] == True])
            indicator_total = len(indicator_results)
            indicator_rate = (indicator_success / indicator_total) * 100
            
            print(f"   {indicator.upper()}: {indicator_rate:.1f}% success ({indicator_success}/{indicator_total})")
        
        # Failed tests summary
        failed_tests = df_results[df_results['success'] == False]
        if len(failed_tests) > 0:
            print(f"\n❌ Failed Tests Summary:")
            for _, test in failed_tests.iterrows():
                print(f"   {test['indicator'].upper()} ({test['backend'].upper()}, {test['dataset_size']:,} points): {test['error']}")
        
        # GPU Memory Management Summary
        gpu_results = df_results[df_results['backend'] == 'cupy']
        if len(gpu_results) > 0:
            print(f"\n🧠 GPU Memory Management:")
            largest_successful = gpu_results[gpu_results['success'] == True]['dataset_size'].max()
            print(f"   Largest dataset processed: {largest_successful:,} data points")
            print(f"   GPU memory management: {'✅ Active' if largest_successful > 75000 else '⚠️ Not triggered'}")
        
        # Save detailed results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_file = f"gpu_test_results_{timestamp}.csv"
        df_results.to_csv(results_file, index=False)
        print(f"\n💾 Detailed results saved to: {results_file}")
        
        print(f"\n🎉 Testing Complete! GPU implementation {'✅ PASSED' if success_rate >= 90 else '⚠️ NEEDS ATTENTION'}")

def main():
    """Main execution function"""
    tester = LargeDatasetGPUTester()
    tester.run_comprehensive_test()

if __name__ == "__main__":
    main()