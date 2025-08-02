import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, time, timedelta
from SynthSpread.spreadviewer_class import SpreadSingle, SpreadViewerData, norm_coeff
#from Database.TPData import TPData, TPDataDa, TPDataAssembly

from Strategies.LeadLagFromDatamart.backtest_class import BacktestLL
from Strategies.LeadLagFromDatamart.strategy_class import StrategyLL, VolumeClass
tol=(1e-1)/2

instr = 'm2'

MACD_long_threshold = 0.075
MACD_short_threshold = -0.050
price_diff_long_threshold = 0.150
price_diff_short_threshold = -0.100

combined_long_threshold = 0.25
combined_short_threshold = 0.25

combined_mode=False
minimum_intensity=0.45

burnout_period=60
stop_profit = 0.3
makeagg_ratio = 0.6
trail_stop=0.8

fit_reg_coef=True
coef1=0.00000001
coef2=0.35

take_profit=2
stop_loss=-1

br_fee = 0.0175
closing_mode='Martinovo_zatvaranie'

##########################
data_lead = pd.read_csv(r's:\Algo\Files\andrej\Data\int_data_lead_production_sample.csv',
                    parse_dates=['datetime']).reset_index()

data_lag = pd.read_csv(r's:\Algo\Files\andrej\Data\int_data_lag_production_sample.csv',
                    parse_dates=['datetime']).reset_index()

data_lead['datetime']=pd.to_datetime(data_lead['datetime'], format='mixed')
data_lag['datetime']=pd.to_datetime(data_lag['datetime'], format='mixed')

data_lag['time_diff']=data_lag['datetime'].diff().dt.total_seconds().fillna(0)

data_lead=data_lead[data_lead['datetime'].apply(lambda x: x.hour>8 and  x.hour<18)]
data_lag=data_lag[data_lag['datetime'].apply(lambda x: x.hour>8 and  x.hour<18)]

##########################
contr_vars = []

param_dict = {}
param_dict['t_end'] = time(17)
param_dict['take_profit'] = take_profit
param_dict['stop_loss'] = stop_loss
param_dict['ba_max'] = 0.3
param_dict['aggloss_thres'] = 0.04


param_dict['br_fee'] = br_fee

param_dict['MACD_long_threshold'] = MACD_long_threshold
param_dict['MACD_short_threshold'] = MACD_short_threshold
param_dict['price_diff_long_threshold'] = price_diff_long_threshold
param_dict['price_diff_short_threshold'] = price_diff_short_threshold

param_dict['combined_long_threshold'] = combined_long_threshold
param_dict['combined_short_threshold'] = combined_short_threshold

param_dict['burnout_period']=burnout_period
param_dict['stop_profit']=stop_profit
param_dict['makeagg_ratio']=makeagg_ratio
param_dict['trail_stop']=trail_stop

param_dict['fit_reg_coef'] = fit_reg_coef
param_dict['coef1'] = coef1
param_dict['coef2'] = coef2

param_dict['combined_mode'] = combined_mode
param_dict['minimum_intensity'] = minimum_intensity


##########################

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

xx = backtest_class.simulate_strategy(strategy_class, instr, data_lag, data_lead)

df = pd.DataFrame({k: strategy_class.stats_dict[k] for k in list(strategy_class.stats_dict.keys()) if k in ['timestamp', 'position', 'price_level']})
df = pd.concat([df, ])

print(xx)