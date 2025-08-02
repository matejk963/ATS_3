#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Dec 10 17:26:13 2023

@author: marek
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, time
from SynthSpread.spreadviewer_class import SpreadSingle, SpreadViewerData, norm_coeff
from Database.TPData import TPData, TPDataDa
from Math.ti_class import TI_class, VI_class, TR_class
from Math.lm_class import kalman, LinearModel
from Math.accumfeatures import EMA, MA, MSTD, DifferentialEMA, DerivativeEMA
from Strategies.Market_making.model_class import simple_model
from Strategies.Market_making.backtest_class import BacktestMM
from Strategies.Market_making.strategy_class import StrategyMM, VolumeClass
tol=(1e-1)/2


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


def tick_data(df_tr, tau, tau_ema):
    df_tr = df_tr.dropna()
    data_p = df_tr['price']

    # Expected size of candle
    ti_cls = TR_class(tau, tau_ema)
    idx_series = ti_cls.tick_imbalance_indices(data_p)

    # Calculate distribution of returns
    return grouped_series(data_p, idx_series)


def model_tr(data, tau, N, alpha=0.2, beta=1):
    X = data.iloc[:,0].values
    value0 = X[0]
    model_std = simple_model(MSTD(tau, N), [tau / 2, N, 2, value0],
                             'mstd', burn=tau)
    std = model_std.predict(X)
    df_out = pd.DataFrame(std, index=data.index)
    # Differential model
    model_dt = simple_model(DerivativeEMA(tau, N), [tau, 1, .5, value0],
                            'dt', burn=tau)
    dt = model_dt.predict(X)
    df_out = pd.concat([df_out, pd.Series(dt, index=data.index)], axis=1)
    # Mean reversion model
    y_df = pd.Series([x[0] for x in std], index=data.index)
    data_ = (y_df - data.iloc[:, 0]).dropna()
    X_data = data_.iloc[:-1].values.reshape(-1,1)
    y_data = data_.iloc[1:].values.reshape(-1,)

    out_dict_lm = ftrl_regression(X_data, y_data, 0, 0, alpha, beta, True, False)
    # Estimated parameters
    theta_list = [1 - x[1] if 1 - x[1] > tol else tol for x in out_dict_lm['coeff']]
    period_list = [(np.log(2) / x) for x in theta_list]
    df_out = pd.concat([df_out, pd.Series(period_list, index=data_.index[1:])], axis=1)
    df_model = df_out.iloc[:,0] + df_out.iloc[:,-2] * df_out.iloc[:,-1]
    return pd.concat([df_model, df_out.iloc[:,1]], axis=1)


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


def adjust_trds(df_tr, df_em):
    df_em = df_em[~df_em.index.duplicated(keep='first')]
    timestamp = df_tr.index
    ts_new = df_em.index.union(timestamp).drop_duplicates()
    df_em = df_em.reindex(ts_new).ffill().loc[timestamp, :]
    lb = df_em.iloc[:, 0]
    ub = df_em.iloc[:, 2]
    df_tr.loc[lb.isna()] = np.nan
    df_tr.loc[(df_tr['price'] > ub) & (df_tr['action'] == 1), :] = np.nan
    df_tr.loc[(df_tr['price'] < lb) & (df_tr['action'] == -1), :] = np.nan
    return df_tr.dropna(how='all')


def calc_ema_m_old(df_data, tau, margin, w, eql_p, tol=0):
    bands = []
    for day, group in df_data.groupby(pd.Grouper(freq='B')):
        mid_ser = .5 * (group.loc[:, 'bid'] + group.loc[:, 'ask'])
        mid_list = mid_ser.values
        dif_list = [0.001]
        dif_list.extend([abs(x - xl) for x, xl in zip(mid_list[1:], mid_list[:-1])])
        model = EMA(tau, mid_list[0])
        ema_list = [model.push(x, dx) if abs(dx) > tol else np.nan
                    for x, dx in zip(mid_list, dif_list)]
        ema_list = [w * eql_p + (1 - w) * x for x in ema_list]
        bands.extend([[x - margin, x, x + margin] for x in ema_list])
    return pd.DataFrame(bands, index=df_data.index).ffill()


