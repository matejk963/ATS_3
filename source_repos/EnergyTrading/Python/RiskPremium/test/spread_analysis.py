# -*- coding: utf-8 -*-
"""
Created on Sat Sep  9 14:44:48 2023

@author: krajcovic
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import datetime as dt
import seaborn as sns

from RiskPremium.RP_Tools import MFR as mfr
from RiskPremium.RP_Tools import Plot2v2a
from Loaders.RLD_fetch import RLDDatabaseData as rldd
import Spread_class as sprd
import CSS_class as cssc
from Loaders.EikonSpot_class import EikonSpot as es


sD = dt.datetime(2018,1,1)
eD = dt.datetime(2023,9,1)
date_range = pd.date_range(sD, eD)

month_start_list = pd.date_range(start=sD,
                                 end=eD,
                                 freq='MS').to_list()
period_list = ['m' for a in month_start_list]
delivery_list = ['base' for a in month_start_list]

prices_dict2 = {}
for market in ['de', 'gas', 'coal']:
    es_o = es(market, sD, eD)
    temp = es_o.fwd_df_abs(sD=sD,
                         eD=eD,
                         period_list=period_list,
                         period_start_list=month_start_list,
                         delivery_list=delivery_list)
    prices_dict2[market] = temp

es_o = es('eua', sD, eD)
test_list = [es_o.fwd_code_creator(es_o.grid, period_start, period, delivery)
               for period_start, period, delivery in zip(month_start_list,
                                                         period_list,
                                                         delivery_list)]

rld_ob = rldd()
norm = rld_ob.getResNormals(sD, eD)

mfr_df = mfr(sD-dt.timedelta(days=120),eD)

cor_dict = {}
# gas and power correlations
month_list = []
year_list = []
cor1_list = []
cor2_list = []
for col, month_date in zip(prices_dict['de'].columns,
                           month_start_list):
    de = prices_dict['de'][col].dropna()
    de = de.loc[((de.index.month!=month_date.month))].copy()
    if de.empty:
        continue
    else:
        ttf = prices_dict['gas'][col.replace('DEBM', 'TFMBM')]
        df = pd.concat([de, ttf], axis=1, join='inner')
        df[['de_ret', 'gas_ret']] = np.log(df.iloc[:,:2]/df.iloc[:,:2].shift(1))
        df2 = df.iloc[:-14].copy()
        cor1_list.append(df['de_ret'].corr(df['gas_ret']))
        cor2_list.append(df2['de_ret'].corr(df2['gas_ret']))
        
        month_list.append(month_date.month)
        year_list.append(month_date.year)
gas_cor_df = pd.DataFrame(np.column_stack([month_list, year_list, cor1_list, cor2_list]),
                              columns=['month', 'year', 'cor1', 'cor2'])
# coal and power correlations
month_list = []
year_list = []
cor1_list = []
cor2_list = []
for col, month_date in zip(prices_dict['de'].columns,
                           month_start_list):
    de = prices_dict['de'][col].dropna()
    de = de.loc[((de.index.month!=month_date.month))].copy()
    if de.empty:
        continue
    else:
        ttf = prices_dict['coal'][col.replace('DEBM', 'ATWM')]
        df = pd.concat([de, ttf], axis=1, join='inner')
        df[['de_ret', 'coal_ret']] = np.log(df.iloc[:,:2]/df.iloc[:,:2].shift(1))
        df2 = df.iloc[:-14].copy()
        cor1_list.append(df['de_ret'].corr(df['coal_ret']))
        cor2_list.append(df2['de_ret'].corr(df2['coal_ret']))
        
        month_list.append(month_date.month)
        year_list.append(month_date.year)
coal_cor_df = pd.DataFrame(np.column_stack([month_list, year_list, cor1_list, cor2_list]),
                              columns=['month', 'year', 'cor1', 'cor2'])
    

#first leg to spread correlation

month_list = []
year_list = []
cor1_list = []
cor2_list = []
for col1,col2, month_date in zip(prices_dict['de'].columns[:-1],
                                 prices_dict['de'].columns[1:],
                           month_start_list):
    de = prices_dict['de'][[col1, col2]].dropna()
    df = de.loc[((de.index.month!=month_date.month))].copy() 
    if df.empty:
        continue
    else:
        
        df[['ret1', 'ret2']] = np.log(df.iloc[:,:2]/df.iloc[:,:2].shift(1))
        df2 = df.iloc[:-14].copy()
        df['ret'] = df['ret1']-df['ret2']
        df2['ret'] = df2['ret1']-df2['ret2']
        cor1_list.append(df['ret1'].corr(df['ret']))
        cor2_list.append(df2['ret1'].corr(df2['ret']))
        month_list.append(month_date.month)
        year_list.append(month_date.year)
spread_cor_df = pd.DataFrame(np.column_stack([month_list, year_list, cor1_list, cor2_list]),
                              columns=['month', 'year', 'cor1', 'cor2'])

#gas_coal ret spread to power ret spread correltaion

month_list = []
year_list = []
cor1_list = []
cor2_list = []
for col1,col2, month_date in zip(prices_dict['de'].columns[:-1],
                                 prices_dict['de'].columns[1:],
                           month_start_list):
    de = prices_dict['de'][[col1, col2]].dropna()
    df = de.loc[((de.index.month!=month_date.month))].copy() 
    if df.empty:
        continue
    else:
        ttf = prices_dict['gas'][col1.replace('DEBM', 'TFMBM')]
        coal = prices_dict['coal'][col1.replace('DEBM', 'ATWM')]
        
        fuels = pd.concat([ttf, coal],axis=1,join='inner')
        fuels[['ret_g', 'ret_c']] = np.log(fuels.iloc[:,:2]/fuels.iloc[:,:2].shift(1))
        fuels['ret_f'] = fuels['ret_g'] - fuels['ret_c']
        df[['ret1', 'ret2']] = np.log(df.iloc[:,:2]/df.iloc[:,:2].shift(1))
        df['ret'] = df['ret1']-df['ret2']
        df = pd.concat([df, fuels], axis=1, join='inner')
        df2 = df.iloc[:-14].copy()
        cor1_list.append(df['ret1'].corr(df['ret']))
        cor2_list.append(df2['ret1'].corr(df2['ret']))
        month_list.append(month_date.month)
        year_list.append(month_date.year)
fuels_spread_cor_df = pd.DataFrame(np.column_stack([month_list, year_list, cor1_list, cor2_list]),
                              columns=['month', 'year', 'cor1', 'cor2'])

#mfr to spread cointegration
month_list = []
year_list = []
cor1_list = []
cor2_list = []
for col1,col2, month_date in zip(prices_dict['de'].columns[:-1],
                                 prices_dict['de'].columns[1:],
                           month_start_list):
    de = prices_dict['de'][[col1, col2]].dropna()
    df = de.loc[((de.index.month!=month_date.month))].copy() 
    if df.empty:
        continue
    else:
        ttf = prices_dict['gas'][col1.replace('DEBM', 'TFMBM')]
        coal = prices_dict['coal'][col1.replace('DEBM', 'ATWM')]
        eua = mfr_df['eua'].copy()
        fuels = pd.concat([ttf, coal, eua],axis=1,join='inner')
        fuels['mfr'] = ((fuels.iloc[:,0]+fuels.iloc[:,2]*0.2)/
                        (fuels.iloc[:,1]/8.14+fuels.iloc[:,2]*0.32))
        fuels[['ret_g', 'ret_c']] = np.log(fuels.iloc[:,:2]/fuels.iloc[:,:2].shift(1))
        fuels['ret_f'] = fuels['ret_g'] - fuels['ret_c']
        df[['ret1', 'ret2']] = np.log(df.iloc[:,:2]/df.iloc[:,:2].shift(1))
        df['ret'] = df['ret1']-df['ret2']
        df['spread'] = df[col1]/df[col2]
        df = pd.concat([df, fuels], axis=1, join='inner')
        df2 = df.iloc[:-14].copy()
        cor1_list.append(df[col1.replace('DEBM', 'TFMBM')].corr(df['spread']))
        cor2_list.append(df2[col1.replace('DEBM', 'TFMBM')].corr(df2['spread']))
        month_list.append(month_date.month)
        year_list.append(month_date.year)
mfr_spread_cor_df = pd.DataFrame(np.column_stack([month_list, year_list, cor1_list, cor2_list]),
                              columns=['month', 'year', 'cor1', 'cor2'])

#mfr to spread ret correlation

month_list = []
year_list = []
cor1_list = []
cor2_list = []
for col1,col2, month_date in zip(prices_dict['de'].columns[:-1],
                                 prices_dict['de'].columns[1:],
                           month_start_list):
    de = prices_dict['de'][[col1, col2]].dropna()
    df = de.loc[((de.index.month!=month_date.month))].copy() 
    if df.empty:
        continue
    else:
        ttf = prices_dict['gas'][col1.replace('DEBM', 'TFMBM')]
        coal = prices_dict['coal'][col1.replace('DEBM', 'ATWM')]
        eua = mfr_df['eua'].copy()
        fuels = pd.concat([ttf, coal, eua],axis=1,join='inner')
        fuels['mfr'] = ((fuels.iloc[:,0]+fuels.iloc[:,2]*0.2)/
                        (fuels.iloc[:,1]/8.14+fuels.iloc[:,2]*0.32))
        fuels[['ret_g', 'ret_c']] = np.log(fuels.iloc[:,:2]/fuels.iloc[:,:2].shift(1))
        fuels['ret_f'] = fuels['mfr'] - fuels['mfr'].shift(1)
        df[['ret1', 'ret2']] = np.log(df.iloc[:,:2]/df.iloc[:,:2].shift(1))
        df['spread'] = df[col1]/df[col2]
        df['ret'] = df['spread']-df['spread'].shift(1)
        
        
        df = pd.concat([df, fuels], axis=1, join='inner')
        df2 = df.iloc[:-14].copy()
        cor1_list.append(df['ret_f'].corr(df['ret']))
        cor2_list.append(df2['ret_f'].corr(df2['ret']))
        month_list.append(month_date.month)
        year_list.append(month_date.year)
mfr_spread_ret_cor_df = pd.DataFrame(np.column_stack([month_list, year_list, cor1_list, cor2_list]),
                              columns=['month', 'year', 'cor1', 'cor2'])

#spread of mfr to spread correlation
month_list = []
year_list = []
cor1_list = []
cor2_list = []
mfr_spread_power_spread_dict = {}
for col1,col2, month_date in zip(prices_dict['de'].columns[:-1],
                                 prices_dict['de'].columns[1:],
                           month_start_list):
    de = prices_dict['de'][[col1, col2]].dropna()
    df = de.loc[((de.index.month!=month_date.month))].copy() 
    if df.empty:
        continue
    else:
        ttf = prices_dict['gas'][[col1.replace('DEBM', 'TFMBM'),
                                 col2.replace('DEBM', 'TFMBM')]]
        coal = prices_dict['coal'][[col1.replace('DEBM', 'ATWM'),
                                   col2.replace('DEBM', 'ATWM')]]
        
        fuels = pd.concat([ttf, coal, eua],axis=1,join='inner')
        fuels[['ret1_g','ret2_g',
               'ret1_c','ret2_c']] = np.log(fuels.iloc[:,:4]/fuels.iloc[:,:4].shift(1))
        fuels['ret1_f'] = fuels['ret1_g'] - fuels['ret1_c']
        fuels['ret2_f'] = fuels['ret2_g'] - fuels['ret2_c']
        fuels['mfr1'] = ((fuels.iloc[:,0]+fuels.iloc[:,4]*0.2)/
                        (fuels.iloc[:,2]/8.14+fuels.iloc[:,4]*0.32))
        fuels['mfr2'] = ((fuels.iloc[:,1]+fuels.iloc[:,4]*0.2)/
                        (fuels.iloc[:,3]/8.14+fuels.iloc[:,4]*0.32))
        df[['ret1', 'ret2']] = np.log(df.iloc[:,:2]/df.iloc[:,:2].shift(1))
        df['ret'] = df['ret1']-df['ret2']
        df['spread'] = df[col1] - df[col2]
        
        df = pd.concat([df, fuels], axis=1, join='inner')
        df['mfr_spread'] = df['mfr1'] - df['mfr2']
        df2 = df.iloc[:-14].copy()
        
        cor1_list.append(df['mfr_spread'].corr(df['spread']))
        cor2_list.append(df2['mfr_spread'].corr(df2['spread']))
        month_list.append(month_date.month)
        year_list.append(month_date.year)
        mfr_spread_power_spread_dict[month_date] = df
mfr_spread_spread_cor_df = pd.DataFrame(np.column_stack([month_list, year_list, cor1_list, cor2_list]),
                              columns=['month', 'year', 'cor1', 'cor2'])





norm1 = norm.loc[((norm.index.month==month1)&
                  (norm.index.year==year))].copy()
mean1 = norm1.mean().item()
std1 = norm1.std().item()
kurt1 = norm1.kurt().item()
skew1 = norm1.skew().item()
norm2 = norm.loc[((norm.index.month==month2)&
                  (norm.index.year==year))].copy()
mean2 = norm2.mean().item()
std2 = norm2.std().item()
kurt2 = norm2.kurt().item()
skew2 = norm2.skew().item()

skew = skew1-skew2
std = std1 - std2
mean = mean1 - mean2
kurt = kurt1 - kurt2

print('mean: ', mean,
      'std: ', std,
      'skew: ', skew,
      'kurt: ', kurt)

df = pd.concat([mfr_df, spread_df[['spread']]], axis=1, join='inner')
df = df.loc[df.index.month!=month1].copy()
df = df.iloc[:-14].copy()

sns.regplot(data=df,x='mfr', y='spread')
plt.show()
Plot2v2a(df, 'mfr', 'spread')

css_o = cssc.CSS(['de'], ['m'], [month1], ['b'], [year])
css1_df = css_o.prices_df(start_date, end_date)    
