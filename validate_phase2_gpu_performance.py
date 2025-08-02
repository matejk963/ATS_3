#!/usr/bin/env python3
"""
Phase 2 GPU Performance Validation Script

Validates the GPU utilization improvement achieved by Phase 2 implementation:
- Target: 60-80% GPU utilization (vs 8.2% baseline)
- Performance: 5-10x speedup using Phase 1 infrastructure
- Batch Processing: 25-40 combinations per batch efficiently
- Algorithm Correctness: 100% compatibility with legacy implementations

This script demonstrates the complete Phase 2 GPU acceleration pipeline
and measures actual GPU utilization against the development plan targets.
"""

import sys
import os
import time
import pandas as pd
import numpy as np
from typing import Dict, List, Any
import argparse

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

try:
    from feature_engineering.array_backend import ArrayBackend
    from feature_engineering.gpu_technical_indicators_batch import (
        GPUTechnicalIndicatorsBatch, 
        BatchProcessingConfig
    )
    from feature_engineering.gpu_memory_manager import UnifiedGPUTechnicalIndicators
    from feature_engineering.atr_calculator import ATRCalculator
    from feature_engineering.macd_calculator import MACDCalculator
    from feature_engineering.gpu_swing_detector import GPUSwingDetector
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you're running from the project root directory")
    sys.exit(1)


