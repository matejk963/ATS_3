"""
WORKING SOLUTION for your specific Refinitiv Data Library version
Your library has: ['close_session', 'get_data', 'open_session', 'pd', 'set_app_key']
Missing: get_history

This script provides working alternatives for your exact setup.
"""

import refinitiv.data as rd
import pandas as pd
from datetime import datetime, timedelta
import warnings

# Suppress warnings
warnings.filterwarnings('ignore')

def check_your_library():
    """Check what's available in your specific library version"""
    print("=" * 60)
    print("YOUR REFINITIV LIBRARY ANALYSIS")
    print("=" * 60)
    
    methods = [method for method in dir(rd) if not method.startswith('_')]
    print(f"Available methods: {methods}")
    
    # Check for specific capabilities
    capabilities = {
        'get_history': hasattr(rd, 'get_history'),
        'get_data': hasattr(rd, 'get_data'),
        'open_session': hasattr(rd, 'open_session'),
        'set_app_key': hasattr(rd, 'set_app_key'),
        'content module': hasattr(rd, 'content'),
        'historical_pricing': hasattr(rd, 'historical_pricing')
    }
    
    for capability, available in capabilities.items():
        status = "✓" if available else "❌"
        print(f"{status} {capability}: {available}")
    
    return capabilities

def solution_with_get_data():
    """
    SOLUTION 1: Using rd.get_data (which you have)
    This gets current/latest data rather than historical
    """
    print("\n" + "=" * 60)
    print("SOLUTION 1: Using rd.get_data()")
    print("=" * 60)
    
    try:
        # Open session
        rd.open_session()
        print("Session opened (may show mock warning - that's normal)")
        
        # Try different field combinations
        field_sets = [
            # Standard fields
            ["CF_LAST", "CF_VOLUME", "CF_BID", "CF_ASK"],
            # Alternative fields
            ["LAST", "VOLUME", "BID", "ASK"],
            # Minimal fields
            ["CF_LAST"],
            # Just try without fields
            []
        ]
        
        for i, fields in enumerate(field_sets, 1):
            try:
                print(f"\nTrying field set {i}: {fields}")
                
                if fields:
                    df = rd.get_data(
                        universe="LCOc1",
                        fields=fields
                    )
                else:
                    df = rd.get_data(universe="LCOc1")
                
                print(f"✓ Success! Shape: {df.shape}")
                if not df.empty:
                    print("Sample data:")
                    print(df.head())
                    return df
                else:
                    print("⚠ Data is empty (normal with mock)")
                    
            except Exception as e:
                print(f"❌ Field set {i} failed: {e}")
        
        print("All field sets tried - this is expected with mock data")
        return None
        
    except Exception as e:
        print(f"❌ Session/connection error: {e}")
        return None

def solution_with_content_module():
    """
    SOLUTION 2: Try using content module if available
    """
    print("\n" + "=" * 60)
    print("SOLUTION 2: Using content module")
    print("=" * 60)
    
    try:
        # Check if content module exists
        if hasattr(rd, 'content'):
            print("✓ Content module found")
            
            # Try historical pricing through content
            from refinitiv.data import content
            
            # Create a definition for historical data
            historical_def = content.historical_pricing.summaries.Definition(
                universe="LCOc1",
                start="2025-07-17",
                end="2025-07-17"
            )
            
            df = historical_def.get_data()
            print(f"✓ Historical data retrieved! Shape: {df.shape}")
            if not df.empty:
                print(df.head())
            return df
            
        else:
            print("❌ Content module not available")
            return None
            
    except Exception as e:
        print(f"❌ Content module error: {e}")
        return None

