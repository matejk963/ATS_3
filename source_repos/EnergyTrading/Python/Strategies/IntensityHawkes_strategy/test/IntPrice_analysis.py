# -*- coding: utf-8 -*-
"""
Created on Mon Mar 11 14:35:09 2024

@author: krajcovic
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import datetime as dt
import seaborn as sns

data = pd.read_csv(r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Algo\dem1_data_with_int.csv',
                   parse_dates=['datetime'], index_col='datetime')
data = data.loc[data.index.date>=dt.date(2023,12,1)].copy()

fwd_time = 10 #seconds

def find_rows_in_window(index_row, local_df, fwd_time):  # Added fwd_time as parameter
    if pd.isna(index_row['price_dem1']):  # More pandas-native check for NaN
        return np.nan, np.nan, np.nan, np.nan  # Return a tuple to keep structure consistent
    else:
        start_time = index_row.name
        end_time = start_time + pd.Timedelta(seconds=fwd_time)
        aux = local_df.loc[start_time:end_time].copy()  # Assume local_df is already indexed by datetime
        max_ask = aux['askbestprice_dem1'].max()
        min_ask_bid = aux['bidbestprice_dem1'].loc[aux['askbestprice_dem1'] == max_ask].max()
        min_bid = aux['bidbestprice_dem1'].max()
        max_ask_bid = aux['askbestprice_dem1'].loc[aux['bidbestprice_dem1'] == min_bid].max()

        return max_ask, min_ask_bid, min_bid, max_ask_bid

# Consider setting 'datetime' as index outside the loop if possible
# And ensure fwd_time is defined

unique_dates = np.unique(data.index.date)

aux_stats = pd.DataFrame()
for date in unique_dates:
    aux = data.loc[data.index.date == date].copy()
    # aux = aux.set_index('datetime')  # Do this once per subset
    fwd_time = 10  # Set your forward time in seconds here, adjust as needed
    results = aux.apply(lambda row: find_rows_in_window(row, aux, fwd_time), axis=1, result_type='expand')
    aux[['max_ask', 'min_ask_bid', 'min_bid', 'max_ask_bid']] = results  # Assumes results are properly aligned
    if aux_stats.empty:
        aux_stats = aux[['max_ask', 'min_ask_bid', 'min_bid', 'max_ask_bid']].copy()
    else:
        aux_stats = pd.concat([aux_stats,
                               aux[['max_ask', 'min_ask_bid', 'min_bid', 'max_ask_bid']]])

data = data.merge(aux_stats, left_index=True,
                  right_index=True, how='left')

data['ask_ret'] = data['max_ask'] / data['askbestprice_dem1'] - 1
data['bid_ret'] = data['bidbestprice_dem1'] / data['min_bid'] - 1

data.dropna(inplace=True)

