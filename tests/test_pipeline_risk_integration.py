"""
Test integration of ATRRiskCalculator with UnifiedTechnicalIndicatorsPipeline

Simple integration test to verify the pipeline can use the new risk management features.
"""

import pytest
import numpy as np
import pandas as pd

# Skip GPU tests if not available
try:
    from src.feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline
    PIPELINE_AVAILABLE = True
except (ImportError, RuntimeError) as e:
    PIPELINE_AVAILABLE = False
    SKIP_REASON = str(e)


@pytest.mark.skipif(not PIPELINE_AVAILABLE, reason=f"Pipeline not available: {SKIP_REASON if not PIPELINE_AVAILABLE else ''}")
class TestPipelineRiskIntegration:
    """Test ATR risk management integration with the unified pipeline"""
    
    def setup_method(self):
        """Setup pipeline for testing"""
        try:
            self.pipeline = UnifiedTechnicalIndicatorsPipeline()
            self.sample_data = self.create_sample_data()
        except Exception as e:
            pytest.skip(f"GPU pipeline not available: {e}")
    
    def create_sample_data(self):
        """Create sample OHLCV data for testing"""
        np.random.seed(42)  # For reproducible tests
        n_points = 100
        
        # Generate realistic price data
        base_price = 100.0
        price_changes = np.random.normal(0, 0.02, n_points)  # 2% volatility
        prices = base_price * np.cumprod(1 + price_changes)
        
        # Create OHLCV data
        data = pd.DataFrame({
            'open': prices * (1 + np.random.normal(0, 0.001, n_points)),
            'high': prices * (1 + np.abs(np.random.normal(0, 0.005, n_points))),
            'low': prices * (1 - np.abs(np.random.normal(0, 0.005, n_points))),
            'close': prices,
            'volume': np.random.randint(1000, 10000, n_points)
        })
        
        # Ensure high >= close >= low and high >= open >= low
        data['high'] = np.maximum(data['high'], np.maximum(data['open'], data['close']))
        data['low'] = np.minimum(data['low'], np.minimum(data['open'], data['close']))
        
        return data
    
    def test_pipeline_has_atr_risk_calculator(self):
        """Test that pipeline initializes with ATR risk calculator"""
        assert hasattr(self.pipeline, 'atr_risk_calculator')
        assert self.pipeline.atr_risk_calculator is not None
    
    def test_pipeline_basic_indicators_still_work(self):
        """Test that basic pipeline functionality still works"""
        result = self.pipeline.compute_all_indicators_and_features(self.sample_data)
        
        # Check that basic indicators are present
        expected_columns = ['open', 'high', 'low', 'close', 'volume', 'macd_line', 'atr']
        for col in expected_columns:
            assert col in result.columns, f"Missing expected column: {col}"
        
        assert len(result) == len(self.sample_data)
    
    def test_pipeline_stop_loss_distance_feature(self):
        """Test that pipeline can compute stop loss distance feature"""
        stop_loss_ratio = 0.5
        
        result = self.pipeline.compute_all_indicators_and_features(
            self.sample_data,
            stop_loss_ratio=stop_loss_ratio
        )
        
        # Check that stop loss distance feature is added
        assert 'stop_loss_distance' in result.columns
        
        # Verify the calculation is correct
        expected_distances = result['atr'] * stop_loss_ratio
        pd.testing.assert_series_equal(
            result['stop_loss_distance'], 
            expected_distances, 
            check_names=False
        )
    
    def test_pipeline_take_profit_distance_feature(self):
        """Test that pipeline can compute take profit distance feature"""
        stop_loss_ratio = 0.5
        sl_tp_ratio = 1.5
        
        result = self.pipeline.compute_all_indicators_and_features(
            self.sample_data,
            stop_loss_ratio=stop_loss_ratio,
            sl_tp_ratio=sl_tp_ratio
        )
        
        # Check that both distance features are added
        assert 'stop_loss_distance' in result.columns
        assert 'take_profit_distance' in result.columns
        
        # Verify the calculations are correct
        expected_stop_loss = result['atr'] * stop_loss_ratio
        expected_take_profit = result['atr'] * stop_loss_ratio * sl_tp_ratio
        
        pd.testing.assert_series_equal(
            result['stop_loss_distance'], 
            expected_stop_loss, 
            check_names=False
        )
        pd.testing.assert_series_equal(
            result['take_profit_distance'], 
            expected_take_profit, 
            check_names=False
        )
    
    def test_pipeline_risk_levels_long_position(self):
        """Test that pipeline can compute risk levels for long positions"""
        stop_loss_ratio = 0.5
        sl_tp_ratio = 1.5
        
        result = self.pipeline.compute_all_indicators_and_features(
            self.sample_data,
            stop_loss_ratio=stop_loss_ratio,
            sl_tp_ratio=sl_tp_ratio,
            position_type='long'
        )
        
        # Check that all risk features are added
        assert 'stop_loss_distance' in result.columns
        assert 'take_profit_distance' in result.columns
        assert 'stop_loss_level' in result.columns
        assert 'take_profit_level' in result.columns
        
        # Verify calculations for long positions
        # Long: stop_loss = close - distance, take_profit = close + distance
        expected_stop_loss_levels = (result['close'] - result['stop_loss_distance']).astype('float32')
        expected_take_profit_levels = (result['close'] + result['take_profit_distance']).astype('float32')
        
        pd.testing.assert_series_equal(
            result['stop_loss_level'], 
            expected_stop_loss_levels, 
            check_names=False
        )
        pd.testing.assert_series_equal(
            result['take_profit_level'], 
            expected_take_profit_levels, 
            check_names=False
        )
    
    def test_pipeline_risk_levels_short_position(self):
        """Test that pipeline can compute risk levels for short positions"""
        stop_loss_ratio = 0.5
        sl_tp_ratio = 1.5
        
        result = self.pipeline.compute_all_indicators_and_features(
            self.sample_data,
            stop_loss_ratio=stop_loss_ratio,
            sl_tp_ratio=sl_tp_ratio,
            position_type='short'
        )
        
        # Verify calculations for short positions
        # Short: stop_loss = close + distance, take_profit = close - distance
        expected_stop_loss_levels = (result['close'] + result['stop_loss_distance']).astype('float32')
        expected_take_profit_levels = (result['close'] - result['take_profit_distance']).astype('float32')
        
        pd.testing.assert_series_equal(
            result['stop_loss_level'], 
            expected_stop_loss_levels, 
            check_names=False
        )
        pd.testing.assert_series_equal(
            result['take_profit_level'], 
            expected_take_profit_levels, 
            check_names=False
        )
    
    def test_pipeline_custom_entry_price(self):
        """Test that pipeline can use custom entry prices"""
        stop_loss_ratio = 0.5
        sl_tp_ratio = 1.5
        custom_entry = 105.0  # Fixed entry price
        
        result = self.pipeline.compute_all_indicators_and_features(
            self.sample_data,
            stop_loss_ratio=stop_loss_ratio,
            sl_tp_ratio=sl_tp_ratio,
            entry_price=custom_entry,
            position_type='long'
        )
        
        # Verify calculations use custom entry price instead of close
        expected_stop_loss_levels = (custom_entry - result['stop_loss_distance']).astype('float32')
        expected_take_profit_levels = (custom_entry + result['take_profit_distance']).astype('float32')
        
        pd.testing.assert_series_equal(
            result['stop_loss_level'], 
            expected_stop_loss_levels, 
            check_names=False
        )
        pd.testing.assert_series_equal(
            result['take_profit_level'], 
            expected_take_profit_levels, 
            check_names=False
        )
    
    def test_pipeline_without_risk_parameters(self):
        """Test that pipeline works normally without risk parameters"""
        result = self.pipeline.compute_all_indicators_and_features(self.sample_data)
        
        # Risk features should not be present
        risk_columns = ['stop_loss_distance', 'take_profit_distance', 'stop_loss_level', 'take_profit_level']
        for col in risk_columns:
            assert col not in result.columns, f"Risk column {col} should not be present without parameters"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])