def solution_with_eikon():
    """
    SOLUTION 3: Using eikon library as alternative
    """
    print("\n" + "=" * 60)
    print("SOLUTION 3: Using eikon library")
    print("=" * 60)
    
    try:
        import eikon as ek
        print("✓ Eikon library available")
        
        # Note: In production, you'd set your app key:
        # ek.set_app_key('YOUR_APP_KEY_HERE')
        
        # Get historical data
        df = ek.get_timeseries(
            'LCOc1',
            start_date='2025-07-17',
            end_date='2025-07-17',
            interval='minute'
        )
        
        print(f"✓ Eikon data retrieved! Shape: {df.shape}")
        if not df.empty:
            print(df.head())
        return df
        
    except ImportError:
        print("❌ Eikon library not available (run: pip install eikon)")
        return None
    except Exception as e:
        print(f"❌ Eikon error: {e}")
        return None

def create_mock_data_realistic():
    """
    SOLUTION 4: Create realistic mock data for development
    """
    print("\n" + "=" * 60)
    print("SOLUTION 4: Creating realistic mock data")
    print("=" * 60)
    
    try:
        import numpy as np
        
        # Create minute-by-minute data for the day
        start_time = datetime(2025, 7, 17, 9, 0)  # 9 AM
        end_time = datetime(2025, 7, 17, 17, 0)   # 5 PM
        
        # Generate timestamps
        timestamps = pd.date_range(start_time, end_time, freq='1min')
        
        # Realistic oil price simulation
        np.random.seed(42)  # Reproducible
        n_points = len(timestamps)
        
        # Start with realistic Brent crude price
        base_price = 85.50
        
        # Generate price movements (random walk with drift)
        returns = np.random.normal(0.0001, 0.003, n_points)  # Small realistic returns
        prices = base_price * np.exp(np.cumsum(returns))
        
        # Create OHLC data
        spread = 0.02  # 2 cent bid-ask spread
        volume_base = 150
        
        df = pd.DataFrame({
            'CLOSE': prices,
            'VOLUME': np.random.poisson(volume_base, n_points),
            'BID': prices - spread/2,
            'ASK': prices + spread/2,
            'HIGH': prices * (1 + np.abs(np.random.normal(0, 0.001, n_points))),
            'LOW': prices * (1 - np.abs(np.random.normal(0, 0.001, n_points)))
        }, index=timestamps)
        
        # Round to realistic precision
        df = df.round(3)
        
        print(f"✓ Mock data created! Shape: {df.shape}")
        print("First few rows:")
        print(df.head())
        
        print("\nLast few rows:")
        print(df.tail())
        
        print(f"\nPrice range: ${df['CLOSE'].min():.2f} - ${df['CLOSE'].max():.2f}")
        print(f"Total volume: {df['VOLUME'].sum():,}")
        
        return df
        
    except Exception as e:
        print(f"❌ Mock data creation failed: {e}")
        return None

def main():
    """Test all solutions and find what works"""
    print("REFINITIV DATA LIBRARY - WORKING SOLUTIONS")
    print("=" * 60)
    print(f"Timestamp: {datetime.now()}")
    
    # Check your library
    capabilities = check_your_library()
    
    # Try each solution
    solutions = [
        ("get_data method", solution_with_get_data),
        ("content module", solution_with_content_module),
        ("eikon library", solution_with_eikon),
        ("mock data", create_mock_data_realistic)
    ]
    
    working_solutions = []
    
    for solution_name, solution_func in solutions:
        print(f"\n{'='*20} TESTING {solution_name.upper()} {'='*20}")
        try:
            result = solution_func()
            if result is not None and not result.empty:
                working_solutions.append(solution_name)
                print(f"✅ {solution_name} WORKS!")
            else:
                print(f"⚠ {solution_name} returned empty data")
        except Exception as e:
            print(f"❌ {solution_name} failed: {e}")
    
    # Summary
    print("\n" + "=" * 60)
    print("SOLUTION SUMMARY")
    print("=" * 60)
    
    if working_solutions:
        print("✅ Working solutions:")
        for sol in working_solutions:
            print(f"   - {sol}")
    else:
        print("❌ No solutions returned data (likely due to mock environment)")
    
    print("\n🔧 RECOMMENDED APPROACH:")
    print("1. For development: Use the mock data solution")
    print("2. For production: Install and use eikon library")
    print("3. Alternative: Use different data provider (yfinance, alpha_vantage)")
    
    return working_solutions

if __name__ == "__main__":
    main()
