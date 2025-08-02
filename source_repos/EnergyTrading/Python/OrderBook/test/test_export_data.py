# -*- coding: utf-8 -*-
"""
Created on Fri Oct 27 10:49:30 2023

@author: Marek
"""

from datetime import datetime, time, timedelta
from Database.TPData import TPData
from Database.DB_reader import Database
from OrderBook.OrderBook import OrderBookSnaps
import os
import itertools
import matplotlib.pyplot as plt
import pandas as pd


def previous_working_day(d):
    if d.weekday() == 0:  # Monday
        return d - timedelta(days=3)  # Previous Friday
    elif d.weekday() == 6:  # Sunday
        return d - timedelta(days=2)  # Previous Friday
    else:
        return d - timedelta(days=1)  # Previous day


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


def get_dataframe(ob_class, m, t, v, pd1, pd2):
    data_class = TPData()
    df_exp = pd.concat([ob_class.best_bid_all, ob_class.best_ask_all,
                        ob_class.best_bid_any, ob_class.best_ask_any], axis=1)
    df_exp.index.name = 'datetime'
    df_exp.columns = ['bidbestprice', 'askbestprice', 'bidbestprice_aonn', 'askbestprice_aonn']
    df_exp = data_class.process_best_orders(df_exp)
    df_exp['instkey'] = instrument_key(m, t, v)
    df_exp['firstsequenceitemid'] = itemid(t, pd1)
    df_exp['secondsequenceitemid'] = itemid(t, pd2)
    current_timestamp = datetime.now()
    df_exp['upload_timestamp'] = current_timestamp
    df_exp = df_exp.reset_index()
    return df_exp[['datetime', 'instkey', 'firstsequenceitemid', 'secondsequenceitemid',
                   'bidbestprice', 'askbestprice', 'upload_timestamp', 'bidbestprice_aonn', 'askbestprice_aonn']]

def save_dataframe(df_exp):
    conn = Database()
    conn._connect()
    df_exp.to_sql('ba_price', conn.engine, schema='best_orders', if_exists='append', index=False)


def export_order_book(mkt, tenor, prod, venue_list, prod_date, date,
                      default_path):
    start_time = time(8, 0, 0)
    end_time = time(18, 0, 0)

    data_class = TPData()
    data_class.create_connection('PostgreSQL')

    bT = datetime.combine(date, start_time)
    eT = datetime.combine(date, end_time)

    df_ord_data = data_class.get_orders_data(mkt, tenor, venue_list, prod_date,
                                             bT, eT, prod)
    ob_class = OrderBookSnaps(verbose=True)
    ob_class.clear()
    _, err_dict = ob_class.construct_data(df_ord_data)
    LoB_dict, ts_list = ob_class.LoB_select(bT, eT, start_time, end_time)
    ob_class.update_data(LoB_dict, ts_list)

    # Export data
    file_path = default_path + prod + '/' + tenor + '/'
    try:
        os.makedirs(file_path)
    except(OSError):
        pass
    sD_str = prod_date.strftime('%y%m%d')
    dt_str = date.strftime('%y%m%d')
    file_name = mkt + '_' + tenor + '_' + sD_str + '_' + dt_str
    ob_class.export_data(file_path, file_name + '.p')
    # Export graph
    file_path += 'figures/'
    fig_path = file_path + file_name + '.png'
    try:
        os.makedirs(file_path)
    except(OSError):
        pass
    fig = plt.figure()
    series_bid = ob_class.best_bid.between_time(start_time, end_time)
    series_ask = ob_class.best_ask.between_time(start_time, end_time)
    series_bid.plot(figsize=(12, 10), grid=True)
    series_ask.plot(figsize=(12, 10), grid=True)
    fig.savefig(fig_path)
    plt.close(fig)
    
    # Save bid asks
    venue = venue_list[0]
    df_exp = get_dataframe(ob_class, mkt, tenor, venue, prod_date, None)
    save_dataframe(df_exp)
    ob_class.clear()
    return err_dict


default_path = '//192.168.10.91/data/Data/orderbooks/'
mkt_list = ['ttf']
tenor_list = ['da']
prod = 'base'
venue_list = ['eex']
tn_dict = {'da': [1],
           'm': [1],
           'q': [1, 2, 3, 4],
           'y': [1, 2]}

manual_bool = True
if manual_bool:
    start_date = datetime(2024, 8, 19)
    end_date = datetime(2024, 8, 19)
else:
    prev_wday = previous_working_day(datetime.today().date())
    start_date = datetime.combine(prev_wday, time(0, 0))
    end_date = datetime.combine(prev_wday, time(0, 0))
    del prev_wday

n_s = 2
dates = pd.date_range(start_date, end_date, freq='B')

combinations = []
for mkt in mkt_list:
    for tenor in tenor_list:
        for tn in tn_dict[tenor]:
            combinations.append((mkt, tenor, tn))

mkt_list_ = [x[0] for x in combinations]
tenor_list_ = [x[1] for x in combinations]
tn_list_ = [x[2] for x in combinations]

product_date = [dates.shift(1, freq='B') if t == 'da' else
                dates.shift(1, freq='D') if t == 'd' else
                dates.shift(tn, freq='W-MON') if t == 'w' else
                (dates + n_s * dates.freq).shift(tn, freq='2QS-Apr') if t in ['sum', 'win'] else
                (dates + n_s * dates.freq).shift(tn, freq=t.upper() + 'S')
                for t, tn in zip(tenor_list_, tn_list_)]

for m, t, prod_d in zip(mkt_list_, tenor_list_, product_date):
    for dt, p_d in zip(dates, prod_d):
        print((m, t, prod, venue_list, p_d))
        try:
            err_dict = export_order_book(m, t, prod, venue_list, p_d, dt,
                                         default_path)
            print('OK')
        except:
            print('Failed')
