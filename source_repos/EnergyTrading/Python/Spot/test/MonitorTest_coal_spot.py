# -*- coding: utf-8 -*-
"""
Created on Mon Jan 22 16:56:32 2024

@author: krajcovic
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime

import seaborn as sns

from Spot.Monitor_class import SettleMonitor as SM

from Loaders.EikonFut_class import EikonFut as EF

from Math.accumfeatures import EMA, MSTD


sD = datetime(2023,9,1)
eD = datetime(2024,1,23)

sm_inst = SM()
sm_inst.set_date_range(sD, eD)
# sm_inst.set_grids(['de'])

coal_df = sm_inst.get_coal_spot()


ef_inst = EF('coal')

product_list = ['M_1', 'M_2']
delivery_list = ['base'] * len(product_list)
year_list = [None] * len(product_list)

ef_coal = ef_inst.fwd_df(sD, eD, product_list, delivery_list, year_list)


ef_coal['spread'] = ef_coal['coal_M_1'] - ef_coal['coal_M_2']

ef_coal['day'] = ef_coal.index.day

# Create a column to identify the start of a new month
ef_coal['is_month_start'] = ef_coal.index.to_series().dt.is_month_start

# Function to calculate business days in a month
def business_days_in_month(date):
    # Normalize the date to ensure it's in 'day' frequency
    date = pd.to_datetime(date).normalize()

    start_month = date.replace(day=1)
    end_month = date + pd.offsets.MonthEnd(1)

    # Using numpy's busday_count to count business days
    return np.busday_count(start_month.strftime('%Y-%m-%d'), end_month.strftime('%Y-%m-%d'))

# Calculate business days in the month for each row
ef_coal['business_days_in_month'] = ef_coal.index.to_series().apply(business_days_in_month)

# Initialize the new column
ef_coal['new_column'] = np.nan

for i in range(len(ef_coal)):
    total_business_days = ef_coal.iloc[i]['business_days_in_month']
    current_day = ef_coal.index[i].day
    business_days_passed = np.busday_count(ef_coal.index[i].replace(day=1).strftime('%Y-%m-%d'), ef_coal.index[i].strftime('%Y-%m-%d')) + 1
    business_days_left = total_business_days - business_days_passed

    if i == 0 or ef_coal.index[i].month != ef_coal.index[i-1].month:
        # First row or first row of a new month
        ef_coal.iloc[i, ef_coal.columns.get_loc('new_column')] = ef_coal.iloc[i]['coal_M_1']
    else:
        # Remaining rows in the month
        sum_previous = ef_coal['new_column'][ef_coal.index.month == ef_coal.index[i].month][:i].sum()
        if business_days_left > 0:
            ef_coal.iloc[i, ef_coal.columns.get_loc('new_column')] = ((ef_coal.iloc[i]['coal_M_1'] * total_business_days) - sum_previous) / business_days_left
        else:
            ef_coal.iloc[i, ef_coal.columns.get_loc('new_column')] = np.nan  # or some other logic for the last business day

# Cumulative sum reset at the start of each month
ef_coal['cumulative_sum'] = ef_coal.groupby([ef_coal.index.year, ef_coal.index.month])['new_column'].cumsum()

        
        


length = len(ef_coal)
decay_rate = 0.25

mean_spread = ef_coal['spread'].mean()
mean_w_spread = sum(ef_coal['spread']*weights)

def generate_exponential_weights(length, decay_rate):
    """
    Generate exponential weights for a time series.

    Parameters:
    length (int): The length of the time series.
    decay_rate (float): The rate of decay for the exponential weights.

    Returns:
    np.ndarray: An array of exponential weights.
    """
    # Ensure decay_rate is positive
    decay_rate = abs(decay_rate)

    # Generate an array of indices (0, 1, ..., length-1)
    indices = np.arange(length)

    # Calculate exponential weights
    weights = np.exp(-decay_rate * indices)

    # Normalize the weights so their sum equals 1
    normalized_weights = weights / np.sum(weights)

    return normalized_weights