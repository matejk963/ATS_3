import pytest
import numpy as np
import pandas as pd
from typing import List, Tuple, Dict

# Test imports - will implement OptimizedGPUArrayConverter
from src.feature_engineering.gpu_converter import GPUArrayConverter
from src.feature_engineering.metadata import DataFrameMetadata
from src.feature_engineering.array_backend import ArrayLike


class TestOptimizedGPUArrayConverterBatchProcessing:
    """Test batch processing for OptimizedGPUArrayConverter (Task 1.2)"""
    
    def setup_method(self):
        """Setup test fixtures for batch processing"""
        self.converter = GPUArrayConverter()
        
        # Create batch of test DataFrames with different shapes and characteristics
        dates1 = pd.date_range('2024-01-01', periods=1000, freq='1min')
        dates2 = pd.date_range('2024-01-02', periods=1500, freq='1min') 
        dates3 = pd.date_range('2024-01-03', periods=800, freq='1min')
        
        self.test_df_batch = [
            pd.DataFrame({
                'open': np.random.rand(1000) * 100 + 100,
                'high': np.random.rand(1000) * 5 + 105,
                'low': np.random.rand(1000) * 5 + 95, 
                'close': np.random.rand(1000) * 100 + 100,
                'volume': np.random.randint(1000, 10000, 1000)
            }, index=dates1),
            
            pd.DataFrame({
                'open': np.random.rand(1500) * 200 + 150,
                'high': np.random.rand(1500) * 10 + 160,
                'low': np.random.rand(1500) * 10 + 140,
                'close': np.random.rand(1500) * 200 + 150,
                'volume': np.random.randint(2000, 20000, 1500)
            }, index=dates2),
            
            pd.DataFrame({
                'open': np.random.rand(800) * 50 + 75,
                'high': np.random.rand(800) * 3 + 78,
                'low': np.random.rand(800) * 3 + 72,
                'close': np.random.rand(800) * 50 + 75,
                'volume': np.random.randint(500, 5000, 800)
            }, index=dates3)
        ]
    
    def test_batch_to_array_method_exists(self):
        """Test batch_to_array method exists for batch DataFrame processing"""
        # GREEN: Implementation exists - test actual functionality
        result = self.converter.batch_to_array(self.test_df_batch)
        
        # Validate structure
        assert isinstance(result, list)
        assert len(result) == len(self.test_df_batch)
        
        # Validate each result is (arrays, metadata) tuple
        for arrays, metadata in result:
            assert isinstance(arrays, dict)
            assert isinstance(metadata, DataFrameMetadata)
    
    def test_batch_to_array_returns_correct_structure(self):
        """Test batch_to_array returns list of (arrays, metadata) tuples"""
        # RED: This test should fail - method doesn't exist yet
        pytest.skip("Requires OptimizedGPUArrayConverter implementation")
        
        # After implementation, validate:
        # result = self.converter.batch_to_array(self.test_df_batch)
        # assert isinstance(result, list)
        # assert len(result) == len(self.test_df_batch)
        # for arrays, metadata in result:
        #     assert isinstance(arrays, dict)
        #     assert isinstance(metadata, DataFrameMetadata)
    
    def test_batch_memory_preallocation(self):
        """Test batch processing pre-allocates GPU memory for entire batch"""
        # RED: This test should fail - optimization doesn't exist yet
        pytest.skip("Requires batch memory pre-allocation implementation")
        
        # After implementation:
        # 1. Monitor GPU memory allocation pattern during batch processing
        # 2. Verify single large allocation instead of multiple small ones
        # 3. Validate memory layout is optimized for GPU operations
    
    def test_batch_processing_preserves_metadata(self):
        """Test batch processing preserves all DataFrame metadata"""
        # RED: This test should fail - method doesn't exist yet
        pytest.skip("Requires OptimizedGPUArrayConverter implementation")
        
        # After implementation:
        # result = self.converter.batch_to_array(self.test_df_batch)
        # for i, (arrays, metadata) in enumerate(result):
        #     original_df = self.test_df_batch[i]
        #     assert metadata.shape == original_df.shape
        #     assert metadata.columns.tolist() == original_df.columns.tolist()
        #     assert metadata.index_name == original_df.index.name


