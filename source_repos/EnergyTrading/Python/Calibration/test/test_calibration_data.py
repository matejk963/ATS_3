# -*- coding: utf-8 -*-
"""
Created on Mon Sep 18 16:55:44 2023

@author: Marek
"""

from datetime import datetime, time
import pandas as pd
import numpy as np
from Math.accumfeatures import MSTD
from Math.ti_class import TI_class, TR_class
from Math.lm_class import LinearModel, OnlineScoring
from Calibration.calibration_class import ModelCalibration
from Database.TPData import TPData
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit


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


def data_process_single(df_data, mkt, tau, tau_ema):
    agg_dict = {'index': 'first'}
    agg_dict.update({k: 'mean' for k in data_p.columns})
    ti_cls = TR_class(tau, tau_ema)
    preds_var = [x for x in data_p.columns if x != mkt]
    # Output dictionary
    out_dict = {k: {} for k in preds_var}
    # Indices based on ticks
    idx_series = ti_cls.tick_imbalance_indices(data_p.loc[:, mkt])
    # Create returns
    data_aux = pd.concat([df_data.reindex(idx_series.index), idx_series], axis=1).reset_index()
    data_aux = data_aux.groupby(0).agg(agg_dict).set_index('index')
    grouped = data_aux.groupby(data_aux.index.date)
    data_dict = {date: group for date, group in grouped}
    for n in preds_var:
        pred_var = [x for x in data_p.columns if x == n]
        regs_var = [x for x in data_p.columns if x != n]
        df_ret = pd.DataFrame([])
        for data in data_dict.values():
            y_series = data.loc[:, n].shift(periods=-1).dropna()
            data = data.reindex(y_series.index)
            data.loc[:, n] = y_series
            ret_aux = np.log(data.fillna(method='ffill')).diff()
            #data.loc[:, m] = data.loc[:, m].shift(periods=-1)
            #ret_aux = np.log(data.dropna()).diff()
            #ret_aux.iloc[:, 0] = ret_aux.iloc[:, 0].shift(periods=1)
            df_ret = pd.concat([df_ret, ret_aux])
        df_ret = df_ret.dropna()
        # Model
        y = df_ret.loc[:, pred_var].values.reshape(-1,)
        X = df_ret.loc[:, regs_var].values.reshape(-1,len(regs_var))
        out_dict[n]['y'] = y
        out_dict[n]['X'] = X
        out_dict[n]['ts'] = df_ret.index
    return out_dict


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


def calibration_reg(X, y, opt_param_dict, fix_param_dict, burn, tau, intercept):
    # Model
    d = X.shape[1]
    clf = LinearModel(d, intercept)
    # Scoring
    score_class = OnlineScoring('r2s', burn=burn, tau=2 * burn)   
    # Calibration module
    opt_param = opt_param_dict.keys()
    calibration_class = ModelCalibration(clf, score_class, opt_param, fix_param_dict)
    # CV
    tscv = TimeSeriesSplit(n_splits=5, max_train_size=2*burn)
    splits = [(train_idx, test_idx) for train_idx, test_idx in tscv.split(y)]
    # Output score
    return calibration_class.calibrate_p(X, y, splits, opt_param_dict)


data_class = TPData()

mkt_list = ['de', 'de', 'de', 'de', 'de', 'de', 'ttf', 'ttf', 'eua']
tenor_list = ['m', 'm', 'q', 'q', 'w', 'y', 'da', 'm', 'dec']
tn_list = [1, 2, 1, 2, 1, 1, 1, 1, 1]
prod = 'base'
venue_list = ['eex']
start_date = datetime(2023, 6, 12)
end_date = datetime(2023, 9, 19)
n_s = 2

dates = pd.date_range(start_date, end_date, freq='B')
product_date = [dates.shift(1, freq='B') if t == 'da' else
                dates.shift(1, freq='D') if t == 'd' else
                dates.shift(tn, freq='W-MON') if t == 'w' else
                (dates + n_s * dates.freq).shift(tn, freq='2QS-Apr') if t in ['sum', 'win'] else
                (dates + n_s * dates.freq).shift(tn, freq='YS') if t in ['dec'] else
                (dates + n_s * dates.freq).shift(tn, freq=t.upper() + 'S')
                for t, tn in zip(tenor_list, tn_list)]


start_time = time(8, 0, 0)
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

# Calibration
tau = 50
tau_ema = 22
tau_scl = 50
burn = 50
n = 16
intercept0 = False
isScaled = True
isEMA = True

# Parameters fix and variable
opt_param = ['lambda1', 'lambda2', 'alpha', 'beta']
opt_param_val = [np.arange(0, 10, .5), np.arange(0, 3, 0.5),
                 np.arange(0.05, 3, 0.2), np.arange(0.5, 1.5, 0.5)]
opt_param_dict = {k: v for k, v in zip(opt_param, opt_param_val)}

fix_param = ['adaptive_l1', 'norm_g']
fix_param_val = [True, True]
fix_param_dict = {k: v for k, v in zip(fix_param, fix_param_val)}

# Markets
mkt = 'dem1'

# Process data
data_dict = data_process_single(data_p, mkt, tau, tau_ema)
#mkt2_list = ['dew1']
mkt2_list = data_dict.keys()
cal_dict = {k: {} for k in mkt2_list}
for m in mkt2_list:
    if isScaled:
        X, y = scale_data_reg(data_dict[m]['X'], data_dict[m]['y'], tau_scl, n, isEMA)
        intercept = False
    else:
        X, y = data_dict[m]['X'], data_dict[m]['y']
        intercept = intercept0
    cal_dict[m] = calibration_reg(X, y, opt_param_dict, fix_param_dict,
                                  burn, tau, intercept)