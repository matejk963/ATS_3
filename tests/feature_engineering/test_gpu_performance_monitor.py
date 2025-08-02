"""
Tests for GPU Performance Monitoring and Validation Tools
"""
import pytest
import numpy as np
import pandas as pd
from unittest.mock import Mock, patch, MagicMock
import time


class TestGPUUtilizationMonitor:
    """Test suite for GPU utilization monitoring functionality"""
    
    @patch('pynvml.nvmlInit')
    @patch('pynvml.nvmlDeviceGetHandleByIndex')
    def test_initialization(self, mock_get_handle, mock_init):
        """Test GPU utilization monitor initializes correctly"""
        from src.feature_engineering.gpu_performance_monitor import GPUUtilizationMonitor
        
        monitor = GPUUtilizationMonitor()
        
        assert monitor.gpu_handle is not None
        assert monitor.monitoring_active is False
        assert monitor.utilization_history == []
        mock_init.assert_called_once()
        mock_get_handle.assert_called_once_with(0)

    @patch('pynvml.nvmlDeviceGetUtilizationRates')
    @patch('pynvml.nvmlDeviceGetMemoryInfo')
    def test_get_real_time_stats(self, mock_memory, mock_util, setup_monitor):
        """Test real-time GPU statistics collection"""
        from src.feature_engineering.gpu_performance_monitor import GPUUtilizationMonitor
        
        # Mock GPU stats
        mock_util_rates = Mock()
        mock_util_rates.gpu = 75
        mock_util_rates.memory = 60
        mock_util.return_value = mock_util_rates
        
        mock_memory_info = Mock()
        mock_memory_info.used = 8000000000  # 8GB
        mock_memory_info.total = 17179869184  # 16GB
        mock_memory_info.free = 9179869184   # ~9GB
        mock_memory.return_value = mock_memory_info
        
        monitor = GPUUtilizationMonitor()
        monitor.gpu_handle = Mock()
        
        stats = monitor.get_real_time_stats()
        
        assert stats['core_utilization'] == 75.0
        assert stats['memory_utilization'] == 60.0
        assert abs(stats['memory_usage_percent'] - 46.5) < 0.1  # 8GB/17.2GB
        assert stats['memory_used_gb'] == 8.0
        assert stats['memory_free_gb'] > 9.0

    def test_start_monitoring_thread(self, setup_monitor):
        """Test monitoring thread starts and stops correctly"""
        from src.feature_engineering.gpu_performance_monitor import GPUUtilizationMonitor
        
        monitor = GPUUtilizationMonitor()
        monitor.get_real_time_stats = Mock(return_value={
            'core_utilization': 80.0,
            'memory_utilization': 70.0,
            'timestamp': time.time()
        })
        
        # Start monitoring
        monitor.start_monitoring(interval=0.1)
        assert monitor.monitoring_active is True
        
        # Let it collect some data
        time.sleep(0.3)
        
        # Stop monitoring
        monitor.stop_monitoring()
        assert monitor.monitoring_active is False
        
        # Verify data was collected
        assert len(monitor.utilization_history) > 0

    def test_calculate_average_utilization(self, setup_monitor):
        """Test average utilization calculation"""
        from src.feature_engineering.gpu_performance_monitor import GPUUtilizationMonitor
        
        monitor = GPUUtilizationMonitor()
        
        # Add mock data
        monitor.utilization_history = [
            {'core_utilization': 80.0, 'memory_utilization': 70.0, 'timestamp': time.time()},
            {'core_utilization': 85.0, 'memory_utilization': 75.0, 'timestamp': time.time()},
            {'core_utilization': 90.0, 'memory_utilization': 80.0, 'timestamp': time.time()}
        ]
        
        avg_stats = monitor.calculate_average_utilization()
        
        assert avg_stats['avg_core_utilization'] == 85.0
        assert avg_stats['avg_memory_utilization'] == 75.0
        assert avg_stats['peak_core_utilization'] == 90.0
        assert avg_stats['peak_memory_utilization'] == 80.0

    @pytest.fixture
    def setup_monitor(self):
        """Setup monitor with mocked GPU components"""
        with patch('pynvml.nvmlInit'), \
             patch('pynvml.nvmlDeviceGetHandleByIndex'):
            from src.feature_engineering.gpu_performance_monitor import GPUUtilizationMonitor
            return GPUUtilizationMonitor()


