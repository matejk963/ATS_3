# -*- coding: utf-8 -*-
"""
Created on Tue Jan  2 17:27:15 2024

@author: Marek
"""

from time import sleep
from datetime import datetime, time
import pandas as pd
import numpy as np
from Math.accumfeatures import MSTD, EMA, DerivativeEMA
from Math.ti_class import TI_class, TR_class
from Database.TPData import TPData, TPDataDa
from Calibration.calibration_class import MMStrategyCalibration
from SynthSpread.spreadviewer_class import SpreadSingle, SpreadViewerData, norm_coeff
from Strategies.Market_making.model_class import simple_model, kalman_reg
from Strategies.Market_making.backtest_class import BacktestMM
from Strategies.Market_making.strategy_class import StrategyMM, VolumeClass
from Math.nlm_class import VasicekEKF, VasicekUKF
from Math.lm_class import kalman, LinearModel
from Utilities.excel_loaders import conn_out_xload
tol=0.019


def calc_model_tr_n(data_dict_, model, model_ema, model_dt):
    out_dict = {k: [] for k in data_dict_.keys()}
    for inst, data_inst in data_dict_.items():
        model.reset()
        model_ema.reset()
        model_dt.reset()
        df_data = data_inst['X']
        # Calculate ema model on data
        df_ema = model_ema.mm_model_raw(df_data, False)
        # ML estimate of parameters
        X_data = (df_data.iloc[:, 0] - df_ema.iloc[:, 0]).values.reshape(-1,)
        df_period = pd.Series(model.calc_period(X_data), index=df_data.index)
        # Calculate derivation model on data
        df_dt = model_dt.mm_model_raw(df_data, False)
        # Unify models
        df_model = df_ema.iloc[:, 0] + df_dt.iloc[:, 0] * df_period
        out_dict[inst] = pd.concat([df_model, df_ema.iloc[:, 1]], axis=1)
    return df_period


def calc_model_tr(data_dict_, model, model_ema, model_dt):
    alpha, beta = .2, 1
    out_dict = {k: [] for k in data_dict_.keys()}
    for inst, data_inst in data_dict_.items():
        model.reset()
        model_ema.reset()
        model_dt.reset()
        df_data = data_inst['X']
        # Calculate ema model on data
        df_ema = model_ema.mm_model_raw(df_data, False)
        # ML estimate of parameters
        X_data = (df_data.iloc[:, 0] - df_ema.iloc[:, 0])
        x_data = X_data.iloc[:-1].values.reshape(-1,1)
        y_data = X_data.iloc[1:].values.reshape(-1,)
        out_dict_lm = ftrl_regression(x_data, y_data, 0, 0, alpha, beta, True, False)
        # Estimated parameters
        theta_list = [1 - x[1] if 1 - x[1] > tol else tol for x in out_dict_lm['coeff']]
        period_list = [np.nan]
        period_list.extend([(np.log(2) / x) for x in theta_list])
        df_period = pd.Series(period_list, index=df_data.index)
        # Calculate derivation model on data
        df_dt = model_dt.mm_model_raw(df_data, False)
        # Unify models
        df_model = df_ema.iloc[:, 0] + df_dt.iloc[:, 0] * df_period
        out_dict[inst] = pd.concat([df_model, df_ema.iloc[:, 1]], axis=1)
    return out_dict


def calc_model_tr_m(data_dict_, tau):
    out_dict = {k: [] for k in data_dict_.keys()}
    for inst, data_inst in data_dict_.items():
        df_data = data_inst['X']
        m_list, me_list, std_list, stde_list, d_list = [], [], [], [], []
        stdm_list = []
        for i, (day, group) in enumerate(df_data.groupby(pd.Grouper(freq='B'))):
            if len(group.index) == 0:
                continue
            m, std = group.mean(), group.std()
            d_list.append(day)
            m_list.append(m[0])
            std_list.append(std[0])
            stdm_list.append(np.std(m_list))
            if i == 0:
                model_ema_m = simple_model(EMA(tau), [tau, m[0]],
                                          'ema', burn=0, time_model=True, tol=0)
                model_ema_s = simple_model(EMA(tau), [tau, std[0]],
                                          'ema', burn=0, time_model=True, tol=0)
            me_list.append(model_ema_m.push(m[0]))
            stde_list.append(model_ema_s.push(std[0]))
        out_dict[inst] = pd.DataFrame([me_list, stde_list, stdm_list], columns=d_list).T
        out_dict[inst].index += pd.offsets.BDay(1)
    return out_dict


