# -*- coding: utf-8 -*-
"""
Created on Fri Sep 22 13:55:05 2023

@author: Marek
"""

from datetime import datetime, time
import numpy as np
import pandas as pd
from Math.lm_class import LinearModel, kalman, OnlineScoring
from Math.accumfeatures import MSTD
from sklearn.preprocessing import StandardScaler
from Math.ti_class import TI_class, TR_class
from Database.TPData import TPData


def ftrl_regression(X, y, l1, l2, a, b, intercept, adaptive_l1=False):
    d = X.shape[1]
    clf = LinearModel(d, intercept, lambda1=l1, lambda2=l2, alpha=a, beta=b,
                      adaptive_l1=adaptive_l1, norm_g=True)
    yhat = []
    score = []
    for x_, y_ in zip(X, y):
        if intercept:
            x_train = np.concatenate([[1], x_])
        else:
            x_train = x_
        yhat.append(clf.predict(x_train))
        score.append(clf.unc_score(x_train))
        clf.push(x_train, y_)
    out_dict = {'coeff': clf.params, 'y_pred': np.asarray(yhat), 'score': score}
    return out_dict


def kalman_regression(X, y, q, r, intercept):
    d = X.shape[1]
    if intercept:
        d += 1
    clf = kalman(q, r)
    yhat = []
    beta = np.zeros((d, 1))
    P = np.zeros((d, d))
    for x_, y_ in zip(X, y):
        if intercept:
            x_train = np.concatenate([[1], x_])
        else:
            x_train = x_
        yhat.append(x_train.dot(beta))
        beta, P = clf.step(y_, x_train.reshape((1, d)), beta, P)
    out_dict = {'coeff': clf.params, 'y_pred': yhat, 'beta': beta, 'P': P}
    return out_dict


def z_score(data_array, tau, p=2, n=5):
    z_list = []
    sigma = MSTD(tau / 2, n, p, value0=data_array[0])
    for x in data_array:
        sigma.push(x)
        m_val = sigma.mean.value
        s_val = sigma.value
        if s_val < 1e-6:
            z = 0
        else:
            z = (x - m_val) / s_val
        z_list.append(0 if np.isnan(z) else z)
    return np.asarray(z_list).reshape(-1, 1)


def data_process_single(df_data_p, mkt, tau, tau_ema, df_data_v=None):
    agg_dict = {'index': 'first'}
    agg_dict.update({k: 'mean' for k in df_data_p.columns})
    ti_cls = TR_class(tau, tau_ema)
    preds_var = [x for x in df_data_p.columns if x != mkt]
    # Output dictionary
    out_dict = {k: {} for k in preds_var}
    # Indices based on ticks
    idx_series = ti_cls.tick_imbalance_indices(df_data_p.loc[:, mkt])
    # Create returns
    data_aux = pd.concat([df_data_p.reindex(idx_series.index), idx_series], axis=1).reset_index()
    data_aux = data_aux.groupby(0).agg(agg_dict).set_index('index')
    grouped = data_aux.groupby(data_aux.index.date)
    data_dict = {date: group for date, group in grouped}
    # Process volume
    if df_data_v is None:
        vol_bool = False
    else:
        df_vol = vol_process_single(df_data_v, idx_series)
        vol_bool = True
    for n in preds_var:
        pred_var = [x for x in df_data_p.columns if x == n]
        regs_var = [x for x in df_data_p.columns if x != n]
        df_ret = pd.DataFrame([])
        for data in data_dict.values():
            y_series = data.loc[:, n].shift(periods=-1).dropna()
            data = data.reindex(y_series.index)
            data.loc[:, n] = y_series
            ret_aux = np.log(data.fillna(method='ffill')).diff()
            df_ret = pd.concat([df_ret, ret_aux])
        df_ret = df_ret.dropna()
        #
        if vol_bool:
            df_data = pd.concat([df_ret, df_vol.reindex(df_ret.index)], axis=1)
            regs_var.extend([x for x in df_vol.columns])
        else:
            df_data = df_ret
        # Model
        y = df_data.loc[:, pred_var].values.reshape(-1,)
        X = df_data.loc[:, regs_var].values.reshape(-1,len(regs_var))
        out_dict[n]['y'] = y
        out_dict[n]['X'] = X
        out_dict[n]['ts'] = df_ret.index
    return out_dict


def vol_process_single(df_data_v, idx_series):
    agg_dict = {'index': 'first'}
    agg_dict.update({k: 'sum' for k in df_data_v.columns})
    data_aux = pd.concat([df_data_v.reindex(idx_series.index), idx_series],
                         axis=1).reset_index()
    data_aux = data_aux.groupby(0).agg(agg_dict).set_index('index')
    grouped = data_aux.groupby(data_aux.index.date)
    data_dict = {date: group for date, group in grouped}
    df_vol = pd.DataFrame([])
    for data in data_dict.values():
        df_vol = pd.concat([df_vol, data])
    df_vol.columns = [x + '_v' for x in df_vol.columns]
    return df_vol


