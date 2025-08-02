# -*- coding: utf-8 -*-
"""
Created on Fri May 10 09:23:07 2024

@author: algouser
"""


from datetime import datetime, time, timedelta
from Database.TPData import TPData
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


def export_order_book(mkt, tenor, prod, venue_list, prod_date, date,
                      default_path):
    start_time = time(8, 0, 0)
    end_time = time(18, 0, 0)

    data_class = TPData()
    data_class.create_connection('PostgreSQL', path_name='z:\EnergyTrading\configDB.json')

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
    ob_class.clear()
    return err_dict


default_path = '//192.168.10.91/data/Data/orderbooks/'
mkt_list = ['de']
tenor_list = ['m', 'q', 'y']
prod = 'base'
venue_list = ['eex']
tn_dict = {'m': [1, 2, 3, 4],
           'q': [1, 2, 3, 4],
           'y': [1, 2]}

manual_bool = True
if manual_bool:
    start_date = datetime(2024, 5, 7)
    end_date = datetime(2024, 5, 9)
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
        print((m, t, prod, venue_list, p_d, dt))
        try:
            err_dict = export_order_book(m, t, prod, venue_list, p_d, dt,
                                     default_path)
            print('OK')
        except:
            print('Failed')