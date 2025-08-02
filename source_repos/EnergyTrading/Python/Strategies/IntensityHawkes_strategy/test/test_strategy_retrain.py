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



# params_dict = {}

# params_dict['tenor_list'] = ['m']
# params_dict['tn1_list'] = [1]
# params_dict['mkt_list'] = ['de'] * len(params_dict['tenor_list'])
# params_dict['tn2_list'] = []
# params_dict['prod'] = 'base'
# params_dict['venue_list'] = ['eex']*len(params_dict['mkt_list'])
# params_dict['start_date'] = datetime(2023, 6, 1)
# params_dict['end_date'] = datetime(2023, 12, 31)
# params_dict['ns'] = 2

# # Fetch trades and best orders for the curve
# assembler = TPDataAssembly(source='trayport', user='matus')
# # assembler.set_start_end_time(start=[10,0,0], end=[12,0,0])    
# trades_dict = assembler.get_data(params_dict, target_data='trades')
# # assembler.set_data_source('trayport')
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
ba.index.name = 'datetime'
ba.to_csv(r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Algo\ba_june.csv')
trades.to_csv(r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Algo\trades_june.csv')

# ba = pd.read_csv(r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Algo\ba_test.csv',
#                     parse_dates=['datetime']).set_index('datetime')
# trades = pd.read_csv(r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Algo\trades_test.csv',
#                     parse_dates=['datetime']).set_index('datetime')

x = 14  # For example, a 7-day rolling window

# Assuming your DataFrame is indexed in ascending order
start_date = pd.to_datetime(ba.index.min().date())
end_date = pd.to_datetime(ba.index.max().date())
products = ['dem1']
# Calculate the end date of the first window
window_end_date = start_date + pd.Timedelta(days=x)

xx_dict = {}
tot_params = {}
pos_df = pd.DataFrame()
int_df = pd.DataFrame()
pnl_df = pd.DataFrame()

while window_end_date <= end_date:
    # Select the data within the current window
    aux_ba = ba[start_date:window_end_date].copy()
    train_ba = aux_ba[:(window_end_date)-timedelta(days=1)].copy()
    test_ba = aux_ba[(window_end_date)-timedelta(days=1):].copy()
    aux_trades = trades[start_date:window_end_date].copy()
    train_trades = aux_trades[:(window_end_date)-timedelta(days=1)].copy()
    test_trades = aux_trades[(window_end_date)-timedelta(days=1):].copy()
    
    # Here, perform your operations with window_df
    
    # Move the window forward by one day
    start_date += pd.Timedelta(days=1)
    window_end_date += pd.Timedelta(days=1)
    
    ti_inst = TI(train_trades, train_ba, products)
    
    ti_inst.prepare_data()
    ti_inst.set_train_size(1)
    ti_inst.set_conditions()
    ti_inst.create_train_test_dict()
    ti_inst.estimate_params(initial_quess=[1,1,1])
    
    params_dict = ti_inst.params_dict
    tot_params[end_date] = params_dict
    params = [[a,b] for a, b in zip(params_dict['dem1']['bid_params'],params_dict['dem1']['ask_params'])]
    
    ti_test = TI(test_trades,test_ba, products)
    ti_test.prepare_data()
    data_raw = ti_test.data

    data = data_raw[['price_dem1', 'volume_dem1','bidbestprice_dem1',
                      'askbestprice_dem1', 'mid_dem1', 'trade_side_dem1']].copy()
    if len(data) == 0:
        continue
    data.columns = [a.split('_')[0] for a in data.columns]
    data.columns = ['trd_price', 'volume', 'bid_price', 'ask_price', 'mid_price', 'trd_side']
    
    param_list = ['t_end', 'take_profit', 'stop_loss', 'ba_spread', 'ba_max']
    contr_vars = ['threshold']
    param_dict = {k: [] for k in param_list}
    param_dict['t_end'] = time(17)
    param_dict['br_fee'] = 0.0175
    param_dict['take_profit'] = 0.02
    param_dict['stop_loss_rat'] = 1
    param_dict['threshold'] = [params[0][0]*3, params[0][1]*3]
    param_dict['lookback'] = 14
    # param_dict['mu'] = params[0]
    # param_dict['alpha'] = params[1]
    # param_dict['beta'] = params[2]

    vol_class = VolumeClass(1, {'max_clips': 1})
    backtest_class = BacktestIB(vol_class)
    model_class = HawkesIntensity
    strategy_class = StrategyHI(model_class=model_class,
                                trades=test_trades,ba=test_ba, products=products,
                                strategy='MM',
                                market='de',
                                instrument='de', is_overnight=False)
    strategy_class.load_params(param_dict, contr_vars)

    xx = backtest_class.simulate_strategy(strategy_class, 'de', data.reset_index())
    
    xx_dict[window_end_date] = xx
    
    df = pd.DataFrame({k: strategy_class.stats_dict[k] for k in strategy_class.stats_dict.keys() if k in ['timestamp', 'position', 'price_level']})
    if pos_df.empty:
        pos_df = df.copy()
    else:
        pos_df = pd.concat([pos_df, df])
    
    if int_df.empty:
        int_df = pd.DataFrame(strategy_class.monitoring_dict).drop_duplicates('timestamp').set_index('timestamp')
    else:
        aux = pd.DataFrame(strategy_class.monitoring_dict).drop_duplicates('timestamp').set_index('timestamp')
        int_df = pd.concat([int_df, aux])
        
    pnl_dict = backtest_class.pnl_dict
    aux_pnl = pd.DataFrame([[date, item] for item, date in zip(pnl_dict['timestamp'], pnl_dict['pnl']) if item!=0], columns=['timestamp', 'pnl'])
    aux_pnl = pd.DataFrame({
            'pnl': aux_pnl.groupby(aux_pnl.index // 2)['pnl'].sum(),
            'timestamp': aux_pnl.iloc[::2]['timestamp'].values  # Take timestamp from even rows
        }).reset_index(drop=True)
    # if pnl_df.empyt:
        
    
    
pnl = pd.DataFrame()
for date, xx in xx_dict.items():
    if pnl.empty:
        pnl = xx.copy()
        last_pnl = pnl.dropna().iloc[-1]
    else:
        pnl = pd.concat([pnl, xx+last_pnl])
        last_pnl = pnl.dropna().iloc[-1]

pnl_std = pnl.diff().std()
pnl_mean = pnl.diff().mean()
pnl_sharpe = pnl_mean/pnl_std
    
    
    


