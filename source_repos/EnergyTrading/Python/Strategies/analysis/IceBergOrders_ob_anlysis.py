# -*- coding: utf-8 -*-
"""
Created on Wed Dec 20 16:25:13 2023

@author: krajcovic
"""

from datetime import datetime, time
import pandas as pd
import numpy as np
from Database.TPData import TPDataDa
from scipy.stats import skew, kurtosis
import matplotlib.pyplot as plt
import seaborn as sns
plt.ion()

import os

# Add your Oracle Client's bin directory to the PATH
oracle_client_bin_path = r'C:\oracle\instantclient_19_9'
os.environ['PATH'] = oracle_client_bin_path + ';' + os.environ['PATH']

# Now you can import and use libraries that rely on the updated PATH
import cx_Oracle

data_class = TPDataDa()

mkt_list = ['de']
tenor_list = ['m']
tn1_list = [1]
tn2_list = [2]
prod = 'base'
venue_list = ['eex']

data_dict = {}
for month in range(10,12):
    data_dict[month] = {}
    try:
        for day in range(1,28):
            start_date = datetime(2023, month, day)
            end_date = datetime(2023, month, day)
            n_s = 2
            
            dates = pd.date_range(start_date, end_date, freq='B')
            product_date1 = [dates.shift(1, freq='B') if t == 'da' else
                            dates.shift(1, freq='D') if t == 'd' else
                            dates.shift(tn, freq='W-MON') if t == 'w' else
                            (dates + n_s * dates.freq).shift(tn, freq='2QS-Apr') if t in ['sum', 'win'] else
                            (dates + n_s * dates.freq).shift(tn, freq=t.upper() + 'S')
                            for t, tn in zip(tenor_list, tn1_list)]
            if not tn2_list:
                product_date2 = [None] * len(product_date1)
            else:
                product_date2 = [dates.shift(1, freq='B') if t == 'da' else
                                dates.shift(1, freq='D') if t == 'd' else
                                dates.shift(tn, freq='W-MON') if t == 'w' else
                                (dates + n_s * dates.freq).shift(tn, freq='2QS-Apr') if t in ['sum', 'win'] else
                                (dates + n_s * dates.freq).shift(tn, freq=t.upper() + 'S')
                                for t, tn in zip(tenor_list, tn2_list)]
            
            if not tn2_list:
                tn_list = [str(t1) for t1 in tn1_list]
            else:
                tn_list = [str(t1) + '_' + str(t2) for (t1, t2) in zip(tn1_list, tn2_list)]
            
            start_time = time(8, 0, 0)
            end_time = time(20, 0, 0)
            
            
            # df_ord_data = data_class.get_orders_data(mkt, tenor, venue_list, start_date,
            #                                          bT, eT, prod)
            
            ba_data_dict = {m + t + n: [] for m, t, n in zip(mkt_list, tenor_list, tn_list)}
            tr_data_dict = {m + t + n: [] for m, t, n in zip(mkt_list, tenor_list, tn_list)}
            
            for m, t, n, p1_d, p2_d in zip(mkt_list, tenor_list, tn_list, product_date1,
                                        product_date2):
                df_ba = pd.DataFrame([])
                df_tr = pd.DataFrame([])
                df_ob = pd.DataFrame([])
                if p2_d is None:
                    df_prod_dates = pd.DataFrame([p1_d], columns=dates).T
                else:
                    df_prod_dates = pd.DataFrame([p1_d, p2_d], columns=dates).T
                for p_d, ds in df_prod_dates.groupby(0).groups.items():
                    bT = datetime.combine(ds[0], start_time)
                    eT = datetime.combine(ds[-1], end_time)
                    if p2_d is None:
                        pd_2 = None
                    else:
                        pd_2 = df_prod_dates.loc[ds[0], 1]
                    # Bid Ask
                    # data_class.create_connection('PostgreSQL')
                    df_ba_aux = data_class.get_best_orders_data(m, t, p_d, bT, eT, prod,
                                                                pd_2)
                    if df_ba_aux.empty:
                        continue
                    df_ba_aux = df_ba_aux.between_time(start_time, end_time)
                    #df_ba_aux = data_class.filter_data(df_ba_aux, df_ba_aux['bidbestprice'], 20)
                    df_ba = pd.concat([df_ba, df_ba_aux])
                    # Trades
                    # data_class.create_connection('OracleSQL')
                    df_tr_aux = data_class.get_trades(m, t, venue_list, p_d, bT, eT, prod,
                                                    pd_2)
                    if df_tr_aux.empty:
                        continue
                    df_tr_aux = df_tr_aux.between_time(start_time, end_time)
                    df_tr_aux = data_class.filter_data(df_tr_aux, df_tr_aux['price'], 20)
                    df_tr = pd.concat([df_tr, df_tr_aux])
                    # Orders
                    # data_class.create_connection('OracleSQL')
                    df_ob_aux = data_class.get_orders_data(m, t, venue_list, p_d, bT, eT, prod,
                                                    pd_2)
                    df_ob_aux = df_ob_aux.between_time(start_time, end_time)
                    # df_ob_aux = data_class.filter_data(df_ob_aux, df_ob_aux['price'], 20)
                    df_ob = pd.concat([df_ob, df_ob_aux])
            if df_ba.empty or df_tr.empty:
                continue
            else:
                df_ba = df_ba.dropna()
                df_ba['mid'] = df_ba.mean(axis=1)
                
                trades = df_tr.loc[df_tr['broker_id']==14].copy()
                trades['datetime_seconds'] = trades.index.floor('S')
                grouped = trades.groupby('datetime_seconds')
                result = grouped['price'].nunique()>1
            
            multiple_prices = result[result].index
            
            day_aux_dict = {'trades': trades,
                            'ba': df_ba,
                            'multiple_prices': multiple_prices}
            data_dict[month][day] = day_aux_dict
    except:
        continue

