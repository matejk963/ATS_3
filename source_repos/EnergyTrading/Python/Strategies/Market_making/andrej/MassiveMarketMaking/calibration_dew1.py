#!/usr/bin/env python
# coding: utf-8

# In[5]:


import warnings
warnings.filterwarnings("ignore")


# In[6]:


from datetime import datetime, time
import pandas as pd
import numpy as np

tol=(1e-1)/2




# # Data preparation

# In[8]:


import warnings

warnings.filterwarnings("ignore")

import sys,os
sys.path.append(r'C:/Users/andrej/Projects/EnergyTrading/Python/Strategies/Market_Making/andrej')
# In[6]:


from datetime import datetime, time
import pandas as pd
import numpy as np

from MassiveMarketMaking.calibration import LLStrategyCalibration
from MassiveMarketMaking.backtest_class import BacktestLL
from MassiveMarketMaking.strategy_class import StrategyLL, VolumeClass

from Utilities.excel_loaders import conn_out_xload
dates_out = [pd.to_datetime(x).date() for x in conn_out_xload()]
dates_out.append(datetime(2025, 1, 24).date())

tol = (1e-1) / 2

# # Data preparation

# In[8]:
if __name__ == '__main__':
    df = pd.read_parquet(r's:\Algo\Files\andrej\Data\MassiveMarketMaking\data_dew1_jan_jun.parquet',
                         engine='fastparquet').reset_index()

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
    df = df[df['datetime'].dt.date.apply(lambda x: x not in dates_out)]

    df['trd_price'] = df['trd_price'].apply(float)
    df['bid_price'] = df['bid_price'].fillna(method='ffill')
    df['ask_price'] = df['ask_price'].fillna(method='ffill')
    df['mid_price'] = df['mid_price'].fillna(method='ffill')


    ## Predictors adding

    from MassiveMarketMaking.support_functions import calculate_MACD, calculate_volatility

    df = calculate_MACD(df)
    df = calculate_volatility(df)
    df['ba_spread'] = df['ask_price'] - df['bid_price']
    df['mid_price'] = (df['ask_price'] + df['bid_price']) / 2
    df = df[df['datetime'].apply(lambda x: x.hour > 8 and x.hour < 18)]

    #data_lag = data_lag.reset_index()
    #del data_lag['level_0']

    # # Parameters

    # In[13]:

    # Parameters to calibrate
    opt_param = ['gamma', 'kappa', 'A']

    opt_param_val = [
        [0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
        [0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
        [0.1, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0,
         20.0]
    ]


    # Paramaters for calibration
    fix_param = ['t_end', 'br_fee', 'ba_max', 'take_profit', 'stop_loss', 'trail_stop',]
    fix_param_val = [time(17), 0.0175, 1, 2, -2, 0.3]

    opt_param_dict = {k: v for k, v in zip(opt_param, opt_param_val)}
    fix_param_dict = {k: v for k, v in zip(fix_param, fix_param_val)}

    all_param_dict = {**opt_param_dict, **fix_param_dict}

    # # Strategy and Backtest classes

    # In[14]
    # # Strategy and Backtest classes

    # In[14]:

    # Strategy & Backtest
    instr = 'm2'
    strategy_param_list = []
    s_param_dict = {k: v for k, v in all_param_dict.items()
                    }

    strategy_class = StrategyLL(strategy='LL',
                                market='de',
                                instrument=instr,
                                is_overnight=False,
                                closing_mode='Simple')

    strategy_class.load_params(s_param_dict, [])

    vol_class = VolumeClass(1, {'max_clips': 1})
    backtest_class = BacktestLL(vol_class)

    # Calibration
    cal_method = ['cumpnl', 'sharp', 'max_absolute_drawdown']
    calibration_class = LLStrategyCalibration(strategy_class, cal_method, opt_param_dict,
                                              fix_param_dict)

    # # Calibration run

    # In[17]:

    out_dict = calibration_class.calibrate_p(df, backtest_class, opt_param_dict, cal_method,
                                             instr=instr, cpu_percent=90)

    print(out_dict)
    #Open a file for binary write
    import pickle

    with open('out_dict.pkl', 'wb') as file:
        pickle.dump(out_dict, file)
    # In[ ]:
    #
    # n = 10
    # top_n_tuples = sorted(out_dict, key=out_dict.get, reverse=True)[:n]
    # param_list_hat = [sum(x) / n for x in zip(*top_n_tuples)]
    # params_dict_hat = {k: v for k, v in zip(opt_param, param_list_hat)}
    #
    # params_dict_hat = {'tau': 9.0, 'stop_loss_rat': 1.0, 'take_profit': 0.25,
    #                    'margin': 0.25}