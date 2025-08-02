# -*- coding: utf-8 -*-
"""
Created on Wed Nov 22 09:00:02 2023

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





"""
Function for getting fair value for borders provided in list
FV is for the day of the fetch 
"""

def CapaFvFetch(border_list, period='M'):
    
    period_dict = {'M': 1, 'W': 3}
    scaling = period_dict[period]
    
    capa_fv_list = []
    delta_list = []
    spread_list = []
    fut1_list = []
    fut2_list = []
    
    base_today = dt.date.today()
    base_date = dt.date(2023,12,14)
    month_start = dt.date(base_today.year,
                          base_today.month,
                          1)
    
    
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
                capacity.capa_fit(data[del_], del_, scaling=scaling)
    
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
            
        elif period == 'Y':
        
            for product in ['Q_0', 'Q_1', 'Q_2', 'Q_3']:
                fut1 = fut_o1.fwd_df_rel(fut_o1.start_date,
                                  fut_o1.end_date,
                                  [product], ['base']).iloc[-1]
                fut2 = fut_o2.fwd_df_rel(fut_o2.start_date,
                                  fut_o2.end_date,
                                  [product], ['base']).iloc[-1]
                
                
                spread = float(fut1) - float(fut2)
                
                delta_aux =  capacity.capa_delta(float(fut1),
                                      float(fut2),
                                      'base')[1]
                capa_fv_aux = capacity.capa_price(float(fut1),
                                      float(fut2),
                                      'base')[1]
                delta_list_aux.append(delta_aux)
                capa_list_aux.append(capa_fv_aux)
                spread_list_aux.append(spread)
                
            delta = sum(delta_list_aux)/len(delta_list_aux)
            capa_fv = sum(capa_list_aux)/len(capa_list_aux)
            spread = sum(spread_list_aux)/len(spread_list_aux)
        
            
        
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
        
    return fv_df
    
    
def save_dfs_to_excel(dfs_dict, file_name, backtest_date=None):
    """
    Saves a dictionary of DataFrames to an Excel file, with each DataFrame as a separate sheet.
    Appends a date to the file name.

    :param dfs_dict: Dictionary where keys are sheet names and values are DataFrames.
    :param file_name: Name of the Excel file to save, without the extension.
    :param backtest_date: Date of the backtest (optional). If None, uses the current date.
    """
    # Use the current date if backtest_date is not provided
    if backtest_date is None:
        backtest_date = dt.datetime.now().strftime("%Y-%m-%d")
    
    # Append the date to the filename
    file_name_with_date = f"{file_name}_{backtest_date}.xlsx"

    with pd.ExcelWriter(file_name_with_date, engine='xlsxwriter') as writer:
        for sheet_name, df in dfs_dict.items():
            df.to_excel(writer, sheet_name=sheet_name)