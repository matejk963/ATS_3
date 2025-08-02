import numpy as np
from Utilities.mock_functions import Mock
from datetime import timedelta
import pandas as pd
import matplotlib.pyplot as plt

# Mock data (replace with your actual mock functions or data)
datetime_seq = Mock.mock_datetime(timedelta(days=1))
trades = Mock.mock_trade_prices(datetime_seq, 50)

df = pd.DataFrame(trades, columns=['x', 'y1'])

# Calculate MACD (you may have your own MACD calculation function)
def calculate_macd(y1, short_window=2, long_window=26, adjustment=0.01):
    """
    Calculate MACD using a custom moving average logic.
    If the price is equal to the last price, the average is slightly adjusted upward.
    
    Parameters:
        y1 (np.ndarray): Array of values (e.g., prices) to calculate MACD for.
        short_window (int): Window size for the short moving average.
        long_window (int): Window size for the long moving average.
        adjustment (float): Small increment added when price equals the last value.
        
    Returns:
        dict: A dictionary containing the short SMA, long SMA, and MACD.
    """
    def custom_moving_average(arr, window):
        result = np.empty(len(arr))
        result[:] = np.nan  # Initialize with NaN

        for i in range(len(arr)):
            if i < window - 1:
                # Not enough data to compute the moving average
                continue
            # Calculate the moving average for the current window
            window_data = arr[i - window + 1:i + 1]
            avg = np.mean(window_data)

            # Apply the custom logic: increase slightly if the current value equals the previous one
            if len(window_data) > 1 and window_data[-1] == window_data[-2]:
                avg += adjustment

            result[i] = avg

        return result

    # Calculate short and long moving averages
    short_sma = custom_moving_average(y1, short_window)
    long_sma = custom_moving_average(y1, long_window)

    # Calculate MACD
    macd = short_sma - long_sma

    return {
        "short_sma": short_sma,
        "long_sma": long_sma,
        "MACD": macd
    }

df = pd.concat([df, pd.DataFrame((calculate_macd(df['y1'].values)))], axis=1)

# Calculate the 'y2' (difference between MACD and its moving average)
df['macd_avg'] = df['MACD'].rolling(window=20).mean()
df['y2'] = df['MACD'] - df['macd_avg']

# y1_mean = df['y1'].mean()

# Calculate the rolling mean for y1
# df['y1_rolling_mean'] = df['y1'].rolling(window=9, center=True).mean()

# Plot setup
# Create the plot
fig, ax1 = plt.subplots()

# Plot y1 on the primary y-axis
ax1.plot(df['x'], df['y1'], 'b-', label='y1 (Price)')
ax1.set_xlabel('X-axis')
ax1.set_ylabel('y1 (Price)', color='b')
ax1.tick_params(axis='y', labelcolor='b')

# Create a secondary y-axis for y2
ax2 = ax1.twinx()

# Plot y2 with its original scale
ax2.plot(df['x'], df['y2'], 'r-', label='y2 (MACD)')
ax2.set_ylabel('y2 (MACD)', color='r')
ax2.tick_params(axis='y', labelcolor='r')

# Add gridlines for better interpretability
ax1.grid(True)

# Add legends for clarity
fig.legend(loc='upper left', bbox_to_anchor=(0.1, 0.9))

# Tight layout for better visuals
fig.tight_layout()

# Show the plot
plt.show()