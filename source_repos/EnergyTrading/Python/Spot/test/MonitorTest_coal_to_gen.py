# -*- coding: utf-8 -*-
"""
Created on Mon Jan 22 16:56:32 2024

@author: krajcovic
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
import datetime as dt

import seaborn as sns

from Spot.Monitor_class import SettleMonitor as SM
from Spot.Monitor_class import RldMonitor as RM

from Loaders.EikonFut_class import EikonFut as EF
from Database.GenFetchClass import ENTSOEData as EData

from Math.accumfeatures import EMA, MSTD


sD = datetime(2017,1,1)
eD = datetime(2024,1,30)

sm_inst = SM()
sm_inst.set_date_range(sD, eD)
market = 'de'
sm_inst.set_grids([market])

coal_df = sm_inst.get_coal_spot()
gas_df = sm_inst.get_gas_spot()
eua_df = sm_inst.get_eua_df()
power_df = sm_inst.get_power_spot()

for fuel in [gas_df, coal_df, eua_df]:
    fuel.reset_index(inplace=True)
    power_df.reset_index(inplace=True)
    power_df['date'] = pd.to_datetime(power_df['datetime'].dt.date)
    power_df = power_df.merge(fuel, on='date', how='inner')
    power_df.set_index('datetime', inplace=True)
    
power_df.drop(['date'],axis=1, inplace=True)

power_df['gmc'] = power_df['ttf_da']+power_df['eua']*0.2
power_df['cmc'] = power_df['spot_coal']/6.15+power_df['eua']*0.34
power_df['mc_ratio'] = power_df['gmc']/power_df['cmc']
for spread in ['css', 'cds', 'cs']:
    if spread in ['css']:
        power_df['css'] = power_df[market] - 2*(power_df['gmc'])
        power_df['ghr'] = power_df[market] / power_df['gmc']
    elif spread in ['cds']:
        power_df['cds'] = power_df[market] - power_df['cmc']/0.35
        power_df['chr'] = power_df[market] / power_df['cmc']
    elif spread in ['cs']:
        power_df['cds'] = power_df[market] - power_df['eua']*0.34
        power_df['chr'] = power_df[market] / power_df['eua']

peak_df = power_df.copy()
peak_df = peak_df[peak_df.index.dayofweek < 5]
peak_df = peak_df[(peak_df.index.hour >= 9) & (peak_df.index.hour <= 20)]
grouped = peak_df.groupby(peak_df.index.normalize())

peak_df = grouped.mean().copy()

mon_inst = RM()
mon_inst.set_date_range(sD, eD)

raw_data = mon_inst.get_raw_data(source='not_db')


test = mon_inst.process_data(raw_data)

rld_da = test.iloc[:,:24].unstack().reset_index()
rld_da['datetime'] = rld_da['forecast_date'] + pd.to_timedelta(rld_da['hours'], unit='h')
rld_da = rld_da[['datetime', 0]].copy()
rld_da.columns = ['datetime', 'rld_da']
rld_da.sort_values(['datetime'], inplace=True)
rld_da.set_index('datetime', inplace=True)



rld_da = pd.concat([rld_da, power_df], axis=1, join='inner')

new_x = np.array([test.loc[pd.to_datetime('20240130')][145:312].mean()])
new_y = np.array([1.49])

w2 = 1.75
w3 = 1.85
w4 = 1.78


sns.regplot(data=rld_da.iloc[-168:],x='rld_da', y='ghr',order=3)
sns.regplot(data=rld_da.iloc[-168*2:-168],x='rld_da', y='ghr',order=3)
plt.scatter(new_x, new_y, color='red')

plt.axhline(y=w2, color='green', linestyle='--')
plt.axhline(y=w3, color='red', linestyle=':')
plt.axhline(y=w4, color='blue', linestyle='-.')





# # Instantiate the ENTSOEData class and set necessary parameters
# entsoe = EData()
# entsoe.set_api_key("4961d306-7fb4-410a-9bb0-165a59343d92")
# entsoe.set_country("10Y1001A1001A83F")
# entsoe.set_date_range(sD, eD)

# gen_df = entsoe.get_generation_data()

# test = pd.concat([power_df, gen_df[['Fossil Hard coal']]], axis=1, join='inner')

# sns.regplot(data=test.loc[abs(test['chr'])<2].resample('D').mean().loc[((test['mc_ratio']<1.3)&
#                                                                         (test['mc_ratio']>1.2))],
#             x='chr', y='Fossil Hard coal', fit_reg=False)
