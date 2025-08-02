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

from Spot.SpotModelClass import PowerModel as PM

import pickle

# To load the dictionary from the file
with open(r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Algo\rld_scen_dict_20240527.pickle', 'rb') as file:
    scen_dict = pickle.load(file)
# scen_dict = {i: scen_dict[i] for i in range(len(scen_dict))}

for i, i_df in scen_dict.items():
    i_df.columns = [a + '_rld' for a in i_df.columns]
    scen_dict[i] = i_df

aux_dict = {}
aux_dict[5] = scen_dict
# aux_dict = {}
# for fwd_day, fwd_days_dict in scen_dict.items():
#     aux_dict[fwd_day] = {}
#     for grid, grid_list in fwd_days_dict.items():
#         # aux_dict[fwd_day][grid] = pd.DataFrame()
#         data_list = grid_list[0]
#         periods_list = grid_list[1]
#         aux_dict[fwd_day][grid] = pd.DataFrame(data_list,index=periods_list)
#         # aux = pd.DataFrame(columns=periods_list)
#         # for i, data_arr in enumerate(data_list):
#         #     aux[periods_list[i]] = data_arr
#         # aux_dict[fwd_day][grid] = aux.T
            
def combine_columns(data_dict):
    combined_dict = {}
    rand_cols = random.sample(list(range(1000)),100)
    # Iterate over each key1 in the dictionary
    for key1, key2_dict in data_dict.items():
        combined_dict[key1] = {}

        # Assuming each DataFrame in key2 has the same columns
        columns = list(key2_dict.values())[0].columns
        
        # Iterate over each column index
        for col in rand_cols:
            combined_df = pd.DataFrame()

            # Iterate over each key2 and collect the corresponding column
            for key2, df in key2_dict.items():
                combined_df[key2] = df[col]
            combined_df.columns = [a + '_rld' for a in combined_df.columns]
            # Add the combined DataFrame to the new dictionary
            combined_dict[key1][col] = combined_df

    return combined_dict

scen_data_dict = {}
scen_data_dict[dt.datetime(2024,5,27)] = aux_dict

# Create dictionary for parameters
params_dict = {}
# params_dict['market_list'] = ['de'] * 7 + ['fr'] * 7
# params_dict['product_list'] = ['M_1', 'M_2', 'M_3', 'M_4',
#                                'Q_1', 'Q_2', 'Q_3'] * 2
params_dict['market_list'] = ['de', 'fr']
params_dict['product_list'] = ['W_2']

params_dict['delivery_list'] = ['base'] * len(params_dict['market_list'])
params_dict['year_list'] = [2024] * len(params_dict['market_list'])
params_dict['sD'] = dt.datetime(2019,3,1)
params_dict['eD'] = dt.datetime(2024,5,27)
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
# model_params_dict['extratrees'] = {'n_estimators': 200,
#                                       'random_state': 0}

# data_dict = pm_inst.create_fcst_curves(train_dict, model_params_dict)



fcst_range = pd.date_range(dt.datetime(2024,5,27), dt.datetime(2024,5,27))

scen_fcst_dict = pm_inst.get_scenario_forecast(fcst_range,model_params_dict,
                                               scen_data_dict, nominal=True)

scen_df_dict = {}
for fcst_date, fcst_dict in scen_fcst_dict.items():
    for fwd_day, fwd_day_dict in fcst_dict.items():
        for scen, scen_dict in fwd_day_dict.items():
            for model, model_dict in scen_dict.items():
                if not model in list(scen_df_dict):
                    scen_df_dict[model] = {}
                aux = pd.DataFrame()
                for delivery, df in model_dict.items():
                    df.columns = [scen]
                    if not delivery in list(scen_df_dict[model]):
                        scen_df_dict[model][delivery] = df.copy()
                    else:
                        scen_df_dict[model][delivery] = pd.concat([scen_df_dict[model][delivery],
                                                                    df], axis=1).copy()
                        
scen_df = scen_df_dict['xgboost']['base']


df = scen_df.copy()
df.columns = df.columns.droplevel([1,2])
df['spread'] = df['de']-df['fr']
# Plotting individual histograms for each column
for column in df.columns:
    plt.figure(figsize=(10, 6))
    sns.histplot(df[column], bins=30, kde=True)
    plt.title(f'Distribution of {column}')
    plt.xlabel('Value')
    plt.ylabel('Frequency')
    plt.show()

# Plotting joint scatter plot with distributions for each pair of columns
g = sns.jointplot(x=df['W.22'], y=df['W.23'], kind='scatter', marginal_kws=dict(bins=30, fill=True))
g.set_axis_labels('W.22', 'W.23')
g.fig.suptitle('Joint Distribution for W.22 and W.23', y=1.02)
plt.show()
    

de_rld = pd.DataFrame()

for fcst_date, date_dict in scen_data_dict.items():
    for fwd_day, fwd_day_dict in date_dict.items():
        for scen, scen_df in fwd_day_dict.items():
            if de_rld.empty:
                de_rld = scen_df[['de_rld']].rename(columns={'de_rld': scen}).copy()
                
            else:
                de_rld = pd.concat([de_rld,
                                    scen_df[['de_rld']].rename(columns={'de_rld': scen})],axis=1) 

df = de_rld.copy()
# Assuming your DataFrame is named `df` and datetime is already set as index
# Calculate the percentiles
percentiles = np.arange(25, 75, 5)
percentile_values = df.apply(lambda x: np.percentile(x, percentiles), axis=1)
percentile_df = pd.DataFrame(percentile_values.tolist(), index=df.index, columns=[f'{p}th' for p in percentiles])

# Plot the percentiles
plt.figure(figsize=(12, 8))
for column in percentile_df.columns:
    plt.plot(percentile_df.index, percentile_df[column], label=column)

plt.title('Percentiles from 5th to 95th')
plt.xlabel('Time')
plt.ylabel('Value')
plt.legend(title='Percentile')
plt.grid(True)
plt.show()                   

# curves_dict = pm_inst.get_fcst_for_range(fcst_range,model_params_dict, nominal=True)
# curves_dict2 = pm_inst.get_fcst_for_range(fcst_range,model_params_dict, nominal=False)

# spreads = pd.DataFrame()
# for date, date_dict in curves_dict.items():
#     for model, model_dict in date_dict.items():
#         for delivery, df in model_dict.items():
#             df['spread'] = df['de'] - df['fr']
#             aux = df[['spread']]
#             aux = aux.rename(columns={'spread': date})
#             # aux = pd.MultiIndex.from_product([[model], aux.columns])
#             if spreads.empty:
#                 spreads = aux.copy()
#             else:
#                 spreads = pd.concat([spreads, aux],
#                                     axis=1)
                
# spreads_ghr = pd.DataFrame()
# for date, date_dict in curves_dict2.items():
#     for model, model_dict in date_dict.items():
#         for delivery, df in model_dict.items():
#             df['spread'] = df['de'] - df['fr']
#             aux = df[['spread']]
#             aux = aux.rename(columns={'spread': date})
#             # aux = pd.MultiIndex.from_product([[model], aux.columns])
#             if spreads_ghr.empty:
#                 spreads_ghr = aux.copy()
#             else:
#                 spreads_ghr = pd.concat([spreads_ghr, aux],
#                                     axis=1)
            
# data_collection = pm_inst.data_collection

# fcst_dict = pm_inst.fcst_dict

# data1 = fcst_dict['xgboost']['nominal']['de_M.5_2024_base']
# data2 = fcst_dict['xgboost']['nominal']['de_M.6_2024_base']

# pm_inst.fit_model(train_dict, model_params_dict)