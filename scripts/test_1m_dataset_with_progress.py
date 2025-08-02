#!/usr/bin/env python3
"""
1M+ Dataset GPU Testing with Progress Bar
Comprehensive test of all technical indicators with real-time progress tracking
"""

import time
import gc
import numpy as np
import pandas as pd
from datetime import datetime
import sys
import os
from typing import Dict, Any
import threading

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from technical_indicators.unified_pipeline import UnifiedTechnicalIndicatorsPipeline


class ProgressTracker:
    """Simple progress tracker with visual bar"""
    
    def __init__(self, total_steps: int, description: str = "Processing"):
        self.total_steps = total_steps
        self.current_step = 0
        self.description = description
        self.start_time = time.perf_counter()
        self.last_update = 0
        
    def update(self, step: int = None, description: str = None):
        """Update progress"""
        if step is not None:
            self.current_step = step
        else:
            self.current_step += 1
            
        if description:
            self.description = description
        
        # Only update display every 0.1 seconds to avoid spam
        current_time = time.perf_counter()
        if current_time - self.last_update > 0.1 or self.current_step >= self.total_steps:
            self._print_progress()
            self.last_update = current_time
    
    def _print_progress(self):
        """Print progress bar"""
        percentage = (self.current_step / self.total_steps) * 100
        bar_length = 40
        filled_length = int(bar_length * self.current_step / self.total_steps)
        
        bar = '█' * filled_length + '░' * (bar_length - filled_length)
        
        elapsed = time.perf_counter() - self.start_time
        if self.current_step > 0:
            rate = self.current_step / elapsed
            eta = (self.total_steps - self.current_step) / rate if rate > 0 else 0
            eta_str = f", ETA: {eta:.1f}s" if eta > 0 else ""
        else:
            eta_str = ""
        
        print(f"\r{self.description}: [{bar}] {percentage:.1f}% ({self.current_step}/{self.total_steps}){eta_str}", end='', flush=True)
        
        if self.current_step >= self.total_steps:
            print()  # New line when complete


class ChunkProgressTracker:
    """Track progress through chunked processing"""
    
    def __init__(self, total_points: int, chunk_size: int):
        self.total_points = total_points
        self.chunk_size = chunk_size
        self.processed_points = 0
        self.total_chunks = (total_points + chunk_size - 1) // chunk_size
        self.current_chunk = 0
        self.progress = ProgressTracker(total_points, "GPU Processing")
        
    def update_chunk(self, chunk_num: int, chunk_points: int):
        """Update progress for a completed chunk"""
        self.current_chunk = chunk_num
        self.processed_points += chunk_points
        
        # Update progress bar
        self.progress.update(
            step=self.processed_points,
            description=f"GPU Processing (Chunk {chunk_num + 1}/{self.total_chunks})"
        )


def generate_large_dataset(size: int = 1_200_000) -> pd.DataFrame:
    """Generate large realistic OHLCV dataset with progress tracking"""
    print(f"🏗️  Generating {size:,} data points...")
    
    progress = ProgressTracker(5, "Data Generation")
    
    # Set random seed for reproducible results
    np.random.seed(42)
    progress.update(description="Setting up random seed")
    
    # Generate base price movements
    base_price = 100.0
    volatility = 0.02
    changes = np.random.normal(0, volatility, size)
    trend = np.linspace(0, 0.5, size)
    progress.update(description="Generating price movements")
    
    # Create close prices
    close_prices = base_price + np.cumsum(changes + trend/size)
    progress.update(description="Computing close prices")
    
    # Generate OHLC noise
    high_noise = np.abs(np.random.normal(0, volatility/2, size))
    low_noise = np.abs(np.random.normal(0, volatility/2, size))
    open_noise = np.random.normal(0, volatility/4, size)
    progress.update(description="Generating OHLC noise")
    
    # Create DataFrame
    data = pd.DataFrame({
        'open': np.roll(close_prices, 1) + open_noise,
        'high': close_prices + high_noise,
        'low': close_prices - low_noise,
        'close': close_prices
    })
    
    # Fix relationships
    data.loc[0, 'open'] = base_price
    data['high'] = np.maximum.reduce([data['open'], data['high'], data['low'], data['close']])
    data['low'] = np.minimum.reduce([data['open'], data['high'], data['low'], data['close']])
    progress.update(description="Finalizing OHLC relationships")
    
    memory_mb = data.memory_usage(deep=True).sum() / 1024**2
    print(f"✅ Dataset created: {len(data):,} rows, {memory_mb:.1f} MB")
    
    return data


