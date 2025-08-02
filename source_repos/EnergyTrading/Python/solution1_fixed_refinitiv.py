
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
