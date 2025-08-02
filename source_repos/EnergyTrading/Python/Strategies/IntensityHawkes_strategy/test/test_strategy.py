#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Dec 10 17:26:13 2023

@author: marek
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, time, timedelta
import datetime as dt
from SynthSpread.spreadviewer_class import SpreadSingle, SpreadViewerData, norm_coeff
from Database.TPData import TPData, TPDataDa, TPDataAssembly
from Strategies.MultipleMarketsIntensity_class import MultiTradeIntensity as TI
from Math.ti_class import TI_class, VI_class, TR_class
from Math.lm_class import kalman, LinearModel
from Math.accumfeatures import EMA, MA, MSTD, DifferentialEMA, DerivativeEMA
from Strategies.IntensityHawkes_strategy.model_class import HawkesIntensity
from Strategies.IntensityHawkes_strategy.backtest_class import BacktestIB
from Strategies.IntensityHawkes_strategy.strategy_class import StrategyHI, VolumeClass
tol=(1e-1)/2



params_dict = {}

params_dict['tenor_list'] = ['w']
params_dict['tn1_list'] = [1]
params_dict['mkt_list'] = ['de'] * len(params_dict['tenor_list'])
params_dict['tn2_list'] = []
params_dict['prod'] = 'base'
params_dict['venue_list'] = ['eex']*len(params_dict['mkt_list'])
params_dict['start_date'] = datetime(2023, 11, 1)
params_dict['end_date'] = datetime(2023, 12, 31)
params_dict['ns'] = 2

# Fetch trades and best orders for the curve
assembler = TPDataAssembly(source='trayport', user='matej')
# assembler.set_start_end_time(start=[10,0,0], end=[12,0,0])    
trades_dict = assembler.get_data(params_dict, target_data='trades')
# assembler.set_data_source('database')
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
ba.index.name = 'datetime'

ba.to_csv(r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Algo\dew1_ba_11_12.csv')
trades.to_csv(r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Algo\dew1_trades_11_12.csv')


# # ti_inst = TI(trades, ba, products)

# # ti_inst.prepare_data()

# # ti_inst.set_train_size(0.6)
# # ti_inst.set_conditions()
# # ti_inst.create_train_test_dict()

# # ti_inst.estimate_params(initial_quess=[1,1,1])

# # params_dict = ti_inst.params_dict
# # params = [[a,b] for a, b in zip(params_dict['dem1']['bid_params'],params_dict['dem1']['ask_params'])]

# # data_raw = ti_inst.data

# # data = data_raw[['price_dem1', 'volume_dem1','bidbestprice_dem1',
# #                   'askbestprice_dem1', 'mid_dem1', 'trade_side_dem1']].copy()
# # data.columns = [a.split('_')[0] for a in data.columns]
# # data.columns = ['trd_price', 'volume', 'bid_price', 'ask_price', 'mid_price', 'trd_side']

# # data.to_csv(r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Algo\int_data_test_short.csv')
# data = pd.read_csv(r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Algo\int_data_test_short.csv',
#                     parse_dates=['datetime']).reset_index()
# # # data['trd_side']  = np.select([data['trd_price'].isna(),
# # #                                               data['trd_price'] > data['mid_price'],
# # #                                               data['trd_price'] < data['mid_price']],
# # #                                             [np.nan, 1, -1], default=np.nan)
# # data = data.reset_index()

# params = [2.16296338, 0.81137195, 2.28561668]
# params = [2.23711182, 0.79584921, 2.41585585]
# params = [[2.413510803009276, 1.9591845554221525],
#          [1.0153154836736966, 0.8939718237480951],
#          [2.060978213898335, 2.6543314794791324]]


# last_train_date = datetime(2023,12,1) + timedelta(days=1)
# test_data = data.loc[((data['datetime']>=last_train_date)&
#                       (data['datetime']<(last_train_date+timedelta(days=20))))].copy()
# instr = 'm1'
# # data_dict = {}
# # data_dict[instr] = BacktestIB.merge_data(df_ba, df_tr, False)



# param_list = ['t_end', 'take_profit', 'stop_loss', 'ba_spread', 'ba_max']
# contr_vars = ['threshold']
# param_dict = {k: [] for k in param_list}
# param_dict['t_end'] = time(17)
# param_dict['take_profit'] = 1
# param_dict['stop_loss_rat'] = 0.5
# # param_dict['ba_spread'] = 0.25
# # param_dict['ba_max'] = 1.5
# param_dict['br_fee'] = 0.0175
# param_dict['threshold'] = [params[0][0]*3, params[0][1]*3]
# param_dict['mu'] = params[0]
# param_dict['alpha'] = params[1]
# param_dict['beta'] = params[2]

# vol_class = VolumeClass(1, {'max_clips': 1})
# backtest_class = BacktestIB(vol_class)
# model_class = HawkesIntensity
# strategy_class = StrategyHI(model_class=model_class,
#                             strategy='MM',
#                             market='de',
#                             instrument=instr, is_overnight=False)
# strategy_class.load_params(param_dict, contr_vars)

# xx = backtest_class.simulate_strategy(strategy_class, instr, test_data)

# df = pd.DataFrame({k: strategy_class.stats_dict[k] for k in strategy_class.stats_dict.keys() if k in ['timestamp', 'position', 'price_level']})
# import plotly.graph_objects as go
# import plotly.io as pio
# pio.renderers.default = "browser"
# from Utilities.dfutils import date_filter
# # df_data = date_filter(data_dict['m1'], '2023-09-11')
# df_data = test_data.drop_duplicates('datetime').set_index('datetime')
# df_params = pd.DataFrame(strategy_class.monitoring_dict).drop_duplicates('timestamp').set_index('timestamp')

# df_agg = pd.concat([df_data, df_params], axis=1, join='outer').dropna(subset=['trd_price'])

# fig = go.Figure()
# fig.add_trace(go.Scatter(
#     x=df_agg.index, y=df_agg['trd_price'],
#     mode='markers',
#     customdata=[[
#         '<BR><b>bid_int: </b> '+str(df_agg.loc[i, 'bid_int']),
#         '<BR><b>ask_int: </b> '+str(df_agg.loc[i, 'ask_int'])
#                 ] for i in df_agg.index],
#     hovertemplate=
#         '<b>%{x} </b> <br>' +  # Displaying X value
#         '<b>Price Level:</b> %{y:.2f}<br>' +  # Displaying Y value with label
#         '%{customdata}'  # Displaying custom data
#     ))
# fig.add_trace(go.Scatter(
#     x=df['timestamp'],
#     y=df['price_level'],
#     mode='markers',
#     marker=dict(color=df['position'])  # Using dict() for clarity
# ))

# pio.show(fig)