def ftrl_regression(X, y, l1, l2, a, b, intercept, adaptive_l1=False):
    d = X.shape[1]
    clf = LinearModel(d, intercept, lambda1=l1, lambda2=l2, alpha=a, beta=b,
                      adaptive_l1=adaptive_l1, norm_g=False)
    yhat = []
    score = []
    param_list = []
    for x_, y_ in zip(X, y):
        if intercept:
            x_train = np.concatenate([[1], x_])
        else:
            x_train = x_
        yhat.append(clf.predict(x_train))
        score.append(clf.unc_score(x_train))
        clf.push(x_train, y_)
        param_list.append([x for x in clf.params])
    out_dict = {'coeff': param_list, 'y_pred': yhat, 'score': score}
    return out_dict


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


def prepare_data(data, dates, n_s, n_train, tau, tau_ema, dates_out=[]):
    # dts = dates.shift(-n_train, freq='B')
    dts = pd.date_range(dates.shift(-n_train, freq='B')[0], dates[-1], freq='B')
    dt1 = spread_class.product_dates(dts, n_s)
    dt2 = spread_class.product_dates(dts, n_train)
    dates_aux = [d for d, pd1, pd2 in zip(dts, dt1[0], dt2[0]) if pd1 != pd2 or d not in dates]
    tr_dict = {}
    for d in dates_aux:
        if d in dates_out:
            continue
        d_range = pd.date_range(d, d, freq='B')
        data_dict = spread_class.aggregate_data(data_class, d_range, n_train, gran=gran,
                                                start_time=start_time, end_time=end_time)

        col_list=['bid', 'ask', 'volume']
        trade_dict = spread_class.aggregate_data(data_class_tr, d_range, n_train, gran=gran_t,
                                                 start_time=start_time, end_time=end_time,
                                                 col_list=col_list, data_dict=data_dict)
        df_tr_ = spread_class.get_trades_otc(data_dict, trade_dict, coeff_list, mm_bool).dropna()
        print(d)
        print(df_tr_)
        instr_ = '_'.join([x[0].strftime('%y%m%d')
                           for x in spread_class.product_dates(d_range, n_train, True)])
        if instr_ in tr_dict.keys():
            tr_dict[instr_] = pd.concat([tr_dict[instr_], df_tr_], axis=0)
        else:
            tr_dict[instr_] = df_tr_
    # Prepare tick data
    out_dict = {k: {} for k in data.keys()}
    for inst, data_ in data.items():
        df_tr = pd.concat([tr_dict[inst], data_['tests']['trds']],
                           axis=0).dropna()
        data_p = df_tr['price']
        # Expected size of candle
        ti_cls = TR_class(tau, tau_ema)
        idx_series = ti_cls.tick_imbalance_indices(data_p)
    
        # Calculate distribution of returns
        X = grouped_series(data_p, idx_series)
        out_dict[inst]['X'] = X
    return out_dict


