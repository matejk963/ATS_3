"""
Integration tests for complete parameter generation (Phase 1.1.3).

Tests full Cartesian product generation and validation.
"""

import pytest
import time
import tempfile
import json
from pathlib import Path
from src.gpu_parallel_processing.parameter_combinations import (
    generate_all_parameter_combinations,
    generate_combination_batch,
    get_combination_sample,
    validate_complete_combination,
    export_combinations_to_file,
    export_combos_metadata_parquet,
    load_combos_metadata_parquet,
    get_combination_counts,
    CONTRACTS,
    PREDICTOR_GRANULARITIES,
    MACD_CONFIGS,
    ATR_LOOKBACKS,
    STOP_LOSS_RANGES,
    SL_TP_RATIOS
)


class TestCompleteParameterGeneration:
    """Test complete parameter combination generation."""
    
    def test_generate_sample_combinations(self):
        """Test sample combination generation."""
        samples = get_combination_sample(5)
        
        assert len(samples) == 5
        
        # Check structure of generated combinations
        for combo in samples:
            assert self._validate_combination_structure(combo)
    
    def test_combination_batch_generation(self):
        """Test batch combination generation."""
        batch_size = 10
        batch = generate_combination_batch(0, batch_size)
        
        assert len(batch) <= batch_size  # May be less due to validation
        
        # Check combo_id sequence
        for i, combo in enumerate(batch):
            assert combo['combo_id'] == i
            assert self._validate_combination_structure(combo)
    
    def test_combination_validation(self):
        """Test complete combination validation."""
        samples = get_combination_sample(3)
        
        # All generated combinations should be valid
        for combo in samples:
            assert validate_complete_combination(combo)
        
        # Test invalid combination
        invalid_combo = samples[0].copy()
        invalid_combo['macd_params']['short'] = invalid_combo['macd_params']['long']  # Invalid: short >= long
        assert not validate_complete_combination(invalid_combo)
    
    def test_combination_uniqueness(self):
        """Test that generated combinations are unique."""
        samples = get_combination_sample(20)
        
        # Convert to tuples for uniqueness check (excluding combo_id)
        combo_signatures = []
        for combo in samples:
            signature = (
                combo['contract'],
                combo['predictor_granularities']['atr_macd'],
                combo['predictor_granularities']['swing'],
                tuple(combo['macd_params'].values()),
                combo['atr_lookback'],
                tuple(combo['bias_thresholds'].values()),
                tuple(combo['strategy_thresholds'].values()),
                combo['stop_loss'],
                combo['sl_tp_ratio']
            )
            combo_signatures.append(signature)
        
        # All should be unique
        assert len(combo_signatures) == len(set(combo_signatures))
    
    def test_tp_value_calculation(self):
        """Test that TP values are calculated correctly."""
        samples = get_combination_sample(10)
        
        for combo in samples:
            expected_tp = combo['stop_loss'] * combo['sl_tp_ratio']
            assert abs(combo['tp_value'] - expected_tp) < 0.001
    
    def _validate_combination_structure(self, combo):
        """Helper to validate combination structure."""
        required_keys = [
            'combo_id', 'date_range', 'contract', 'predictor_granularities',
            'macd_params', 'atr_lookback', 'bias_thresholds', 'strategy_thresholds',
            'stop_loss', 'sl_tp_ratio', 'tp_value'
        ]
        
        for key in required_keys:
            if key not in combo:
                return False
        
        # Check specific structures
        if not isinstance(combo['predictor_granularities'], dict):
            return False
        if 'atr_macd' not in combo['predictor_granularities']:
            return False
        if 'swing' not in combo['predictor_granularities']:
            return False
        
        if not isinstance(combo['macd_params'], dict):
            return False
        if not all(key in combo['macd_params'] for key in ['short', 'long', 'signal']):
            return False
        
        return True


