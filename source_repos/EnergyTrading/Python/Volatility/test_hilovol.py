# -*- coding: utf-8 -*-
"""
Created on Thu Oct 24 09:13:36 2024

@author: Marek
"""

from datetime import datetime, time
import pandas as pd
import numpy as np
from Math.ti_class import TR_class
from Database.TPData import TPData
from Math.accumfeatures import MA, EMA

import cx_Oracle
try:
    cx_Oracle.init_oracle_client(lib_dir=r"C:\Users\andrej\Downloads\instantclient_21_11")
except:
    pass

def group_trades(df_trades):
    agg_dict = {'price': 'sum', 'volume': 'sum', 'count': 'sum'}
    df_trades = df_trades.sort_index()
    df_trades['count'] = 1
    df_trades['price'] *= df_trades['volume']
    df_trades = df_trades.groupby(df_trades.index).agg(agg_dict)
    df_trades['price'] /= df_trades['volume']
    return df_trades


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


def hilovol(data_p, quant=.6):
    log_bool = True
    # Expected size of candle
    tau = 25
    # EMA
    tau_ema = 25
    df_ret = data_process(data_p, tau, tau_ema, data_v, log_bool)
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
    # Filtered dates
    dates_fltr = pd.DatetimeIndex(hilo_new_ser[hilo_new_ser].index)
    return dates_fltr


data_class = TPData()
data_class.create_connection('OracleSQL')

mkt_list = ['de']
tenor_list = ['m']
tn_list = [1]
prod = 'base'
venue_list = ['eex']
start_date = datetime(2024, 1, 1)
end_date = datetime(2024, 11, 7)

allwd_broker_ids = [1441]

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
for m, t, n, p_dates in zip(mkt_list, tenor_list, tn_list, product_date):
    df_tr = pd.DataFrame([])
    series = pd.Series(p_dates, index=dates)
    for p_d, ds in series.groupby(series).groups.items():
        bT = datetime.combine(ds[0], start_time)
        eT = datetime.combine(ds[-1], end_time)
        # Trades
        try:
            df_tr_aux = data_class.get_trades(m, t, venue_list, p_d, bT, eT, prod)
        except:
            continue
        # Filter by broker
        if not allwd_broker_ids:
            pass
        else:
            df_tr_aux = df_tr_aux[df_tr_aux['broker_id'].isin(allwd_broker_ids)]
        df_tr_aux = group_trades(df_tr_aux)
        if df_tr.empty:
            df_tr = df_tr_aux
        else:
            df_tr = pd.concat([df_tr, df_tr_aux])
    tr_data_dict[m + t + str(n)] = df_tr

data_p = pd.concat({k: v['price'] for k, v in tr_data_dict.items()}, axis=1)
data_v = pd.concat({k: v['volume'] for k, v in tr_data_dict.items()}, axis=1)

# log_bool=True
# # Expected size of candle
# tau = 25
# # EMA
# tau_ema = 25
# df_ret = data_process(data_p, tau, tau_ema, data_v, log_bool)
# df_vol = calc_vol(df_ret)

# period_list = [3, 10, 21]
# name_list = ['s', 'm', 'h']
# ma_dict = {}
# ma_dict_ = {}
# for n, w in zip(name_list, period_list):
#     ma_dict[n] = df_vol.shift(periods=1).rolling(window=w, min_periods=w).mean()
#     ma_dict_[n] = df_vol.shift(periods=0).rolling(window=w, min_periods=w).mean()

# df_ma = pd.DataFrame(ma_dict).dropna()
# ma_dict = {m: v.reindex(df_ma.index) for m, v in ma_dict.items()}

# df_ma_ = pd.DataFrame(ma_dict_).dropna()
# ma_dict_ = {m: v.reindex(df_ma_.index) for m, v in ma_dict_.items()}

# pd.concat([df_vol, df_ma], axis=1).plot()


# hilo_list = [1 if (m > h) | (s > m) else 0 for s, m, h in zip(ma_dict['s'].values, ma_dict['m'].values, ma_dict['h'].values)]
# hilo_ser = pd.Series(hilo_list, index=df_ma.index)

# hilo_list_ = [1 if (m > h) | (s > m) else 0 for s, m, h in zip(ma_dict_['s'].values, ma_dict_['m'].values, ma_dict_['h'].values)]
# hilo_ser_ = pd.Series(hilo_list_, index=df_ma_.index)

# quant = .6
# hilo_new = [False for x in df_vol.values]
# for n in name_list:
#     diff_quant = (df_vol - df_ma[n]).quantile(quant)
#     hilo_new = [True if (x > diff_quant) or b else False for x, b in zip((df_vol - df_ma[n]).values, hilo_new)]
# hilo_new_ser = pd.Series(hilo_new, index=df_vol.index)

# diff_quant = (df_vol - df_ma['m']).quantile(quant)
# hilo_new = [1 if x > diff_quant else 0 for x in (df_vol - df_ma['m']).values]
# hilo_new_ser = pd.Series(hilo_new, index=df_vol.index)

quant = .6
dates_fltr = hilovol(data_p, quant)


pass