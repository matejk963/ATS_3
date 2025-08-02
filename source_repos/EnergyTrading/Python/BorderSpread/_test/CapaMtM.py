# -*- coding: utf-8 -*-
"""
Created on Tue Mar 12 13:34:22 2024

@author: krajcovic
"""


import numpy as np
import pandas as pd
#from BorderSpread_tools import *
import BorderSpread.border_class as bs
import BorderSpread.capacity_class as capa
from BorderSpread.PositionManager import PositionManagerCapa, PositionManagerHedge
from BorderSpread.capacity_contract_class import CapacityContr, FwdContract
from Loaders.EikonSpot_class import EikonSpot as es
import datetime as dt
from dateutil.relativedelta import relativedelta
import calendar
import matplotlib.pyplot as plt


border_list = ['de_fr', 'fr_de', 'de_be', 'be_de',
                'de_nl', 'nl_de', 'be_nl', 'nl_be',
                'be_fr', 'fr_be',
                'de_at', 'at_de', 'at_hu', 'hu_at',
                'at_cz', 'cz_at', 'cz_de', 'de_cz']
border_list = ['de_be', 'be_de']


period = 'Q_1'

periods_dict = {}

period_dict = {'M': 1, 'W': 3, 'Q': 1}
# scaling = period_dict[period]
scaling = 1

capa_fv_list = []
delta_list = []
spread_list = []
fut1_list = []
fut2_list = []

base_today = dt.date.today()
month_start = dt.date(base_today.year,
                      base_today.month,
                      1)
for period in ['Q_1', 'Q_2', 'Q_3']:
    capa_fv_list = []
    delta_list = []
    spread_list = []
    fut1_list = []
    fut2_list = []
    for border in border_list:
        print(border)
        border = [border]
        bs_class = bs.DataBorderClass(border,
                                     ['implicit'],
                                     start_date=dt.datetime(2021,10,1),
                                     end_date=dt.date.today()-dt.timedelta(days=-1,hours=1))
        #bs_class.load_data(path_spot=r'C:\Users\krajcovic\Documents\Trading\Data\Price\EEX\Spot\spot.txt')
        bs_class.load_data()
        delivery_ = ['base']
        data = dict()
        for del_ in delivery_:
            data[del_] = bs_class.aggregate_data('M', delivery=del_)
    
        capacity = capa.ImplicitCapacity(border, delivery_)
        for b in border:
            for del_ in delivery_:
                capacity.capa_fit(data[del_], del_, scaling=3)
    
        fut_o1 = es(border[0].lower().split('_')[0],
                   month_start.strftime('%Y-%m-%d'),
                   (base_today-dt.timedelta(days=1)).strftime('%Y-%m-%d'))
        fut_o2 = es(border[0].lower().split('_')[1],
                   month_start.strftime('%Y-%m-%d'),
                   (base_today-dt.timedelta(days=1)).strftime('%Y-%m-%d'))
        
        delta_list_aux = []
        capa_list_aux = []
        spread_list_aux = []
        
        if period == 'M':
            fut1 = fut_o1.fwd_df_rel(fut_o1.start_date,
                              fut_o1.end_date,
                              ['M_1'], ['base']).iloc[-1]
            fut2 = fut_o2.fwd_df_rel(fut_o2.start_date,
                              fut_o2.end_date,
                              ['M_1'], ['base']).iloc[-1]
            
            
            spread = float(fut1) - float(fut2)
            
            delta =  capacity.capa_delta(float(fut1),
                                  float(fut2),
                                  'base')[1]
            capa_fv = capacity.capa_price(float(fut1),
                                  float(fut2),
                                  'base')[1]
        if 'Q' in period:
            fut1 = fut_o1.fwd_df_rel(fut_o1.start_date,
                              fut_o1.end_date,
                              [period], ['base']).iloc[-1]
            fut2 = fut_o2.fwd_df_rel(fut_o2.start_date,
                              fut_o2.end_date,
                              [period], ['base']).iloc[-1]
            
            
            spread = float(fut1) - float(fut2)
            
            delta =  capacity.capa_delta(float(fut1),
                                  float(fut2),
                                  'base')[1]
            capa_fv = capacity.capa_price(float(fut1),
                                  float(fut2),
                                  'base')[1]
        capa_fv_list.append(capa_fv)
        delta_list.append(delta)
        spread_list.append(spread)
        
    fv_df = pd.DataFrame([border_list,
                         capa_fv_list,
                         delta_list,
                         spread_list]).T
    fv_df.columns = ['border', 'fv', 'delta', 'spread']
    fv_df['spread'] = fv_df['spread']*(-1)
    fv_df['ext'] = np.where(fv_df['spread']>0,
                            fv_df['fv']-fv_df['spread'],
                    fv_df['fv'])
    
    fv_df = pd.DataFrame([border_list,
                         capa_fv_list,
                         delta_list,
                         spread_list]).T
    fv_df.columns = ['border', 'fv', 'delta', 'spread']
    fv_df['spread'] = fv_df['spread']*(-1)
    fv_df['ext'] = np.where(fv_df['spread']>0,
                            fv_df['fv']-fv_df['spread'],
                            fv_df['fv'])
    periods_dict[period] = fv_df
    
vol_dict = {'de_dke': 1, 'dkw_nl': 1, 'at_de': 5, 'be_de': 3,
            'be_nl': 3, 'de_at': 5, 'de_be': 3, 'de_nl': 3,
            'nl_be': 3, 'nl_de': 3, 'cz_de': 3, 'de_cz': 2,
            'at_hu': 2, 'hu_at': 2, 'at_cz': 2, 'cz_at': 2,
            'sk_cz': 1, 'hu_sk': 1, 'be_fr': 4, 'fr_be': 4}

price_dict = {'de_dke': 1.48, 'dkw_nl': 7.33, 'at_de': 1.49, 'be_de': 5.6,
            'be_nl': 3.96, 'de_at': 6.97, 'de_be': 5.11, 'de_nl': 4.36,
            'nl_be': 4.4, 'nl_de': 5.1, 'cz_de': 1.35, 'de_cz': 5.35,
            'at_hu': 6.89, 'hu_at': 1.71, 'at_cz': 2.01, 'cz_at': 3.88,
            'sk_cz': 0.8, 'hu_sk': 0.66, 'be_fr': 4.73, 'fr_be': 3.14}




hours = [91*24,92*24,92*24+1]

pnl_dict = {}
i = 0
for  period, data in periods_dict.items():
    vol_list = []
    price_list = []
    border_list = []
    fv_list = []
    for border in data['border']:
        if border not in list(vol_dict):
            vol_list.append(np.nan)
        else:
            vol_list.append(vol_dict[border])
        if border not in list(price_dict):
            price_list.append(np.nan)
        else:
            price_list.append(price_dict[border])
        border_list.append(border)
        fv_list.append(data['fv'].loc[data['border']==border].values[0])
    aux = pd.DataFrame([border_list,
                         fv_list,
                         vol_list,
                         price_list]).T
    aux.columns = ['border', 'fv', 'vol', 'price']
    aux['pnl'] = (aux['fv']-aux['price']) * aux['vol'] * hours[i]
    pnl_dict[period] = aux
    i +=1
    print(aux['pnl'].sum())
    
    


    
    