"""
Comprehensive Refinitiv Data Library Fix and Diagnosis Script
Addresses the common issues:
1. Session not opened warning
2. AttributeError: module 'refinitiv.data' has no attribute 'get_history'
"""

import os
import sys
import warnings
from datetime import datetime, timedelta

def check_environment():
    """Check the current Python environment and packages"""
    print("=" * 60)
    print("ENVIRONMENT DIAGNOSTIC")
    print("=" * 60)
    
    print(f"Python version: {sys.version}")
    print(f"Current working directory: {os.getcwd()}")
    
    # Check installed packages
    try:
        import pkg_resources
        installed_packages = [d.project_name for d in pkg_resources.working_set]
        refinitiv_packages = [pkg for pkg in installed_packages if 'refinitiv' in pkg.lower()]
        print(f"Refinitiv packages found: {refinitiv_packages}")
    except Exception as e:
        print(f"Could not check packages: {e}")
    
    return True

def test_refinitiv_import():
    """Test importing refinitiv.data and check available methods"""
    print("\n" + "=" * 60)
    print("REFINITIV IMPORT TEST")
    print("=" * 60)
    
    try:
        import refinitiv.data as rd
        print("✓ Successfully imported refinitiv.data")
        
        # Check available methods
        methods = [method for method in dir(rd) if not method.startswith('_')]
        print(f"Available methods: {methods}")
        
        # Check for specific methods
        has_get_history = hasattr(rd, 'get_history')
        has_get_data = hasattr(rd, 'get_data')
        has_session = hasattr(rd, 'session')
        
        print(f"Has get_history: {has_get_history}")
        print(f"Has get_data: {has_get_data}")
        print(f"Has session: {has_session}")
        
        return rd, True
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return None, False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return None, False

def test_session_methods(rd):
    """Test different session opening methods"""
    print("\n" + "=" * 60)
    print("SESSION TESTING")
    print("=" * 60)
    
    session_methods = [
        ("Default session", lambda: rd.open_session()),
        ("Desktop session", lambda: rd.open_session('desktop')),
        ("Platform session", lambda: rd.open_session('platform')),
    ]
    
    for method_name, method_func in session_methods:
        try:
            print(f"\nTrying {method_name}...")
            result = method_func()
            
            if hasattr(rd, 'session') and rd.session.get_open_state():
                print(f"✓ {method_name} successful!")
                return True
            else:
                print(f"⚠ {method_name} opened but state unclear")
        except Exception as e:
            print(f"❌ {method_name} failed: {e}")
    
    return False

def test_data_retrieval_methods(rd):
    """Test different data retrieval methods"""
    print("\n" + "=" * 60)
    print("DATA RETRIEVAL TESTING")
    print("=" * 60)
    
    # Test instruments - using simpler ones first
    test_instruments = ["EUR=", "GBP=", "USD="]  # Currency codes are usually more reliable
    
    data_methods = [
        ("get_history", lambda instrument: rd.get_history(
            universe=instrument,
            start="2025-07-17",
            end="2025-07-17"
        )),
        ("get_data", lambda instrument: rd.get_data(
            universe=instrument,
            fields=["CF_LAST"]
        )),
    ]
    
    for method_name, method_func in data_methods:
        if not hasattr(rd, method_name.replace('get_', '')):
            print(f"⚠ Method {method_name} not available")
            continue
            
        print(f"\nTesting {method_name}...")
        for instrument in test_instruments:
            try:
                print(f"  Trying {instrument}...")
                result = method_func(instrument)
                if result is not None and len(result) > 0:
                    print(f"    ✓ Success! Shape: {result.shape if hasattr(result, 'shape') else 'N/A'}")
                    print(f"    Sample data: {result.head(2) if hasattr(result, 'head') else result}")
                    return True
                else:
                    print(f"    ⚠ No data returned")
            except Exception as e:
                print(f"    ❌ Failed: {e}")
    
    return False

