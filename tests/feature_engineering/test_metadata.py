"""Tests for DataFrameMetadata class - TDD approach"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from src.feature_engineering.metadata import DataFrameMetadata


class TestDataFrameMetadata:
    """Test DataFrameMetadata functionality"""
    
    def setup_method(self):
        """Setup test data"""
        dates = pd.date_range('2023-01-01', periods=100, freq='D')
        self.test_df = pd.DataFrame({
            'open': np.random.uniform(100, 200, 100).astype(np.float64),
            'high': np.random.uniform(150, 250, 100).astype(np.float64),
            'low': np.random.uniform(50, 150, 100).astype(np.float64),
            'close': np.random.uniform(80, 220, 100).astype(np.float64),
            'volume': np.random.randint(1000, 10000, 100).astype(np.int64)
        }, index=dates)
    
    def test_from_dataframe_extracts_metadata(self):
        """Test metadata extraction from DataFrame"""
        metadata = DataFrameMetadata.from_dataframe(self.test_df)
        
        # Check index preservation
        pd.testing.assert_index_equal(metadata.index, self.test_df.index)
        
        # Check columns preservation
        assert metadata.columns == self.test_df.columns.tolist()
        
        # Check dtypes preservation
        expected_dtypes = self.test_df.dtypes.to_dict()
        assert metadata.dtypes == expected_dtypes
    
    def test_reconstruct_preserves_original_dataframe(self):
        """Test DataFrame reconstruction preserves original data"""
        # Extract metadata
        metadata = DataFrameMetadata.from_dataframe(self.test_df)
        
        # Convert to array format (simulating GPU processing)
        arrays = {col: self.test_df[col].values for col in self.test_df.columns}
        
        # Reconstruct DataFrame
        reconstructed = metadata.reconstruct(arrays)
        
        # Check data integrity
        pd.testing.assert_frame_equal(reconstructed, self.test_df)
    
    def test_reconstruct_handles_missing_columns(self):
        """Test reconstruction with missing columns"""
        metadata = DataFrameMetadata.from_dataframe(self.test_df)
        
        # Partial arrays (missing 'volume')
        partial_arrays = {
            'open': self.test_df['open'].values,
            'high': self.test_df['high'].values,
            'close': self.test_df['close'].values
        }
        
        reconstructed = metadata.reconstruct(partial_arrays)
        
        # Should have only the provided columns
        assert list(reconstructed.columns) == ['open', 'high', 'close']
        
        # Data should match
        expected = self.test_df[['open', 'high', 'close']]
        pd.testing.assert_frame_equal(reconstructed, expected)
    
    def test_reconstruct_preserves_dtypes(self):
        """Test dtype preservation during reconstruction"""
        metadata = DataFrameMetadata.from_dataframe(self.test_df)
        
        # Convert arrays to different dtype (simulating processing)
        arrays = {col: self.test_df[col].values.astype(np.float32) 
                 for col in self.test_df.columns}
        
        reconstructed = metadata.reconstruct(arrays)
        
        # Should restore original dtypes
        for col in self.test_df.columns:
            assert reconstructed[col].dtype == self.test_df[col].dtype
    
    def test_metadata_serializable(self):
        """Test that metadata can be serialized/copied"""
        metadata = DataFrameMetadata.from_dataframe(self.test_df)
        
        # Should be able to create copy
        import copy
        metadata_copy = copy.deepcopy(metadata)
        
        # Check all attributes are preserved
        pd.testing.assert_index_equal(metadata_copy.index, metadata.index)
        assert metadata_copy.columns == metadata.columns
        assert metadata_copy.dtypes == metadata.dtypes
    
    def test_empty_dataframe_handling(self):
        """Test handling of empty DataFrame"""
        empty_df = pd.DataFrame()
        metadata = DataFrameMetadata.from_dataframe(empty_df)
        
        reconstructed = metadata.reconstruct({})
        pd.testing.assert_frame_equal(reconstructed, empty_df)
    
    def test_single_column_dataframe(self):
        """Test handling of single column DataFrame"""
        single_col_df = pd.DataFrame({'price': [1.0, 2.0, 3.0]})
        metadata = DataFrameMetadata.from_dataframe(single_col_df)
        
        arrays = {'price': single_col_df['price'].values}
        reconstructed = metadata.reconstruct(arrays)
        
        pd.testing.assert_frame_equal(reconstructed, single_col_df)