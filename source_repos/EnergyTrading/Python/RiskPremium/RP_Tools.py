# -*- coding: utf-8 -*-
"""
Created on Fri Aug 25 16:34:53 2023

@author: krajcovic
"""

import numpy as np
import pandas as pd

from abc import ABC, abstractmethod

"""
class Hedge
create object for calculation of hedge
for beta hedge "x" variable denotes hedging instrument
& "y" variable is hedged instrument
"""

class Hedge:
    """
    initiate with data dataframe of columns ["hedging instrument",
                                             "hedged instrument"]
    prices with date as index
    """
    def __init__(self, data, returns_in=False):
        self.__data = data.copy()
        self.__returns_in = returns_in
        # Check if DataFrame has two columns
        assert self.__data.shape[1] == 2, "DataFrame should have exactly two columns."
        
        # Check if the index is datetime
        assert isinstance(self.__data.index, pd.DatetimeIndex), "DataFrame index should be of datetime type."

    @property
    def data(self):
        df = self.__data
        df = df.sort_index()
        return df
    @property
    def returns_in(self):
        return self.__returns_in
    
    #log returns
    @property
    def _returns(self):
        df = self.data
        df = np.log(df/df.shift(1))
        return df.iloc[1:]
    @property
    def _input_data(self):
        if self.returns_in == False:
            df = self._returns
        else:
            df = self.data
        return df
    
    @property
    def _single_beta1(self):
        df = self._input_data
        return np.corrcoef(df.iloc[:,0],
                           df.iloc[:,1])[0][1] *\
            (np.std(df.iloc[:,1])/np.std(df.iloc[:,0]))
            
    @property
    def _single_beta0(self):
        df = self._input_data
        b1 = self._single_beta1
        return np.mean(df.iloc[:,1])-b1*np.mean(df.iloc[:,0])
    
    
    def rolling_beta(self, rol_window):
        df = self._input_data
        cor = df.iloc[:,0].rolling(rol_window).\
            corr(df.iloc[:,1])
        b1 = cor*(df.iloc[:,1].rolling(rol_window).std()/
                  df.iloc[:,0].rolling(rol_window).std())
        df = pd.DataFrame(pd.concat([b1, cor],axis=1))
        df.columns = ['beta', 'cor']
        return df
    
    
        
"""
MFR = marginal fuels ratio
MFR = marginal gas mwh cost/marginal coal mwh cost
"""
from Loaders.EikonSpot_class import EikonSpot as es
import datetime as dt

def MFR(sD, eD,com_list = ['gas', 'coal', 'eua'],
        tenor_list = ['M_1'],
        rel=True):
        tenor_list = [[tenor_list[0]] for a in range(len(com_list))]
        
        gas_o = es(com_list[0], sD, eD)
        gas_data = gas_o.fwd_df_rel(sD,eD,tenor_list[0],['base'])
        gas_data.columns = [com_list[0]]
        coal_o = es(com_list[1], sD, eD)
        coal_data = coal_o.fwd_df_rel(sD,eD,tenor_list[1],['base'])
        coal_data.columns = [com_list[1]]
        eua_o = es(com_list[2], sD, eD)
        eua_data = eua_o.fwd_df_rel(sD,eD,tenor_list[2],['base'])
        eua_data.columns = [com_list[2]]
        df = pd.concat([gas_data, coal_data, eua_data],
                       axis=1, join='inner')
        
        df['mfr'] = ((df['gas']+df['eua']*0.2)/
                     (df['coal']/8.14 + df['eua']*0.36))
        
        return df
 
# sD = dt.datetime(2020,1,1)
# eD = dt.date.today()
# df = MFR(sD, eD)

import matplotlib.pyplot as plt

def Plot2v2a(df, col1, col2):
    fig, ax1 = plt.subplots()

    # Plotting column 'A' on the primary y-axis
    ax1.plot(df.index, df[col1], color='b', label=col1)
    ax1.set_ylabel(col1, color='b')
    ax1.tick_params('y', colors='b')

    # Creating a secondary y-axis for column 'B'
    ax2 = ax1.twinx()
    ax2.plot(df.index, df[col2], color='r', label='B')
    ax2.set_ylabel(col2, color='r')
    ax2.tick_params('y', colors='r')

    # Setting the x-axis title
    ax1.set_xlabel('date')

    # Display the plot
    plt.show()
    
"""
Function for calcuation x days forward return
Default value is 7 days
"""
def calculate_return(date, dataframe, col1, col2, days_ahead=7):
    current_value = dataframe[col1].get(date)
    future_value = dataframe[col2].get(date + pd.Timedelta(days=days_ahead))
    
    # Check if either value is None (indicating it was not in the index)
    if current_value is None or future_value is None:
        return np.nan
    else:
    
        return (future_value - current_value) / current_value
    
"""
Get trade data from trayport database
tenor_list example = ['w', 'm', 'q']
tn_list example = [1,2,3] => front 1st, 2nd, 3rd contract for respective data in series
"""
from Database.TPData import TPData
try:
    cx_Oracle.init_oracle_client(lib_dir=r"C:\oracle\instantclient_19_9")
except:
    pass
