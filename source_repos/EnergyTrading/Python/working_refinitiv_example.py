
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
