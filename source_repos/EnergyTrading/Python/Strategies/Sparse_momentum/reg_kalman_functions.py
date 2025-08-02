# -*- coding: utf-8 -*-
"""
Created on Thu Jul  4 14:51:51 2024

@author: Marek
"""

from datetime import datetime, time
import numpy as np
import pandas as pd
from Math.lm_class import LinearModel, kalman, kalman1d, OnlineScoring
from Math.accumfeatures import MSTD
from sklearn.preprocessing import StandardScaler
from Math.ti_class import TI_class, TR_class
from Database.TPData import TPData, TPDataDa
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import TimeSeriesSplit
from Strategies.Sparse_momentum.ob_attributes import OB_attributes
from sklearn.metrics import confusion_matrix
import itertools


def class_data_test(df_ba, timestamp, cls_margin, tick_val, gran=None):
    variable_dict = df_ba.to_dict(orient='list')
    variable_dict['timestamp'] = df_ba.index
    obSim = OB_attributes([])
    # Prepare main market
    idx, csum, ts = obSim.calc_tick_index(variable_dict, None, None, 1)
    data_cl = obSim.prepare_class_data(variable_dict, csum, idx, tick_val,
                                       cls_margin, timestamp, gran)
    return data_cl


def scale_data_reg_old(X, y, tau, n, isEMA):
    if isEMA:
        X_scaled = np.column_stack([z_score(X[:, i], tau, n=n)
                                    for i in range(X.shape[1])])
        y_scaled = z_score(y, tau, n=n)
    else:
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        y_scaled = scaler.fit_transform(y.reshape(-1, 1))
    return X_scaled, y_scaled.reshape(-1,)


def scale_data_reg(X_train, y_train, X_tests, y_tests, n, isEMA):
    if isEMA:
        tau = len(y_train)
        X_params = [z_score_params(X_train[:, i], tau, n=n) for i in range(X_train.shape[1])]
        y_params = z_score_params(y_train, tau, n=n)
        X_train_s = np.column_stack([(X_train[:, i] - s.mean.value) / s.value
                                     for i, s in enumerate(X_params)])
        y_train_s = (y_train - y_params.mean.value) / y_params.value
        X_tests_s = np.column_stack([(X_tests[:, i] - s.mean.value) / s.value
                                     for i, s in enumerate(X_params)])
        y_tests_s = (y_tests - y_params.mean.value) / y_params.value
    else:
        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_tests_s = scaler.transform(X_tests)
        y_train_s = scaler.fit_transform(y_train.reshape(-1, 1)).reshape(-1,)
        y_tests_s = scaler.transform(y_tests.reshape(-1, 1)).reshape(-1,)
    return X_train_s, y_train_s, X_tests_s, y_tests_s


def rescale_data_reg_old(y_original, y_scaled, tau, n, isEMA):
    if isEMA:
        y_new = z_score_inv(y_original, y_scaled, tau, n=n)
    else:
        scaler = StandardScaler()
        scaler.fit_transform(y_original.reshape(-1, 1))
        y_new = scaler.inverse_transform(y_scaled.reshape(-1, 1))
    return y_new.reshape(-1,)


def rescale_data_reg(y_original, y_scaled, tau, n, isEMA):
    if isEMA:
        tau = len(y_original)
        y_params = z_score_params(y_original, tau, n=n)
        y_new = y_scaled * y_params.value + y_params.mean.value
    else:
        scaler = StandardScaler()
        scaler.fit_transform(y_original.reshape(-1, 1))
        y_new = scaler.inverse_transform(y_scaled.reshape(-1, 1)).reshape(-1,)
    return y_new


def z_score(data_array, tau, p=2, n=15):
    z_list = []
    sigma = MSTD(tau / 2, n, p, value0=data_array[0])
    for x in data_array:
        sigma.push(x)
        m_val = sigma.mean.value
        s_val = sigma.value
        if s_val < 1e-6:
            s_val = 1e-6
        z = (x - m_val) / s_val
        z_list.append(0 if np.isnan(z) else z)
    return np.asarray(z_list).reshape(-1, 1)


def z_score_params(data_array, tau, p=2, n=15):
    sigma = MSTD(tau / 2, n, p, value0=data_array[0])
    [sigma.push(x) for x in data_array]
    if sigma.value < 1e-6:
        sigma.value = 1e-6
    return sigma