def calc_ema_m(df_data, tau, margin, w, eql_p, tol=0):
    bands = []
    for day, group in df_data.groupby(pd.Grouper(freq='B')):
        mid_ser = .5 * (group.loc[:, 'bid'] + group.loc[:, 'ask'])
        mid_list = mid_ser.values
        # Create model
        model_class = simple_model(EMA(tau), [tau, mid_list[0]],
                                   'ema', burn=0, time_model=False, tol=tol)
        # Calc model
        ema_list = model_class.predict(mid_list)
        ema_list = [w * eql_p + (1 - w) * x for x in ema_list]
        bands.extend([[x - margin, x, x + margin] for x in ema_list])
    return pd.DataFrame(bands, index=df_data.index).ffill()


def calc_ema_m_std(df_data, tau, margin, w, w1, w_std, eql_p,N=30, tol=0):
    bands = []
    for day, group in df_data.groupby(pd.Grouper(freq='B')):
        mid_ser = .5 * (group.loc[:, 'bid'] + group.loc[:, 'ask'])
        mid_list = mid_ser.values
        model = simple_model(MSTD(tau, N), [tau / 2, N, 2, mid_list[0], .1 ** 2],
                             'mstd', burn=0, time_model=False, tol=tol)
        std_list = model.predict(mid_list)
        # dif_list = [0.001]
        # dif_list.extend([abs(x - xl) for x, xl in zip(mid_list[1:], mid_list[:-1])])
        # model = simple_model(MSTD(tau, N), [tau / 2, N, 2, mid_list[0]],
        #                      'mstd', burn=0, time_model=False, tol=tol)
        # std_list = [model.push_mstd(x, dx) if abs(dx) > tol else [np.nan] * 2
        #             for x, dx in zip(mid_list, dif_list)]
        ema_list = [w * eql_p + (1 - w) * x[0] for x in std_list]
        mrg_list = [w1 * margin + (1 - w1) * m[1] * w_std for m in std_list]
        bands.extend([[x - m, x, x + m] for x, m in zip(ema_list, mrg_list)])
    return pd.DataFrame(bands, index=df_data.index).ffill()


def calc_ema_mstd(df_data, tau, margin, w, w1, df_model, tol=0):
    ts = df_data.index
    df_model = df_model.reindex(ts).ffill()
    bands = []
    for day, group in df_data.groupby(pd.Grouper(freq='B')):
        df_model_aux = df_model.loc[group.index, :]
        mid_ser = .5 * (group.loc[:, 'bid'] + group.loc[:, 'ask'])
        mid_list = mid_ser.values
        dif_list = [0.001]
        dif_list.extend([abs(x - xl) for x, xl in zip(mid_list[1:], mid_list[:-1])])
        model = EMA(tau, mid_list[0])
        ema_list = [model.push(x, dx) if abs(dx) > tol else np.nan
                    for x, dx in zip(mid_list, dif_list)]
        eql_list = df_model_aux.iloc[:, 0].values
        mrg_list = [w1 * margin + (1 - w1) * m for m in df_model_aux.iloc[:, 1].values]
        ema_list = [w * eq + (1 - w) * x for x, eq in zip(ema_list, eql_list)]
        bands.extend([[x - m, x, x + m] for x, m in zip(ema_list, mrg_list)])
    return pd.DataFrame(bands, index=df_data.index).ffill()


n_s = 4
start_date = datetime(2025, 6, 27)
end_date = datetime(2025, 6, 27)
dates = pd.date_range(start_date, end_date, freq='B')
market = ['the', 'ttf']
tenor = ['da', 'm']
tn1_list = [1, 1]
tn2_list = []
brk_list = ['eex']
mm_bool = [True, True]

start_time = time(10, 40, 0, 0)
end_time = time(17, 0, 0, 0)
gran = None
gran_t = None
gran_snap = 'optu'
# gran_snap = ''
coeff_list = norm_coeff([1, -1], market)


ob_data = False
tp_data = False

df_ba = pd.DataFrame([])
df_tr = pd.DataFrame([])

spread_class = SpreadSingle(market, tenor, tn1_list, tn2_list, brk_list)
data_class = SpreadViewerData()
db_class = TPData()
tenors_list = spread_class.tenors_list
if not ob_data:
    data_class.load_best_order_otc(market, tenors_list,
                                   spread_class.product_dates(dates, n_s),
                                   db_class,
                                   start_time=start_time, end_time=end_time)
