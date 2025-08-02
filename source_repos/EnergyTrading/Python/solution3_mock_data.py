
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
