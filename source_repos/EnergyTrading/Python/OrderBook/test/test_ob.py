#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Aug 26 15:21:20 2023

@author: marek
"""

from datetime import datetime
from Database.TPData import TPData, TPDataDa
from OrderBook.OrderBook import OrderBookSnaps
import pandas as pd

l_path = '//192.168.10.91/data/Data/orderbooks/base/'
# l_path = '/Volumes/data/Data/orderbooks/base/'


def load_ob(m, t, dt, p_d, bT, eT):
    ob_class = OrderBookSnaps(verbose=True)
    file_path = l_path + t.split('_')[0] + '/'
    file_name = m + '_' + t.split('_')[0] + '_' + p_d.strftime('%y%m%d') + '_' + dt.strftime('%y%m%d') + '.p'
    print('%s Loading OrderBook %d...' % (dt.strftime('%y-%m-%d'), 0))
    time_load = ob_class.import_data(file_path + file_name)
    print('OrderBook %d created in %d sec' % (0, time_load))
    # ob_class.LoB_truncate(thres_vol=1)
    return ob_class.LoB_select(bT, eT, freq=None)


mkt = 'de'
tenor = 'm'
prod = 'base'
venue_list = ['eex']
start_date1 = datetime(2025, 7, 1)
start_date2 = None
bT = datetime(2025, 6, 2, hour=8, minute=0, second=0)
eT = datetime(2025, 6, 2, hour=18, minute=0, second=57)

is_calc = False
is_db = True

if is_db:
    data_class = TPData()
    data_class.create_connection('PostgreSQL')
else:
    data_class = TPDataDa()

ts_s = datetime.now().timestamp()
ob_class = OrderBookSnaps(verbose=True)
if is_db:
    if is_calc:
        df_ord_data = data_class.get_orders_data(mkt, tenor, venue_list, start_date1,
                                                 bT, eT, prod, start_date2)
        
        LoB_dict, err_dict = ob_class.construct_data(df_ord_data)
    else:
        LoB_dict, time_list = load_ob(mkt, tenor, bT, start_date1, bT, eT)
        ob_class.update_data(LoB_dict, time_list)
else:
    df_ord_data = data_class.get_orders_data(mkt, tenor, venue_list, start_date1,
                                             bT, eT, prod, start_date2)
    ob_class.import_from_tp(df_ord_data)
ts_e = datetime.now().timestamp()
print(ts_e - ts_s)

# df_ba_data = data_class.get_best_orders_data(mkt, tenor, start_date1, bT, eT,
#                                              prod, start_date2)

# data_class = TPDataDa()
# df_ba_data1 = data_class.get_best_ob_data(mkt, tenor, venue_list, start_date1,
#                                           bT, eT, prod, start_date2)

ax = pd.concat([ob_class.best_bid_all, ob_class.best_ask_all], axis=1).plot()
# df_ba_data1.plot(ax=ax)