class TestGPUBenchmarkValidator:
    """Test suite for GPU benchmark validation"""
    
    def test_initialization(self):
        """Test GPU benchmark validator initializes correctly"""
        from src.feature_engineering.gpu_performance_monitor import GPUBenchmarkValidator
        
        validator = GPUBenchmarkValidator()
        
        assert validator.benchmark_results == []
        assert validator.performance_thresholds is not None

    def test_run_processing_benchmark(self, setup_validator):
        """Test GPU processing benchmark execution"""
        from src.feature_engineering.gpu_performance_monitor import GPUBenchmarkValidator
        
        validator = GPUBenchmarkValidator()
        
        # Mock the processing pipeline and monitor
        mock_processor = Mock()
        mock_processor.process_with_dynamic_batching.return_value = {
            'macd': np.random.random(50000),
            'atr': np.random.random(50000)
        }
        
        mock_monitor = Mock()
        mock_monitor.get_real_time_stats.return_value = {
            'core_utilization': 85.0,
            'memory_utilization': 70.0
        }
        
        # Create test data
        test_data = pd.DataFrame({
            'open': np.random.random(50000),
            'high': np.random.random(50000),
            'low': np.random.random(50000),
            'close': np.random.random(50000),
            'volume': np.random.randint(1000, 10000, 50000)
        })
        
        benchmark_result = validator.run_processing_benchmark(
            processor=mock_processor,
            monitor=mock_monitor,
            test_data=test_data,
            target_utilization=0.85
        )
        
        assert 'processing_time' in benchmark_result
        assert 'points_per_second' in benchmark_result
        assert 'avg_gpu_utilization' in benchmark_result
        assert 'target_achieved' in benchmark_result
        assert benchmark_result['data_points'] == 50000

    def test_validate_performance_meets_targets(self, setup_validator):
        """Test performance validation against targets"""
        from src.feature_engineering.gpu_performance_monitor import GPUBenchmarkValidator
        
        validator = GPUBenchmarkValidator()
        
        # Mock benchmark results
        benchmark = {
            'points_per_second': 1800,
            'avg_gpu_utilization': 87.0,
            'peak_gpu_utilization': 92.0,
            'processing_time': 27.8,
            'target_utilization': 85.0
        }
        
        validation = validator.validate_performance(benchmark)
        
        assert validation['meets_speed_target'] is True  # > 1500 points/sec
        assert validation['meets_utilization_target'] is True  # > 85%
        assert validation['overall_performance'] == 'EXCELLENT'
        assert 'recommendations' in validation

    def test_validate_performance_below_targets(self, setup_validator):
        """Test performance validation when below targets"""
        from src.feature_engineering.gpu_performance_monitor import GPUBenchmarkValidator
        
        validator = GPUBenchmarkValidator()
        
        # Mock poor performance results
        benchmark = {
            'points_per_second': 800,
            'avg_gpu_utilization': 45.0,
            'peak_gpu_utilization': 55.0,
            'processing_time': 62.5,
            'target_utilization': 85.0
        }
        
        validation = validator.validate_performance(benchmark)
        
        assert validation['meets_speed_target'] is False  # < 1500 points/sec
        assert validation['meets_utilization_target'] is False  # < 85%
        assert validation['overall_performance'] == 'NEEDS_OPTIMIZATION'
        assert len(validation['recommendations']) > 0

    @pytest.fixture
    def setup_validator(self):
        """Setup validator with mocked components"""
        from src.feature_engineering.gpu_performance_monitor import GPUBenchmarkValidator
        return GPUBenchmarkValidator()


