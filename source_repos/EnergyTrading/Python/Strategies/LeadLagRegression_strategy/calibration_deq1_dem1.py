# # Data preparation

# In[8]:


import warnings

warnings.filterwarnings("ignore")

# In[6]:


from datetime import datetime, time
import pandas as pd
import numpy as np

from Strategies.LeadLagXGB.calibration import LLStrategyCalibration
from Strategies.LeadLagXGB.backtest_class import BacktestLL
from Strategies.LeadLagXGB.strategy_class import StrategyLL, VolumeClass

tol = (1e-1) / 2

# # Data preparation

# In[8]:
if __name__ == '__main__':
    data_lead = pd.read_parquet(r's:\Algo\Files\andrej\Data\int_data_lead_dem1_sep_oct.parquet', engine='fastparquet').reset_index()
    data_lag = pd.read_parquet(r's:\Algo\Files\andrej\Data\int_data_lag_frm1_sep_oct.parquet', engine='fastparquet').reset_index()

#     data_lag = pd.concat([pd.read_csv(r's:\Algo\Files\andrej\Data\int_data_lag_deq1_nov_test_short.csv',
#                         parse_dates=['datetime']).reset_index(),pd.read_csv(r's:\Algo\Files\andrej\Data\int_data_lag_deq1_dec_test_short.csv',
#                         parse_dates=['datetime']).reset_index()]).reset_index()
#     data_lag['datetime']=pd.to_datetime(data_lag['datetime'], format='mixed')
#     del data_lag['level_0']

    # In[9]:

    data_lag['time_diff'] = data_lag['datetime'].diff().dt.total_seconds().fillna(0)

    # In[10]:

    data_lead = data_lead[data_lead['datetime'].apply(lambda x: x.hour > 8 and x.hour < 18)]
    data_lag = data_lag[data_lag['datetime'].apply(lambda x: x.hour > 8 and x.hour < 18)]
    
    del data_lead['level_0']
    del data_lag['level_0']
    
    del data_lead['index']
    del data_lag['index']

    # # Parameters

    # In[13]:

    # Parameters to calibrate
    opt_param = ['MACD_long_threshold', 'MACD_short_threshold','price_diff_long_threshold', 'price_diff_short_threshold',
                 'minimum_intensity',
                 'burnout_period', 'stop_profit', 'makeagg_ratio', 'trail_stop',
                 'take_profit', 'stop_loss']


    
    opt_param_val = [[0.04,0.06,0.08,0.1], [-0.04,-0.06,-0.08,-0.1],[0.06,0.08,0.1], [-0.06,-0.08,-0.1],
                     [ 0, 0.2, 0.4, 0.6, 0.8, 1,1.2, 1.3, 1.4, 1.5, 1.6],
                     [60], [0.3], [0.6],[0.5, 0.75, 1, 1.5, 100],
                     [2,1.5, 1], [-1, -1.5, -2]
                     ]
    #
    # opt_param_val = [[0.25], [0.25], [0.25], [0.25],
    #                  [1],
    #                   [60], [0.3], [0.6],[100],
    #                   [1], [ -1]
    #                   ]

    # Paramaters for calibration
    fix_param = ['t_end', 'br_fee', 'ba_max', 'combined_mode', 'aggloss_thres', 'fit_reg_coef', 'coef1', 'coef2']
    fix_param_val = [time(17), 0.0175, 0.3, False, 0.06, True, 0, 0]

    opt_param_dict = {k: v for k, v in zip(opt_param, opt_param_val)}
    fix_param_dict = {k: v for k, v in zip(fix_param, fix_param_val)}

    all_param_dict = {**opt_param_dict, **fix_param_dict}

    # # Strategy and Backtest classes

    # In[14]:

    # Strategy & Backtest
    instr = 'm2'
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
                                             instr=instr,cpu_percent=90)
    
    print(out_dict)
    
    # Open a file for binary write
    import pickle
    with open('out_dict.pkl', 'wb') as file:
        pickle.dump(out_dict, file)
