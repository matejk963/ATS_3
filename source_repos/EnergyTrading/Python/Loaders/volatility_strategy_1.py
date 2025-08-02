# -*- coding: utf-8 -*-
"""
Created on Fri Sep  8 09:56:55 2023

@author: krajcovic
"""

from datetime import datetime, time
import datetime as dt
import pandas as pd
import numpy as np
from Database.TPData import TPData
from Math.ti_class import TI_class
from RiskPremium.RP_Tools import Plot2v2a, percentile_rank

import cx_Oracle

try:
    cx_Oracle.init_oracle_client(lib_dir=r"C:\oracle\instantclient_19_9")
except:
    pass

data_class = TPData()

mkt_list = ['de']
tenor_list = ['m']
tn_list = [1]
prod = 'base'
venue_list = ['eex']
start_date = datetime(2023, 5, 12)
end_date = datetime(2023, 9, 1)
n_s = 2

dates = pd.date_range(start_date, end_date, freq='B')
product_date = [dates.shift(1, freq='B') if t == 'da' else
                dates.shift(1, freq='D') if t == 'd' else
                dates.shift(tn, freq='W-MON') if t == 'w' else
                (dates + n_s * dates.freq).shift(tn, freq='2QS-Apr') if t in ['sum', 'win'] else
                (dates + n_s * dates.freq).shift(tn, freq='YS') if t in ['dec'] else
                (dates + n_s * dates.freq).shift(tn, freq=t.upper() + 'S')
                for t, tn in zip(tenor_list, tn_list)]


start_time = time(8, 0, 0)
end_time = time(18, 0, 0)

tr_data_dict = {m + t + str(n): [] for m, t, n in zip(mkt_list, tenor_list, tn_list)}
agg_dict = {'price': 'mean', 'volume': 'sum', 'action': 'first', 'broker_id': 'first'}

for m, t, n, p_dates in zip(mkt_list, tenor_list, tn_list, product_date):
    df_tr = pd.DataFrame([])
    series = pd.Series(p_dates, index=dates)
    for p_d, ds in series.groupby(series).groups.items():
        bT = datetime.combine(ds[0], start_time)
        eT = datetime.combine(ds[-1], end_time)
        # Trades
        data_class.create_connection('OracleSQL')
        df_tr_aux = data_class.get_trades(m, t, venue_list, p_d, bT, eT, prod)
        try:
            df_tr_aux = df_tr_aux.between_time(start_time, end_time)
        except(TypeError):
            pass
        #df_tr_aux = data_class.filter_data(df_tr_aux, df_tr_aux['price'], 20)
        df_tr = pd.concat([df_tr, df_tr_aux])
    df_tr = data_class.filter_data(df_tr, df_tr['price'], 20)
    df_tr = df_tr.groupby(df_tr.index).agg(agg_dict)
    tr_data_dict[m + t + str(n)] = df_tr

data_p = pd.concat({k: v['price'] for k, v in tr_data_dict.items()}, axis=1)

# Expected size of candle
tau = 10
# EMA
tau_ema = 15
ti_cls = TI_class(tau, tau_ema)
# ti_cls.plot_candles(data_p.iloc[:, 0], data_p.iloc[:, 0])
candles = ti_cls.make_candles(data_p.iloc[:, 0], data_p.iloc[:, 0])

dates = np.unique(candles.index.date)

daily_dict = {}

for date in dates:
    temp = candles.loc[candles.index.date==date].copy()
    daily_dict[date] = temp

# dates = np.unique(data_p.index.date)
# for date in dates:
#     temp = data_p.loc[data_p.index.date==date].copy()
#     daily_dict[date] = temp
    
update_dict = {} 

roll_sig_window = 20
ma_window = 10
roll_eval_window = 100
sig_thres = 2
open_thres = 5
close_thres = 0.8

comp_col = 'Close'
for key in  list(daily_dict.keys())[0:]:
    test = daily_dict[key].copy()
    if not test.empty:
        
        test['std'] = np.log(test[comp_col]/test[comp_col].shift(1)).rolling(roll_sig_window).std()
        
        test['std_rank'] = test['std'].rolling(roll_eval_window).apply(percentile_rank)
        
        test['ma'] = test[comp_col].shift(1).rolling(ma_window).mean()
        test['upB'] = test['ma'] * (1+(test['std'] * sig_thres))
        test['downB'] = test['ma'] * (1-(test['std'] * sig_thres))
        
        
        
        test = test.dropna(subset=['std_rank'])
        update_dict[key] = test.copy()
    else:
        continue



pnl_dict = {} 
#Backtest

open_col = 'Open'
close_col = 'Open'

tot_pnl = []
mean_pnl = []
for key in update_dict.keys():
    test = update_dict[key]
    open_price = None
    close_price = None
    position = None
    last_row = None
    last_index = None
    pnl_list = []
    
    pos_list = []
    open_price_list = []
    close_price_list = []
    for index, row in test.iterrows():
        if last_row is None:
            last_row = row
            last_index = index
            pnl_list.append(None)
            pos_list.append(0)
            continue
        else:
            if open_price is None:
                pnl_list.append(None)
                if row['std_rank']<open_thres:
                    if row[open_col] > last_row['upB']:
                        open_price = row[open_col] * (-1)
                        open_price_list.append(open_price)
                        position = 1
                    elif row[open_col]< last_row['downB']:
                        open_price = row[open_col]
                        open_price_list.append(open_price)
                        position = -1
                    pos_list.append(position)
                else:
                    pos_list.append(0)
            else:
                pos_list.append(position)
                if position == 1:
                    if (row[close_col]+open_price) > (2*last_row['std'])*open_price:
                        close_price = row[close_col]
                        close_price_list.append(close_price)
                elif position == -1:
                    if (-row[close_col]+open_price) > (2*last_row['std'])*open_price:
                        close_price = row[close_col] * (-1)  
                        close_price_list.append(close_price)
                if close_price is None:
                    pnl_list.append(None)
                else:
                    pnl_list.append(close_price+open_price)
                    open_price, position, close_price = None, None, None
            last_row = row
            last_index = index
    pnl_list = [0 if a is None else a for a in pnl_list]
    test['pos'] = pos_list
    test['pnl'] = pnl_list
    
    tot_pnl.append(sum(pnl_list))
    mean_pnl.append(np.mean([a  for a in pnl_list if a >0]))
    pnl_dict[key] = test.copy()

print(sum(tot_pnl))
print(np.nanmean(mean_pnl))