best_orders = pd.DataFrame()
all_trades = pd.DataFrame()
for month in data_dict.keys():
    for day in data_dict[month].keys():
        if best_orders.empty:
            best_orders = data_dict[month][day]['ba']
        else:
            best_orders = pd.concat([best_orders, data_dict[month][day]['ba']])
        if all_trades.empty:
            all_trades = data_dict[month][day]['trades']
        else:
            all_trades = pd.concat([all_trades, data_dict[month][day]['trades']])


# Pair best orders to trades and decide the side the trades was made on based on
# where is the trade in relation to the middle

best_orders['datetime_seconds'] = best_orders.index
df_ba_aux = best_orders.set_index('datetime_seconds').resample('S').ffill()
trades_aux = all_trades[['price','volume', 'datetime_seconds']].set_index('datetime_seconds')
data = trades_aux[['price', 'volume']].reset_index().merge(df_ba_aux.reset_index(),
                                                on='datetime_seconds', how='left')
data = data.set_index('datetime_seconds')
data['trade_side'] = np.where(data['mid']>data['price'], 0,1)

price_within = np.where(((data['bidbestprice']<=data['price'])&(data['askbestprice']>=data['price'])),1,0).mean()

print('Price is within best orders: ', str(price_within))

data = data.reset_index()




# Define the new grouping condition
condition = (
    (data['price'] != data['price'].shift()) |
    (data['trade_side'] != data['trade_side'].shift()) |
    (data['datetime_seconds'].dt.date != data['datetime_seconds'].shift().dt.date)
)
data['group'] = condition.cumsum()

# Perform the cumulative sum within each group for 'volume'
data['cumulative_volume'] = data.groupby('group')['volume'].cumsum()

# Perform the cumulative average within each group for 'action'
data['average_action'] = data.groupby('group')['trade_side'].cumsum() /\
    (data.groupby('group')['trade_side'].cumcount() + 1)

# grouped_data = data.gr

grouped_data = data.groupby('group').last()
grouped_data['date'] = grouped_data['datetime_seconds'].dt.date

