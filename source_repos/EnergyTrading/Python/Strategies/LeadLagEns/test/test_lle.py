# -*- coding: utf-8 -*-
"""
Created on Fri Sep  6 13:55:29 2024

@author: Marek
"""

from datetime import datetime, time
import pandas as pd
import numpy as np
from Math.lm_class import OnlineScoring
from Database.TPData import TPData, TPDataDa
from Math.ti_class import TR_class
from Strategies.LeadLagEns.lead_lag_ensamble import LMOnline, LMOffline, DataClass
from Utilities.excel_loaders import conn_out_xload


def data_process(df_data_p, tau, tau_ema, df_data_v=None, log_bool=True):
    agg_dict = {'index': 'first'}
    agg_dict.update({k: 'mean' for k in df_data_p.columns})
    ti_cls = TR_class(tau, tau_ema)
    # Indices based on ticks
    idx_series = ti_cls.tick_imbalance_indices(df_data_p.iloc[:, 0])
    # Create returns
    data_aux = pd.concat([df_data_p.reindex(idx_series.index), idx_series], axis=1).reset_index()
    data_aux = data_aux.groupby(0).agg(agg_dict).set_index('index')
    grouped = data_aux.groupby(data_aux.index.date)
    data_dict = {date: group for date, group in grouped}
    df_ret = pd.DataFrame([])
    for data in data_dict.values():
        y_series = data.shift(periods=0).dropna()
        data = data.iloc[:, 0].reindex(y_series.index)
        if log_bool:
            ret_aux = np.log(data.ffill()).diff()
        else:
            ret_aux = data.ffill().diff()
        if df_ret.empty:
            df_ret = ret_aux.dropna()
        else:
            df_ret = pd.concat([df_ret, ret_aux.dropna()])    
    return df_ret


def calc_vol(df_ret):
    grouped = df_ret.groupby(df_ret.index.date)
    data_dict = {date: group for date, group in grouped}
    vol_dict = {date: np.std(vals) for date, vals in data_dict.items()}
    return pd.Series(vol_dict)


def hilovol(data_p_, data_v_, mkt, quant=.6):
    log_bool = True
    # Expected size of candle
    tau = 25
    # EMA
    tau_ema = 25
    df_ret = data_process(data_p_.loc[:, [mkt]], tau, tau_ema, data_v_, log_bool)
    df_vol = calc_vol(df_ret)

    period_list = [3, 10, 21]
    name_list = ['s', 'm', 'h']
    ma_dict = {}
    ma_dict_ = {}
    for n, w in zip(name_list, period_list):
        ma_dict[n] = df_vol.shift(periods=1).rolling(window=w, min_periods=w).mean()
        ma_dict_[n] = df_vol.shift(periods=0).rolling(window=w, min_periods=w).mean()

    df_ma = pd.DataFrame(ma_dict).dropna()
    ma_dict = {m: v.reindex(df_ma.index) for m, v in ma_dict.items()}
    hilo_new = [False for x in df_vol.values]
    for n in name_list:
        diff_quant = (df_vol - df_ma[n]).quantile(quant)
        hilo_new = [True if (x > diff_quant) or b else False for x, b in zip((df_vol - df_ma[n]).values, hilo_new)]
    hilo_new_ser = pd.Series(hilo_new, index=df_vol.index)
    # Filter data
    true_dates = pd.to_datetime(hilo_new_ser[hilo_new_ser].index)
    idx = data_p_.index.normalize().isin(true_dates)
    # Filtered dates
    dates_fltr = pd.DatetimeIndex(hilo_new_ser[hilo_new_ser].index)
    return data_p_.loc[idx, :], data_v_.loc[idx, :], dates_fltr


data_class = TPData()
data_class.create_connection('OracleSQL')
data_class_pg = TPData()
data_class_pg.create_connection('PostgreSQL')
data_class_tp = TPDataDa()

mkt_list = ['de', 'de', 'de', 'de', 'ttf', 'ttf', 'eua']
tenor_list = ['m', 'q', 'm', 'y', 'm', 'da', 'dec']
tn_list = [1, 1, 2, 1, 1, 1, 1]
# mkt_list = ['ttf', 'eua']
# tenor_list = ['q', 'dec']
# tn_list = [2, 1]
prod = 'base'
venue_list = ['eex']
# start_date = datetime(2024, 6, 3)
start_date = datetime(2025, 3, 1)
end_date = datetime(2025, 4, 30)
dates_out = [x.date() for x in conn_out_xload()]

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
ba_data_dict = {m + t + str(n): [] for m, t, n in zip(mkt_list, tenor_list, tn_list)}
agg_dict = {'price': 'sum', 'volume': 'sum', 'action': 'median',
            'broker_id': 'median', 'count': 'sum', 'tradeid': 'first'}