class TestCombinationCounts:
    """Test combination count calculations and estimates."""
    
    def test_combination_count_accuracy(self):
        """Test that combination counts are accurate for small samples."""
        counts = get_combination_counts()
        
        # Generate a small batch and verify counts are reasonable
        batch = generate_combination_batch(0, 50)
        
        # Should generate combinations without error
        assert len(batch) > 0
        assert len(batch) <= 50
    
    def test_total_combination_estimate(self):
        """Test total combination estimate calculation."""
        counts = get_combination_counts()
        
        # Manual calculation
        expected_total = (len(CONTRACTS) *
                         len(PREDICTOR_GRANULARITIES['atr_macd_granularities']) *
                         len(PREDICTOR_GRANULARITIES['swing_granularities']) *
                         len(MACD_CONFIGS) *
                         len(ATR_LOOKBACKS) *
                         counts['bias_combinations'] *
                         counts['strategy_combinations'] *
                         len(STOP_LOSS_RANGES) *
                         len(SL_TP_RATIOS))
        
        assert counts['total_combinations_estimate'] == expected_total
    
    def test_combination_space_coverage(self):
        """Test that combinations cover the expected parameter space."""
        # Generate larger sample to test coverage
        samples = generate_combination_batch(0, 100)
        
        # Extract unique values for each parameter
        unique_contracts = set(combo['contract'] for combo in samples)
        unique_atr_macd_grans = set(combo['predictor_granularities']['atr_macd'] for combo in samples)
        unique_macd_shorts = set(combo['macd_params']['short'] for combo in samples)
        
        # Should see some variety (not exhaustive coverage with small sample)
        assert len(unique_contracts) >= 1
        assert len(unique_atr_macd_grans) >= 1
        assert len(unique_macd_shorts) >= 1