def scale_data_dict_old(data_dict, tau, n, isScaled, isEMA):
    if not isScaled:
        return data_dict
    scaled_dict = {'keys': [], 'train': {}, 'tests': {}}
    for d in data_dict['keys']:
        scaled_dict['train'][d] = {}
        scaled_dict['tests'][d] = {}
        # Data
        X_train, y_train = data_dict['train'][d]['X'], data_dict['train'][d]['y']
        X_tests, y_tests = data_dict['tests'][d]['X'], data_dict['tests'][d]['y']
        # Scale
        X_train_s, y_train_s = scale_data_reg(X_train, y_train, tau, n, isEMA)
        X_tests_s, y_tests_s = scale_data_reg(X_tests, y_tests, tau, n, isEMA)
        # Write to dictionary
        scaled_dict['train'][d]['X'], scaled_dict['train'][d]['y'] = X_train_s, y_train_s
        scaled_dict['tests'][d]['X'], scaled_dict['tests'][d]['y'] = X_tests_s, y_tests_s
        scaled_dict['train'][d]['ts'] = data_dict['train'][d]['ts']
        scaled_dict['tests'][d]['ts'] = data_dict['tests'][d]['ts']
        scaled_dict['keys'].append(d)
    return scaled_dict


def scale_data_dict(data_dict, tau, n, isScaled, isEMA):
    if not isScaled:
        return data_dict
    scaled_dict = {'keys': [], 'train': {}, 'tests': {}}
    for d in data_dict['keys']:
        scaled_dict['train'][d] = {}
        scaled_dict['tests'][d] = {}
        # Data
        X_train, y_train = data_dict['train'][d]['X'], data_dict['train'][d]['y']
        X_tests, y_tests = data_dict['tests'][d]['X'], data_dict['tests'][d]['y']
        # yp_tests, Xp_tests = [data_dict['tests'][d][k] for k in ['y_p', 'X_p']]
        Xp_dict = data_dict['tests'][d]['X_p']
        Xp_tests = data_dict['tests'][d]['X_p']['x'].reshape(-1, 1)
        # Scale
        X_train_s, y_train_s, X_tests_s, y_tests_s = scale_data_reg(X_train, y_train, X_tests, y_tests, n, isEMA)
        # Scale trades output
        _, _, Xp_s, _ = scale_data_reg(X_train, y_train, Xp_tests, y_tests, n, isEMA)
        # Write to dictionary
        scaled_dict['train'][d]['X'], scaled_dict['train'][d]['y'] = X_train_s, y_train_s
        scaled_dict['tests'][d]['X'], scaled_dict['tests'][d]['y'] = X_tests_s, y_tests_s
        # scaled_dict['tests'][d]['X_p'], scaled_dict['tests'][d]['y_p'] = Xp_tests, yp_tests
        scaled_dict['tests'][d]['X_p'] = {'index': Xp_dict['index'], 'x': Xp_s.reshape(-1,), 't_y': Xp_dict['t_y']}
        scaled_dict['train'][d]['ts'] = data_dict['train'][d]['ts']
        scaled_dict['tests'][d]['ts'] = data_dict['tests'][d]['ts']
        scaled_dict['keys'].append(d)
    return scaled_dict


def rescale_out_dict(scaled_out_dict, true_dict, tau, n, isScaled, isEMA):
    if not isScaled:
        return scaled_out_dict
    rescaled_dict = {k: {} for k in scaled_out_dict.keys()}
    for d, dct in scaled_out_dict.items():
        y_original = true_dict[d]['y']
        y_scaled = dct['y_pred']
        y_true_s = dct['y_true']
        y_pred_rs = rescale_data_reg(y_original, y_scaled, tau, n, isEMA)
        y_true_rs = rescale_data_reg(y_original, y_true_s, tau, n, isEMA)
        rescaled_dict[d]['y_pred'] = y_pred_rs
        rescaled_dict[d]['y_true'] = y_true_rs
    return rescaled_dict


def z_score_inv(y_original, y_scaled, tau, p=2, n=15):
    y_list = []
    sigma = MSTD(tau / 2, n, p, value0=y_original[0])
    for y_true, z in zip(y_original, y_scaled):
        sigma.push(y_true)
        m_val = sigma.mean.value
        s_val = sigma.value
        if s_val < 1e-6:
            s_val = 1e-6
        y = z * s_val + m_val
        y_list.append(np.nan if np.isnan(y) else y)
    return np.asarray(y_list).reshape(-1, 1)