class TestOptimizedGPUArrayConverterBatchOptimization:
    """Test batch optimization features for GPU memory efficiency"""
    
    def setup_method(self):
        """Setup test fixtures for optimization testing"""
        self.converter = GPUArrayConverter()
        
        # Create batch with mixed dtypes to test type conversion optimization
        self.mixed_dtype_batch = [
            pd.DataFrame({
                'float64_col': np.random.rand(1000).astype(np.float64),
                'int32_col': np.random.randint(0, 100, 1000).astype(np.int32),
                'float32_col': np.random.rand(1000).astype(np.float32)
            }),
            pd.DataFrame({
                'double_precision': np.random.rand(1500).astype(np.float64),
                'integer_data': np.random.randint(0, 1000, 1500).astype(np.int64),
                'single_precision': np.random.rand(1500).astype(np.float32)
            })
        ]
    
    def test_optimize_dtypes_batch_method_exists(self):
        """Test optimize_dtypes_batch method exists for efficient type conversion"""
        # GREEN: Implementation exists - test actual functionality
        # Extract arrays from DataFrames first (current functionality)
        array_batches = []
        for df in self.mixed_dtype_batch:
            arrays, _ = self.converter.to_arrays(df)
            array_batches.append(arrays)
        
        # Test the implemented method
        optimized = self.converter.optimize_dtypes_batch(array_batches)
        
        # Validate results
        assert isinstance(optimized, list)
        assert len(optimized) == len(array_batches)
        
        # Verify optimization - all arrays should be float32 and C-contiguous
        for optimized_arrays in optimized:
            assert isinstance(optimized_arrays, dict)
            for key, arr in optimized_arrays.items():
                assert arr.dtype == np.float32
                assert arr.flags.c_contiguous
    
    def test_batch_type_conversion_to_float32(self):
        """Test batch type conversion optimizes all arrays to float32"""
        # RED: This test should fail - batch optimization doesn't exist yet
        pytest.skip("Requires optimize_dtypes_batch implementation")
        
        # After implementation:
        # 1. Convert batch of mixed dtypes to arrays
        # 2. Apply batch type optimization
        # 3. Verify all results are float32
        # 4. Validate data preservation during conversion
    
    def test_single_gpu_transfer_per_batch(self):
        """Test batch processing uses single GPU transfer instead of multiple"""
        # RED: This test should fail - optimization doesn't exist yet
        pytest.skip("Requires batch GPU transfer optimization")
        
        # After implementation:
        # 1. Monitor GPU memory transfer operations
        # 2. Verify single transfer per batch instead of per DataFrame
        # 3. Validate transfer efficiency improvement
    
    def test_contiguous_memory_layout_enforcement(self):
        """Test batch processing enforces C-contiguous memory layout"""
        # RED: This test should fail - batch layout optimization doesn't exist yet
        pytest.skip("Requires batch memory layout optimization")
        
        # After implementation:
        # 1. Process batch with non-contiguous arrays
        # 2. Verify all results have C-contiguous layout
        # 3. Validate GPU performance improvement


class TestOptimizedGPUArrayConverterCompatibility:
    """Test backward compatibility with existing GPUArrayConverter"""
    
    def setup_method(self):
        """Setup compatibility test fixtures"""
        self.converter = GPUArrayConverter()
        
        # Standard test DataFrame for compatibility testing
        dates = pd.date_range('2024-01-01', periods=1000, freq='1min')
        self.test_df = pd.DataFrame({
            'open': np.random.rand(1000) * 100 + 100,
            'high': np.random.rand(1000) * 5 + 105,
            'low': np.random.rand(1000) * 5 + 95,
            'close': np.random.rand(1000) * 100 + 100,
            'volume': np.random.randint(1000, 10000, 1000).astype(np.float32)
        }, index=dates)
    
    def test_existing_to_arrays_method_still_works(self):
        """Test existing to_arrays method continues to work after optimization"""
        # Current functionality should be preserved
        arrays, metadata = self.converter.to_arrays(self.test_df)
        
        # Validate current functionality
        assert isinstance(arrays, dict)
        assert isinstance(metadata, DataFrameMetadata)
        assert len(arrays) == len(self.test_df.columns)
        
        # Verify array properties
        for col, arr in arrays.items():
            assert arr.dtype == np.float32  # Default dtype
            assert arr.flags.c_contiguous   # Default contiguous=True
            assert arr.shape[0] == len(self.test_df)
    
    def test_existing_from_arrays_method_still_works(self):
        """Test existing from_arrays method continues to work after optimization"""
        # Test round-trip conversion
        arrays, metadata = self.converter.to_arrays(self.test_df)
        reconstructed_df = self.converter.from_arrays(arrays, metadata)
        
        # Validate reconstruction
        assert isinstance(reconstructed_df, pd.DataFrame)
        assert reconstructed_df.shape == self.test_df.shape
        assert reconstructed_df.columns.tolist() == self.test_df.columns.tolist()
        
        # Verify data preservation (allowing for float32 precision)
        for col in self.test_df.columns:
            np.testing.assert_allclose(
                reconstructed_df[col].values,
                self.test_df[col].values,
                rtol=1e-6  # Account for float32 precision
            )
    
    def test_existing_optimize_for_gpu_method_still_works(self):
        """Test existing optimize_for_gpu method continues to work after optimization"""
        # Convert to arrays first
        arrays, _ = self.converter.to_arrays(self.test_df, dtype='float64')  # Start with float64
        
        # Apply current optimization
        optimized = self.converter.optimize_for_gpu(arrays)
        
        # Validate current optimization functionality
        assert isinstance(optimized, dict)
        assert len(optimized) == len(arrays)
        
        for col, arr in optimized.items():
            assert arr.dtype == np.float32  # Should be converted to float32
            assert arr.flags.c_contiguous   # Should be C-contiguous


