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

from Strategies.LeadLagRegression_strategy.calibration import LLStrategyCalibration
from Strategies.LeadLagRegression_strategy.backtest_class import BacktestLL
from Strategies.LeadLagRegression_strategy.strategy_class import StrategyLL, VolumeClass

tol = (1e-1) / 2

# # Data preparation

# In[8]:
if __name__ == '__main__':
    data_lead = pd.read_csv(r'z:\andrej\Data\int_data_lead_dem1_jan_feb.csv',
                            parse_dates=['datetime']).reset_index()

    data_lag = pd.read_csv(r'z:\andrej\Data\int_data_lag_deq1_jan_feb.csv',
                           parse_dates=['datetime']).reset_index()

    # In[9]:
    data_lead['datetime'] = pd.to_datetime(data_lead['datetime'], format='mixed')
    data_lag['datetime'] = pd.to_datetime(data_lag['datetime'], format='mixed')

    data_lag['time_diff'] = data_lag['datetime'].diff().dt.total_seconds().fillna(0)

    # In[10]:

    data_lead = data_lead[data_lead['datetime'].apply(lambda x: x.hour > 8 and x.hour < 18)]
    data_lag = data_lag[data_lag['datetime'].apply(lambda x: x.hour > 8 and x.hour < 18)]

    #data_lag = data_lag.reset_index()
    #del data_lag['level_0']

    # # Parameters

    # In[13]:

    # Parameters to calibrate
    opt_param = ['MACD_long_threshold', 'MACD_short_threshold', 'price_diff_long_threshold', 'price_diff_short_threshold',
                 'burnout_period', 'stop_profit', 'makeagg_ratio',
                 'take_profit', 'stop_loss']

                     
    opt_param_val = [[0.1], [-0.1], [0.1], [-0.1],
                     [60], [0.3], [0.6],
                     [1.5], [-0.5]
                     ]
    
    opt_param_val = [[0.025, 0.05, 0.075, 0.1, 0.15, 0.2], [-0.025, -0.05, -0.075, -0.1, -0.15, -0.2], [0.025, 0.05, 0.075, 0.1, 0.15, 0.2], [-0.025, -0.05, -0.075, -0.1, -0.15, -0.2],
                     [10,30,60, 90, 120], [0.3], [0.6],
                     [0.5, 1, 1.5, 2], [-0.5, -1, -1.5, -2]
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

    out_dict = calibration_class.calibrate_p(data_lag, data_lead, backtest_class, opt_param_dict, cal_method,
                                             instr=instr, cpu_percent=90)

    print(out_dict)
    # Open a file for binary write
    # import pickle
    #
    # with open('out_dict.pkl', 'wb') as file:
    #     pickle.dump(out_dict, file)
    # # In[ ]:
    #
    # n = 10
    # top_n_tuples = sorted(out_dict, key=out_dict.get, reverse=True)[:n]
    # param_list_hat = [sum(x) / n for x in zip(*top_n_tuples)]
    # params_dict_hat = {k: v for k, v in zip(opt_param, param_list_hat)}
    #
    # params_dict_hat = {'tau': 9.0, 'stop_loss_rat': 1.0, 'take_profit': 0.25,
    #                    'margin': 0.25}