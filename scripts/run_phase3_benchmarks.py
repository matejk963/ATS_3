#!/usr/bin/env python3
"""
Phase 3 Performance Benchmarks Runner

This script runs comprehensive performance benchmarks for Phase 3 components
and generates detailed reports with recommendations.
"""

import sys
import os
import time
import json
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from src.feature_engineering.performance_benchmark import PerformanceBenchmark
from src.feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline


def main():
    """Run Phase 3 performance benchmarks"""
    
    print("🚀 Starting Phase 3 Performance Benchmarks")
    print("=" * 60)
    
    # Initialize benchmark system
    benchmark = PerformanceBenchmark(
        runs=3,  # Reasonable number for actual testing
        data_sizes=[1000, 5000, 10000, 25000],
        enable_memory_tracking=True,
        random_seed=42
    )
    
    print("📊 Running comprehensive benchmarks...")
    print("   Data sizes:", benchmark.config.data_sizes)
    print("   Runs per operation:", benchmark.config.runs)
    print()
    
    # Run the full benchmark suite
    start_time = time.time()
    
    try:
        benchmark.run_full_benchmark()
        
        # Generate performance report
        print("\n📋 Generating Performance Report...")
        report = benchmark.generate_performance_report()
        
        # Save report to analysis/reports directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        reports_dir = Path("analysis/reports")
        reports_dir.mkdir(parents=True, exist_ok=True)
        
        report_file = reports_dir / f"PHASE3_BENCHMARK_REPORT_{timestamp}.md"
        
        with open(report_file, 'w') as f:
            f.write(report)
        
        print(f"📄 Report saved to: {report_file}")
        print()
        print("📈 PERFORMANCE SUMMARY")
        print("-" * 40)
        print(report)
        
        # Generate visualization data
        viz_data = benchmark.prepare_visualization_data()
        
        # Save visualization data as JSON
        viz_file = reports_dir / f"phase3_benchmark_data_{timestamp}.json"
        with open(viz_file, 'w') as f:
            # Convert numpy arrays to lists for JSON serialization
            serializable_data = {}
            for key, value in viz_data.items():
                if isinstance(value, dict):
                    serializable_data[key] = {k: list(v.values()) if hasattr(v, 'values') else v 
                                            for k, v in value.items()}
                else:
                    serializable_data[key] = value
            
            json.dump(serializable_data, f, indent=2)
        
        print(f"📊 Visualization data saved to: {viz_file}")
        
        # Detect GPU advantage threshold
        threshold = benchmark.detect_gpu_advantage_threshold()
        if threshold:
            print(f"🎯 GPU Advantage Threshold: {threshold} data points")
        else:
            print("🎯 No clear GPU advantage threshold detected")
        
        # Generate recommendations
        print("\n💡 RECOMMENDATIONS")
        print("-" * 40)
        
        # Analyze results for recommendations
        if benchmark.results:
            speedups = [r['speedup'] for r in benchmark.results.values() 
                       if r['speedup'] is not None]
            
            if speedups:
                avg_speedup = sum(speedups) / len(speedups)
                
                if avg_speedup > 2.0:
                    print("✅ GPU acceleration provides significant benefits (>2x speedup)")
                    print("   Recommendation: Enable GPU backend for production workloads")
                elif avg_speedup > 1.2:
                    print("⚠️  GPU acceleration provides moderate benefits (1.2-2x speedup)")
                    print("   Recommendation: Consider GPU for large datasets")
                else:
                    print("❌ GPU acceleration provides minimal benefits (<1.2x speedup)")
                    print("   Recommendation: Stick with CPU backend for current workloads")
                
                print(f"   Average speedup across all operations: {avg_speedup:.2f}x")
            else:
                print("⚠️  No successful GPU benchmarks completed")
                print("   Recommendation: Verify GPU/CuPy installation")
        
        # Test unified pipeline
        print("\n🔧 Testing Unified Pipeline Performance...")
        
        pipeline = UnifiedTechnicalIndicatorsPipeline()
        test_data = benchmark.generate_test_data(5000)
        
        # Test pipeline performance comparison
        pipeline_comparison = pipeline.compare_backend_performance(
            data=test_data,
            indicators=['macd', 'atr'],
            runs=2
        )
        
        print("Pipeline Performance Comparison:")
        for backend, results in pipeline_comparison.items():
            if isinstance(results, dict) and results.get('backend_available'):
                print(f"  {backend.upper()}: {results['avg_time']:.4f}s avg")
        
        if 'speedup' in pipeline_comparison:
            speedup = pipeline_comparison['speedup']
            print(f"  Overall Pipeline Speedup: {speedup:.2f}x")
        
    except Exception as e:
        print(f"❌ Benchmark failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    total_time = time.time() - start_time
    print(f"\n⏱️  Total benchmark time: {total_time:.2f} seconds")
    
    print("\n✅ Phase 3 benchmarks completed successfully!")
    print("📋 Check the generated report files for detailed analysis.")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())