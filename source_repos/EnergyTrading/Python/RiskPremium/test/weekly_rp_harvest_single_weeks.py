# -*- coding: utf-8 -*-
"""
Created on Mon Sep  4 08:52:06 2023

@author: krajcovic
"""


from Database.TPData import TPData as tpd
from RiskPremium import RP_Tools as rpt
import Loaders.RLD_fetch as rf
from RiskPremium.RP_Tools import MFR, Plot2v2a, calculate_return,\
    TP_trades_data, ttf_settle_data, vwap_from_tp_trades, gas_for_week,\
        ttf_intraweek_settle
from Database import DB_reader as dbr
from Loaders import RLD_fetch as rldf

import refinitiv.data as rd


from Loaders.EikonSpot_class import EikonSpot as ES
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import datetime as dt
from datetime import time
import seaborn as sns
import refinitiv.data as rd
import pytz

from Database.TPData import TPData

import cx_Oracle

try:
    cx_Oracle.init_oracle_client(lib_dir=r"C:\oracle\instantclient_19_9")
except:
    pass


data_class = TPData()
data_class.create_connection('OracleSQL')

start_date = dt.datetime(2023,1,1)
end_date = dt.datetime(2023,9,1)

date_range = pd.date_range(start=start_date+dt.timedelta(days=7-start_date.weekday()),
                           end=end_date, freq='w')-dt.timedelta(days=6)

weeks_tp_dict = {}
for mon in date_range:
    product_date = mon
    eT = product_date-dt.timedelta(days=2)
    bT = eT - dt.timedelta(days=21)
    aux = data_class.get_trades('de', 'w', ['eex'],
                                product_date, bT, eT, 'base')
    weeks_tp_dict[mon] = aux

#spot data fetch
database = dbr.Database()
spot = database.getSpotPriceData(['de'], _from=start_date.strftime('%Y-%m-%d'),
                                 _to=end_date.strftime('%Y-%m-%d'))

spot = spot.resample('W').mean().iloc[1:]
spot.index = spot.index - dt.timedelta(days=6)
    
from_time = time(10,0,0)
to_time = time(18,0,0)  

weeks_dict = {}
for key in weeks_tp_dict.keys():
    temp = weeks_tp_dict[key]
    temp = temp.loc[((temp.index.time>=from_time)&
                 (temp.index.time<=to_time))].copy()
    dates = temp.index.normalize().unique()
    result_daily = {date: (temp.loc[temp.index.normalize() == date, 'price']\
                           * temp.loc[temp.index.normalize() == date, 'volume']).sum()\
                    / temp.loc[temp.index.normalize() == date, 'volume'].sum() for date in dates}
    temp = pd.DataFrame(list(result_daily.items()), columns=['date', 'week'])
    temp = temp.set_index('date')
    weeks_dict[key] = temp.copy()



rp_dict = {}

for key in weeks_dict.keys():
    temp = weeks_dict[key]
    temp['week'] = temp['week']/spot.loc[key].item() - 1
    rp_dict[key] = temp.copy()


#power RP without gas
for key in rp_dict.keys():
    temp = rp_dict[key]
    plt.figure(figsize=(15,10))
    plt.plot(temp['week'])
    plt.show()
    
mfr_df = MFR(start_date, end_date)

for key in rp_dict.keys():
    temp = rp_dict[key]
    # temp = temp.set_index('date')
    temp = pd.concat([temp, mfr_df],axis=1, join='inner')
    Plot2v2a(temp, 'week', 'mfr')
    
ttf_dict = TP_trades_data(['ttf', 'ttf'],
                     ['m', 'm'], [1,2], 'base',
                     ['eex'], start_date, end_date)  

ttf = vwap_from_tp_trades(ttf_dict, from_time=from_time)
    
# power RP with gas
rp2_dict = {}
for key in weeks_dict.keys():
    week_df = weeks_dict[key]
    df = gas_for_week(key, week_df, ttf)
    ttf_settle = ttf_intraweek_settle(ttf,
                                      key)
    spot_settle = spot.loc[key].item()
    
    df['week_rp'] = df['week']/spot_settle - 1
    df['ttf_rp'] = df['ttf']/ttf_settle - 1
    df['rp'] = df['week_rp'] - 2*df['ttf_rp']
    rp2_dict[key] = df.copy()
    
    
#power RP with gas
for key in rp2_dict.keys():
    temp = rp2_dict[key]
    plt.figure(figsize=(15,10))
    plt.plot(temp['rp'])
    plt.show()
    
for key in rp2_dict.keys():
    temp = rp2_dict[key]
    
    Plot2v2a(temp, 'week_rp', 'rp')
    
for key in rp2_dict.keys():
    temp = rp2_dict[key]
    # temp = temp.set_index('date')
    temp = pd.concat([temp, mfr_df],axis=1, join='inner')
    Plot2v2a(temp, 'rp', 'mfr')

rld_data = rldf.RLDDatabaseData()


#adding wa rld
rp_rld_dict = {}
for key in rp2_dict.keys():
    df = rp2_dict[key]
    wa = rld_data.getResWeekAhead(df.index[0],
                                  df.index[-1])
    wa.index.name = 'date'
    norm = rld_data.getResNormals(key, key+dt.timedelta(days=6)).mean().item()
    df = pd.concat([df[['mean']], wa], axis=1, join='inner')
    df['rld_norm'] = df['mean']/norm
    rp_rld_dict[key] = df
    