def price_process_km_tick(df_data_p, mkt, tau, tau_ema, df_data_v=None):
    agg_dict = {'index': 'first'}
    agg_dict.update({k: 'mean' for k in df_data_p.columns})
    ti_cls = TR_class(tau, tau_ema)
    # Indices based on ticks
    idx_series = ti_cls.tick_imbalance_indices(df_data_p.loc[:, mkt])
    # Create returns
    data_aux = pd.concat([df_data_p.reindex(idx_series.index), idx_series], axis=1).reset_index()
    data_aux = data_aux.groupby(0).agg(agg_dict).set_index('index')
    grouped = data_aux.groupby(data_aux.index.date)
    data_dict = {date: group for date, group in grouped}
    data_sm = pd.DataFrame([])
    data_rl = pd.DataFrame([])
    for data in data_dict.values():
        data_aux = KFSmootherDF(data.dropna())
        data_sm = pd.concat([data_sm, data_aux])
        data_rl = pd.concat([data_rl, data.dropna()])
    return data_rl, data_sm


def price_process_km(df_data_p):
    grouped = df_data_p.groupby(df_data_p.index.date)
    data_dict = {date: group for date, group in grouped}
    data_sm = pd.DataFrame([])
    data_st = pd.DataFrame([])
    for data in data_dict.values():
        data_b = pd.DataFrame([])
        data_p = pd.DataFrame([])
        for m in data.columns:
            b_ser, p_ser = [x.reindex(data.index) for x in KFSmootherS(data.loc[:, m].dropna())]
            data_b = pd.concat([data_b, b_ser], axis=1)
            data_p = pd.concat([data_p, p_ser], axis=1)
        data_b.columns = data.columns
        data_sm = pd.concat([data_sm, data_b])
        data_p.columns = data.columns
        data_st = pd.concat([data_st, data_p])
    return data_sm, data_st


def data_process_single_ret_km(df_data_p, mkt, tau, tau_ema, df_data_v=None, diff_bool=True):
    agg_dict = {'index': 'first'}
    agg_dict.update({k: 'mean' for k in df_data_p.columns})
    ti_cls = TR_class(tau, tau_ema)
    # preds_var = [x for x in df_data_p.columns if x != mkt]
    preds_var = [x for x in df_data_p.columns]
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
            y_series = data.loc[:, n].shift(periods=0).dropna()
            data = data.reindex(y_series.index)
            data.loc[:, n] = y_series
            if diff_bool:
                ret_aux = np.log(data.fillna(method='ffill')).diff()
            else:
                ret_aux = data.dropna()
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
        X, y = KFSmoother(X, y)
        out_dict[n]['y'] = y
        out_dict[n]['X'] = X
        out_dict[n]['ts'] = df_ret.index
    return out_dict


def tick_data(df_data_p, df_data_v, mkt, tau, tau_ema):
    agg_dict = {'index': 'first'}
    agg_dict.update({k: 'sum' for k in df_data_p.columns})
    agg_dict.update({k + '_v': 'sum' for k in df_data_p.columns})
    ti_cls = TR_class(tau, tau_ema)
    # preds_var = [x for x in df_data_p.columns if x != mkt]
    # Indices based on ticks
    idx_series = ti_cls.tick_imbalance_indices(df_data_p.loc[:, mkt])
    # Create returns
    data_vw = pd.concat([df_data_p * df_data_v, df_data_v], axis=1)
    data_vw.columns = list(agg_dict.keys())[1:]
    data_aux = pd.concat([data_vw.reindex(idx_series.index), idx_series], axis=1).reset_index()
    data_aux = data_aux.groupby(0).agg(agg_dict).set_index('index')
    # Back to vwp
    for col in df_data_p.columns:
        data_aux.loc[:, col] /= data_aux.loc[:, col + '_v']
    return data_aux


