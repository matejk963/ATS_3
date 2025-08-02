# -*- coding: utf-8 -*-
"""
Created on Wed Jun 12 09:50:31 2024

@author: krajcovic
"""

from Spot.SpotModelClass_mark4 import PowerModel as PM
from Spot.Monitor_class import RldMonitor as RM

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import datetime as dt
import pickle

# To load the dictionary from the file
scen_dict = {}
with open(r'Z:\Data\Scenarios\Long scenario\daily 20230701_20230701 scen dicts\scen_date_20231211.pickle', 'rb') as file:
    scen_dict = pickle.load(file)
    
    

for date, date_dict in scen_dict.items():
    for scen_type, scen_type_dict in date_dict.items():        
        for i, i_df in scen_type_dict.items():
            i_df.columns = [a + '_rld' for a in i_df.columns]
            scen_dict[date][scen_type][i] = i_df
            
# aux_dict = {key: scen_dict[key] for key in list(scen_dict)[2:]}

# del scen_dict


base_products = ['W_1', 'W_2', 'W_3', 'M_1', 'M_2', 'M_3', 'Q_1', 'Q_2', 'Q_3']
base_products = ['Y_1']
market_list = ['de', 'fr', 'hu']
delivery_dict = ['base', 'peak']

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

params_dict['year_list'] = [None] * len(params_dict['market_list'])
params_dict['sD'] = dt.datetime(2020,1,1)
params_dict['eD'] = dt.datetime(2024,10,3)
params_dict['ns'] = 2
params_dict['cont'] = False


params_dict['delivery_list'] = ['base'] * len(params_dict['product_list'])
params_dict['year_list'] = [2024] * len(params_dict['market_list'])
params_dict['sD'] = dt.datetime(2020,1,1)
params_dict['eD'] = pd.to_datetime(dt.datetime.today().date())
params_dict['eD'] = dt.datetime(2024,10,3)
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
pm_inst.set_pivot_date(params_dict['eD'])
new_params_dict = pm_inst.transform_params_dict(pm_inst.pivot_date)
pm_inst.update_params_dict(new_params_dict)
pm_inst.raw_data = {}


pm_inst.assemble_raw_data()
da_data = pm_inst.assemble_da_data()

train_dict = pm_inst.create_train_data(da_data)
pm_inst.assemble_fcst_predictors(train_dict)

fcst_data = pm_inst.fcst_data.copy()

# Adjust for demand destruction
rm_inst = RM()
rm_inst.set_date_range(params_dict['sD'], params_dict['eD'])

# Initialize empty DataFrames for 'base', '25th', 'mean', '75th' scenarios
scen_dict2 = {params_dict['eD']: {'liq': {'base': pd.DataFrame(), '25th': pd.DataFrame(), 'mean': pd.DataFrame(), '75th': pd.DataFrame()}}}

# Initialize empty DataFrames for 'base', '25th', 'mean', '75th' scenarios
base_df = pd.DataFrame(index=fcst_data.index)
mean_df = pd.DataFrame(index=fcst_data.index)
q75th_df = pd.DataFrame(index=fcst_data.index)
q25th_df = pd.DataFrame(index=fcst_data.index)

for country in ['de', 'fr']:   
    if country in ['de', 'fr']:
        source = 'local'
    else:
        source = 'db'
    
    # Fetching data
    cons_norm = rm_inst.get_fund_data('normal', 'CON', '00', source=source, market=country)
    cons_ = rm_inst.get_fund_curve('CON', '00', market=country)
    cons_da = rm_inst.get_da_data(cons_)
    
    # Merging data
    cons_data = pd.merge(cons_da, cons_norm, how='left', on='value_date')

    # Calculating differences
    cons_data['diff'] = cons_data['rld_da'] - cons_data['CON']
    mean_diff = cons_data['diff'].iloc[-8760:].mean()
    diff_75th = cons_data['diff'].iloc[-8760:].quantile(q=0.75)
    diff_25th = cons_data['diff'].iloc[-8760:].quantile(q=0.25)

    # Defining the RLD column for the current country
    rld_name = country + '_rld'

    # Creating adjusted series for 'mean', '75th', and '25th'
    ser_base = fcst_data[[rld_name]]  # No adjustment for 'base'
    ser_mean = fcst_data[[rld_name]] + mean_diff
    ser_75th = fcst_data[[rld_name]] + diff_75th
    ser_25th = fcst_data[[rld_name]] + diff_25th

    # Flatten the 2D arrays to 1D before assigning to the DataFrame
    base_df[rld_name] = ser_base.values.flatten()
    mean_df[rld_name] = ser_mean.values.flatten()
    q75th_df[rld_name] = ser_75th.values.flatten()
    q25th_df[rld_name] = ser_25th.values.flatten()

# Now add these DataFrames to the dict after processing all countries
scen_dict2 = {
    params_dict['eD']: {
        'liq': {
            'base': base_df,
            '25th': q25th_df,
            'mean': mean_df,
            '75th': q75th_df
        }
    }
}



    

# fcst_data_de_adj = fcst_data.copy()
# fcst_data_de_adj['de_rld'] = fcst_data_de_adj['de_rld'] + mean_diff
# rld_de_75th = fcst_data[['de_rld']] + diff_75th
# rld_de_25th = fcst_data[['de_rld']] + diff_25th



# # scen_dict2 = {date:{'liq':{}} for date in pd.date_range(dt.datetime(2024,7,1), dt.datetime(2024,8,1),freq='B')}
# scen_dict2 = {params_dict['eD']:{'liq':{a:b for a,b in zip(['base', 'mean', '75th', '25th'],
#                                                            [fcst_data, fcst_data_de_adj,
#                                                             rld_de_75th, rld_de_25th])}}}

spread_dict = pm_inst.get_country_spread(model_params_dict, scen_dict2)

spread_dict2 = pm_inst.get_calendar_spread(model_params_dict, scen_dict2)

# prod_dict = pm_inst.get_product_forecast(model_params_dict, scen_dict2)
# fcst_range_curves = pm_inst.get_fcst_for_range(fcst_range, model_params_dict)
# scenario_fcst_dict = pm_inst.get_scenario_forecast(model_params_dict, aux_dict)
