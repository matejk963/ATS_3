# -*- coding: utf-8 -*-
"""
Created on Thu Apr 14 09:36:39 2022

@author: zelenaymar
"""

import pandas as pd
import numpy as np
from datetime import datetime, time
from SynthSpread.spreadviewer_class import SpreadSingle, SpreadViewerData, norm_coeff
from Database.TPData import TPData, TPDataDa
from Math.accumfeatures import EMA, MA, MSTD


def calc_ema(df_data, tau):
    mid_ser = .5 * (df_data.loc[:, 'bid'] + df_data.loc[:, 'ask'])
    mid_list = mid_ser.values
    dif_list = [0.001]
    dif_list.extend([abs(x - xl) for x, xl in zip(mid_list[1:], mid_list[:-1])])
    model = EMA(tau, mid_list[0])
    ema_list = [model.push(x, dx) for x, dx in zip(mid_list, dif_list)]
    return pd.Series(ema_list, index=mid_ser.index)


def calc_ema_m(df_data, tau, margin, w, eql_p):
    mid_ser = .5 * (df_data.loc[:, 'bid'] + df_data.loc[:, 'ask'])
    mid_list = mid_ser.values
    dif_list = [0.001]
    dif_list.extend([abs(x - xl) for x, xl in zip(mid_list[1:], mid_list[:-1])])
    model = EMA(tau, mid_list[0])
    ema_list = [model.push(x, dx) for x, dx in zip(mid_list, dif_list)]
    ema_list = [w * eql_p + (1 - w) * x for x in ema_list]
    bands = [[x - margin, x, x + margin] for x in ema_list]
    return pd.DataFrame(bands, index=mid_ser.index)


def adjust_trds(df_tr, df_em):
    timestamp = df_tr.index
    ts_new = df_em.index.union(timestamp)
    df_em = df_em.reindex(ts_new).ffill().reindex(timestamp)
    lb = df_em.iloc[:, 0]
    ub = df_em.iloc[:, 2]
    df_tr.loc[df_tr['buy'] > ub, 'buy'] = np.nan
    df_tr.loc[df_tr['sell'] < lb, 'sell'] = np.nan
    return df_tr.dropna(how='all')


n_s = 3
start_date = datetime(2024, 5, 15)
end_date = datetime(2024, 5, 29)
dates = pd.date_range(start_date, end_date, freq='B')
market = ['de']*2
tenor = ['w', 'w']
tn1_list = [1,2]
tn2_list = []
brk_list = ['eex']*2
mm_bool = [True]*2

tau = 5
margin = .43

start_time = time(9, 0, 0, 0)
end_time = time(17, 25, 0, 0)
gran = None
gran_s = '1h'
coeff_list = norm_coeff([1,1], market)

eql_p = -6.25
w = 0

add_trades = True
ob_data = False


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
if add_trades:
    data_class_tr = SpreadViewerData()
    data_class_tr.load_trades_otc(market, tenors_list, db_class,
                                  start_time=start_time, end_time=end_time)
    
sm_all = pd.DataFrame([])
tm_all = pd.DataFrame([])
for d in dates:
    d_range = pd.date_range(d, d)
    data_dict = spread_class.aggregate_data(data_class, d_range, n_s, gran=gran,
                                            start_time=start_time, end_time=end_time)
    sm = spread_class.spread_maker(data_dict, coeff_list, trade_type=['cmb', 'cmb']).dropna()
    
    sm_all = pd.concat([sm_all, sm], axis=0)
    
    # em = calc_ema_m(sm, tau, margin, w, eql_p)
    # sm = pd.concat([sm, em], axis=1)
    
    # ax = sm.plot(grid=True, legend=True, figsize=(34, 22), title=d.strftime('%Y/%B/%d-%a'))
    if add_trades:
        col_list=['bid', 'ask', 'volume', 'broker_id']
        trade_dict = spread_class.aggregate_data(data_class_tr, d_range, n_s, gran=gran_s,
                                                 start_time=start_time, end_time=end_time,
                                                 col_list=col_list, data_dict=data_dict)
        tm = spread_class.add_trades(data_dict, trade_dict, coeff_list, mm_bool)
        
        tm_all = pd.concat([tm_all, tm], axis=0)
        
        # tm_ = adjust_trds(tm, em)
        
        # tm_.plot(grid=True, legend=True, style='.', figsize=(36, 24),
        #          title=d.strftime('%Y/%B/%d-%a'), ax=ax)

em = calc_ema_m(sm_all, tau, margin, w, eql_p)
sm = pd.concat([sm_all, em], axis=1)

tm_ = adjust_trds(tm_all, em)

ax = sm.plot(grid=True, legend=True, figsize=(34, 22), title=d.strftime('%Y/%B/%d-%a'))
tm_.plot(grid=True, legend=True, style='.', figsize=(36, 24),
         title=d.strftime('%Y/%B/%d-%a'), ax=ax)
