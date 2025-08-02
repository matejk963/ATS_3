# -*- coding: utf-8 -*-
"""
Created on Wed Apr  3 11:29:46 2024

@author: Marek
"""

from datetime import datetime, time
from Database.TPData import TPData, TPDataDa
from OrderBook.OrderBook import OrderBookSnaps
from SynthSpread.spreadviewer_class import SpreadSingle
from Strategies.Sparse_momentum.ob_attributes import OB_attributes, TR_attributes, unify_time_pd
import pandas as pd
import matplotlib.pyplot as plt

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


def prepare_data(LoB_dicts, obAtt, timestamp, depth_list, period_list,
                 cls_margin, tick_val, gran=None):
    # Prepare raw data from OBs
    variable_dict = {k: {} for k in LoB_dicts.keys()}
    for i, LoB in LoB_dicts.items():
        variable_dict[i] = obAtt.prepare_ob_data(LoB, depth_list)
    # Prepare main market
    idx, csum, ts = obAtt.calc_tick_index(variable_dict[0], None, None, 1)
    data_cl = obAtt.prepare_class_data(variable_dict[0], csum, idx, tick_val,
                                       cls_margin, timestamp, gran)
    # Prepare regressors
    data_ob = pd.DataFrame()
    for data_dict in variable_dict.values():
        data_aux = obAtt.prepare_reg_data_mkt(data_dict, ts, idx, period_list,
                                              depth_list, ts_data=timestamp)
        data_ob = pd.concat([data_ob, data_aux], axis=1)
    data_cl = data_cl.reindex(data_ob.index)
    return pd.concat([data_cl, data_ob], axis=1)


def class_data_test(LoB_dict, timestamp, cls_margin, tick_val, gran=None):
    obSim = OB_attributes([])
    variable_dict = obSim.prepare_ob_data(LoB_dict, [0])
    # Prepare main market
    idx, csum, ts = obSim.calc_tick_index(variable_dict, None, None, 1)
    data_cl = obAtt.prepare_class_data(variable_dict, csum, idx, tick_val,
                                       cls_margin, timestamp, gran)
    # Bid Ask
    keys = ['a_price', 'b_price']
    df_data = pd.DataFrame(variable_dict).set_index(keys='timestamp').loc[:, keys]
    df_data = unify_time_pd(df_data, data_cl.index)
    # Plot Data
    df_data.plot()
    for i in range(len(df_data)):
        if data_cl.iloc[i, 0] == -1:
            plt.axvspan(df_data.index[i], df_data.index[i], color='red', alpha=0.5)
        elif data_cl.iloc[i, 0] == 1:
            plt.axvspan(df_data.index[i], df_data.index[i], color='green', alpha=0.5)
    return data_cl, df_data


n_s = 2
mkt_list = ['de']
tenor_list = ['m']
tn1_list = [1]
tn2_list = []
prod = 'base'
venue_list = ['eex']
start_date = datetime(2024, 6, 3)
end_date = datetime(2024, 6, 3)

if not tn2_list:
    tn_list = [str(t1) for t1 in tn1_list]
else:
    tn_list = [str(t1) + '_' + str(t2) for (t1, t2) in zip(tn1_list, tn2_list)]

dates = pd.date_range(start_date, end_date, freq='B')

spread_class = SpreadSingle(mkt_list, tenor_list, tn1_list, tn2_list, venue_list)
product_date1 = spread_class.product_dates(dates, n_s, tn_bool=True)
product_date2 = spread_class.product_dates(dates, n_s, tn_bool=False)

start_time = time(9, 0, 0, 0)
end_time = time(17, 25, 0, 0)

gran = None

is_db = False
is_tr = True

if is_db:
    data_class = TPData() 
else:
    data_class = TPDataDa()
data_class_tr = TPDataDa()

