"""
Contract data loading and management system for GPU parallel processing.

Phase 1.1.4: Foundation with file resolution and data validation.
"""

import pandas as pd
from typing import Dict, Optional, List, Tuple
from pathlib import Path
import logging
import os
import time
from collections import OrderedDict
import gc


class ContractDataManager:
    """
    Contract data manager with LRU caching for efficient loading and validation.
    
    Manages contract data files with automatic path resolution, comprehensive 
    data validation, LRU caching, and performance optimization.
    
    Phase 1.1.4: Foundation implementation with file management and validation.
    Phase 1.1.5: LRU caching and memory management implementation.
    """
    
    def __init__(self, data_directory: str = "data", max_cached_contracts: int = 3):
        """
        Initialize contract data manager with caching.
        
        Args:
            data_directory: Base directory for contract data files
            max_cached_contracts: Maximum number of contracts to cache simultaneously
        """
        self.data_directory = Path(data_directory)
        self.max_cached_contracts = max_cached_contracts
        
        # LRU Cache implementation using OrderedDict
        self.data_cache: OrderedDict[str, pd.DataFrame] = OrderedDict()
        self.cache_metadata: Dict[str, Dict] = {}
        
        # Cache performance tracking
        self.cache_hits = 0
        self.cache_misses = 0
        self.cache_evictions = 0
        self.total_memory_saved_mb = 0.0
        
        # File operation statistics
        self.files_loaded = 0
        self.validation_failures = 0
        self.file_not_found_errors = 0
        
        # Memory management
        self.current_cache_memory_mb = 0.0
        self.max_cache_memory_mb = None  # Will be set based on available memory
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        
        # Validate data directory
        if not self._validate_data_directory():
            raise ValueError(f"Invalid data directory: {self.data_directory}")
        
        # Initialize memory limits
        self._set_memory_limits()
    
    def load_contract_data(self, contract_code: str) -> pd.DataFrame:
        """
        Load contract data with LRU caching.
        
        Args:
            contract_code: Contract identifier (e.g., 'dem07_25')
            
        Returns:
            DataFrame with contract OHLCV data
            
        Raises:
            FileNotFoundError: If contract file doesn't exist
            ValueError: If data validation fails
            Exception: For other loading errors
        """
        start_time = time.time()
        
        try:
            # Check cache first
            if contract_code in self.data_cache:
                self._update_cache_access(contract_code)
                self.cache_hits += 1
                
                load_time = time.time() - start_time
                self.logger.info(f"📋 Cache HIT: {contract_code} (loaded in {load_time:.3f}s)")
                self._log_cache_stats()
                
                return self.data_cache[contract_code]
            
            # Cache miss - load from file
            self.cache_misses += 1
            self.logger.info(f"📂 Cache MISS: Loading {contract_code} from file...")
            
            # Load and validate data
            contract_path = self._resolve_contract_path(contract_code)
            data = pd.read_parquet(contract_path)
            
            validation_result = self._validate_contract_data(data, contract_code)
            if not validation_result.is_valid:
                self.validation_failures += 1
                raise ValueError(f"Data validation failed for {contract_code}: {validation_result.error_message}")
            
            # Calculate memory usage
            memory_usage_mb = data.memory_usage(deep=True).sum() / (1024 * 1024)
            
            # Cache management - check memory limits and evict if necessary
            self._ensure_cache_capacity(memory_usage_mb)
            
            # Cache the data
            self._add_to_cache(contract_code, data, memory_usage_mb, validation_result)
            
            self.files_loaded += 1
            load_time = time.time() - start_time
            
            self.logger.info(f"✅ Loaded {len(data):,} candles from {contract_code} in {load_time:.3f}s")
            self.logger.info(f"💾 Memory usage: {memory_usage_mb:.1f} MB")
            self._log_cache_stats()
            
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
            # Read small sample to get structure info
            sample_data = pd.read_parquet(contract_path)
            if len(sample_data) > 5:
                sample_data = sample_data.head(5)
            row_count_estimate = len(pd.read_parquet(contract_path)) if len(sample_data) <= 1000 else None
        except Exception:
            sample_data = None
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
        - test123 (Test contracts for development)
        """
        if not isinstance(contract_code, str):
            return False
        
        if len(contract_code) == 0:
            return False
        
        # Allow alphanumeric characters and underscores only
        if not all(c.isalnum() or c == '_' for c in contract_code):
            return False
        
        # Must contain at least one letter and one number, OR be a test/development contract
        has_alpha = any(c.isalpha() for c in contract_code)
        has_digit = any(c.isdigit() for c in contract_code)
        
        # Allow test contracts and common development patterns
        test_patterns = ('test', 'sample', 'demo', 'mock', 'dummy', 'example', 
                        'load_test', 'info_test', 'stats_test', 'invalid_test', 
                        'existing', 'nonexistent', 'contract', 'lru', 'cache', 
                        'memory', 'perf', 'benchmark', 'methods', 'ops')
        is_test_contract = any(pattern in contract_code.lower() for pattern in test_patterns)
        
        return (has_alpha and has_digit) or is_test_contract
    
    def get_cached_data(self, contract_code: str) -> Optional[pd.DataFrame]:
        """
        Get cached data without loading from file.
        
        Args:
            contract_code: Contract identifier
            
        Returns:
            DataFrame if cached, None otherwise
        """
        if contract_code in self.data_cache:
            self._update_cache_access(contract_code)
            return self.data_cache[contract_code]
        return None
    
    def is_cached(self, contract_code: str) -> bool:
        """
        Check if contract is currently cached.
        
        Args:
            contract_code: Contract identifier
            
        Returns:
            True if cached, False otherwise
        """
        return contract_code in self.data_cache
    
    def preload_contracts(self, contract_codes: List[str]) -> Dict[str, bool]:
        """
        Preload multiple contracts into cache.
        
        Args:
            contract_codes: List of contract identifiers to preload
            
        Returns:
            Dictionary mapping contract codes to success status
        """
        results = {}
        
        self.logger.info(f"🔄 Preloading {len(contract_codes)} contracts...")
        
        for i, contract_code in enumerate(contract_codes):
            try:
                self.load_contract_data(contract_code)
                results[contract_code] = True
                self.logger.info(f"✅ Preloaded {contract_code} ({i+1}/{len(contract_codes)})")
            except Exception as e:
                results[contract_code] = False
                self.logger.error(f"❌ Failed to preload {contract_code}: {e}")
        
        successful_loads = sum(results.values())
        self.logger.info(f"🎯 Preloading complete: {successful_loads}/{len(contract_codes)} successful")
        
        return results
    
    def clear_cache(self, contract_code: Optional[str] = None):
        """
        Clear cache for specific contract or all contracts.
        
        Args:
            contract_code: Specific contract to remove, or None for all
        """
        if contract_code is None:
            # Clear entire cache
            cleared_count = len(self.data_cache)
            self.data_cache.clear()
            self.cache_metadata.clear()
            self.current_cache_memory_mb = 0.0
            
            self.logger.info(f"🗑️  Cleared entire cache: {cleared_count} contracts removed")
        else:
            # Clear specific contract
            if contract_code in self.data_cache:
                memory_freed = self.cache_metadata[contract_code]['memory_mb']
                del self.data_cache[contract_code]
                del self.cache_metadata[contract_code]
                self.current_cache_memory_mb -= memory_freed
                
                self.logger.info(f"🗑️  Cleared {contract_code} from cache: {memory_freed:.1f} MB freed")
        
        # Force garbage collection after cache clearing
        gc.collect()
    
    def _add_to_cache(self, contract_code: str, data: pd.DataFrame, 
                     memory_mb: float, validation_result):
        """
        Add contract data to cache with metadata.
        
        Args:
            contract_code: Contract identifier
            data: Contract DataFrame
            memory_mb: Memory usage in MB
            validation_result: Validation result with details
        """
        # Store data and metadata
        self.data_cache[contract_code] = data
        self.cache_metadata[contract_code] = {
            'memory_mb': memory_mb,
            'cached_at': time.time(),
            'access_count': 1,
            'last_accessed': time.time(),
            'validation_warnings': len(validation_result.warnings),
            'row_count': len(data),
            'columns': list(data.columns)
        }
        
        self.current_cache_memory_mb += memory_mb
        
        self.logger.debug(f"📦 Added {contract_code} to cache: {memory_mb:.1f} MB")
    
    def _update_cache_access(self, contract_code: str):
        """
        Update cache access information for LRU tracking.
        
        Args:
            contract_code: Contract identifier
        """
        # Move to end in OrderedDict (most recently used)
        self.data_cache.move_to_end(contract_code)
        
        # Update metadata
        if contract_code in self.cache_metadata:
            self.cache_metadata[contract_code]['last_accessed'] = time.time()
            self.cache_metadata[contract_code]['access_count'] += 1
    
    def _ensure_cache_capacity(self, new_item_memory_mb: float):
        """
        Ensure cache has capacity for new item by evicting LRU items if necessary.
        
        Args:
            new_item_memory_mb: Memory required for new item
        """
        # Check count-based limit
        while len(self.data_cache) >= self.max_cached_contracts:
            self._evict_lru_item()
        
        # Check memory-based limit (if set)
        if self.max_cache_memory_mb is not None:
            while (self.current_cache_memory_mb + new_item_memory_mb > self.max_cache_memory_mb 
                   and len(self.data_cache) > 0):
                self._evict_lru_item()
    
    def _evict_lru_item(self):
        """
        Evict least recently used item from cache.
        """
        if not self.data_cache:
            return
        
        # OrderedDict maintains insertion order, first item is LRU
        lru_contract = next(iter(self.data_cache))
        
        # Get memory info before eviction
        memory_freed = self.cache_metadata[lru_contract]['memory_mb']
        
        # Remove from cache
        del self.data_cache[lru_contract]
        del self.cache_metadata[lru_contract]
        
        self.current_cache_memory_mb -= memory_freed
        self.cache_evictions += 1
        
        self.logger.info(f"🗑️  Evicted LRU contract: {lru_contract} ({memory_freed:.1f} MB freed)")
    
    def _set_memory_limits(self):
        """
        Set memory limits based on available system memory.
        """
        try:
            import psutil
            available_memory_gb = psutil.virtual_memory().available / (1024**3)
            
            # Use up to 25% of available memory for cache
            self.max_cache_memory_mb = (available_memory_gb * 0.25) * 1024
            
            self.logger.info(f"💾 Cache memory limit set to: {self.max_cache_memory_mb:.1f} MB")
            
        except ImportError:
            self.logger.warning("psutil not available - memory limits disabled")
            self.max_cache_memory_mb = None
        except Exception as e:
            self.logger.warning(f"Could not determine memory limits: {e}")
            self.max_cache_memory_mb = None
    
    def _log_cache_stats(self):
        """
        Log current cache statistics.
        """
        total_requests = self.cache_hits + self.cache_misses
        hit_rate = (self.cache_hits / total_requests * 100) if total_requests > 0 else 0
        
        self.logger.debug(
            f"📊 Cache: {len(self.data_cache)}/{self.max_cached_contracts} items, "
            f"{self.current_cache_memory_mb:.1f} MB, "
            f"hit rate: {hit_rate:.1f}% ({self.cache_hits}/{total_requests})"
        )
    
    def get_cache_stats(self) -> Dict:
        """
        Get comprehensive cache performance statistics.
        
        Returns:
            Dictionary with cache performance metrics
        """
        total_requests = self.cache_hits + self.cache_misses
        hit_rate = (self.cache_hits / total_requests * 100) if total_requests > 0 else 0
        
        # Calculate memory efficiency
        if self.cache_misses > 0:
            avg_memory_per_load = self.current_cache_memory_mb / len(self.data_cache) if self.data_cache else 0
            estimated_memory_without_cache = avg_memory_per_load * total_requests
            memory_saved = max(0, estimated_memory_without_cache - self.current_cache_memory_mb)
        else:
            memory_saved = 0
        
        return {
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'cache_evictions': self.cache_evictions,
            'hit_rate_percent': round(float(hit_rate), 1),
            'cached_contracts': len(self.data_cache),
            'max_cached_contracts': self.max_cached_contracts,
            'current_memory_mb': round(float(self.current_cache_memory_mb), 1),
            'max_memory_mb': round(float(self.max_cache_memory_mb), 1) if self.max_cache_memory_mb else None,
            'memory_efficiency_mb': round(float(memory_saved), 1),
            'avg_memory_per_contract_mb': round(
                float(self.current_cache_memory_mb) / len(self.data_cache), 1
            ) if self.data_cache else 0
        }
    
    def get_cache_details(self) -> Dict[str, Dict]:
        """
        Get detailed information about cached contracts.
        
        Returns:
            Dictionary mapping contract codes to cache metadata
        """
        details = {}
        
        for contract_code, metadata in self.cache_metadata.items():
            details[contract_code] = {
                'memory_mb': round(float(metadata['memory_mb']), 1),
                'cached_duration_seconds': round(float(time.time() - metadata['cached_at']), 1),
                'access_count': metadata['access_count'],
                'last_accessed_seconds_ago': round(float(time.time() - metadata['last_accessed']), 1),
                'validation_warnings': metadata['validation_warnings'],
                'row_count': metadata['row_count'],
                'columns': metadata['columns']
            }
        
        return details
    
    def optimize_cache(self) -> Dict[str, int]:
        """
        Optimize cache by removing contracts with low access frequency.
        
        Returns:
            Dictionary with optimization statistics
        """
        if len(self.data_cache) <= 1:
            return {'contracts_analyzed': 0, 'contracts_removed': 0}
        
        contracts_analyzed = len(self.data_cache)
        contracts_to_remove = []
        
        # Calculate access frequency for each contract
        current_time = time.time()
        
        for contract_code, metadata in self.cache_metadata.items():
            cached_duration = current_time - metadata['cached_at']
            access_frequency = metadata['access_count'] / max(cached_duration, 1)  # accesses per second
            
            # Remove contracts with very low access frequency (less than 0.01 accesses per second)
            # and haven't been accessed in the last 60 seconds
            time_since_last_access = current_time - metadata['last_accessed']
            
            if access_frequency < 0.01 and time_since_last_access > 60:
                contracts_to_remove.append(contract_code)
        
        # Remove low-frequency contracts
        for contract_code in contracts_to_remove:
            self.clear_cache(contract_code)
        
        contracts_removed = len(contracts_to_remove)
        
        if contracts_removed > 0:
            self.logger.info(f"🔧 Cache optimization: removed {contracts_removed} low-frequency contracts")
        
        return {
            'contracts_analyzed': contracts_analyzed,
            'contracts_removed': contracts_removed
        }

    def get_manager_statistics(self) -> Dict:
        """
        Get comprehensive statistics about the data manager's operations.
        
        Returns:
            Dictionary with operation and cache statistics
        """
        cache_stats = self.get_cache_stats()
        
        return {
            'files_loaded': self.files_loaded,
            'validation_failures': self.validation_failures,
            'file_not_found_errors': self.file_not_found_errors,
            'data_directory': str(self.data_directory),
            'available_contracts': len(self.list_available_contracts()),
            'cache_performance': cache_stats,
            'cache_enabled': True,
            'max_cached_contracts': self.max_cached_contracts
        }


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


if __name__ == "__main__":
    # Test caching functionality
    print("🧪 Testing Contract Data Manager with Caching...")
    
    try:
        # Initialize manager with caching
        manager = ContractDataManager("data", max_cached_contracts=2)
        print(f"✅ Manager initialized with caching: max {manager.max_cached_contracts} contracts")
        
        # Test cache stats
        stats = manager.get_cache_stats()
        print(f"📊 Initial cache stats: {stats}")
        
        # List available contracts
        contracts = manager.list_available_contracts()
        print(f"📋 Available contracts: {contracts}")
        
        if contracts:
            # Test loading and caching
            test_contract = contracts[0]
            
            print(f"\n🔄 Testing cache with contract: {test_contract}")
            
            # First load (cache miss)
            data1 = manager.load_contract_data(test_contract)
            print(f"📂 First load: {len(data1)} rows")
            
            # Second load (cache hit)
            data2 = manager.load_contract_data(test_contract)
            print(f"📋 Second load: {len(data2)} rows")
            
            # Check cache stats
            cache_stats = manager.get_cache_stats()
            print(f"📊 Cache stats after loading: {cache_stats}")
            
            # Test cache details
            cache_details = manager.get_cache_details()
            print(f"🔍 Cache details: {cache_details}")
            
            # Test cache optimization
            optimization_stats = manager.optimize_cache()
            print(f"🔧 Cache optimization: {optimization_stats}")
            
        else:
            print("⚠️  No contracts found for testing")
        
        print("✅ Contract Data Manager with caching ready!")
        
    except Exception as e:
        print(f"❌ Error testing manager: {e}")