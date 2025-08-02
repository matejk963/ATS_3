# -*- coding: utf-8 -*-
"""
Created on Thu Jan  4 14:37:29 2024

@author: krajcovic
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta, time
from Strategies.IceBergOrders_class import IceBergOrders as IBO
from Database.TPData import TPDataDa

data_class = TPDataDa()

mkt_list = ['de']
tenor_list = ['m']
tn1_list = [1]
tn2_list = [2]
prod = 'base'
venue_list = ['eex']

data_dict = {}
for month in range(11,12):
    data_dict[month] = {}
    try:
        for day in range(1,5):
            start_date = datetime(2023, month, day)
            end_date = datetime(2023, month, day)
            n_s = 2
            
            dates = pd.date_range(start_date, end_date, freq='B')
            product_date1 = [dates.shift(1, freq='B') if t == 'da' else
                            dates.shift(1, freq='D') if t == 'd' else
                            dates.shift(tn, freq='W-MON') if t == 'w' else
                            (dates + n_s * dates.freq).shift(tn, freq='2QS-Apr') if t in ['sum', 'win'] else
                            (dates + n_s * dates.freq).shift(tn, freq=t.upper() + 'S')
                            for t, tn in zip(tenor_list, tn1_list)]
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
            
            start_time = time(8, 0, 0)
            end_time = time(20, 0, 0)
            
            
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
                    # data_class.create_connection('PostgreSQL')
                    df_ba_aux = data_class.get_best_orders_data(m, t, p_d, bT, eT, prod,
                                                                pd_2)
                    if df_ba_aux.empty:
                        continue
                    df_ba_aux = df_ba_aux.between_time(start_time, end_time)
                    #df_ba_aux = data_class.filter_data(df_ba_aux, df_ba_aux['bidbestprice'], 20)
                    df_ba = pd.concat([df_ba, df_ba_aux])
                    # Trades
                    # data_class.create_connection('OracleSQL')
                    df_tr_aux = data_class.get_trades(m, t, venue_list, p_d, bT, eT, prod,
                                                    pd_2)
                    if df_tr_aux.empty:
                        continue
                    df_tr_aux = df_tr_aux.between_time(start_time, end_time)
                    df_tr_aux = data_class.filter_data(df_tr_aux, df_tr_aux['price'], 20)
                    df_tr = pd.concat([df_tr, df_tr_aux])
                    # Orders
                    # data_class.create_connection('OracleSQL')
                    df_ob_aux = data_class.get_orders_data(m, t, venue_list, p_d, bT, eT, prod,
                                                    pd_2)
                    df_ob_aux = df_ob_aux.between_time(start_time, end_time)
                    # df_ob_aux = data_class.filter_data(df_ob_aux, df_ob_aux['price'], 20)
                    df_ob = pd.concat([df_ob, df_ob_aux])
            if df_ba.empty or df_tr.empty:
                continue
            else:
                df_ba = df_ba.dropna()
                df_ba['mid'] = df_ba.mean(axis=1)
                
                trades = df_tr.loc[df_tr['broker_id']==14].copy()
                trades['datetime_seconds'] = trades.index.floor('S')
                grouped = trades.groupby('datetime_seconds')
                result = grouped['price'].nunique()>1
            
            multiple_prices = result[result].index
            
            day_aux_dict = {'trades': trades,
                            'ba': df_ba,
                            'multiple_prices': multiple_prices}
            data_dict[month][day] = day_aux_dict
    except:
        continue

best_orders = pd.DataFrame()
all_trades = pd.DataFrame()
for month in data_dict.keys():
    for day in data_dict[month].keys():
        if best_orders.empty:
            best_orders = data_dict[month][day]['ba']
        else:
            best_orders = pd.concat([best_orders, data_dict[month][day]['ba']])
        if all_trades.empty:
            all_trades = data_dict[month][day]['trades']
        else:
            all_trades = pd.concat([all_trades, data_dict[month][day]['trades']])
            
            
analyzer = IBO(best_orders, all_trades)
analyzer.prepare_data()

analyzer.group_and_analyze()
analyzer.analyze_orders()