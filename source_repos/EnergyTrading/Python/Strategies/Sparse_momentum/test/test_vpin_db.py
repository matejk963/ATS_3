# -*- coding: utf-8 -*-
"""
Created on Wed Jun  4 11:31:14 2025

@author: Marek
"""

import pandas as pd
from datetime import datetime, time
from Strategies.Sparse_momentum.ob_attributes import TR_attributes
from Database.TPData import TPData


def process_db(data_dict, trd_dict):
    out_dict = {}
    for m, df_data in data_dict.items():
        df_trd_all = trd_dict[m]
        df_trd_aux = df_trd_all.loc[df_data.index, 'tradeid']
        out_dict[m] = pd.concat([df_trd_aux, df_data], axis=1).sort_index()
    return out_dict


data_class = TPData()
data_class.create_connection('OracleSQL')

mkt_list = ['de']
tenor_list = ['m']
tn_list = [1]

prod = 'base'
venue_list = ['eex']
start_date = datetime(2025, 3, 1)
end_date = datetime(2025, 3, 25)

allwd_broker_ids = [1441]

sample_dates = pd.date_range(start_date, end_date, freq='B')

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
agg_dict = {'price': 'sum', 'volume': 'sum', 'action': 'median',
            'broker_id': 'median', 'count': 'sum', 'tradeid': 'first'}

for m, t, n, p_dates in zip(mkt_list, tenor_list, tn_list, product_date):
    df_tr = pd.DataFrame([])
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
        del df_tr_aux
    tr_data_dict[m + t + str(n)] = df_tr

data_p_ = pd.concat({k: v['price'] for k, v in tr_data_dict.items()}, axis=1)
data_v_ = pd.concat({k: v['volume'] for k, v in tr_data_dict.items()}, axis=1)

trAtt = TR_attributes([])
# Market
mkt_code_list = [m + t + str(tn) for m, t, tn in zip(mkt_list, tenor_list, tn_list)]

### VPIN ###
vol_bucket_dict = {'dem1': 20, 'dem2': 13, 'deq1': 12, 'dey1': 13}
bucket_n_list = [10, 20, 50, 100]
n_days = 3

vpin_dict = {}
for m in mkt_code_list:
    df_data_vpin = pd.concat([data_p_[m], data_v_[m]], axis=1).dropna()
    df_data_vpin.columns = ['price', 'volume']
    df_data_vpin.index.name = 'timestamp'
     
    df_vpin = pd.DataFrame()
    for n_buckets in bucket_n_list:
        df_aux = trAtt.vpin(df_data_vpin, vol_bucket_dict[m], n_buckets, n_days=n_days)
        df_aux.columns = ['vpin_' + str(n_buckets)]
        if df_vpin.empty:
            df_vpin = df_aux
        else:
            df_vpin = pd.concat([df_vpin, df_aux], axis=1)
    vpin_dict[m] = df_vpin

db_dict = process_db(vpin_dict, tr_data_dict)
pass