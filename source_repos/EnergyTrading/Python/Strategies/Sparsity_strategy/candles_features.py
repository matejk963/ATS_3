# -*- coding: utf-8 -*-
"""
Created on Tue Nov  5 11:07:11 2024

@author: scasny
"""
import pandas as pd
import pickle
import numpy as np

df = pd.read_pickle("trades.pkl")

def create_ohlc_candles(df, time_intervals=['1H', '15T', '5T']):
    """
    Create OHLC candles for specified time intervals from a series of trade data.

    Parameters:
    - df (pd.DataFrame): DataFrame with 'timestamp' as the index and 'price' column representing trade prices.
    - time_intervals (list): List of strings representing time intervals, e.g., ['1H', '15T', '5T'].

    Returns:
    - dict of pd.DataFrame: Dictionary where each key is a time interval and the value is the OHLC DataFrame for that interval.
    """
    ohlc_data = {}

    # Ensure 'timestamp' is the index and in datetime format
    df.index = pd.to_datetime(df.index)

    for interval in time_intervals:
        ohlc_df = df['trd_price'].resample(interval).ohlc()
        ohlc_data[interval] = ohlc_df

    return ohlc_data

# Example usage
# Suppose 'df' is your DataFrame with trade data, indexed by 'timestamp' and containing a 'price' column
ohlc_data = create_ohlc_candles(df)

# Access the OHLC data for each interval
ohlc_1h = ohlc_data['1H']   # 1-hour candles
ohlc_15m = ohlc_data['15T'] # 15-minute candles
ohlc_5m = ohlc_data['5T']   # 5-minute candles



i = 0
# Initialize variables
last_low, last_high = np.inf, -np.inf  # Proper extreme values
highs, lows = [], []

# Iterate through OHLC data
for i, row in enumerate(ohlc_5m.dropna().to_dict(orient='records')):
    o, h, l, c = row['open'], row['high'], row['low'], row['close']
    color = 'g' if c > o else 'r'
    value_dict = lambda t, v, idx, col: {'type': t, 'value': v, 'index': idx, 'color': col}

    # Update highs
    if h > last_high:
        if not highs or last_high < highs[-1]['value']:
            highs.append(value_dict('h', h, i, color))
        else:
            highs[-1] = value_dict('h', h, i, color)

    # Update lows
    if l < last_low:
        if not lows or last_low > lows[-1]['value']:
            lows.append(value_dict('l', l, i, color))
        else:
            lows[-1] = value_dict('l', l, i, color)

    # Update last high and low
    last_high, last_low = h, l


import plotly.graph_objects as go
from Utilities.dfutils import show_in_window
# Prepare the OHLC data for a 1-hour interval (as an example)
ohlc_1h = ohlc_5m[['open', 'high', 'low', 'close']].dropna()
idxs = ohlc_1h.index.values
# Create the initial candlestick chart
fig = go.Figure(data=[go.Candlestick(
    x=ohlc_1h.index,
    open=ohlc_1h['open'],
    high=ohlc_1h['high'],
    low=ohlc_1h['low'],
    close=ohlc_1h['close']
)])

highs_x = [ohlc_1h.index[item['index']] for item in highs]
lows_x = [ohlc_1h.index[item['index']] for item in lows]

# Add scatter traces for highs (green) and lows (red)
fig.add_trace(go.Scatter(
    x=highs_x,
    y=[item['value'] for item in highs],
    mode='markers',
    marker=dict(symbol='cross', color='blue', size=8),
    name='Highs'
))

fig.add_trace(go.Scatter(
    x=lows_x,
    y=[item['value'] for item in lows],
    mode='markers',
    marker=dict(symbol='cross', color='orange', size=8),
    name='Lows'
))

# Customize layout
fig.update_layout(
    title="5-min OHLC Candlestick Chart with Highs and Lows",
    xaxis_title="Time",
    yaxis_title="Price"
)

show_in_window(fig)




# append highs, lows
# sort
# duplicity sort based on color


hl_list = [*highs, *lows]

from itertools import groupby

# sorted(hl_list, key=lambda x: x['index'])

# Primary sort by index

    


class HL_class():
    def __init__(self, trades, interval):
        ohlc_data = create_ohlc_candles(df)
        
        # Access the OHLC data for each interval
        self.hl_list = self.calculate_highlow_list(ohlc_data['1H'])   # 1-hour candles
        self.hl_15m = self.calculate_highlow_list(ohlc_data['15T']) # 15-minute candles
        self.hl_5m = self.calculate_highlow_list(ohlc_data['5T'])  # 5-minute candles

        
    def calculate_highlow_list(self, ohlc_5m):
        i = 0
        last_low, last_high = np.max, np.min
        highs = []
        lows = []
        for row in ohlc_5m.dropna().to_dict(orient='records'):
            o, h, l, c = row['open'], row['high'], row['low'], row['close']
            value_dict = lambda t, v, i, c: {'type': t, 'value': v, 'index': i, 'color': c}
            color = 'g' if c > o else 'r'
            if highs == [] or lows == []:
                highs.append(value_dict('h', h, i, color))
                lows.append(value_dict('h', l, i, color))
            else:
                if h > last_high:
                    if last_high == highs[-1]['value']:
                        highs[-1] = value_dict('h', h, i, color)
                    elif last_high < highs[-1]['value']:  # Check if last high is less
                        highs.append(value_dict('h', h, i, color))  # Append as a new high
                    else:
                        highs.append(value_dict('h', h, i, color))

                if l < last_low:
                    if last_low == lows[-1]['value']:
                        lows[-1] = value_dict('l', l, i, color)
                    elif last_low > lows[-1]['value']:  # Check if last low is greater
                        lows.append(value_dict('l', l, i, color))  # Append as a new low
                    else:
                        lows.append(value_dict('l', l, i, color))
                        
            last_low, last_high = l, h     
            i += 1
            
            hl_list = [*highs, *lows]

            sorted_list = sorted(hl_list, key=lambda x: x['index'])

            # Group by index to handle duplicates separately
            result = []
            for _, group in groupby(sorted_list, key=lambda x: x['index']):
                group_list = list(group)
                if len(group_list) > 1:
                    # Apply secondary sort within the group based on color and type
                    group_list.sort(key=lambda x: (
                        0 if (x['color'] == 'g' and x['type'] == 'l') or (x['color'] == 'r' and x['type'] == 'h') else 1
                    ))
                result.extend(group_list)
                
            return result