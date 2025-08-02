# -*- coding: utf-8 -*-
"""
Created on Mon Apr  8 13:20:45 2024

@author: krajcovic
"""

import pandas as pd
import numpy as np
import datetime as dt
import itertools

from Spot.SpotModelClass import PowerModel as PM


# Create dictionary for parameters
params_dict = {}
params_dict['market_list'] = ['de'] * 11 + ['fr'] * 11 + ['hu']*11
params_dict['product_list'] = ['W_1', 'W_2' ,'W_3', 
                                'M_1', 'M_2', 'M_3', 'M_4',
                                'Q_1', 'Q_2', 'Q_3', 'Q_4'] * 3
# params_dict['market_list'] = ['de']*3
# params_dict['product_list'] = ['W_1', 'W_2' ,'W_3']


params_dict['delivery_list'] = ['base'] * len(params_dict['market_list'])
params_dict['year_list'] = [2024] * len(params_dict['market_list'])
params_dict['sD'] = dt.datetime(2022,6,22)
params_dict['eD'] = dt.datetime(2024,6,10)
params_dict['ns'] = 2
params_dict['cont'] = False

pm_inst = PM(params_dict)
# pm_inst.set_pivot_date(dt.datetime(2024,4,26))

# fuels_data = pm_inst.get_fuel_data()

# da_data = pm_inst.assemble_da_data()

# train_dict = pm_inst.create_train_data(da_data)

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
model_params_dict['xgboost']['hu'] = {'alpha': 0.010895398859824533, 'colsample_bytree': 0.9622126960415747,
          'gamma': 0.22653480769373827, 'lambda': 0.19084485197671305,
          'learning_rate': 0.02690767935041876, 'max_depth': 16, 'min_child_weight': 11,
          'n_estimators': 167, 'subsample': 0.2106044847212501}
model_params_dict['xgboost']['hu']['scaler'] = 'yeojohnson'
# model_params_dict['extratrees'] = {'n_estimators': 200,
#                                       'random_state': 0}

# data_dict = pm_inst.create_fcst_curves(train_dict, model_params_dict)



fcst_range = pd.date_range(dt.datetime(2024,6,7), dt.datetime(2024,6,10), freq='B')

# scen_fcst_dict = pm_inst.get_scenario_forecast(fcst_range,model_params_dict,
#                                                scen_data_dict, nominal=True)

curves_dict = pm_inst.get_fcst_for_range(fcst_range,model_params_dict, nominal=True)
# curves_dict2 = pm_inst.get_fcst_for_range(fcst_range,model_params_dict, nominal=False)


product_order = ['day', 'weekend', 'week', 'month', 'quarter', 'year']
# Extract the product type from the product_list
def get_product_type(product):
    if 'M.' in product:
        return 'month'
    elif 'Q.' in product:
        return 'quarter'
    elif 'W.' in product:
        return 'week'
    else:
        return 'unknown'
    
curve_dict2 = curves_dict.copy()
spreads = {}
spreads['country'] = {}
spreads['calendar'] = {}
for date, date_dict in curve_dict2.items():
    for model, model_dict in date_dict.items():
        for spread_type in ['country', 'calendar']:
            if not model in list(spreads[spread_type]):
                spreads[spread_type][model] = {}
        for delivery, df in model_dict.items():
            for spread_type in ['country', 'calendar']:
                if not delivery in list(spreads[spread_type][model]):
                    spreads[spread_type][model][delivery] = {}
            product_list, year_list, del_start = [df.reset_index()[a].to_list()
                                                  for a in ['product_list',
                                                                    'year_list',
                                                                    'del_start']]
            for c1, c2 in list(itertools.combinations(df.columns,2)):                
                spread_name = c1 + '_' + c2                
                if not spread_name in list(spreads['country'][model][delivery]):
                    spreads['country'][model][delivery][spread_name] = pd.DataFrame()
                df[spread_name] = df[c1] - df[c2]
                if spreads['country'][model][delivery][spread_name].empty:
                    spreads['country'][model][delivery][spread_name] = df[[spread_name]].rename(columns={spread_name: date})
                else:
                    spreads['country'][model][delivery][spread_name] = pd.concat([spreads['country'][model][delivery][spread_name],
                                                                                  df[[spread_name]].rename(columns={spread_name: date})],
                                                                                 axis=1)
            for country in df.columns:
                aux = pd.DataFrame(df['de'].values.reshape(-1,1)
                                    - df['de'].values.reshape(1,-1),
                                    index=df.index, columns=df.index)
                if not date in list(spreads['calendar'][model][delivery]):
                    spreads['calendar'][model][delivery][date] = {}
                
                spreads['calendar'][model][delivery][date][country] = aux
                
                
            
    


