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
        # Scale
        X_train_s, y_train_s, X_tests_s, y_tests_s = scale_data_reg(X_train, y_train, X_tests, y_tests, n, isEMA)
        # Write to dictionary
        scaled_dict['train'][d]['X'], scaled_dict['train'][d]['y'] = X_train_s, y_train_s
        scaled_dict['tests'][d]['X'], scaled_dict['tests'][d]['y'] = X_tests_s, y_tests_s
        scaled_dict['train'][d]['ts'] = data_dict['train'][d]['ts']
        scaled_dict['tests'][d]['ts'] = data_dict['tests'][d]['ts']
        scaled_dict['keys'].append(d)
    return scaled_dict


def rescale_out_dict(scaled_out_dict, true_dict, tau, n, isScaled, isEMA):
    if not isScaled:
        return out_dict
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
    for data in data_dict.values():
        data_aux = pd.DataFrame([])
        for m in data.columns:
            aux_ser = KFSmootherS(data.loc[:, m].dropna()).reindex(data.index)
            data_aux = pd.concat([data_aux, aux_ser], axis=1)
        data_aux.columns = data.columns
        data_sm = pd.concat([data_sm, data_aux])
    return data_sm


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


def data_process_single_ret(df_data_p, mkt, tau, tau_ema, df_data_v=None,
                            diff_bool=True, vol_bool=False, km_bool=False):
    if df_data_v is None:
        df_data_v = pd.DataFrame(np.ones(df_data_p.shape), index=df_data_p.index, columns=df_data_p.columns)
        df_data_v = df_data_v.where(~df_data_p.isna(), other=np.nan)
    agg_dict = {'index': 'first'}
    agg_dict.update({k: 'sum' for k in df_data_p.columns})
    agg_dict.update({k + '_v': 'sum' for k in df_data_p.columns})
    ti_cls = TR_class(tau, tau_ema)
    # preds_var = [x for x in df_data_p.columns if x != mkt]
    preds_var = [x for x in df_data_p.columns]
    # Output dictionary
    out_dict = {k: {} for k in preds_var}
    # Indices based on ticks
    idx_series = ti_cls.tick_imbalance_indices(df_data_p.loc[:, mkt])
    # Create returns
    data_vw = pd.concat([df_data_p * df_data_v, df_data_v], axis=1)
    data_vw.columns = list(agg_dict.keys())[1:]
    vol_cols = [k + '_v' for k in df_data_v.columns]
    data_aux = pd.concat([data_vw.reindex(idx_series.index), idx_series], axis=1).reset_index()
    data_aux = data_aux.groupby(0).agg(agg_dict).set_index('index')
    # Back to vwp
    for col in df_data_p.columns:
        data_aux.loc[:, col] /= data_aux.loc[:, col + '_v']
    df_vol = data_aux.loc[:, vol_cols]
    data_aux = data_aux.loc[:, df_data_p.columns]
    grouped = data_aux.groupby(data_aux.index.date)
    data_dict = {date: group for date, group in grouped}
    for n in preds_var:
        pred_var = [x for x in df_data_p.columns if x == n]
        regs_var = [x for x in df_data_p.columns if x != n]
        df_ret = pd.DataFrame([])
        for data in data_dict.values():
            if km_bool:
                data = price_process_km(data)
            y_series = data.loc[:, n].shift(periods=0).dropna()
            data = data.reindex(y_series.index)
            data.loc[:, n] = y_series
            if diff_bool:
                ret_aux = np.log(data.ffill()).diff()
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
        # X, y = KFSmoother(X, y)
        out_dict[n]['y'] = y
        out_dict[n]['X'] = X
        out_dict[n]['ts'] = df_ret.index
    return out_dict


def split_data(data_dict_, date_range_dict, n_test):
    out_dict = {k: {'train': {}, 'tests': {}, 'keys': []} for k in data_dict_.keys()}
    date_s = {k: (v[-n_test], v[-1]) for k, v in date_range_dict.items()}
    for m, data in data_dict_.items():
        y_ser = pd.Series(data['y'], index=data['ts'])
        X_df = pd.DataFrame(data['X'], index=data['ts'])
        for d, date_tuple in date_s.items():
            date_test, date_end = date_tuple
            date_end += pd.Timedelta(hours=24)
            date = date_test.date()
            out_dict[m]['train'][date] = {}
            out_dict[m]['tests'][date] = {}
            y_train, y_tests = y_ser.loc[:date_test], y_ser.loc[date_test:date_end]
            X_train, X_tests = X_df.loc[:date_test, :], X_df.loc[date_test:date_end, :]
            # Train
            out_dict[m]['train'][date]['y'] = y_train.values
            out_dict[m]['train'][date]['X'] = X_train.values
            out_dict[m]['train'][date]['ts'] = y_train.index
            # Tests
            out_dict[m]['tests'][date]['y'] = y_tests.values
            out_dict[m]['tests'][date]['X'] = X_tests.values
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
    x_ = KFSmootherSingle(data_ser.values)
    return pd.Series(x_, index=data_ser.index)


