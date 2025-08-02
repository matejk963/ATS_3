# Phase 1.1.4: Contract Data Manager Foundation

## Overview
**Dependencies**: None (parallel to 1.1.1-1.1.3)  
**Track**: Data Management (Track B)

This micro-phase establishes the foundational contract data management system, including file path resolution, data validation, and basic loading functionality without caching.

## Objectives
1. Create `ContractDataManager` class structure
2. Implement file path resolution logic
3. Add comprehensive data validation functions
4. Write tests for path resolution and validation

## Implementation Steps

### Step 1: Create Contract Data Manager File (`src/gpu_parallel_processing/contract_data_manager.py`)

```python
"""
Contract data loading and management system for GPU parallel processing.

Phase 1.1.4: Foundation with file resolution and data validation.
"""

import pandas as pd
from typing import Dict, Optional, List, Tuple
from pathlib import Path
import logging


class ContractDataManager:
    """
    Contract data manager for efficient loading and validation.
    
    Manages contract data files with automatic path resolution,
    comprehensive data validation, and error handling.
    
    Phase 1.1.4: Foundation implementation with file management.
    Phase 1.1.5: Will add LRU caching and performance optimization.
    """
    
    def __init__(self, data_directory: str = "data"):
        """
        Initialize contract data manager.
        
        Args:
            data_directory: Base directory for contract data files
        """
        self.data_directory = Path(data_directory)
        
        # Statistics tracking
        self.files_loaded = 0
        self.validation_failures = 0
        self.file_not_found_errors = 0
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        
        # Validate data directory
        if not self._validate_data_directory():
            raise ValueError(f"Invalid data directory: {self.data_directory}")
    
    def load_contract_data(self, contract_code: str) -> pd.DataFrame:
        """
        Load contract data from file with validation.
        
        Args:
            contract_code: Contract identifier (e.g., 'dem07_25')
            
        Returns:
            DataFrame with contract OHLCV data
            
        Raises:
            FileNotFoundError: If contract file doesn't exist
            ValueError: If data validation fails
            Exception: For other loading errors
            
        Example:
            >>> manager = ContractDataManager("data")
            >>> data = manager.load_contract_data("dem07_25")
            >>> print(f"Loaded {len(data)} candles")
        """
        try:
            # Resolve file path
            contract_path = self._resolve_contract_path(contract_code)
            
            # Load data
            self.logger.info(f"Loading contract data from: {contract_path}")
            data = pd.read_parquet(contract_path)
            
            # Validate data
            validation_result = self._validate_contract_data(data, contract_code)
            if not validation_result.is_valid:
                self.validation_failures += 1
                raise ValueError(f"Data validation failed for {contract_code}: {validation_result.error_message}")
            
            self.files_loaded += 1
            self.logger.info(f"Successfully loaded {len(data):,} candles from {contract_code}")
            
            return data
            
        except FileNotFoundError as e:
            self.file_not_found_errors += 1
            self.logger.error(f"Contract file not found: {contract_code}")
            raise
        except Exception as e:
            self.logger.error(f"Error loading contract {contract_code}: {e}")
            raise
    
    def check_contract_exists(self, contract_code: str) -> bool:
        """
        Check if contract data file exists without loading it.
        
        Args:
            contract_code: Contract identifier
            
        Returns:
            True if file exists, False otherwise
        """
        try:
            contract_path = self._resolve_contract_path(contract_code)
            return contract_path.exists()
        except Exception:
            return False
    
    def get_contract_info(self, contract_code: str) -> Dict:
        """
        Get basic information about a contract file without loading all data.
        
        Args:
            contract_code: Contract identifier
            
        Returns:
            Dictionary with file information
            
        Raises:
            FileNotFoundError: If contract file doesn't exist
        """
        contract_path = self._resolve_contract_path(contract_code)
        
        if not contract_path.exists():
            raise FileNotFoundError(f"Contract file not found: {contract_path}")
        
        # Get file stats
        file_stat = contract_path.stat()
        file_size_mb = file_stat.st_size / (1024 * 1024)
        
        # Quick peek at data structure (read just first few rows)
        try:
            sample_data = pd.read_parquet(contract_path, nrows=5)
            row_count_estimate = len(sample_data) * (file_stat.st_size / sample_data.memory_usage(deep=True).sum())
        except Exception:
            row_count_estimate = None
        
        return {
            'contract_code': contract_code,
            'file_path': str(contract_path),
            'file_size_mb': round(file_size_mb, 2),
            'file_exists': True,
            'estimated_rows': int(row_count_estimate) if row_count_estimate else None,
            'columns': list(sample_data.columns) if 'sample_data' in locals() else None,
            'last_modified': file_stat.st_mtime
        }
    
    def list_available_contracts(self) -> List[str]:
        """
        List all available contract codes in the data directory.
        
        Returns:
            List of contract codes found in directory
        """
        contract_codes = []
        
        if not self.data_directory.exists():
            return contract_codes
        
        # Look for files matching the pattern: *_tr_ba_data.parquet
        pattern = "*_tr_ba_data.parquet"
        
        for file_path in self.data_directory.glob(pattern):
            # Extract contract code from filename
            filename = file_path.stem  # Remove .parquet extension
            if filename.endswith("_tr_ba_data"):
                contract_code = filename[:-11]  # Remove "_tr_ba_data" suffix
                contract_codes.append(contract_code)
        
        return sorted(contract_codes)
    
    def _validate_data_directory(self) -> bool:
        """
        Validate that data directory exists and is accessible.
        
        Returns:
            True if directory is valid, False otherwise
        """
        try:
            if not isinstance(self.data_directory, Path):
                return False
            
            # Check if directory exists or can be created
            if not self.data_directory.exists():
                self.logger.warning(f"Data directory does not exist: {self.data_directory}")
                return False
            
            if not self.data_directory.is_dir():
                self.logger.error(f"Data path is not a directory: {self.data_directory}")
                return False
            
            # Check read permissions
            if not os.access(self.data_directory, os.R_OK):
                self.logger.error(f"No read permission for data directory: {self.data_directory}")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error validating data directory: {e}")
            return False
    
    def _resolve_contract_path(self, contract_code: str) -> Path:
        """
        Resolve contract code to file path.
        
        Args:
            contract_code: Contract identifier (e.g., 'dem07_25')
            
        Returns:
            Path object for contract file
            
        Raises:
            ValueError: If contract code is invalid
            FileNotFoundError: If contract file doesn't exist
            
        Contract File Naming Convention:
        - Input: 'dem07_25'
        - Output: 'data/dem07_25_tr_ba_data.parquet'
        """
        # Validate contract code format
        if not self._validate_contract_code_format(contract_code):
            raise ValueError(f"Invalid contract code format: {contract_code}")
        
        # Build file path
        contract_file = f"{contract_code}_tr_ba_data.parquet"
        contract_path = self.data_directory / contract_file
        
        # Check if file exists
        if not contract_path.exists():
            # Provide helpful error message with suggestions
            available_contracts = self.list_available_contracts()
            error_msg = f"Contract data file not found: {contract_path}"
            
            if available_contracts:
                error_msg += f"\nAvailable contracts: {', '.join(available_contracts[:5])}"
                if len(available_contracts) > 5:
                    error_msg += f" ... and {len(available_contracts) - 5} more"
            else:
                error_msg += f"\nNo contract files found in {self.data_directory}"
            
            raise FileNotFoundError(error_msg)
        
        return contract_path
    
    def _validate_contract_code_format(self, contract_code: str) -> bool:
        """
        Validate contract code format.
        
        Args:
            contract_code: Contract code to validate
            
        Returns:
            True if format is valid, False otherwise
            
        Expected format examples:
        - dem07_25 (Germany July 2025)
        - fra08_25 (France August 2025)
        - gbr07_25 (Great Britain July 2025)
        """
        if not isinstance(contract_code, str):
            return False
        
        if len(contract_code) == 0:
            return False
        
        # Basic format check - should contain letters and numbers
        if not any(c.isalpha() for c in contract_code):
            return False
        
        if not any(c.isdigit() for c in contract_code):
            return False
        
        # Should not contain spaces or special characters (except underscore)
        if any(c in contract_code for c in [' ', '.', '/', '\\', ':', '*', '?', '"', '<', '>', '|']):
            return False
        
        return True


class ValidationResult:
    """
    Result of data validation with detailed information.
    """
    
    def __init__(self, is_valid: bool, error_message: str = "", warnings: List[str] = None):
        self.is_valid = is_valid
        self.error_message = error_message
        self.warnings = warnings or []
        self.validation_details = {}
    
    def add_warning(self, warning: str):
        """Add a warning message."""
        self.warnings.append(warning)
    
    def add_detail(self, key: str, value):
        """Add validation detail."""
        self.validation_details[key] = value


def _validate_contract_data(self, data: pd.DataFrame, contract_code: str) -> ValidationResult:
    """
    Comprehensive validation of contract data.
    
    Args:
        data: DataFrame to validate
        contract_code: Contract identifier for error messages
        
    Returns:
        ValidationResult with detailed validation information
    """
    result = ValidationResult(True)
    
    try:
        # Check basic structure
        if data is None:
            return ValidationResult(False, "Data is None")
        
        if not isinstance(data, pd.DataFrame):
            return ValidationResult(False, f"Data is not a DataFrame: {type(data)}")
        
        if len(data) == 0:
            return ValidationResult(False, "Dataset is empty")
        
        # Check required columns
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        missing_columns = [col for col in required_columns if col not in data.columns]
        
        if missing_columns:
            return ValidationResult(False, f"Missing required columns: {missing_columns}")
        
        result.add_detail('columns_present', list(data.columns))
        result.add_detail('row_count', len(data))
        
        # Check data types
        numeric_columns = ['open', 'high', 'low', 'close', 'volume']
        for col in numeric_columns:
            if col in data.columns:
                if not pd.api.types.is_numeric_dtype(data[col]):
                    return ValidationResult(False, f"Non-numeric data in column: {col}")
        
        # Check for null values
        null_counts = data[required_columns].isnull().sum()
        total_nulls = null_counts.sum()
        
        if total_nulls > 0:
            null_pct = (total_nulls / (len(data) * len(required_columns))) * 100
            if null_pct > 5:  # More than 5% nulls is an error
                return ValidationResult(False, f"Too many null values: {total_nulls} ({null_pct:.1f}%)")
            else:
                result.add_warning(f"Found {total_nulls} null values ({null_pct:.1f}%)")
        
        result.add_detail('null_values', dict(null_counts))
        
        # Check OHLC relationships
        invalid_ohlc = 0
        
        # High should be >= Low
        if (data['high'] < data['low']).any():
            invalid_ohlc += (data['high'] < data['low']).sum()
        
        # High should be >= Open and Close
        if (data['high'] < data['open']).any():
            invalid_ohlc += (data['high'] < data['open']).sum()
        
        if (data['high'] < data['close']).any():
            invalid_ohlc += (data['high'] < data['close']).sum()
        
        # Low should be <= Open and Close
        if (data['low'] > data['open']).any():
            invalid_ohlc += (data['low'] > data['open']).sum()
        
        if (data['low'] > data['close']).any():
            invalid_ohlc += (data['low'] > data['close']).sum()
        
        if invalid_ohlc > 0:
            invalid_pct = (invalid_ohlc / len(data)) * 100
            if invalid_pct > 1:  # More than 1% invalid OHLC is an error
                return ValidationResult(False, f"Invalid OHLC relationships: {invalid_ohlc} rows ({invalid_pct:.1f}%)")
            else:
                result.add_warning(f"Found {invalid_ohlc} rows with invalid OHLC relationships")
        
        result.add_detail('invalid_ohlc_rows', invalid_ohlc)
        
        # Check for reasonable price ranges
        price_columns = ['open', 'high', 'low', 'close']
        price_stats = data[price_columns].describe()
        
        # Check for non-positive prices
        non_positive = (data[price_columns] <= 0).any(axis=1).sum()
        if non_positive > 0:
            return ValidationResult(False, f"Found {non_positive} rows with non-positive prices")
        
        # Check for extreme price values (potential data errors)
        for col in price_columns:
            col_max = data[col].max()
            col_min = data[col].min()
            col_mean = data[col].mean()
            
            # Flag if max is more than 100x the mean (potential outlier)
            if col_max > col_mean * 100:
                result.add_warning(f"Potential outlier in {col}: max={col_max:.2f}, mean={col_mean:.2f}")
            
            # Flag if min is less than 1% of mean (potential data error)
            if col_min < col_mean * 0.01:
                result.add_warning(f"Potential data error in {col}: min={col_min:.2f}, mean={col_mean:.2f}")
        
        result.add_detail('price_statistics', price_stats.to_dict())
        
        # Check volume data
        if 'volume' in data.columns:
            volume_stats = data['volume'].describe()
            
            # Check for negative volume
            negative_volume = (data['volume'] < 0).sum()
            if negative_volume > 0:
                return ValidationResult(False, f"Found {negative_volume} rows with negative volume")
            
            # Check for zero volume (warning, not error)
            zero_volume = (data['volume'] == 0).sum()
            if zero_volume > 0:
                zero_pct = (zero_volume / len(data)) * 100
                if zero_pct > 10:  # More than 10% zero volume is suspicious
                    result.add_warning(f"High percentage of zero volume: {zero_volume} rows ({zero_pct:.1f}%)")
            
            result.add_detail('volume_statistics', volume_stats.to_dict())
            result.add_detail('zero_volume_rows', zero_volume)
        
        # Check index/timestamp if present
        if hasattr(data.index, 'is_monotonic_increasing'):
            if not data.index.is_monotonic_increasing:
                result.add_warning("Index is not monotonically increasing (data may not be time-sorted)")
        
        result.add_detail('data_types', data.dtypes.to_dict())
        result.add_detail('memory_usage_mb', data.memory_usage(deep=True).sum() / 1024 / 1024)
        
        return result
        
    except Exception as e:
        return ValidationResult(False, f"Validation error: {str(e)}")


# Add the validation method to the ContractDataManager class
ContractDataManager._validate_contract_data = _validate_contract_data


def get_manager_statistics(self) -> Dict:
    """
    Get statistics about the data manager's operations.
    
    Returns:
        Dictionary with operation statistics
    """
    return {
        'files_loaded': self.files_loaded,
        'validation_failures': self.validation_failures,
        'file_not_found_errors': self.file_not_found_errors,
        'data_directory': str(self.data_directory),
        'available_contracts': len(self.list_available_contracts())
    }


# Add the statistics method to the ContractDataManager class
ContractDataManager.get_manager_statistics = get_manager_statistics


# Import os for file permissions check
import os


if __name__ == "__main__":
    # Quick test of contract data manager
    print("🧪 Testing Contract Data Manager Foundation...")
    
    try:
        # Initialize manager
        manager = ContractDataManager("data")
        print(f"✅ Manager initialized with directory: {manager.data_directory}")
        
        # List available contracts
        contracts = manager.list_available_contracts()
        print(f"📋 Available contracts: {contracts}")
        
        # Test contract existence check
        if contracts:
            test_contract = contracts[0]
            exists = manager.check_contract_exists(test_contract)
            print(f"✅ Contract {test_contract} exists: {exists}")
            
            # Get contract info
            info = manager.get_contract_info(test_contract)
            print(f"📊 Contract info: {info}")
        else:
            print("⚠️  No contracts found for testing")
        
        # Get manager statistics
        stats = manager.get_manager_statistics()
        print(f"📈 Manager statistics: {stats}")
        
        print("✅ Contract Data Manager foundation ready!")
        
    except Exception as e:
        print(f"❌ Error testing manager: {e}")
```

