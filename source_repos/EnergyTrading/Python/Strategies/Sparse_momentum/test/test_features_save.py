#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed May 28 11:02:06 2025

@author: marek
"""

import pandas as pd
import pickle
from datetime import datetime, time
from Strategies.Sparse_momentum.ob_attributes import OB_attributes, TR_attributes
from Database.TPData import TPData
import numpy as np
from Database.TPData import TPData
from SynthSpread.spreadviewer_class import SpreadSingle
from Math.ti_class import TR_class
from OrderBook.OrderBook import OrderBookSnaps
from Strategies.LeadLagEns.lead_lag_ensamble import LMOnline, LMOffline, DataClass
from Utilities.excel_loaders import conn_out_xload


def class_stats(df_ba, data_p, tick_val):
    df_ba.reindex(df_ba.index.union(data_p_.index)).ffill().loc[data_p_.index, :].dropna()
    grouped = df_ba.groupby(df_ba.index.date)
    time_diffs = pd.Series()
    for d, df_data in grouped:
        idx, csum, ts = obAtt.calc_tick_index_pd(df_data, tick_val, 0.01)
        df_aux = pd.Series(idx, index=ts, name='idx')
        # Find where value changes
        change_points = df_aux[df_aux != df_aux.shift(1)]
        # Compute time differences between change points
        
        if time_diffs.empty:
            time_diffs = change_points.index.to_series().diff().dropna().dt.total_seconds() / 60
        else:
            time_diffs = pd.concat([time_diffs, change_points.index.to_series().diff().dropna().dt.total_seconds() / 60])
        # Now change_points contains the timestamps and values where idx changes
        # and time_diffs contains the seconds between those changes
    
    # Calculate and print statistics for the time_diffs series
    return time_diffs.describe()


data_class = TPData()
data_class.create_connection('OracleSQL')
data_class_pg = TPData()
data_class_pg.create_connection('PostgreSQL')


start_date = datetime(2025, 3, 1)
end_date = datetime(2025, 6, 23)
dates_out = [x.date() for x in conn_out_xload()]

dates = pd.date_range(start_date, end_date, freq='B')

n_s = 2

start_time = time(9, 0, 0)
end_time = time(18, 0, 0)

### Class ###
tick_val_list = [70, 70, 70, 100, 150]
cls_margin_list = [0.04, 0.06, 0.1, 0.1, 0.1]

### Fair Price Estimation ####
mkt_list = ['de', 'de', 'de', 'de']
tenor_list = ['m', 'q', 'm', 'y']
tn_list = [1, 1, 2, 1]

prod = 'base'
venue_list = ['eex']


allwd_broker_ids = [1441]

# Data properties
mkt = 'deq1'
mkt_l = ['ttfm1', 'ttfq1', 'euadec1']
mkt_aux = [x + '_aux' for x in ['ttfm1', 'ttfq1', 'euadec1']]
# mkt = 'ttfq2'
# mkt_l = ['euadec1']
tau = 14
tau_ema = 14

### LOAD DATA ###
dump_path = "C:\\Users\\krajcovic\\Documents\\Trading\\test_data\\algo\\lle_data_dq1_ens_20250301_20250623.pkl"
with open(dump_path, 'rb') as f:
    loaded_data = pickle.load(f)

data_p_ = loaded_data['data_p_']
data_v_ = loaded_data['data_v_']
ba_data_dict = loaded_data['ba_data_dict']
model_data = loaded_data['model_data']
db_data = loaded_data['db_data']
filtered_dict = loaded_data['filtered_dict']

df_ba = ba_data_dict[mkt]

class_dict = {}
for tick_val, cls_margin in zip(tick_val_list, cls_margin_list):
    ba_dict, class_dict_aux = model_data.prepare_class_data(df_ba, tick_val, cls_margin=cls_margin)
    if not class_dict:
        for k, v in class_dict_aux.items():
            v.columns = [f'class_{tick_val}_{cls_margin * 100:.0f}']
            class_dict[k] = v
    else:
        for k, v in class_dict_aux.items():
            v.columns = [f'class_{tick_val}_{cls_margin * 100:.0f}']
            class_dict[k] = pd.concat([class_dict[k], v], axis=1)
            

mdl_dict = model_data.process_model_mkt(ba_dict, class_dict_aux, filtered_dict)

#### Load OB data ####
l_path = '//192.168.10.91/data/Data/orderbooks/base/'


def load_ob(m, t, dt, p_d, bT, eT):
    ob_class = OrderBookSnaps(verbose=True)
    file_path = l_path + t.split('_')[0] + '/'
    file_name = m + '_' + t.split('_')[0] + '_' + p_d.strftime('%y%m%d') + '_' + dt.strftime('%y%m%d') + '.p'
    print('%s Loading OrderBook %d...' % (dt.strftime('%y-%m-%d'), 0))
    time_load = ob_class.import_data(file_path + file_name)
    print('OrderBook %d created in %d sec' % (0, time_load))
    # ob_class.LoB_truncate(thres_vol=1)
    return ob_class.LoB_select(bT, eT, freq=None)


def group_data(df_class, data_ob, data_tr, df_tr_gap, df_fair_reg, df_fair, df_vpin, df_dti):
    timestamp = data_tr.index
    # Merge together based on timestamp
    df_cl_aux = df_class.reindex(df_class.index.union(timestamp)).ffill().loc[timestamp, :]
    df_ob_aux = data_ob.reindex(data_ob.index.union(timestamp)).ffill().loc[timestamp, :]
    df_fr_aux = df_fair_reg.loc[timestamp, :]
    df_rt_aux = df_fair.loc[:, ['ret']].replace(0, np.nan).ffill().loc[timestamp, :]
    df_vp_aux = df_vpin.reindex(df_vpin.index.union(timestamp)).ffill().loc[timestamp, :]
    df_dti_aux = df_dti.reindex(df_dti.index.union(timestamp)).ffill().loc[timestamp, :]
    df_gap_aux = df_tr_gap.loc[timestamp, 'trd_gap']
    df_out = pd.concat([df_cl_aux, df_ob_aux, data_tr, df_fr_aux, df_rt_aux,
                        df_vp_aux, df_dti_aux, df_gap_aux], axis=1)
    return df_out


mkt_list = ['de']
tenor_list = ['y']
tn1_list = [1]
tn2_list = []
prod = 'base'
venue_list = ['eex']

gran = None

if not tn2_list:
    tn_list = [str(t1) for t1 in tn1_list]
else:
    tn_list = [str(t1) + '_' + str(t2) for (t1, t2) in zip(tn1_list, tn2_list)]

spread_class = SpreadSingle(mkt_list, tenor_list, tn1_list, tn2_list, venue_list)
product_date1 = spread_class.product_dates(dates, n_s, tn_bool=True)
product_date2 = spread_class.product_dates(dates, n_s, tn_bool=False)

run_dates = [d.date() for d in dates if d.date() in ba_dict.keys()]
product_date1 = [[pd for pd, d in zip(p_d, dates) if d.date() in ba_dict.keys()] for p_d in product_date1]


features_list = OB_attributes.attr_list()
depth_list = [0., .05, .08, .1, .15, .2, .25]
period_list = [5, 10, 50, 75]
ma_list = [10, 50, 100]
tick = 0.01
max_depth = max(depth_list) + 0.1

obAtt = OB_attributes(features_list)
 
tr_att_list = ['lamb_tr', 'trd_gap']
trAtt = TR_attributes(tr_att_list)
n_trades = 5
 
name_list = [m + t + tn for m, t, tn in zip(mkt_list, tenor_list, tn_list)]
 
vol_bucket_dict = {'dem1': 20, 'dem2': 13, 'deq1': 12, 'dey1': 13, 'dew1': 20}
 
 
class_ser = pd.Series([])
data_tr_dict = {d: v for d, v in data_p_.groupby(data_p_.index.date)}
 
df_data_vpin = pd.concat([data_p_[mkt], data_v_[mkt]], axis=1).dropna()
df_data_vpin.columns = ['price', 'volume']
df_data_vpin.index.name = 'timestamp'
 
### VPIN ###
bucket_n_list = [10, 20, 50, 100]
df_vpin = pd.DataFrame()
for n_buckets in bucket_n_list:
    df_aux = trAtt.vpin(df_data_vpin, vol_bucket_dict[mkt], n_buckets, n_days=3)
    df_aux.columns = ['vpin_' + str(n_buckets)]
    if df_vpin.empty:
        df_vpin = df_aux
    else:
        df_vpin = pd.concat([df_vpin, df_aux], axis=1)
 
data_vpin_dict = {d: v for d, v in df_vpin.groupby(df_vpin.index.date)}
 
df_data = pd.DataFrame()
for k, ds in enumerate(run_dates):
    variable_dict = {k: {} for k in range(len(name_list))}
    tr_dicts = {k: {} for k in range(len(name_list))}
    df_ba_day, df_class_day, df_trades = ba_dict[ds], class_dict[ds], data_tr_dict[ds]
    df_fair = pd.DataFrame(filtered_dict[ds]).set_index('index')
    df_fair.index.name = 'timestamp'
    ts_snap = df_trades.index
    bT = datetime.combine(ds, start_time)
    eT = datetime.combine(ds, end_time)
    pd1_aux = [None if p is None else p[k] for p in product_date1]
    pd2_aux = [None if p is None else p[k] for p in product_date2]
    # Fair price
    df_fair_reg = pd.DataFrame(trAtt.feature_trd_momentum(df_fair, ma_list)).set_index('timestamp')
    # VPIN
    df_vpin_reg = data_vpin_dict[ds]
    for i, (m, t, n, pd1, pd2) in enumerate(zip(mkt_list, tenor_list, tn_list,
                                                pd1_aux, pd2_aux)):
        # Order Book attributes
        ob_class = OrderBookSnaps(verbose=True)
        LoB, ts_ = load_ob(m, t, bT, pd1, bT, eT)
        ob_class.update_data(LoB, ts_)
        variable_dict[i] = obAtt.prepare_ob_data(ob_class.LoB_dict, depth_list)
        if i == 0:
            # Prepare main market
            idx, csum, ts = obAtt.calc_tick_index(variable_dict[i], ts_snap, None, 2.)
        data_ob = obAtt.prepare_reg_data_mkt(variable_dict[i], ts, idx,
                                             period_list, depth_list, gran, ts_data=ts)
        # Trades
        df_trd_aux = pd.DataFrame(df_trades.loc[:, m + t + n].dropna())
        df_trd_aux.columns = ['trd_price']
        df_trd_aux = pd.concat([df_trd_aux, trAtt.trade_side(df_trd_aux, df_ba_day)], axis=1)
        tr_dicts[i] = pd.concat([df_ba_day.reindex(df_trd_aux.index), df_trd_aux], axis=1)
        data_tr = trAtt.prepare_reg_data(tr_dicts[i], tr_dicts[i].index, ma_list, period_list)
        df_tr_momentum = trAtt.feature_trd_momentum(df_fair, ma_list)
        df_tr_gap = trAtt.aggregated_reg(tr_dicts[i])
        df_trd_aux.index.name = 'timestamp'
        df_dti = trAtt.calculate_dti_time(df_trd_aux, '300s')
        df_data_new = group_data(df_class_day, data_ob, data_tr, df_tr_gap, df_fair_reg, df_fair, df_vpin_reg, df_dti)
    if df_data.empty:
        df_data = df_data_new
    else:
        df_data = pd.concat([df_data, df_data_new])
# Dump path
dump_path = 'C:/data/lle/model_data_dey1_03_06.pkl'
 
# Write to file
with open(dump_path, 'wb') as f:
    pickle.dump({
        'df_data': df_data
    }, f)