def KFSmootherDF(df_data):
    X = df_data.values
    X_ = np.empty(X.shape, dtype=np.float64)
    for n in range(X.shape[1]):
        x_ = X[:, n]
        X_[:, n] = KFSmootherSingle(x_)
    return pd.DataFrame(X_, index=df_data.index, columns=df_data.columns)


def KFSmoother(X, y):
    y_ = KFSmootherSingle(y)
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
    for x_ in x:
        beta, P = clf.step(x_, 1, beta, P)
        beta_list.append(beta)
    return np.array(beta_list)


# def calibration():
    


data_class = TPDataDa()
data_class.create_connection('OracleSQL')
data_class_pg = TPData()
data_class_pg.create_connection('PostgreSQL')
data_class_tp = TPDataDa()

mkt_list = ['de', 'de']
tenor_list = ['m', 'q']
tn_list = [1, 1]
prod = 'base'
venue_list = ['eex']
start_date = datetime(2024, 5, 2)
end_date = datetime(2024, 6, 28)

allwd_broker_ids = [1441]

sample_dates = pd.date_range(start_date, end_date, freq='B')

n = 16
n_t = 15
d_t = 1
date_range_dict = {k.date(): pd.date_range(k, periods=n, freq='B')
                   for k in sample_dates[:-n+1]}

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
agg_dict = {'price': 'sum', 'volume': 'sum', 'action': 'median',
            'broker_id': 'median', 'count': 'sum'}

for m, t, n, p_dates in zip(mkt_list, tenor_list, tn_list, product_date):
    df_tr = pd.DataFrame([])
    series = pd.Series(p_dates, index=dates)
    for p_d, ds in series.groupby(series).groups.items():
        bT = datetime.combine(ds[0], start_time)
        eT = datetime.combine(ds[-1], end_time)
        # Trades
        df_tr_aux = data_class.get_trades(m, t, venue_list, p_d, bT, eT, prod)
        # Filter by broker
        if not allwd_broker_ids:
            pass
        else:
            df_tr_aux = df_tr_aux[df_tr_aux['broker_id'].isin(allwd_broker_ids)]
        # Clean trades
        df_ba = data_class_pg.get_best_ob_data(m, t, venue_list, p_d, bT, eT, prod, None)
        if df_ba.empty:
            df_ba = data_class_tp.get_best_ob_data(m, t, venue_list, p_d, bT, eT, prod, None)
        df_ba = df_ba.rename(columns={'bidbestprice': 'b_price', 'askbestprice': 'a_price'})
        df_tr_aux = data_class.clean_trades(df_tr_aux, df_ba)
        try:
            df_tr_aux = df_tr_aux.between_time(start_time, end_time)
        except(TypeError):
            pass
        # Group trades
        df_tr_aux['count'] = 1
        df_tr_aux['price'] *= df_tr_aux['volume']
        df_tr_aux = df_tr_aux.groupby(df_tr_aux.index).agg(agg_dict)
        df_tr_aux['price'] /= df_tr_aux['volume']
        df_tr = pd.concat([df_tr, df_tr_aux])
        del df_tr_aux, df_ba
    tr_data_dict[m + t + str(n)] = df_tr

data_p = pd.concat({k: v['price'] for k, v in tr_data_dict.items()}, axis=1)
data_v = pd.concat({k: v['volume'] for k, v in tr_data_dict.items()}, axis=1)

# Model
tau = 10
tau_ema = 10
tau_scl = 50
burn = 50
n = 16
intercept0 = False
isScaled = True
isEMA = False
# FTRL params
lambda1=0
lambda2=0
alpha=0.7
beta=1.
# lambda1=.5
# lambda2=.5
# alpha=0.45
# beta=1

# Scoring
score_class = OnlineScoring('r2', burn=0, tau=200)

# Markets
mkt = 'deq1'

# Process data
# data_dict = data_process_single_ret(price_process_km(data_p), mkt, tau, tau_ema, None, True)
data_dict = data_process_single_ret(data_p, mkt, tau, tau_ema, None, True, km_bool=True)
split_dict = split_data(data_dict, date_range_dict, d_t)
# Scale
reg_data = scale_data_dict(split_dict[mkt], tau, n, isScaled, isEMA)
# Train & Test
# out_dict = linear_offline(reg_data, False)
out_dict = linear_online(reg_data, False, lambda1, lambda2, alpha, beta)
rs_out_dict = rescale_out_dict(out_dict, split_dict[mkt]['train'], tau, n, isScaled, isEMA)
score_dict = score(rs_out_dict, score_class)
print({d: v[-1] for d, v in score_dict.items()})
print(sum([v[-1] for v in score_dict.values()]) / len([v[-1] for v in score_dict.values()]))
