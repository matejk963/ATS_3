# -*- coding: utf-8 -*-
"""
Created on Tue Jan  2 17:27:15 2024

@author: Marek
"""

from time import sleep
from datetime import datetime, time
import pandas as pd
import numpy as np
from Strategies.Spot_strategy.MMSpot.accumfeatures import MSTD, EMA, DerivativeEMA
from Math.ti_class import TI_class, TR_class
from Database.TPData import TPData, TPDataDa
from Strategies.Spot_strategy.MMSpot.calibration_class import MMStrategyCalibration
from SynthSpread.spreadviewer_class import SpreadSingle, SpreadViewerData, norm_coeff
from Strategies.Spot_strategy.MMSpot.model_class import simple_model, kalman_reg
from Strategies.Spot_strategy.MMSpot.backtest_class import BacktestMM
from Strategies.Spot_strategy.MMSpot.strategy_class import StrategyMM, VolumeClass
from Math.nlm_class import VasicekEKF, VasicekUKF
from Math.lm_class import kalman, LinearModel
tol=0.019


if __name__ == '__main__':
#if True:
    user_list = ['matej', 'marek', 'andrej', 'martin', 'matus']
    user_num = 3
    
    n_s = 0
    start_date = datetime(2024, 4, 3)
    start_date_t = datetime(2024, 7, 1)
    end_date = datetime(2024, 7, 30)
    dates = pd.date_range(start_date, end_date, freq='B')
    market = ['de', 'de']
    tenor = ['w', 'w']
    tn1_list = [1, 2]
    tn2_list = []
    brk_list = ['eex']
    mm_bool = [True, True]
    instr = 'w1x2'
    
    start_time = time(9, 0, 0, 0)
    end_time = time(17, 25, 0, 0)
    gran = None
    gran_t = '1s'
    coeff_list = norm_coeff([1, -1], market)
    
    import pickle
    file_path = r'Z:\Data\Spot\MM\test\de_w1_w2_240401_240801_test_data.pickle'

    with open(file_path,'rb') as f:
        data = pickle.load(f)
    
    # ob_data = True
    
    # df_ba = pd.DataFrame([])
    # df_tr = pd.DataFrame([])
    
    # spread_class = SpreadSingle(market, tenor, tn1_list, tn2_list, brk_list)
    # data_class = SpreadViewerData()
    # db_class = TPDataDa(user=user_list[user_num])
    # tenors_list = spread_class.tenors_list
    # if not ob_data:
    #     data_class.load_best_order_otc(market, tenors_list,
    #                                     spread_class.product_dates(dates, n_s),
    #                                     db_class,
    #                                     start_time=start_time, end_time=end_time)
    # else:
    #     # data_class.load_best_ob(market, tenors_list, dates, spread_class.product_dates(dates, n_s),
    #     #                         v_thres=5, freq=gran)
    #     data_class.load_best_ob_tp(market, tenors_list,
    #                                 spread_class.product_dates(dates, n_s),
    #                                 db_class,
    #                                 start_time=start_time, end_time=end_time)
    
    # data_class_tr = SpreadViewerData()
    # data_class_tr.load_trades_otc(market, tenors_list, db_class,
    #                               start_time=start_time, end_time=end_time)
    
    # data = {}
    # col_list=['bid', 'ask', 'volume']
    # for d in dates:
    #     try:
    #         d_range = pd.date_range(d, d)
    #         try:
    #             data_dict = spread_class.aggregate_data(data_class, d_range, n_s, gran=gran,
    #                                                     start_time=start_time, end_time=end_time)
    #             df_ba_ = spread_class.spread_maker(data_dict, coeff_list, trade_type=['cmb', 'cmb']).dropna()
                
    #             trade_dict = spread_class.aggregate_data(data_class_tr, d_range, n_s, gran=gran_t,
    #                                                       start_time=start_time, end_time=end_time,
    #                                                       col_list=col_list, data_dict=data_dict)
    #             df_tr_ = spread_class.get_trades_otc(data_dict, trade_dict, coeff_list, mm_bool).dropna()
    #         except:
    #             user_num = (user_num + 1) % len(user_list)
    #             print('new user %s' % user_list[user_num])
    #             data_class.change_user_data(user_list[user_num])
    #             data_class_tr.change_user_data(user_list[user_num])
    #             sleep(100)
    #             data_dict = spread_class.aggregate_data(data_class, d_range, n_s, gran=gran,
    #                                                     start_time=start_time, end_time=end_time)
    #             df_ba_ = spread_class.spread_maker(data_dict, coeff_list, trade_type=['cmb', 'cmb']).dropna()
                
    #             trade_dict = spread_class.aggregate_data(data_class_tr, d_range, n_s, gran=gran_t,
    #                                                       start_time=start_time, end_time=end_time,
    #                                                       col_list=col_list, data_dict=data_dict)
    #             df_tr_ = spread_class.get_trades_otc(data_dict, trade_dict, coeff_list, mm_bool).dropna()
            
            
    #         instr_ = '_'.join([x[0].strftime('%y%m%d') if t not in ['da'] else t
    #                             for x, t in zip(spread_class.product_dates(d_range, n_s, True), tenor)])
    #         if instr_ in data.keys():
    #             if d >= start_date_t:
    #                 name = 'tests_o'
    #                 if not data[instr_]['tests_o']:
    #                     data[instr_][name]['ords'] = df_ba_
    #                     data[instr_][name]['trds'] = df_tr_
    #                 else:
    #                     data[instr_][name]['ords'] = pd.concat([data[instr_][name]['ords'],
    #                                                             df_ba_], axis=0)
    #                     data[instr_][name]['trds'] = pd.concat([data[instr_][name]['trds'],
    #                                                             df_tr_], axis=0)
    #             else:
    #                 data[instr_]['tests']['ords'] = pd.concat([data[instr_]['tests']['ords'],
    #                                                             df_ba_], axis=0)
    #                 data[instr_]['tests']['trds'] = pd.concat([data[instr_]['tests']['trds'],
    #                                                             df_tr_], axis=0)
    #         else:
    #             data[instr_] = {k: {} for k in ['train', 'tests', 'tests_o']}
    #             data[instr_]['tests']['ords'] = df_ba_
    #             data[instr_]['tests']['trds'] = df_tr_
    #     except Exception as e:
    #         if str(e) == 'No Trades for criteria':
    #             print("Caught specific error: No Trades for criteria")
    #             continue
    #             # You can handle the error here, e.g., return a default value, log it, etc.
    #         else:
    #             # Re-raise the exception if it's not the one you're looking for
    #             raise
        
    mm_model = '3band_std'
    
    # Paramaters for calibration
    fix_param = ['t_end', 'ba_spread', 'ba_max', 'br_fee']
    fix_param_val = [time(16,0,0), .5, 1, 0.035]
    
    if mm_model in ['mstd', 'mstd_tr']:
        opt_param = ['tau',
                     'take_profit', 'stop_loss_rat',
                     'w1', 'w_std']
        opt_param_val = [np.arange(5, 7, .5),
                         np.arange(0.1, 0.3, 0.1), np.arange(0.5, 1.5, 0.5),
                         np.arange(0, 0.4, 0.2), np.arange(0.5, 0.9, 0.2)]
        fix_param.extend(['w', 'eql_p', 'margin'])
        fix_param_val.extend([0, 0, 0.2])
        
    elif mm_model in ['3band_std']:
        opt_param = ['tau', 'w_std','take_profit', 'stop_loss_rat']
        opt_param_val = [np.arange(5, 50, 1), np.arange(0.5, 2.1, 0.1),
                         np.arange(1,2,1),np.arange(1,2,1)]

    
    else:
        ValueError('mm model unknown %s' % mm_model) 
    
    
    opt_param_dict = {k: v for k, v in zip(opt_param, opt_param_val)}
    fix_param_dict = {k: v for k, v in zip(fix_param, fix_param_val)}
    
    all_param_dict = {**opt_param_dict, **fix_param_dict}
    
    # Strategy & Backtest
    strategy_param_list = []
    s_param_dict = {k: v for k, v in all_param_dict.items()
                    if k in strategy_param_list}
    strat_method = 'position_mtm'
    strategy_class = StrategyMM('MM', 'de', instr, is_overnight=False)
    strategy_class.load_params(s_param_dict, [])
    
    vol_class = VolumeClass(1, {'max_clips': 3})
    backtest_class = BacktestMM(vol_class)
    
    # Models
    N = 30
    tau = 5
    w_std = 1
    if mm_model == 'mstd':
        model_class = simple_model(MSTD(tau, N), [tau / 2, N, 2, 0],
                                   'mstd', burn=0, time_model=False, tol=tol)
    if mm_model == '3band_std':
        model_class = simple_model(MSTD(tau, N), [tau / 2, N, 2, 0, w_std],
                                   '3band_std', burn=0, time_model=False, tol=tol)
    else:
        ValueError('mm model unknown %s' % mm_model)
    
    # Calibration
    cal_method = 'sharp'
    calibration_class = MMStrategyCalibration(strategy_class, cal_method, opt_param,
                                              fix_param_dict)
    out_dict = calibration_class.calibrate_p(data, backtest_class, model_class,
                                             opt_param_dict, strat_method, multip=True, pct=.35)
    
    # Run best
    n = 5
    top_n_tuples = sorted(out_dict, key=out_dict.get, reverse=True)[:n]
    param_list_hat = [sum(x)/n for x in zip(*top_n_tuples)]
    params_dict_hat = {k: v for k, v in zip(opt_param, param_list_hat)}
    
    for i in range(-5,0):
        instr_ = list(data)[i]
        
        # params_dict_hat = {'tau': 50, 'stop_loss_rat': 1.0, 'take_profit': 0.25,
        #                     'w_std': 1}
        
        data_train = data[instr_]['train']
        data_tests = data[instr_]['tests_o']
        out_series = calibration_class.simulate_strategy_params(data_train, data_tests,
                                                                params_dict_hat,
                                                                backtest_class,
                                                                model_class, strat_method)
        
        out_series.plot()
