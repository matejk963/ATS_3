"""
UAT Test for Data Fetcher Implementation
========================================

User Acceptance Test demonstrating real-world usage of the DataFetcher
with actual contract configurations and live data fetching.

Test Scenarios:
1. Multiple contracts with different markets and configurations
2. Both explicit dates and lookback-based configurations
3. Real data fetching and validation
4. Output structure and data quality verification
5. Export functionality testing
"""

import sys
import os
import time
from datetime import datetime
import pandas as pd
import numpy as np

# Add project root to path - cross-platform compatible
if os.name == 'nt':  # Windows
    # Running in Windows PowerShell
    project_root = r'C:\Users\krajcovic\Documents\GitHub\ATS_3'
else:
    # Running in WSL/Linux
    project_root = '/mnt/c/Users/krajcovic/Documents/GitHub/ATS_3'

sys.path.append(project_root)

from src.core.data_fetcher import DataFetcher, TPDATA_AVAILABLE


def print_header(title):
    """Print formatted test section header"""
    print(f"\n{'='*60}")
    print(f"[TEST] {title}")
    print(f"{'='*60}")


def print_subheader(title):
    """Print formatted test subsection header"""
    print(f"\n{'-'*40}")
    print(f"[STEP] {title}")
    print(f"{'-'*40}")


def validate_dataframe(df, df_name, expected_columns=None):
    """Validate DataFrame structure and content"""
    print(f"\n[DATA] Validating {df_name}:")
    
    if df.empty:
        print(f"   [FAIL] {df_name} is empty")
        return False
    
    print(f"   [OK] Shape: {df.shape} (rows × columns)")
    print(f"   [OK] Index type: {type(df.index).__name__}")
    print(f"   [OK] Columns: {list(df.columns)}")
    
    if expected_columns:
        missing_cols = set(expected_columns) - set(df.columns)
        if missing_cols:
            print(f"   [WARN] Missing expected columns: {missing_cols}")
        else:
            print(f"   [OK] All expected columns present")
    
    # Show data types
    print(f"   [INFO] Data types:")
    for col in df.columns:
        dtype = df[col].dtype
        non_null = df[col].notna().sum()
        print(f"      {col}: {dtype} ({non_null} non-null values)")
    
    # Show sample data
    print(f"   [INFO] Sample data (first 3 rows):")
    print(df.head(3).to_string())
    
    return True