class TestOptimizedGPUArrayConverterBatchPerformance:
    """Performance tests for batch processing optimization"""
    
    def setup_method(self):
        """Setup performance test fixtures"""
        self.converter = GPUArrayConverter()
        
        # Large batch for performance testing
        self.large_batch = []
        for i in range(25):  # Target: 25-40 combinations per batch
            dates = pd.date_range(f'2024-01-{i+1:02d}', periods=5000, freq='1min')
            df = pd.DataFrame({
                'open': np.random.rand(5000) * 100 + 100,
                'high': np.random.rand(5000) * 5 + 105,
                'low': np.random.rand(5000) * 5 + 95,
                'close': np.random.rand(5000) * 100 + 100,
                'volume': np.random.randint(1000, 10000, 5000),
                'additional_feature': np.random.rand(5000) * 10
            }, index=dates)
            self.large_batch.append(df)
    
    def test_current_individual_processing_baseline(self):
        """Establish baseline performance for individual DataFrame processing"""
        # Process each DataFrame individually to establish baseline
        results = []
        for df in self.large_batch[:5]:  # Test with smaller subset for baseline
            arrays, metadata = self.converter.to_arrays(df)
            results.append((arrays, metadata))
        
        # Validate baseline functionality
        assert len(results) == 5
        for arrays, metadata in results:
            assert isinstance(arrays, dict)
            assert isinstance(metadata, DataFrameMetadata)
    
    @pytest.mark.skip(reason="Requires batch processing implementation")
    def test_batch_processing_performance_improvement(self):
        """Test batch processing provides performance improvement over individual processing"""
        # This test will validate performance improvement after implementation
        # Target: <50ms conversion overhead per batch
        # Target: Process 25-40 combinations per batch efficiently
        pass
    
    @pytest.mark.skip(reason="Requires GPU utilization monitoring")
    def test_batch_processing_gpu_utilization(self):
        """Test batch processing achieves target GPU utilization"""
        # This test will validate GPU utilization improvement after implementation
        # Target: Contribute to 60-70% GPU utilization baseline
        pass


class TestOptimizedGPUArrayConverterIntegration:
    """Integration tests with other pipeline components""" 
    
    def setup_method(self):
        """Setup integration test fixtures"""
        self.converter = GPUArrayConverter()
        
        # Create test data that mimics real technical indicators pipeline
        dates = pd.date_range('2024-01-01', periods=10000, freq='1min')
        self.pipeline_test_data = [
            pd.DataFrame({
                'open': np.random.rand(10000) * 100 + 100,
                'high': np.random.rand(10000) * 5 + 105,
                'low': np.random.rand(10000) * 5 + 95,
                'close': np.random.rand(10000) * 100 + 100,
                'volume': np.random.randint(1000, 10000, 10000)
            }, index=dates),
            
            # Second DataFrame with technical indicators
            pd.DataFrame({
                'sma_20': np.random.rand(10000) * 100 + 100,
                'ema_12': np.random.rand(10000) * 100 + 100,
                'rsi': np.random.rand(10000) * 100,
                'macd': np.random.rand(10000) * 2 - 1,
                'atr': np.random.rand(10000) * 5
            }, index=dates)
        ]
    
    def test_integration_with_unified_pipeline(self):
        """Test OptimizedGPUArrayConverter integrates with UnifiedTechnicalIndicatorsPipeline"""
        # This test validates that the optimization doesn't break pipeline integration
        # Test current integration
        for df in self.pipeline_test_data:
            arrays, metadata = self.converter.to_arrays(df)
            
            # Validate structure that pipeline expects
            assert isinstance(arrays, dict)
            assert isinstance(metadata, DataFrameMetadata)
            
            # Verify all columns converted
            assert len(arrays) == len(df.select_dtypes(include=[np.number]).columns)
    
    def test_metadata_preservation_in_batch_processing(self):
        """Test batch processing preserves metadata required by downstream components"""
        # RED: This test should fail until batch processing is implemented
        pytest.skip("Requires batch processing implementation")
        
        # After implementation:
        # 1. Process batch with batch_to_array
        # 2. Verify metadata contains all required fields for pipeline
        # 3. Test downstream components can use the metadata
    
    def test_array_format_compatibility_with_array_backend(self):
        """Test converted arrays are compatible with ArrayBackend operations"""
        from src.feature_engineering.array_backend import ArrayBackend
        
        backend = ArrayBackend(backend='cupy')
        
        # Convert DataFrame to arrays
        arrays, metadata = self.converter.to_arrays(self.pipeline_test_data[0])
        
        # Test that arrays work with ArrayBackend operations
        for col, arr in arrays.items():
            gpu_array = backend.asarray(arr)
            
            # Test basic operations
            result = backend.add(gpu_array, 1.0)
            cpu_result = backend.to_cpu(result)
            
            # Verify operation worked
            assert cpu_result.shape == arr.shape
            np.testing.assert_allclose(cpu_result, arr + 1.0, rtol=1e-6)