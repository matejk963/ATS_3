"""
Phase 1.2.1 Performance Tests - Sustained Processing & Memory Efficiency
Tests for advanced memory management and sustained combination processing.
"""

import pytest
import pandas as pd
import numpy as np
import time
from typing import List, Dict

try:
    from src.gpu_parallel_processing.enhanced_gpu_processor import EnhancedGPUCombinationProcessor
    from src.gpu_parallel_processing.advanced_memory_manager import AdvancedGPUMemoryPool
    HAS_GPU_PROCESSOR = True
except ImportError:
    HAS_GPU_PROCESSOR = False


class TestPhase121Performance:
    """Performance tests for Phase 1.2.1 implementation."""
    
    @pytest.fixture
    def large_contract_data(self):
        """Create larger contract data for performance testing."""
        np.random.seed(42)
        # Create 6 months of hourly data
        dates = pd.date_range('2023-01-01', '2023-06-30', freq='1h')
        
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
    
    def generate_test_combinations(self, count: int) -> List[Dict]:
        """Generate test parameter combinations."""
        combinations = []
        
        for i in range(count):
            combo = {
                'combo_id': f'perf_test_{i:04d}',
                'contract': 'ES',
                'date_range': {'start': '2023-01-01', 'end': '2023-06-30'},
                'macd_params': {
                    'short': 8 + (i % 12),  # Vary between 8-19
                    'long': 21 + (i % 20),  # Vary between 21-40
                    'signal': 5 + (i % 10)  # Vary between 5-14
                },
                'atr_lookback': 10 + (i % 20),  # Vary between 10-29
                'bias_thresholds': {
                    'macd_line_lower': -0.5 - (i % 5) * 0.1,
                    'macd_line_upper': 0.5 + (i % 5) * 0.1,
                    'macd_histogram_lower': -0.3 - (i % 3) * 0.1,
                    'macd_histogram_upper': 0.3 + (i % 3) * 0.1
                },
                'strategy_thresholds': {
                    'neutral_buy': 0.1 + (i % 5) * 0.02,
                    'neutral_sell': -0.1 - (i % 5) * 0.02,
                    'strong_bullish_buy_adjust': 0.05 + (i % 3) * 0.01,
                    'bullish_buy_adjust': 0.02 + (i % 3) * 0.005,
                    'bearish_buy_adjust': -0.02 - (i % 3) * 0.005,
                    'strong_bearish_sell_adjust': -0.05 - (i % 3) * 0.01,
                    'bearish_sell_adjust': -0.02 - (i % 3) * 0.005,
                    'bullish_sell_adjust': 0.02 + (i % 3) * 0.005
                },
                'predictor_granularities': {'atr_macd': '1h'},
                'stop_loss': 0.02 + (i % 3) * 0.005,
                'sl_tp_ratio': 1.5 + (i % 4) * 0.25,
                'tp_value': 0.03 + (i % 4) * 0.0075
            }
            combinations.append(combo)
        
        return combinations
    
    @pytest.mark.skipif(not HAS_GPU_PROCESSOR, reason="GPU processor not available")
    def test_sustained_processing_100_combinations(self, large_contract_data):
        """Test sustained processing of 100 combinations."""
        processor = EnhancedGPUCombinationProcessor(
            gpu_memory_pool_gb=2.0,  # Smaller pool for testing
            processing_chunk_size=500000
        )
        
        try:
            # Generate 100 test combinations
            combinations = self.generate_test_combinations(100)
            
            # Process all combinations
            start_time = time.time()
            results = processor.process_contract_combinations_sustained(
                contract_data=large_contract_data,
                combinations_batch=combinations,
                enable_memory_monitoring=True
            )
            processing_time = time.time() - start_time
            
            # Validate results
            assert len(results) > 80, f"Expected >80 successful results, got {len(results)}"
            
            # Get processing statistics
            stats = processor.get_processing_stats()
            
            # Performance assertions
            assert stats['combinations_processed'] == 100
            assert stats['success_rate_percent'] > 80, f"Success rate {stats['success_rate_percent']:.1f}% too low"
            assert stats['memory_pressure_events'] < 10, f"Too many memory pressure events: {stats['memory_pressure_events']}"
            assert processing_time < 300, f"Processing took too long: {processing_time:.1f}s"  # <5 minutes
            
            # Memory efficiency assertions
            memory_stats = stats['memory_stats']
            assert memory_stats['reuse_efficiency_percent'] > 50, f"Memory reuse efficiency too low: {memory_stats['reuse_efficiency_percent']:.1f}%"
            
            print(f"✅ 100 combinations processed successfully:")
            print(f"   Success rate: {stats['success_rate_percent']:.1f}%")
            print(f"   Processing time: {processing_time:.1f}s")
            print(f"   Memory reuse efficiency: {memory_stats['reuse_efficiency_percent']:.1f}%")
            print(f"   Memory pressure events: {stats['memory_pressure_events']}")
            
        finally:
            processor.cleanup()
    
    @pytest.mark.skipif(not HAS_GPU_PROCESSOR, reason="GPU processor not available")
    def test_memory_reuse_efficiency(self, large_contract_data):
        """Test memory reuse efficiency with repeated similar operations."""
        processor = EnhancedGPUCombinationProcessor(
            gpu_memory_pool_gb=1.5,
            processing_chunk_size=200000
        )
        
        try:
            # Generate combinations with similar shapes to test reuse
            combinations = []
            for i in range(20):
                # Use same MACD params to encourage reuse
                combo = {
                    'combo_id': f'reuse_test_{i:03d}',
                    'contract': 'ES',
                    'date_range': {'start': '2023-01-01', 'end': '2023-06-30'},
                    'macd_params': {'short': 12, 'long': 26, 'signal': 9},  # Same for all
                    'atr_lookback': 14,  # Same for all
                    'bias_thresholds': {
                        'macd_line_lower': -0.5,
                        'macd_line_upper': 0.5,
                        'macd_histogram_lower': -0.3,
                        'macd_histogram_upper': 0.3
                    },
                    'strategy_thresholds': {
                        'neutral_buy': 0.1 + i * 0.01,  # Slight variation
                        'neutral_sell': -0.1 - i * 0.01,
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
            
            # Process combinations
            results = processor.process_contract_combinations_sustained(
                contract_data=large_contract_data,
                combinations_batch=combinations,
                enable_memory_monitoring=True
            )
            
            # Check memory reuse efficiency
            stats = processor.get_processing_stats()
            memory_stats = stats['memory_stats']
            
            # With similar operations, reuse efficiency should be high
            assert memory_stats['reuse_efficiency_percent'] > 70, \
                f"Memory reuse efficiency {memory_stats['reuse_efficiency_percent']:.1f}% below 70% target"
            
            print(f"✅ Memory reuse efficiency test passed:")
            print(f"   Reuse efficiency: {memory_stats['reuse_efficiency_percent']:.1f}%")
            print(f"   Successful reuses: {memory_stats['successful_reuses']}")
            print(f"   Total allocations: {memory_stats['total_allocations']}")
            
        finally:
            processor.cleanup()
    
    @pytest.mark.skipif(not HAS_GPU_PROCESSOR, reason="GPU processor not available")
    def test_memory_fragmentation_handling(self, large_contract_data):
        """Test memory fragmentation detection and handling."""
        processor = EnhancedGPUCombinationProcessor(
            gpu_memory_pool_gb=1.0,  # Small pool to force fragmentation
            processing_chunk_size=100000
        )
        
        try:
            # Generate combinations with varying data sizes to create fragmentation
            combinations = []
            for i in range(30):
                combo = {
                    'combo_id': f'frag_test_{i:03d}',
                    'contract': 'ES',
                    'date_range': {'start': '2023-01-01', 'end': '2023-06-30'},
                    'macd_params': {
                        'short': 8 + (i % 10),
                        'long': 21 + (i % 15),
                        'signal': 5 + (i % 8)
                    },
                    'atr_lookback': 10 + (i % 20),
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
            
            # Process combinations
            results = processor.process_contract_combinations_sustained(
                contract_data=large_contract_data,
                combinations_batch=combinations,
                enable_memory_monitoring=True
            )
            
            # Check fragmentation handling
            stats = processor.get_processing_stats()
            memory_stats = stats['memory_stats']
            
            # Should have handled fragmentation without major issues
            assert stats['success_rate_percent'] > 70, \
                f"Success rate {stats['success_rate_percent']:.1f}% too low with fragmentation"
            assert memory_stats['fragmentation_ratio'] < 0.5, \
                f"Fragmentation ratio {memory_stats['fragmentation_ratio']:.2f} too high"
            
            print(f"✅ Fragmentation handling test passed:")
            print(f"   Success rate: {stats['success_rate_percent']:.1f}%")
            print(f"   Final fragmentation ratio: {memory_stats['fragmentation_ratio']:.2f}")
            print(f"   Defragmentation events: {memory_stats['defragmentation_count']}")
            
        finally:
            processor.cleanup()
    
    @pytest.mark.skipif(not HAS_GPU_PROCESSOR, reason="GPU processor not available")
    def test_memory_pool_statistics_accuracy(self):
        """Test accuracy of memory pool statistics."""
        memory_pool = AdvancedGPUMemoryPool(max_pool_size_gb=0.5)
        
        try:
            # Allocate several arrays
            arrays = []
            for i in range(10):
                shape = (1000 + i * 100, 5)
                arr = memory_pool.get_array(shape, 'float32')
                arrays.append(arr)
            
            # Check statistics
            stats = memory_pool.get_memory_stats()
            assert stats['total_allocations'] == 10
            assert stats['allocated_blocks_count'] == 10
            assert stats['current_usage_gb'] > 0
            
            # Return half the arrays
            for arr in arrays[:5]:
                memory_pool.return_array(arr)
            
            # Check updated statistics
            stats = memory_pool.get_memory_stats()
            assert stats['total_deallocations'] == 5
            assert stats['allocated_blocks_count'] == 5
            assert stats['free_blocks_count'] == 5
            
            # Reuse arrays
            for i in range(3):
                new_arr = memory_pool.get_array((1000, 5), 'float32')
                arrays.append(new_arr)
            
            # Check reuse statistics
            stats = memory_pool.get_memory_stats()
            assert stats['successful_reuses'] > 0
            assert stats['reuse_efficiency_percent'] > 0
            
            print(f"✅ Memory statistics accuracy test passed:")
            print(f"   Total allocations: {stats['total_allocations']}")
            print(f"   Successful reuses: {stats['successful_reuses']}")
            print(f"   Reuse efficiency: {stats['reuse_efficiency_percent']:.1f}%")
            
        finally:
            memory_pool.cleanup()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])