ob_dict = {}
ob_dict['active'] = {}
ob_dict['pasive'] = {}
for date in grouped_data['date'].drop_duplicates():
    active_dict = {}
    active_dict[0] = {}
    active_dict[1] = {}
    pasive_dict = {}
    pasive_dict[0] = {}
    pasive_dict[1] = {}
   
    

    for i, row in grouped_data.loc[grouped_data['date']==date].iterrows():
        
        if not active_dict[row['trade_side']]:
            active_dict[row['trade_side']] = {row['price']:[row['cumulative_volume']]}
            
        else:
            if 0 in active_dict.keys():
                keys_list = list(active_dict[0].keys())
                for stored_price in keys_list:
                    if row['price'] < stored_price:
                        if not pasive_dict[0]:
                            pasive_dict[0] = {stored_price: {1: active_dict[0][stored_price]}}
                            del active_dict[0][stored_price]
                            
                        else:
                            if stored_price not in pasive_dict[0].keys():
                                pasive_dict[0][stored_price] = {1: active_dict[0][stored_price]}
                            else:
                                new_index = max(pasive_dict[0][stored_price].keys()) + 1
                                pasive_dict[0][stored_price][new_index] = active_dict[0][stored_price]
                            del active_dict[0][stored_price]
                if row['trade_side'] == 0:
                    if row['price'] in active_dict[row['trade_side']].keys():
                        active_dict[row['trade_side']][row['price']].append(row['cumulative_volume'])
                    else:
                        active_dict[row['trade_side']][row['price']] = [row['cumulative_volume']]
            else:
                pass
            if 1 in active_dict.keys():
                keys_list = list(active_dict[1].keys())
                for stored_price in keys_list:
                    if row['price'] > stored_price:
                        if not pasive_dict[1]:
                            pasive_dict[1] = {stored_price: {1: active_dict[1][stored_price]}}
                            del active_dict[1][stored_price]
                        else:
                            if stored_price not in pasive_dict[1].keys():
                                pasive_dict[1][stored_price] = {1: active_dict[1][stored_price]}
                            else:
                                new_index = max(pasive_dict[1][stored_price].keys()) + 1
                                pasive_dict[1][stored_price][new_index] = active_dict[1][stored_price]
                            del active_dict[1][stored_price]
                if row['trade_side'] == 1:
                    if row['price'] in active_dict[row['trade_side']].keys():
                        active_dict[row['trade_side']][row['price']].append(row['cumulative_volume'])
                    else:
                        active_dict[row['trade_side']][row['price']] = [row['cumulative_volume']]
            else:
                pass

            
                        
                        
    ob_dict['active'][date] = active_dict
    ob_dict['pasive'][date] = pasive_dict
    
iceberg_list = []
    
for a_p in ob_dict.keys():
    for date in ob_dict[a_p].keys():
        for price in ob_dict[a_p][date].keys():
            for index in ob_dict[a_p][date][price].keys():
                iceberg_list.append(sum(ob_dict[a_p][date][price][index]))
    
iceberg_volumes = pd.Series(iceberg_list)
           
n = len(iceberg_list)

def get_iceberg_probability(iceberg_volumes, iceberg_min_value):
    result_dict = {k: -1 for k in iceberg_volumes.value_counts().loc[
        lambda x: x.index < iceberg_min_value].sort_index().index}
    n = iceberg_volumes.count()
    pmf = iceberg_volumes.value_counts().sort_index()

    for volume in result_dict.keys():
        # A Event: iceberg length >= iceberg_min_value
        # B Event: iceberg length >= volume
        # Omega sample space: pmf
        # P(A|B) = pmf.loc/
        p_A = pmf.loc[pmf.index >= iceberg_min_value].sum()/n
        p_B = 1 - pmf.loc[pmf.index <= volume].sum()/n
        result_dict[volume] = p_A / p_B
    
    return result_dict

# histogram
iceberg_volumes.value_counts().sort_index()
get_iceberg_probability(iceberg_volumes, 15)

