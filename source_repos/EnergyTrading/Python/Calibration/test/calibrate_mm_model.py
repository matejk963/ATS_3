#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Jan 10 13:02:56 2024

@author: marek
"""

from time import sleep
from datetime import datetime, time
import pandas as pd
import numpy as np
from sklearn.model_selection import TimeSeriesSplit
from Math.accumfeatures import MSTD, EMA, MA
from Math.ti_class import TI_class, TR_class
from Database.TPData import TPData, TPDataDa
from Calibration.calibration_class import MMModelCalibration
from SynthSpread.spreadviewer_class import SpreadSingle, SpreadViewerData, norm_coeff
from Strategies.Market_making.model_class import simple_model, kalman_reg
from Math.nlm_class import VasicekEKF, VasicekUKF
tol=0.024


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


def prepare_data(data_dict, tau, tau_ema, burn=10):
    out_dict = {k: {} for k in data_dict.keys()}
    # CV
    tscv = TimeSeriesSplit(n_splits=5, max_train_size=2*burn)
    for inst, data in data_dict.items():
        df_tr = data['tests']['trds'].dropna()
        data_p = df_tr['price']

        # Expected size of candle
        ti_cls = TR_class(tau, tau_ema)
        idx_series = ti_cls.tick_imbalance_indices(data_p)
    
        # Calculate distribution of returns
        X = grouped_series(data_p, idx_series)
        out_dict[inst]['X'] = X
        # Determine splits
        out_dict[inst]['split_list'] = [(train, test)
                                        for train, test in tscv.split(X)]
    return out_dict


user_list = ['matej', 'marek', 'andrej', 'martin', 'matus']
user_num = 3

n_s = 5
start_date = datetime(2023, 8, 1)
end_date = datetime(2023, 12, 22)
dates = pd.date_range(start_date, end_date, freq='B')
market = ['de', 'fr']
tenor = ['m', 'm']
tn1_list = [1, 1]
tn2_list = []
brk_list = ['eex']
mm_bool = [True, True]
instr = 'm1x2'

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
db_class = TPDataDa(user=user_list[user_num])
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
    d_range = pd.date_range(d, d)
    try:
        data_dict = spread_class.aggregate_data(data_class, d_range, n_s, gran=gran,
                                                start_time=start_time, end_time=end_time)
        df_ba_ = spread_class.spread_maker(data_dict, coeff_list, trade_type=['cmb', 'cmb']).dropna()
        
        trade_dict = spread_class.aggregate_data(data_class_tr, d_range, n_s, gran=gran_t,
                                                 start_time=start_time, end_time=end_time,
                                                 col_list=col_list, data_dict=data_dict)
        df_tr_ = spread_class.get_trades_otc(data_dict, trade_dict, coeff_list, mm_bool).dropna()
    except:
        user_num = (user_num + 1) % len(user_list)
        print('new user %s' % user_list[user_num])
        data_class.change_data_user(user_list[user_num])
        data_class_tr.change_data_user(user_list[user_num])
        sleep(100)
        data_dict = spread_class.aggregate_data(data_class, d_range, n_s, gran=gran,
                                                start_time=start_time, end_time=end_time)
        df_ba_ = spread_class.spread_maker(data_dict, coeff_list, trade_type=['cmb', 'cmb']).dropna()
        
        trade_dict = spread_class.aggregate_data(data_class_tr, d_range, n_s, gran=gran_t,
                                                 start_time=start_time, end_time=end_time,
                                                 col_list=col_list, data_dict=data_dict)
        df_tr_ = spread_class.get_trades_otc(data_dict, trade_dict, coeff_list, mm_bool).dropna()
    
    
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

### Tick model ###
# Model
tau_t = 10
tau_ema = 22
data_dict = prepare_data(data, tau_t, tau_ema)

### EMA for calibration ###
tau = 10
N = 30
ema_class = simple_model(MA(tau, N), [tau, N, 0],
                         'ma', burn=0, time_model=True, tol=tol)

### Model for calibration
mm_model = 'ukf'
# Paramaters for calibration
sigma = 0.05
par_sigma = 0.02
q = np.eye(3) * (par_sigma ** 2)
q[0][0] = sigma ** 2
r = par_sigma ** 2
param_list = [sigma, par_sigma, 1, 1e-3, 0, 2]

model_class = kalman_reg(VasicekUKF(q, r), param_list, 'ukf')


fix_param = ['N', 'dt', 'kappa']
fix_param_val = [N, 1, 0]

if mm_model == 'ukf':
    opt_param = ['tau',
                  'sigma', 'par_sigma',
                  'alpha', 'beta']
    opt_param_val = [np.arange(5, 20, .5),
                      np.arange(0.05, 0.3, 0.1), np.arange(0.01, 0.1, 0.05),
                      np.arange(1e-3, 0.1, 0.02), np.arange(1, 4, 1)]
    # opt_param = ['tau',
    #              'sigma', 'par_sigma']
    # opt_param_val = [np.arange(5, 20, .5),
    #                  np.arange(0.05, 0.3, 0.1), np.arange(0.01, 0.1, 0.05)]
    # fix_param.extend(['alpha', 'beta'])
    fix_param_val.extend([1e-3, 2])
elif mm_model == 'ekf':
    opt_param = ['tau', 'sigma', 'par_sigma']
    opt_param_val = [np.arange(5, 20, .5),
                     np.arange(0.05, 0.3, 0.05), np.arange(0.01, 0.1, 0.01)]
else:
    ValueError('mm model unknown %s' % mm_model) 


opt_param_dict = {k: v for k, v in zip(opt_param, opt_param_val)}
fix_param_dict = {k: v for k, v in zip(fix_param, fix_param_val)}

all_param_dict = {**opt_param_dict, **fix_param_dict}

# Calibration
cal_method = 'mean'
calibration_class = MMModelCalibration(model_class, cal_method, opt_param,
                                       fix_param_dict)
out_dict = calibration_class.calibrate_p(data_dict, ema_class, opt_param_dict)

# Run best
n = 10
top_n_tuples = sorted(out_dict, key=out_dict.get, reverse=True)[:n]
param_list_hat = [sum(x)/n for x in zip(*top_n_tuples)]
