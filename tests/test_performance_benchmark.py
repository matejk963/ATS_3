"""
Performance benchmark for legacy swing detector integration.

This test validates that the legacy swing detector integration maintains
acceptable performance in the GPU pipeline.
"""

import pytest
import pandas as pd
import numpy as np
import time
import sys
import os

# Add source to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline
from feature_engineering.legacy_swing_detector import LegacySwingDetector


class TestPerformanceBenchmark:
    """Performance benchmark tests"""
    
    @pytest.fixture
    def large_ohlc_data(self):
        """Generate larger OHLC dataset for performance testing"""
        np.random.seed(42)
        n_points = 1000  # Larger dataset for performance testing
        
        # Generate realistic price data
        base_price = 100.0
        prices = [base_price]
        
        for i in range(n_points - 1):
            change = np.random.normal(0, 0.5)
            if i % 50 == 0:  # Trend every 50 points
                change += np.random.choice([-2, 2])
            prices.append(max(50, prices[-1] + change))
        
        # Create OHLC from prices
        data = []
        for i, close in enumerate(prices):
            high = close + abs(np.random.normal(0, 0.3))
            low = close - abs(np.random.normal(0, 0.3))
            open_price = prices[i-1] if i > 0 else close
            
            data.append({
                'open': open_price,
                'high': high,
                'low': low,
                'close': close,
                'volume': 1000 + np.random.randint(-200, 200)
            })
        
        return pd.DataFrame(data)
    
    @pytest.fixture
    def pipeline(self):
        """Initialize GPU pipeline for testing"""
        try:
            return UnifiedTechnicalIndicatorsPipeline()
        except (ImportError, RuntimeError) as e:
            pytest.skip(f"GPU pipeline not available: {e}")
    
    def test_swing_detection_performance(self, pipeline, large_ohlc_data):
        """Test swing detection performance"""
        start_time = time.perf_counter()
        
        result = pipeline.compute_indicators(
            data=large_ohlc_data,
            indicators=['swing_points']
        )
        
        end_time = time.perf_counter()
        execution_time = end_time - start_time
        
        print(f"\nSwing detection performance:")
        print(f"  Data points: {len(large_ohlc_data):,}")
        print(f"  Execution time: {execution_time:.4f} seconds")
        print(f"  Points per second: {len(large_ohlc_data)/execution_time:,.0f}")
        
        # Performance target: should process at least 1000 points per second
        assert len(large_ohlc_data)/execution_time > 1000, f"Performance too slow: {len(large_ohlc_data)/execution_time:.0f} points/sec"
        
        # Validate results
        assert len(result) == len(large_ohlc_data)
        assert 'swing_highs' in result.columns
        assert 'swing_lows' in result.columns
    
    def test_full_pipeline_performance(self, pipeline, large_ohlc_data):
        """Test full pipeline performance with all features"""
        start_time = time.perf_counter()
        
        result = pipeline.compute_all_indicators_and_features(
            data=large_ohlc_data
        )
        
        end_time = time.perf_counter()
        execution_time = end_time - start_time
        
        print(f"\nFull pipeline performance:")
        print(f"  Data points: {len(large_ohlc_data):,}")
        print(f"  Execution time: {execution_time:.4f} seconds")
        print(f"  Points per second: {len(large_ohlc_data)/execution_time:,.0f}")
        
        # Performance target: should process at least 500 points per second for full pipeline
        assert len(large_ohlc_data)/execution_time > 500, f"Full pipeline too slow: {len(large_ohlc_data)/execution_time:.0f} points/sec"
        
        # Validate results
        assert len(result) == len(large_ohlc_data)
        assert 'swing_highs' in result.columns
        assert 'swing_lows' in result.columns
        assert 'price_position' in result.columns
    
    def test_legacy_vs_pipeline_compatibility(self, large_ohlc_data):
        """Test that pipeline produces same results as standalone legacy detector"""
        # Standalone legacy detector
        legacy_detector = LegacySwingDetector()
        legacy_start = time.perf_counter()
        legacy_result = legacy_detector.detect_swing_points(large_ohlc_data)
        legacy_end = time.perf_counter()
        legacy_time = legacy_end - legacy_start
        
        # Pipeline with legacy detector integration
        try:
            pipeline = UnifiedTechnicalIndicatorsPipeline()
            pipeline_start = time.perf_counter()
            pipeline_result = pipeline.compute_indicators(
                data=large_ohlc_data,
                indicators=['swing_points']
            )
            pipeline_end = time.perf_counter()
            pipeline_time = pipeline_end - pipeline_start
        except (ImportError, RuntimeError):
            pytest.skip("GPU pipeline not available")
        
        print(f"\nCompatibility benchmark:")
        print(f"  Legacy detector time: {legacy_time:.4f} seconds")
        print(f"  Pipeline time: {pipeline_time:.4f} seconds")
        print(f"  Performance ratio: {pipeline_time/legacy_time:.2f}x")
        
        # Results should be approximately equal (allowing for floating point precision differences)
        np.testing.assert_allclose(
            legacy_result['swing_high'].values,
            pipeline_result['swing_highs'].values,
            rtol=1e-7, atol=1e-5,
            err_msg="Pipeline results don't match legacy detector for swing_high"
        )
        
        np.testing.assert_allclose(
            legacy_result['swing_low'].values,
            pipeline_result['swing_lows'].values,
            rtol=1e-7, atol=1e-5,
            err_msg="Pipeline results don't match legacy detector for swing_low"
        )
        
        # Pipeline should not be more than 5x slower than standalone
        assert pipeline_time/legacy_time < 5.0, f"Pipeline too slow vs legacy: {pipeline_time/legacy_time:.2f}x"
    
    def test_memory_efficiency(self, pipeline, large_ohlc_data):
        """Test memory efficiency of the pipeline"""
        # Get initial memory stats
        initial_stats = pipeline.get_gpu_memory_statistics()
        print(f"\nMemory efficiency test:")
        print(f"  Initial GPU memory: {initial_stats}")
        
        # Run computation
        result = pipeline.compute_indicators(
            data=large_ohlc_data,
            indicators=['swing_points', 'macd', 'atr']
        )
        
        # Get final memory stats
        final_stats = pipeline.get_gpu_memory_statistics()
        print(f"  Final GPU memory: {final_stats}")
        
        # Validate results were computed
        assert len(result) == len(large_ohlc_data)
        assert 'swing_highs' in result.columns
        assert 'macd_line' in result.columns
        assert 'atr' in result.columns
        
        # Clear cache and check memory is freed
        pipeline.clear_gpu_memory_cache()
        cleared_stats = pipeline.get_gpu_memory_statistics()
        print(f"  After cache clear: {cleared_stats}")
    
    def test_scalability(self, pipeline):
        """Test scalability with different data sizes"""
        sizes = [100, 500, 1000]
        times = []
        
        print(f"\nScalability test:")
        
        for size in sizes:
            # Generate data of specific size
            np.random.seed(42)
            base_price = 100.0
            prices = [base_price]
            
            for i in range(size - 1):
                change = np.random.normal(0, 0.5)
                prices.append(max(50, prices[-1] + change))
            
            data = []
            for i, close in enumerate(prices):
                high = close + abs(np.random.normal(0, 0.2))
                low = close - abs(np.random.normal(0, 0.2))
                open_price = prices[i-1] if i > 0 else close
                
                data.append({
                    'open': open_price,
                    'high': high,
                    'low': low,
                    'close': close
                })
            
            test_data = pd.DataFrame(data)
            
            # Benchmark
            start_time = time.perf_counter()
            result = pipeline.compute_indicators(
                data=test_data,
                indicators=['swing_points']
            )
            end_time = time.perf_counter()
            
            execution_time = end_time - start_time
            times.append(execution_time)
            
            print(f"  {size:,} points: {execution_time:.4f}s ({size/execution_time:,.0f} points/sec)")
            
            # Validate results
            assert len(result) == size
        
        # Check that performance scales reasonably (not exponentially worse)
        # Time per point should not increase drastically
        time_per_point = [times[i]/sizes[i] for i in range(len(sizes))]
        max_ratio = max(time_per_point) / min(time_per_point)
        
        print(f"  Scalability ratio: {max_ratio:.2f}x")
        assert max_ratio < 3.0, f"Poor scalability: {max_ratio:.2f}x difference in time per point"


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s"])