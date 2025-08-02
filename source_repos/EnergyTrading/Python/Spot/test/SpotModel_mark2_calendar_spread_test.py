# -*- coding: utf-8 -*-
"""
Created on Wed Jun 12 09:50:31 2024

@author: krajcovic
"""

from Spot.SpotModelClass_mark2 import PowerModel as PM

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import datetime as dt
import pickle

# To load the dictionary from the file
# scen_dict = {}
# with open(r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Algo\rld_scen_dict_20240527_4.pickle', 'rb') as file:
#     scen_dict[dt.datetime(2024,5,27)] = pickle.load(file)
    
    
# # # scen_dict = {i: scen_dict[i] for i in range(len(scen_dict))}
# for date, date_dict in scen_dict.items():
#     for scen_type, scen_type_dict in date_dict.items():        
#         for i, i_df in scen_type_dict.items():
#             i_df.columns = [a + '_rld' for a in i_df.columns]
#             scen_dict[date][scen_type][i] = i_df
            
# aux_dict = {key: scen_dict[key] for key in list(scen_dict)[:2]}


params_dict = {}
params_dict = {}
# params_dict['market_list'] = ['de']*2 + ['fr'] *2
# params_dict['product_list'] = ['W_1', 'W_2']*2

params_dict['product_list'] = ['M_1', 'M_2', 'M_3', 'Q_1', 'Q_2', 'Q_3']

params_dict['market_list'] = ['de'] * len(params_dict['product_list'])

params_dict['delivery_list'] = ['base'] * len(params_dict['product_list'])

params_dict['year_list'] = [2024] * len(params_dict['market_list'])
params_dict['sD'] = dt.datetime(2022,6,22)
params_dict['eD'] = dt.datetime(2024,6,13)
params_dict['ns'] = 2
params_dict['cont'] = False

model_params_dict = {}
model_params_dict['xgboost'] = {}
model_params_dict['xgboost']['de'] = {'alpha': 0.010895398859824533, 'colsample_bytree': 0.9622126960415747,
          'gamma': 0.22653480769373827, 'lambda': 0.19084485197671305,
          'learning_rate': 0.02690767935041876, 'max_depth': 16, 'min_child_weight': 11,
          'n_estimators': 167, 'subsample': 0.2106044847212501,
          'nthread': -1}
model_params_dict['xgboost']['de']['scaler'] = 'yeojohnson'
model_params_dict['xgboost']['fr'] = {'alpha': 0.006790738192923923, 'colsample_bytree': 0.5826675107604863,
                                        'gamma': 0.25423182181883813, 'lambda': 0.3892329219499202,
                                        'learning_rate': 0.03641228637838651, 'max_depth': 10,
                                        'min_child_weight': 18, 'n_estimators': 189,
                                        'subsample': 0.19945640341866677,
                                        'nthread': -1}
model_params_dict['xgboost']['fr']['scaler'] = 'yeojohnson'
model_params_dict['xgboost']['hu'] = {'alpha': 0.010895398859824533, 'colsample_bytree': 0.9622126960415747,
          'gamma': 0.22653480769373827, 'lambda': 0.19084485197671305,
          'learning_rate': 0.02690767935041876, 'max_depth': 16, 'min_child_weight': 11,
          'n_estimators': 167, 'subsample': 0.2106044847212501}
model_params_dict['xgboost']['hu']['scaler'] = 'yeojohnson'


pm_inst = PM(params_dict)



scen_dict = {dt.datetime(2024,5,27):{'liq':{}}}

spread_dict = pm_inst.get_calendar_spread(model_params_dict, scen_dict)





