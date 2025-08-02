"""
Enhanced GPU Combination Processor with advanced memory management
for sustained high-throughput parameter combination processing.
"""

import time
import pandas as pd
from typing import List, Dict, Optional
from .advanced_memory_manager import AdvancedGPUMemoryPool
from src.feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline
from src.feature_engineering.bias_classifier import ThresholdConfig as BiasThresholdConfig
from src.feature_engineering.position_generator import ThresholdConfig as PositionThresholdConfig

class EnhancedGPUCombinationProcessor:
    """
    Enhanced GPU processor with advanced memory management for
    sustained processing of massive parameter combinations.
    """
    
    def __init__(self, 
                 gpu_memory_pool_gb: float = 14.0,
                 processing_chunk_size: int = 2000000):
        """
        Initialize enhanced processor with memory management.
        
        Args:
            gpu_memory_pool_gb: GPU memory pool size
            processing_chunk_size: Chunk size for pipeline processing
        """
        # Initialize advanced memory pool
        self.memory_pool = AdvancedGPUMemoryPool(
            max_pool_size_gb=gpu_memory_pool_gb,
            fragmentation_threshold=0.25
        )
        
        # Initialize pipeline with memory-aware settings
        self.pipeline = UnifiedTechnicalIndicatorsPipeline(
            chunk_size=processing_chunk_size,
            memory_threshold=0.92  # Leave room for memory pool
        )
        
        # Processing statistics
        self.processing_stats = {
            'combinations_processed': 0,
            'total_processing_time': 0.0,
            'memory_pressure_events': 0,
            'successful_combinations': 0,
            'failed_combinations': 0
        }
        
        print(f"🚀 Enhanced GPU Processor initialized with {gpu_memory_pool_gb:.1f}GB memory pool")
    
    def process_contract_combinations_sustained(self,
                                              contract_data: pd.DataFrame,
                                              combinations_batch: List[Dict],
                                              enable_memory_monitoring: bool = True) -> List[Dict]:
        """
        Process combinations with sustained memory management.
        
        Args:
            contract_data: Contract OHLCV data
            combinations_batch: Parameter combinations to process
            enable_memory_monitoring: Whether to monitor memory during processing
            
        Returns:
            List of processing results with metadata
        """
        results = []
        batch_start_time = time.time()
        
        print(f"🔄 Processing batch: {len(combinations_batch)} combinations")
        
        for i, combo in enumerate(combinations_batch):
            combo_start_time = time.time()
            
            try:
                # Memory monitoring before processing
                if enable_memory_monitoring:
                    self._monitor_memory_before_processing()
                
                # Convert parameters and validate
                ats3_params = self._convert_legacy_parameters(combo)
                if not self._validate_combination_parameters(combo):
                    print(f"⚠️  Skipping invalid combination {combo['combo_id']}")
                    self.processing_stats['failed_combinations'] += 1
                    continue
                
                # Process with memory-managed pipeline
                result_data = self._process_combination_with_memory_management(
                    contract_data, combo, ats3_params
                )
                
                # Create result with metadata
                result = self._create_result_with_memory_stats(combo, result_data)
                results.append(result)
                
                # Update statistics
                combo_time = time.time() - combo_start_time
                self.processing_stats['combinations_processed'] += 1
                self.processing_stats['successful_combinations'] += 1  
                self.processing_stats['total_processing_time'] += combo_time
                
                # Progress reporting
                if (i + 1) % 10 == 0:
                    progress = (i + 1) / len(combinations_batch) * 100
                    avg_time = combo_time
                    eta_minutes = (len(combinations_batch) - i - 1) * avg_time / 60
                    
                    print(f"📊 Progress: {progress:.1f}% ({i+1}/{len(combinations_batch)}) "
                          f"| Avg: {avg_time:.2f}s | ETA: {eta_minutes:.1f}min")
                    
                    # Memory stats
                    if enable_memory_monitoring:
                        memory_stats = self.memory_pool.get_memory_stats()
                        print(f"💾 Memory: {memory_stats['utilization_percent']:.1f}% used, "
                              f"{memory_stats['reuse_efficiency_percent']:.1f}% reuse efficiency")
                
            except Exception as e:
                combo_time = time.time() - combo_start_time
                self.processing_stats['failed_combinations'] += 1
                self.processing_stats['total_processing_time'] += combo_time
                
                print(f"❌ Combination {combo['combo_id']} failed after {combo_time:.2f}s: {e}")
                
                # Handle memory pressure
                if "out of memory" in str(e).lower():
                    self.processing_stats['memory_pressure_events'] += 1
                    self._handle_memory_pressure()
                
                continue
        
        batch_time = time.time() - batch_start_time
        success_rate = (self.processing_stats['successful_combinations'] / 
                       len(combinations_batch) * 100) if combinations_batch else 0
        
        print(f"✅ Batch complete: {len(results)} successful, {success_rate:.1f}% success rate, "
              f"{batch_time:.1f}s total")
        
        return results
    
    def _process_combination_with_memory_management(self,
                                                  contract_data: pd.DataFrame,
                                                  combo: Dict,
                                                  ats3_params: Dict) -> pd.DataFrame:
        """Process single combination with memory management."""
        
        # Pre-allocate arrays for processing if possible
        data_shape = (len(contract_data), 5)  # OHLCV
        
        try:
            # Get managed arrays for intermediate processing
            temp_array = self.memory_pool.get_array(data_shape, 'float32')
            
            # Process through pipeline
            result_data = self.pipeline.compute_all_indicators_features_bias_and_positions(
                data=contract_data,
                candle_granularity=combo['predictor_granularities']['atr_macd'],
                macd_params=ats3_params['macd_params'],
                atr_period=combo['atr_lookback'],
                bias_thresholds=ats3_params['bias_thresholds'],
                position_thresholds=ats3_params['position_thresholds']
            )
            
            # Return temporary array to pool
            self.memory_pool.return_array(temp_array)
            
            return result_data
            
        except Exception as e:
            # Ensure array is returned even on failure
            if 'temp_array' in locals():
                self.memory_pool.return_array(temp_array)
            raise e
    
    def _monitor_memory_before_processing(self) -> None:
        """Monitor memory state before processing combination."""
        memory_stats = self.memory_pool.get_memory_stats()
        
        # Warn if memory utilization is high
        if memory_stats['utilization_percent'] > 85:
            print(f"⚠️  High memory usage: {memory_stats['utilization_percent']:.1f}%")
        
        # Trigger cleanup if fragmentation is high
        if memory_stats['fragmentation_ratio'] > 0.3:
            print(f"🔧 High fragmentation detected: {memory_stats['fragmentation_ratio']:.2f}")
    
    def _handle_memory_pressure(self) -> None:
        """Handle memory pressure situations."""
        print("🚨 Handling memory pressure...")
        
        # Get current memory stats
        memory_stats = self.memory_pool.get_memory_stats()
        print(f"💾 Before cleanup: {memory_stats['utilization_percent']:.1f}% used")
        
        # Force memory cleanup
        import gc
        import cupy as cp
        
        gc.collect()
        cp.get_default_memory_pool().free_all_blocks() 
        
        # Wait for cleanup to complete
        time.sleep(1)
        
        # Check results
        memory_stats = self.memory_pool.get_memory_stats()
        print(f"✅ After cleanup: {memory_stats['utilization_percent']:.1f}% used")
    
    def _convert_legacy_parameters(self, legacy_combo: Dict) -> Dict:
        """Convert legacy parameters to ATS_3 format (from Phase 1)."""
        macd_params = {
            'fast': legacy_combo['macd_params']['short'],
            'slow': legacy_combo['macd_params']['long'], 
            'signal': legacy_combo['macd_params']['signal']
        }
        
        bias_thresholds = BiasThresholdConfig(
            macd_line_lower=legacy_combo['bias_thresholds']['macd_line_lower'],
            macd_line_upper=legacy_combo['bias_thresholds']['macd_line_upper'],
            macd_histogram_lower=legacy_combo['bias_thresholds']['macd_histogram_lower'],
            macd_histogram_upper=legacy_combo['bias_thresholds']['macd_histogram_upper']
        )
        
        strategy = legacy_combo['strategy_thresholds']
        position_thresholds = PositionThresholdConfig(
            strong_bullish_buy=strategy['neutral_buy'] + strategy['strong_bullish_buy_adjust'],
            bullish_buy=strategy['neutral_buy'] + strategy['bullish_buy_adjust'],
            neutral_buy=strategy['neutral_buy'],
            bearish_buy=strategy['neutral_buy'] + strategy['bearish_buy_adjust'],
            strong_bearish_sell=strategy['neutral_sell'] + strategy['strong_bearish_sell_adjust'],
            bearish_sell=strategy['neutral_sell'] + strategy['bearish_sell_adjust'],
            neutral_sell=strategy['neutral_sell'],
            bullish_sell=strategy['neutral_sell'] + strategy['bullish_sell_adjust']
        )
        
        return {
            'macd_params': macd_params,
            'bias_thresholds': bias_thresholds,
            'position_thresholds': position_thresholds
        }
    
    def _validate_combination_parameters(self, combo: Dict) -> bool:
        """Validate combination parameters (from Phase 1)."""
        required_keys = [
            'combo_id', 'contract', 'macd_params', 'atr_lookback',
            'bias_thresholds', 'strategy_thresholds', 'predictor_granularities'
        ]
        
        for key in required_keys:
            if key not in combo:
                return False
        
        macd = combo['macd_params']
        if not all(isinstance(macd[k], int) and macd[k] > 0 for k in ['short', 'long', 'signal']):
            return False
        
        if macd['short'] >= macd['long']:
            return False
        
        return True
    
    def _create_result_with_memory_stats(self, combo: Dict, result_data: pd.DataFrame) -> Dict:
        """Create result with memory statistics."""
        memory_stats = self.memory_pool.get_memory_stats()
        
        return {
            'combo_id': combo['combo_id'],
            'result_data': result_data,
            'metadata': {
                'contract': combo['contract'],
                'date_range': combo['date_range'],
                'predictor_granularities': combo['predictor_granularities'],
                'macd_params': combo['macd_params'],
                'atr_lookback': combo['atr_lookback'],
                'bias_thresholds': combo['bias_thresholds'],
                'strategy_thresholds': combo['strategy_thresholds'],
                'stop_loss': combo['stop_loss'],
                'sl_tp_ratio': combo['sl_tp_ratio'],
                'tp_value': combo['tp_value'],
                'memory_stats': {
                    'peak_memory_gb': memory_stats['peak_usage_gb'],
                    'processing_memory_gb': memory_stats['current_usage_gb'],
                    'reuse_efficiency': memory_stats['reuse_efficiency_percent']
                }
            }
        }
    
    def get_processing_stats(self) -> Dict:
        """Get comprehensive processing statistics."""
        memory_stats = self.memory_pool.get_memory_stats()
        
        avg_processing_time = (self.processing_stats['total_processing_time'] / 
                             max(1, self.processing_stats['combinations_processed']))
        
        return {
            'combinations_processed': self.processing_stats['combinations_processed'],
            'successful_combinations': self.processing_stats['successful_combinations'],
            'failed_combinations': self.processing_stats['failed_combinations'],
            'success_rate_percent': (self.processing_stats['successful_combinations'] / 
                                   max(1, self.processing_stats['combinations_processed']) * 100),
            'average_processing_time_seconds': avg_processing_time,
            'estimated_throughput_per_hour': 3600 / avg_processing_time if avg_processing_time > 0 else 0,
            'memory_pressure_events': self.processing_stats['memory_pressure_events'],
            'memory_stats': memory_stats
        }
    
    def cleanup(self) -> None:
        """Clean up processor resources."""
        print("🛑 Cleaning up Enhanced GPU Processor...")
        self.memory_pool.cleanup()
        print("✅ Enhanced GPU Processor cleanup complete")