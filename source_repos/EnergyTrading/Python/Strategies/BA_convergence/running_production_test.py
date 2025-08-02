import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, time, timedelta
from SynthSpread.spreadviewer_class import SpreadSingle, SpreadViewerData, norm_coeff
#from Database.TPData import TPData, TPDataDa, TPDataAssembly

from Strategies.BA_convergence.backtest_class import BacktestLL
from Strategies.BA_convergence.strategy_class import StrategyLL, VolumeClass
tol=(1e-1)/2

instr = 'm2'

ba_conv_large_threshold=0.03
ba_conv_small_threshold=0.01
ba_conv_volatility_threshold=0.05
ba_conv_ba_threshold=0.09

burnout_period=60
stop_profit = 0.3
makeagg_ratio = 0.6
trail_stop=1

take_profit=2
stop_loss=-1

br_fee = 0.0175
closing_mode='Martinovo_zatvaranie'

MACD_long_threshold = 0.0
MACD_short_threshold = -0.05

minimum_intensity=0

br_fee = 0.0175
closing_mode='Martinovo_zatvaranie'

##########################
data_trades = pd.read_csv(r's:\Algo\Files\andrej\Data\data_instrument_trades_production_sample_dem2_our_db.csv')
data_lag = pd.read_csv(r's:\Algo\Files\andrej\Data\int_data_lag_production_sample_dem2_our_db.csv',
                    parse_dates=['datetime']).reset_index()

data_trades['datetime'] = pd.to_datetime(data_trades['Unnamed: 0'])
del data_trades['Unnamed: 0']

data_trades['datetime']=pd.to_datetime(data_trades['datetime'], format='mixed')
data_lag['datetime']=pd.to_datetime(data_lag['datetime'], format='mixed')

data_lag['time_diff']=data_lag['datetime'].diff().dt.total_seconds().fillna(0)

data_trades=data_trades[data_trades['datetime'].apply(lambda x: x.hour>8 and  x.hour<18)]
data_lag=data_lag[data_lag['datetime'].apply(lambda x: x.hour>8 and  x.hour<18)]

# # Identify rows where bid_price and ask_price are the same as the previous row
# same_prices = (data_lag["bid_price"] == data_lag["bid_price"].shift()) & (data_lag["ask_price"] == data_lag["ask_price"].shift())
#
# # Identify rows where neither the current nor the previous row has a trade price
# no_trade = data_lag["trd_price"].isna() & data_lag["trd_price"].shift().isna()
#
# # Remove rows where both conditions hold (consecutive bid/ask prices & no trades)
# data_lag = data_lag[~(same_prices & no_trade)]
# #data_lag=data_lag.drop(index=177223).reset_index()
# # del data_lag['level_0']
# # del data_lead['level_0']

data_lag.head()

##########################
contr_vars = []

param_list = ['t_end', 'take_profit', 'stop_loss']
param_dict = {k: [] for k in param_list}
param_dict['t_end'] = time(17)
param_dict['take_profit'] = take_profit
param_dict['stop_loss'] = stop_loss
param_dict['ba_max']=0.3

param_dict['br_fee'] = br_fee


param_dict['ba_conv_large_threshold']=ba_conv_large_threshold
param_dict['ba_conv_small_threshold']=ba_conv_small_threshold
param_dict['ba_conv_volatility_threshold']=ba_conv_volatility_threshold
param_dict['ba_conv_ba_threshold']=ba_conv_ba_threshold

param_dict['MACD_long_threshold'] = MACD_long_threshold
param_dict['MACD_short_threshold'] = MACD_short_threshold

param_dict['minimum_intensity'] = minimum_intensity

param_dict['burnout_period']=burnout_period
param_dict['stop_profit']=stop_profit
param_dict['makeagg_ratio']=makeagg_ratio
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

xx = backtest_class.simulate_strategy(strategy_class, instr, data_lag, data_trades)

df = pd.DataFrame({k: strategy_class.stats_dict[k] for k in list(strategy_class.stats_dict.keys()) if k in ['timestamp', 'position', 'price_level']})
df = pd.concat([df, ])

print(xx)
##########################