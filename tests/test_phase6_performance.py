"""Performance benchmarking tests for Phase 6 position signal generation."""

import pytest
import pandas as pd
import numpy as np
import cupy as cp
import time
from datetime import datetime, timedelta

from src.feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline
from src.feature_engineering.position_generator import GPUPositionGenerator, ThresholdConfig
from src.feature_engineering.array_backend import ArrayBackend


class TestPhase6Performance:
    """Performance tests for Phase 6 position generation."""
    
    @pytest.fixture
    def backend(self):
        """Create ArrayBackend instance."""
        return ArrayBackend()
    
    @pytest.fixture
    def generator(self, backend):
        """Create GPUPositionGenerator instance."""
        return GPUPositionGenerator(backend)
    
    @pytest.fixture
    def pipeline(self):
        """Create pipeline instance."""
        return UnifiedTechnicalIndicatorsPipeline()
    
    def generate_test_data(self, size):
        """Generate test OHLCV data of specified size."""
        dates = pd.date_range('2024-01-01', periods=size, freq='5min')
        prices = 100 + np.cumsum(np.random.randn(size) * 0.1)
        
        data = pd.DataFrame({
            'Datetime': dates,
            'open': prices + np.random.randn(size) * 0.05,
            'high': prices + np.abs(np.random.randn(size) * 0.1),
            'low': prices - np.abs(np.random.randn(size) * 0.1),
            'close': prices,
            'volume': np.random.randint(1000, 10000, size)
        })
        
        return data
    
    def test_position_generator_performance(self, generator):
        """Test raw position generator performance."""
        sizes = [1000, 10000, 100000, 1000000]
        
        print("\n=== Position Generator Performance ===")
        print("Size\t\tTime(s)\t\tPoints/sec")
        print("-" * 45)
        
        for size in sizes:
            # Generate test data
            bias_numeric = cp.random.randint(-2, 3, size=size)
            price_position = cp.random.uniform(0, 1, size=size)
            
            # Warm up
            _ = generator.compute_position_signals(bias_numeric[:100], price_position[:100])
            
            # Benchmark
            cp.cuda.Stream.null.synchronize()
            start_time = time.time()
            
            signals = generator.compute_position_signals(bias_numeric, price_position)
            
            cp.cuda.Stream.null.synchronize()
            elapsed_time = time.time() - start_time
            
            points_per_sec = size / elapsed_time
            
            print(f"{size:,}\t\t{elapsed_time:.4f}\t\t{points_per_sec:,.0f}")
    
    def test_phase6_overhead(self, pipeline):
        """Test overhead of Phase 6 on top of Phase 5."""
        sizes = [1000, 5000, 10000, 50000]
        
        print("\n=== Phase 6 Pipeline Overhead ===")
        print("Size\t\tPhase5(s)\tPhase6(s)\tOverhead(s)\tOverhead(%)")
        print("-" * 65)
        
        for size in sizes:
            data = self.generate_test_data(size)
            
            # Clear GPU cache
            cp.get_default_memory_pool().free_all_blocks()
            
            # Benchmark Phase 5
            start_time = time.time()
            phase5_result = pipeline.compute_all_indicators_features_and_bias(data)
            phase5_time = time.time() - start_time
            
            # Clear GPU cache
            cp.get_default_memory_pool().free_all_blocks()
            
            # Benchmark Phase 6
            start_time = time.time()
            phase6_result = pipeline.compute_all_indicators_features_bias_and_positions(data)
            phase6_time = time.time() - start_time
            
            overhead = phase6_time - phase5_time
            overhead_pct = (overhead / phase5_time) * 100 if phase5_time > 0 else 0
            
            print(f"{size:,}\t\t{phase5_time:.4f}\t\t{phase6_time:.4f}\t\t"
                  f"{overhead:.4f}\t\t{overhead_pct:.1f}%")
    
    def test_memory_efficiency(self, generator):
        """Test memory usage of position generation."""
        size = 1000000
        
        print("\n=== Memory Efficiency Test ===")
        
        # Clear GPU memory
        mempool = cp.get_default_memory_pool()
        mempool.free_all_blocks()
        
        initial_memory = mempool.used_bytes() / (1024 * 1024)  # MB
        
        # Create test data
        bias_numeric = cp.random.randint(-2, 3, size=size)
        price_position = cp.random.uniform(0, 1, size=size)
        
        data_memory = mempool.used_bytes() / (1024 * 1024)  # MB
        
        # Compute position signals
        signals = generator.compute_position_signals(bias_numeric, price_position)
        
        final_memory = mempool.used_bytes() / (1024 * 1024)  # MB
        
        print(f"Initial memory: {initial_memory:.2f} MB")
        print(f"After data creation: {data_memory:.2f} MB")
        print(f"After position generation: {final_memory:.2f} MB")
        print(f"Memory for position signals: {final_memory - data_memory:.2f} MB")
        print(f"Memory per million points: {(final_memory - data_memory) / (size / 1000000):.2f} MB")
    
    def test_threshold_performance_impact(self, backend):
        """Test if custom thresholds impact performance."""
        size = 100000
        
        # Generate test data
        bias_numeric = cp.random.randint(-2, 3, size=size)
        price_position = cp.random.uniform(0, 1, size=size)
        
        # Default thresholds
        default_generator = GPUPositionGenerator(backend)
        
        # Custom thresholds
        custom_config = ThresholdConfig(
            strong_bullish_buy=0.4,
            bullish_buy=0.25,
            bullish_sell=0.85,
            neutral_buy=0.25,
            neutral_sell=0.85,
            bearish_buy=0.15,
            bearish_sell=0.75,
            strong_bearish_sell=0.6
        )
        custom_generator = GPUPositionGenerator(backend, custom_config)
        
        print("\n=== Threshold Performance Impact ===")
        
        # Benchmark default
        cp.cuda.Stream.null.synchronize()
        start_time = time.time()
        _ = default_generator.compute_position_signals(bias_numeric, price_position)
        cp.cuda.Stream.null.synchronize()
        default_time = time.time() - start_time
        
        # Benchmark custom
        cp.cuda.Stream.null.synchronize()
        start_time = time.time()
        _ = custom_generator.compute_position_signals(bias_numeric, price_position)
        cp.cuda.Stream.null.synchronize()
        custom_time = time.time() - start_time
        
        print(f"Default thresholds: {default_time:.4f}s")
        print(f"Custom thresholds: {custom_time:.4f}s")
        print(f"Difference: {abs(custom_time - default_time):.4f}s "
              f"({abs(custom_time - default_time) / default_time * 100:.1f}%)")
    
    def test_scaling_efficiency(self, generator):
        """Test how well the position generator scales with data size."""
        sizes = [10000, 50000, 100000, 500000, 1000000]
        
        print("\n=== Scaling Efficiency Test ===")
        print("Size\t\tTime(s)\t\tμs/point\tScaling Factor")
        print("-" * 55)
        
        base_time_per_point = None
        
        for size in sizes:
            # Generate test data
            bias_numeric = cp.random.randint(-2, 3, size=size)
            price_position = cp.random.uniform(0, 1, size=size)
            
            # Benchmark
            cp.cuda.Stream.null.synchronize()
            start_time = time.time()
            _ = generator.compute_position_signals(bias_numeric, price_position)
            cp.cuda.Stream.null.synchronize()
            elapsed_time = time.time() - start_time
            
            time_per_point = (elapsed_time / size) * 1000000  # microseconds
            
            if base_time_per_point is None:
                base_time_per_point = time_per_point
                scaling_factor = 1.0
            else:
                scaling_factor = time_per_point / base_time_per_point
            
            print(f"{size:,}\t\t{elapsed_time:.4f}\t\t{time_per_point:.2f}\t\t{scaling_factor:.2f}x")