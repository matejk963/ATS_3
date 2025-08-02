# -*- coding: utf-8 -*-
"""
Created on Tue Jan  2 17:27:15 2024

@author: Marek
"""

from datetime import datetime, time
import pandas as pd
import numpy as np
from Math.accumfeatures import MSTD, EMA, DerivativeEMA
from Math.ti_class import TI_class, TR_class
from Database.TPData import TPData, TPDataDa
from Strategies.Iceberg_strategy.calibration import IBStrategyCalibration
from SynthSpread.spreadviewer_class import SpreadSingle, SpreadViewerData, norm_coeff
from Strategies.Iceberg_strategy.model_class import IcebergModel
from Strategies.Iceberg_strategy.backtest_class import BacktestIB
from Strategies.Iceberg_strategy.strategy_class import StrategyIB, VolumeClass
from Math.nlm_class import VasicekEKF, VasicekUKF
from Math.lm_class import kalman, LinearModel
tol=0.019


def grouped_series(data_series, idx_series):
    df_data = pd.DataFrame([])
    agg_dict = agg_dict = {'index': 'first', data_series.name: 'mean'}
    data_aux = pd.concat([data_series.reindex(idx_series.index), idx_series],
                         axis=1).reset_index()
    data_aux = data_aux.groupby(0).agg(agg_dict).set_index('index')
    grouped = data_aux.groupby(data_aux.index.date)
    data_dict = {date: group for date, group in grouped}
    for data in data_dict.values():
        df_data = pd.concat([df_data, data])
    return df_data.dropna()


def prepare_data(data, dates, n_s, n_train, tau, tau_ema):
    dts = dates.shift(-n_train, freq='B')
    dt1 = spread_class.product_dates(dts, n_s)
    dt2 = spread_class.product_dates(dts, n_train)
    dates_aux = [d for d, pd1, pd2 in zip(dts, dt1[0], dt2[0]) if pd1 != pd2]
    tr_dict = {}
    for d in dates_aux:
        d_range = pd.date_range(d, d)
        data_dict = spread_class.aggregate_data(data_class, d_range, n_s, gran=gran,
                                                start_time=start_time, end_time=end_time)

        col_list=['bid', 'ask', 'volume']
        trade_dict = spread_class.aggregate_data(data_class_tr, d_range, n_s, gran=gran_t,
                                                 start_time=start_time, end_time=end_time,
                                                 col_list=col_list, data_dict=data_dict)
        df_tr_ = spread_class.get_trades_otc(data_dict, trade_dict, coeff_list, mm_bool).dropna()
        
        instr_ = '_'.join([x[0].strftime('%y%m%d')
                           for x in spread_class.product_dates(d_range, n_s, True)])
        if instr_ in tr_dict.keys():
            tr_dict[instr_] = pd.concat([tr_dict[instr_], df_tr_], axis=0)
        else:
            tr_dict[instr_] = df_tr_
    # Prepare tick data
    out_dict = {k: {} for k in data.keys()}
    for inst, data_ in data.items():
        df_tr = pd.concat([tr_dict[instr_], data_['tests']['trds']],
                           axis=0).dropna()
        data_p = df_tr['price']
        # Expected size of candle
        ti_cls = TR_class(tau, tau_ema)
        idx_series = ti_cls.tick_imbalance_indices(data_p)
    
        # Calculate distribution of returns
        X = grouped_series(data_p, idx_series)
        out_dict[inst]['X'] = X
    return out_dict