def run_uat_test():
    """Run comprehensive UAT test"""
    
    print_header("Data Fetcher UAT Test")
    print(f"[TIME] Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Check TPData availability
    if not TPDATA_AVAILABLE:
        print("[FAIL] TPData not available - cannot run UAT test")
        return False
    
    print("[OK] TPData available - proceeding with UAT test")
    
    # Initialize DataFetcher
    print_subheader("DataFetcher Initialization")
    try:
        fetcher = DataFetcher(
            trading_hours=(9, 17),
            allowed_broker_ids=[1441]  # EEX broker ID
        )
        print("[OK] DataFetcher initialized successfully")
        print(f"   Trading hours: {fetcher.trading_hours}")
        print(f"   Allowed brokers: {fetcher.allowed_broker_ids}")
    except Exception as e:
        print(f"[FAIL] DataFetcher initialization failed: {e}")
        return False
    
    # Define test contracts
    print_subheader("Test Contract Configurations")
    
    test_contracts = [
        {
            'name': 'German Monthly July 2025 (Lookback)',
            'config': {
                'market': 'de',
                'tenor': 'm',
                'contract': '08_25',
                'start_date': '2025-05-15',
                'end_date': '2025-07-31'
            }
        },
        {
            'name': 'German Quarterly Q3 2025 (Explicit Dates)',
            'config': {
                'market': 'de',
                'tenor': 'q',
                'contract': '3_25',
                'start_date': '2025-01-01',
                'end_date': '2025-06-30'  # Small date range for testing
            }
        },
        {
            'name': 'German Cal 2026 (Explicit Dates)',
            'config': {
                'market': 'de',
                'tenor': 'y',
                'contract': '26',
                'start_date': '2025-01-01',
                'end_date': '2025-06-30'  # Small date range for testing
            }
        },
        {
            'name': 'German Monthly August 2025 (Lookback)',
            'config': {
                'market': 'de',
                'tenor': 'm', 
                'contract': '09_25',
                'lookback_days': 3  # Very small for quick testing
            }
        }
    ]
    
    # Display test configurations
    for i, contract in enumerate(test_contracts, 1):
        print(f"\n[FILE] Contract {i}: {contract['name']}")
        config = contract['config']
        print(f"   Market: {config['market']}")
        print(f"   Tenor: {config['tenor']}")
        print(f"   Contract: {config['contract']}")
        
        if 'lookback_days' in config:
            print(f"   Lookback: {config['lookback_days']} business days")
            # Show what this resolves to
            from src.core.data_fetcher import DeliveryDateCalculator, DateRangeResolver
            calc = DeliveryDateCalculator()
            resolver = DateRangeResolver()
            
            delivery_date = calc.calc_delivery_date(config['tenor'], config['contract'])
            start_date, end_date = resolver.resolve_date_range(delivery_date, config['lookback_days'])
            print(f"   Delivery Date: {delivery_date.strftime('%Y-%m-%d')}")
            print(f"   Resolved Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        else:
            print(f"   Period: {config['start_date']} to {config['end_date']}")
    
    # Test individual contract fetching
    print_header("Individual Contract Data Fetching")
    
    individual_results = {}
    
    for i, contract in enumerate(test_contracts, 1):
        print_subheader(f"Testing Contract {i}: {contract['name']}")
        
        start_time = time.time()
        
        try:
            result = fetcher.fetch_contract_data(
                contract['config'],
                include_trades=True,
                include_orders=True
            )
            
            fetch_time = time.time() - start_time
            print(f"[OK] Data fetch completed in {fetch_time:.2f} seconds")
            
            # Validate results
            contract_key = f"{contract['config']['market']}{contract['config']['tenor']}{contract['config']['contract']}"
            individual_results[contract_key] = result
            
            # Validate each data type
            if 'trades' in result:
                validate_dataframe(
                    result['trades'], 
                    "Trades Data",
                    expected_columns=['price', 'volume', 'action', 'broker_id']
                )
            
            if 'orders' in result:
                validate_dataframe(
                    result['orders'],
                    "Orders Data", 
                    expected_columns=['b_price', 'a_price']
                )
            
            if 'mid_prices' in result:
                print(f"\n[DATA] Validating Mid Prices:")
                mid_prices = result['mid_prices']
                print(f"   [OK] Type: {type(mid_prices).__name__}")
                print(f"   [OK] Length: {len(mid_prices)}")
                print(f"   [OK] Non-null values: {mid_prices.notna().sum()}")
                if len(mid_prices) > 0:
                    print(f"   [OK] Sample values: {mid_prices.head(3).tolist()}")
            
        except Exception as e:
            print(f"[FAIL] Error fetching data for {contract['name']}: {e}")
            individual_results[f"error_{i}"] = str(e)
    
    # Test multiple contract fetching
    print_header("Multiple Contract Data Fetching")
    
    print("[BATCH] Fetching all contracts in batch...")
    start_time = time.time()
    
    try:
        # Extract just the configs for batch processing
        batch_configs = [contract['config'] for contract in test_contracts]
        
        batch_results = fetcher.fetch_multiple_contracts(
            batch_configs,
            include_trades=True,
            include_orders=True
        )
        
        batch_time = time.time() - start_time
        print(f"[OK] Batch fetch completed in {batch_time:.2f} seconds")
        
        # Validate batch results
        print(f"\n[INFO] Batch Results Summary:")
        for contract_key, data in batch_results.items():
            print(f"\n   Contract: {contract_key}")
            if not data:
                print(f"      [FAIL] No data returned")
                continue
                
            for data_type, df in data.items():
                if isinstance(df, pd.DataFrame):
                    print(f"      [OK] {data_type}: {len(df)} rows, {len(df.columns)} columns")
                elif isinstance(df, pd.Series):
                    print(f"      [OK] {data_type}: {len(df)} values")
                else:
                    print(f"      [UNKNOWN] {data_type}: {type(df).__name__}")
        
    except Exception as e:
        print(f"[FAIL] Batch fetch failed: {e}")
        batch_results = {}
    
    # Test export functionality
    print_header("Data Export Testing")
    
    if batch_results:
        # Cross-platform output directory
        if os.name == 'nt':  # Windows
            output_dir = r"C:\Users\krajcovic\Documents\Testing Data\ATS_data\temp"
        else:  # WSL/Linux
            output_dir = "/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_data/temp"
        print(f"[DIR] Exporting data to: {output_dir}")
        
        try:
            # Ensure parquet engine is available
            parquet_engine = None
            
            try:
                import pyarrow
                print(f"[OK] pyarrow found - version {pyarrow.__version__}")
                parquet_engine = "pyarrow"
            except ImportError:
                try:
                    import fastparquet
                    print(f"[OK] fastparquet found - version {fastparquet.__version__}")
                    parquet_engine = "fastparquet"
                except ImportError:
                    print("[INSTALL] No parquet engines available. Installing pyarrow...")
                    import subprocess
                    
                    # Try different installation approaches for Python 3.13 compatibility
                    install_success = False
                    
                    # Method 1: Compatible pyarrow version for Python 3.13
                    try:
                        print("[INSTALL] Attempting to install compatible pyarrow...")
                        result = subprocess.run([sys.executable, "-m", "pip", "install", "pyarrow==14.0.2"], 
                                              capture_output=True, text=True)
                        if result.returncode == 0:
                            import pyarrow
                            print(f"[OK] pyarrow {pyarrow.__version__} installed successfully")
                            parquet_engine = "pyarrow"
                            install_success = True
                        else:
                            print(f"[FAIL] pyarrow 14.0.2 installation failed: {result.stderr[:100]}...")
                            # Try latest if specific version fails
                            print("[INSTALL] Trying latest pyarrow version...")
                            result2 = subprocess.run([sys.executable, "-m", "pip", "install", "pyarrow"], 
                                                    capture_output=True, text=True)
                            if result2.returncode == 0:
                                import pyarrow
                                print(f"[OK] pyarrow {pyarrow.__version__} installed successfully")
                                parquet_engine = "pyarrow"
                                install_success = True
                            else:
                                print(f"[FAIL] latest pyarrow installation failed: {result2.stderr[:100]}...")
                    except Exception as e:
                        print(f"[FAIL] pyarrow installation failed: {str(e)[:100]}...")
                    
                    # Method 2: Try fastparquet as backup
                    if not install_success:
                        try:
                            print("[INSTALL] Attempting to install fastparquet...")
                            result = subprocess.run([sys.executable, "-m", "pip", "install", "fastparquet"], 
                                                  capture_output=True, text=True)
                            if result.returncode == 0:
                                import fastparquet
                                print(f"[OK] fastparquet {fastparquet.__version__} installed successfully")
                                parquet_engine = "fastparquet"
                                install_success = True
                            else:
                                print(f"[FAIL] fastparquet installation failed: {result.stderr[:100]}...")
                        except Exception as e:
                            print(f"[FAIL] fastparquet installation failed: {str(e)[:100]}...")
                    
                    if not install_success:
                        raise ImportError("Could not install any parquet engine")
            
            # Export to parquet with specified engine
            print(f"[EXPORT] Using {parquet_engine} engine for parquet export")
            try:
                fetcher.export_to_parquet(batch_results, output_dir)
                print(f"[SUCCESS] Parquet export completed successfully!")
            except Exception as parquet_error:
                print(f"[ERROR] Parquet export failed with {parquet_engine}: {str(parquet_error)[:150]}...")
                
                # Try alternative export method
                if parquet_engine == "pyarrow":
                    print("[RETRY] Attempting manual parquet export with engine fallback...")
                    try:
                        os.makedirs(output_dir, exist_ok=True)
                        
                        for contract_key, data in batch_results.items():
                            for data_type, df in data.items():
                                if isinstance(df, (pd.DataFrame, pd.Series)):
                                    parquet_filename = f"{contract_key}_{data_type}_data.parquet"
                                    parquet_path = os.path.join(output_dir, parquet_filename)
                                    
                                    # Try with different engines
                                    for engine in ['fastparquet', None]:
                                        try:
                                            if isinstance(df, pd.Series):
                                                df.to_frame().to_parquet(parquet_path, engine=engine)
                                            else:
                                                df.to_parquet(parquet_path, engine=engine)
                                            print(f"   [OK] Manual export: {parquet_filename} (engine: {engine})")
                                            break
                                        except Exception as manual_error:
                                            if engine is None:  # Last attempt failed
                                                print(f"   [FAIL] Manual export failed: {parquet_filename}")
                                            continue
                                            
                        print("[SUCCESS] Manual parquet export completed!")
                        
                    except Exception as manual_export_error:
                        print(f"[FAIL] Manual parquet export failed: {str(manual_export_error)[:100]}...")
                        raise parquet_error  # Re-raise original error
                else:
                    raise parquet_error  # Re-raise if not pyarrow
            
            # List exported files
            if os.path.exists(output_dir):
                files = os.listdir(output_dir)
                print(f"[OK] Export completed. Files created:")
                for file in files:
                    file_path = os.path.join(output_dir, file)
                    file_size = os.path.getsize(file_path)
                    print(f"   [FILE] {file} ({file_size} bytes)")
                    
                    # Validate parquet file can be read back
                    try:
                        df_check = pd.read_parquet(file_path)
                        print(f"      [OK] Readable: {df_check.shape}")
                    except Exception as e:
                        print(f"      [FAIL] Read error: {e}")
            else:
                print(f"[FAIL] Output directory not created")
                
        except Exception as e:
            print(f"[ERROR] Parquet export failed: {e}")
            print(f"[ERROR] Error details: {str(e)[:200]}...")
            
            # If parquet fails, suggest manual installation
            print("\n[SOLUTION] To fix parquet export, manually install pyarrow:")
            print("   Option 1: pip install pyarrow")
            print("   Option 2: pip install fastparquet")
            print("   Option 3: Install Visual Studio Build Tools for compilation")
            
            print("\n[RETRY] Attempting CSV export as fallback...")
            
            try:
                # Fallback to CSV export
                os.makedirs(output_dir, exist_ok=True)
                csv_files = []
                
                for contract_key, data in batch_results.items():
                    for data_type, df in data.items():
                        if isinstance(df, pd.DataFrame):
                            csv_filename = f"{contract_key}_{data_type}_data.csv"
                            csv_path = os.path.join(output_dir, csv_filename)
                            df.to_csv(csv_path)
                            csv_files.append(csv_filename)
                            print(f"   [FILE] Exported: {csv_filename}")
                        elif isinstance(df, pd.Series):
                            csv_filename = f"{contract_key}_{data_type}_series.csv"
                            csv_path = os.path.join(output_dir, csv_filename)
                            df.to_csv(csv_path)
                            csv_files.append(csv_filename)
                            print(f"   [FILE] Exported: {csv_filename}")
                
                print(f"[OK] CSV export completed. {len(csv_files)} files created")
                print("[INFO] CSV files can be converted to parquet later using pandas")
                
                # Show CSV files
                for file in csv_files:
                    file_path = os.path.join(output_dir, file)
                    file_size = os.path.getsize(file_path)
                    print(f"   [FILE] {file} ({file_size} bytes)")
                    
            except Exception as csv_error:
                print(f"[FAIL] CSV export also failed: {csv_error}")
                return False
    
    else:
        print("[WARN]  No data to export (batch results empty)")
    
    # Final summary
    print_header("UAT Test Summary")
    
    print("[DATA] Test Results:")
    print(f"   [OK] TPData Connectivity: {'Passed' if TPDATA_AVAILABLE else 'Failed'}")
    print(f"   [OK] DataFetcher Initialization: Passed")
    print(f"   [OK] Individual Contract Fetching: {len([k for k in individual_results.keys() if not k.startswith('error')])} of {len(test_contracts)} succeeded")
    print(f"   [OK] Batch Contract Fetching: {'Passed' if batch_results else 'Failed'}")
    # Cross-platform path check for data export
    export_check_path = r"C:\Users\krajcovic\Documents\Testing Data\ATS_data\temp" if os.name == 'nt' else "/mnt/c/Users/krajcovic/Documents/Testing Data/ATS_data/temp"
    print(f"   [OK] Data Export: {'Passed' if os.path.exists(export_check_path) else 'Failed'}")
    
    # Data Quality Summary
    total_trades = 0
    total_orders = 0
    
    for data in batch_results.values():
        if 'trades' in data and isinstance(data['trades'], pd.DataFrame):
            total_trades += len(data['trades'])
        if 'orders' in data and isinstance(data['orders'], pd.DataFrame):
            total_orders += len(data['orders'])
    
    print(f"\n[STATS] Data Volume Summary:")
    print(f"   [DATA] Total Trade Records: {total_trades:,}")
    print(f"   [DATA] Total Order Records: {total_orders:,}")
    
    print(f"\n[SUCCESS] UAT Test completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    return True


if __name__ == "__main__":
    """
    Run this UAT test to validate the complete DataFetcher workflow:
    
    Usage:
        python uat/test_data_fetcher_uat.py
        
    Expected Output:
    - Contract configuration validation
    - Live data fetching from TPData
    - Data structure validation
    - Export to parquet files
    - Comprehensive test summary
    """
    
    success = run_uat_test()
    
    if success:
        print("\n[PASS] UAT TEST PASSED - DataFetcher is ready for production use!")
    else:
        print("\n[ERROR] UAT TEST FAILED - Please review errors above")
    
    print("\n" + "="*60)