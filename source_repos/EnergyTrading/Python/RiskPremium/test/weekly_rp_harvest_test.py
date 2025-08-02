# -*- coding: utf-8 -*-
"""
Created on Mon Aug 28 08:07:38 2023

@author: krajcovic
"""

from Database.TPData import TPData as tpd
from RiskPremium import RP_Tools as rpt
import Loaders.RLD_fetch as rf
from RiskPremium.RP_Tools import MFR, Plot2v2a, calculate_return,\
    TP_trades_data, df_from_tp_data_dict


from Loaders.EikonSpot_class import EikonSpot as ES
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import datetime as dt
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

mkt_list = ['de', 'de', 'de']
tenor_list = ['w', 'w', 'w']
tn_list = [1, 2, 3]
prod = 'base'
venue_list = ['eex']
start_date = dt.datetime(2020, 1, 1)
end_date = dt.datetime(2023, 8, 26)
n_s = 2

tr_data_dict = TP_trades_data(mkt_list=mkt_list,
                              tenor_list=tenor_list,
                              tn_list=tn_list,
                              prod=prod,
                              start_date=start_date,
                              venue_list=venue_list,
                              end_date=end_date,
                              n_s=n_s)
    
weeks = df_from_tp_data_dict(tr_data_dict=tr_data_dict)



w2 = weeks[['w1', 'w2']].copy()

# w2['ret'] = np.where(w2.index.weekday<4,
#                      w2['w2'].shift(-1)/w2['w2']-1,
#                      w2['w1'].shift(-1)/w2['w2']-1)
w2['ret'] = w2.index.map(lambda x: calculate_return(x, w2, 'w2', 'w1'))
w2['cum_pnl'] = w2['ret'].cumsum()

w3 = weeks[['w2', 'w3']].copy()

# w3['ret'] = np.where(w3.index.weekday<4,
#                      w3['w3'].shift(-1)/w3['w3']-1,
#                      w3['w2'].shift(-1)/w3['w3']-1)
w3['ret'] = w3.index.map(lambda x: calculate_return(x, w3, 'w3', 'w2'))
w3['cum_pnl'] = w3['ret'].cumsum()

rd.open_session()
ttf = rd.get_history(universe=['TFMBMc2', 'TFMBMc3'],
                      fields=['VWAP'],
                        interval='1D', 
                        start=start_date,
                        end=end_date)
rd.close_session()
ttf = ttf.tz_localize('UTC')
ttf = ttf.tz_convert('Europe/Berlin')
ttf = ttf.tz_localize(None)
ttf.index = pd.to_datetime(ttf.index.date)
ttf.columns = ['ttf_1', 'ttf_2']


ttf['ttf_ret'] = np.where(ttf.index.day>23,
                          ttf.index.map(lambda x: calculate_return(x, ttf, 'ttf_2', 'ttf_2')),
                          ttf.index.map(lambda x: calculate_return(x, ttf, 'ttf_1', 'ttf_1')))

rld = rf.RLDDatabaseData()
rld_data = rld.createRLDVector(start_date, end_date,
                               delta_f=7,
                               delta_h=7)

rld_data['date'] = rld_data['forecast_date']
rld_mean = rld_data.set_index('date')[['mean']].copy()


test = pd.concat([w2['ret'], ttf['ttf_ret']],
                 axis=1,
                 join='inner').dropna()

hedge = rpt.Hedge(test,returns_in=True)

rol_beta = hedge.rolling_beta(30)

test = pd.concat([test, rol_beta],
                 axis=1,
                 join='inner').dropna()

test['ret_hdg'] = test['ttf_ret'].astype(float)*test['beta']-test['ret']
test[['ret', 'ret_hdg', 'ttf_ret']].iloc[:-15].cumsum().plot()

# sns.histplot(data=test,x='cor')
# plt.show()



test = pd.concat([test, rld_mean], axis=1, join='inner')
test['norm'] = test['mean'].rolling(30).mean().dropna()
test['rld_ch'] = np.log(test['mean']/test['mean'].shift(1))
test['rld_d'] = test['mean']/test['norm']
test['cum_pnl_h'] = test['ret_hdg'].cumsum()

Plot2v2a(test, 'cum_pnl_h', 'mean')

# Display the plot
plt.show()

mfr = MFR(dt.date(2020,1,1), dt.date.today(),tenor_list=['M_1'])

test = pd.concat([test, mfr], axis=1, join='inner')
test['mfr_d'] = test.index.map(lambda x: calculate_return(x, test, 'mfr', 'mfr'))


Plot2v2a(test, 'cum_pnl_h', 'mfr')
