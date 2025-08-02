# -*- coding: utf-8 -*-
"""
Created on Wed Aug 30 15:23:07 2023

@author: Marek
"""

from datetime import datetime, time
import pandas as pd
import numpy as np
from Database.TPData import TPData
from Math.ti_class import TI_class, TR_class
import matplotlib.pyplot as plt

from sklearn.linear_model import LinearRegression


data_class = TPData()

# mkt_list = ['de', 'de', 'de', 'de', 'de', 'de', 'ttf', 'ttf', 'eua']
# tenor_list = ['m', 'm', 'q', 'q', 'w', 'y', 'da', 'm', 'dec']
# tn_list = [1, 2, 1, 2, 1, 1, 1, 1, 1]
mkt_list = ['de', 'de', 'ttf', 'eua']
tenor_list = ['m', 'q', 'm', 'dec']
tn_list = [1, 1, 1, 1]
prod = 'base'
venue_list = ['eex']
start_date = datetime(2025, 1, 2)
end_date = datetime(2025, 4, 30)
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
end_time = time(17, 30, 0)

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

"""
#param_list = [2, 4, 5, 7, 10, 15, 20, 25, 30, 50]
+

"#""
param_list = range(5,50)
r_dict = {k: np.nan for k in param_list}
pred_idx = 1
pred_var = [x for i, x in enumerate(data_p.columns) if i == pred_idx]
regs_var = [x for i, x in enumerate(data_p.columns) if i != pred_idx]

agg_dict = {'index': 'first'}
agg_dict.update({k: 'mean' for k in data_p.columns})

for param in param_list: 
    ti_cls = TI_class(param, 30 + param)
    #param_dict = ti_cls.tick_imbalance_params(data.iloc[:, 0])
    #ti_cls.plot_params(data.iloc[:, 0])
    idx_series = ti_cls.tick_imbalance_indices(data_p.iloc[:, 0])
    
    # Create returns
    data_aux = pd.concat([data_p.reindex(idx_series.index), idx_series], axis=1).reset_index()
    data_aux = data_aux.groupby(0).agg(agg_dict).set_index('index')
    grouped = data_aux.groupby(data_aux.index.date)
    data_dict = {date: group for date, group in grouped}
    df_ret = pd.DataFrame([])
    for data in data_dict.values():
        data.iloc[:, pred_idx] = data.iloc[:, pred_idx].shift(periods=-1)
        ret_aux = np.log(data.dropna()).diff()
        #ret_aux.iloc[:, 0] = ret_aux.iloc[:, 0].shift(periods=1)
        df_ret = pd.concat([df_ret, ret_aux])
        
    df_ret = df_ret.dropna()
    # Model
    y = df_ret.loc[:, pred_var].values.reshape(-1,1)
    X = df_ret.loc[:, regs_var].values.reshape(-1,len(regs_var))
    reg = LinearRegression().fit(X, y)
    r_dict[param] = reg.score(X, y)


param_list = range(5,50)
r_dict = {m: {m1: {k: np.nan for k in param_list} for m1 in data_p.columns if m1 != m} for m in data_p.columns}
for m in data_p.columns:
    pred_var = [x for x in data_p.columns if x == m]
    regs_var = [x for x in data_p.columns if x != m]
    
    agg_dict = {'index': 'first'}
    agg_dict.update({k: 'mean' for k in data_p.columns})
    for m1 in regs_var:
        for param1 in param_list:
            ti_cls = TI_class(param1 + 20, param1)
            #param_dict = ti_cls.tick_imbalance_params(data.iloc[:, 0])
            #ti_cls.plot_params(data.iloc[:, 0])
            idx_series = ti_cls.tick_imbalance_indices(data_p.loc[:, m1])
            
            # Create returns
            data_aux = pd.concat([data_p.reindex(idx_series.index), idx_series], axis=1).reset_index()
            data_aux = data_aux.groupby(0).agg(agg_dict).set_index('index')
            grouped = data_aux.groupby(data_aux.index.date)
            data_dict = {date: group for date, group in grouped}
            df_ret = pd.DataFrame([])
            for data in data_dict.values():
                data.loc[:, m] = data.loc[:, m].shift(periods=-1)
                ret_aux = np.log(data.dropna()).diff()
                #ret_aux.iloc[:, 0] = ret_aux.iloc[:, 0].shift(periods=1)
                df_ret = pd.concat([df_ret, ret_aux])
                
            df_ret = df_ret.dropna()
            # Model
            y = df_ret.loc[:, pred_var].values.reshape(-1,1)
            X = df_ret.loc[:, regs_var].values.reshape(-1,len(regs_var))
            reg = LinearRegression().fit(X, y)
            r_dict[m][m1][param1] = reg.score(X, y)
"""


