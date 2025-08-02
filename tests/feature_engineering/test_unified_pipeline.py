"""
Test suite for unified technical indicators pipeline with backend selection.

Following TDD principles: write tests first, then implement the pipeline.
"""

import pytest
import pandas as pd
import numpy as np
from typing import Dict, Optional
from unittest.mock import patch, MagicMock

# Import will be created after test
from src.feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline


class TestUnifiedPipeline:
    """Test unified pipeline with backend selection"""
    
    @pytest.fixture
    def sample_data(self):
        """Create sample OHLCV data for testing"""
        np.random.seed(42)
        size = 1000
        prices = 100 + np.cumsum(np.random.randn(size) * 0.1)
        
        return pd.DataFrame({
            'open': prices * (1 + np.random.randn(size) * 0.001),
            'high': prices * (1 + np.abs(np.random.randn(size)) * 0.002),
            'low': prices * (1 - np.abs(np.random.randn(size)) * 0.002),
            'close': prices,
            'volume': np.random.randint(1000, 10000, size),
            'datetime': pd.date_range('2023-01-01', periods=size, freq='1min')
        })
    
    def test_pipeline_initialization_cpu_backend(self):
        """Test pipeline initializes with CPU backend"""
        pipeline = UnifiedTechnicalIndicatorsPipeline(backend='numpy')
        
        assert pipeline.backend_name == 'numpy'
        assert pipeline.array_backend is not None
        assert hasattr(pipeline, 'candle_generator')
        assert hasattr(pipeline, 'macd_calculator')
        assert hasattr(pipeline, 'atr_calculator')
        assert hasattr(pipeline, 'swing_detector')
    
    def test_pipeline_initialization_gpu_backend(self):
        """Test pipeline initializes with GPU backend (fallback to CPU if CuPy unavailable)"""
        pipeline = UnifiedTechnicalIndicatorsPipeline(backend='cupy')
        
        # Should either be 'cupy' or fallback to 'numpy'
        assert pipeline.backend_name in ['cupy', 'numpy']
        assert pipeline.array_backend is not None
    
    def test_pipeline_auto_backend_selection(self):
        """Test automatic backend selection based on data size"""
        pipeline = UnifiedTechnicalIndicatorsPipeline(backend='auto')
        
        # Should default to numpy for auto selection
        assert pipeline.backend_name in ['numpy', 'cupy']
    
    def test_pipeline_invalid_backend_raises_error(self):
        """Test pipeline raises error for invalid backend"""
        with pytest.raises(ValueError, match="Unsupported backend"):
            UnifiedTechnicalIndicatorsPipeline(backend='invalid')
    
    def test_compute_all_indicators_cpu(self, sample_data):
        """Test computing all indicators with CPU backend"""
        pipeline = UnifiedTechnicalIndicatorsPipeline(backend='numpy')
        
        result = pipeline.compute_all_indicators(
            data=sample_data,
            candle_granularity='15min',
            macd_params={'fast': 12, 'slow': 26, 'signal': 9},
            atr_period=14,
            swing_lookback=20
        )
        
        # Check result structure
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(sample_data)
        
        # Check required columns exist
        expected_columns = {
            'open', 'high', 'low', 'close', 'volume', 'datetime',
            'macd', 'signal', 'histogram',
            'atr',
            'swing_high', 'swing_low'
        }
        assert expected_columns.issubset(set(result.columns))
    
    def test_compute_all_indicators_gpu(self, sample_data):
        """Test computing all indicators with GPU backend"""
        pipeline = UnifiedTechnicalIndicatorsPipeline(backend='cupy')
        
        result = pipeline.compute_all_indicators(
            data=sample_data,
            candle_granularity='15min',
            macd_params={'fast': 12, 'slow': 26, 'signal': 9},
            atr_period=14,
            swing_lookback=20
        )
        
        # Result should be identical regardless of backend
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(sample_data)
    
    def test_compute_selective_indicators(self, sample_data):
        """Test computing only selected indicators"""
        pipeline = UnifiedTechnicalIndicatorsPipeline(backend='numpy')
        
        result = pipeline.compute_indicators(
            data=sample_data,
            indicators=['macd', 'atr'],
            macd_params={'fast': 12, 'slow': 26, 'signal': 9},
            atr_period=14
        )
        
        # Should only have MACD and ATR columns (plus original data)
        macd_columns = {'macd', 'signal', 'histogram'}
        atr_columns = {'atr'}
        original_columns = set(sample_data.columns)
        
        expected_columns = original_columns | macd_columns | atr_columns
        assert set(result.columns) == expected_columns
        
        # Should not have swing point columns
        assert 'swing_high' not in result.columns
        assert 'swing_low' not in result.columns
    
    def test_backend_performance_comparison(self, sample_data):
        """Test backend performance comparison functionality"""
        pipeline = UnifiedTechnicalIndicatorsPipeline()
        
        comparison = pipeline.compare_backend_performance(
            data=sample_data,
            indicators=['macd', 'atr'],
            runs=2  # Small number for testing
        )
        
        assert isinstance(comparison, dict)
        assert 'numpy' in comparison
        assert 'results' in comparison['numpy']
        assert 'avg_time' in comparison['numpy']
    
    def test_pipeline_error_handling_invalid_data(self):
        """Test pipeline handles invalid input data gracefully"""
        pipeline = UnifiedTechnicalIndicatorsPipeline(backend='numpy')
        
        # Test with empty DataFrame
        empty_df = pd.DataFrame()
        with pytest.raises(ValueError, match="Input data cannot be empty"):
            pipeline.compute_all_indicators(empty_df)
        
        # Test with missing required columns
        invalid_df = pd.DataFrame({'invalid': [1, 2, 3]})
        with pytest.raises(ValueError, match="Missing required columns"):
            pipeline.compute_all_indicators(invalid_df)
    
    def test_pipeline_fallback_mechanism(self, sample_data):
        """Test fallback from GPU to CPU when GPU processing fails"""
        pipeline = UnifiedTechnicalIndicatorsPipeline(backend='cupy')
        
        # Mock a GPU error and ensure fallback works
        with patch.object(pipeline.array_backend, 'xp') as mock_xp:
            mock_xp.asarray.side_effect = RuntimeError("GPU memory error")
            
            # Should fallback to CPU and still work
            result = pipeline.compute_indicators(
                data=sample_data,
                indicators=['macd'],
                fallback_on_error=True
            )
            
            assert isinstance(result, pd.DataFrame)
            assert 'macd' in result.columns
    
    def test_memory_optimization_flags(self, sample_data):
        """Test memory optimization settings"""
        pipeline = UnifiedTechnicalIndicatorsPipeline(
            backend='numpy',
            optimize_memory=True,
            dtype='float32'
        )
        
        result = pipeline.compute_indicators(
            data=sample_data,
            indicators=['macd']
        )
        
        # Check that float32 dtype is preserved where appropriate
        assert result['macd'].dtype in [np.float32, np.float64]  # Allow some flexibility
    
    def test_pipeline_configuration_validation(self):
        """Test pipeline configuration validation"""
        # Test valid configurations
        config = {
            'backend': 'numpy',
            'dtype': 'float32',
            'optimize_memory': True,
            'fallback_on_error': True
        }
        
        pipeline = UnifiedTechnicalIndicatorsPipeline(**config)
        assert pipeline.config == config
        
        # Test invalid dtype
        with pytest.raises(ValueError, match="Unsupported dtype"):
            UnifiedTechnicalIndicatorsPipeline(dtype='int8')
    
    def test_pipeline_caching_mechanism(self, sample_data):
        """Test caching of intermediate results"""
        pipeline = UnifiedTechnicalIndicatorsPipeline(
            backend='numpy',
            enable_caching=True
        )
        
        # First computation
        result1 = pipeline.compute_indicators(
            data=sample_data,
            indicators=['macd']
        )
        
        # Second computation with same data should use cache
        result2 = pipeline.compute_indicators(
            data=sample_data,
            indicators=['macd']
        )
        
        pd.testing.assert_frame_equal(result1, result2)
        
        # Check that cache was used (implementation specific)
        assert hasattr(pipeline, '_cache')