def data_process_single_ret(df_data_p, mkt, tau, tau_ema, df_data_v=None,
                            diff_bool=True, vol_bool=False, km_bool=False):
    if df_data_v is None:
        df_data_v = pd.DataFrame(np.ones(df_data_p.shape), index=df_data_p.index, columns=df_data_p.columns)
        df_data_v = df_data_v.where(~df_data_p.isna(), other=np.nan)
    preds_var = [x for x in df_data_p.columns]
    # Output dictionary
    out_dict = {k: {} for k in preds_var}
    # Ticks
    data_aux = tick_data(df_data_p, df_data_v, mkt, tau, tau_ema)
    vol_cols = [k + '_v' for k in df_data_v.columns]
    df_vol = data_aux.loc[:, vol_cols]
    data_aux = data_aux.loc[:, df_data_p.columns]
    grouped = data_aux.groupby(data_aux.index.date)
    data_dict = {date: group for date, group in grouped}
    for n in preds_var:
        pred_var = [x for x in df_data_p.columns if x == n]
        regs_var = [x for x in df_data_p.columns if x != n]
        df_ret = pd.DataFrame([])
        df_price = pd.DataFrame([])
        for data in data_dict.values():
            if km_bool:
                data_s, _ = price_process_km(data)
            else:
                data_s = data
            y_series = data_s.loc[:, n].shift(periods=0).dropna()
            data_s = data_s.reindex(y_series.index)
            data_s.loc[:, n] = y_series
            if diff_bool:
                ret_aux = np.log(data_s.ffill()).diff()
                price_aux = data.reindex(data_s.index).ffill()
            else:
                ret_aux = data_s.dropna()
                price_aux = data.reindex(data_s.index).dropna()
            df_ret = pd.concat([df_ret, ret_aux])
            df_price = pd.concat([df_price, price_aux])
        df_ret = df_ret.dropna()
        df_price = df_price.reindex(df_ret.index)
        #
        if vol_bool:
            df_data = pd.concat([df_ret, df_vol.reindex(df_ret.index)], axis=1)
            regs_var.extend([x for x in df_vol.columns])
        else:
            df_data = df_ret
        # Model
        y = df_data.loc[:, pred_var].values.reshape(-1,)
        X = df_data.loc[:, regs_var].values.reshape(-1,len(regs_var))
        y_p = df_price.loc[:, pred_var].values.reshape(-1,)
        X_p = df_price.loc[:, regs_var].values.reshape(-1,len(regs_var))
        # X, y = KFSmoother(X, y)
        out_dict[n]['y'] = y
        out_dict[n]['X'] = X
        out_dict[n]['y_p'] = y_p
        out_dict[n]['X_p'] = X_p
        out_dict[n]['ts'] = df_ret.index
    return out_dict





def data_process_mdl(trd_ser, data_, data_s, data_p, pred_var, regs_var, km_bool):
    # Unify timestamp
    ts = data_.index.union(trd_ser.index)
    data_s = data_s.shift(1).reindex(ts).ffill().reindex(trd_ser.index)
    data_ = data_.shift(1).reindex(ts).ffill().reindex(trd_ser.index)
    trd_ser = trd_ser.loc[:, regs_var]
    if km_bool:
        # Smooth trades based on ticks
        data_p = data_p.shift(1).reindex(ts).ffill().reindex(trd_ser.index)
        trd_ser = KFSmoothTrades(trd_ser, data_s.loc[:, regs_var], data_p.loc[:, regs_var])
    else:
        trd_ser = trd_ser.iloc[:, 0]
    # df_out = pd.concat([trd_ser, data_s.loc[:, regs_var], data_.loc[:, pred_var]], axis=1)
    # df_out.columns = ['trds', 't_x', 't_y']
    x_ser = np.log(trd_ser) - np.log(data_s.loc[:, regs_var[0]])
    df_out = pd.concat([x_ser, data_.loc[:, pred_var]], axis=1)
    df_out.columns = ['x', 't_y']
    return df_out


def to_dict_xp(df_price):
    X_p = df_price.loc[:, 'x'].values.reshape(-1,)
    y_t = df_price.loc[:, 't_y'].values.reshape(-1,)
    return {'index': df_price.index, 'x': X_p, 't_y': y_t}


def split_data(data_dict_, date_range_dict, n_test):
    out_dict = {k: {'train': {}, 'tests': {}, 'keys': []} for k in data_dict_.keys()}
    date_s = {k: (v[-n_test], v[-1]) for k, v in date_range_dict.items()}
    for m, data in data_dict_.items():
        y_ser = pd.Series(data['y'], index=data['ts'])
        X_df = pd.DataFrame(data['X'], index=data['ts'])
        # yp_ser = pd.Series(data['y_p'], index=data['ts'])
        # Xp_df = pd.DataFrame(data['X_p'], index=data['ts'])
        Xp_df = pd.DataFrame(data['X_p']).set_index('index')
        for d, date_tuple in date_s.items():
            date_test, date_end = date_tuple
            date_end += pd.Timedelta(hours=24)
            date = date_test.date()
            out_dict[m]['train'][date] = {}
            out_dict[m]['tests'][date] = {}
            y_train, y_tests = y_ser.loc[:date_test], y_ser.loc[date_test:date_end]
            X_train, X_tests = X_df.loc[:date_test, :], X_df.loc[date_test:date_end, :]
            # Prices
            # yp_tests = yp_ser.loc[date_test:date_end]
            Xp_tests = Xp_df.loc[date_test:date_end, :]
            # Train
            out_dict[m]['train'][date]['y'] = y_train.values
            out_dict[m]['train'][date]['X'] = X_train.values
            out_dict[m]['train'][date]['ts'] = y_train.index
            # Tests
            out_dict[m]['tests'][date]['y'] = y_tests.values
            out_dict[m]['tests'][date]['X'] = X_tests.values
            # out_dict[m]['tests'][date]['y_p'] = yp_tests.values
            out_dict[m]['tests'][date]['X_p'] = to_dict_xp(Xp_tests)
            out_dict[m]['tests'][date]['ts'] = y_tests.index
            # Keys
            out_dict[m]['keys'].append(date)
    return out_dict


