# -*- coding: utf-8 -*-
"""
Created on Mon Apr  8 13:20:45 2024

@author: krajcovic
"""

import pandas as pd
import numpy as np
import datetime as dt

from Spot.SpotModelClass import PowerModel as PM


# Create dictionary for parameters
params_dict = {}
params_dict['market_list'] = ['de'] * 11 + ['fr'] * 11 + ['hu']*11
params_dict['product_list'] = ['W_1', 'W_2' ,'W_3', 
                                'M_1', 'M_2', 'M_3', 'M_4',
                                'Q_1', 'Q_2', 'Q_3', 'Q_4'] * 3
# params_dict['market_list'] = ['de']*2
# params_dict['product_list'] = ['W_2' ,'W_3']


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
    


spreads = {}
spreads['country'] = {}
spreads['calendar'] = {}
for date, date_dict in curves_dict.items():
    for model, model_dict in date_dict.items():
        for spread_type in ['country', 'calendar']:
            if not model in list(spreads[spread_type]):
                spreads[spread_type][model] = pd.DataFrame()
        for delivery, df in model_dict.items():
            if not 'product_list' in df.columns:
                df.reset_index(inplace=True)
            df['spread'] = df['de'] - df['fr']
            df['product_type'] = df['product_list'].apply(get_product_type)
            df['product_type'] = pd.Categorical(df['product_type'], categories=product_order, ordered=True)
            df_sorted = df.sort_values(by=['product_type', 'del_start'])
            df_sorted.set_index(['product_list', 'year_list', 'del_start'], inplace=True)
            # Iterate over the columns that do not contain 'spread' and are numeric
            df_sorted[['de', 'fr', 'spread']] = df_sorted[['de', 'fr', 'spread']].astype(float)
            numeric_cols = [a for a in df_sorted.select_dtypes(include=['float64']).columns
                            if 'spread' not in a]
            
            for column in numeric_cols:
                if 'spread' not in column:
                    # Sequential differences within each product type for the current column
                    df_sorted[f'seq_diff_{column}'] = df_sorted.groupby('product_type', observed=False)[column].diff()
                    
                    # Get the first month's value for the current column
                    first_month_value = df_sorted[df_sorted['product_type'] == 'month'][column].iloc[0]
                    
                    # Differences of each week's value to the first month's value for the current column
                    df_sorted[f'week_to_month_{column}'] = df_sorted.apply(lambda row: row[column] - first_month_value if row['product_type'] == 'week' else None, axis=1)
                    
                    # Differences of each month's value to the quarter it belongs to for the current column
                    def month_to_quarter_diff(row):
                        if row['product_type'] == 'month':
                            quarter_start = pd.Timestamp(year=row.name[1], month=((row.name[2].month - 1) // 3) * 3 + 1, day=1)
                            quarter_value = df_sorted[(df_sorted['product_type'] == 'quarter') & (df_sorted.index.get_level_values('del_start') == quarter_start)][column]
                            if not quarter_value.empty:
                                return row[column] - quarter_value.iloc[0]
                        return None
                    
                    df_sorted[f'month_to_quart_{column}'] = df_sorted.apply(month_to_quarter_diff, axis=1)
            df_sorted.drop(columns=['product_type'], inplace=True)
            for spread_type in ['country', 'calendar']:
                if spread_type in ['country']:
                    spread = df_sorted[['spread']].copy()
                    spread = spread.rename(columns={'spread': date})
                elif spread_type in ['calendar']:
                    # spread = df_sorted.drop(columns=['spread']).copy()
                    spread = df_sorted[['fr']].copy()
                    spread = spread.rename(columns={'fr': date})
                    
                # aux = pd.MultiIndex.from_product([[model], aux.columns])
                if spreads[spread_type][model].empty:
                    spreads[spread_type][model] = spread.copy()
                else:
                    spreads[spread_type][model] = pd.concat([spreads[spread_type][model],
                                                             spread],
                                                            axis=1)
                
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
            
data_collection = pm_inst.data_collection

# fcst_dict = pm_inst.fcst_dict

# data1 = fcst_dict['xgboost']['nominal']['de_M.5_2024_base']
# data2 = fcst_dict['xgboost']['nominal']['de_M.6_2024_base']

# pm_inst.fit_model(train_dict, model_params_dict)