### Step 2: Create Test File (`tests/test_contract_data_manager_foundation.py`)

```python
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
        assert not manager._validate_contract_code_format("123")  # No letters
        assert not manager._validate_contract_code_format("abc")  # No numbers
        assert not manager._validate_contract_code_format("test with spaces")
        assert not manager._validate_contract_code_format("test/with/slashes")
        assert not manager._validate_contract_code_format("test*with*wildcards")


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
        assert info['file_size_mb'] > 0
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
        assert "non-positive prices" in result.error_message.lower() or "negative volume" in result.error_message.lower()
    
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
```

### Step 3: Create Validation Script (`validate_phase_1_1_4.py`)

```python
"""
Validation script for Phase 1.1.4 completion.

Run this script to verify that Phase 1.1.4 is properly implemented.
"""

import sys
import tempfile
import pandas as pd
from pathlib import Path

def validate_phase_1_1_4():
    """Validate Phase 1.1.4 implementation."""
    print("🔍 Validating Phase 1.1.4: Contract Data Manager Foundation...")
    
    success = True
    
    # Check imports
    try:
        from src.gpu_parallel_processing.contract_data_manager import (
            ContractDataManager,
            ValidationResult
        )
        print("✅ Phase 1.1.4 imports successful")
    except ImportError as e:
        print(f"❌ Import error: {e}")
        success = False
        return False
    
    # Test basic initialization
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ContractDataManager(temp_dir)
            print("✅ Manager initialization successful")
        
    except Exception as e:
        print(f"❌ Manager initialization failed: {e}")
        success = False
    
    # Test contract code validation
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ContractDataManager(temp_dir)
            
            # Test valid codes
            valid_codes = ["dem07_25", "fra08_25", "test123"]
            for code in valid_codes:
                if not manager._validate_contract_code_format(code):
                    print(f"❌ Valid contract code rejected: {code}")
                    success = False
            
            # Test invalid codes
            invalid_codes = ["", "123", "abc", "test with spaces"]
            for code in invalid_codes:
                if manager._validate_contract_code_format(code):
                    print(f"❌ Invalid contract code accepted: {code}")
                    success = False
            
            print("✅ Contract code validation working")
            
    except Exception as e:
        print(f"❌ Contract code validation error: {e}")
        success = False
    
    # Test file operations
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ContractDataManager(temp_dir)
            
            # Test empty directory
            contracts = manager.list_available_contracts()
            if contracts != []:
                print(f"❌ Expected empty contract list, got: {contracts}")
                success = False
            else:
                print("✅ Empty directory handling working")
            
            # Test contract existence check
            exists = manager.check_contract_exists("nonexistent")
            if exists:
                print("❌ Non-existent contract reported as existing")
                success = False
            else:
                print("✅ Contract existence check working")
                
    except Exception as e:
        print(f"❌ File operations error: {e}")
        success = False
    
    # Test data validation
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ContractDataManager(temp_dir)
            
            # Test valid data
            valid_data = pd.DataFrame({
                'open': [100.0, 101.0, 102.0],
                'high': [105.0, 106.0, 107.0],
                'low': [95.0, 96.0, 97.0],
                'close': [103.0, 104.0, 105.0],
                'volume': [1000, 1100, 1200]
            })
            
            result = manager._validate_contract_data(valid_data, "test")
            if not result.is_valid:
                print(f"❌ Valid data rejected: {result.error_message}")
                success = False
            else:
                print("✅ Valid data validation working")
            
            # Test invalid data
            invalid_data = pd.DataFrame({
                'open': [100.0, -101.0],  # Negative price
                'high': [105.0, 106.0],
                'low': [95.0, 96.0],
                'close': [103.0, 104.0],
                'volume': [1000, 1100]
            })
            
            result = manager._validate_contract_data(invalid_data, "test")
            if result.is_valid:
                print("❌ Invalid data accepted")
                success = False
            else:
                print("✅ Invalid data validation working")
                
    except Exception as e:
        print(f"❌ Data validation error: {e}")
        success = False
    
    # Test ValidationResult class
    try:
        result = ValidationResult(True)
        result.add_warning("Test warning")
        result.add_detail("test_key", "test_value")
        
        if len(result.warnings) != 1 or result.validation_details.get("test_key") != "test_value":
            print("❌ ValidationResult functionality incorrect")
            success = False
        else:
            print("✅ ValidationResult class working")
            
    except Exception as e:
        print(f"❌ ValidationResult error: {e}")
        success = False
    
    # Test with actual contract file
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ContractDataManager(temp_dir)
            
            # Create test contract file
            test_data = pd.DataFrame({
                'open': [100.0, 101.0, 102.0],
                'high': [105.0, 106.0, 107.0],
                'low': [95.0, 96.0, 97.0],
                'close': [103.0, 104.0, 105.0],
                'volume': [1000, 1100, 1200]
            })
            
            contract_file = Path(temp_dir) / "test_contract_tr_ba_data.parquet"
            test_data.to_parquet(contract_file)
            
            # Test contract listing
            contracts = manager.list_available_contracts()
            if "test_contract" not in contracts:
                print("❌ Contract file not detected in listing")
                success = False
            else:
                print("✅ Contract file detection working")
            
            # Test contract info
            info = manager.get_contract_info("test_contract")
            if not info['file_exists'] or info['contract_code'] != "test_contract":
                print("❌ Contract info incorrect")
                success = False
            else:
                print("✅ Contract info working")
            
            # Test actual data loading
            loaded_data = manager.load_contract_data("test_contract")
            if len(loaded_data) != len(test_data):
                print("❌ Data loading size mismatch")
                success = False
            else:
                print("✅ Data loading working")
                
    except Exception as e:
        print(f"❌ File operations with real data error: {e}")
        success = False
    
    # Test manager statistics
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ContractDataManager(temp_dir)
            
            stats = manager.get_manager_statistics()
            required_keys = ['files_loaded', 'validation_failures', 'file_not_found_errors', 
                           'data_directory', 'available_contracts']
            
            for key in required_keys:
                if key not in stats:
                    print(f"❌ Missing statistics key: {key}")
                    success = False
            
            if success:
                print("✅ Manager statistics working")
                
    except Exception as e:
        print(f"❌ Manager statistics error: {e}")
        success = False
    
    # Check test file exists
    test_file = Path("tests/test_contract_data_manager_foundation.py")
    if test_file.exists():
        print(f"✅ Test file exists: {test_file}")
    else:
        print(f"❌ Missing test file: {test_file}")
        success = False
    
    # Run tests
    try:
        print("\n🧪 Running foundation tests...")
        import subprocess
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "tests/test_contract_data_manager_foundation.py", 
            "-v", "--tb=short"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ All foundation tests passed")
        else:
            print(f"❌ Foundation tests failed:\n{result.stdout}\n{result.stderr}")
            success = False
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        success = False
    
    if success:
        print("\n🎉 Phase 1.1.4 validation PASSED!")
        print("✅ Contract Data Manager foundation is ready")
        print("🚀 Ready to proceed to Phase 1.1.5: Cache Implementation")
        return True
    else:
        print("\n❌ Phase 1.1.4 validation FAILED!")
        print("Please fix the issues before proceeding.")
        return False

if __name__ == "__main__":
    validate_phase_1_1_4()
```

## Success Criteria for Phase 1.1.4

### Functional Requirements:
- ✅ ContractDataManager class with initialization and configuration
- ✅ File path resolution with contract code validation
- ✅ Comprehensive data validation with detailed error reporting
- ✅ Contract existence checking and listing functionality
- ✅ Basic data loading with validation integration

### Testing Requirements:
- ✅ Unit tests for all manager functionality
- ✅ File operations testing with temporary directories
- ✅ Data validation testing with valid/invalid datasets
- ✅ Error handling and edge case testing
- ✅ Statistics and information retrieval testing

### Quality Requirements:
- ✅ Proper error handling with informative messages
- ✅ Comprehensive data validation with warnings and details
- ✅ Clear separation of concerns (validation vs loading)
- ✅ Statistical tracking of operations
- ✅ Logging integration for debugging

## Next Steps
Upon successful validation of Phase 1.1.4, proceed to **Phase 1.1.5: Cache Implementation** which will add LRU caching, memory management, and performance optimization to the foundation established here.

## TDD Cycle for Phase 1.1.4
1. **RED**: Write failing tests for file operations and validation
2. **GREEN**: Implement file resolution and data validation
3. **REFACTOR**: Improve error handling and validation details
4. **VALIDATE**: Run comprehensive foundation tests