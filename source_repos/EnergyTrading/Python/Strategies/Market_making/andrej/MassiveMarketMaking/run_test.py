import sys,os
sys.path.append(r'C:/Users/andrej/Projects/EnergyTrading/Python/Strategies/Market_Making/andrej')

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, time, timedelta
from SynthSpread.spreadviewer_class import SpreadSingle, SpreadViewerData, norm_coeff
#from Database.TPData import TPData, TPDataDa, TPDataAssembly
from Database.DB_reader import Database

from MassiveMarketMaking.backtest_class import BacktestLL
from MassiveMarketMaking.strategy_class import StrategyLL, VolumeClass
tol=(1e-1)/2

import warnings
warnings.filterwarnings('ignore')

from Utilities.excel_loaders import conn_out_xload
dates_out = [pd.to_datetime(x).date() for x in conn_out_xload()]
dates_out.append(datetime(2025, 1, 24).date())



#5	17	0.1	1.00	-0.75

#0.08	-0.08	0.08	-0.10	1.5	60	0.3	0.6	0.50	2.0	-2.0

#0.04	-0.04	0.06	-0.06	1.2	60	0.3	0.6	0.8 2.0	-1.5 -> around 40, stable perf
#0.04	-0.04	0.06	-0.06	0.7	60	0.3	0.6	0.8	 2.0	-1 -> around 51, weak perf on prod sample
#0.075	-0.050	0.150	-0.100	0.45	60	0.3	0.6	0.8	 2.0	-1 -> around 41, good stable performance overall
#other combinations do not work well on prod sample

gamma=2 #risk appetite
kappa=4 #sensitivity of trade arrival rate to spread
A=100 #base trade arrival rate at spread 0

#long_threshold = 2
#short_threshold = 2

#burnout_period=60
#stop_profit = 0.3
#makeagg_ratio = 0.6
trail_stop=0.3

take_profit=2
stop_loss=-2
#aggloss_thres=0.04

br_fee = 0.0175
closing_mode='Simple'

# OOT part -Jan25, Jun25

## Data preparation

df=pd.read_parquet(r's:\Algo\Files\andrej\Data\MassiveMarketMaking\data_dew1_jan_jun.parquet', engine='fastparquet').reset_index()

# Create floored timestamp to the millisecond
df['ts_millis'] = df['datetime'].dt.floor('ms')

# Get next row's values for comparison
next_trade = df['trd_price'].shift(-1)
next_ts_millis = df['ts_millis'].shift(-1)

# Condition 1: Non-trade row just before a trade in same millisecond → shift timestamp
mask_shift = (
    df['trd_price'].isna() &
    next_trade.notna() &
    (df['ts_millis'] == next_ts_millis)
)

# Shift timestamp of those rows forward by 1 millisecond
df.loc[mask_shift, 'datetime'] += pd.Timedelta(milliseconds=1)

# Condition 2: Invalid rows with bid >= ask → drop them
mask_drop = df['bid_price'].notna() & df['ask_price'].notna() & (df['bid_price'] >= df['ask_price'])

# Drop invalid rows
df = df[~mask_drop].drop(columns='ts_millis').sort_values(by='datetime').reset_index()

import decimal
df = df.applymap(lambda x: float(x) if isinstance(x, decimal.Decimal) else x)
df=df[df['datetime'].dt.date.apply(lambda x: x not in dates_out)]

df['trd_price']=df['trd_price'].apply(float)
df['bid_price']=df['bid_price'].fillna(method='ffill')
df['ask_price']=df['ask_price'].fillna(method='ffill')
df['mid_price']=df['mid_price'].fillna(method='ffill')

df.head()

## Predictors adding

from MassiveMarketMaking.support_functions import calculate_MACD, calculate_volatility

df=calculate_MACD(df)
df=calculate_volatility(df)
df['ba_spread']=df['ask_price']-df['bid_price']
df['mid_price']=(df['ask_price']+df['bid_price'])/2
df=df[df['datetime'].apply(lambda x: x.hour>8 and  x.hour<18)]

df

## Parameters and calculations

data_lead=df.copy()

instr = 'm2'

contr_vars = []

param_list = ['t_end', 'take_profit', 'stop_loss']
param_dict = {k: [] for k in param_list}
param_dict['t_end'] = time(17)
param_dict['take_profit'] = take_profit
param_dict['stop_loss'] = stop_loss
param_dict['ba_max']=1
#param_dict['aggloss_thres']=aggloss_thres

param_dict['gamma']=gamma
param_dict['kappa']=kappa
param_dict['A']=A


param_dict['br_fee'] = br_fee

#param_dict['long_threshold'] = long_threshold
#param_dict['short_threshold'] = short_threshold


#param_dict['burnout_period']=burnout_period
#param_dict['stop_profit']=stop_profit
#param_dict['makeagg_ratio']=makeagg_ratio
param_dict['trail_stop']=trail_stop


vol_class = VolumeClass(1, {'max_clips': 1})
backtest_class = BacktestLL(vol_class)
# model_class = HawkesIntensity
strategy_class = StrategyLL(
                            strategy='LL',
                            market='de',
                            instrument=instr,
                            is_overnight=False,
                            closing_mode=closing_mode)

strategy_class.load_params(param_dict, contr_vars)

xx = backtest_class.simulate_strategy(strategy_class, instr, df)

df = pd.DataFrame({k: strategy_class.stats_dict[k] for k in list(strategy_class.stats_dict.keys()) if k in ['timestamp', 'position', 'price_level']})
df = pd.concat([df, ])

print(xx[-1:])