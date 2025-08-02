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
from Strategies.Intensity_class import adjust_datetime_precision
from lifetimes.datasets import load_transaction_data
from lifetimes.utils import summary_data_from_transaction_data
from lifetimes.utils import calibration_and_holdout_data
from lifetimes import BetaGeoFitter



   
assembler = TDA(source='database')
params_dict = {}

params_dict['tenor_list'] = ['m', 'm', 'm', 'q', 'q', 'q', 'q', 'y', 'y']
params_dict['tn1_list'] = [1,2,3,1,2,3,4,1,2]
params_dict['mkt_list'] = ['de'] * len(params_dict['tenor_list'])
params_dict['tn2_list'] = []
params_dict['prod'] = 'base'
params_dict['venue_list'] = ['eex']*len(params_dict['mkt_list'])
params_dict['start_date'] = datetime(2023, 11, 20)
params_dict['end_date'] = datetime(2023, 11, 20)
params_dict['ns'] = 2

# Fetch trades and best orders for the curve
assembler = TDA(source='trayport')
# assembler.set_start_end_time(start=[10,0,0], end=[12,0,0])    
trades_dict = assembler.get_data(params_dict, target_data='trades')
assembler.set_data_source('database')
ba_dict = assembler.get_data(params_dict, target_data='best_orders')

assert ba_dict.keys() == trades_dict.keys(), "Curve doesn't fit for both trades and best_orders"

# Go key by key(product by product) in dictionaries and process through Intensity Class
# together to get proper trade side
# Concat the porcessed products to one df
data = pd.DataFrame()
for key in trades_dict.keys():
    trades_aux = trades_dict[key].loc[trades_dict[key]['broker_id']==14].copy()
    ba_aux = ba_dict[key]
    # iInitalize IntClass with each key
    int_inst = TI(trades_aux, ba_aux)
    int_inst.set_conditions()
    data_aux = int_inst.data
    data_aux['id'] = key
    if data.empty:
        data = data_aux.copy()
    else:
        data = pd.concat([data, data_aux])

bid_trades = data.loc[data['bid_trade']==1]['id'].copy()
bid_trades = bid_trades.reset_index()


bid_trades_adj = adjust_datetime_precision(bid_trades, 'datetime', 'S')
# bid_trades_adj = bid_trades.copy()
# bid_trades_adj['datetime'] = pd.to_datetime(bid_trades_adj['datetime'].dt.date)

summary = summary_data_from_transaction_data(bid_trades_adj, 'id', 'datetime', freq='s')    


bgf = BetaGeoFitter(penalizer_coef=1)

# trade = summary.iloc[[0]]
# trade = summary.iloc[[1]]

bgf.fit(summary['frequency'], summary['recency'], summary['T'])

print(bgf)


from lifetimes.plotting import plot_history_alive

# Get train data on the first 10% of data in day
#10% index
fraction_index = len(bid_trades_adj)//1
train_data = bid_trades_adj.sort_values('datetime').iloc[:fraction_index].copy()
# train_data = train_data.set_index('datetime').resample('h').sum()
# test_data = bid_trades_adj.sort_values('datetime').iloc[fraction_index:int(fraction_index*1.5)].copy()

train_summary = summary_data_from_transaction_data(train_data, 'id', 'datetime', freq='s')

bgf1 = BetaGeoFitter(penalizer_coef=0.1)
bgf1.fit(train_summary['frequency'],
         train_summary['recency'],
         train_summary['T'])
print(bgf1.summary)
   
# days_since_birth = 5
# sp_trans = test_data.loc[test_data['id']=='dem2'].copy()
# sp_trans['datetime'] = sp_trans['datetime'].dt.floor('S')

# # sp_trans = sp_trans.groupby(['datetime']).sum()
# # sp_trans = sp_trans.reset_index()
# # sp_trans['datetime'] = sp_trans['datetime'].dt.strftime('%Y-%m-%d %H:%M:%S')

# plot_history_alive(bgf1, days_since_birth, sp_trans, 'datetime', freq='s')

trans_data = load_transaction_data().sort_values('date')

trans_summary = summary_data_from_transaction_data(trans_data, 'id', 'date', observation_period_end='2014-12-31')

bgf2 = BetaGeoFitter(penalizer_coef=0)
bgf2.fit(trans_summary['frequency'],
         trans_summary['recency'],
         trans_summary['T'])
print(bgf2.summary)

days_since_birth = 200
sp_trans = trans_data.loc[trans_data['id']==3552].copy()

plot_history_alive(bgf2, days_since_birth, sp_trans, 'date')
