# -*- coding: utf-8 -*-
"""
Created on Tue Sep 12 08:15:08 2023

@author: krajcovic
"""

from datetime import datetime, time
import datetime as dt
import pandas as pd
import numpy as np
from Database.TPData import TPData
from Math.ti_class import TI_class

import cx_Oracle

try:
    cx_Oracle.init_oracle_client(lib_dir=r"C:\oracle\instantclient_19_9")
except:
    pass

def data_prep(start_date,end_date,
                 mkt_list=['de'], tenor_list=['w'], tn_list=[1],
                 prod='base', venue_list=['eex']):
    data_class = TPData()
    
    # mkt_list = ['de']
    # tenor_list = ['m']
    # tn_list = [1]
    # prod = 'base'
    # venue_list = ['eex']
    # start_date = datetime(2023, 6, 12)
    # end_date = datetime(2023, 9, 1)
    n_s = 2
    
    dates = pd.date_range(start_date, end_date, freq='B')
    product_date = [dates.shift(1, freq='B') if t == 'da' else
                    dates.shift(1, freq='D') if t == 'd' else
                    dates.shift(tn, freq='W-MON') if t == 'w' else
                    (dates + n_s * dates.freq).shift(tn, freq='2QS-Apr') if t in ['sum', 'win'] else
                    (dates + n_s * dates.freq).shift(tn, freq='YS') if t in ['dec'] else
                    (dates + n_s * dates.freq).shift(tn, freq=t.upper() + 'S')
                    for t, tn in zip(tenor_list, tn_list)]
    
    
    start_time = time(8, 0, 0)
    end_time = time(18, 0, 0)
    
    tr_data_dict = {m + t + str(n): [] for m, t, n in zip(mkt_list, tenor_list, tn_list)}
    agg_dict = {'price': 'mean', 'volume': 'sum', 'action': 'first', 'broker_id': 'first'}
    
    for m, t, n, p_dates in zip(mkt_list, tenor_list, tn_list, product_date):
        df_tr = pd.DataFrame([])
        series = pd.Series(p_dates, index=dates)
        for p_d, ds in series.groupby(series).groups.items():
            bT = datetime.combine(ds[0], start_time)
            eT = datetime.combine(ds[-1], end_time)
            # Trades
            data_class.create_connection('OracleSQL')
            df_tr_aux = data_class.get_trades(m, t, venue_list, p_d, bT, eT, prod)
            try:
                df_tr_aux = df_tr_aux.between_time(start_time, end_time)
            except(TypeError):
                pass
            #df_tr_aux = data_class.filter_data(df_tr_aux, df_tr_aux['price'], 20)
            df_tr = pd.concat([df_tr, df_tr_aux])
        df_tr = data_class.filter_data(df_tr, df_tr['price'], 20)
        df_tr = df_tr.groupby(df_tr.index).agg(agg_dict)
        tr_data_dict[m + t + str(n)] = df_tr
    
    data_p = pd.concat({k: v['price'] for k, v in tr_data_dict.items()}, axis=1)
    return data_p

def make_candles(tau, tau_ema, start_date,end_date,
                 mkt_list=['de'], tenor_list=['w'], tn_list=[1],
                 prod='base', venue_list=['eex']):
    data_p = data_prep(start_date, end_date)

    # # Expected size of candle
    # tau = 10
    # # EMA
    # tau_ema = 15
    ti_cls = TI_class(tau, tau_ema)
    # ti_cls.plot_candles(data_p.iloc[:, 0], data_p.iloc[:, 0])
    candles = ti_cls.make_candles(data_p.iloc[:, 0], data_p.iloc[:, 0])
    return candles

def tick_prop(tau, tau_ema, start_date, end_date):
    data_p = data_prep(start_date,end_date)
    ti_cls = TI_class(tau, tau_ema)
    idx_series = ti_cls.tick_imbalance_indices(data_p.iloc[:, 0])
    grouped = idx_series.groupby(idx_series).count()
    grouped.plot(kind='hist', bins=range(1, grouped.max(), int(grouped.max() / 50)))
    print('mean: %s, median: %s ' % (grouped.mean(), grouped.median()))

    grouped = idx_series.groupby(idx_series.index.date).agg(['first', 'last'])
    grouped = grouped.iloc[:, 1] - grouped.iloc[:, 0] + 1
    print('mean: %s, median: %s ' % (grouped.mean(), grouped.median()))
    # ti_cls.plot_candles(data_p.iloc[:, 0], data_p.iloc[:, 0])

def tick_index(tau, tau_ema, start_date, end_date):
    data_p = data_prep(start_date, end_date)
    ti_cls = TI_class(tau, tau_ema)
    idx_series = ti_cls.tick_imbalance_indices(data_p.iloc[:, 0])
    return idx_series

def calculate_max_drawdown(equity_line):
    if not equity_line:
        return 0.0, 0.0

    max_drawdown_percentage = 0.0
    max_drawdown_absolute = 0.0
    peak = equity_line[0]

    for equity in equity_line:
        if equity > peak:
            peak = equity
        drawdown_absolute = peak - equity
        drawdown_percentage = drawdown_absolute / peak

        max_drawdown_absolute = max(max_drawdown_absolute, drawdown_absolute)
        max_drawdown_percentage = max(max_drawdown_percentage, drawdown_percentage)

    return max_drawdown_percentage, max_drawdown_absolute

