"""
Phase 4 Integration Tests - Complete Pipeline Validation
Tests Phase 3 (indicators) + Phase 4 (feature engineering) integration

EXACT ATS_2 Legacy Validation:
- Complete pipeline produces legacy feature names and formulas
- Performance maintains Phase 3 optimization levels
- Integration preserves all Phase 3 outputs
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch

from src.feature_engineering.unified_pipeline import UnifiedTechnicalIndicatorsPipeline


class TestPhase4Integration:
    """Test complete Phase 3 + Phase 4 pipeline integration"""
    
    def setup_method(self):
        """Setup test data and pipeline"""
        # Create sample market data
        np.random.seed(42)  # For reproducible tests
        n_points = 1000
        
        self.test_data = pd.DataFrame({
            'open': 100 + np.cumsum(np.random.randn(n_points) * 0.1),
            'high': 100 + np.cumsum(np.random.randn(n_points) * 0.1) + np.abs(np.random.randn(n_points) * 0.5),
            'low': 100 + np.cumsum(np.random.randn(n_points) * 0.1) - np.abs(np.random.randn(n_points) * 0.5),
            'close': 100 + np.cumsum(np.random.randn(n_points) * 0.1),
            'volume': np.random.randint(1000, 10000, n_points)
        })
        
        # Ensure high >= close >= low (valid OHLC data)
        self.test_data['high'] = np.maximum(self.test_data['high'], self.test_data[['open', 'close']].max(axis=1))
        self.test_data['low'] = np.minimum(self.test_data['low'], self.test_data[['open', 'close']].min(axis=1))
    
    @patch('src.feature_engineering.unified_pipeline.UnifiedTechnicalIndicatorsPipeline._validate_gpu_availability')
    def test_complete_pipeline_integration(self, mock_gpu_validation):
        """Test that Phase 3 + Phase 4 pipeline works end-to-end"""
        mock_gpu_validation.return_value = None
        
        pipeline = UnifiedTechnicalIndicatorsPipeline()
        
        # Test complete pipeline
        result = pipeline.compute_all_indicators_and_features(self.test_data)
        
        # Validate Phase 3 outputs still present
        phase3_columns = ['open', 'high', 'low', 'close', 'volume', 
                         'macd_line', 'macd_signal', 'macd_histogram', 
                         'atr', 'swing_highs', 'swing_lows']
        
        for col in phase3_columns:
            assert col in result.columns, f"Phase 3 column {col} missing from integrated pipeline"
        
        # Validate Phase 4 features present with EXACT legacy names
        phase4_features = ['macd_norm', 'macd_hist_norm', 'price_range', 'price_position']
        
        for feature in phase4_features:
            assert feature in result.columns, f"Phase 4 feature {feature} missing from integrated pipeline"
            
            # Check that we have some valid (non-NaN) values - NaN values are expected during warmup period
            valid_values = result[feature].dropna()
            assert len(valid_values) > len(result) * 0.7, f"Feature {feature} has too many NaN values"
    
    @patch('src.feature_engineering.unified_pipeline.UnifiedTechnicalIndicatorsPipeline._validate_gpu_availability')
    def test_legacy_feature_formulas_exact_match(self, mock_gpu_validation):
        """Test that computed features match EXACT legacy formulas"""
        mock_gpu_validation.return_value = None
        
        pipeline = UnifiedTechnicalIndicatorsPipeline()
        result = pipeline.compute_all_indicators_and_features(self.test_data)
        
        # Test EXACT legacy formula: macd_norm = macd / atr (only for non-NaN values)
        valid_mask = ~(result['macd_line'].isna() | result['atr'].isna())
        expected_macd_norm = result.loc[valid_mask, 'macd_line'] / result.loc[valid_mask, 'atr']
        np.testing.assert_allclose(result.loc[valid_mask, 'macd_norm'], expected_macd_norm, rtol=1e-6,
                                  err_msg="macd_norm formula doesn't match legacy: macd / atr")
        
        # Test EXACT legacy formula: macd_hist_norm = hist / atr (only for non-NaN values)
        valid_mask_hist = ~(result['macd_histogram'].isna() | result['atr'].isna())
        expected_hist_norm = result.loc[valid_mask_hist, 'macd_histogram'] / result.loc[valid_mask_hist, 'atr']
        np.testing.assert_allclose(result.loc[valid_mask_hist, 'macd_hist_norm'], expected_hist_norm, rtol=1e-6,
                                  err_msg="macd_hist_norm formula doesn't match legacy: hist / atr")
        
        # Test EXACT legacy formula: price_range = swing_high - swing_low (only for non-NaN values)
        valid_mask_swing = ~(result['swing_highs'].isna() | result['swing_lows'].isna())
        expected_price_range = result.loc[valid_mask_swing, 'swing_highs'] - result.loc[valid_mask_swing, 'swing_lows']
        np.testing.assert_allclose(result.loc[valid_mask_swing, 'price_range'], expected_price_range, rtol=1e-6,
                                  err_msg="price_range formula doesn't match legacy: swing_high - swing_low")
        
        # Test EXACT legacy formula: price_position = (price - swing_low) / price_range (only for non-NaN values)
        valid_mask_pos = ~(result['close'].isna() | result['swing_lows'].isna() | result['price_range'].isna())
        expected_price_position = (result.loc[valid_mask_pos, 'close'] - result.loc[valid_mask_pos, 'swing_lows']) / result.loc[valid_mask_pos, 'price_range']
        np.testing.assert_allclose(result.loc[valid_mask_pos, 'price_position'], expected_price_position, rtol=1e-6,
                                  err_msg="price_position formula doesn't match legacy: (price - swing_low) / price_range")
    
    @patch('src.feature_engineering.unified_pipeline.UnifiedTechnicalIndicatorsPipeline._validate_gpu_availability')
    def test_price_position_range_validation(self, mock_gpu_validation):
        """Test that price_position stays in expected [0,1] range"""
        mock_gpu_validation.return_value = None
        
        pipeline = UnifiedTechnicalIndicatorsPipeline()
        result = pipeline.compute_all_indicators_and_features(self.test_data)
        
        price_position = result['price_position']
        
        # Remove any inf or nan values for range testing
        valid_positions = price_position[np.isfinite(price_position)]
        
        if len(valid_positions) > 0:
            # Most positions should be in [0,1] range for valid swing data
            # Allow some tolerance for edge cases where price may be outside swing range
            positions_in_range = valid_positions[(valid_positions >= -0.1) & (valid_positions <= 1.1)]
            ratio_in_range = len(positions_in_range) / len(valid_positions)
            
            assert ratio_in_range > 0.8, f"Only {ratio_in_range:.1%} of price positions in expected range"
    
    @patch('src.feature_engineering.unified_pipeline.UnifiedTechnicalIndicatorsPipeline._validate_gpu_availability')
    def test_no_data_corruption_from_feature_engineering(self, mock_gpu_validation):
        """Test that Phase 4 doesn't corrupt Phase 3 data"""
        mock_gpu_validation.return_value = None
        
        pipeline = UnifiedTechnicalIndicatorsPipeline()
        
        # Compute Phase 3 only
        phase3_result = pipeline.compute_all_indicators(self.test_data)
        
        # Compute Phase 3 + Phase 4
        integrated_result = pipeline.compute_all_indicators_and_features(self.test_data)
        
        # Verify Phase 3 core indicators are identical (excluding swing arrays which are transformed)
        core_phase3_columns = ['macd_line', 'macd_signal', 'macd_histogram', 'atr']
        
        for col in core_phase3_columns:
            np.testing.assert_array_equal(
                phase3_result[col].values, 
                integrated_result[col].values,
                err_msg=f"Phase 3 column {col} was corrupted by Phase 4 integration"
            )
        
        # For swing columns, verify that Phase 4 converted them to price values correctly
        # (boolean arrays should be converted to actual price values)
        assert integrated_result['swing_highs'].dtype in [np.float32, np.float64], "swing_highs should be converted to price values"
        assert integrated_result['swing_lows'].dtype in [np.float32, np.float64], "swing_lows should be converted to price values"
    
    @patch('src.feature_engineering.unified_pipeline.UnifiedTechnicalIndicatorsPipeline._validate_gpu_availability')
    def test_feature_engineering_performance_overhead(self, mock_gpu_validation):
        """Test that Phase 4 adds minimal performance overhead"""
        mock_gpu_validation.return_value = None
        
        pipeline = UnifiedTechnicalIndicatorsPipeline()
        
        import time
        
        # Time Phase 3 only
        start_time = time.perf_counter()
        phase3_result = pipeline.compute_all_indicators(self.test_data)
        phase3_time = time.perf_counter() - start_time
        
        # Time Phase 3 + Phase 4
        start_time = time.perf_counter()
        integrated_result = pipeline.compute_all_indicators_and_features(self.test_data)
        integrated_time = time.perf_counter() - start_time
        
        # Phase 4 overhead should be minimal (target: <0.5s additional)
        overhead = integrated_time - phase3_time
        overhead_ratio = overhead / phase3_time
        
        print(f"Phase 3 time: {phase3_time:.3f}s")
        print(f"Integrated time: {integrated_time:.3f}s")
        print(f"Phase 4 overhead: {overhead:.3f}s ({overhead_ratio:.1%})")
        
        # Feature engineering should add less than 50% overhead
        assert overhead_ratio < 0.5, f"Phase 4 overhead too high: {overhead_ratio:.1%} (target: <50%)"
    
    @patch('src.feature_engineering.unified_pipeline.UnifiedTechnicalIndicatorsPipeline._validate_gpu_availability')
    def test_output_data_structure_consistency(self, mock_gpu_validation):
        """Test that output structure is consistent and contains all required data"""
        mock_gpu_validation.return_value = None
        
        pipeline = UnifiedTechnicalIndicatorsPipeline()
        result = pipeline.compute_all_indicators_and_features(self.test_data)
        
        # Validate DataFrame structure
        assert isinstance(result, pd.DataFrame), "Result should be a pandas DataFrame"
        assert len(result) == len(self.test_data), "Result should have same length as input"
        
        # Validate all values are numeric
        numeric_columns = ['macd_norm', 'macd_hist_norm', 'price_range', 'price_position']
        for col in numeric_columns:
            assert pd.api.types.is_numeric_dtype(result[col]), f"Column {col} should be numeric"
        
        # Validate no infinite values
        for col in numeric_columns:
            finite_mask = np.isfinite(result[col])
            finite_ratio = finite_mask.sum() / len(result[col])
            assert finite_ratio > 0.95, f"Column {col} has too many non-finite values: {finite_ratio:.1%}"
    
    @patch('src.feature_engineering.unified_pipeline.UnifiedTechnicalIndicatorsPipeline._validate_gpu_availability')
    def test_small_dataset_handling(self, mock_gpu_validation):
        """Test that pipeline handles small datasets correctly"""
        mock_gpu_validation.return_value = None
        
        # Create small dataset
        small_data = self.test_data.head(50).copy()
        
        pipeline = UnifiedTechnicalIndicatorsPipeline()
        result = pipeline.compute_all_indicators_and_features(small_data)
        
        # Should complete without errors
        assert len(result) == len(small_data)
        
        # Should have all required features
        required_features = ['macd_norm', 'macd_hist_norm', 'price_range', 'price_position']
        for feature in required_features:
            assert feature in result.columns, f"Feature {feature} missing from small dataset result"
            # For small datasets, some features may be all NaN due to insufficient swing points
            # This is expected behavior - just check that the feature exists
            assert result[feature].shape[0] == len(small_data), f"Feature {feature} has wrong shape"
    
    @patch('src.feature_engineering.unified_pipeline.UnifiedTechnicalIndicatorsPipeline._validate_gpu_availability')
    def test_large_dataset_memory_efficiency(self, mock_gpu_validation):
        """Test that pipeline handles larger datasets efficiently"""
        mock_gpu_validation.return_value = None
        
        # Create larger dataset
        large_data = pd.concat([self.test_data] * 5, ignore_index=True)  # 5000 points
        
        pipeline = UnifiedTechnicalIndicatorsPipeline()
        
        # Should complete without memory errors
        result = pipeline.compute_all_indicators_and_features(large_data)
        
        assert len(result) == len(large_data)
        
        # Validate feature quality on larger dataset
        required_features = ['macd_norm', 'macd_hist_norm', 'price_range', 'price_position']
        for feature in required_features:
            assert feature in result.columns
            # Check that we have substantial valid values 
            valid_values = result[feature].dropna()
            assert len(valid_values) > len(result) * 0.7, f"Feature {feature} has too many NaN values on large dataset"


if __name__ == "__main__":
    # Run integration tests
    pytest.main([__file__, "-v"])