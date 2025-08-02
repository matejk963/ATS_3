# -*- coding: utf-8 -*-
"""
Created on Mon Apr  8 13:20:45 2024

@author: krajcovic
"""

import pandas as pd
import numpy as np
import datetime as dt
import matplotlib.pyplot as plt
import seaborn as sns
import random
from copy import deepcopy
import os

from Spot.SpotModelClass_mark2 import PowerModel as PM

import pickle


file_paths = [
    r"Z:\Data\Scenarios\scen_dict_20230701_20230711.pickle",
    r"Z:\Data\Scenarios\scen_dict_20230713_20230913.pickle",
    r"Z:\Data\Scenarios\scen_dict_20230915_20231107.pickle",
    r"Z:\Data\Scenarios\scen_dict_20231111_20240205.pickle",
    r"Z:\Data\Scenarios\scen_dict_20240207_20240401.pickle"
    ]

for  file_path in file_paths[3:4]:

    # To load the dictionary from the file
    with open(file_path, 'rb') as file:
        scen_dict = pickle.load(file)
    # scen_dict = {i: scen_dict[i] for i in range(len(scen_dict))}
    for date, date_dict in scen_dict.items():
        for scen_type, scen_type_dict in date_dict.items():        
            for i, i_df in scen_type_dict.items():
                i_df.columns = [a + '_rld' for a in i_df.columns]
                scen_dict[date][scen_type][i] = i_df
    
    for scen_date, scen_data in scen_dict.items():
        if scen_date<=dt.datetime(2024,3,26):
            continue
        aux_dict = {}
        aux_dict[scen_date] = scen_data
        
        # Create dictionary for parameters
        params_dict = {}
    
        params_dict['market_list'] = ['de']*3
        params_dict['product_list'] = ['W_1','W_2', 'W_3']
        
        params_dict['delivery_list'] = ['base'] * len(params_dict['market_list'])
        params_dict['year_list'] = [2024] * len(params_dict['market_list'])
        params_dict['sD'] = dt.datetime(2020,1,1)
        params_dict['eD'] = dt.datetime(2024,5,27)
        params_dict['ns'] = 2
        params_dict['cont'] = False
        
        pm_inst = PM(params_dict)
        
        model_params_dict = {}
        model_params_dict['xgboost'] = {}
        model_params_dict['xgboost']['de'] = {'alpha': 0.010895398859824533, 'colsample_bytree': 0.9622126960415747,
                  'gamma': 0.22653480769373827, 'lambda': 0.19084485197671305,
                  'learning_rate': 0.02690767935041876, 'max_depth': 16, 'min_child_weight': 11,
                  'n_estimators': 167, 'subsample': 0.2106044847212501}
        model_params_dict['xgboost']['de']['scaler'] = 'yeojohnson'
        model_params_dict['xgboost']['fr'] = {'alpha': 0.006790738192923923, 'colsample_bytree': 0.5826675107604863,
                                                'gamma': 0.25423182181883813, 'lambda': 0.3892329219499202,
                                                'learning_rate': 0.03641228637838651, 'max_depth': 10,
                                                'min_child_weight': 18, 'n_estimators': 189,
                                                'subsample': 0.19945640341866677}
        model_params_dict['xgboost']['fr']['scaler'] = 'yeojohnson'
        # model_params_dict['extratrees'] = {'n_estimators': 200,
        #                                       'random_state': 0}
        
        # data_dict = pm_inst.create_fcst_curves(train_dict, model_params_dict)
        
        
        
    
        
        scen_fcst_dict = pm_inst.get_calendar_spread(model_params_dict, aux_dict)
        scen_fcst_dict_backup = deepcopy(scen_fcst_dict)
        
        for date, date_dict in scen_fcst_dict.items():
            for market, market_df in date_dict.items():
                # Extract elements from tuple and create new columns
                market_df[['Product', 'Year', 'Delivery']] = pd.DataFrame(market_df['Row'].tolist(), index=market_df.index)
                
                # Create a new index from elements of the 'Row' column
                market_df.set_index(['Product', 'Year', 'Delivery'], inplace=True)
                
                # Drop the original 'Row' column and the 'Column' column as they are no longer needed
                market_df.drop(columns=['Row', 'Column'], inplace=True)
                
            
        
        
        folder_path = r'Z:\Data\Scenarios\Scenario_prices'
        
        # start_end_dates = file_path.split('\\')[-1].split('_')
        # start_date = start_end_dates[-2]
        # end_date = start_end_dates[-1].split('.')[0]
        
        file_name = 'de_w1_w2_' + scen_date.strftime('%Y%m%d') + '_2.pickle'
        file_path = os.path.join(folder_path, file_name)
        
        with open(file_path, 'wb') as file2:
            pickle.dump(scen_fcst_dict, file2)
            
        
