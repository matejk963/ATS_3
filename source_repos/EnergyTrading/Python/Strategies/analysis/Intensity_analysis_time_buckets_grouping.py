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
from lifetimes.plotting import plot_frequency_recency_matrix
from lifetimes.plotting import plot_probability_alive_matrix
from lifetimes.plotting import plot_history_alive, plot_history_prediction
from lifetimes.plotting import plot_period_transactions



   
assembler = TDA(source='database')
params_dict = {}

params_dict['tenor_list'] = ['m']
params_dict['tn1_list'] = [1]
params_dict['mkt_list'] = ['de'] * len(params_dict['tenor_list'])
params_dict['tn2_list'] = []
params_dict['prod'] = 'base'
params_dict['venue_list'] = ['eex']*len(params_dict['mkt_list'])
params_dict['start_date'] = datetime(2023, 11, 1)
params_dict['end_date'] = datetime(2023, 11, 25)
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
# bid_trades = bid_trades.reset_index()
freq = '1T'
time_buckets = bid_trades.resample(freq).size()

id_mapping = time_buckets.reset_index().reset_index().rename(columns={'index': 'ID',
                                                                      'datetime': 'floor'})
id_mapping = id_mapping[['floor', 'ID']]
bid_trades = bid_trades.reset_index()


bid_trades['floor'] = bid_trades['datetime'].dt.floor(freq)
bid_trades = bid_trades.merge(id_mapping, on='floor', how='left')

bid_trades['datetime'] = bid_trades['datetime'].dt.floor('S')
bid_trades['time'] = bid_trades['datetime'] - bid_trades['floor']
# bid_trades['time'] = bid_trades['time'].apply(lambda x: "{:02d}:{:02d}".format(x.seconds // 60, x.seconds % 60))
bid_trades['datetime'] = dt.datetime(2024,1,1) + bid_trades['time']
bid_trades = bid_trades[['datetime', 'ID']].copy()

summary = summary_data_from_transaction_data(bid_trades, 'ID', 'datetime', freq='s')    


bgf = BetaGeoFitter(penalizer_coef=0)


bgf.fit(summary['frequency'], summary['recency'], summary['T'])

print(bgf)

plot_frequency_recency_matrix(bgf)
# plot_probability_alive_matrix(bgf)


   
days_since_birth = 1
max_summary = summary['frequency'].idxmax()
sp_trans = bid_trades.loc[bid_trades['ID']==3371].copy()

sp_trans['datetime'] = sp_trans['datetime'].dt.strftime('%Y-%m-%d %H:%M:%S')

# plot_history_alive(bgf, days_since_birth, sp_trans, 'datetime', freq='s')
# plt.show()

# plot_period_transactions(bgf)

plot_history_prediction(bgf, days_since_birth, sp_trans, 'datetime', freq='s')
