# -*- coding: utf-8 -*-
"""
Created on Thu Sep  7 11:06:46 2023

@author: Marek
"""

from datetime import datetime, time
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import norm
from Database.TPData import TPData
from Math.ti_class import TI_class, VI_class, TR_class

# import cx_Oracle

# try:
#     cx_Oracle.init_oracle_client(lib_dir=r"C:\Users\andrej\Downloads\instantclient_21_11")
# except:
#     pass

def ret_series(data_series, idx_series):
    df_ret = pd.DataFrame([])
    agg_dict = agg_dict = {'index': 'first', data_series.name: 'mean'}
    data_aux = pd.concat([data_series.reindex(idx_series.index), idx_series],
                         axis=1).reset_index()
    data_aux = data_aux.groupby(0).agg(agg_dict).set_index('index')
    grouped = data_aux.groupby(data_aux.index.date)
    data_dict = {date: group for date, group in grouped}
    for data in data_dict.values():
        ret_aux = np.log(data.fillna(method='ffill')).diff()
        df_ret = pd.concat([df_ret, ret_aux])
    return df_ret.dropna()


data_class = TPData()

mkt_list = ['de']
tenor_list = ['q']
tn_list = [1]
prod = 'base'
venue_list = ['eex']
start_date = datetime(2024, 5, 2)
end_date = datetime(2024, 7, 20)
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
data_v = pd.concat({k: v['volume'] for k, v in tr_data_dict.items()}, axis=1)

# Expected size of candle
tau = 10
# EMA
tau_ema = 10
ti_cls = TR_class(tau, tau_ema)
idx_series = ti_cls.tick_imbalance_indices(data_p.iloc[:, 0])
grouped = idx_series.groupby(idx_series).count()
#grouped.plot(kind='hist', bins=range(1, grouped.max(), int(grouped.max() / 50)))
print('mean: %s, median: %s ' % (grouped.mean(), grouped.median()))

# Calculate distribution of returns
ret = ret_series(data_p.iloc[:, 0], idx_series)
#ret.plot(kind='hist', bins=np.arange(ret.min()[0], ret.max()[0], ret.max()[0] / 50))
plt.figure()
plt.hist(ret, bins=50, density=True, alpha=0.6, color='g')
# Calculate mean and standard deviation
mu, std = ret.mean()[0], ret.std()[0]
skw, kur = ret.skew()[0], ret.kurtosis()[0]
x = np.linspace(ret.min()[0] - std, ret.max()[0] + std, 100)
p = norm.pdf(x, mu, std)
plt.plot(x, p, 'k', linewidth=2)
plt.show()

print('mean: %s, std: %s, skew: %s, curtosis: %s ' % (mu, std, skw, kur))

grouped = idx_series.groupby(idx_series.index.date).agg(['first', 'last'])
grouped = grouped.iloc[:, 1] - grouped.iloc[:, 0] + 1
print('mean: %s, median: %s ' % (grouped.mean(), grouped.median()))
ti_cls.plot_candles(data_p.iloc[:, 0], data_p.iloc[:, 0], volume_series=data_v.iloc[:, 0])
