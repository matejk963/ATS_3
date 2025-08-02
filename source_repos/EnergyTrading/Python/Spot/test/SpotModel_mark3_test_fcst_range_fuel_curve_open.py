# -*- coding: utf-8 -*-
"""
Created on Wed Jun 12 09:50:31 2024

@author: krajcovic
"""

from Spot.SpotModelClass_mark3 import PowerModel as PM

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import datetime as dt
import pickle

# To load the dictionary from the file
scen_dict = {}
with open(r'Z:\Data\Spot\Model\Inputs\Fuels\gas_eua_curves_20230701_20240430.pickle', 'rb') as file:
    scen_dict = pickle.load(file)
    
    
# scen_dict = {i: scen_dict[i] for i in range(len(scen_dict))}
# for date, date_dict in scen_dict.items():
#     for scen_type, scen_type_dict in date_dict.items():        
#         for i, i_df in scen_type_dict.items():
#             i_df.columns = [a + '_rld' for a in i_df.columns]
#             scen_dict[date][scen_type][i] = i_df
            
# aux_dict = {key: scen_dict[key] for key in list(scen_dict)[2:]}

# del scen_dict


params_dict = {}
params_dict = {}
# params_dict['market_list'] = ['de', 'fr', 'hu'] * 4
# params_dict['product_list'] = ['W_1', 'W_2', 'M_1', 'M_2']*3
# params_dict['market_list'] = ['de']*3 + ['fr']*3
# params_dict['product_list'] = ['W_1', 'W_2', 'W_3']*2
params_dict['market_list'] = ['de']*3
params_dict['product_list'] = ['M_1', 'M_2', 'M_3']


params_dict['delivery_list'] = ['base'] * len(params_dict['product_list'])
params_dict['year_list'] = [2024] * len(params_dict['market_list'])
params_dict['sD'] = dt.datetime(2020,1,1)
params_dict['eD'] = pd.to_datetime(dt.datetime.today().date())
params_dict['eD'] = dt.datetime(2024,7,26)
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

# file_name = r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Strategies\SpotMM\DE_FR_W1_W2\fcst_curve_dict.pickle'

# with open(file_name, 'rb') as file:
    # fcst_curve_dict = pickle.load(file)
    
# pm_inst.fcst_curve_dict = fcst_curve_dict


scen_dict2 = {dt.datetime(2024,7,10):{'liq':{}}}

# spread_dict = pm_inst.get_country_spread(model_params_dict, scen_dict)

# spread_dict = pm_inst.get_calendar_spread(model_params_dict, scen_dict2)

prod_dict = pm_inst.get_product_forecast(model_params_dict, scen_dict)
# fcst_range_curves = pm_inst.get_fcst_for_range(fcst_range, model_params_dict)
# scenario_fcst_dict = pm_inst.get_scenario_forecast(model_params_dict, aux_dict)