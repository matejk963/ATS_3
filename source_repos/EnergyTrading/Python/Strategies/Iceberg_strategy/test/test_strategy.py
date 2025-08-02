#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Dec 10 17:26:13 2023

@author: marek
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, time
from SynthSpread.spreadviewer_class import SpreadSingle, SpreadViewerData, norm_coeff
from Database.TPData import TPData, TPDataDa, TPDataAssembly
from Math.ti_class import TI_class, VI_class, TR_class
from Strategies.MultipleMarketsIntensity_class import MultiTradeIntensity as TI
from Math.lm_class import kalman, LinearModel
from Math.accumfeatures import EMA, MA, MSTD, DifferentialEMA, DerivativeEMA
from Strategies.Iceberg_strategy.model_class import IcebergModel
from Strategies.Iceberg_strategy.backtest_class import BacktestIB
from Strategies.Iceberg_strategy.strategy_class import StrategyIB, VolumeClass
tol=(1e-1)/2


data_class = TPDataDa()

mkt_list = ['de']
tenor_list = ['m']
tn1_list = [1]
tn2_list = []
prod = 'base'
venue_list = ['eex']
start_date = datetime(2023, 9, 1)
end_date = datetime(2023, 11, 25)
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

start_time = time(9, 0, 0)
end_time = time(18, 0, 0)

tr_data_dict = {m + t + str(n): [] for m, t, n in zip(mkt_list, tenor_list, tn_list)}
ba_data_dict = {m + t + str(n): [] for m, t, n in zip(mkt_list, tenor_list, tn_list)}
agg_dict = {'price': 'mean', 'volume': 'sum', 'action': 'first', 'broker_id': 'first'}

for m, t, n, p1_d, p2_d in zip(mkt_list, tenor_list, tn_list, product_date1,
                               product_date2):
    df_ba = pd.DataFrame([])
    df_tr = pd.DataFrame([])
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
        try:
            data_class.create_connection('PostgreSQL')
            df_ba_aux = data_class.get_best_ob_data(m, t, venue_list, p_d, bT, eT, prod,
                                                        pd_2)
            df_ba_aux = df_ba_aux.between_time(start_time, end_time)
            df_ba_aux = df_ba_aux.rename(columns={'bidbestprice': 'bid', 'askbestprice': 'ask'})
            #df_ba_aux = data_class.filter_data(df_ba_aux, df_ba_aux['bidbestprice'], 20)
            df_ba = pd.concat([df_ba, df_ba_aux], axis=0)
            # Trades
            data_class.create_connection('OracleSQL')
            df_tr_aux = data_class.get_trades(m, t, venue_list, p_d, bT, eT, prod,
                                            pd_2)
        except Exception as e:
            print(e)
            continue
        try:
            df_tr_aux = df_tr_aux.between_time(start_time, end_time)
        except(TypeError):
            pass
        df_tr_aux = df_tr_aux[(df_tr_aux['broker_id']==14) |
                              (df_tr_aux['volume']<=20)]
        df_tr = pd.concat([df_tr, df_tr_aux], axis=0)
    df_tr = data_class.filter_data(df_tr, df_tr['price'], 20)
    df_tr = df_tr.groupby(df_tr.index).agg(agg_dict)

df_ba.index.rename('index', inplace=True)
df_tr.index.rename('index', inplace=True)



instr = 'm1'
data_dict = {}
data_dict[instr] = BacktestIB.merge_data(df_ba, df_tr)

# import pickle
# with open('m1_11_2023.pkl', 'rb') as file:
#     data_dict = pickle.load(file)
# -----------------------------------------------------------------
# params_dict = {}
# params_dict['tenor_list'] = ['m']
# params_dict['tn1_list'] = [1]
# params_dict['mkt_list'] = ['de'] * len(params_dict['tenor_list'])
# params_dict['tn2_list'] = []
# params_dict['prod'] = 'base'
# params_dict['venue_list'] = ['eex']*len(params_dict['mkt_list'])
# params_dict['start_date'] = datetime(2023, 10, 12)
# params_dict['end_date'] = datetime(2023, 12, 25)
# params_dict['ns'] = 2
 
# # Fetch trades and best orders for the curve
# assembler = TPDataAssembly(source='trayport', user='matej')
# # assembler.set_start_end_time(start=[10,0,0], end=[12,0,0])    
# trades_dict = assembler.get_data(params_dict, target_data='trades')
# assembler.set_data_source('database')
# ba_dict = assembler.get_data(params_dict, target_data='best_orders')
 
# assert ba_dict.keys() == trades_dict.keys(), "Curve doesn't fit for both trades and best_orders"
 
