"""
Test suite for CPU/GPU performance benchmarking functionality.

Following TDD principles: write tests first, then implement the benchmarking system.
"""

import pytest
import pandas as pd
import numpy as np
import time
from unittest.mock import patch, MagicMock

# Import will be created after test
from src.feature_engineering.performance_benchmark import PerformanceBenchmark


class TestPerformanceBenchmark:
    """Test performance benchmarking system"""
    
    @pytest.fixture
    def sample_data_small(self):
        """Create small sample data for testing"""
        np.random.seed(42)
        size = 100
        prices = 100 + np.cumsum(np.random.randn(size) * 0.01)
        
        return pd.DataFrame({
            'open': prices * (1 + np.random.randn(size) * 0.001),
            'high': prices * (1 + np.abs(np.random.randn(size)) * 0.002),
            'low': prices * (1 - np.abs(np.random.randn(size)) * 0.002),
            'close': prices,
            'volume': np.random.randint(1000, 10000, size),
            'datetime': pd.date_range('2023-01-01', periods=size, freq='1min')
        })
    
    @pytest.fixture
    def sample_data_large(self):
        """Create large sample data for testing"""
        np.random.seed(42)
        size = 50000
        prices = 100 + np.cumsum(np.random.randn(size) * 0.01)
        
        return pd.DataFrame({
            'open': prices * (1 + np.random.randn(size) * 0.001),
            'high': prices * (1 + np.abs(np.random.randn(size)) * 0.002),
            'low': prices * (1 - np.abs(np.random.randn(size)) * 0.002),
            'close': prices,
            'volume': np.random.randint(1000, 10000, size),
            'datetime': pd.date_range('2023-01-01', periods=size, freq='1min')
        })
    
    def test_benchmark_initialization(self):
        """Test benchmark system initializes properly"""
        benchmark = PerformanceBenchmark()
        
        assert hasattr(benchmark, 'results')
        assert isinstance(benchmark.results, dict)
        assert hasattr(benchmark, 'generate_test_data')
        assert hasattr(benchmark, 'benchmark_operation')
        assert hasattr(benchmark, 'run_full_benchmark')
    
    def test_generate_test_data(self):
        """Test synthetic data generation"""
        benchmark = PerformanceBenchmark()
        
        # Test different sizes
        for size in [100, 1000, 10000]:
            data = benchmark.generate_test_data(size)
            
            assert isinstance(data, pd.DataFrame)
            assert len(data) == size
            assert set(data.columns) == {'open', 'high', 'low', 'close', 'volume'}
            
            # Check data quality - each row should have high >= low
            assert (data['high'] >= data['low']).all()  # High >= Low for each row
            assert not data.isnull().any().any()  # No null values
    
    def test_benchmark_single_operation(self, sample_data_small):
        """Test benchmarking a single operation"""
        benchmark = PerformanceBenchmark()
        
        # Mock operation function
        def mock_macd_operation(data, backend):
            time.sleep(0.01)  # Simulate computation time
            return data.copy()
        
        # Benchmark the operation
        result = benchmark.benchmark_operation(
            operation_func=mock_macd_operation,
            data=sample_data_small,
            backend='numpy',
            runs=3
        )
        
        # Check result structure
        assert isinstance(result, dict)
        required_keys = {'avg_time', 'std_time', 'min_time', 'max_time', 
                        'avg_memory', 'backend', 'data_size'}
        assert set(result.keys()) == required_keys
        
        # Check values are reasonable
        assert result['avg_time'] > 0
        assert result['min_time'] <= result['avg_time'] <= result['max_time']
        assert result['backend'] == 'numpy'
        assert result['data_size'] == len(sample_data_small)
    
    def test_benchmark_multiple_data_sizes(self):
        """Test benchmarking across multiple data sizes"""
        benchmark = PerformanceBenchmark()
        
        # Mock operation that scales with data size
        def scaling_operation(data, backend):
            # Simulate O(n) operation
            for _ in range(len(data) // 100):
                pass
            return data.copy()
        
        data_sizes = [100, 500, 1000]
        benchmark.run_full_benchmark(
            data_sizes=data_sizes,
            custom_operations={'scaling_test': scaling_operation},
            runs=2
        )
        
        # Check results exist for all sizes
        for size in data_sizes:
            key = f"scaling_test_{size}"
            assert key in benchmark.results
            assert 'cpu' in benchmark.results[key]
            assert 'speedup' in benchmark.results[key]
    
    def test_benchmark_macd_operation(self, sample_data_small):
        """Test MACD-specific benchmarking"""
        benchmark = PerformanceBenchmark()
        
        result = benchmark._benchmark_macd(sample_data_small, 'numpy')
        
        # Should return a DataFrame with MACD columns
        assert isinstance(result, pd.DataFrame)
        expected_cols = {'macd', 'signal', 'histogram'}
        assert expected_cols.issubset(set(result.columns))
    
    def test_benchmark_atr_operation(self, sample_data_small):
        """Test ATR-specific benchmarking"""
        benchmark = PerformanceBenchmark()
        
        result = benchmark._benchmark_atr(sample_data_small, 'numpy')
        
        # Should return a DataFrame with ATR column
        assert isinstance(result, pd.DataFrame)
        assert 'atr' in result.columns
    
    def test_benchmark_error_handling(self, sample_data_small):
        """Test benchmark handles operation errors gracefully"""
        benchmark = PerformanceBenchmark()
        
        # Mock operation that raises an error
        def failing_operation(data, backend):
            raise RuntimeError("GPU memory error")
        
        # Should handle the error and record it
        result = benchmark.benchmark_operation(
            operation_func=failing_operation,
            data=sample_data_small,
            backend='cupy',
            runs=1
        )
        
        # Result should indicate the error
        assert 'error' in result
        assert result['backend'] == 'cupy'
    
    def test_performance_report_generation(self):
        """Test performance report generation"""
        benchmark = PerformanceBenchmark()
        
        # Add some mock results
        benchmark.results = {
            'MACD_1000': {
                'cpu': {'avg_time': 0.1, 'std_time': 0.01},
                'gpu': {'avg_time': 0.05, 'std_time': 0.005},
                'speedup': 2.0,
                'memory_ratio': 1.2
            },
            'ATR_1000': {
                'cpu': {'avg_time': 0.08, 'std_time': 0.008},
                'gpu': {'avg_time': 0.02, 'std_time': 0.002},
                'speedup': 4.0,
                'memory_ratio': 1.1
            }
        }
        
        report = benchmark.generate_performance_report()
        
        assert isinstance(report, str)
        assert 'Performance Benchmark Report' in report
        assert 'Summary' in report
        assert 'MACD' in report
        assert 'ATR' in report
        assert '2.00x speedup' in report or '2.0x speedup' in report
    
    def test_benchmark_memory_tracking(self, sample_data_small):
        """Test memory usage tracking during benchmarks"""
        benchmark = PerformanceBenchmark()
        
        # Mock memory tracking
        with patch.object(benchmark, '_get_memory_usage') as mock_memory:
            mock_memory.side_effect = [100, 150]  # Before and after
            
            def simple_operation(data, backend):
                return data.copy()
            
            result = benchmark.benchmark_operation(
                operation_func=simple_operation,
                data=sample_data_small,
                backend='numpy',
                runs=1
            )
            
            assert result['avg_memory'] == 50  # 150 - 100
    
    def test_speedup_calculation(self):
        """Test speedup calculation between backends"""
        benchmark = PerformanceBenchmark()
        
        # Mock benchmark results
        cpu_result = {'avg_time': 0.1, 'backend_available': True}
        gpu_result = {'avg_time': 0.025, 'backend_available': True}
        
        speedup = benchmark._calculate_speedup(cpu_result, gpu_result)
        
        assert speedup == 4.0  # 0.1 / 0.025
    
    def test_benchmark_with_different_parameters(self, sample_data_small):
        """Test benchmarking with different operation parameters"""
        benchmark = PerformanceBenchmark()
        
        # Test MACD with different parameters
        params = [
            {'fast': 12, 'slow': 26, 'signal': 9},
            {'fast': 5, 'slow': 10, 'signal': 3}
        ]
        
        for param_set in params:
            result = benchmark._benchmark_macd_with_params(
                sample_data_small, 'numpy', param_set
            )
            assert isinstance(result, pd.DataFrame)
            assert 'macd' in result.columns
    
    def test_benchmark_visualization_data(self):
        """Test data preparation for visualization"""
        benchmark = PerformanceBenchmark()
        
        # Add mock results
        benchmark.results = {
            'MACD_1000': {'speedup': 2.0, 'cpu': {'avg_time': 0.1}, 'gpu': {'avg_time': 0.05}},
            'MACD_5000': {'speedup': 3.0, 'cpu': {'avg_time': 0.5}, 'gpu': {'avg_time': 0.17}},
            'ATR_1000': {'speedup': 1.5, 'cpu': {'avg_time': 0.08}, 'gpu': {'avg_time': 0.053}}
        }
        
        viz_data = benchmark.prepare_visualization_data()
        
        assert isinstance(viz_data, dict)
        assert 'operations' in viz_data
        assert 'data_sizes' in viz_data
        assert 'speedups' in viz_data
        assert 'cpu_times' in viz_data
        assert 'gpu_times' in viz_data
    
    def test_benchmark_threshold_detection(self):
        """Test detection of GPU advantage threshold"""
        benchmark = PerformanceBenchmark()
        
        # Mock results showing GPU advantage kicks in at larger sizes
        benchmark.results = {
            'MACD_100': {'speedup': 0.8},    # GPU slower
            'MACD_1000': {'speedup': 1.2},   # GPU slightly faster
            'MACD_10000': {'speedup': 3.0},  # GPU much faster
        }
        
        threshold = benchmark.detect_gpu_advantage_threshold()
        
        assert threshold == 1000  # First size where speedup > 1.0
    
    def test_benchmark_configuration_validation(self):
        """Test benchmark configuration validation"""
        # Valid configuration
        config = {
            'runs': 5,
            'warmup_runs': 1,
            'data_sizes': [1000, 10000],
            'enable_memory_tracking': True
        }
        
        benchmark = PerformanceBenchmark(**config)
        assert benchmark.config['runs'] == 5
        
        # Invalid configuration
        with pytest.raises(ValueError, match="runs must be positive"):
            PerformanceBenchmark(runs=0)
    
    def test_benchmark_reproducibility(self, sample_data_small):
        """Test that benchmarks are reproducible with same data"""
        benchmark1 = PerformanceBenchmark(random_seed=42)
        benchmark2 = PerformanceBenchmark(random_seed=42)
        
        # Should produce same synthetic data
        data1 = benchmark1.generate_test_data(100)
        data2 = benchmark2.generate_test_data(100)
        
        pd.testing.assert_frame_equal(data1, data2)