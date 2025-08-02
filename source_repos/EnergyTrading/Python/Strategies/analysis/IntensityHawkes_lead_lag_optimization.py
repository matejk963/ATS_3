# -*- coding: utf-8 -*-
"""
Created on Tue Jan 30 12:57:40 2024

@author: krajcovic
"""


import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

import datetime as dt
from datetime import datetime, timedelta

from Strategies.MultipleMarketsIntensity_class import MultiTradeIntensity as TI
from Database.TPData import TPDataAssembly as TDA

from statsmodels.tsa.stattools import ccf
import seaborn as sns



assembler = TDA(source='database')
params_dict = {}

params_dict['tenor_list'] = ['m', 'm']
params_dict['tn1_list'] = [1, 1]
params_dict['mkt_list'] = ['de', 'ttf'] * len(params_dict['tenor_list'])
params_dict['tn2_list'] = []
params_dict['prod'] = 'base'
params_dict['venue_list'] = ['eex']*len(params_dict['mkt_list'])
params_dict['start_date'] = datetime(2023, 10, 1)
params_dict['end_date'] = datetime(2023, 11, 30)
params_dict['ns'] = 2

# Fetch trades and best orders for the curve
assembler = TDA(source='trayport', user='matej')
# assembler.set_start_end_time(start=[10,0,0], end=[12,0,0])    
trades_dict = assembler.get_data(params_dict, target_data='trades')
assembler.set_data_source('database')
ba_dict = assembler.get_data(params_dict, target_data='best_orders')

assert ba_dict.keys() == trades_dict.keys(), "Curve doesn't fit for both trades and best_orders"

trades = pd.DataFrame()
ba = pd.DataFrame()
products = []
for key in trades_dict.keys():
    ba_aux = ba_dict[key].copy()
    trade_aux = trades_dict[key].copy()
    trade_aux.columns = [a + '_' + key for a in trade_aux.columns]
    ba_aux.columns = [a + '_' + key for a in ba_aux.columns]
    if trades.empty:
        trades = trade_aux.copy()
    else:
        trades = pd.concat([trades, trade_aux])
    if ba.empty:
        ba = ba_aux.copy()
    else:
        ba = pd.concat([ba, ba_aux])
    products.append(key)
trades.sort_index(inplace=True)
ba.sort_index(inplace=True)


ti_inst = TI(trades, ba, products)

ti_inst.prepare_data()

ti_inst.set_train_size(0.6)
ti_inst.set_conditions()
# train_dict = ti_inst.train_dict

ti_inst.calculate_intensities()


agg_trades = pd.DataFrame()
agg_dict = {}
for date, aux_dict in ti_inst.test_dict.items():
    aux_df = pd.DataFrame()
    for prod, prod_dict in aux_dict.items():
        if aux_df.empty:
            aux_df = prod_dict['trades']
        else:
            aux_df = pd.concat([aux_df, prod_dict['trades']], axis=1, join='outer')
    agg_dict[date] = aux_df
    if agg_trades.empty:
        agg_trades = aux_df.copy()
    else:
        agg_trades = pd.concat([agg_trades, aux_df])
        
        
df = agg_trades.copy()
plt.figure(figsize=(14, 7))
plt.plot(df.index, df['int_bid_dem1'], label='int_bid_dem1')
plt.plot(df.index, df['int_bid_ttfm1'], label='int_bid_ttfm1', alpha=0.7)
plt.legend()
plt.show()



date, aux = next(iter(agg_dict.items()))

# Initialize lists to gather all intensity data
all_int_bid_dem1 = []
all_int_bid_ttfm1 = []

# Iterate to gather data
for df in agg_dict.values():
    
    all_int_bid_dem1.extend(df['int_bid_dem1'].dropna().values)
    all_int_bid_ttfm1.extend(df['int_bid_ttfm1'].dropna().values)

# Calculate global bin edges
num_bins = 10
all_int_bid_dem1 = pd.Series(all_int_bid_dem1)
bin_edges_dem1 = np.histogram_bin_edges(all_int_bid_dem1, bins=num_bins)
all_int_bid_ttfm1 = pd.Series(all_int_bid_ttfm1)
bin_edges_ttfm1 = np.histogram_bin_edges(all_int_bid_ttfm1[all_int_bid_ttfm1>0], bins=num_bins)

# Convert bin edges to upper bounds for labels
upper_bounds_dem1 = ["{:.2f}".format(edge) for edge in bin_edges_dem1[1:]]
upper_bounds_ttfm1 = ["{:.2f}".format(edge) for edge in bin_edges_ttfm1[1:]]

time_lag = pd.Timedelta(seconds=5)  # Time lag
threshold = 2.2  # Threshold for int_bid_dem1

# Initialize cumulative transition counts
cumulative_transition_counts = np.zeros((num_bins, num_bins))

for key, df in agg_dict.items():
    df.reset_index(inplace=True)
    df['datetime'] = pd.to_datetime(df['datetime'])
    

    # Filter based on 'int_bid_dem1' threshold
    filtered_df = df[df['int_bid_dem1'] > threshold].copy()
    if filtered_df.empty:
        continue

    # Use global bin edges for consistent binning
    filtered_df['bin_int_bid_dem1'] = pd.cut(filtered_df['int_bid_dem1'], bins=bin_edges_dem1, labels=range(num_bins)) + 1
    filtered_df['bin_int_bid_ttfm1'] = pd.cut(filtered_df['int_bid_ttfm1'], bins=bin_edges_ttfm1, labels=range(num_bins)) + 1

    # Calculate transitions
    transition_counts = np.zeros((num_bins, num_bins))
    for index, row in filtered_df.iterrows():
        start_time = row['datetime']
        end_time = start_time + time_lag
        future_rows = filtered_df[(filtered_df['datetime'] > start_time) & (filtered_df['datetime'] <= end_time)]
        if not future_rows.empty:
            future_bins = future_rows['bin_int_bid_dem1'].unique()
            for future_bin in future_bins:
                transition_counts[row['bin_int_bid_ttfm1'] - 1, future_bin - 1] += 1
    cumulative_transition_counts += transition_counts
    df.set_index('datetime', inplace=True)

