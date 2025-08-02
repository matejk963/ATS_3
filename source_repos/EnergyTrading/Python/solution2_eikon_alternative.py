
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