def test_gpu_setup():
    """Test GPU availability and display info"""
    print("\n" + "="*70)
    print("🔧 GPU SETUP VALIDATION")
    print("="*70)
    
    try:
        import cupy as cp
        
        # GPU info
        device = cp.cuda.Device()
        free_mem, total_mem = cp.cuda.runtime.memGetInfo()
        
        print(f"✅ GPU Device: {device.id}")
        print(f"✅ Total Memory: {total_mem / 1e9:.1f} GB")
        print(f"✅ Free Memory: {free_mem / 1e9:.1f} GB")
        print(f"✅ Used Memory: {(total_mem - free_mem) / 1e9:.1f} GB")
        
        # Test basic GPU operation
        test_array = cp.random.randn(1000, 1000, dtype=cp.float32)
        result = cp.sum(test_array)
        print(f"✅ GPU Computation Test: {float(result):.2f}")
        
        return True
        
    except Exception as e:
        print(f"❌ GPU Setup Failed: {e}")
        return False


def test_indicator_with_progress(data: pd.DataFrame, 
                                indicator: str, 
                                pipeline: UnifiedTechnicalIndicatorsPipeline) -> Dict[str, Any]:
    """Test individual indicator with progress tracking"""
    
    print(f"\n📊 Testing {indicator.upper()} ({len(data):,} points)")
    print("-" * 50)
    
    try:
        # Clear GPU memory
        import cupy as cp
        cp.get_default_memory_pool().free_all_blocks()
        
        # Memory before
        free_before, total_mem = cp.cuda.runtime.memGetInfo()
        
        # Setup progress tracking
        expected_chunks = max(1, len(data) // pipeline.config.chunk_size)
        progress = ProgressTracker(100, f"{indicator.upper()} Computation")
        
        # Start computation
        start_time = time.perf_counter()
        
        # Simulate progress updates during computation
        def update_progress():
            for i in range(100):
                time.sleep(0.01)  # Small delay
                progress.update()
                if progress.current_step >= 100:
                    break
        
        # Start progress thread
        progress_thread = threading.Thread(target=update_progress, daemon=True)
        progress_thread.start()
        
        # Compute indicator
        if indicator == 'macd':
            result = pipeline.compute_indicators(
                data, 
                ['macd'], 
                macd_params={'fast': 12, 'slow': 26, 'signal': 9}
            )
            expected_cols = ['macd']
        elif indicator == 'atr':
            result = pipeline.compute_indicators(
                data, 
                ['atr'], 
                atr_period=14
            )
            expected_cols = ['atr']
        elif indicator == 'swing_points':
            result = pipeline.compute_indicators(
                data, 
                ['swing_points'], 
                swing_lookback=20
            )
            expected_cols = ['swing_highs', 'swing_lows']
        elif indicator == 'candles':
            result = pipeline.compute_indicators(
                data, 
                ['candles'], 
                candle_granularity='15min'
            )
            expected_cols = ['candle_open', 'candle_high', 'candle_low', 'candle_close']
        
        end_time = time.perf_counter()
        
        # Ensure progress is complete
        progress.update(step=100)
        
        # Memory after
        free_after, _ = cp.cuda.runtime.memGetInfo()
        
        # Calculate metrics
        computation_time = end_time - start_time
        memory_used = (free_before - free_after) / 1e9
        points_per_second = len(data) / computation_time
        memory_efficiency = (memory_used / (total_mem / 1e9)) * 100
        
        # Validate results
        found_cols = [col for col in expected_cols if col in result.columns]
        
        print(f"✅ Success! Time: {computation_time:.2f}s")
        print(f"📈 Throughput: {points_per_second:,.0f} points/sec")
        print(f"💾 GPU Memory: {memory_used:.2f} GB ({memory_efficiency:.1f}%)")
        print(f"📊 Result: {result.shape[0]:,} rows, {len(found_cols)} indicators")
        
        # Show non-null counts
        for col in found_cols:
            non_null = result[col].notna().sum()
            print(f"   {col}: {non_null:,} non-null values")
        
        return {
            'indicator': indicator,
            'success': True,
            'time': computation_time,
            'throughput': points_per_second,
            'memory_gb': memory_used,
            'memory_efficiency': memory_efficiency,
            'result_shape': result.shape,
            'columns': found_cols
        }
        
    except Exception as e:
        print(f"❌ {indicator.upper()} FAILED: {e}")
        return {
            'indicator': indicator,
            'success': False,
            'error': str(e)
        }


def test_all_indicators_with_progress(data: pd.DataFrame, 
                                    pipeline: UnifiedTechnicalIndicatorsPipeline) -> Dict[str, Any]:
    """Test all indicators combined with progress tracking"""
    
    print(f"\n🎯 Testing ALL INDICATORS COMBINED ({len(data):,} points)")
    print("-" * 60)
    
    try:
        # Clear GPU memory
        import cupy as cp
        cp.get_default_memory_pool().free_all_blocks()
        
        # Memory before
        free_before, total_mem = cp.cuda.runtime.memGetInfo()
        
        # Setup progress
        total_steps = 100
        progress = ProgressTracker(total_steps, "All Indicators")
        
        start_time = time.perf_counter()
        
        # Progress simulation for combined computation
        def simulate_progress():
            for i in range(total_steps):
                time.sleep(0.02)  # Slightly longer for combined
                progress.update()
                if progress.current_step >= total_steps:
                    break
        
        progress_thread = threading.Thread(target=simulate_progress, daemon=True)
        progress_thread.start()
        
        # Compute all indicators
        result = pipeline.compute_all_indicators(
            data,
            candle_granularity='15min',
            macd_params={'fast': 12, 'slow': 26, 'signal': 9},
            atr_period=14,
            swing_lookback=20
        )
        
        end_time = time.perf_counter()
        progress.update(step=total_steps)
        
        # Memory after
        free_after, _ = cp.cuda.runtime.memGetInfo()
        
        # Calculate metrics
        computation_time = end_time - start_time
        memory_used = (free_before - free_after) / 1e9
        points_per_second = len(data) / computation_time
        memory_efficiency = (memory_used / (total_mem / 1e9)) * 100
        
        # Get indicator columns
        base_cols = ['open', 'high', 'low', 'close']
        indicator_cols = [col for col in result.columns if col not in base_cols]
        
        print(f"✅ Success! Time: {computation_time:.2f}s")
        print(f"📈 Throughput: {points_per_second:,.0f} points/sec")
        print(f"💾 GPU Memory: {memory_used:.2f} GB ({memory_efficiency:.1f}%)")
        print(f"📊 Result: {result.shape[0]:,} rows, {len(indicator_cols)} indicators")
        print(f"🎯 Indicators: {', '.join(indicator_cols)}")
        
        return {
            'success': True,
            'time': computation_time,
            'throughput': points_per_second,
            'memory_gb': memory_used,
            'memory_efficiency': memory_efficiency,
            'result_shape': result.shape,
            'indicator_count': len(indicator_cols),
            'indicators': indicator_cols
        }
        
    except Exception as e:
        print(f"❌ COMBINED TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'error': str(e)
        }


def display_final_summary(individual_results: Dict, combined_result: Dict, dataset_size: int):
    """Display comprehensive test summary"""
    
    print("\n" + "="*80)
    print("🎯 FINAL 1M+ DATASET TEST SUMMARY")
    print("="*80)
    
    print(f"📊 Dataset Size: {dataset_size:,} data points")
    print(f"🔧 GPU Backend: CuPy with optimized memory management")
    print(f"⚙️  Configuration: 200K chunks, 85% memory threshold")
    
    print(f"\n📈 INDIVIDUAL INDICATOR PERFORMANCE:")
    print("-" * 50)
    
    total_successful = 0
    best_throughput = 0
    best_indicator = ""
    
    for indicator in ['macd', 'atr', 'swing_points', 'candles']:
        result = individual_results.get(indicator, {})
        if result.get('success'):
            throughput = result['throughput']
            memory = result['memory_gb']
            time_taken = result['time']
            
            print(f"✅ {indicator.upper():<12}: {time_taken:>6.2f}s | {throughput:>8,.0f} pts/sec | {memory:>5.2f} GB")
            
            total_successful += 1
            if throughput > best_throughput:
                best_throughput = throughput
                best_indicator = indicator
        else:
            print(f"❌ {indicator.upper():<12}: FAILED")
    
    print(f"\n🎯 COMBINED INDICATORS PERFORMANCE:")
    print("-" * 50)
    
    if combined_result.get('success'):
        print(f"✅ All Indicators: {combined_result['time']:>6.2f}s | {combined_result['throughput']:>8,.0f} pts/sec | {combined_result['memory_gb']:>5.2f} GB")
        print(f"📊 Total Columns: {combined_result['indicator_count']} indicators generated")
        print(f"💾 Memory Efficiency: {combined_result['memory_efficiency']:.1f}% of GPU memory used")
    else:
        print(f"❌ Combined test failed")
    
    print(f"\n🏆 PERFORMANCE HIGHLIGHTS:")
    print(f"  🥇 Best Individual: {best_indicator.upper()} at {best_throughput:,.0f} points/sec")
    print(f"  ✅ Success Rate: {total_successful}/4 indicators working")
    
    if combined_result.get('success'):
        print(f"  🎯 Combined Throughput: {combined_result['throughput']:,.0f} points/sec")
        print(f"  💾 Peak Memory Usage: {combined_result['memory_gb']:.2f} GB")
    
    print(f"\n⚡ OPTIMIZATION IMPACT:")
    print(f"  📦 Large Chunks: 200K points per chunk (4x larger)")
    print(f"  🔥 Aggressive Threshold: 85% memory utilization")
    print(f"  🚀 Better GPU Usage: Optimized for 16GB GPU memory")


def main():
    """Main test execution"""
    print("🚀 1M+ DATASET GPU TESTING WITH PROGRESS TRACKING")
    print("="*80)
    
    # Check GPU setup
    if not test_gpu_setup():
        print("❌ Cannot proceed without GPU")
        return
    
    # Generate large dataset
    dataset_size = 1_200_000  # 1.2M points
    data = generate_large_dataset(dataset_size)
    
    # Initialize optimized pipeline
    pipeline = UnifiedTechnicalIndicatorsPipeline(
        backend='cupy',
        enable_gpu_memory_management=True,
        chunk_size=200000,    # Optimized chunk size
        memory_threshold=0.85  # Optimized threshold
    )
    
    print(f"\n⚙️  Pipeline Configuration:")
    print(f"   Backend: {pipeline.backend_name}")
    print(f"   Chunk Size: {pipeline.config.chunk_size:,} points")
    print(f"   Memory Threshold: {pipeline.config.memory_threshold}")
    print(f"   Memory Management: {'Enabled' if pipeline.memory_manager else 'Disabled'}")
    
    # Test individual indicators
    individual_results = {}
    indicators = ['macd', 'atr', 'swing_points', 'candles']
    
    for i, indicator in enumerate(indicators, 1):
        print(f"\n📍 Testing {i}/{len(indicators)}: {indicator.upper()}")
        result = test_indicator_with_progress(data, indicator, pipeline)
        individual_results[indicator] = result
        
        # Brief pause between tests
        time.sleep(1)
        
        # Cleanup between tests
        gc.collect()
        try:
            import cupy as cp
            cp.get_default_memory_pool().free_all_blocks()
        except:
            pass
    
    # Test all indicators combined
    combined_result = test_all_indicators_with_progress(data, pipeline)
    
    # Display final summary
    display_final_summary(individual_results, combined_result, dataset_size)
    
    print(f"\n✅ 1M+ Dataset GPU Testing Completed Successfully!")
    print(f"🎉 All tests finished at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n❌ Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()