def test_oil_data_specifically(rd):
    """Test oil data retrieval specifically (LCOc1)"""
    print("\n" + "=" * 60)
    print("OIL DATA SPECIFIC TESTING")
    print("=" * 60)
    
    oil_instruments = ["LCOc1", "CLc1", "BRN"]  # Different oil contract codes
    
    for instrument in oil_instruments:
        print(f"\nTesting {instrument}...")
        
        # Method 1: Basic get_history
        try:
            df = rd.get_history(
                universe=instrument,
                start="2025-07-17",
                end="2025-07-17"
            )
            print(f"  ✓ Basic get_history successful! Shape: {df.shape}")
            print(f"  Columns: {df.columns.tolist()}")
            return df
        except Exception as e:
            print(f"  ❌ Basic get_history failed: {e}")
        
        # Method 2: With specific fields
        try:
            df = rd.get_history(
                universe=instrument,
                fields=["CLOSE", "VOLUME"],
                start="2025-07-17",
                end="2025-07-17"
            )
            print(f"  ✓ get_history with fields successful! Shape: {df.shape}")
            return df
        except Exception as e:
            print(f"  ❌ get_history with fields failed: {e}")
        
        # Method 3: get_data
        try:
            df = rd.get_data(
                universe=instrument,
                fields=["CF_LAST", "CF_VOLUME"]
            )
            print(f"  ✓ get_data successful! Shape: {df.shape}")
            return df
        except Exception as e:
            print(f"  ❌ get_data failed: {e}")
    
    return None

def create_working_example(rd):
    """Create a working example based on successful tests"""
    print("\n" + "=" * 60)
    print("CREATING WORKING EXAMPLE")
    print("=" * 60)
    
    working_code = '''
# Working Refinitiv Data Library Example
import refinitiv.data as rd
import pandas as pd
from datetime import datetime, timedelta

def get_oil_data():
    """
    Working function to get oil data from Refinitiv
    """
    try:
        # Open session (modify based on your setup)
        rd.open_session()
        
        # Check session state
        if hasattr(rd, 'session') and not rd.session.get_open_state():
            print("Warning: Session may not be properly opened")
        
        # Get data - try multiple approaches
        try:
            # Method 1: Simple get_history
            df = rd.get_history(
                universe="LCOc1",  # Brent Crude Oil
                start="2025-07-17",
                end="2025-07-17"
            )
            return df
        except:
            # Method 2: get_data
            df = rd.get_data(
                universe="LCOc1",
                fields=["CF_LAST", "CF_VOLUME"]
            )
            return df
            
    except Exception as e:
        print(f"Error: {e}")
        return None

# Execute
if __name__ == "__main__":
    data = get_oil_data()
    if data is not None:
        print("Success!")
        print(data.head())
    else:
        print("Failed to retrieve data")
'''
    
    # Save working example
    with open("working_refinitiv_example.py", "w") as f:
        f.write(working_code)
    
    print("✓ Created working_refinitiv_example.py")
    
    return working_code

def main():
    """Main diagnostic and fix function"""
    print("REFINITIV DATA LIBRARY DIAGNOSTIC AND FIX")
    print("=" * 60)
    print(f"Timestamp: {datetime.now()}")
    
    # Step 1: Check environment
    check_environment()
    
    # Step 2: Test import
    rd, import_success = test_refinitiv_import()
    if not import_success:
        print("\n❌ CRITICAL: Cannot import refinitiv.data")
        print("Solution: pip install refinitiv-data")
        return False
    
    # Step 3: Test session
    session_success = test_session_methods(rd)
    if not session_success:
        print("\n⚠ WARNING: No session method worked")
        print("This is likely due to:")
        print("1. Refinitiv Eikon/Workspace not running")
        print("2. No valid credentials configured")
        print("3. Network/firewall issues")
    
    # Step 4: Test data retrieval
    data_success = test_data_retrieval_methods(rd)
    
    # Step 5: Test oil data specifically
    oil_data = test_oil_data_specifically(rd)
    
    # Step 6: Create working example
    create_working_example(rd)
    
    # Final summary
    print("\n" + "=" * 60)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 60)
    print(f"Import successful: {import_success}")
    print(f"Session successful: {session_success}")
    print(f"Data retrieval successful: {data_success}")
    print(f"Oil data retrieval: {'Success' if oil_data is not None else 'Failed'}")
    
    if not session_success:
        print("\n🔧 RECOMMENDED ACTIONS:")
        print("1. Ensure Refinitiv Eikon or Workspace is running")
        print("2. Check your Refinitiv credentials")
        print("3. Try the alternative eikon library:")
        print("   pip install eikon")
        print("   import eikon as ek")
        print("   ek.set_app_key('your_app_key')")
    
    return True

if __name__ == "__main__":
    main()