def scale_data_reg(X, y, tau, n, isEMA):
    if isEMA:
        X_scaled = np.column_stack([z_score(X[:, i], tau, n=n)
                                    for i in range(X.shape[1])])
        y_scaled = z_score(y, tau, n=n)
    else:
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        y_scaled = scaler.fit_transform(y.reshape(-1, 1))
    return X_scaled, y_scaled.reshape(-1,)


def rescale_data_reg(y_original, y_scaled, tau, n, isEMA):
    if isEMA:
        y_new = y_scaled
    else:
        scaler = StandardScaler()
        scaler.fit_transform(y_original.reshape(-1, 1))
        y_new = scaler.inverse_transform(y_scaled.reshape(-1, 1))
    return y_new.reshape(-1)


data_class = TPData()

mkt_list = ['de', 'de', 'de', 'de', 'de', 'de', 'ttf', 'ttf']
tenor_list = ['m', 'm', 'q', 'q', 'w', 'y', 'da', 'm']
tn_list = [1, 2, 1, 2, 1, 1, 1, 1]
prod = 'base'
venue_list = ['eex']
start_date = datetime(2023, 6, 12)
end_date = datetime(2023, 10, 18)
n_s = 2

dates = pd.date_range(start_date, end_date, freq='B')
product_date = [dates.shift(1, freq='B') if t == 'da' else
                dates.shift(1, freq='D') if t == 'd' else
                dates.shift(tn, freq='W-MON') if t == 'w' else
                (dates + n_s * dates.freq).shift(tn, freq='2QS-Apr') if t in ['sum', 'win'] else
                (dates + n_s * dates.freq).shift(tn, freq='YS') if t in ['dec'] else
                (dates + n_s * dates.freq).shift(tn, freq=t.upper() + 'S')
                for t, tn in zip(tenor_list, tn_list)]


start_time = time(9, 0, 0)
end_time = time(18, 0, 0)

tr_data_dict = {m + t + str(n): [] for m, t, n in zip(mkt_list, tenor_list, tn_list)}
agg_dict = {'price': 'mean', 'volume': 'sum', 'action': 'first', 'broker_id': 'first'}

for m, t, n, p_dates in zip(mkt_list, tenor_list, tn_list, product_date):
    df_tr = pd.DataFrame([])
    series = pd.Series(p_dates, index=dates)
    for p_d, ds in series.groupby(series).groups.items():
        bT = datetime.combine(ds[0], start_time)
        eT = datetime.combine(ds[-1], end_time)
        # Trades
        data_class.create_connection('OracleSQL')
        df_tr_aux = data_class.get_trades(m, t, venue_list, p_d, bT, eT, prod)
        try:
            df_tr_aux = df_tr_aux.between_time(start_time, end_time)
        except(TypeError):
            pass
        #df_tr_aux = data_class.filter_data(df_tr_aux, df_tr_aux['price'], 20)
        df_tr = pd.concat([df_tr, df_tr_aux])
    df_tr = data_class.filter_data(df_tr, df_tr['price'], 20)
    df_tr = df_tr.groupby(df_tr.index).agg(agg_dict)
    tr_data_dict[m + t + str(n)] = df_tr

data_p = pd.concat({k: v['price'] for k, v in tr_data_dict.items()}, axis=1)
data_v = pd.concat({k: v['volume'] for k, v in tr_data_dict.items()}, axis=1)

# Model
tau = 32
tau_ema = 20
tau_scl = 50
burn = 50
n = 16
intercept0 = False
isScaled = True
isEMA = True
# FTRL params
lambda1=6
lambda2=1
alpha=0.7
beta=1
# lambda1=.5
# lambda2=.5
# alpha=0.45
# beta=1

# Markets
mkt = 'dem1'

# Process data
data_dict = data_process_single(data_p, mkt, tau, tau_ema, None)

score_class = OnlineScoring('r2s', burn=burn, tau=2 * burn)
mkt2_list = ['deq1']
#mkt2_list = [k for k in data_dict.keys() if k != mkt]
score_dict = {k: {} for k in mkt2_list}
for m in mkt2_list:
    if isScaled:
        X, y = scale_data_reg(data_dict[m]['X'], data_dict[m]['y'], tau_scl, n, isEMA)
        intercept = False
    else:
        X, y = data_dict[m]['X'], data_dict[m]['y']
        intercept = intercept0
    out_dict = ftrl_regression(X, y, lambda1, lambda2, alpha, beta,
                               intercept, True)
    isScaled = False
    if isScaled:
        # Convert back to returns
        y_pred = rescale_data_reg(data_dict[m]['y'], out_dict['y_pred'], tau,
                                  n, isEMA)
        y = data_dict[m]['y']
    else:
        y_pred = out_dict['y_pred']
    y_all = pd.DataFrame([[x, z] for x, z in zip(y, y_pred)],
                         columns=['true', 'ftrl'])
    score_dict[m] = pd.Series([score_class.score(y_p, y_n)
                               for y_p, y_n in zip(y_pred, y)])