def score_reg_t_params(data_p, mkt, param_list, tau_ema=20):
    #param_list = range(5,50)
    r_dict = {m: {k: np.nan for k in param_list} for m in data_p.columns}
    for m in data_p.columns:
        pred_var = [x for x in data_p.columns if x == m]
        regs_var = [x for x in data_p.columns if x != m]
        
        agg_dict = {'index': 'first'}
        agg_dict.update({k: 'mean' for k in data_p.columns})
        for param1 in param_list:
            ti_cls = TR_class(param1, tau_ema)
            #param_dict = ti_cls.tick_imbalance_params(data.iloc[:, 0])
            #ti_cls.plot_params(data.iloc[:, 0])
            idx_series = ti_cls.tick_imbalance_indices(data_p.loc[:, mkt])
            
            
            # Create returns
            data_aux = pd.concat([data_p.reindex(idx_series.index), idx_series], axis=1).reset_index()
            data_aux = data_aux.groupby(0).agg(agg_dict).set_index('index')
            grouped = data_aux.groupby(data_aux.index.date)
            data_dict = {date: group for date, group in grouped}
            df_ret = pd.DataFrame([])
            for data in data_dict.values():
                y_series = data.loc[:, m].shift(periods=-1).dropna()
                data = data.reindex(y_series.index)
                data.loc[:, m] = y_series
                ret_aux = np.log(data.ffill()).diff()
                #data.loc[:, m] = data.loc[:, m].shift(periods=-1)
                #ret_aux = np.log(data.dropna()).diff()
                #ret_aux.iloc[:, 0] = ret_aux.iloc[:, 0].shift(periods=1)
                df_ret = pd.concat([df_ret, ret_aux])
                
            df_ret = df_ret.dropna()
            # Model
            y = df_ret.loc[:, pred_var].values.reshape(-1,1)
            X = df_ret.loc[:, regs_var].values.reshape(-1,len(regs_var))
            reg = LinearRegression().fit(X, y)
            r_dict[m][param1] = reg.score(X, y)
    return r_dict


def score_reg_t_params_oc(data_p, mkt, param_list, tau_ema=20):
    #param_list = range(5,50)
    r_dict = {m: {k: np.nan for k in param_list} for m in data_p.columns}
    for m in data_p.columns:
        pred_var = [x for x in data_p.columns if x == m]
        regs_var = [x for x in data_p.columns if x != m]
        
        agg_dict_f, agg_dict_l = {'index': 'first'}, {'index': 'first'}
        agg_dict_f.update({k: 'first' for k in data_p.columns})
        agg_dict_l.update({k: 'last' for k in data_p.columns})
        for param1 in param_list:
            ti_cls = TI_class(param1, tau_ema)
            #param_dict = ti_cls.tick_imbalance_params(data.iloc[:, 0])
            #ti_cls.plot_params(data.iloc[:, 0])
            idx_series = ti_cls.tick_imbalance_indices(data_p.loc[:, mkt])
            
            # Create returns
            data_aux = pd.concat([data_p.reindex(idx_series.index), idx_series], axis=1).reset_index()
            data_aux_f = data_aux.groupby(0).agg(agg_dict_f).set_index('index')
            data_aux_l = data_aux.groupby(0).agg(agg_dict_l).set_index('index')
            grouped_f = data_aux_f.groupby(data_aux_f.index.date)
            grouped_l = data_aux_l.groupby(data_aux_l.index.date)
            data_dict = {g1[0]: np.log(g2[1] / g1[1]) for g1, g2 in zip(grouped_f, grouped_l)}
            df_ret = pd.DataFrame([])
            for data in data_dict.values():
                y_series = data.loc[:, m].shift(periods=-1).dropna()
                data = data.reindex(y_series.index)
                data.loc[:, m] = y_series
                df_ret = pd.concat([df_ret, data.dropna()])
                
            df_ret = df_ret.dropna()
            # Model
            y = df_ret.loc[:, pred_var].values.reshape(-1,1)
            X = df_ret.loc[:, regs_var].values.reshape(-1,len(regs_var))
            reg = LinearRegression().fit(X, y)
            r_dict[m][param1] = reg.score(X, y)
    return r_dict


def score_models_lr(data_p, tau, tau_ema):
    r_dict = {m: {k: np.nan for k in data_p.columns} for m in data_p.columns}
    
    agg_dict = {'index': 'first'}
    agg_dict.update({k: 'mean' for k in data_p.columns})
    ti_cls = TR_class(tau, tau_ema)
    for m in data_p.columns:
        preds_var = [x for x in data_p.columns if x != m]
        idx_series = ti_cls.tick_imbalance_indices(data_p.loc[:, m])
        r_dict[m][m] = ti_cls.corr_ticks(data_p.loc[:, m], idx_series, 1)
        
        # Create returns
        data_aux = pd.concat([data_p.reindex(idx_series.index), idx_series], axis=1).reset_index()
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
                ret_aux = np.log(data.ffill()).diff()
                #data.loc[:, m] = data.loc[:, m].shift(periods=-1)
                #ret_aux = np.log(data.dropna()).diff()
                #ret_aux.iloc[:, 0] = ret_aux.iloc[:, 0].shift(periods=1)
                df_ret = pd.concat([df_ret, ret_aux])
            df_ret = df_ret.dropna()
            # Model
            y = df_ret.loc[:, pred_var].values.reshape(-1,1)
            X = df_ret.loc[:, regs_var].values.reshape(-1,len(regs_var))
            reg = LinearRegression().fit(X, y)
            r_dict[m][n] = reg.score(X, y)
    return pd.DataFrame(r_dict)


tau = 50
tau_ema = 22
ti_cls = TR_class(tau, tau_ema)
r_dict = score_models_lr(data_p, tau, tau_ema)

tau_list = np.arange(46, 60, 2)
tau_ema_list = np.arange(30, 44, 2)
for tau in tau_list:
    for tau_ema in tau_ema_list:
        ti_cls = TR_class(tau, tau_ema)
        ti_cls.plot_relation(data_p, ['dem1', 'deq1'])

mkt = 'dem1'
for tau_ema in tau_ema_list:
    aux_dict = score_reg_t_params(data_p, mkt, np.arange(20, 52, 1), tau_ema)
    pd.DataFrame(aux_dict).plot(grid=True)
    plt.suptitle(f'tau_ema={tau_ema}, mkt={mkt}')
    