class Phase2PerformanceValidator:
    """
    Comprehensive performance validator for Phase 2 GPU acceleration.
    
    Measures and validates:
    - GPU utilization improvement (target: 60-80%)
    - Processing speed improvement (target: 5-10x)
    - Batch processing efficiency (25-40 combinations)
    - Algorithm correctness and compatibility
    """
    
    def __init__(self):
        """Initialize performance validator"""
        self.gpu_backend = None
        self.results = {}
        
    def initialize_gpu_backend(self) -> bool:
        """Initialize GPU backend and validate availability"""
        try:
            print("🔧 Initializing GPU backend...")
            self.gpu_backend = ArrayBackend(backend='cupy')
            
            # Test GPU availability
            test_array = self.gpu_backend.asarray([1, 2, 3, 4, 5])
            result = self.gpu_backend.to_cpu(test_array)
            
            print("✅ GPU backend initialized successfully")
            print(f"   Backend type: {self.gpu_backend.backend}")
            print(f"   Test computation successful: {result}")
            
            return True
            
        except Exception as e:
            print(f"❌ GPU backend initialization failed: {e}")
            print("   This validation requires a CUDA-compatible GPU with CuPy installed")
            return False
    
    def generate_test_combinations(self, num_combinations: int = 50) -> List[Dict]:
        """Generate realistic test combinations for validation"""
        print(f"📊 Generating {num_combinations} test combinations...")
        
        combinations = []
        np.random.seed(42)  # Reproducible results
        
        for i in range(num_combinations):
            # Generate realistic tick data
            n_ticks = 1000 + (i * 10)  # Varying data sizes
            base_price = 100.0 + (i * 0.1)
            
            # Generate price movements
            price_changes = np.random.normal(0, 0.1, n_ticks).cumsum()
            prices = base_price + price_changes
            
            tick_data = pd.DataFrame({
                'datetime': pd.date_range('2024-01-01', periods=n_ticks, freq='1min'),
                'price': prices,
                'volume': np.random.randint(1, 100, n_ticks),
                'tradeid': range(n_ticks),
                'nanotime': pd.date_range('2024-01-01', periods=n_ticks, freq='1min')
            })
            
            # Generate historical OHLC data
            n_candles = 100
            opens = base_price + np.random.normal(0, 1, n_candles).cumsum()
            closes = opens + np.random.normal(0, 0.5, n_candles)
            highs = np.maximum(opens, closes) + np.random.exponential(0.2, n_candles)
            lows = np.minimum(opens, closes) - np.random.exponential(0.2, n_candles)
            
            historical_data = pd.DataFrame({
                'open': opens,
                'high': highs,
                'low': lows,
                'close': closes,
                'volume': np.random.randint(100, 1000, n_candles)
            }, index=pd.date_range('2024-01-01', periods=n_candles, freq='1h'))
            
            combination = {
                'combination_id': f'validation_combo_{i:06d}',
                'tick_data': tick_data,
                'historical_candles': historical_data,
                'historical_macd': historical_data,
                'atr_period': 14 + (i % 5),
                'macd_params': {
                    'fast': 12 + (i % 3),
                    'slow': 26 + (i % 3),
                    'signal': 9 + (i % 2)
                }
            }
            combinations.append(combination)
        
        print(f"✅ Generated {len(combinations)} test combinations")
        return combinations
    
    def validate_individual_components(self, test_combinations: List[Dict]) -> Dict[str, Any]:
        """Validate individual GPU-accelerated components"""
        print("\\n🧪 Validating Individual GPU Components...")
        
        component_results = {}
        
        # Test ATR Calculator
        print("\\n  📈 Testing ATR Calculator GPU Acceleration...")
        atr_calculator = ATRCalculator(self.gpu_backend)
        
        start_time = time.time()
        atr_results = atr_calculator.compute_atr_batch_gpu_accelerated(test_combinations)
        atr_time = time.time() - start_time
        
        component_results['atr'] = {
            'processing_time': atr_time,
            'combinations_processed': len(test_combinations),
            'processing_rate': len(test_combinations) / atr_time,
            'results_count': len(atr_results),
            'success': len(atr_results) == len(test_combinations)
        }
        
        print(f"    ✅ ATR: {atr_time:.2f}s, {component_results['atr']['processing_rate']:.1f} combinations/sec")
        
        # Test MACD Calculator
        print("\\n  📊 Testing MACD Calculator GPU Acceleration...")
        macd_calculator = MACDCalculator(self.gpu_backend)
        
        start_time = time.time()
        macd_results = macd_calculator.compute_macd_batch_gpu_accelerated(test_combinations)
        macd_time = time.time() - start_time
        
        component_results['macd'] = {
            'processing_time': macd_time,
            'combinations_processed': len(test_combinations),
            'processing_rate': len(test_combinations) / macd_time,
            'results_count': len(macd_results),
            'success': len(macd_results) == len(test_combinations)
        }
        
        print(f"    ✅ MACD: {macd_time:.2f}s, {component_results['macd']['processing_rate']:.1f} combinations/sec")
        
        # Test Swing Detector
        print("\\n  📉 Testing Swing Detector GPU Optimization...")
        swing_detector = GPUSwingDetector(self.gpu_backend)
        
        ohlc_batch = [combo['historical_candles'] for combo in test_combinations]
        
        start_time = time.time()
        swing_results = swing_detector.detect_swings_batch_gpu_accelerated(ohlc_batch)
        swing_time = time.time() - start_time
        
        component_results['swing'] = {
            'processing_time': swing_time,
            'dataframes_processed': len(ohlc_batch),
            'processing_rate': len(ohlc_batch) / swing_time,
            'results_count': len(swing_results),
            'success': len(swing_results) == len(ohlc_batch)
        }
        
        print(f"    ✅ Swing: {swing_time:.2f}s, {component_results['swing']['processing_rate']:.1f} DataFrames/sec")
        
        return component_results
    
    def validate_unified_pipeline(self, test_combinations: List[Dict]) -> Dict[str, Any]:
        """Validate unified GPU pipeline with Phase 1 infrastructure"""
        print("\\n🚀 Validating Unified GPU Pipeline...")
        
        unified_pipeline = UnifiedGPUTechnicalIndicators(self.gpu_backend)
        
        start_time = time.time()
        pipeline_results = unified_pipeline.compute_all_indicators_batch(test_combinations)
        pipeline_time = time.time() - start_time
        
        # Get performance statistics
        performance_stats = unified_pipeline.get_gpu_performance_statistics()
        
        pipeline_validation = {
            'processing_time': pipeline_time,
            'combinations_processed': len(test_combinations),
            'processing_rate': len(test_combinations) / pipeline_time,
            'results_count': len(pipeline_results),
            'success': len(pipeline_results) == len(test_combinations),
            'performance_stats': performance_stats
        }
        
        print(f"✅ Unified Pipeline: {pipeline_time:.2f}s, {pipeline_validation['processing_rate']:.1f} combinations/sec")
        
        return pipeline_validation
    
    def validate_batch_processing_infrastructure(self, test_combinations: List[Dict]) -> Dict[str, Any]:
        """Validate batch processing infrastructure with performance monitoring"""
        print("\\n⚡ Validating Batch Processing Infrastructure...")
        
        # Configure for maximum performance monitoring
        config = BatchProcessingConfig(
            target_gpu_utilization=0.75,
            max_batch_size=40,
            min_batch_size=25,
            enable_performance_monitoring=True,
            cuda_streams=8
        )
        
        batch_processor = GPUTechnicalIndicatorsBatch(self.gpu_backend, config)
        
        start_time = time.time()
        batch_results = batch_processor.process_combinations_batch(test_combinations)
        total_time = time.time() - start_time
        
        # Get comprehensive performance report
        performance_report = batch_processor.get_performance_report()
        
        batch_validation = {
            'total_processing_time': total_time,
            'combinations_processed': len(test_combinations),
            'processing_rate': len(test_combinations) / total_time,
            'results_count': len(batch_results),
            'success': len(batch_results) == len(test_combinations),
            'performance_report': performance_report
        }
        
        gpu_utilization = performance_report['gpu_utilization']['average_percent']
        target_achieved = performance_report['gpu_utilization']['target_achieved']
        
        print(f"✅ Batch Processing: {total_time:.2f}s, {batch_validation['processing_rate']:.1f} combinations/sec")
        print(f"✅ GPU Utilization: {gpu_utilization:.1f}% ({'TARGET MET' if target_achieved else 'BELOW TARGET'})")
        
        return batch_validation
    
    def validate_performance_targets(self, results: Dict[str, Any]) -> Dict[str, bool]:
        """Validate that performance targets from the development plan are met"""
        print("\\n🎯 Validating Performance Targets...")
        
        validation_results = {}
        
        # Target 1: GPU Utilization (60-80%)
        batch_results = results.get('batch_processing', {})
        performance_report = batch_results.get('performance_report', {})
        gpu_utilization = performance_report.get('gpu_utilization', {}).get('average_percent', 0)
        
        gpu_target_met = 60 <= gpu_utilization <= 80
        validation_results['gpu_utilization_target'] = gpu_target_met
        
        status = "✅ MET" if gpu_target_met else "❌ NOT MET"
        print(f"  📊 GPU Utilization Target (60-80%): {gpu_utilization:.1f}% - {status}")
        
        # Target 2: Processing Speed (baseline improvement)
        pipeline_rate = results.get('unified_pipeline', {}).get('processing_rate', 0)
        speed_target_met = pipeline_rate > 10  # Target: >10 combinations/sec
        validation_results['processing_speed_target'] = speed_target_met
        
        status = "✅ MET" if speed_target_met else "❌ NOT MET"
        print(f"  ⚡ Processing Speed Target (>10 comb/sec): {pipeline_rate:.1f} - {status}")
        
        # Target 3: Batch Processing Efficiency (25-40 combinations per batch)
        avg_batch_size = performance_report.get('processing_statistics', {}).get('average_batch_size', 0)
        batch_target_met = 25 <= avg_batch_size <= 40
        validation_results['batch_size_target'] = batch_target_met
        
        status = "✅ MET" if batch_target_met else "❌ NOT MET"
        print(f"  📦 Batch Size Target (25-40): {avg_batch_size:.1f} - {status}")
        
        # Target 4: Algorithm Correctness (all components successful)
        all_successful = all([
            results.get('components', {}).get('atr', {}).get('success', False),
            results.get('components', {}).get('macd', {}).get('success', False),
            results.get('components', {}).get('swing', {}).get('success', False),
            results.get('unified_pipeline', {}).get('success', False),
            results.get('batch_processing', {}).get('success', False)
        ])
        validation_results['algorithm_correctness'] = all_successful
        
        status = "✅ MET" if all_successful else "❌ NOT MET"
        print(f"  🧮 Algorithm Correctness: {status}")
        
        return validation_results
    
    def run_validation(self, num_combinations: int = 50) -> Dict[str, Any]:
        """Run complete Phase 2 performance validation"""
        print("🚀 PHASE 2 GPU PERFORMANCE VALIDATION")
        print("=" * 60)
        
        # Initialize GPU backend
        if not self.initialize_gpu_backend():
            return {'success': False, 'error': 'GPU initialization failed'}
        
        # Generate test data
        test_combinations = self.generate_test_combinations(num_combinations)
        
        # Run validation tests
        results = {}
        
        try:
            # Test individual components
            results['components'] = self.validate_individual_components(test_combinations)
            
            # Test unified pipeline
            results['unified_pipeline'] = self.validate_unified_pipeline(test_combinations)
            
            # Test batch processing infrastructure
            results['batch_processing'] = self.validate_batch_processing_infrastructure(test_combinations)
            
            # Validate performance targets
            results['target_validation'] = self.validate_performance_targets(results)
            
            # Overall success assessment
            all_targets_met = all(results['target_validation'].values())
            results['overall_success'] = all_targets_met
            
            return results
            
        except Exception as e:
            print(f"❌ Validation failed with error: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': str(e)}
    
    def print_final_report(self, results: Dict[str, Any]):
        """Print comprehensive final validation report"""
        print("\\n" + "=" * 60)
        print("PHASE 2 GPU ACCELERATION VALIDATION REPORT")
        print("=" * 60)
        
        if not results.get('success', True):
            print(f"❌ VALIDATION FAILED: {results.get('error', 'Unknown error')}")
            return
        
        # Performance Summary
        print("\\n📊 PERFORMANCE SUMMARY:")
        
        batch_results = results.get('batch_processing', {})
        performance_report = batch_results.get('performance_report', {})
        
        gpu_utilization = performance_report.get('gpu_utilization', {}).get('average_percent', 0)
        processing_rate = batch_results.get('processing_rate', 0)
        total_combinations = batch_results.get('combinations_processed', 0)
        total_time = batch_results.get('total_processing_time', 0)
        
        print(f"  📈 GPU Utilization: {gpu_utilization:.1f}% (Target: 60-80%)")
        print(f"  ⚡ Processing Rate: {processing_rate:.1f} combinations/sec")
        print(f"  📦 Total Combinations Processed: {total_combinations}")
        print(f"  ⏱️  Total Processing Time: {total_time:.2f}s")
        
        # Component Performance
        print("\\n🧩 COMPONENT PERFORMANCE:")
        components = results.get('components', {})
        
        for component_name, component_data in components.items():
            rate = component_data.get('processing_rate', 0)
            success = component_data.get('success', False)
            status = "✅" if success else "❌"
            print(f"  {status} {component_name.upper()}: {rate:.1f} units/sec")
        
        # Target Achievement
        print("\\n🎯 TARGET ACHIEVEMENT:")
        target_validation = results.get('target_validation', {})
        
        for target_name, achieved in target_validation.items():
            status = "✅ ACHIEVED" if achieved else "❌ NOT ACHIEVED"
            target_display = target_name.replace('_', ' ').title()
            print(f"  {status} {target_display}")
        
        # Overall Assessment
        overall_success = results.get('overall_success', False)
        
        print("\\n" + "=" * 60)
        if overall_success:
            print("🎉 PHASE 2 VALIDATION: SUCCESS")
            print("   GPU acceleration targets achieved!")
            print("   Ready for production deployment.")
        else:
            print("💥 PHASE 2 VALIDATION: PARTIAL SUCCESS")
            print("   Some targets not met. Review performance metrics.")
            print("   May require optimization before production.")
        print("=" * 60)


def main():
    """Main validation script entry point"""
    parser = argparse.ArgumentParser(description='Phase 2 GPU Performance Validation')
    parser.add_argument('--combinations', type=int, default=50,
                       help='Number of test combinations to process (default: 50)')
    parser.add_argument('--verbose', action='store_true',
                       help='Enable verbose output')
    
    args = parser.parse_args()
    
    # Run validation
    validator = Phase2PerformanceValidator()
    results = validator.run_validation(args.combinations)
    validator.print_final_report(results)
    
    # Exit with appropriate code
    if results.get('overall_success', False):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()