def lin_reg_da(lookback):

    pred_df = pd.DataFrame()
    for date in pd.date_range(start=start_date+dt.timedelta(days=lookback),
                              end=end_date):
        sT = date-dt.timedelta(days=lookback)
        
        train = df.loc[((pd.to_datetime(df.index.date)>=sT)&
                        (pd.to_datetime(df.index.date)<date))].copy()
        test = df.loc[pd.to_datetime(df.index.date)==pd.Timestamp(date)].copy()
        if train['rld'].empty:
            continue
        else:
            coefs = np.polyfit(train['rld'], train['de'],deg=1)
            test['de_pred'] = test['rld']*coefs[0] + coefs[1]
            if pred_df.empty:
                pred_df = test.copy()
            else:
                pred_df = pd.concat([pred_df, test])
        
    pred_df['error'] = (pred_df['de_pred']-pred_df['de'])**2
    return pred_df['error'].mean()**(1/2)
    # return pred_df

from sklearn.linear_model import LinearRegression
def lin_reg_wa(lookback, train_df, rld_ser, x_cols, y_col):
    df = train_df.copy()

    pred_df = pd.DataFrame()
    pred_list = []
    date_list = []
    temp = df.copy()
    temp.index = temp.index.date
    duplicated_dates = temp.index.duplicated(keep='first')
    df_unique_date = temp[~duplicated_dates]
    dates = pd.to_datetime(df_unique_date.index)
    for date in dates:
        try:
            sT = date-dt.timedelta(days=lookback)
                    
            train = df.loc[((pd.to_datetime(df.index.date)>=sT)&
                            (pd.to_datetime(df.index.date)<=date))].copy()
            test = df.loc[((pd.to_datetime(df.index.date)>=(date+dt.timedelta(days=7-date.weekday())))&
                           (pd.to_datetime(df.index.date)<=(date+dt.timedelta(days=13-date.weekday()))))].copy()
            rld_test = rld_ser.loc[date].copy()
            if train['rld'].empty:
                continue
            else:
                # coefs = np.polyfit(train['rld'], train['de'],deg=1)
                # de_pred = rld_test*coefs[0] + coefs[1]
                # pred_list.append(de_pred.mean())
                # date_list.append(date)
                model = LinearRegression()
                model.fit(train[x_cols], train[y_col])
                
        except:
            continue
    out_df = pd.DataFrame({'date': date_list,
                           'de_pred': pred_list})
    return out_df

def lin_reg_wa_opt(lookback,train_df,
                   for_optimization=False, mean=True):
    df = train_df.copy()
    pred_df = pd.DataFrame()
    temp = df.copy()
    temp.index = temp.index.date
    duplicated_dates = temp.index.duplicated(keep='first')
    df_unique_date = temp[~duplicated_dates]
    dates = pd.to_datetime(df_unique_date.index)
    for date in dates:
        sT = date-dt.timedelta(days=lookback)
        
        train = df.loc[((pd.to_datetime(df.index.date)>=sT)&
                        (pd.to_datetime(df.index.date)<=date))].copy()
        test = df.loc[((pd.to_datetime(df.index.date)>=(date+dt.timedelta(days=7-date.weekday())))&
                       (pd.to_datetime(df.index.date)<=(date+dt.timedelta(days=13-date.weekday()))))].copy()
        if train['rld'].empty:
            continue
        else:
            coefs = np.polyfit(train['rld'], train['de'],deg=3)
            test['de_pred'] = (test['rld']**3)*coefs[0] + (test['rld']**2)*coefs[1]+\
                test['rld']*coefs[2] + coefs[3]
            if mean == True:
                test = pd.DataFrame(test.mean(),columns=[date]).T
                if pred_df.empty:
                    pred_df = test.copy()
                else:
                    pred_df = pd.concat([pred_df, test])
            else:
                if pred_df.empty:
                    pred_df = test.reset_index(drop=True).copy()
                else:
                    pred_df = pd.concat([pred_df, test.reset_index(drop=True)])
        
    pred_df['error'] = (pred_df['de_pred']-pred_df['de'])**2
    if for_optimization == True:
        return pred_df['error'].mean()**(1/2)
    else:
        return pred_df
        
        
# df = train_df.copy()

# pred_df = pd.DataFrame()
# pred_list = []
# date_list = []
# temp = df.copy()
# temp.index = temp.index.date
# duplicated_dates = temp.index.duplicated(keep='first')
# df_unique_date = temp[~duplicated_dates]
# dates = pd.to_datetime(df_unique_date.index)
# for date in dates:
#     try:
#         sT = date-dt.timedelta(days=lookback)
                
#         train = df.loc[((pd.to_datetime(df.index.date)>=sT)&
#                         (pd.to_datetime(df.index.date)<=date))].copy()
#         test = df.loc[((pd.to_datetime(df.index.date)>=(date+dt.timedelta(days=7-date.weekday())))&
#                        (pd.to_datetime(df.index.date)<=(date+dt.timedelta(days=13-date.weekday()))))].copy()
#         rld_test = rld_ser.loc[date].copy()
#         if train['rld'].empty:
#             continue
#         else:
#             coefs = np.polyfit(train['rld'], train['de'],deg=1)
#             de_pred = rld_test*coefs[0] + coefs[1]
#             pred_list.append(de_pred.mean())
#             date_list.append(date)
#     except:
#         continue
# out_df = pd.DataFrame({'date': date_list,
#                        'de_pred': pred_list})