for m, t, n, p_dates in zip(mkt_list, tenor_list, tn_list, product_date):
    df_tr, df_ba = pd.DataFrame([]), pd.DataFrame([])
    series = pd.Series(p_dates, index=dates)
    for p_d, ds in series.groupby(series).groups.items():
        bT = datetime.combine(ds[0], start_time)
        eT = datetime.combine(ds[-1], end_time)
        # Trades
        df_tr_aux = data_class.get_trades(m, t, venue_list, p_d, bT, eT, prod)
        # Filter by broker
        if not allwd_broker_ids or t == 'da':
            pass
        else:
            df_tr_aux = df_tr_aux[df_tr_aux['broker_id'].isin(allwd_broker_ids)]
        # Clean trades
        df_ba_aux = data_class_pg.get_best_ob_data(m, t, venue_list, p_d, bT, eT, prod, None)
        if df_ba_aux.empty:
            df_ba_aux = data_class_tp.get_best_ob_data(m, t, venue_list, p_d, bT, eT, prod, None)
        df_ba_aux = df_ba_aux.rename(columns={'bidbestprice': 'b_price', 'askbestprice': 'a_price'})
        df_tr_aux = data_class.clean_trades(df_tr_aux, df_ba_aux)
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
        df_ba = pd.concat([df_ba, df_ba_aux])
        del df_tr_aux, df_ba_aux
    tr_data_dict[m + t + str(n)] = df_tr
    ba_data_dict[m + t + str(n)] = df_ba

data_p_ = pd.concat({k: v['price'] for k, v in tr_data_dict.items()}, axis=1)
data_v_ = pd.concat({k: v['volume'] for k, v in tr_data_dict.items()}, axis=1)


#### Auxiliary ###
mkt_aux_list = ['ttf', 'ttf', 'eua']
tenor_aux_list = ['m', 'q', 'dec']
tn_aux_list = [1, 1, 1]

mid_data_dict = {m + t + str(n): [] for m, t, n in zip(mkt_aux_list, tenor_aux_list, tn_aux_list)}
# Auxiliary regressors
product_aux_date = [dates.shift(1, freq='B') if t == 'da' else
                    dates.shift(1, freq='D') if t == 'd' else
                    dates.shift(tn, freq='W-MON') if t == 'w' else
                    (dates + n_s * dates.freq).shift(tn, freq='2QS-Apr') if t in ['sum', 'win'] else
                    (dates + n_s * dates.freq).shift(tn, freq='YS') if t in ['dec'] else
                    (dates + n_s * dates.freq).shift(tn, freq=t.upper() + 'S')
                    for t, tn in zip(tenor_aux_list, tn_aux_list)]

for m, t, n, p_dates in zip(mkt_aux_list, tenor_aux_list, tn_aux_list, product_aux_date):
    df_ba = pd.DataFrame([])
    series = pd.Series(p_dates, index=dates)
    for p_d, ds in series.groupby(series).groups.items():
        bT = datetime.combine(ds[0], start_time)
        eT = datetime.combine(ds[-1], end_time)
        # OB data
        data_class.create_connection('PostgreSQL')
        df_ba_aux = data_class.get_best_ob_data(m, t, venue_list, p_d, bT, eT, prod, None, False)
        df_ba_aux = df_ba_aux.rename(columns={'bidbestprice': 'b_price', 'askbestprice': 'a_price'})
        try:
            df_ba_aux = df_ba_aux.between_time(start_time, end_time)
        except(TypeError):
            pass
        # Omit data from drop dates
        df_ba_aux['date'] = df_ba_aux.index.date
        df_ba_aux = df_ba_aux[~df_ba_aux['date'].isin(dates_out)].drop(columns='date')
        # Filter timestamps
        df_tr_aux = data_p_.loc[bT:eT, :]
        ts = df_tr_aux.index.union(df_ba_aux.index)
        df_ba_aux = df_ba_aux.reindex(ts).ffill().loc[df_tr_aux.index, :]
        df_ba = pd.concat([df_ba, df_ba_aux])
        del df_ba_aux, df_tr_aux
    mid_data_dict[m + t + str(n)] = .5 * (df_ba['b_price'] + df_ba['a_price'])

if mkt_aux_list:
    data_aux = pd.concat({k + '_aux': v for k, v in mid_data_dict.items()}, axis=1)
    # Merge
    data_p_ = pd.concat([data_p_, data_aux], axis=1)
#######

# Data properties
mkt = 'deq1'
mkt_l = ['dem1', 'dem2', 'dey1']
mkt_aux = [x + '_aux' for x in ['ttfm1', 'euadec1']]
# mkt = 'ttfq2'
# mkt_l = ['euadec1']
tau = 10
tau_ema = 15
n_ema = 16

diff_bool = True
vol_bool = False
scale_bool = True
isEma = False

tick_val = 200

km_bool = False

# Score
score_class = OnlineScoring('r2', burn=0, tau=200)

# Model params & class
intercept = False
lambda1=.2
lambda2=.0
alpha=17.8
beta=2.9

adaptive_l1 = False
norm_g = False