if __name__ == '__main__':
    n_s = 2
    start_date = datetime(2023, 11, 1)
    end_date = datetime(2023, 11, 3)
    dates = pd.date_range(start_date, end_date, freq='B')
    market = ['de']
    tenor = ['m']
    tn1_list = [1]
    tn2_list = []
    brk_list = ['eex']
    mm_bool = [True, True]
    instr = 'm1'

    start_time = time(9, 0, 0, 0)
    end_time = time(17, 25, 0, 0)
    gran = None
    gran_t = '1S'
    coeff_list = norm_coeff([1, -1], market)


    ob_data = True

    df_ba = pd.DataFrame([])
    df_tr = pd.DataFrame([])

    spread_class = SpreadSingle(market, tenor, tn1_list, tn2_list, brk_list)
    data_class = SpreadViewerData()
    db_class = TPDataDa()
    tenors_list = spread_class.tenors_list
    if not ob_data:
        data_class.get_best_ob_data(market, tenors_list, brk_list,
                                    spread_class.product_dates(dates, n_s),
                                    db_class,
                                    start_time=start_time, end_time=end_time)
    else:
        # data_class.load_best_ob(market, tenors_list, dates, spread_class.product_dates(dates, n_s),
        #                         v_thres=5, freq=gran)
        data_class.load_best_ob_tp(market, tenors_list,
                                spread_class.product_dates(dates, n_s),
                                db_class,
                                start_time=start_time, end_time=end_time)

    data_class_tr = SpreadViewerData()
    data_class_tr.load_trades_otc(market, tenors_list, db_class,
                                start_time=start_time, end_time=end_time)

    data = {}
    for d in dates:
        d_range = pd.date_range(d, d)
        data_dict = spread_class.aggregate_data(data_class, d_range, n_s, gran=gran,
                                                start_time=start_time, end_time=end_time)
        df_ba_ = spread_class.spread_maker(data_dict, coeff_list, trade_type=['cmb', 'cmb']).dropna()
        col_list=['bid', 'ask', 'volume']
        trade_dict = spread_class.aggregate_data(data_class_tr, d_range, n_s, gran=gran_t,
                                                start_time=start_time, end_time=end_time,
                                                col_list=col_list, data_dict=data_dict)
        df_tr_ = spread_class.get_trades_otc(data_dict, trade_dict, coeff_list, mm_bool).dropna()
        
        # df_ba = pd.concat([df_ba, df_ba_], axis=0)
        # df_tr = pd.concat([df_tr, df_tr_], axis=0)
        
        instr_ = '_'.join([x[0].strftime('%y%m%d')
                        for x in spread_class.product_dates(d_range, n_s, True)])
        if instr_ in data.keys():
            data[instr_]['tests']['ords'] = pd.concat([data[instr_]['tests']['ords'],
                                                    df_ba_], axis=0)
            data[instr_]['tests']['trds'] = pd.concat([data[instr_]['tests']['trds'],
                                                    df_tr_], axis=0)
        else:
            data[instr_] = {k: {} for k in ['train', 'tests']}
            data[instr_]['tests']['ords'] = df_ba_
            data[instr_]['tests']['trds'] = df_tr_

    opt_param = ['iceberg_target', 'iceberg_prob',
                    'take_profit', 'stop_loss',
                    'trailing_tp_tau']
    opt_param_val = [
        np.arange(5, 15, 1), np.arange(.4, .8, .05),
        np.array([0.2, 0.3]),
        np.array([-.2, -.3, -.4, -.5]), np.arange(5, 15, 1)]

    # Paramaters for calibration
    fix_param = ['t_end', 'ba_spread', 'ba_max', 'br_fee']
    fix_param_val = [time(17,45), .5, 1.5, 0.035/2]


    opt_param_dict = {k: v for k, v in zip(opt_param, opt_param_val)}
    fix_param_dict = {k: v for k, v in zip(fix_param, fix_param_val)}

    all_param_dict = {**opt_param_dict, **fix_param_dict}

    # Strategy & Backtest
    strategy_param_list = []
    s_param_dict = {k: v for k, v in all_param_dict.items()
                    if k in strategy_param_list}
    strat_method = 'simple_mtm'
    strategy_class = StrategyIB(IcebergModel, 'MM', 'de', instr, is_overnight=False, trailing_takeprofit=True)
    strategy_class.load_params(s_param_dict, [])

    vol_class = VolumeClass(1, {'max_clips': 1})
    backtest_class = BacktestIB(vol_class)

    # Calibration
    cal_method = 'cumpnl'
    calibration_class = IBStrategyCalibration(strategy_class, cal_method, opt_param_dict,
                                            fix_param_dict)
    out_dict = calibration_class.calibrate_p(data, backtest_class, IcebergModel, opt_param_dict,
                                            cal_method)

    # Run best
    n = 10
    top_n_tuples = sorted(out_dict, key=out_dict.get, reverse=True)[:n]
    param_list_hat = [sum(x)/n for x in zip(*top_n_tuples)]
    params_dict_hat = {k: v for k, v in zip(opt_param, param_list_hat)}

    # params_dict_hat = {'tau': 9.0, 'stop_loss_rat': 1.0, 'take_profit': 0.25,
    #                     'margin': 0.25}

    data_train = data[instr_]['train']
    data_tests = data[instr_]['tests']
    out_series = calibration_class.simulate_strategy_params(data_tests,
                                                            params_dict_hat,
                                                            backtest_class)

    out_series.plot()