class TestDynamicGPUDiagnostics:
    """Test suite for dynamic GPU diagnostics and reporting"""
    
    def test_initialization(self):
        """Test diagnostics tool initializes correctly"""
        from src.feature_engineering.gpu_performance_monitor import DynamicGPUDiagnostics
        
        diagnostics = DynamicGPUDiagnostics()
        
        assert diagnostics.monitor is not None
        assert diagnostics.validator is not None
        assert diagnostics.diagnostic_reports == []

    @patch('pynvml.nvmlDeviceGetMemoryInfo')
    @patch('pynvml.nvmlDeviceGetName')
    def test_run_comprehensive_analysis(self, mock_get_name, mock_get_memory, setup_diagnostics):
        """Test comprehensive GPU analysis execution"""
        from src.feature_engineering.gpu_performance_monitor import DynamicGPUDiagnostics
        
        # Mock GPU hardware calls
        mock_memory_info = Mock()
        mock_memory_info.total = 17179869184  # 16GB
        mock_memory_info.used = 5000000000   # 5GB
        mock_get_memory.return_value = mock_memory_info
        mock_get_name.return_value = b'RTX 4080 SUPER'
        
        diagnostics = DynamicGPUDiagnostics()
        
        # Mock the components
        diagnostics.monitor = Mock()
        diagnostics.monitor.gpu_handle = Mock()
        diagnostics.monitor.get_real_time_stats.return_value = {
            'core_utilization': 82.0,
            'memory_utilization': 68.0
        }
        diagnostics.monitor.calculate_average_utilization.return_value = {
            'avg_core_utilization': 80.0,
            'avg_memory_utilization': 65.0
        }
        
        diagnostics.validator = Mock()
        diagnostics.validator.run_processing_benchmark.return_value = {
            'points_per_second': 1650,
            'avg_gpu_utilization': 82.0,
            'processing_time': 30.3,
            'target_achieved': True
        }
        diagnostics.validator.validate_performance.return_value = {
            'overall_performance': 'EXCELLENT',
            'meets_speed_target': True,
            'meets_utilization_target': True,
            'recommendations': []
        }
        
        # Mock processor
        mock_processor = Mock()
        
        # Create test data
        test_data = pd.DataFrame({
            'close': np.random.random(25000),
            'high': np.random.random(25000),
            'low': np.random.random(25000)
        })
        
        analysis = diagnostics.run_comprehensive_analysis(
            processor=mock_processor,
            test_data=test_data,
            target_utilization=0.85,
            duration_seconds=1.0
        )
        
        assert 'hardware_info' in analysis
        assert 'performance_benchmark' in analysis
        assert 'validation_results' in analysis
        assert 'utilization_analysis' in analysis
        assert 'recommendations' in analysis

    def test_generate_optimization_report(self, setup_diagnostics):
        """Test optimization report generation"""
        from src.feature_engineering.gpu_performance_monitor import DynamicGPUDiagnostics
        
        diagnostics = DynamicGPUDiagnostics()
        
        # Mock analysis data
        analysis_data = {
            'performance_benchmark': {
                'points_per_second': 1800,
                'avg_gpu_utilization': 87.0,
                'processing_time': 27.8
            },
            'validation_results': {
                'overall_performance': 'EXCELLENT',
                'meets_speed_target': True,
                'meets_utilization_target': True
            },
            'utilization_analysis': {
                'avg_core_utilization': 85.0,
                'peak_core_utilization': 92.0
            },
            'recommendations': ['Consider increasing batch size for sustained load']
        }
        
        report = diagnostics.generate_optimization_report(analysis_data)
        
        assert 'performance_summary' in report
        assert 'optimization_opportunities' in report
        assert 'recommended_settings' in report
        assert report['performance_rating'] in ['EXCELLENT', 'GOOD', 'NEEDS_OPTIMIZATION']

    @pytest.fixture
    def setup_diagnostics(self):
        """Setup diagnostics with mocked components"""
        with patch('src.technical_indicators.gpu_performance_monitor.GPUUtilizationMonitor'), \
             patch('src.technical_indicators.gpu_performance_monitor.GPUBenchmarkValidator'):
            from src.feature_engineering.gpu_performance_monitor import DynamicGPUDiagnostics
            return DynamicGPUDiagnostics()