model_single = LMOnline(1, intercept, lambda1, lambda2, alpha, beta,
                        adaptive_l1, norm_g)
model_single = LMOffline(intercept)
# Data preparation
model_data = DataClass(mkt, tau, tau_ema, diff_bool, vol_bool, scale_bool,
                       isEma, n_ema)

df_ba = ba_data_dict[mkt]
# Hilo VOL
vol_filter = False
if vol_filter:
    n = 16
    quant = .6
    data_p, data_v, dates_fltr = hilovol(data_p_, data_v_, 'dem1', quant)
    date_range_dict = {k.date(): dates_fltr[i:i+n].difference(dates_out)
                       for i, k in enumerate(dates_fltr[:-n+1]) if k.date() not in dates_out}
    df_ba = df_ba.loc[df_ba.index.normalize().isin(dates_fltr), :]
else:
    n = 16
    data_p, data_v = data_p_, data_v_
    date_range_dict = {k.date(): pd.date_range(k, periods=n, freq='B').difference(dates_out)
                       for k in sample_dates[:-n+1] if k.date() not in dates_out}
    

data_dict = model_data.data_process_3(data_p, None, km_bool=km_bool, reg_aux=mkt_aux)
split_dict = model_data.split_data(data_dict, date_range_dict, d_t)
ba_dict, class_dict = model_data.prepare_class_data(df_ba, tick_val, cls_margin=.04)
ba_dict = {k: v for k, v in ba_dict.items() if k not in dates_out}
class_dict = {k: v for k, v in class_dict.items() if k not in dates_out}
# Loop for models
# for m in mkt_l:
#     # Scale
#     reg_data = model_data.scale_data_dict(split_dict[m])
#     out_dict = model_single.eval_model_data(reg_data)
#     rs_out_dict = model_data.rescale_out_dict(out_dict)
#     score_dict = model_single.score(rs_out_dict, score_class)
#     print(sum([v[-1] for v in score_dict.values()]) / len([v[-1] for v in score_dict.values()]))

#     pred_dict = model_data.prepare_model_trds(data_p, mkt, model_single, reg_data)
#     mdl_dict = model_data.process_model_mkt(ba_dict, class_dict, pred_dict)
#     tot_conf, conf_dict = model_data.conf_matrix(mdl_dict, 0.08, 1.4)
#     tot_acc, acc_dict = model_data.process_conf_matrix(tot_conf, conf_dict)
#     print((tot_acc, np.sum(tot_conf)))
#     print(pd.DataFrame({'n': {k: int(np.sum(v)) for k, v in conf_dict.items()},
#                         'acc': acc_dict, 'r2': {d: v[-1] for d, v in score_dict.items()}}))

pred_dict = {m: [] for m in mkt_l}
for m in mkt_l:
    # Scale
    reg_data = model_data.scale_data_dict(split_dict[m])
    out_dict = model_single.eval_model_data(reg_data)
    rs_out_dict = model_data.rescale_out_dict(out_dict)
    score_dict = model_single.score(rs_out_dict, score_class)
    print('Lag market: [%s] vs. Lead market: [%s] \n' % (mkt, m))
    print(sum([v[-1] for v in score_dict.values()]) / len([v[-1] for v in score_dict.values()]))

    pred_dict[m] = model_data.prepare_model_trds(data_p, mkt, model_single, reg_data)
    mdl_dict = model_data.process_model_mkt(ba_dict, class_dict, pred_dict[m])
    tot_conf, conf_dict = model_data.conf_matrix(mdl_dict, 0.08, 1.4, grouped=True)
    # agg_dict = {'index': 'first', 'b_price': 'first', 'a_price': 'first',
    #             'price': 'mean', 'ret': 'mean', 'fair_margin': 'mean', 'class': 'mean'}
    # mdl_dict = {k: v.reset_index().groupby('counter').agg(agg_dict).set_index('index')
    #             for k, v in mdl_dict.items()}
    # tot_conf, conf_dict = model_data.conf_matrix(mdl_dict, 0.01, 0.9)
    tot_acc, acc_dict = model_data.process_conf_matrix(tot_conf, conf_dict)
    print((tot_acc, np.sum(tot_conf)))
    print(pd.DataFrame({'n': {k: int(np.sum(v)) for k, v in conf_dict.items()},
                        'acc': acc_dict, 'r2': {d: v[-1] for d, v in score_dict.items()}}))
    print('\n\n')

mdl_dict = model_data.process_model_mkt_n(ba_dict, class_dict, pred_dict)

db_dict = model_data.process_model_db_n(pred_dict, tr_data_dict)
"""
test = mdl_dict[list(mdl_dict.keys())[0]].iloc[:, [0, 1, 2, -3]].dropna()
test_p = data_p.loc[test.index[0]:test.index[-1], mkt].dropna()

test_n = test.reindex(test.index.union(test_p.index)).iloc[:, -1].ffill().loc[test_p.index]

test_res = (test_p - test_n).abs()

test_res.median()
"""