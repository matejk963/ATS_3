# -*- coding: utf-8 -*-
"""
Created on Thu Sep  7 12:20:58 2023

@author: krajcovic
"""
import sys,os
sys.path.append(r'C:/Users/andrej/Projects/EnergyTrading/Python/')

import cx_Oracle
try:
    cx_Oracle.init_oracle_client(lib_dir=r"C:\Users\andrej\Downloads\instantclient_21_11")
except:
    pass

from Database.TPData import TPData as tpd
from RiskPremium import RP_Tools as rpt
import Loaders.RLD_fetch as rf
from RiskPremium.RP_Tools import MFR, Plot2v2a, calculate_return,\
    TP_trades_data, ttf_settle_data, vwap_from_tp_trades, gas_for_week,\
        ttf_intraweek_settle
from Database import DB_reader as dbr
from Loaders import RLD_fetch as rldf
from scipy.optimize import minimize_scalar
from Strategies import RegTools as rt

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

start_date = dt.datetime(2019,6,1)
end_date = dt.datetime(2023,9,9)

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

spot_w = spot.resample('W').mean().iloc[1:]
spot_w.index = spot_w.index - dt.timedelta(days=6)
    
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
    

rld_data = rldf.RLDDatabaseData()


rld_da = rld_data.getResDayAhead(start_date, end_date, hourly=True)

df = pd.concat([spot, rld_da],axis=1,join='inner')
df.columns = ['de', 'rld']
df = df.dropna()
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
    
opt_da = minimize_scalar(lin_reg_da_opt, bounds=(2,30), method='bounded')

#gather trades
from datetime import datetime, time
mkt_list = ['de']
tenor_list = ['w']
tn_list = [1]
prod = 'base'
venue_list = ['eex']
start_date = datetime(2019, 6, 1)
end_date = datetime(2023, 9, 1)
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

wa_prices = pd.concat({k: v['price'] for k, v in tr_data_dict.items()}, axis=1)
wa_volumes = pd.concat({k: v['volume'] for k, v in tr_data_dict.items()}, axis=1)

def lin_reg_wa(lookback, for_optimization=False, mean=True):

    pred_df = pd.DataFrame()
    for date in pd.date_range(start=start_date+dt.timedelta(days=lookback),
                              end=end_date):
        sT = date-dt.timedelta(days=lookback)
        
        train = df.loc[((pd.to_datetime(df.index.date)>=sT)&
                        (pd.to_datetime(df.index.date)<=date))].copy()
        test = df.loc[((pd.to_datetime(df.index.date)>=(date+dt.timedelta(days=7-date.weekday())))&
                       (pd.to_datetime(df.index.date)<=(date+dt.timedelta(days=13-date.weekday()))))].copy()
        if train['rld'].empty:
            continue
        else:
            coefs = np.polyfit(train['rld'], train['de'],deg=1)
            test['de_pred'] = test['rld']*coefs[0] + coefs[1]
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
    
opt_wa = minimize_scalar(lambda lookback: lin_reg_wa(lookback, for_optimization=True),
                         bounds=(20,40), method='bounded')
    
    
pred_df = lin_reg_wa(28)
pred_df.index = pred_df.index.date

#testing prediction with trades
tick_indicess = rt.tick_index(10, 15, start_date, end_date)
tick_indices = tick_indeicies
trades = pd.concat([wa_prices,wa_volumes, tick_indices], axis=1)
trades.columns = ['price', 'volume', 'idx']
trades = trades.dropna()

vwap = [(trades.loc[trades['idx']==a,'price']*trades.loc[trades['idx']==a,'volume']).sum()\
        /trades.loc[trades['idx']==a,'volume'].sum() for a in trades['idx'].drop_duplicates()]
vwap_index = trades['idx'].drop_duplicates().index.date
wa_vwap = pd.DataFrame(vwap, index=vwap_index,columns=['wa_vwap'])

wa_vwap = wa_vwap.merge(pred_df, left_index=True, right_index=True,how='left')
wa_vwap.index = pd.to_datetime(wa_vwap.index)
wa_vwap = wa_vwap.dropna()
for date in wa_vwap.index.drop_duplicates():
    temp = wa_vwap.loc[[date]].reset_index().copy()
    plt.plot(temp['wa_vwap'])
    plt.plot(temp['de_pred'])
    plt.plot(temp['de'])
    plt.title(date)
    plt.show()

daily_wa = wa_vwap.resample('D').mean().dropna()
daily_wa['pred_error'] = daily_wa['de_pred'] - daily_wa['de']
daily_wa['market_error'] = daily_wa['wa_vwap'] - daily_wa['de']

print(abs(daily_wa['pred_error']).mean())
print(abs(daily_wa['market_error']).mean())

daily_wa['pnl_settle'] = np.where(daily_wa['de_pred']<daily_wa['wa_vwap'],
                           daily_wa['wa_vwap'] - daily_wa['de'],
                           daily_wa['de']-daily_wa['wa_vwap'])

rld_da = pd.DataFrame(rld_da.resample('d').mean(), columns=['rld_da'])

rld_da['rld_mean'] = rld_da['rld_da'].rolling(30).mean()
rld_da['rld_to_mean'] = rld_da['rld_da']/rld_da['rld_mean']-1

daily_wa = pd.concat([daily_wa, rld_da], axis=1, join='inner')

for year in daily_wa.index.year.drop_duplicates():
    plt.figure()
    plt.plot(daily_wa['pnl_settle'].loc[daily_wa.index.year==year].cumsum())
    plt.title(year)
    plt.show()
    
    
#make trades backuk
# trades.to_csv(r's:\Algo\Database\Backups\wa_trades_20190604_20230901.csv')
