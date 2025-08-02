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

# In[6]:


from datetime import datetime, time
import pandas as pd
import numpy as np

from Strategies.BA_convergence.calibration import LLStrategyCalibration
from Strategies.BA_convergence.backtest_class import BacktestLL
from Strategies.BA_convergence.strategy_class import StrategyLL, VolumeClass

tol = (1e-1) / 2

# # Data preparation

# In[8]:
if __name__ == '__main__':
    data_lag = pd.read_csv(r's:\Algo\Files\andrej\Data\int_data_lag_dey1_sep_oct_our_db.csv',
                           parse_dates=['datetime']).reset_index()

    # In[9]:
    data_lag['datetime'] = pd.to_datetime(data_lag['datetime'], format='mixed')

    data_lag['time_diff'] = data_lag['datetime'].diff().dt.total_seconds().fillna(0)

    # In[10]:
    data_lag = data_lag[data_lag['datetime'].apply(lambda x: x.hour > 8 and x.hour < 18)]

    data_lag['ba_spread'] = data_lag['ask_price'] - data_lag['bid_price']

    #data_lag = data_lag.reset_index()
    #del data_lag['level_0']

    # # Parameters

    # In[13]:

    # Parameters to calibrate
    opt_param = ['ba_conv_large_threshold', 'ba_conv_small_threshold', 'ba_conv_volatility_threshold', 'ba_conv_ba_threshold',
                 'MACD_long_threshold', 'MACD_short_threshold', 'minimum_intensity' ,
                 'burnout_period', 'stop_profit', 'makeagg_ratio', 'trail_stop',
                 'take_profit', 'stop_loss']

                     
    opt_param_val = [[0.04], [0.01], [0.5], [0.12],
                     [0.04], [-0.04], [0.5],
                     [60], [0.3], [0.6], [0.5],
                     [2], [-1]
                     ]

    opt_param_val = [[0.06, 0.05, 0.04, 0.03], [0.005, 0.01, 0.02], [0.1, 0.05, 0.03], [0.05, 0.09,0.12,0.15],
                     [0, 0.05, 0.025], [0,-0.050,-0.025], [0,0.5,1, 1.5],
                     [60], [0.3], [0.6], [100,0.5, 1],
                     [2], [-1]
                     ]

    # Paramaters for calibration
    fix_param = ['t_end', 'br_fee', 'ba_max']
    fix_param_val = [time(17), 0.0175, 0.3]

    opt_param_dict = {k: v for k, v in zip(opt_param, opt_param_val)}
    fix_param_dict = {k: v for k, v in zip(fix_param, fix_param_val)}

    all_param_dict = {**opt_param_dict, **fix_param_dict}

    # # Strategy and Backtest classes

    # In[14]:

    # Strategy & Backtest
    instr = 'm2'
    strategy_param_list = []
    s_param_dict = {k: v for k, v in all_param_dict.items()
                    if k in strategy_param_list}

    strategy_class = StrategyLL(strategy='LL',
                                market='de',
                                instrument=instr,
                                is_overnight=False)

    strategy_class.load_params(s_param_dict, [])

    vol_class = VolumeClass(1, {'max_clips': 1})
    backtest_class = BacktestLL(vol_class)

    # Paramaters for calibration
    fix_param = ['t_end', 'br_fee', 'ba_max']
    fix_param_val = [time(17), 0.0175, 0.3]

    opt_param_dict = {k: v for k, v in zip(opt_param, opt_param_val)}
    fix_param_dict = {k: v for k, v in zip(fix_param, fix_param_val)}

    all_param_dict = {**opt_param_dict, **fix_param_dict}

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
                                closing_mode='Martinovo_zatvaranie')

    strategy_class.load_params(s_param_dict, [])

    vol_class = VolumeClass(1, {'max_clips': 1})
    backtest_class = BacktestLL(vol_class)

    # Calibration
    cal_method = ['cumpnl', 'sharp', 'max_absolute_drawdown']
    calibration_class = LLStrategyCalibration(strategy_class, cal_method, opt_param_dict,
                                              fix_param_dict)

    # # Calibration run

    # In[17]:

    out_dict = calibration_class.calibrate_p(data_lag, backtest_class, opt_param_dict, cal_method,
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