def linear_offline(data_dict, intercept=True):
    out_dict = {d: {} for d in data_dict['keys']}
    model = LinearRegression(fit_intercept=intercept)
    for d in data_dict['keys']:
        # Data
        X_train, y_train = data_dict['train'][d]['X'], data_dict['train'][d]['y']
        X_tests, y_tests = data_dict['tests'][d]['X'], data_dict['tests'][d]['y']
        # Training
        model.fit(X_train, y_train)
        # Testing
        y_pred = model.predict(X_tests)
        # Save data
        out_dict[d]['y_pred'] = y_pred
        out_dict[d]['y_true'] = y_tests
    return out_dict


def linear_online(data_dict, intercept, l1, l2, a, b, adaptive_l1=False):
    out_dict = {d: {} for d in data_dict['keys']}
    for d in data_dict['keys']:
        # Data
        X_train, y_train = data_dict['train'][d]['X'], data_dict['train'][d]['y']
        X_tests, y_tests = data_dict['tests'][d]['X'], data_dict['tests'][d]['y']
        # Model
        n = X_train.shape[1]
        model = LinearModel(n, intercept, lambda1=l1, lambda2=l2, alpha=a, beta=b,
                            adaptive_l1=adaptive_l1, norm_g=True)
        # Training
        for x_, y in zip(X_train, y_train):
            if intercept:
                x = np.concatenate([[1], x_])
            else:
                x = x_
            model.push(x, y)
        # Testing
        y_pred = []
        for x_, y in zip(X_tests, y_tests):
            if intercept:
                x = np.concatenate([[1], x_])
            else:
                x = x_
            # y_pred.append(model.predict(x))
            model.push(x, y)
            y_pred.append(model.predict(x))
        # Save data
        out_dict[d]['y_pred'] = np.asarray(y_pred)
        out_dict[d]['y_true'] = y_tests
    return out_dict


def score(pred_dict, score_class):
    score_dict = {d: [] for d in pred_dict.keys()}
    for d, data in pred_dict.items():
        score_class.reset()
        y_pred = data['y_pred']
        y_true = data['y_true']
        score_dict[d].extend([score_class.score(y_p, y_t) for y_p, y_t in zip(y_pred, y_true)])
    return score_dict


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


def KFSmootherS(data_ser):
    x_, P_ = KFSmootherSingle(data_ser.values)
    return pd.Series(x_, index=data_ser.index), pd.Series(P_, index=data_ser.index)


def KFSmootherDF(df_data):
    X = df_data.values
    X_ = np.empty(X.shape, dtype=np.float64)
    for n in range(X.shape[1]):
        x_ = X[:, n]
        X_[:, n], _ = KFSmootherSingle(x_)
    return pd.DataFrame(X_, index=df_data.index, columns=df_data.columns)


def KFSmoother(X, y):
    y_, _ = KFSmootherSingle(y)
    X_ = np.empty(X.shape, dtype=np.float64)
    for n in range(X.shape[1]):
        x_ = X[:, n]
        X_[:, n] = KFSmootherSingle(x_)
    return X_, y_

def KFSmootherSingle(x):
    q = .05
    r = 1.
    clf = kalman1d(q, r)
    beta = x[0]
    P = 1
    beta_list = []
    P_list = []
    for x_ in x:
        beta, P = clf.step(x_, 1, beta, P)
        beta_list.append(beta)
        P_list.append(P)
    return np.array(beta_list), np.array(P_list)


def KFSmoothTrades(trd_ser, data_s, data_p):
    ts = trd_ser.index
    df_data = pd.concat([trd_ser, data_s, data_p], axis=1).dropna()
    q = .05
    r = 1.
    clf = kalman1d(q, r)
    price_list = []
    for x_, b, p in df_data.values:
        x, _ = clf.step(x_, 1, b, p)
        price_list.append(x)
    return pd.Series(price_list, index=df_data.index).reindex(ts)





