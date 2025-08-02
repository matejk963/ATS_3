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
from Strategies.IntensityHawkes_strategy.model_class_daily_retraining import HawkesIntensity
from Strategies.IntensityHawkes_strategy.backtest_class import BacktestIB
from Strategies.IntensityHawkes_strategy.strategy_class import StrategyHI, VolumeClass
from Math.nlm_class import VasicekEKF, VasicekUKF
from Math.lm_class import kalman, LinearModel
tol=0.019

ba = pd.read_csv(r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Algo\dem1_ba_6_12.csv',
                    parse_dates=['datetime']).set_index('datetime')
trades = pd.read_csv(r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Algo\dem1_trades_6_12.csv',
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
param_dict['train_lookback'] = 21
param_dict['trailing_tp_tau'] = 5

strategy_class = StrategyHI(HawkesIntensity,trades, ba, ['dem1'],
                            'MM', 'de', 'de', is_overnight=False, trailing_takeprofit=False)

strategy_class.model.estimate_params()

params_dict = strategy_class.model.params_dict

# mu = []
# alpha = []
# beta = []
# for date, dates_dict in params_dict.items():
#     for prod, prod_dict in dates_dict.items():
#         for ba, ba_list in prod_dict.items():
#             mu.append(ba_list[0])
#             alpha.append(ba_list[1])
#             beta.append(ba_list[2])
            
# mu_df = pd.DataFrame(mu)
# alpha_df = pd.DataFrame(alpha)
# alpha_df.rolling(30).mean().plot()
# beta_df = pd.DataFrame(beta)
# beta_df.rolling(30).mean().plot()
            
            