# features_list = ['ba_volrat', 'mid_priceW', 'bid_sparsity', 'ask_sparsity']
features_list = OB_attributes.attr_list()
depth_list = [0., .05, .1, .2, .3, .5, .9]
period_list = [5, 10, 50, 100]
tick = 0.01
tick_val = 150
cls_margin = 0.15
max_depth = max(depth_list) + 0.1
obAtt = OB_attributes(features_list)

name_list = [m + t + tn for m, t, tn in zip(mkt_list, tenor_list, tn_list)]
# for i, (m, t, n, p1_d, p2_d) in enumerate(zip(mkt_list, tenor_list, tn_list, 
#                                               product_date1, product_date2)):
#     if p2_d is None:
#         p2_d = [None] * len(p1_d)
#     for ds, pd1, pd2 in zip(dates, p1_d, p2_d):
#         bT = datetime.combine(ds, start_time)
#         eT = datetime.combine(ds, end_time)
#         ob_class = OrderBookSnaps(verbose=True)
#         if is_db:
#             LoB_dict, time_list = load_ob(m, t, bT, pd1, bT, eT)
#             ob_class.update_data(LoB_dict, time_list)
#         else:
#             df_ord_data = data_class.get_orders_data(m, t, venue_list, pd1,
#                                                      bT, eT, prod, pd2)
#             ob_class.import_from_tp(df_ord_data)
#         LoB_dict[i] = ob_class.LoB_dict
#     data_dict = obAtt.prepare_ob_data(ob_class.LoB_dict, depth_list)
#     idx, csum = obAtt.calc_tick_index(data_dict, None, None, 1, tick=tick)
#     class_ser = obAtt.prepare_class_data(data_dict, csum, idx,
#                                          tick_val, cls_margin)

class_ser = pd.Series([])
for k, ds in enumerate(dates):
    LoB_dicts = {k: {} for k in range(len(name_list))}
    tr_dicts = {k: {} for k in range(len(name_list))}
    bT = datetime.combine(ds, start_time)
    eT = datetime.combine(ds, end_time)
    pd1_aux = [None if p is None else p[k] for p in product_date1]
    pd2_aux = [None if p is None else p[k] for p in product_date2]
    for i, (m, t, n, pd1, pd2) in enumerate(zip(mkt_list, tenor_list, tn_list,
                                                pd1_aux, pd2_aux)):
        # Order Book attributes
        ob_class = OrderBookSnaps(verbose=True)
        if is_db:
            LoB, ts = load_ob(m, t, bT, pd1, bT, eT)
            ob_class.update_data(LoB, ts)
        else:
            data_class.create_connection('PostgreSQL')
            df_ord_data = data_class.get_orders_data(m, t, venue_list, pd1,
                                                     bT, eT, prod, pd2)
            ob_class.import_from_tp(df_ord_data)
            LoB, ts = ob_class.LoB_truncate(thres_val=max_depth, tp_bool=True)
            ob_class.update_data(LoB, ts)
        # Trades
        if is_tr:
            data_class_tr.create_connection('OracleSQL')
            tr_dicts[i] = data_class_tr.get_trades(m, t, venue_list, pd1, bT, eT,
                                                   prod)
        LoB_dicts[i] = ob_class.LoB_dict
        # data_dict = obAtt.prepare_ob_data(ob_class.LoB_dict, depth_list)
        # idx, csum, _ = obAtt.calc_tick_index(data_dict, None, None, 1)
        # class_ser_aux = obAtt.prepare_class_data(data_dict, csum, idx,
        #                                          tick_val, cls_margin)
        # class_ser = pd.concat([class_ser, class_ser_aux.iloc[:, 0]])
    ts = OB_attributes.unify_timestamp(tr_dicts, gran, None)
    data_ob = prepare_data(LoB_dicts, obAtt, ts, depth_list, period_list,
                           cls_margin, tick_val, gran)
    data_cls, data_ba = class_data_test(LoB_dicts[0], ts, cls_margin, tick_val, gran)
    
    
    