def prepare_model_trds_on(df_data_p, mkt, model, data_dict_, true_dict, tau, n, isEma):
    grouped = df_data_p.loc[:, mkt].groupby(df_data_p.index.date)
    price_dict = {date: group.dropna() for date, group in grouped if date in data_dict_['keys']}
    out_dict = {k: [] for k in data_dict_['keys']}
    for dt, price_ser in price_dict.items():
        model.reset()
        # Train model
        X_train, y_train = [data_dict_['train'][dt][k] for k in ['X', 'y']]
        model.fit(X_train, y_train)
        # Data
        # Original y
        y_original = true_dict[dt]['y']
        # Data trades
        Xp_dict = data_dict_['tests'][dt]['X_p']
        # Adjust trades and ticks
        X_tests, y_tests, ts_tests = [data_dict_['tests'][dt][k] for k in ['X', 'y', 'ts']]
        df_test = pd.DataFrame(np.concatenate([X_tests, y_tests.reshape(-1,1)], axis=1),
                               index=ts_tests, columns=['X', 'y'])
        ttest_ser = pd.Series(Xp_dict['x'], index=Xp_dict['index'], name='trd')
        data_mat = pd.concat([df_test, ttest_ser], axis=1).values
        # Testing and rescale
        y_pred_list = []
        for x_, y, trd in data_mat:
            if not np.isnan(x_):
                # Retrain model
                if model.intercept:
                    x = np.concatenate([[1], x_])
                else:
                    x = x_
                model.push(np.array(x).reshape(1,), y)
            if not np.isnan(trd):
                # Predict
                y_pred_list.append(model.predict(np.array(trd).reshape(1,)))
        y_pred_s = np.asarray(y_pred_list)
        y_pred = rescale_data_reg(y_original, y_pred_s, tau, n, isEMA)
        # Transform to prices
        price_pred = np.exp(y_pred) * Xp_dict['t_y']
        # Write to out_dict
        out_dict[dt] = {'index': Xp_dict['index'], 'price': price_pred, 'ret': y_pred_s}
    return out_dict


def prepare_class_data(df_ba, tick_val, cls_margin=.0):
    grouped = df_ba.groupby(df_ba.index.date)
    ba_dict = {date: group.dropna() for date, group in grouped if date in pred_dict.keys()}
    cls_dict = {k: [] for k in ba_dict.keys()}
    for dt, df_ba_aux in ba_dict.items():
        # Class
        cls_dict[dt] = class_data_test(df_ba_aux, None, cls_margin, tick_val, None)
    return ba_dict, cls_dict


def process_model_mkt(ba_dict,  pred_dict):
    out_dict = {k: [] for k in ba_dict.keys()}
    for dt, df_ba_aux in ba_dict.items():
        df_pred = pd.DataFrame(pred_dict[dt]).set_index('index')
        ts = df_ba_aux.index.union(df_pred.index)
        ba_aux = df_ba_aux.reindex(ts).ffill().reindex(df_pred.index)

        # Bid Ask margin
        # Bid margin
        bmrg_ser = ba_aux.loc[:, 'b_price'] - df_pred.loc[:, 'price']
        amrg_ser = df_pred.loc[:, 'price'] - ba_aux.loc[:, 'a_price']
        mrg_ser = amrg_ser.clip(lower=0) - bmrg_ser.clip(lower=0)
        mrg_ser.name = 'fair_margin'
        out_dict[dt] = pd.concat([ba_aux, df_pred, mrg_ser], axis=1)
    return out_dict


