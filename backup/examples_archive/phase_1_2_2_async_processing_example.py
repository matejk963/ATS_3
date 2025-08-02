"""
Phase 1.2.2 Async Processing Pipeline Example

Demonstrates the asynchronous processing pipeline with parallel GPU workers
and concurrent I/O operations for improved throughput.
"""

import asyncio
import time
import pandas as pd
import numpy as np
from pathlib import Path

# Add src to path for imports
import sys
sys.path.append(str(Path(__file__).parent.parent / 'src'))

from gpu_parallel_processing.async_processing_pipeline import AsyncProcessingPipeline
from gpu_parallel_processing.async_orchestrator import AsyncGPUOrchestrator

class MockGPUProcessor:
    """Mock GPU processor for demonstration purposes"""
    
    def __init__(self, processing_time: float = 0.1):
        self.processing_time = processing_time
        self.processing_stats = {
            'total_processing_time': 0.0,
            'combinations_processed': 0
        }
    
    def process_contract_combinations_sustained(self, contract_data, combinations, enable_monitoring=True):
        """Mock processing method that simulates GPU computation"""
        time.sleep(self.processing_time)  # Simulate processing time
        
        results = []
        for combo in combinations:
            # Generate mock trading signals
            signal_data = pd.DataFrame({
                'timestamp': pd.date_range('2023-01-01', periods=100, freq='1min'),
                'signal': np.random.choice([-1, 0, 1], size=100, p=[0.3, 0.4, 0.3]),
                'confidence': np.random.uniform(0.5, 1.0, 100),
                'price': contract_data['close'].iloc[:100] if len(contract_data) >= 100 else contract_data['close'],
                'combo_id': combo['combo_id']
            })
            
            results.append({
                'result_data': signal_data,
                'metadata': {
                    'combo_id': combo['combo_id'],
                    'parameters': combo,
                    'processing_time': self.processing_time,
                    'memory_stats': {
                        'gpu_memory_used': np.random.randint(1000, 5000),
                        'peak_memory': np.random.randint(5000, 10000)
                    }
                }
            })
        
        self.processing_stats['total_processing_time'] += self.processing_time * len(combinations)
        self.processing_stats['combinations_processed'] += len(combinations)
        
        return results
    
    def get_processing_stats(self):
        """Return processing statistics"""
        return self.processing_stats.copy()
    
    def cleanup(self):
        """Cleanup mock processor"""
        print("🧹 Mock GPU processor cleaned up")

class MockContractDataManager:
    """Mock contract data manager for demonstration"""
    
    def __init__(self):
        self.cache_stats = {'cache_hits': 0, 'cache_misses': 0}
    
    def load_contract_data(self, contract_code: str) -> pd.DataFrame:
        """Load mock contract data"""
        print(f"📂 Loading mock contract data for {contract_code}")
        
        # Generate realistic OHLCV data
        data_length = np.random.randint(50000, 200000)  # 50K-200K candles
        
        base_price = 100.0
        prices = [base_price]
        
        for _ in range(data_length - 1):
            change = np.random.normal(0, 0.02)  # 2% volatility
            new_price = prices[-1] * (1 + change)
            prices.append(max(new_price, 0.01))  # Prevent negative prices
        
        highs = [p * (1 + abs(np.random.normal(0, 0.01))) for p in prices]
        lows = [p * (1 - abs(np.random.normal(0, 0.01))) for p in prices]
        volumes = np.random.exponential(1000, data_length)
        
        contract_data = pd.DataFrame({
            'timestamp': pd.date_range('2020-01-01', periods=data_length, freq='1min'),
            'open': prices,
            'high': highs,
            'low': lows,
            'close': prices,
            'volume': volumes
        })
        
        self.cache_stats['cache_misses'] += 1
        return contract_data
    
    def get_cache_stats(self):
        """Return cache statistics"""
        return self.cache_stats.copy()