class TestCombinationExport:
    """Test combination export functionality."""
    
    def test_export_to_file(self):
        """Test exporting combinations to JSON file."""
        samples = get_combination_sample(5)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "test_combinations.json"
            
            # Export combinations
            success = export_combinations_to_file(samples, str(output_file))
            assert success
            
            # Verify file was created
            assert output_file.exists()
            
            # Verify file contents
            with open(output_file, 'r') as f:
                loaded_combinations = json.load(f)
            
            assert len(loaded_combinations) == len(samples)
            assert loaded_combinations[0]['combo_id'] == samples[0]['combo_id']
    
    def test_export_empty_list(self):
        """Test exporting empty combination list."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "empty_combinations.json"
            
            success = export_combinations_to_file([], str(output_file))
            assert success
            
            with open(output_file, 'r') as f:
                loaded_combinations = json.load(f)
            
            assert loaded_combinations == []


class TestParquetExport:
    """Test parquet export functionality for combos metadata."""
    
    def test_parquet_export_and_load(self):
        """Test exporting and loading combos metadata via parquet."""
        pytest.importorskip("pandas")
        pytest.importorskip("pyarrow")
        
        samples = get_combination_sample(10)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "test_combos_metadata.parquet"
            
            # Export to parquet
            success = export_combos_metadata_parquet(samples, str(output_file))
            assert success
            
            # Verify file was created
            assert output_file.exists()
            
            # Load back from parquet
            loaded_combinations = load_combos_metadata_parquet(str(output_file))
            
            assert len(loaded_combinations) == len(samples)
            
            # Verify structure is preserved
            for original, loaded in zip(samples, loaded_combinations):
                assert original['combo_id'] == loaded['combo_id']
                assert original['contract'] == loaded['contract']
                assert original['macd_params'] == loaded['macd_params']
                assert original['bias_thresholds'] == loaded['bias_thresholds']
    
    def test_parquet_compression_efficiency(self):
        """Test that parquet provides good compression."""
        pytest.importorskip("pandas")
        pytest.importorskip("pyarrow")
        
        samples = get_combination_sample(100)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            parquet_file = Path(temp_dir) / "test_combos.parquet"
            json_file = Path(temp_dir) / "test_combos.json"
            
            # Export both formats
            parquet_success = export_combos_metadata_parquet(samples, str(parquet_file))
            json_success = export_combinations_to_file(samples, str(json_file))
            
            assert parquet_success and json_success
            
            # Compare file sizes
            parquet_size = parquet_file.stat().st_size
            json_size = json_file.stat().st_size
            
            # Parquet should be significantly smaller
            compression_ratio = parquet_size / json_size
            assert compression_ratio < 0.5  # At least 50% compression
            
            print(f"Compression ratio: {compression_ratio:.2f} (Parquet: {parquet_size} bytes, JSON: {json_size} bytes)")
    
    def test_parquet_default_filename(self):
        """Test parquet export with default filename generation."""
        pytest.importorskip("pandas")
        pytest.importorskip("pyarrow")
        
        samples = get_combination_sample(5)
        
        # Export with default filename
        success = export_combos_metadata_parquet(samples)
        assert success
        
        # Find the generated file
        import glob
        parquet_files = glob.glob("combos_metadata_*.parquet")
        assert len(parquet_files) >= 1
        
        # Load and verify
        loaded = load_combos_metadata_parquet(parquet_files[0])
        assert len(loaded) == len(samples)
        
        # Clean up
        for file in parquet_files:
            Path(file).unlink(missing_ok=True)
    
    def test_parquet_empty_combinations(self):
        """Test parquet export with empty combinations list."""
        pytest.importorskip("pandas")
        pytest.importorskip("pyarrow")
        
        success = export_combos_metadata_parquet([], "empty_combos.parquet")
        assert not success  # Should fail gracefully
    
    def test_parquet_missing_dependencies(self):
        """Test graceful handling when pandas/pyarrow not available."""
        # This test will pass if dependencies are available, skip if not
        try:
            import pandas
            import pyarrow
            pytest.skip("Dependencies available - cannot test missing dependency case")
        except ImportError:
            samples = get_combination_sample(5)
            success = export_combos_metadata_parquet(samples, "test.parquet")
            assert not success  # Should fail gracefully without dependencies


class TestPerformance:
    """Test performance characteristics of combination generation."""
    
    def test_small_batch_performance(self):
        """Test performance of small batch generation."""
        start_time = time.time()
        batch = generate_combination_batch(0, 50)
        generation_time = time.time() - start_time
        
        # Should generate 50 combinations quickly (under 5 seconds)
        assert generation_time < 5.0
        assert len(batch) > 0
        
        print(f"Generated {len(batch)} combinations in {generation_time:.3f} seconds")
        print(f"Rate: {len(batch) / generation_time:.1f} combinations/second")
    
    def test_memory_efficiency(self):
        """Test that batch generation is memory efficient."""
        import sys
        
        # Generate combinations in batches to test memory usage
        batch_sizes = [10, 50, 100]
        
        for batch_size in batch_sizes:
            batch = generate_combination_batch(0, batch_size)
            
            # Calculate approximate memory usage
            combo_size = sys.getsizeof(batch[0]) if batch else 0
            total_size = len(batch) * combo_size
            
            print(f"Batch size {batch_size}: ~{total_size / 1024:.1f} KB")
            
            # Should be reasonable memory usage
            assert total_size < 1024 * 1024  # Less than 1MB for test batches
    
    @pytest.mark.slow
    def test_large_batch_generation(self):
        """Test generation of larger combination batches."""
        # Only run if specifically requested (marked as slow)
        large_batch = generate_combination_batch(0, 1000)
        
        assert len(large_batch) > 0
        assert len(large_batch) <= 1000
        
        # All should be valid
        valid_count = sum(1 for combo in large_batch if validate_complete_combination(combo))
        assert valid_count == len(large_batch)


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_invalid_batch_parameters(self):
        """Test batch generation with invalid parameters."""
        # Start index beyond available combinations
        total_combinations = get_combination_counts()['total_combinations_estimate']
        
        batch = generate_combination_batch(total_combinations + 1000, 10)
        assert len(batch) == 0  # Should return empty list
    
    def test_zero_batch_size(self):
        """Test batch generation with zero size."""
        batch = generate_combination_batch(0, 0)
        assert len(batch) == 0
    
    def test_combination_validation_edge_cases(self):
        """Test combination validation with edge cases."""
        # Test with missing keys
        incomplete_combo = {'combo_id': 0}
        assert not validate_complete_combination(incomplete_combo)
        
        # Test with wrong types
        bad_combo = get_combination_sample(1)[0]
        bad_combo['combo_id'] = "not_an_integer"
        assert not validate_complete_combination(bad_combo)


class TestIntegration:
    """Integration tests combining multiple components."""
    
    def test_end_to_end_generation_and_validation(self):
        """Test complete end-to-end generation and validation."""
        # Generate sample
        samples = get_combination_sample(10)
        
        # Validate all combinations
        all_valid = all(validate_complete_combination(combo) for combo in samples)
        assert all_valid
        
        # Export to file
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "integration_test.json"
            success = export_combinations_to_file(samples, str(output_file))
            assert success
            
            # Reload and validate
            with open(output_file, 'r') as f:
                reloaded = json.load(f)
            
            assert len(reloaded) == len(samples)
            
            # Re-validate loaded combinations
            reloaded_valid = all(validate_complete_combination(combo) for combo in reloaded)
            assert reloaded_valid
    
    def test_deterministic_generation(self):
        """Test that generation is deterministic."""
        batch1 = generate_combination_batch(0, 20)
        batch2 = generate_combination_batch(0, 20)
        
        # Should be identical
        assert len(batch1) == len(batch2)
        
        for combo1, combo2 in zip(batch1, batch2):
            assert combo1 == combo2


if __name__ == "__main__":
    # Run with: pytest tests/test_complete_parameter_generation.py -v
    # Run slow tests with: pytest tests/test_complete_parameter_generation.py -v -m slow
    pytest.main([__file__, "-v"])