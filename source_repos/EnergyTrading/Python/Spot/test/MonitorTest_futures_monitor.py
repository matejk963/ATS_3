# -*- coding: utf-8 -*-
"""
Created on Mon Jan 22 16:56:32 2024

@author: krajcovic
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import datetime as dt

import seaborn as sns

from Spot.Monitor_class import SettleMonitor as SM
from Spot.Monitor_class import FuturesMonitor as FM

base_products = ['W_1', 'W_2', 'W_3', 'M_1', 'M_2', 'M_3', 'Q_1', 'Q_2', 'Q_3']
base_products = ['Q.2', 'Q.3']
market_list = ['de']
delivery_dict = ['base']

# Generate the combinations
products = []
markets = []
delivery = []

for product in base_products:
    for market in market_list:
        for delivery_option in delivery_dict:
            products.append(product)
            markets.append(market)
            delivery.append(delivery_option)

params_dict = {}

params_dict['product_list'] = products

params_dict['market_list'] = markets

params_dict['delivery_list'] = delivery 


params_dict['sD'] = dt.datetime(2019,1,1)
params_dict['eD'] = dt.datetime(2024,9,19)
params_dict['ns'] = 2
params_dict['cont'] = False

selected_year = 2025
spreads_df = pd.DataFrame()
for year in range(2019,2026):
    name = 'DE_Q.2_Q.3_' + str(year)
    params_dict['year_list'] = [year] * len(params_dict['market_list'])

    fm_inst = FM(params_dict)
    
    temp = fm_inst.spread_maker()
    temp = temp[[name]].copy()
    temp = temp.loc[~((temp.index.month==2)&(temp.index.day==29))]
    # Get the year of the latest date in the index
    latest_year = pd.to_datetime(temp.index).max().year
    
    # Compute the year shift
    if year != selected_year:
        year_shift = selected_year - latest_year
        
        # Shift the index by the year difference
        temp.index = pd.to_datetime(temp.index).map(lambda x: x.replace(year=x.year + year_shift))

    spreads_df = pd.concat([spreads_df, temp], axis=1)



