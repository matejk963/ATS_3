# -*- coding: utf-8 -*-
"""
Created on Tue Dec 12 17:27:03 2023

@author: Marek
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, time
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
    period_list = [np.log(2) / x for x in theta_list]
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


def calc_ema_m(df_data, tau, margin, w, eql_p, tol=0):
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


def calc_ema_mstd(df_data, tau, margin, w, df_model, tol=0):
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
        margin_list = [max(m * w, margin) for m in df_model_aux.iloc[:, 1].values]
        ema_list = [w * eq + (1 - w) * x for x, eq in zip(ema_list, eql_list)]
        bands.extend([[x - m, x, x + m] for x, m in zip(ema_list, margin_list)])
    return pd.DataFrame(bands, index=df_data.index).ffill()


data_class = TPDataDa()

mkt_list = ['de']
tenor_list = ['m']
tn1_list = [1]
tn2_list = [2]
prod = 'base'
venue_list = ['eex']
start_date = datetime(2023, 12, 1)
end_date = datetime(2023, 12, 15)
n_s = 2

dates = pd.date_range(start_date, end_date, freq='B')
product_date1 = [dates.shift(1, freq='B') if t == 'da' else
                 dates.shift(1, freq='D') if t == 'd' else
                 dates.shift(tn, freq='W-MON') if t == 'w' else
                 (dates + n_s * dates.freq).shift(tn, freq='2QS-Apr') if t in ['sum', 'win'] else
                 (dates + n_s * dates.freq).shift(tn, freq=t.upper() + 'S')
                 for t, tn in zip(tenor_list, tn1_list)]
if not tn2_list:
    product_date2 = [None] * len(product_date1)
else:
    product_date2 = [dates.shift(1, freq='B') if t == 'da' else
                     dates.shift(1, freq='D') if t == 'd' else
                     dates.shift(tn, freq='W-MON') if t == 'w' else
                     (dates + n_s * dates.freq).shift(tn, freq='2QS-Apr') if t in ['sum', 'win'] else
                     (dates + n_s * dates.freq).shift(tn, freq=t.upper() + 'S')
                     for t, tn in zip(tenor_list, tn2_list)]

if not tn2_list:
    tn_list = [str(t1) for t1 in tn1_list]
else:
    tn_list = [str(t1) + '_' + str(t2) for (t1, t2) in zip(tn1_list, tn2_list)]

start_time = time(9, 0, 0)
end_time = time(18, 0, 0)

tr_data_dict = {m + t + str(n): [] for m, t, n in zip(mkt_list, tenor_list, tn_list)}
ba_data_dict = {m + t + str(n): [] for m, t, n in zip(mkt_list, tenor_list, tn_list)}
agg_dict = {'price': 'mean', 'volume': 'sum', 'action': 'first', 'broker_id': 'first'}

for m, t, n, p1_d, p2_d in zip(mkt_list, tenor_list, tn_list, product_date1,
                               product_date2):
    df_ba = pd.DataFrame([])
    df_tr = pd.DataFrame([])
    if p2_d is None:
        df_prod_dates = pd.DataFrame([p1_d], columns=dates).T
    else:
        df_prod_dates = pd.DataFrame([p1_d, p2_d], columns=dates).T
    for p_d, ds in df_prod_dates.groupby(0).groups.items():
        bT = datetime.combine(ds[0], start_time)
        eT = datetime.combine(ds[-1], end_time)
        if p2_d is None:
            pd_2 = None
        else:
            pd_2 = df_prod_dates.loc[ds[0], 1]
        # Bid Ask
        data_class.create_connection('PostgreSQL')
        df_ba_aux = data_class.get_best_orders_data(m, t, p_d, bT, eT, prod,
                                                    pd_2)
        df_ba_aux = df_ba_aux.between_time(start_time, end_time)
        df_ba_aux = df_ba_aux.rename(columns={'bidbestprice': 'bid', 'askbestprice': 'ask'})
        #df_ba_aux = data_class.filter_data(df_ba_aux, df_ba_aux['bidbestprice'], 20)
        df_ba = pd.concat([df_ba, df_ba_aux], axis=0)
        # Trades
        data_class.create_connection('OracleSQL')
        df_tr_aux = data_class.get_trades(m, t, venue_list, p_d, bT, eT, prod,
                                          pd_2)
        try:
            df_tr_aux = df_tr_aux.between_time(start_time, end_time)
        except(TypeError):
            pass
        df_tr_aux = df_tr_aux[(df_tr_aux['broker_id']==14) |
                              (df_tr_aux['volume']<=20)]
        df_tr = pd.concat([df_tr, df_tr_aux], axis=0)
    df_tr = data_class.filter_data(df_tr, df_tr['price'], 20)
    df_tr = df_tr.groupby(df_tr.index).agg(agg_dict)

df_ba.index.rename('index', inplace=True)
df_tr.index.rename('index', inplace=True)

# Model
tau_t = 15
tau_ema = 22
data = tick_data(df_tr, tau_t, tau_ema)
N = 30
tau_m = 15
model_data = model_tr(data, tau_m, N)

method = 'simple'
tau = 5
margin = .2
eql_p = -6.25
w = 0.1

# Adjust trades
df_em = calc_ema_mstd(df_ba, tau, margin, w, model_data).dropna()
# df_em = calc_ema_m(df_ba, tau, margin, w, eql_p)
df_ba_a = df_ba.loc[df_em.index, :]
df_tr_a = adjust_trds(df_tr.copy(), df_em)

instr = 'm1'
data_dict = {}
data_dict[instr] = BacktestMM.merge_data(df_ba, df_tr_a)

# data_dict['output'] = calc_ema_m(data_dict[instr], tau, margin, w, eql_p)
ts = data_dict[instr].index
df_em = df_em[~df_em.index.duplicated(keep='first')]
df_em = df_em.reindex(ts.drop_duplicates()).ffill()
data_dict['output'] = df_em.loc[ts, :]

param_list = ['t_end', 'take_profit', 'stop_loss', 'ba_spread', 'ba_max']
contr_vars = ['threshold']
param_dict = {k: [] for k in param_list}
param_dict['t_end'] = datetime(2023, 12, 28)
param_dict['take_profit'] = 5
param_dict['stop_loss_rat'] = 1
param_dict['ba_spread'] = 0.50
param_dict['ba_max'] = 1.5
param_dict['br_fee'] = 0.035

vol_class = VolumeClass(1)
backtest_class = BacktestMM(vol_class)
strategy_class = StrategyMM('MM', 'de', instr)
strategy_class.load_params(param_dict, contr_vars)

xx = backtest_class.simulate_strategy(strategy_class, method, instr, data_dict)


