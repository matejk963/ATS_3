"""
COMPREHENSIVE FIX for Refinitiv Data Library Issues
This addresses the specific problems found in the diagnostic:
1. Mock refinitiv.data being used instead of real one
2. Missing get_history method
3. Session management issues
"""

import sys
import os
import subprocess
from datetime import datetime, timedelta

def fix_refinitiv_installation():
    """Fix the Refinitiv Data Library installation"""
    print("=" * 60)
    print("FIXING REFINITIV DATA LIBRARY INSTALLATION")
    print("=" * 60)
    
    # Step 1: Uninstall existing (possibly corrupted) installation
    print("1. Uninstalling existing refinitiv-data...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "uninstall", "refinitiv-data", "-y"], 
                      capture_output=True, text=True, check=True)
        print("   ✓ Uninstalled existing refinitiv-data")
    except:
        print("   ⚠ No existing installation found or uninstall failed")
    
    # Step 2: Clear pip cache
    print("2. Clearing pip cache...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "cache", "purge"], 
                      capture_output=True, text=True, check=True)
        print("   ✓ Pip cache cleared")
    except:
        print("   ⚠ Could not clear pip cache")
    
    # Step 3: Install fresh refinitiv-data
    print("3. Installing fresh refinitiv-data...")
    try:
        result = subprocess.run([sys.executable, "-m", "pip", "install", "refinitiv-data", "--upgrade", "--force-reinstall"], 
                               capture_output=True, text=True, check=True)
        print("   ✓ Fresh refinitiv-data installed")
        print(f"   Output: {result.stdout[-200:]}")  # Last 200 chars
    except subprocess.CalledProcessError as e:
        print(f"   ❌ Installation failed: {e}")
        print(f"   Error output: {e.stderr}")
        return False
    
    # Step 4: Install eikon as backup
    print("4. Installing eikon as backup...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "eikon"], 
                      capture_output=True, text=True, check=True)
        print("   ✓ Eikon installed as backup")
    except:
        print("   ⚠ Could not install eikon")
    
    return True

def test_fixed_installation():
    """Test the fixed installation"""
    print("\n" + "=" * 60)
    print("TESTING FIXED INSTALLATION")
    print("=" * 60)
    
    # Force reload modules
    if 'refinitiv.data' in sys.modules:
        del sys.modules['refinitiv.data']
    if 'refinitiv' in sys.modules:
        del sys.modules['refinitiv']
    
    try:
        import refinitiv.data as rd
        print("✓ Import successful")
        
        # Check methods
        methods = [method for method in dir(rd) if not method.startswith('_')]
        print(f"Available methods: {methods}")
        
        has_get_history = hasattr(rd, 'get_history')
        has_get_data = hasattr(rd, 'get_data')
        
        print(f"Has get_history: {has_get_history}")
        print(f"Has get_data: {has_get_data}")
        
        if has_get_history:
            print("✓ get_history method is now available!")
            return True
        else:
            print("❌ get_history still not available")
            return False
            
    except Exception as e:
        print(f"❌ Import still failing: {e}")
        return False

def create_working_solutions():
    """Create multiple working solutions"""
    print("\n" + "=" * 60)
    print("CREATING WORKING SOLUTIONS")
    print("=" * 60)
    
    # Solution 1: Fixed refinitiv.data approach
    solution1 = '''
"""
SOLUTION 1: Fixed Refinitiv Data Library Usage
Use this after running the fix script
"""
import refinitiv.data as rd
import pandas as pd
from datetime import datetime

def get_oil_data_fixed():
    """Get oil data using the fixed refinitiv.data library"""
    try:
        # Open session
        rd.open_session()
        print("Session opened")
        
        # Get historical data - NOW WITH CORRECT METHOD
        df = rd.get_history(
            universe="LCOc1",
            fields=["CLOSE", "VOLUME", "BID", "ASK"],
            start="2025-07-17",
            end="2025-07-17",
            interval="1min"
        )
        
        print("✓ Data retrieved successfully!")
        print(f"Shape: {df.shape}")
        print(df.head())
        return df
        
    except Exception as e:
        print(f"Error: {e}")
        # Fallback to get_data
        try:
            df = rd.get_data(
                universe="LCOc1",
                fields=["CF_LAST", "CF_VOLUME", "CF_BID", "CF_ASK"]
            )
            print("✓ Fallback get_data successful!")
            return df
        except Exception as e2:
            print(f"Fallback also failed: {e2}")
            return None

if __name__ == "__main__":
    data = get_oil_data_fixed()
'''
    
    # Solution 2: Eikon library approach
    solution2 = '''
"""
SOLUTION 2: Using Eikon Library (Alternative)
Use this if refinitiv.data still doesn't work
"""
import eikon as ek
import pandas as pd
from datetime import datetime

def get_oil_data_eikon():
    """Get oil data using eikon library"""
    try:
        # Set app key (you may need to get this from Refinitiv)
        # ek.set_app_key('YOUR_APP_KEY_HERE')  # Uncomment and add your key
        
        # Get historical data
        df = ek.get_timeseries(
            'LCOc1',
            start_date='2025-07-17',
            end_date='2025-07-17',
            interval='minute'
        )
        
        print("✓ Data retrieved using eikon!")
        print(f"Shape: {df.shape}")
        print(df.head())
        return df
        
    except Exception as e:
        print(f"Eikon error: {e}")
        return None

if __name__ == "__main__":
    data = get_oil_data_eikon()
'''
    
    # Solution 3: Mock data for development
    solution3 = '''
"""
SOLUTION 3: Mock Data for Development/Testing
Use this when Refinitiv services are not available
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def create_mock_oil_data():
    """Create realistic mock oil data for development"""
    
    # Create date range
    dates = pd.date_range(start='2025-07-17', end='2025-07-17', freq='1min')
    
    # Generate realistic oil price data
    np.random.seed(42)  # For reproducible results
    base_price = 85.0  # Rough Brent crude price
    
    n_points = len(dates)
    price_changes = np.random.normal(0, 0.1, n_points)  # Small random changes
    prices = base_price + np.cumsum(price_changes)
    
    # Create OHLC data
    df = pd.DataFrame({
        'CLOSE': prices,
        'VOLUME': np.random.randint(100, 1000, n_points),
        'BID': prices - 0.01,
        'ASK': prices + 0.01
    }, index=dates)
    
    print("✓ Mock data created for development!")
    print(f"Shape: {df.shape}")
    print(df.head())
    return df

if __name__ == "__main__":
    data = create_mock_oil_data()
'''
    
    # Save all solutions
    solutions = [
        ("solution1_fixed_refinitiv.py", solution1),
        ("solution2_eikon_alternative.py", solution2),
        ("solution3_mock_data.py", solution3)
    ]
    
    for filename, content in solutions:
        with open(filename, 'w') as f:
            f.write(content)
        print(f"✓ Created {filename}")
    
    return solutions

