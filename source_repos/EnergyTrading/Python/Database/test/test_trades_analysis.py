# -*- coding: utf-8 -*-
"""
Created on Thu Oct 19 13:24:08 2023

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

mkt_list = ['de']
tenor_list = ['m']
tn_list = [1]
prod = 'base'
venue_list = ['eex']
start_date = datetime(2024, 9, 1)
end_date = datetime(2024, 10, 18)
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
        df_tr_aux = df_tr_aux[(df_tr_aux['broker_id']==14) |
                              (df_tr_aux['volume']<=20)]
        df_tr = pd.concat([df_tr, df_tr_aux])
    df_tr = data_class.filter_data(df_tr, df_tr['price'], 20)
    df_tr = df_tr.groupby(df_tr.index).agg(agg_dict)
    tr_data_dict[m + t + str(n)] = df_tr

data_p = pd.concat({k: v['volume'] for k, v in tr_data_dict.items()}, axis=1)
trade_dict = {d: data_p.loc[data_p.index.date==d,:].squeeze()
              for d in pd.unique(data_p.index.date)}
volume_dict = {k: np.nan for k in trade_dict.keys()}
pop_list = []
for date, df in trade_dict.items():
    try:
        df.index = df.index.time
        df.iloc[:] = df.iloc[:].cumsum()
        volume_dict[date] = df.iloc[-1]
        df.iloc[:] /= df.iloc[-1]
    except(AttributeError):
        pop_list.append(date)
for date in pop_list:
    trade_dict.pop(date)
    volume_dict.pop(date)

# average
date_dict = {pd.date(): [] for pd in product_date[0].unique()}
[date_dict[pd.date()].append(d.date())for d, pd in zip(dates, product_date[0])]
m_lin_dict = {}
vol_avg_dict = {}
for p_d, d in date_dict.items():
    trade_dict_aux = {k: v for k, v in trade_dict.items() if k in d}
    avg_series = pd.DataFrame(trade_dict_aux).fillna(method='ffill').mean(axis=1)
    index = [datetime.combine(datetime.min.date(), i) for i in avg_series.index]
    index_diff = [(i - index[0]).seconds / (index[-1] - index[0]).seconds
                  for i in index]
    lin_time = pd.Series(index_diff, index=avg_series.index)
    mlin = pd.concat([avg_series, lin_time], axis=1)
    m_lin_dict[p_d] = (mlin.iloc[:, 0] - mlin.iloc[:, 1])
    if not trade_dict_aux:
        pass
    else:
        vol_avg_dict[p_d] = (sum([v for k, v in volume_dict.items() if k in d]) / 
                             len(trade_dict_aux.keys()))
pd.DataFrame(m_lin_dict).plot(grid=True)