def conf_matrix(processed_dict, thres_mrg, thres_ret, start_time=None, end_time=None):
    df_cls = pd.DataFrame([])
    mat_dict = {}
    for dt, df_data in processed_dict.items():
        # Select
        pred_cls_aux = pd.Series(0, index=df_data.index, name='pred')
        idx_l = ((df_data['ret'] > thres_ret) & (df_data['fair_margin'] > thres_mrg) &
                 (df_data['ret'] * df_data['fair_margin'] > 0))
        idx_s = ((df_data['ret'] < -thres_ret) & (df_data['fair_margin'] < -thres_mrg) &
                 (df_data['ret'] * df_data['fair_margin'] > 0))
        pred_cls_aux[idx_l] = 1
        pred_cls_aux[idx_s] = -1
        df_cls_aux = pd.concat([pred_cls_aux, df_data['class']], axis=1)
        df_cls_aux = df_cls_aux[df_cls_aux.loc[:, 'pred'] != 0]
        if start_time is None:
            pass
        else:
            df_cls_aux = df_cls_aux.between_time(start_time, end_time)
        if df_cls.empty:
            df_cls = df_cls_aux
        else:
            df_cls = pd.concat([df_cls, df_cls_aux], axis=0)
        y_pred = df_cls_aux.loc[:, 'pred']
        y_true = df_cls_aux.loc[:, 'class']
        mat_dict[dt] = confusion_matrix(y_true, y_pred, labels=[-1, 0, 1])
    y_pred = df_cls.loc[:, 'pred']
    y_true = df_cls.loc[:, 'class']
    tot_mat = confusion_matrix(y_true, y_pred, labels=[-1, 0, 1])
    return tot_mat, mat_dict


def process_conf_matrix(tot_mat, mat_dict):
    def accuracy(mat):
        TN, FP = mat[0, 0], mat[1, 0] + mat[2, 0]
        FN, TP = mat[0, 2] + mat[1, 2], mat[2, 2]
        if (TP + TN + FP + FN) == 0:
            return np.nan
        else:
            return (TP + TN) / (TP + TN + FP + FN)
    return accuracy(tot_mat), {k: accuracy(m) for k, m in mat_dict.items()}