def TP_trades_data(mkt_list, tenor_list, tn_list,
                   prod, venue_list, start_date, end_date, n_s=2):
    data_class = TPData()
    dates = pd.date_range(start_date, end_date, freq='B')
    product_date = [dates.shift(1, freq='B') if t == 'da' else
                    dates.shift(1, freq='D') if t == 'd' else
                    dates.shift(tn, freq='W-MON') if t == 'w' else
                    (dates + n_s * dates.freq).shift(tn, freq='2QS-Apr') if t in ['sum', 'win'] else
                    (dates + n_s * dates.freq).shift(tn, freq=t.upper() + 'S')
                    for t, tn in zip(tenor_list, tn_list)]


    start_time = dt.time(8, 0, 0)
    end_time = dt.time(18, 0, 0)

    bT = dt.datetime(2023, 8, 21, hour=8, minute=0, second=0)
    eT = dt.datetime(2023, 8, 21, hour=18, minute=0, second=0)

    tr_data_dict = {m + t + str(n): [] for m, t, n in zip(mkt_list, tenor_list, tn_list)}

    for m, t, n, p_dates in zip(mkt_list, tenor_list, tn_list, product_date):
        df_tr = pd.DataFrame([])
        series = pd.Series(p_dates, index=dates)
        for p_d, ds in series.groupby(series).groups.items():
            bT = dt.datetime.combine(ds[0], start_time)
            eT = dt.datetime.combine(ds[-1], end_time)
            # Trades
            data_class.create_connection('OracleSQL')
            df_tr_aux = data_class.get_trades(m, t, venue_list, p_d, bT, eT, prod)
            print(start_time, end_time)
            try:
                df_tr_aux = df_tr_aux.between_time(start_time, end_time)
                df_tr = pd.concat([df_tr, df_tr_aux])
            except:
                continue
            
            df_tr = data_class.filter_data(df_tr, df_tr['price'], 20)
        tr_data_dict[m + t + str(n)] = df_tr
    return tr_data_dict

"""
create df from trayport data dictionary
"""
from datetime import time
def vwap_from_tp_trades(tr_data_dict,
                         from_time = time(8,0,0),
                         to_time = time(18,0,0)):
    tp_dict = {}
    for key in tr_data_dict.keys():
        df = tr_data_dict[key]
        df = df.loc[((df.index.time>=from_time)&
                     (df.index.time<=to_time))].copy()
        dates = df.index.s
        result_daily = {date: (df.loc[df.index.normalize() == date, 'price']\
                               * df.loc[df.index.normalize() == date, 'volume']).sum()\
                        / df.loc[df.index.normalize() == date, 'volume'].sum() for date in dates}
        try:
            temp = pd.DataFrame(list(result_daily.items()), columns=['date', key[-2:]])
        except:
            temp = pd.DataFrame(list(result_daily.items()), columns=['date', str(key)])
        temp = temp.set_index('date')
        tp_dict[key] = temp
            
    return tp_dict


def ttf_intraweek_settle(ttf_dict, week_date):
    
    sun_date = week_date + dt.timedelta(days=6)
    dates = ttf_dict['ttfm1'].loc[(week_date-dt.timedelta(days=1)):
                                  (sun_date)].index.to_series()
    weights = dates.diff(-1).dropna().dt.days.values * (-1)
    val = sun_date-pd.to_datetime(dates.values[-1])
    weights = np.append(weights, val.days)
    
        
    if sun_date.day>29 or sun_date.month != week_date.month:
        df = ttf_dict['ttfm2']
    else:
        df = ttf_dict['ttfm1']
        
    df = df.loc[((df.index>=week_date) &
                 (df.index<=sun_date))].copy()
    out = np.dot(df.values.T,weights)[0]/np.sum(weights)
    return out

def gas_for_week(week_date, week_df, ttf_dict):
    sun_date = week_date + dt.timedelta(days=6)
    if sun_date.day>29 or sun_date.month != week_date.month:
        gas_df = ttf_dict['ttfm2']
        gas_df = gas_df.rename(columns={'m2': 'ttf'})
    else:
        gas_df = ttf_dict['ttfm1']
        gas_df = gas_df.rename(columns={'m1': 'ttf'})
        
    df = pd.concat([week_df, gas_df], axis=1, join='inner')
    
    return df
    

import refinitiv.data as rd
def ttf_settle_data(sD, eD):
    rd.open_session()
    ttf = rd.get_history(universe=['TFMBMc1', 'TFMBMc2'],
                          fields=['VWAP'],
                            interval='1D', 
                            start=sD,
                            end=eD)
    rd.close_session()
    ttf = ttf.tz_localize('UTC')
    ttf = ttf.tz_convert('Europe/Berlin')
    ttf = ttf.tz_localize(None)
    ttf.index = pd.to_datetime(ttf.index.date)
    ttf.columns = ['ttf_1', 'ttf_2']


    ttf['ttf_ret'] = np.where(ttf.index.day>23,
                              ttf.index.map(lambda x: calculate_return(x, ttf, 'ttf_2', 'ttf_2')),
                              ttf.index.map(lambda x: calculate_return(x, ttf, 'ttf_1', 'ttf_1')))
    return ttf


def percentile_rank(window):
    return (sum(window[:-1] < window[-1]) + 0.5*sum(window[:-1] == window[-1])) / len(window[:-1]) * 100

# Use the rolling method to create a rolling window and then use the apply method to calculate the percentile rank of the current value within each window

# def rp_from_single_weeks(weeks_dict,
#                          from_time = time(8,0,0),
#                          to_time = time(18,0,0))




# df = pd.read_csv(r'c:\Users\krajcovic\Documents\Trading\Spreads\temp\cgs.csv',
#                  parse_dates=['date'], dtype=float, index_col=0)
# df = df.iloc[:,:2].copy()
# o = Hedge(df)
# ret = o.rolling_beta1(rol_window=10)

#class PriceFetch(self, )
