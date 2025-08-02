"""
Unit tests for contract data manager foundation (Phase 1.1.4).

Tests file resolution, data validation, and basic functionality.
"""

import pytest
import pandas as pd
import tempfile
import os
from pathlib import Path
from src.gpu_parallel_processing.contract_data_manager import (
    ContractDataManager,
    ValidationResult
)


@pytest.fixture
def temp_data_dir():
    """Create temporary data directory for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def sample_contract_data():
    """Create sample valid contract data."""
    return pd.DataFrame({
        'open': [100.0, 101.0, 102.0, 103.0, 104.0],
        'high': [105.0, 106.0, 107.0, 108.0, 109.0],
        'low': [95.0, 96.0, 97.0, 98.0, 99.0],
        'close': [103.0, 104.0, 105.0, 106.0, 107.0],
        'volume': [1000, 1100, 1200, 1300, 1400]
    })


@pytest.fixture
def invalid_contract_data():
    """Create sample invalid contract data for testing validation."""
    return pd.DataFrame({
        'open': [100.0, 101.0, -10.0],  # Negative price (invalid)
        'high': [105.0, 100.0, 105.0],  # High < Open (invalid)
        'low': [95.0, 102.0, 95.0],     # Low > Open (invalid)
        'close': [103.0, 104.0, 105.0],
        'volume': [1000, -500, 1200]    # Negative volume (invalid)
    })


class TestContractDataManagerInitialization:
    """Test contract data manager initialization."""
    
    def test_init_with_valid_directory(self, temp_data_dir):
        """Test initialization with valid data directory."""
        manager = ContractDataManager(str(temp_data_dir))
        
        assert manager.data_directory == temp_data_dir
        assert manager.files_loaded == 0
        assert manager.validation_failures == 0
        assert manager.file_not_found_errors == 0
    
    def test_init_with_nonexistent_directory(self):
        """Test initialization with non-existent directory."""
        with pytest.raises(ValueError, match="Invalid data directory"):
            ContractDataManager("/nonexistent/directory/path")
    
    def test_init_with_file_instead_of_directory(self, temp_data_dir):
        """Test initialization with file path instead of directory."""
        # Create a file instead of directory
        test_file = temp_data_dir / "not_a_directory.txt"
        test_file.write_text("test")
        
        with pytest.raises(ValueError, match="Invalid data directory"):
            ContractDataManager(str(test_file))


class TestContractPathResolution:
    """Test contract file path resolution."""
    
    def test_resolve_existing_contract(self, temp_data_dir, sample_contract_data):
        """Test resolving path for existing contract."""
        # Create test contract file
        contract_file = temp_data_dir / "test01_tr_ba_data.parquet"
        sample_contract_data.to_parquet(contract_file)
        
        manager = ContractDataManager(str(temp_data_dir))
        
        # Should resolve successfully
        resolved_path = manager._resolve_contract_path("test01")
        assert resolved_path == contract_file
        assert resolved_path.exists()
    
    def test_resolve_nonexistent_contract(self, temp_data_dir):
        """Test resolving path for non-existent contract."""
        manager = ContractDataManager(str(temp_data_dir))
        
        with pytest.raises(FileNotFoundError, match="Contract data file not found"):
            manager._resolve_contract_path("nonexistent")
    
    def test_contract_code_format_validation(self, temp_data_dir):
        """Test contract code format validation."""
        manager = ContractDataManager(str(temp_data_dir))
        
        # Valid contract codes
        assert manager._validate_contract_code_format("dem07_25")
        assert manager._validate_contract_code_format("fra08_25")
        assert manager._validate_contract_code_format("test123")
        
        # Invalid contract codes
        assert not manager._validate_contract_code_format("")
        assert not manager._validate_contract_code_format("123")  # No letters (unless test)
        assert not manager._validate_contract_code_format("abc")  # No numbers (unless test)
        assert not manager._validate_contract_code_format("test with spaces")
        assert not manager._validate_contract_code_format("test/with/slashes")
        assert not manager._validate_contract_code_format("test*with*wildcards")
        
        # Test contracts should be valid even without numbers
        assert manager._validate_contract_code_format("test_contract")
        assert manager._validate_contract_code_format("sample_data")
        assert manager._validate_contract_code_format("demo_run")


class TestContractExistenceCheck:
    """Test contract existence checking."""
    
    def test_check_existing_contract(self, temp_data_dir, sample_contract_data):
        """Test checking existence of existing contract."""
        # Create test contract file
        contract_file = temp_data_dir / "existing_tr_ba_data.parquet"
        sample_contract_data.to_parquet(contract_file)
        
        manager = ContractDataManager(str(temp_data_dir))
        
        assert manager.check_contract_exists("existing") == True
    
    def test_check_nonexistent_contract(self, temp_data_dir):
        """Test checking existence of non-existent contract."""
        manager = ContractDataManager(str(temp_data_dir))
        
        assert manager.check_contract_exists("nonexistent") == False
    
    def test_check_contract_with_invalid_code(self, temp_data_dir):
        """Test checking existence with invalid contract code."""
        manager = ContractDataManager(str(temp_data_dir))
        
        # Should handle invalid codes gracefully
        assert manager.check_contract_exists("") == False
        assert manager.check_contract_exists("invalid/code") == False


class TestContractListing:
    """Test listing available contracts."""
    
    def test_list_contracts_empty_directory(self, temp_data_dir):
        """Test listing contracts in empty directory."""
        manager = ContractDataManager(str(temp_data_dir))
        
        contracts = manager.list_available_contracts()
        assert contracts == []
    
    def test_list_contracts_with_files(self, temp_data_dir, sample_contract_data):
        """Test listing contracts with multiple files."""
        # Create multiple contract files
        contracts_to_create = ["dem07_25", "fra08_25", "gbr07_25"]
        
        for contract in contracts_to_create:
            contract_file = temp_data_dir / f"{contract}_tr_ba_data.parquet"
            sample_contract_data.to_parquet(contract_file)
        
        # Create some non-contract files (should be ignored)
        (temp_data_dir / "not_a_contract.parquet").write_text("test")
        (temp_data_dir / "wrong_format_data.parquet").write_text("test")
        
        manager = ContractDataManager(str(temp_data_dir))
        
        contracts = manager.list_available_contracts()
        assert sorted(contracts) == sorted(contracts_to_create)
    
    def test_list_contracts_sorts_results(self, temp_data_dir, sample_contract_data):
        """Test that contract listing returns sorted results."""
        # Create contracts in random order
        contracts_to_create = ["zebra_25", "alpha_25", "beta_25"]
        
        for contract in contracts_to_create:
            contract_file = temp_data_dir / f"{contract}_tr_ba_data.parquet"
            sample_contract_data.to_parquet(contract_file)
        
        manager = ContractDataManager(str(temp_data_dir))
        
        contracts = manager.list_available_contracts()
        assert contracts == sorted(contracts_to_create)


class TestContractInfo:
    """Test contract information retrieval."""
    
    def test_get_contract_info_existing(self, temp_data_dir, sample_contract_data):
        """Test getting info for existing contract."""
        contract_file = temp_data_dir / "info_test_tr_ba_data.parquet"
        sample_contract_data.to_parquet(contract_file)
        
        manager = ContractDataManager(str(temp_data_dir))
        
        info = manager.get_contract_info("info_test")
        
        assert info['contract_code'] == "info_test"
        assert info['file_exists'] == True
        assert info['file_size_mb'] >= 0  # File might be very small, just check it's a valid number
        assert info['estimated_rows'] is not None
        assert info['columns'] == list(sample_contract_data.columns)
        assert 'last_modified' in info
    
    def test_get_contract_info_nonexistent(self, temp_data_dir):
        """Test getting info for non-existent contract."""
        manager = ContractDataManager(str(temp_data_dir))
        
        with pytest.raises(FileNotFoundError):
            manager.get_contract_info("nonexistent")


class TestDataValidation:
    """Test data validation functionality."""
    
    def test_validate_valid_data(self, temp_data_dir, sample_contract_data):
        """Test validation of valid contract data."""
        manager = ContractDataManager(str(temp_data_dir))
        
        result = manager._validate_contract_data(sample_contract_data, "test")
        
        assert result.is_valid == True
        assert result.error_message == ""
        assert 'row_count' in result.validation_details
        assert result.validation_details['row_count'] == len(sample_contract_data)
    
    def test_validate_invalid_data(self, temp_data_dir, invalid_contract_data):
        """Test validation of invalid contract data."""
        manager = ContractDataManager(str(temp_data_dir))
        
        result = manager._validate_contract_data(invalid_contract_data, "test")
        
        assert result.is_valid == False
        # Should catch any validation error (could be OHLC relationships, non-positive prices, or negative volume)
        error_lower = result.error_message.lower()
        assert any(phrase in error_lower for phrase in ["non-positive prices", "negative volume", "invalid ohlc"])
    
    def test_validate_missing_columns(self, temp_data_dir):
        """Test validation with missing required columns."""
        # Data missing 'volume' column
        incomplete_data = pd.DataFrame({
            'open': [100.0, 101.0],
            'high': [105.0, 106.0],
            'low': [95.0, 96.0],
            'close': [103.0, 104.0]
            # Missing 'volume'
        })
        
        manager = ContractDataManager(str(temp_data_dir))
        
        result = manager._validate_contract_data(incomplete_data, "test")
        
        assert result.is_valid == False
        assert "missing required columns" in result.error_message.lower()
    
    def test_validate_empty_data(self, temp_data_dir):
        """Test validation of empty dataset."""
        empty_data = pd.DataFrame()
        
        manager = ContractDataManager(str(temp_data_dir))
        
        result = manager._validate_contract_data(empty_data, "test")
        
        assert result.is_valid == False
        assert "empty" in result.error_message.lower()
    
    def test_validate_null_data(self, temp_data_dir):
        """Test validation with null input."""
        manager = ContractDataManager(str(temp_data_dir))
        
        result = manager._validate_contract_data(None, "test")
        
        assert result.is_valid == False
        assert "none" in result.error_message.lower()


class TestDataLoading:
    """Test actual data loading functionality."""
    
    def test_load_valid_contract(self, temp_data_dir, sample_contract_data):
        """Test loading valid contract data."""
        contract_file = temp_data_dir / "load_test_tr_ba_data.parquet"
        sample_contract_data.to_parquet(contract_file)
        
        manager = ContractDataManager(str(temp_data_dir))
        
        loaded_data = manager.load_contract_data("load_test")
        
        assert isinstance(loaded_data, pd.DataFrame)
        assert len(loaded_data) == len(sample_contract_data)
        assert list(loaded_data.columns) == list(sample_contract_data.columns)
        assert manager.files_loaded == 1
    
    def test_load_nonexistent_contract(self, temp_data_dir):
        """Test loading non-existent contract."""
        manager = ContractDataManager(str(temp_data_dir))
        
        with pytest.raises(FileNotFoundError):
            manager.load_contract_data("nonexistent")
        
        assert manager.file_not_found_errors == 1
    
    def test_load_invalid_contract_data(self, temp_data_dir, invalid_contract_data):
        """Test loading invalid contract data."""
        contract_file = temp_data_dir / "invalid_test_tr_ba_data.parquet"
        invalid_contract_data.to_parquet(contract_file)
        
        manager = ContractDataManager(str(temp_data_dir))
        
        with pytest.raises(ValueError, match="Data validation failed"):
            manager.load_contract_data("invalid_test")
        
        assert manager.validation_failures == 1


class TestManagerStatistics:
    """Test manager statistics functionality."""
    
    def test_initial_statistics(self, temp_data_dir):
        """Test initial statistics after manager creation."""
        manager = ContractDataManager(str(temp_data_dir))
        
        stats = manager.get_manager_statistics()
        
        assert stats['files_loaded'] == 0
        assert stats['validation_failures'] == 0
        assert stats['file_not_found_errors'] == 0
        assert stats['data_directory'] == str(temp_data_dir)
        assert stats['available_contracts'] == 0
    
    def test_statistics_after_operations(self, temp_data_dir, sample_contract_data):
        """Test statistics after performing operations."""
        # Create test files
        contract_file = temp_data_dir / "stats_test_tr_ba_data.parquet"
        sample_contract_data.to_parquet(contract_file)
        
        manager = ContractDataManager(str(temp_data_dir))
        
        # Load valid contract
        manager.load_contract_data("stats_test")
        
        # Try to load non-existent contract
        try:
            manager.load_contract_data("nonexistent")
        except FileNotFoundError:
            pass
        
        stats = manager.get_manager_statistics()
        
        assert stats['files_loaded'] == 1
        assert stats['file_not_found_errors'] == 1
        assert stats['available_contracts'] == 1


class TestValidationResult:
    """Test ValidationResult class functionality."""
    
    def test_validation_result_creation(self):
        """Test creating ValidationResult objects."""
        # Valid result
        valid_result = ValidationResult(True)
        assert valid_result.is_valid == True
        assert valid_result.error_message == ""
        assert valid_result.warnings == []
        
        # Invalid result with message
        invalid_result = ValidationResult(False, "Test error")
        assert invalid_result.is_valid == False
        assert invalid_result.error_message == "Test error"
    
    def test_validation_result_warnings(self):
        """Test adding warnings to ValidationResult."""
        result = ValidationResult(True)
        
        result.add_warning("Warning 1")
        result.add_warning("Warning 2")
        
        assert len(result.warnings) == 2
        assert "Warning 1" in result.warnings
        assert "Warning 2" in result.warnings
    
    def test_validation_result_details(self):
        """Test adding details to ValidationResult."""
        result = ValidationResult(True)
        
        result.add_detail("rows", 1000)
        result.add_detail("columns", ["open", "high", "low", "close"])
        
        assert result.validation_details["rows"] == 1000
        assert result.validation_details["columns"] == ["open", "high", "low", "close"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])