def create_jupyter_notebook_fix():
    """Create a Jupyter notebook with the complete fix"""
    print("\n" + "=" * 60)
    print("CREATING JUPYTER NOTEBOOK FIX")
    print("=" * 60)
    
    notebook_content = {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": ["# Refinitiv Data Library - Complete Fix\\n\\nThis notebook contains the complete solution for the Refinitiv Data Library issues."]
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "source": [
                    "# STEP 1: Import and test the fixed library\\n",
                    "import refinitiv.data as rd\\n",
                    "import pandas as pd\\n",
                    "from datetime import datetime\\n\\n",
                    "# Check available methods\\n",
                    "print('Available methods:', [m for m in dir(rd) if not m.startswith('_')])\\n",
                    "print('Has get_history:', hasattr(rd, 'get_history'))"
                ],
                "outputs": []
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "source": [
                    "# STEP 2: Open session\\n",
                    "try:\\n",
                    "    rd.open_session()\\n",
                    "    print('✓ Session opened successfully')\\n",
                    "except Exception as e:\\n",
                    "    print(f'⚠ Session warning: {e}')"
                ],
                "outputs": []
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "source": [
                    "# STEP 3: Get oil data (FIXED VERSION)\\n",
                    "try:\\n",
                    "    # This should now work with the fixed installation\\n",
                    "    df = rd.get_history(\\n",
                    "        universe='LCOc1',\\n",
                    "        fields=['CLOSE', 'VOLUME', 'BID', 'ASK'],\\n",
                    "        start='2025-07-17',\\n",
                    "        end='2025-07-17',\\n",
                    "        interval='1min'\\n",
                    "    )\\n",
                    "    \\n",
                    "    print('✓ Data retrieved successfully!')\\n",
                    "    print(f'Shape: {df.shape}')\\n",
                    "    print('\\nFirst few rows:')\\n",
                    "    display(df.head())\\n",
                    "    \\n",
                    "except AttributeError as e:\\n",
                    "    print(f'❌ get_history still not available: {e}')\\n",
                    "    print('Trying alternative method...')\\n",
                    "    \\n",
                    "    try:\\n",
                    "        df = rd.get_data(\\n",
                    "            universe='LCOc1',\\n",
                    "            fields=['CF_LAST', 'CF_VOLUME']\\n",
                    "        )\\n",
                    "        print('✓ Alternative method worked!')\\n",
                    "        display(df.head())\\n",
                    "    except Exception as e2:\\n",
                    "        print(f'❌ Alternative also failed: {e2}')\\n",
                    "        \\n",
                    "except Exception as e:\\n",
                    "    print(f'❌ Other error: {e}')"
                ],
                "outputs": []
            }
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3"
            },
            "language_info": {
                "name": "python",
                "version": "3.12.3"
            }
        },
        "nbformat": 4,
        "nbformat_minor": 4
    }
    
    import json
    with open("refinitiv_fix_complete.ipynb", 'w') as f:
        json.dump(notebook_content, f, indent=2)
    
    print("✓ Created refinitiv_fix_complete.ipynb")

def main():
    """Main fix function"""
    print("REFINITIV DATA LIBRARY - COMPREHENSIVE FIX")
    print("=" * 60)
    print(f"Timestamp: {datetime.now()}")
    
    # Step 1: Fix installation
    fix_success = fix_refinitiv_installation()
    
    if fix_success:
        # Step 2: Test the fix
        test_success = test_fixed_installation()
        
        # Step 3: Create working solutions
        create_working_solutions()
        
        # Step 4: Create Jupyter notebook
        create_jupyter_notebook_fix()
        
        print("\n" + "=" * 60)
        print("FIX COMPLETE!")
        print("=" * 60)
        print("✅ Next steps:")
        print("1. Restart your Jupyter kernel/Python session")
        print("2. Try running: solution1_fixed_refinitiv.py")
        print("3. If that fails, try: solution2_eikon_alternative.py")
        print("4. For development, use: solution3_mock_data.py")
        print("5. Open: refinitiv_fix_complete.ipynb for interactive testing")
        
        if test_success:
            print("\\n🎉 The get_history method should now be available!")
        else:
            print("\\n⚠ If get_history is still not available, use the eikon alternative")
            
    else:
        print("\\n❌ Installation fix failed. Try manual installation:")
        print("pip uninstall refinitiv-data -y")
        print("pip install refinitiv-data --upgrade --force-reinstall")

if __name__ == "__main__":
    main()
