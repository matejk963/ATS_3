# -*- coding: utf-8 -*-
"""
Created on Wed Nov 29 17:40:24 2023

@author: Marek
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, time
import holidays
from SynthSpread.spreadviewer_class import SpreadSingle, SpreadViewerData, norm_coeff
from Database.TPData import TPData, TPDataDa
from Math.ti_class import TI_class, VI_class, TR_class
from Math.lm_class import kalman, LinearModel
from Math.accumfeatures import MA, MSTD, DifferentialEMA, DerivativeEMA
from Strategies.Market_making.model_class import simple_model
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


n_s = 3
start_date = datetime(2023, 7, 11)
end_date = datetime(2024, 7, 1)
dates_all = pd.date_range(start_date, end_date, freq='B')
date_list = [a for a in dates_all if a not in holidays.DE()]
start_date = min(date_list)
end_date = max(date_list)

trades_dict = {}
ba_dict = {}
df_dict = {}
for tn in [1]:
    # Create a date range
    dates = pd.date_range(start=start_date, end=end_date)
    market = ['de']
    tenor = ['m']
    tn1_list = [1]
    tn2_list = []
    brk_list = ['eex']
    mm_bool = [True, False]
    
    start_time = time(9, 0, 0, 0)
    end_time = time(17, 0, 0, 0)
    gran = None
    coeff_list = norm_coeff([1, -1], market)
    
    
    ob_data = True
    
    df_ba = pd.DataFrame([])
    df_tr = pd.DataFrame([])
    
    spread_class = SpreadSingle(market, tenor, tn1_list, tn2_list, brk_list)
    data_class = SpreadViewerData()
    db_class = TPDataDa()
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
    
    
    data_dict = spread_class.aggregate_data(data_class, dates, n_s, gran=gran,
                                            start_time=start_time, end_time=end_time)
    df_ba = spread_class.spread_maker(data_dict, coeff_list, trade_type=['cmb', 'cmb'])
    col_list=['bid', 'ask', 'volume']
    
    trade_dict = spread_class.aggregate_data(data_class_tr, dates, n_s, gran='1S',
                                             start_time=start_time, end_time=end_time,
                                             col_list=col_list, data_dict=data_dict)
    df_tr = spread_class.get_trades_otc(data_dict, trade_dict, coeff_list, mm_bool)
    
    data_p = df_tr['price']
    data_v = df_tr['volume']

    # Expected size of candle
    tau = 20
    # EMA
    tau_ema = 22
    ti_cls = TR_class(tau, tau_ema)
    idx_series = ti_cls.tick_imbalance_indices(data_p)
    grouped = idx_series.groupby(idx_series).count()
    
    # Calculate distribution of returns
    data = grouped_series(data_p, idx_series)
    ti_cls.plot_candles(data_p, data_p, volume_series=data_v,
                        mav=())
    
    
    X = data.iloc[:,0].values
    
    tau = 15
    N = 30
    value0 = data.iloc[0,0]
    
    model_std = simple_model(MSTD(tau, N), [tau / 2, N, 2, value0], 'mstd', burn=tau)
    model_ma = simple_model(MA(tau, N), [tau / 2, N, value0], 'ma', burn=tau)
    model_diff = simple_model(DifferentialEMA(tau, N), [5*tau, value0], 'diff', burn=tau)
    model_dt = simple_model(DerivativeEMA(tau, N), [10*tau, 1, 1, value0], 'dt', burn=tau)
    std = model_std.predict(X)
    ma = model_ma.predict(X)
    diff = model_diff.predict(X)
    dt = model_dt.predict(X)
    bands = np.asarray([[x[0] - 2*x[1], x[0], x[0] + 2*x[1]] for x in std])
    y_df = pd.DataFrame(bands, index=data.index)
    df = pd.concat([y_df, data], axis=1).iloc[:,-1]
    
    trades_dict[tn] = df_tr
    ba_dict[tn] = df_ba
    df_dict[tn] = df

# # model_dict = {k: simple_model(DerivativeEMA(tau, N), [k*tau, 1, .5, value0], 'dt', burn=tau)
# #               for k in [1, 5, 10, 20, 50]}
# # dt_dict = {k: v.predict(X) for k, v in model_dict.items()}
# # plt.figure()
# # pd.DataFrame(dt_dict).plot()

# model_dt = simple_model(DerivativeEMA(tau, N), [1*tau, 1, .5, value0], 'dt', burn=tau)
# dt = model_dt.predict(X)

# fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True)
# df.plot(ax=ax1)
# pd.Series(dt).plot(ax=ax2)

# def on_xlims_change(event_ax):
#     other_ax = ax2 if event_ax == ax1 else ax1
#     other_ax.set_xlim(event_ax.get_xlim())

# ax1.callbacks.connect('xlim_changed', on_xlims_change)

# plt.show()

# model_dt2 = simple_model(DerivativeEMA(tau, N), [1*tau, 2, 1, value0], 'dt', burn=tau)
# dt2 = model_dt2.predict(X)

# fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True)
# pd.Series(dt[1000:]).plot(ax=ax1)
# pd.Series(dt2[1000:]).plot(ax=ax2)

# def on_xlims_change(event_ax):
#     other_ax = ax2 if event_ax == ax1 else ax1
#     other_ax.set_xlim(event_ax.get_xlim())

# ax1.callbacks.connect('xlim_changed', on_xlims_change)

# plt.show()


# data_ = (y_df.iloc[:, 1] - data.iloc[:, 0]).dropna()
# X_data = data_.iloc[:-1].values.reshape(-1,1)
# y_data = data_.iloc[1:].values.reshape(-1,)

# alpha = 0.2
# beta = 1
# out_dict_lm = ftrl_regression(X_data, y_data, 0, 0, alpha, beta, True, False)

# # Estimated parameters
# theta_list = [1 - x[1] if 1 - x[1] > tol else tol for x in out_dict_lm['coeff']]
# mu_list = [x[0] / y for x, y in zip(out_dict_lm['coeff'], theta_list)]

# period_list = [np.log(4) / x for x in theta_list]

# fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True)
# pd.concat([pd.Series(X_data.reshape(-1,)), pd.Series(mu_list)], axis=1).plot(ax=ax1)
# pd.Series(period_list).plot(ax=ax2)

# def on_xlims_change(event_ax):
#     other_ax = ax2 if event_ax == ax1 else ax1
#     other_ax.set_xlim(event_ax.get_xlim())

# ax1.callbacks.connect('xlim_changed', on_xlims_change)

# plt.show()
