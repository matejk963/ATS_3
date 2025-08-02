# -*- coding: utf-8 -*-
"""
Created on Mon Nov 20 10:16:49 2023

@author: krajcovic
"""

import sys
import numpy as np
import pandas as pd
import BorderSpread.border_class as bs
import BorderSpread.capacity_class as capa
from BorderSpread.PositionManager import PositionManagerCapa, PositionManagerHedge
from BorderSpread.capacity_contract_class import CapacityContr, FwdContract
from Loaders.EikonSpot_class import EikonSpot as es
import datetime as dt
from dateutil.relativedelta import relativedelta
import calendar
import seaborn as sns
import matplotlib.pyplot as plt


def CapaFVFetch(borders_list,
                start_date,
                end_date=None,
                period='M',
                delivery=['base']):
    
    capa_fv_list = []
    delta_list = []
    spread_list = []
    fut1_list = []
    fut2_list = []
    
    base_today = dt.date.today()
    month_start = dt.date(base_today.year+1,
                         1,
                          1)
    
    for border in border_list:
        border = [border]
        bs_class = bs.DataBorderClass(border,
                                     ['implicit'],
                                     start_date=start_date,
                                     end_date=dt.date.today()-dt.timedelta(days=-1,hours=1))
        #bs_class.load_data(path_spot=r'C:\Users\krajcovic\Documents\Trading\Data\Price\EEX\Spot\spot.txt')
        bs_class.load_data()
        delivery_ = delivery
        data = dict()
        for del_ in delivery_:
            data[del_] = bs_class.aggregate_data('W', delivery=del_)
    
        capacity = capa.ImplicitCapacity(border, delivery_)
        for b in border:
            for del_ in delivery_:
                capacity.capa_fit(data[del_], del_, scaling=scaling_dict)
        month = 10
        year = 2023
    
        fut_o1 = es(border[0].lower().split('_')[0],
                   month_start.strftime('%Y-%m-%d'),
                   base_today.strftime('%Y-%m-%d'))
        fut_o2 = es(border[0].lower().split('_')[1],
                   month_start.strftime('%Y-%m-%d'),
                   base_today.strftime('%Y-%m-%d'))
            
        fut1 = fut_o1.fwd_df_rel(fut_o1.start_date,
                          fut_o1.end_date,
                          ['Y_1'], ['base']).iloc[-1]
        fut2 = fut_o2.fwd_df_rel(fut_o2.start_date,
                          fut_o2.end_date,
                          ['Y_1'], ['base']).iloc[-1]
        
        
        spread = float(fut1) - float(fut2)
        
        delta =  capacity.capa_delta(float(fut1),
                              float(fut2),
                              'base')[0]
        capa_fv = capacity.capa_price(float(fut1),
                              float(fut2),
                              'base')[0]
        
        capa_fv_list.append(capa_fv)
        delta_list.append(delta)
        spread_list.append(spread)
        