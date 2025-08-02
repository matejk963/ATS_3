# -*- coding: utf-8 -*-
"""
Created on Fri Jan  5 13:12:42 2024

@author: krajcovic
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta, time
import datetime as dt
import seaborn as sns
from Database.TPData import TPDataAssembly as TDA
from Strategies.IceBergOrders_class import IceBergOrders as IBO
from Math.accumfeatures import EMA
from Strategies.Intensity_class import TradeIntensity as TI
from lifetimes.datasets import load_transaction_data
from lifetimes.utils import summary_data_from_transaction_data
from lifetimes.utils import calibration_and_holdout_data
from lifetimes import BetaGeoFitter



   
assembler = TDA(source='database')
params_dict = {}
params_dict['mkt_list'] = ['de', 'de']
params_dict['tenor_list'] = ['m', 'm']
params_dict['tn1_list'] = [1,2]
params_dict['tn2_list'] = []
params_dict['prod'] = 'base'
params_dict['venue_list'] = ['eex']*len(params_dict['mkt_list'])
params_dict['start_date'] = datetime(2023, 11, 20)
params_dict['end_date'] = datetime(2023, 11, 20)
params_dict['ns'] = 2

assembler = TDA(source='trayport')
# assembler.set_start_end_time(start=[10,0,0], end=[12,0,0])    
trades_dict = assembler.get_data(params_dict, target_data='trades')
trades_key = next(iter(trades_dict))
trades = trades_dict[trades_key]
trades = trades.loc[trades['broker_id']==14].copy()
assembler.set_data_source('database')
ba_dict = assembler.get_data(params_dict, target_data='best_orders')
ba_key = next(iter(ba_dict))
assert ba_key == trades_key, 'Not the same instruments'


int_inst = TI(trades, ba_dict[ba_key])
# trans_data = int_inst.prepare_data().sort_values('datetime')
tau = 1
int_inst.ema_int(tau)

test_df = int_inst.data    
ret_df = test_df.dropna().copy()
ret_df['ret'] = ret_df['price'].diff()
ret_df['cum_bid_int'] = ret_df['bid_int'].cumsum()
ret_df['cum_ask_int'] = ret_df['ask_int'].cumsum()
ret_df['cum_int'] = ret_df['cum_ask_int'] - ret_df['cum_bid_int']
ret_df['cum_ret'] = ret_df['ret'].cumsum()





def adjust_datetime_precision(df, datetime_col):
    """
    Adjusts datetime precision in a dataframe without modifying the original dataframe.

    Parameters:
    df (pandas.DataFrame): The dataframe containing the datetime data.
    datetime_col (str): The name of the column containing datetime objects.

    Returns:
    pandas.DataFrame: A new dataframe with an additional column 'modified_datetime'.
    """

    # Create a copy of the dataframe to avoid modifying the original
    df_copy = df.copy()
    origin_cols = df_copy.columns

    # Ensure the datetime column is in the correct format
    df_copy[datetime_col] = pd.to_datetime(df_copy[datetime_col])

    # Round down to nearest second and count occurrences
    df_copy['datetime_rounded'] = df_copy[datetime_col].dt.floor('S')
    df_copy['count_within_second'] = df_copy.groupby('datetime_rounded').cumcount()

    # Calculate the total occurrences of each second
    total_counts = df_copy['datetime_rounded'].map(df_copy['datetime_rounded'].value_counts())

    # Calculate the fraction to add
    df_copy['fraction_to_add'] = df_copy['count_within_second'] / total_counts

    # Add the fraction of a second to the rounded datetime
    df_copy['modified_datetime'] = df_copy['datetime_rounded'] + pd.to_timedelta(df_copy['fraction_to_add'], unit='s')


    
    df_copy['datetime'] = df_copy['modified_datetime']
    df_copy = df_copy[origin_cols].copy()
    

    return df_copy
bid_trades = ret_df.loc[ret_df['bid_trade']==1]['bid_trade'].reset_index().copy()
bid_trades_adj = adjust_datetime_precision(bid_trades, 'datetime')
# bid_trades_adj = bid_trades.copy()
# bid_trades_adj['datetime'] = pd.to_datetime(bid_trades_adj['datetime'].dt.date)

summary = summary_data_from_transaction_data(bid_trades_adj, 'bid_trade', 'datetime', freq='s')    
summary['recency'] = summary['recency'] 
summary['T'] = summary['T'] 

bgf = BetaGeoFitter(penalizer_coef=0.9)

trade = summary.iloc[[0]]
# trade = summary.iloc[[1]]

bgf.fit(trade['frequency'], trade['recency'], trade['T'])

print(bgf)

from lifetimes.plotting import plot_frequency_recency_matrix

plot_frequency_recency_matrix(bgf)

from lifetimes.utils import calibration_and_holdout_data

summary_cal_holdout = calibration_and_holdout_data(bid_trades_adj, 'bid_trade', 'datetime', freq='s',
                                        calibration_period_end='2023-11-20 14:00:12' )

# from lifetimes.plotting import plot_calibration_purchases_vs_holdout_purchases

# bgf.fit(summary_cal_holdout['frequency_cal'], summary_cal_holdout['recency_cal'], summary_cal_holdout['T_cal'])
# plot_calibration_purchases_vs_holdout_purchases(bgf, summary_cal_holdout)

# bgf.fit(trade['frequency'], trade['recency'], trade['T'])

from lifetimes.plotting import plot_probability_alive_matrix

plot_probability_alive_matrix(bgf)

# from lifetimes.plotting import plot_history_alive    
# days_since_birth = 100
# sp_trans = bid_trades_adj.copy()
# sp_trans['datetime'] = sp_trans['datetime'].dt.floor('S')

# # sp_trans = sp_trans.groupby(['datetime']).sum()
# # sp_trans = sp_trans.reset_index()
# # sp_trans['datetime'] = sp_trans['datetime'].dt.strftime('%Y-%m-%d %H:%M:%S')

# plot_history_alive(bgf, days_since_birth, sp_trans, 'datetime', freq='s')
