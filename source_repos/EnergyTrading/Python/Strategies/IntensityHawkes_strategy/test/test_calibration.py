# -*- coding: utf-8 -*-
"""
Created on Tue Jan  2 17:27:15 2024

@author: Marek
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

if __name__ == '__main__':
    ba = pd.read_csv(r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Algo\ba_11_12.csv',
                        parse_dates=['datetime']).set_index('datetime')
    trades = pd.read_csv(r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Algo\trades_11_12.csv',
                        parse_dates=['datetime']).set_index('datetime')
    
    
    opt_param = ['iceberg_target', 'iceberg_prob',
                    'take_profit', 'stop_loss_rat']
    # Parameters to calibrate
    opt_param = ['bid_threshold', 'ask_threshold',
                    'take_profit', 'stop_loss_rat',
                'train_lookback']
    opt_param_val = [np.arange(5,7, 1), np.arange(5,7, 1),
                        np.arange(0.02, 0.04, 0.01), np.arange(0.75, 1.25, 0.25),
                        np.arange(21,30,7)]
    
    # Paramaters for calibration
    fix_param = ['t_end', 'br_fee']
    fix_param_val = [time(17), 0.0175]
    
    
    opt_param_dict = {k: v for k, v in zip(opt_param, opt_param_val)}
    fix_param_dict = {k: v for k, v in zip(fix_param, fix_param_val)}
    
    all_param_dict = {**opt_param_dict, **fix_param_dict}
    
    # Strategy & Backtest
    strategy_param_list = []
    s_param_dict = {k: v for k, v in all_param_dict.items()
                    if k in strategy_param_list}
    
    strategy_class = StrategyHI(HawkesIntensity,trades, ba, ['dem1'],
                                'MM', 'de', 'de', False)
    strategy_class.model.estimate_params()
    model_params = strategy_class.model.params_dict
    model_params = params_dict
    strategy_class.load_params(s_param_dict, [])
    
    vol_class = VolumeClass(1, {'max_clips': 1})
    backtest_class = BacktestIB(vol_class)
    
    # Calibration
    cal_method = 'cumpnl'
    calibration_class = HIStrategyCalibration(strategy_class, cal_method, opt_param_dict,
                                            fix_param_dict)
    out_dict = calibration_class.calibrate_p(backtest_class, HawkesIntensity, opt_param_dict, model_params,
                                            cal_method)

    # Open a file for binary write
    import pickle

    with open('out_dict.pkl', 'wb') as file:
        pickle.dump(out_dict, file)

    # Run best
    n = 10
    top_n_tuples = sorted(out_dict, key=out_dict.get, reverse=True)[:n]
    param_list_hat = [sum(x)/n for x in zip(*top_n_tuples)]
    params_dict_hat = {k: v for k, v in zip(opt_param, param_list_hat)}
    
    params_dict_hat = {'tau': 9.0, 'stop_loss_rat': 1.0, 'take_profit': 0.25,
                        'margin': 0.25}
    
    # data_train = data[instr_]['train']
    # data_tests = data[instr_]['tests']
    # out_series = calibration_class.simulate_strategy_params(data_train, data_tests,
    #                                                         params_dict_hat,
    #                                                         backtest_class,
    #                                                         strat_method)
    
    # out_series.plot()