# trades = pd.DataFrame()
# ba = pd.DataFrame()
# products = []
# for key in trades_dict.keys():
#     ba_aux = ba_dict[key].copy()
#     trade_aux = trades_dict[key].copy()
#     trade_aux.columns = [a + '_' + key for a in trade_aux.columns]
#     ba_aux.columns = [a + '_' + key for a in ba_aux.columns]
#     if trades.empty:
#         trades = trade_aux.copy()
#     else:
#         trades = pd.concat([trades, trade_aux])
#     if ba.empty:
#         ba = ba_aux.copy()
#     else:
#         ba = pd.concat([ba, ba_aux])
#     products.append(key)
# trades.sort_index(inplace=True)
# ba.sort_index(inplace=True)
# ti_inst = TI(trades, ba, products)

# ti_inst.prepare_data()
# data_raw = ti_inst.data

# data = data_raw[['price_dem1', 'volume_dem1','bidbestprice_dem1',
#                   'askbestprice_dem1', 'mid_dem1', 'trade_side_dem1']].copy()
# data.columns = [a.split('_')[0] for a in data.columns]
# data.columns = ['trd_price', 'volume', 'bid_price', 'ask_price', 'mid_price', 'trd_side']
# data.index.name = 'timestamp'
# instr = 'm1'
# data_dict = {instr: data}
# ------------------------------------------------------------------------

# [(12, 0.6, 1.0, 0.25), returns 1.5 (max 4, min -.5)
#  (11, 0.6, 1.0, 0.25), returns .25 (max 3.5, min -0.5)
#  (6, 0.75, 0.5, 0.5), -3 max 1 min -3
#  (14, 0.55, 0.5, 0.5),
#  (9, 0.6, 1.0, 0.25),
#  (9, 0.6499999999999999, 1.0, 0.25),
#  (10, 0.6499999999999999, 0.5, 0.25),
#  (10, 0.6499999999999999, 0.4, 0.25),
#  (10, 0.6499999999999999, 0.4, 0.5),
#  (6, 0.7, 1.0, 0.25)]

# 12 .6 1 .35
param_list = ['t_end', 'take_profit', 'stop_loss', 'ba_spread', 'ba_max']
contr_vars = ['threshold']
param_dict = {k: [] for k in param_list}
param_dict['t_end'] = time(17, 45)

param_dict['br_fee'] = 0.035/2
param_dict['iceberg_target'] = 12
param_dict['iceberg_prob'] = .6
param_dict['trailing_tp_tau'] = 15
param_dict['take_profit'] =  .4 # percent
param_dict['stop_loss'] = -.35

vol_class = VolumeClass(1, {'max_clips': 1})
backtest_class = BacktestIB(vol_class)
model_class = IcebergModel
strategy_class = StrategyIB(model_class, 'MM', 'de', instr, is_overnight=False, trailing_takeprofit=True)
strategy_class.load_params(param_dict, contr_vars)

xx = backtest_class.simulate_strategy(strategy_class, instr, data_dict)
xx.plot()
print(len(backtest_class.profit_trade_series))

df = pd.DataFrame({k: strategy_class.stats_dict[k] for k in strategy_class.stats_dict.keys() if k in ['timestamp', 'position', 'price_level']})
import plotly.graph_objects as go
import plotly.io as pio
pio.renderers.default = "browser"
from Utilities.dfutils import date_filter
# df_data = date_filter(data_dict['m1'], '2023-10-11')
df_data = data_dict[instr]
df_params = pd.DataFrame(strategy_class.monitoring_dict)
fig = go.Figure()
fig.add_trace(go.Scatter(
    x=df_data.index, y=df_data['trd_price'], mode='markers', marker=dict(symbol="diamond"),
    customdata=[[
        '<BR><b>pb_bid: </b> '+str(df_params.loc[i, 'pb_bid']),
        '<BR><b>pb_ask: </b> '+str(df_params.loc[i, 'pb_ask']),
        '<BR><b>iceberg_bid: </b> '+str(df_params.loc[i, 'iceberg_bid']),
        '<BR><b>iceberg_ask: </b> '+str(df_params.loc[i, 'iceberg_ask']),
        '<BR><b>takeprofit_ema: </b> '+str(df_params.loc[i, 'takeprofit_ema'])
                ] for i in df_params.index],
    hovertemplate=
        '<b>%{x} </b> <br>' +  # Displaying X value
        '<b>Price Level:</b> %{y:.2f}<br>' +  # Displaying Y value with label
        '%{customdata}'  # Displaying custom data
    ))
fig.add_trace(go.Scatter(
    x=df['timestamp'],
    y=df['price_level'],
    mode='markers',
    marker=dict(color=df['position'])  # Using dict() for clarity
))

pio.show(fig)