def calibration(reg_data, opt_param_dict, fix_param_dict):
    data_keys = reg_data['keys']
    tscv = TimeSeriesSplit(n_splits=5, max_train_size=len(data_keys)//3)
    splits = [(train_idx, test_idx) for train_idx, test_idx in tscv.split(reg_data['keys'])]
    keys = opt_param_dict.keys()
    lists = opt_param_dict.values()
    combinations = list(itertools.product(*lists))
    # Create dictionaries for each combination
    params_dict_list = [dict(zip(keys, combo)) for combo in combinations]
    s_dict = {k: [] for k in combinations}
    for train_idx, _ in splits:
        train_keys = [data_keys[i] for i in train_idx]
        reg_data_ = {'keys': train_keys,
                     'train': {k: reg_data['train'][k] for k in train_keys},
                     'tests': {k: reg_data['tests'][k] for k in train_keys}}
        out_dict_ = eval_single(reg_data_, params_dict_list, fix_param_dict)
        [s_dict[k].append(v) for k, v in out_dict_.items()]
    # for o_param_dict in params_dict_list:
    #     param_dict = {**o_param_dict, **fix_param_dict}
    #     out_dict_ = eval_single(reg_data, param_dict, splits)
    #     [s_dict[k].append(v) for k, v in out_dict_.items()]
    return {k: np.mean(v) for k, v in s_dict.items()}


def eval_single(reg_data_, params_dict_list, fix_param_dict):
    combinations = [tuple(x.values()) for x in params_dict_list]
    s_dict = {k: 0 for k in combinations}
    for o_param_dict in params_dict_list:
        k = tuple(o_param_dict.values())
        param_dict = {**o_param_dict, **fix_param_dict}
        tau, n, isScaled, isEMA = [param_dict[k] for k in ['tau', 'n', 'isScaled', 'isEMA']]
        lambda1, lambda2, alpha, beta, ad = [param_dict[k] for k in ['lambda1', 'lambda2', 'alpha', 'beta', 'adaptive_l1']]
        out_dict = linear_online(reg_data_, False, lambda1, lambda2, alpha, beta, adaptive_l1=ad)
        rs_out_dict = rescale_out_dict(out_dict, split_dict[mkt]['train'], tau, n, isScaled, isEMA)
        score_dict = score(rs_out_dict, score_class)
        s_dict[k] = sum([v[-1] for v in score_dict.values()]) / len([v[-1] for v in score_dict.values()])
    return s_dict

def predict_labels(processed_dict, thres_mrg, thres_ret):
    df_cls = pd.DataFrame([])
    for _, df_data in processed_dict.items():
        # Select
        pred_cls_aux = pd.Series(0, index=df_data.index, name='pred')
        idx_l = ((df_data['ret'] > thres_ret) & (df_data['fair_margin'] > thres_mrg) &
                (df_data['ret'] * df_data['fair_margin'] > 0))
        idx_s = ((df_data['ret'] < -thres_ret) & (df_data['fair_margin'] < -thres_mrg) &
                (df_data['ret'] * df_data['fair_margin'] > 0))
        pred_cls_aux[idx_l] = 1
        pred_cls_aux[idx_s] = -1
    
        if df_cls.empty:
            df_cls = df_data
        else:
            df_cls = pd.concat([df_cls, df_data], axis=0)
    return df_cls

def prepare_model_trds_off(df_data_p, mkt, model, data_dict_, true_dict, tau, n, isEma):
    grouped = df_data_p.loc[:, mkt].groupby(df_data_p.index.date)
    price_dict = {date: group.dropna() for date, group in grouped if date in data_dict_['keys']}
    out_dict = {k: [] for k in data_dict_['keys']}
    for dt, _ in price_dict.items():
        # Train model
        X_train, y_train = [data_dict_['train'][dt][k] for k in ['X', 'y']]
        model.fit(X_train, y_train)
        # Data
        # Original y
        y_original = true_dict[dt]['y']
        # Data trades
        Xp_dict = data_dict_['tests'][dt]['X_p']
        X_tests = Xp_dict['x'].reshape(-1, 1)
        # Testing and rescale
        y_pred_s = model.predict(X_tests)
        y_pred = rescale_data_reg(y_original, y_pred_s, tau, n, isEma)
        # Transform to prices
        price_pred = np.exp(y_pred) * Xp_dict['t_y']
        # Write to out_dict
        out_dict[dt] = {'index': Xp_dict['index'], 'price': price_pred, 'ret': y_pred_s}
    return out_dict

def data_process_single_ret_n(df_data_p, mkt, tau, tau_ema, df_data_v=None,
                            diff_bool=True, vol_bool=False, km_bool=False):
    if df_data_v is None:
        df_data_v = pd.DataFrame(np.ones(df_data_p.shape), index=df_data_p.index, columns=df_data_p.columns)
        df_data_v = df_data_v.where(~df_data_p.isna(), other=np.nan)
    preds_var = [x for x in df_data_p.columns]
    # Output dictionary
    out_dict = {k: {} for k in preds_var}
    # Ticks
    data_aux = tick_data(df_data_p, df_data_v, mkt, tau, tau_ema)
    vol_cols = [k + '_v' for k in df_data_v.columns]
    df_vol = data_aux.loc[:, vol_cols]
    data_aux = data_aux.loc[:, df_data_p.columns]
    grouped = data_aux.groupby(data_aux.index.date)
    data_dict = {date: group for date, group in grouped}
    trds_dict = {date: group for date, group in df_data_p.groupby(df_data_p.index.date)}
    for n in preds_var:
        pred_var = [x for x in df_data_p.columns if x == n]
        regs_var = [x for x in df_data_p.columns if x != n]
        df_ret = pd.DataFrame([])
        df_price = pd.DataFrame([])
        for date, data in data_dict.items():
            if km_bool:
                data_s, data_p = price_process_km(data)
            else:
                data_s, data_p = data, None
            df_aux = data_process_mdl(trds_dict[date], data, data_s, data_p,
                                    pred_var, regs_var, km_bool)
            # Differentiate
            y_series = data_s.loc[:, n].shift(periods=0).dropna()
            data_s = data_s.reindex(y_series.index)
            data_s.loc[:, n] = y_series
            if diff_bool:
                ret_aux = np.log(data_s.ffill()).diff()
                # price_aux = data.reindex(data_s.index).ffill()
            else:
                ret_aux = data_s.dropna()
                # price_aux = data.reindex(data_s.index).dropna()
            df_ret = pd.concat([df_ret, ret_aux])
            df_price = pd.concat([df_price, df_aux])
        df_ret = df_ret.dropna()
        df_price = df_price.dropna()
        #
        if vol_bool:
            df_data = pd.concat([df_ret, df_vol.reindex(df_ret.index)], axis=1)
            regs_var.extend([x for x in df_vol.columns])
        else:
            df_data = df_ret
        # Model
        y = df_data.loc[:, pred_var].values.reshape(-1,)
        X = df_data.loc[:, regs_var].values.reshape(-1,len(regs_var))
        # y_p = df_price.loc[:, pred_var].values.reshape(-1,)
        # X_p = df_price.loc[:, regs_var].values.reshape(-1,len(regs_var))
        # X, y = KFSmoother(X, y)
        out_dict[n]['y'] = y
        out_dict[n]['X'] = X
        # out_dict[n]['y_p'] = y_p
        # out_dict[n]['X_p'] = X_p
        out_dict[n]['X_p'] = to_dict_xp(df_price)
        out_dict[n]['ts'] = df_ret.index
    return out_dict