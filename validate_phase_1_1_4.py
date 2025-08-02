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