async def demonstrate_async_pipeline():
    """Demonstrate the async processing pipeline capabilities"""
    print("🚀 Phase 1.2.2 Async Processing Pipeline Demonstration")
    print("=" * 60)
    
    # Create sample contract data
    print("\n📊 Generating sample contract data...")
    contract_data = pd.DataFrame({
        'open': np.random.random(100000) * 100,
        'high': np.random.random(100000) * 100,
        'low': np.random.random(100000) * 100,
        'close': np.random.random(100000) * 100,
        'volume': np.random.random(100000) * 1000
    })
    print(f"✅ Contract data created: {len(contract_data):,} candles")
    
    # Create parameter combinations
    print("\n🔢 Creating parameter combinations...")
    combinations = []
    for i in range(1, 26):  # 25 combinations
        combinations.append({
            'combo_id': i,
            'fast_period': np.random.randint(5, 20),
            'slow_period': np.random.randint(20, 50),
            'signal_threshold': np.random.uniform(0.1, 0.5),
            'stop_loss': np.random.uniform(0.02, 0.10)
        })
    print(f"✅ Created {len(combinations)} parameter combinations")
    
    # Initialize async processing pipeline
    print("\n🔧 Initializing Async Processing Pipeline...")
    output_dir = "async_pipeline_demo_output"
    
    pipeline = AsyncProcessingPipeline(
        max_gpu_workers=4,      # 4 parallel GPU workers
        max_io_workers=2,       # 2 parallel I/O workers
        task_queue_size=50,
        result_buffer_size=20,
        output_directory=output_dir
    )
    
    # Create mock GPU processor
    gpu_processor = MockGPUProcessor(processing_time=0.05)  # 50ms per combination
    
    print(f"🎯 Processing {len(combinations)} combinations with {pipeline.max_gpu_workers} GPU workers")
    
    # Process combinations asynchronously
    start_time = time.time()
    processed_results = []
    
    # Track progress
    def progress_callback(progress: float, result):
        if result and result.success:
            print(f"✅ Combo {result.combo_id:2d} completed by {result.worker_id} "
                  f"({progress*100:.1f}% done, {result.processing_time:.3f}s)")
        elif result and not result.success:
            print(f"❌ Combo {result.combo_id:2d} failed: {result.error_message}")
    
    print("\n🔄 Starting asynchronous processing...")
    async for result in pipeline.process_combinations_async(
        gpu_processor,
        combinations,
        contract_data,
        progress_callback=progress_callback
    ):
        processed_results.append(result)
    
    end_time = time.time()
    processing_time = end_time - start_time
    
    # Display results
    print(f"\n🎉 Processing Complete!")
    print("=" * 40)
    
    successful_results = [r for r in processed_results if r.success]
    failed_results = [r for r in processed_results if not r.success]
    
    print(f"Total combinations: {len(combinations)}")
    print(f"Successful: {len(successful_results)}")
    print(f"Failed: {len(failed_results)}")
    print(f"Success rate: {len(successful_results)/len(combinations)*100:.1f}%")
    print(f"Total processing time: {processing_time:.2f}s")
    print(f"Throughput: {len(successful_results)/processing_time:.1f} combinations/second")
    
    # Get detailed statistics
    stats = pipeline.get_pipeline_statistics()
    print(f"\n📈 Pipeline Statistics:")
    print(f"GPU efficiency: {stats['gpu_efficiency_percent']:.1f}%")
    print(f"I/O efficiency: {stats['io_efficiency_percent']:.1f}%")
    print(f"Peak concurrent tasks: {stats['concurrent_tasks_peak']}")
    print(f"Tasks retried: {stats['tasks_retried']}")
    print(f"Results written: {stats['results_written']}")
    
    # Calculate theoretical sequential time
    sequential_time = len(combinations) * 0.05  # 50ms per combo
    speedup = sequential_time / processing_time
    print(f"\n⚡ Performance Improvement:")
    print(f"Sequential time (estimated): {sequential_time:.2f}s")
    print(f"Parallel time (actual): {processing_time:.2f}s")
    print(f"Speedup: {speedup:.2f}x")
    
    # Cleanup
    pipeline.cleanup()
    
    return {
        'total_combinations': len(combinations),
        'successful_combinations': len(successful_results),
        'processing_time': processing_time,
        'throughput': len(successful_results) / processing_time,
        'speedup': speedup,
        'pipeline_stats': stats
    }