# if __name__ == '__main__':
if True:
    user_list = ['matej', 'marek', 'andrej', 'martin', 'matus']
    user_num = 3
    
    n_s = 2
    start_date = datetime(2025, 4, 15)
    start_date_t = datetime(2025, 5, 15)
    end_date = datetime(2025, 6, 20)
    dates = pd.date_range(start_date, end_date, freq='B')
    dates_out = conn_out_xload()
    market = ['de', 'de']
    tenor = ['q', 'q']
    tn1_list = [2, 3]
    tn2_list = []
    brk_list = ['eex']
    mm_bool = [True, True]
    instr = 'de_q4q1'
    
    start_time = time(10, 0, 0, 0)
    end_time = time(16, 25, 0, 0)
    gran = None
    gran_t = None
    gran_snap = 'optu'
    coeff_list = norm_coeff([1, -1], market)
    
    
    ob_data = True
    
    df_ba = pd.DataFrame([])
    df_tr = pd.DataFrame([])
    
    spread_class = SpreadSingle(market, tenor, tn1_list, tn2_list, brk_list)
    data_class = SpreadViewerData()
    # db_class = TPDataDa(user=user_list[user_num])
    db_class = TPData()
    tenors_list = spread_class.tenors_list
    if not ob_data:
        data_class.load_best_order_otc(market, tenors_list,
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
    col_list=['bid', 'ask', 'volume']
    for d in dates:
        if d in dates_out:
            continue
        d_range = pd.date_range(d, d)
        try:
            data_dict = spread_class.aggregate_data(data_class, d_range, n_s, gran=gran,
                                                    start_time=start_time, end_time=end_time)
            df_ba_ = spread_class.spread_maker(data_dict, coeff_list, trade_type=['cmb', 'cmb']).dropna()
            df_ba_ = spread_class.time_snapshot(df_ba_, db_class, gran_snap, start_time, end_time)
            
            trade_dict = spread_class.aggregate_data(data_class_tr, d_range, n_s, gran=gran_t,
                                                     start_time=start_time, end_time=end_time,
                                                     col_list=col_list, data_dict=data_dict)
            df_tr_ = spread_class.get_trades_otc(data_dict, trade_dict, coeff_list, mm_bool).dropna()
        except:
            user_num = (user_num + 1) % len(user_list)
            print('new user %s' % user_list[user_num])
            data_class.change_user_data(user_list[user_num])
            data_class_tr.change_user_data(user_list[user_num])
            sleep(100)
            data_dict = spread_class.aggregate_data(data_class, d_range, n_s, gran=gran,
                                                    start_time=start_time, end_time=end_time)
            df_ba_ = spread_class.spread_maker(data_dict, coeff_list, trade_type=['cmb', 'cmb']).dropna()
            df_ba_ = spread_class.time_snapshot(df_ba_, db_class, gran_snap, start_time, end_time)
            
            trade_dict = spread_class.aggregate_data(data_class_tr, d_range, n_s, gran=gran_t,
                                                     start_time=start_time, end_time=end_time,
                                                     col_list=col_list, data_dict=data_dict)
            df_tr_ = spread_class.get_trades_otc(data_dict, trade_dict, coeff_list, mm_bool).dropna()
        
        
        # instr_ = '_'.join([x[0].strftime('%y%m%d') if t not in ['da'] else t
        #                    for x, t in zip(spread_class.product_dates(d_range, n_s, True), tenor)])
        instr_ = instr
        if instr_ in data.keys():
            if d >= start_date_t:
                name = 'tests_o'
                if not data[instr_]['tests_o']:
                    data[instr_][name]['ords'] = df_ba_
                    data[instr_][name]['trds'] = df_tr_
                else:
                    data[instr_][name]['ords'] = pd.concat([data[instr_][name]['ords'],
                                                            df_ba_], axis=0)
                    data[instr_][name]['trds'] = pd.concat([data[instr_][name]['trds'],
                                                            df_tr_], axis=0)
            else:
                data[instr_]['tests']['ords'] = pd.concat([data[instr_]['tests']['ords'],
                                                           df_ba_], axis=0)
                data[instr_]['tests']['trds'] = pd.concat([data[instr_]['tests']['trds'],
                                                           df_tr_], axis=0)
        else:
            data[instr_] = {k: {} for k in ['train', 'tests', 'tests_o']}
            data[instr_]['tests']['ords'] = df_ba_
            data[instr_]['tests']['trds'] = df_tr_
    
    mm_model = 'mstd'
    if mm_model == 'ema_mstd':
        tau_t = 10
        tau_ema = 22
        n_train = 10 #2 * n_s
        data_ = prepare_data(data, dates, n_s, n_train, tau_t, tau_ema, dates_out)
        # Model trd
        tau_m = 30
        N = 30
        t_model_ema = simple_model(MSTD(tau_m, N), [tau_m / 2, N, 2, 0],
                                   'mstd', burn=0, time_model=True, tol=tol)
        t_model_dif = simple_model(DerivativeEMA(tau_m, 1), [tau_m, 1, .5, 0],
                                   'dt', burn=tau_m)
        # Model reg
        sigma = 0.25
        par_sigma = 0.01
        q = np.eye(3) * (par_sigma ** 2)
        q[0][0] = sigma ** 2
        r = par_sigma ** 2
        param_list = [sigma, par_sigma, 1, 0.041, 0, 1.5]
        t_model = kalman_reg(VasicekUKF(q, r), param_list, 'ukf')
        model_dict = calc_model_tr(data_, t_model, t_model_ema, t_model_dif)
    elif mm_model == 'ema_hist':
        tau_t = 10
        tau_ema = 22
        n_train = 10 #2 * n_s
        data_ = prepare_data(data, dates, n_s, n_train, tau_t, tau_ema)
        # Model trd
        tau = 5
        model_dict = calc_model_tr_m(data_, tau)
    
    # Paramaters for calibration
    fix_param = ['t_end', 'ba_spread', 'ba_max', 'br_fee']
    fix_param_val = [datetime(2028, 11, 28), .5, 1.5, 0.035]
    
    if mm_model in ['mstd', 'mstd_tr']:
        opt_param = ['tau',
                     'take_profit', 'stop_loss_rat',
                     'w1', 'w_std']
        opt_param_val = [np.arange(5, 40, .5),
                         np.arange(0.1, 0.9, 0.1), np.arange(0.5, 1.5, 0.5),
                         np.arange(0, 1, 0.2), np.arange(0.5, 5, 0.2)]
        fix_param.extend(['w', 'eql_p', 'margin'])
        fix_param_val.extend([0, 0, 0.2])
    elif mm_model == 'ema':
        opt_param = ['tau', 'margin',
                     'take_profit', 'stop_loss_rat']
        opt_param_val = [np.arange(5, 20, 1), np.arange(0.1, 0.6, 0.1),
                         np.arange(0.1, 0.6, 0.1), np.arange(0.5, 1.5, 0.5)]
        fix_param.extend(['w', 'eql_p'])
        fix_param_val.extend([0, 0])
    elif mm_model == 'ema_mstd':
        opt_param = ['tau',
                     'take_profit', 'stop_loss_rat',
                     'w', 'w_std']
        opt_param_val = [np.arange(5, 20, .5),
                         np.arange(0.1, 0.9, 0.1), np.arange(0.6, 1.4, 0.2),
                         np.arange(0, 1, 0.2), np.arange(0.5, 2, 0.2)]
        fix_param.extend(['df_model', 'w1', 'margin'])
        fix_param_val.extend([model_dict, 0.3, 0.2])
    elif mm_model == 'ema_hist':
        opt_param = ['tau',
                     'take_profit', 'stop_loss_rat',
                     'w', 'w_std']
        opt_param_val = [np.arange(5, 30, .5),
                         np.arange(0.1, 3.5, 0.1), np.arange(0.75, 1.25, 0.25),
                         np.arange(0, 1, 0.1), np.arange(0.5, 2, 0.2)]
        fix_param.extend(['df_model', 'w1'])
        fix_param_val.extend([model_dict, 0.75])
    else:
        ValueError('mm model unknown %s' % mm_model) 
    
    
    opt_param_dict = {k: v for k, v in zip(opt_param, opt_param_val)}
    fix_param_dict = {k: v for k, v in zip(fix_param, fix_param_val)}
    
    all_param_dict = {**opt_param_dict, **fix_param_dict}
    
    # Strategy & Backtest
    strategy_param_list = []
    s_param_dict = {k: v for k, v in all_param_dict.items()
                    if k in strategy_param_list}
    strat_method = 'simple_mtm'
    strategy_class = StrategyMM('MM', 'de', instr)
    strategy_class.load_params(s_param_dict, [])
    
    vol_class = VolumeClass(1, {'max_clips': 1})
    backtest_class = BacktestMM(vol_class)
    
    # Models
    N = 30
    tau = 5
    if mm_model == 'mstd':
        model_class = simple_model(MSTD(tau, N), [tau / 2, N, 2, 0.1 ** 2],
                                   'mstd', burn=0, time_model=True, tol=tol)
    elif mm_model == 'ema':
        model_class = simple_model(EMA(tau), [tau, 0],
                                   'ema', burn=0, time_model=False, tol=tol)
    elif mm_model == 'ema_mstd':
        model_class = simple_model(EMA(tau), [tau, 0],
                                   'ema_mstd', burn=0, time_model=False, tol=tol)
    elif mm_model == 'ema_hist':
        model_class = simple_model(EMA(tau), [tau, 0],
                                   'ema_hist', burn=0, time_model=False, tol=tol)
    else:
        ValueError('mm model unknown %s' % mm_model)
    
    # Calibration
    cal_method = 'sharp'
    calibration_class = MMStrategyCalibration(strategy_class, cal_method, opt_param,
                                              fix_param_dict)
    out_dict = calibration_class.calibrate_p(data, backtest_class, model_class,
                                             opt_param_dict, strat_method, multip=False, pct=.35)
    
    # Run best
    n = 10
    top_n_tuples = sorted(out_dict, key=out_dict.get, reverse=True)[:n]
    param_list_hat = [sum(x)/n for x in zip(*top_n_tuples)]
    params_dict_hat = {k: v for k, v in zip(opt_param, param_list_hat)}
    
    # params_dict_hat = {'tau': 9.0, 'stop_loss_rat': 1.0, 'take_profit': 0.25,
    #                     'margin': 0.25}
    
    data_train = data[instr_]['train']
    data_tests = data[instr_]['tests_o']
    out_series = calibration_class.simulate_strategy_params(data_train, data_tests,
                                                            params_dict_hat,
                                                            backtest_class,
                                                            model_class, strat_method)
    
    out_series.plot()
