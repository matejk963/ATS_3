# -*- coding: utf-8 -*-
"""
Created on Tue Sep 24 14:49:02 2024

@author: krajcovic
"""

from Spot.SpotModelClass_mark4 import PowerModel as PM
from Spot.Monitor_class import RldMonitor as RM
from Spot.Monitor_class import AvCapMonitor as AM

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import datetime as dt
import pickle
import os

import seaborn as sns

start_date = dt.datetime(2015,1,1)
end_date = dt.datetime(2024,9,25)

rm_inst = RM()
rm_inst.set_date_range(start_date,
                      end_date)

rld_scen_dict = {}
for market in ['de', 'fr', 'be', 'nl', 'at']:

    rld = rm_inst.get_fund_curve('ResidualDemand', '00',
                                 normalize_to='ResidualDemand',
                                 market=market)
    norm_data = rm_inst.get_fund_data('normal', 'ResidualDemand', '00',market=market, source='local')
    norm_data['month'] = norm_data['value_date'].dt.month
    
    rld_da = rm_inst.get_da_data(rld).set_index('value_date')
    rld_da['month'] = rld_da.index.month
    
    quant_df = pd.DataFrame()
    
    for quant in range(10,100,10):
        quant_prc = quant/100
        temp = rld_da.groupby('month').quantile(quant_prc)
        temp_norm = pd.DataFrame(norm_data['rld'] * norm_data['month'].map(temp['rld_da']),
                                 columns=[f'quant_{str(quant)}'])
        temp_norm.index = norm_data['value_date']
        quant_df = pd.concat([quant_df, temp_norm],axis=1)
        
    rld_scen_dict[market] = quant_df
    
    
norm_data = rm_inst.get_fund_data('normal', 'ResidualDemand', '00', source='local')


folder_path = r'Z:\Data\Spot\Scenarios\Rld'
file_path = os.path.join(folder_path, f"Rld_scen_{end_date.strftime('%Y%m%d')}.pkl")

with open(file_path, 'wb') as f:
    pickle.dump(rld_scen_dict, f)


