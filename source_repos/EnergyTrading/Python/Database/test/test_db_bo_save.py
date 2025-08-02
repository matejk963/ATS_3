# -*- coding: utf-8 -*-
"""
Created on Mon Jul  1 11:19:05 2024

@author: Marek
"""

from datetime import datetime, time
from Database.TPData import TPData, TPDataDa
from Database.DB_reader import Database
from SynthSpread.spreadviewer_class import SpreadSingle
from OrderBook.OrderBook import OrderBookSnaps
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


def contract_name(market, tenor, n):
    relative_tenor = tenor + str(n)
    return market + relative_tenor


def instrument_key(market, tenor, venue):
    data_class = TPData()
    instid = data_class.instid_dict[market][venue]
    prodid = data_class.seqid_dict(data_class.com_dict[market])[tenor.upper()]
    return str(instid) + '_' + str(prodid)


def itemid(t, p_d):
    if p_d is None:
        return 0
    else:
        data_class = TPData()
        return data_class.calc_itemid(t, p_d)


def get_dataframe_old(ob_class, m, t, n, pd1):
    df_exp = pd.concat([ob_class.best_bid_all, ob_class.best_ask_all], axis=1)
    df_exp.index.name = 'datetime'
    df_exp.columns = ['bidbestprice', 'askbestprice']
    df_exp = data_class.process_best_orders(df_exp)
    df_exp['relativecontract'] = contract_name(m, t, n)
    df_exp['contractstartdate'] = pd1.date()
    current_timestamp = datetime.now()
    df_exp['upload_timestamp'] = current_timestamp
    df_exp = df_exp.reset_index()
    return df_exp[['datetime', 'relativecontract', 'contractstartdate',
                   'bidbestprice', 'askbestprice', 'upload_timestamp']]


def get_dataframe(ob_class, m, t, v, pd1, pd2):
    df_exp = pd.concat([ob_class.best_bid_all, ob_class.best_ask_all], axis=1)
    df_exp.index.name = 'datetime'
    df_exp.columns = ['bidbestprice', 'askbestprice']
    df_exp = data_class.process_best_orders(df_exp)
    df_exp['instkey'] = instrument_key(m, t, v)
    df_exp['firstsequenceitemid'] = itemid(t, pd1)
    df_exp['secondsequenceitemid'] = itemid(t, pd2)
    current_timestamp = datetime.now()
    df_exp['upload_timestamp'] = current_timestamp
    df_exp = df_exp.reset_index()
    return df_exp[['datetime', 'instkey', 'firstsequenceitemid', 'secondsequenceitemid',
                   'bidbestprice', 'askbestprice', 'upload_timestamp']]


def save_dataframe(df_exp):
    conn = Database()
    conn._connect()
    df_exp.to_sql('ba_price', conn.engine, schema='best_orders', if_exists='append', index=False)


n_s = 2
# mkt_list = ['de', 'de', 'de']
# tenor_list = ['m', 'm', 'm']
# tn1_list = [2, 3, 4]
# tn2_list = []
# prod = 'base'
# venue_list = ['eex'] * len(mkt_list)

mkt_list = ['de']
tenor_list = ['q', 'y']
prod = 'base'
venue_list = ['eex']
tn_dict = {'w': [1, 2],
           'm': [1, 2, 3, 4],
           'q': [2, 3, 4],
           'y': [1, 2]}

combinations = []
for mkt in mkt_list:
    for tenor in tenor_list:
        for tn in tn_dict[tenor]:
            combinations.append((mkt, tenor, tn))

mkt_list_ = [x[0] for x in combinations]
tenor_list_ = [x[1] for x in combinations]
tn1_list_ = [x[2] for x in combinations]
tn2_list_ = []
venue_list = ['eex'] * len(mkt_list_)

start_date = datetime(2024, 6, 1)
end_date = datetime(2024, 6, 30)

if not tn2_list_:
    tn_list = [str(t1) for t1 in tn1_list_]
else:
    tn_list = [str(t1) + '_' + str(t2) for (t1, t2) in zip(tn1_list_, tn2_list_)]

dates = pd.date_range(start_date, end_date, freq='B')

spread_class = SpreadSingle(mkt_list_, tenor_list_, tn1_list_, tn2_list_, venue_list)
product_date1 = spread_class.product_dates(dates, n_s, tn_bool=True)
product_date2 = spread_class.product_dates(dates, n_s, tn_bool=False)

start_time = time(8, 0, 0, 0)
end_time = time(18, 0, 0, 0)

data_class = TPData()
for k, ds in enumerate(dates):
    bT = datetime.combine(ds, start_time)
    eT = datetime.combine(ds, end_time)
    pd1_aux = [None if p is None else p[k] for p in product_date1]
    pd2_aux = [None if p is None else p[k] for p in product_date2]
    for i, (m, t, v, pd1, pd2) in enumerate(zip(mkt_list_, tenor_list_, venue_list,
                                                pd1_aux, pd2_aux)):
        # Order Book attributes
        ob_class = OrderBookSnaps(verbose=True)
        try:
            LoB, ts = load_ob(m, t, bT, pd1, bT, eT)
            ob_class.update_data(LoB, ts)
        except(FileNotFoundError):
            continue
        df_exp = get_dataframe(ob_class, m, t, v, pd1, pd2)
        save_dataframe(df_exp)