# Calculate and normalize average transition counts
average_transition_counts = cumulative_transition_counts / len(agg_dict)
with np.errstate(divide='ignore', invalid='ignore'):
    average_transition_probabilities = np.nan_to_num(average_transition_counts / average_transition_counts.sum(axis=1, keepdims=True))
average_probabilities_df = pd.DataFrame(average_transition_probabilities, index=upper_bounds_ttfm1, columns=upper_bounds_dem1)

plt.figure(figsize=(12, 10))
sns.heatmap(average_probabilities_df, annot=True, cmap='viridis', fmt=".2f", linewidths=.5)
plt.title('Average Transition Probabilities Heatmap')
plt.xlabel('Destination Bin Upper Bound (dem1)')
plt.ylabel('Source Bin Upper Bound (ttfm1)')
plt.xticks(rotation=45)
plt.yticks(rotation=0)
plt.show()



plt.hist(aux['int_bid_dem1'].loc[aux['int_bid_dem1']>2.2].dropna(), bins=50, alpha=0.75)
plt.title('Distribution of int_bid_dem1')
plt.xlabel('int_bid_dem1')
plt.ylabel('Frequency')
plt.grid(True)
plt.show()


# num_quantiles = 10

# for date in agg_dict.keys():
#     aux = agg_dict[date].copy()
#     aux.reset_index(inplace=True)
#     aux['quantile_bid_dem1'] = pd.qcut(aux['int_bid_dem1'], q=num_quantiles, labels=False, duplicates='drop')
#     aux['quantile_ask_dem1'] = pd.qcut(aux['int_ask_dem1'], q=num_quantiles, labels=False, duplicates='drop')
#     aux['quantile_bid_ttfm1'] = pd.qcut(aux['int_bid_ttfm1'], q=num_quantiles, labels=False, duplicates='drop')
#     aux['quantile_ask_ttfm1'] = pd.qcut(aux['int_ask_ttfm1'], q=num_quantiles, labels=False, duplicates='drop')

#     # Initialize a matrix to store average time differences
#     average_time_diffs = np.zeros((num_quantiles, num_quantiles))
    
#     for q1 in range(num_quantiles):
#         for q2 in range(num_quantiles):
#             # Find indices where dem1 is in quantile q1
#             indices_q1 = aux[aux['quantile_bid_dem1'] == q1].index
            
#             time_diffs = []
            
#             for idx in indices_q1:
#                 # For each index, find the next time ttfm1 enters quantile q2
#                 future_indices_q2 = aux[(aux.index > idx) & (aux['quantile_bid_ttfm1'] == q2)].index
                
#                 if not future_indices_q2.empty:
#                     next_idx = future_indices_q2[0]
#                     time_diff = (aux.loc[next_idx, 'datetime'] - aux.loc[idx, 'datetime']).total_seconds()
#                     time_diffs.append(time_diff)
            
#             # Calculate average time difference for this quantile combination
#             if time_diffs:
#                 average_time_diffs[q1, q2] = np.mean(time_diffs)
#             else:
#                 average_time_diffs[q1, q2] = np.nan
                
#     sns.heatmap(average_time_diffs, annot=True, cmap='viridis', fmt=".2f")
#     plt.title('Average Time Differences from Quantile in dem1 to Quantile in ttfm1')
#     plt.xlabel('Quantile ttfm1')
#     plt.ylabel('Quantile dem1')
#     plt.show()



# tot_bid = pd.DataFrame()
# tot_ask = pd.DataFrame()
# for date in agg_dict.keys():
#     aux = agg_dict[date].copy()
#     de_int_bid = aux[['int_bid_dem1', 'bull_bear_result']].copy()
#     de_int_ask = aux[['int_ask_dem1', 'bull_bear_result']].copy()
#     de_int_bid['int_bid_dem1_round'] = round(de_int_bid['int_bid_dem1'],0)
#     de_int_ask['int_ask_dem1_round'] = round(de_int_ask['int_ask_dem1'],0)
#     de_int_bid = de_int_bid.groupby(['int_bid_dem1_round']).mean()
#     de_int_ask = de_int_ask.groupby(['int_ask_dem1_round']).mean()
#     if tot_bid.empty:
#         tot_bid = de_int_bid
    
#     plt.show()
    
    

# for date in agg_dict.keys():
#     aux = agg_dict[date].copy()
#     aux['mid_dem1'] = (aux['bidbestprice_dem1'] + aux['askbestprice_dem1'])/2
#     aux['mid_ttfm1'] = (aux['bidbestprice_ttfm1'] + aux['askbestprice_ttfm1'])/2
#     aux_dif = aux[['mid_dem1', 'mid_ttfm1']].diff().dropna().copy()
#     ccf_values = ccf(aux['mid_dem1'], aux['mid_ttfm1'], unbiased=True)
    
#     # Plot the CCF
#     plt.plot(ccf_values)
#     plt.xlabel('Lag')
#     plt.ylabel('Cross-correlation')
#     plt.title('Cross-Correlation between int_bid_dem1 and int_bid_ttfm1')
# plt.legend()
# plt.show()
    
    
