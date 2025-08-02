#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Aug 22 14:23:19 2023

@author: marek
"""

from datetime import datetime, time
import pandas as pd
from Database.TPData import TPData, TPDataDa
import matplotlib.pyplot as plt
plt.ion()

import os

# Add your Oracle Client's bin directory to the PATH
oracle_client_bin_path = r'C:\oracle\instantclient_19_9'
os.environ['PATH'] = oracle_client_bin_path + ';' + os.environ['PATH']

# Now you can import and use libraries that rely on the updated PATH
import cx_Oracle

data_class = TPData()

mkt_list = ['de']
tenor_list = ['w']
tn1_list = [1]
tn2_list = []
prod = 'base'
# <<<<<<< Updated upstream
venue_list = ['eex']
start_date = datetime(2024, 9, 23)
end_date = datetime(2024, 9, 23)
# =======
# venue_list = ['eex'] * len(mkt_list)
# start_date = datetime(2023, 12, 10)
# end_date = datetime(2023, 12, 20)
# >>>>>>> Stashed changes
n_s = 2

dates = pd.date_range(start_date, end_date, freq='B')
product_date1 = [
        dates.shift(1, freq='B') if t == 'da' else
        dates.shift(1, freq='D') if t == 'd' else
        dates.shift(tn, freq='W-MON') if t == 'w' else
        (dates + n_s * dates.freq).shift(tn, freq='2QS-Apr') if t in ['sum', 'win'] else
        dates.shift(tn, freq='YS') if t in ['dec'] else
        (dates + n_s * dates.freq).shift(tn, freq=t.upper() + 'S')
        for t, tn in zip(tenor_list, tn1_list)
    ]
if not tn2_list:
    product_date2 = [None] * len(product_date1)
else:
    product_date2 = [dates.shift(1, freq='B') if t == 'da' else
                     dates.shift(1, freq='D') if t == 'd' else
                     dates.shift(tn, freq='W-MON') if t == 'w' else
                     (dates + n_s * dates.freq).shift(tn, freq='2QS-Apr') if t in ['sum', 'win'] else
                     (dates + n_s * dates.freq).shift(tn, freq=t.upper() + 'S')
                     for t, tn in zip(tenor_list, tn2_list)]

if not tn2_list:
    tn_list = [str(t1) for t1 in tn1_list]
else:
    tn_list = [str(t1) + '_' + str(t2) for (t1, t2) in zip(tn1_list, tn2_list)]

start_time = time(9, 0, 0)
end_time = time(17, 0, 0)


# df_ord_data = data_class.get_orders_data(mkt, tenor, venue_list, start_date,
#                                          bT, eT, prod)

ba_data_dict = {m + t + n: [] for m, t, n in zip(mkt_list, tenor_list, tn_list)}
tr_data_dict = {m + t + n: [] for m, t, n in zip(mkt_list, tenor_list, tn_list)}

for m, t, n, p1_d, p2_d in zip(mkt_list, tenor_list, tn_list, product_date1,
                               product_date2):
    df_ba = pd.DataFrame([])
    df_tr = pd.DataFrame([])
    df_ob = pd.DataFrame([])
    if p2_d is None:
        df_prod_dates = pd.DataFrame([p1_d], columns=dates).T
    else:
        df_prod_dates = pd.DataFrame([p1_d, p2_d], columns=dates).T
    for p_d, ds in df_prod_dates.groupby(0).groups.items():
        bT = datetime.combine(ds[0], start_time)
        eT = datetime.combine(ds[-1], end_time)
        if p2_d is None:
            pd_2 = None
        else:
            pd_2 = df_prod_dates.loc[ds[0], 1]
        # Bid Ask
        data_class.create_connection('PostgreSQL')
        df_ba_aux = data_class.get_best_ob_data(m, t,'eex', p_d, bT, eT, prod,
                                                    pd_2)
        df_ba_aux = df_ba_aux.between_time(start_time, end_time)
        #df_ba_aux = data_class.filter_data(df_ba_aux, df_ba_aux['bidbestprice'], 20)
        df_ba = pd.concat([df_ba, df_ba_aux])
        # Trades
        # data_class.create_connection('OracleSQL')
        # df_tr_aux = data_class.get_trades(m, t, venue_list, p_d, bT, eT, prod,
        #                                   pd_2)
        # df_tr_aux = df_tr_aux.between_time(start_time, end_time)
        # df_tr_aux = data_class.filter_data(df_tr_aux, df_tr_aux['price'], 20)
        # df_tr = pd.concat([df_tr, df_tr_aux])
        # Orders
        data_class.create_connection('PostgreSQL')
        df_ob_aux = data_class.get_orders_data(m, t, venue_list, p_d, bT, eT, prod,
                                          pd_2)
        df_ob_aux = df_ob_aux.set_index('datetime')
        df_ob_aux = df_ob_aux.between_time(start_time, end_time)
        # df_tr_aux = data_class.filter_data(df_tr_aux, df_tr_aux['price'], 20)
        df_ob = pd.concat([df_ob, df_ob_aux])
    fig, ax = plt.subplots(figsize=(10, 6))
    #df_ba.plot(ax=ax, grid=True)
    df_ba.plot(ax=ax, grid=True)
    # df_tr['price'].plot(style=".", grid=True)
    #ax.scatter(df_tr.index, df_tr['price'], s=df_tr['volume'] * 10, color='green',
    #           label='df_tr Scatter')
    ax.set_title('Combined Price and Trades Plot')
    ax.set_xlabel('Date')
    ax.set_ylabel('Price')
    ax.legend()  # Show legend
    plt.show()

    ba_data_dict[m + t + str(n)] = df_ba
    tr_data_dict[m + t + str(n)] = df_tr


# file_path = r'Z:\Data\Spot\Model\Inputs\ttf_da_20230701_20240801_ba.pickle'
# import pickle
# with open(file_path, 'wb') as f:
#     pickle.dump(ba_data_dict, f)
    
# file_path = r'Z:\Data\Spot\Model\Inputs\de_w2_20230701_20240801.pickle'
# import pickle
# with open(file_path, 'wb') as f:
#     pickle.dump(tr_data_dict, f)