async def demonstrate_orchestrator():
    """Demonstrate the async orchestrator with multiple contracts"""
    print("\n\n🎭 Async GPU Orchestrator Demonstration")
    print("=" * 60)
    
    # Create mock components
    from unittest.mock import patch
    
    # Mock contract data manager
    contract_manager = MockContractDataManager()
    
    # Mock GPU processor  
    gpu_processor = MockGPUProcessor(processing_time=0.03)  # 30ms per combo
    
    with patch('gpu_parallel_processing.async_orchestrator.ContractDataManager', return_value=contract_manager), \
         patch('gpu_parallel_processing.async_orchestrator.EnhancedGPUCombinationProcessor', return_value=gpu_processor):
        
        # Initialize orchestrator
        orchestrator = AsyncGPUOrchestrator(
            max_gpu_workers=3,
            max_io_workers=2,
            gpu_memory_pool_gb=12.0,
            output_directory="orchestrator_demo_output"
        )
        
        # Create combinations for multiple contracts
        contract_combinations = {
            'ES_2024_03': [{'combo_id': i, 'param1': i*5, 'param2': i*10} for i in range(1, 11)],  # 10 combos
            'NQ_2024_03': [{'combo_id': i, 'param1': i*7, 'param2': i*14} for i in range(11, 21)], # 10 combos  
            'YM_2024_03': [{'combo_id': i, 'param1': i*3, 'param2': i*6} for i in range(21, 31)]   # 10 combos
        }
        
        print(f"🌐 Processing {len(contract_combinations)} contracts:")
        for contract, combos in contract_combinations.items():
            print(f"  - {contract}: {len(combos)} combinations")
        
        # Track overall progress
        def multi_progress_callback(progress_info):
            print(f"📊 {progress_info['contract']}: {progress_info['contract_progress']*100:.1f}% | "
                  f"Overall: {progress_info['overall_progress']*100:.1f}% | "
                  f"({progress_info['processed_combinations']}/{progress_info['total_combinations']})")
        
        # Process all contracts
        start_time = time.time()
        results = await orchestrator.process_multiple_contracts(
            contract_combinations,
            progress_callback=multi_progress_callback
        )
        end_time = time.time()
        
        # Display results
        print(f"\n🎊 Multi-Contract Processing Complete!")
        print("=" * 50)
        
        total_time = end_time - start_time
        total_combinations = sum(result['total_combinations'] for result in results.values())
        total_successful = sum(result['successful_combinations'] for result in results.values())
        
        print(f"Total processing time: {total_time:.2f}s")
        print(f"Total combinations: {total_combinations}")
        print(f"Total successful: {total_successful}")
        print(f"Overall throughput: {total_successful/total_time:.1f} combinations/second")
        
        print(f"\n📋 Contract Results:")
        for contract, result in results.items():
            success_rate = result['success_rate_percent']
            throughput = result['throughput_per_minute']
            print(f"  {contract}: {result['successful_combinations']}/{result['total_combinations']} "
                  f"({success_rate:.1f}% success, {throughput:.0f}/min)")
        
        # Get orchestrator statistics
        orchestrator_stats = orchestrator.get_orchestrator_statistics()
        print(f"\n📈 Orchestrator Statistics:")
        print(f"Batches processed: {orchestrator_stats['orchestrator_stats']['batches_processed']}")
        print(f"Contracts loaded: {orchestrator_stats['orchestrator_stats']['contracts_loaded']}")
        print(f"Errors encountered: {orchestrator_stats['orchestrator_stats']['errors_encountered']}")
        
        # Cleanup
        await orchestrator.cleanup()
        
        return results

async def main():
    """Main demonstration function"""
    print("🎯 Phase 1.2.2: Asynchronous Processing Pipeline Demonstration")
    print("================================================================")
    
    try:
        # Demonstrate basic async pipeline
        pipeline_results = await demonstrate_async_pipeline()
        
        # Demonstrate orchestrator with multiple contracts
        orchestrator_results = await demonstrate_orchestrator()
        
        print("\n🎉 Demonstration Complete!")
        print("=" * 60)
        print("Key achievements demonstrated:")
        print("✅ Parallel GPU processing with multiple workers")
        print("✅ Asynchronous I/O operations preventing blocking")
        print("✅ Producer-consumer pattern with task queues")
        print("✅ Error handling and retry mechanisms")
        print("✅ Multi-contract orchestration with batch processing")
        print("✅ Comprehensive performance monitoring")
        
        speedup = pipeline_results['speedup']
        throughput = pipeline_results['throughput']
        print(f"\n📊 Performance Summary:")
        print(f"Pipeline speedup: {speedup:.2f}x over sequential processing")
        print(f"Pipeline throughput: {throughput:.1f} combinations/second")
        print(f"Success rate: {pipeline_results['successful_combinations']}/{pipeline_results['total_combinations']} combinations")
        
    except Exception as e:
        print(f"❌ Demonstration failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())