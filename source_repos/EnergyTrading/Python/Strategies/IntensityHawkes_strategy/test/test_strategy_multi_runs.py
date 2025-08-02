# -*- coding: utf-8 -*-
"""
Created on Fri Feb 23 13:20:09 2024

@author: krajcovic
"""

import warnings
warnings.filterwarnings("ignore")


from datetime import datetime, time
import pandas as pd
import numpy as np
from Math.accumfeatures import MSTD, EMA, DerivativeEMA
from Math.ti_class import TI_class, TR_class
from Database.TPData import TPData, TPDataDa
from Strategies.IntensityHawkes_strategy.calibration import HIStrategyCalibration
from SynthSpread.spreadviewer_class import SpreadSingle, SpreadViewerData, norm_coeff
from Strategies.IntensityHawkes_strategy.model_class import HawkesIntensity
from Strategies.IntensityHawkes_strategy.backtest_class import BacktestIB
from Strategies.IntensityHawkes_strategy.strategy_class import StrategyHI, VolumeClass
from Math.nlm_class import VasicekEKF, VasicekUKF
from Math.lm_class import kalman, LinearModel
tol=0.019

ba = pd.read_csv(r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Algo\dem1_ba_11_12.csv',
                    parse_dates=['datetime']).set_index('datetime')
trades = pd.read_csv(r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Algo\dem1_trades_11_12.csv',
                    parse_dates=['datetime']).set_index('datetime')

param_list = ['t_end', 'take_profit', 'stop_loss', 'ba_spread', 'ba_max']
contr_vars = ['threshold']
param_dict = {k: [] for k in param_list}
param_dict['t_end'] = time(17)
param_dict['br_fee'] = 0.0175
param_dict['take_profit'] = 0.02
param_dict['stop_loss_rat'] = 0.75
param_dict['bid_threshold'] = 5
param_dict['ask_threshold'] = 5
param_dict['train_lookback'] = 30
param_dict['trailing_tp_tau'] = 10
param_dict['trail_sl_bool'] = False

strategy_class = StrategyHI(HawkesIntensity,trades, ba, ['dem1'],
                            'MM', 'de', 'de', is_overnight=False, trailing_takeprofit=True)
# strategy_class.load_params(param_dict)

vol_class = VolumeClass(1, {'max_clips': 1})
backtest_class = BacktestIB(vol_class)

strategy_class.load_params(param_dict, contr_vars)

strategy_class.model.estimate_params()

est_params = strategy_class.model.params_dict



xx = backtest_class.simulate_strategy(strategy_class, 'de', strategy_class.model.return_data_dict()['dem1'])

df = pd.DataFrame({k: strategy_class.stats_dict[k] for k in strategy_class.stats_dict.keys() if k in ['timestamp', 'position', 'price_level']})
import plotly.graph_objects as go
import plotly.io as pio
pio.renderers.default = "browser"
from Utilities.dfutils import date_filter
# df_data = date_filter(data_dict['m1'], '2023-09-11')
df_data = trades.reset_index().drop_duplicates('datetime').set_index('datetime')
df_params = pd.DataFrame(strategy_class.monitoring_dict).drop_duplicates('timestamp').set_index('timestamp')

df_agg = pd.concat([df_data, df_params], axis=1, join='outer').dropna(subset=['price_dem1'])

fig = go.Figure()
fig.add_trace(go.Scatter(
    x=df_agg.index, y=df_agg['price_dem1'],
    mode='markers',
    customdata=[[
        '<BR><b>bid_int: </b> '+str(df_agg.loc[i, 'bid_int']),
        '<BR><b>ask_int: </b> '+str(df_agg.loc[i, 'ask_int'])
                ] for i in df_agg.index],
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