else:
    data_class.load_best_ob_tp(market, tenors_list,
                               spread_class.product_dates(dates, n_s),
                               db_class,
                               start_time=start_time, end_time=end_time)

data_class_tr = SpreadViewerData()
data_class_tr.load_trades_otc(market, tenors_list, db_class,
                              start_time=start_time, end_time=end_time)

for d in dates:
    d_range = pd.date_range(d, d)
    data_dict = spread_class.aggregate_data(data_class, d_range, n_s, gran=gran,
                                            start_time=start_time, end_time=end_time)
    df_ba_ = spread_class.spread_maker(data_dict, coeff_list, trade_type=['cmb', 'cmb']).dropna()
    df_ba_ = spread_class.time_snapshot(df_ba_, db_class, gran_snap, start_time, end_time)
    col_list=['bid', 'ask', 'volume']
    trade_dict = spread_class.aggregate_data(data_class_tr, d_range, n_s, gran=gran_t,
                                             start_time=start_time, end_time=end_time,
                                             col_list=col_list, data_dict=data_dict)
    df_tr_ = spread_class.get_trades_otc(data_dict, trade_dict, coeff_list, mm_bool).dropna()
    
    df_ba = pd.concat([df_ba, df_ba_], axis=0)
    df_tr = pd.concat([df_tr, df_tr_], axis=0)


df_ba = df_ba.dropna()

# Model
tau_t = 10
tau_ema = 22
data = tick_data(df_tr, tau_t, tau_ema)
N = 30
tau_m = 30
model_data = model_tr(data, tau_m, N)

method = 'simple_mtm'
# EMA
# tau = 8
# margin = .20
# eql_p = -6.25
# w = 0.0 #0.4
# w1 = .5
# MSTD
# if tp_data:
#     tau = 6.4
# else:
#     tau = 6.45
# margin = .20
# eql_p = 0.0
# w = 0.0
# w1 = 0.72
# w_std = 3.34

if tp_data:
    tau = 6.4
else:
    tau = 13.9
    tau = 16.8
margin = .10
eql_p = 0.0
w = 0.0
w1 = 0.24
w_std = 1.84

w1 = 0.6
w_std = 1.


# Adjust trades
#df_em = calc_ema_mstd(df_ba, tau, margin, w, w1, model_data).dropna()
# df_em = calc_ema_m(df_ba, tau, margin, w, eql_p, tol=.024)
df_em = calc_ema_m_std(df_ba, tau, margin, w, w1, w_std, eql_p, tol=0.024)
df_ba_a = df_ba.loc[df_em.index, :]
df_tr_a = adjust_trds(df_tr.copy(), df_em)

instr = 'm1xq1'
data_dict = {}
data_dict[instr] = BacktestMM.merge_data(df_ba_a, df_tr_a, False)

# data_dict['output'] = calc_ema_m(data_dict[instr], tau, margin, w, eql_p)
ts = data_dict[instr].index
df_em = df_em[~df_em.index.duplicated(keep='first')]
df_em = df_em.reindex(ts.drop_duplicates()).ffill()
data_dict['output'] = df_em.loc[ts, :]

param_list = ['t_end', 'take_profit', 'stop_loss', 'ba_spread', 'ba_max']
contr_vars = ['threshold']
param_dict = {k: [] for k in param_list}
param_dict['t_end'] = datetime(2026, 3, 28)
param_dict['take_profit'] = 0.2
param_dict['stop_loss_rat'] = .95
param_dict['ba_spread'] = 0.50
param_dict['ba_max'] = 1.5
param_dict['br_fee'] = 0.06

vol_class = VolumeClass(1, {'max_clips': 1})
backtest_class = BacktestMM(vol_class)
strategy_class = StrategyMM('MM', 'de', instr)
strategy_class.load_params(param_dict, contr_vars)

xx = backtest_class.simulate_strategy(strategy_class, method, instr, data_dict)

ax = data_dict['m1xq1'].iloc[:,:2].plot(grid=True, legend=True, figsize=(30, 12))
data_dict['m1xq1'].iloc[:,3].plot(grid=True, legend=True, style='.', figsize=(30, 12), ax=ax)
data_dict['output'].plot(grid=True, legend=True, figsize=(30, 12), ax=ax)
