"""
Test suite for EnhancedGPUCombinationProcessor - Phase 1.2.1 Implementation
Following TDD: Write failing tests first, then implement to pass.
"""

import pytest
import pandas as pd
import numpy as np
import time
from unittest.mock import Mock, patch, MagicMock

# This will fail initially - implementing TDD approach
try:
    from src.gpu_parallel_processing.enhanced_gpu_processor import EnhancedGPUCombinationProcessor
    from src.gpu_parallel_processing.advanced_memory_manager import AdvancedGPUMemoryPool
    HAS_ENHANCED_PROCESSOR = True
except ImportError:
    HAS_ENHANCED_PROCESSOR = False


class TestEnhancedGPUCombinationProcessor:
    """Test EnhancedGPUCombinationProcessor core functionality."""
    
    @pytest.fixture
    def sample_contract_data(self):
        """Create sample contract data for testing."""
        np.random.seed(42)
        dates = pd.date_range('2023-01-01', '2023-12-31', freq='1h')
        data = pd.DataFrame({
            'open': np.random.uniform(100, 200, len(dates)),
            'high': np.random.uniform(150, 250, len(dates)),
            'low': np.random.uniform(50, 150, len(dates)),
            'close': np.random.uniform(80, 180, len(dates)),
            'volume': np.random.uniform(1000, 10000, len(dates))
        }, index=dates)
        
        # Ensure OHLC relationships are valid
        data['high'] = np.maximum.reduce([data['open'], data['high'], data['close']])
        data['low'] = np.minimum.reduce([data['open'], data['low'], data['close']])
        
        return data
    
    @pytest.fixture
    def sample_combinations(self):
        """Create sample parameter combinations for testing."""
        return [
            {
                'combo_id': 'test_001',
                'contract': 'ES',
                'date_range': {'start': '2023-01-01', 'end': '2023-12-31'},
                'macd_params': {'short': 12, 'long': 26, 'signal': 9},
                'atr_lookback': 14,
                'bias_thresholds': {
                    'macd_line_lower': -0.5,
                    'macd_line_upper': 0.5,
                    'macd_histogram_lower': -0.3,
                    'macd_histogram_upper': 0.3
                },
                'strategy_thresholds': {
                    'neutral_buy': 0.1,
                    'neutral_sell': -0.1,
                    'strong_bullish_buy_adjust': 0.05,
                    'bullish_buy_adjust': 0.02,
                    'bearish_buy_adjust': -0.02,
                    'strong_bearish_sell_adjust': -0.05,
                    'bearish_sell_adjust': -0.02,
                    'bullish_sell_adjust': 0.02
                },
                'predictor_granularities': {'atr_macd': '1h'},
                'stop_loss': 0.02,
                'sl_tp_ratio': 2.0,
                'tp_value': 0.04
            },
            {
                'combo_id': 'test_002',
                'contract': 'ES',
                'date_range': {'start': '2023-01-01', 'end': '2023-12-31'},
                'macd_params': {'short': 8, 'long': 21, 'signal': 5},
                'atr_lookback': 20,
                'bias_thresholds': {
                    'macd_line_lower': -0.7,
                    'macd_line_upper': 0.7,
                    'macd_histogram_lower': -0.4,
                    'macd_histogram_upper': 0.4
                },
                'strategy_thresholds': {
                    'neutral_buy': 0.15,
                    'neutral_sell': -0.15,
                    'strong_bullish_buy_adjust': 0.08,
                    'bullish_buy_adjust': 0.03,
                    'bearish_buy_adjust': -0.03,
                    'strong_bearish_sell_adjust': -0.08,
                    'bearish_sell_adjust': -0.03,
                    'bullish_sell_adjust': 0.03
                },
                'predictor_granularities': {'atr_macd': '1h'},
                'stop_loss': 0.025,
                'sl_tp_ratio': 1.5,
                'tp_value': 0.0375
            }
        ]
    
    @pytest.fixture
    def enhanced_processor(self):
        """Create enhanced processor for testing."""
        if not HAS_ENHANCED_PROCESSOR:
            pytest.skip("Enhanced GPU Processor not available")
        return EnhancedGPUCombinationProcessor(
            gpu_memory_pool_gb=1.0,
            processing_chunk_size=100000
        )
    
    def test_enhanced_processor_initialization(self, enhanced_processor):
        """Test enhanced processor initializes correctly."""
        assert enhanced_processor.memory_pool is not None
        assert enhanced_processor.pipeline is not None
        assert enhanced_processor.processing_stats['combinations_processed'] == 0
        assert enhanced_processor.processing_stats['successful_combinations'] == 0
        assert enhanced_processor.processing_stats['failed_combinations'] == 0
    
    def test_process_single_combination(self, enhanced_processor, sample_contract_data, sample_combinations):
        """Test processing a single parameter combination."""
        combo = sample_combinations[0]
        
        # This should fail initially - no implementation yet
        results = enhanced_processor.process_contract_combinations_sustained(
            contract_data=sample_contract_data,
            combinations_batch=[combo],
            enable_memory_monitoring=True
        )
        
        assert len(results) == 1
        result = results[0]
        
        # Check result structure
        assert 'combo_id' in result
        assert 'result_data' in result
        assert 'metadata' in result
        assert result['combo_id'] == combo['combo_id']
        
        # Check metadata includes memory stats
        metadata = result['metadata']
        assert 'memory_stats' in metadata
        assert 'peak_memory_gb' in metadata['memory_stats']
        assert 'processing_memory_gb' in metadata['memory_stats']
        assert 'reuse_efficiency' in metadata['memory_stats']
    
    def test_process_multiple_combinations(self, enhanced_processor, sample_contract_data, sample_combinations):
        """Test processing multiple parameter combinations."""
        results = enhanced_processor.process_contract_combinations_sustained(
            contract_data=sample_contract_data,
            combinations_batch=sample_combinations,
            enable_memory_monitoring=True
        )
        
        assert len(results) == len(sample_combinations)
        
        # All results should have unique combo_ids
        combo_ids = [r['combo_id'] for r in results]
        assert len(set(combo_ids)) == len(combo_ids)
        
        # Check processing stats
        stats = enhanced_processor.get_processing_stats()
        assert stats['combinations_processed'] == len(sample_combinations)
        assert stats['successful_combinations'] <= len(sample_combinations)
    
    def test_memory_monitoring_integration(self, enhanced_processor, sample_contract_data, sample_combinations):
        """Test memory monitoring during processing."""
        # Process with memory monitoring enabled
        results = enhanced_processor.process_contract_combinations_sustained(
            contract_data=sample_contract_data,
            combinations_batch=sample_combinations[:1],
            enable_memory_monitoring=True
        )
        
        # Memory pool should track usage
        memory_stats = enhanced_processor.memory_pool.get_memory_stats()
        assert 'current_usage_gb' in memory_stats
        assert 'peak_usage_gb' in memory_stats
        assert memory_stats['total_allocations'] > 0
    
    def test_sustained_processing_capability(self, enhanced_processor, sample_contract_data):
        """Test sustained processing without memory errors."""
        # Create many combinations for sustained test
        combinations = []
        for i in range(50):  # Reduced for testing, real test would use 1000+
            combo = {
                'combo_id': f'sustained_test_{i:03d}',
                'contract': 'ES',
                'date_range': {'start': '2023-01-01', 'end': '2023-12-31'},
                'macd_params': {'short': 12 + (i % 10), 'long': 26 + (i % 15), 'signal': 9},
                'atr_lookback': 14 + (i % 5),
                'bias_thresholds': {
                    'macd_line_lower': -0.5,
                    'macd_line_upper': 0.5,
                    'macd_histogram_lower': -0.3,
                    'macd_histogram_upper': 0.3
                },
                'strategy_thresholds': {
                    'neutral_buy': 0.1,
                    'neutral_sell': -0.1,
                    'strong_bullish_buy_adjust': 0.05,
                    'bullish_buy_adjust': 0.02,
                    'bearish_buy_adjust': -0.02,
                    'strong_bearish_sell_adjust': -0.05,
                    'bearish_sell_adjust': -0.02,
                    'bullish_sell_adjust': 0.02
                },
                'predictor_granularities': {'atr_macd': '1h'},
                'stop_loss': 0.02,
                'sl_tp_ratio': 2.0,
                'tp_value': 0.04
            }
            combinations.append(combo)
        
        # Process all combinations - should not run out of memory
        results = enhanced_processor.process_contract_combinations_sustained(
            contract_data=sample_contract_data,
            combinations_batch=combinations,
            enable_memory_monitoring=True
        )
        
        # Should have processed most combinations successfully
        success_rate = len(results) / len(combinations)
        assert success_rate > 0.8  # 80% success rate minimum
        
        # Memory pressure events should be low
        stats = enhanced_processor.get_processing_stats()
        assert stats['memory_pressure_events'] < len(combinations) * 0.1  # <10% pressure events
    
    def test_memory_pressure_handling(self, enhanced_processor, sample_contract_data, sample_combinations):
        """Test memory pressure detection and handling."""
        # Mock memory pressure scenario
        with patch.object(enhanced_processor.memory_pool, 'get_array') as mock_get_array:
            # First call succeeds, second fails with memory error
            mock_get_array.side_effect = [
                Mock(),  # First allocation succeeds
                RuntimeError("out of memory")  # Second allocation fails
            ]
            
            # Process should handle memory pressure gracefully
            results = enhanced_processor.process_contract_combinations_sustained(
                contract_data=sample_contract_data,
                combinations_batch=sample_combinations,
                enable_memory_monitoring=True
            )
            
            # Should have attempted memory pressure handling
            stats = enhanced_processor.get_processing_stats()
            assert stats['memory_pressure_events'] > 0
    
    def test_parameter_conversion(self, enhanced_processor, sample_combinations):
        """Test legacy parameter conversion to ATS_3 format."""
        combo = sample_combinations[0]
        
        # This should fail initially - no implementation yet
        ats3_params = enhanced_processor._convert_legacy_parameters(combo)
        
        # Check MACD parameters conversion
        assert 'macd_params' in ats3_params
        macd_params = ats3_params['macd_params']
        assert macd_params['fast'] == combo['macd_params']['short']
        assert macd_params['slow'] == combo['macd_params']['long']
        assert macd_params['signal'] == combo['macd_params']['signal']
        
        # Check bias thresholds conversion
        assert 'bias_thresholds' in ats3_params
        bias_thresholds = ats3_params['bias_thresholds']
        assert hasattr(bias_thresholds, 'macd_line_lower')
        assert hasattr(bias_thresholds, 'macd_line_upper')
        
        # Check position thresholds conversion
        assert 'position_thresholds' in ats3_params
        position_thresholds = ats3_params['position_thresholds']
        assert hasattr(position_thresholds, 'neutral_buy')
        assert hasattr(position_thresholds, 'neutral_sell')
    
    def test_combination_validation(self, enhanced_processor, sample_combinations):
        """Test parameter combination validation."""
        valid_combo = sample_combinations[0]
        invalid_combo = valid_combo.copy()
        del invalid_combo['macd_params']  # Remove required field
        
        # Valid combination should pass
        assert enhanced_processor._validate_combination_parameters(valid_combo) is True
        
        # Invalid combination should fail
        assert enhanced_processor._validate_combination_parameters(invalid_combo) is False
        
        # Test MACD parameter validation
        invalid_macd_combo = valid_combo.copy()
        invalid_macd_combo['macd_params']['short'] = 30  # short >= long
        invalid_macd_combo['macd_params']['long'] = 26
        assert enhanced_processor._validate_combination_parameters(invalid_macd_combo) is False
    
    def test_processing_statistics(self, enhanced_processor, sample_contract_data, sample_combinations):
        """Test processing statistics collection."""
        # Process some combinations
        enhanced_processor.process_contract_combinations_sustained(
            contract_data=sample_contract_data,
            combinations_batch=sample_combinations,
            enable_memory_monitoring=True
        )
        
        # Get statistics
        stats = enhanced_processor.get_processing_stats()
        
        # Check required statistics fields
        required_fields = [
            'combinations_processed', 'successful_combinations', 'failed_combinations',
            'success_rate_percent', 'average_processing_time_seconds',
            'estimated_throughput_per_hour', 'memory_pressure_events', 'memory_stats'
        ]
        
        for field in required_fields:
            assert field in stats
        
        # Basic validation
        assert stats['combinations_processed'] >= 0
        assert stats['successful_combinations'] >= 0
        assert stats['failed_combinations'] >= 0
        assert 0 <= stats['success_rate_percent'] <= 100
    
    def test_cleanup_resources(self, enhanced_processor):
        """Test proper cleanup of processor resources."""
        # Processor should cleanup without errors
        enhanced_processor.cleanup()
        
        # Memory pool should be cleaned up
        # This is tested in the memory pool tests
        pass
    
    @patch('src.feature_engineering.unified_pipeline.UnifiedTechnicalIndicatorsPipeline')
    def test_pipeline_integration(self, mock_pipeline_class, enhanced_processor, sample_contract_data, sample_combinations):
        """Test integration with UnifiedTechnicalIndicatorsPipeline."""
        # Mock pipeline instance
        mock_pipeline = Mock()
        mock_pipeline.compute_all_indicators_features_bias_and_positions.return_value = pd.DataFrame({
            'feature_1': [1, 2, 3],
            'feature_2': [4, 5, 6]
        })
        mock_pipeline_class.return_value = mock_pipeline
        
        # Create new processor with mocked pipeline
        processor = EnhancedGPUCombinationProcessor(gpu_memory_pool_gb=1.0)
        processor.pipeline = mock_pipeline
        
        # Process combinations
        results = processor.process_contract_combinations_sustained(
            contract_data=sample_contract_data,
            combinations_batch=sample_combinations[:1],
            enable_memory_monitoring=False
        )
        
        # Pipeline should have been called
        assert mock_pipeline.compute_all_indicators_features_bias_and_positions.called
        assert len(results) == 1


if __name__ == "__main__":
    # Run tests to see failures (TDD approach)
    pytest.main([__file__, "-v"])