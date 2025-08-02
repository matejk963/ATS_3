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
import os
from pandas.tseries.offsets import Week

# # To load the dictionary from the file
# with open(r"Z:\Data\Scenarios\scen_dict_20240401_20240601_3.pickle", 'rb') as file:
#     scen_dict = pickle.load(file)
# # scen_dict = {i: scen_dict[i] for i in range(len(scen_dict))}
# for date, date_dict in scen_dict.items():
#     for scen_type, scen_type_dict in date_dict.items():        
#         for i, i_df in scen_type_dict.items():
#             i_df.columns = [a + '_rld' for a in i_df.columns]
#             scen_dict[date][scen_type][i] = i_df
            
# aux_dict = {key: scen_dict[key] for key in list(scen_dict)[:2]}

# aux_dict = {key: scen_dict[key] for key in
#             pd.date_range(start=dt.datetime(2024,5,1),
#                           end=dt.datetime(2024,5,4))}



params_dict = {}
params_dict = {}
params_dict['market_list'] = ['de']*3
params_dict['product_list'] = ['W_1', 'W_2', 'W_3', 'M_1']
# params_dict['market_list'] = ['de']*2
# params_dict['product_list'] = ['W_2' ,'W_3']


params_dict['delivery_list'] = ['base'] * len(params_dict['market_list'])
params_dict['year_list'] = [2024] * len(params_dict['market_list'])
params_dict['sD'] = dt.datetime(2022,6,22)
params_dict['eD'] = dt.datetime(2024,7,13)
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

scen_dict2 = {a:{'liq':{}} for a in pd.date_range(start=dt.datetime(2024,1,1),
                                                  end=dt.datetime(2024,7,1),
                                                  freq='B')}


spread_dict = pm_inst.get_calendar_spread(model_params_dict, scen_dict2)

folder_path = r'Z:\Data\Scenarios\Scenario_prices'
file_name = 'de_w1_w2_nominal_20240101_20240701.pickle'
file_path = os.path.join(folder_path, file_name)

with open(file_path, 'wb') as file:
    # Step 4: Serialize the dictionary and write it to the file
    pickle.dump(spread_dict, file)



# def scatter_plot_from_dfs(dfs_dict, col1, col2):
#     # Initialize dictionaries to collect values for each specified row
#     data_first = {col1: [], col2: []}
#     data_50th = {col1: [], col2: []}
#     data_100th = {col1: [], col2: []}
#     data_200th = {col1: [], col2: []}
    
#     # Iterate over each DataFrame in the dictionary
#     for key, df in dfs_dict.items():
#         # Ensure the DataFrame has enough rows
#         if len(df) > 200:
#             # Append values for the specified rows
#             data_first[col1].append(df.iloc[0][col1])
#             data_first[col2].append(df.iloc[0][col2])
            
#             data_50th[col1].append(df.iloc[49][col1])
#             data_50th[col2].append(df.iloc[49][col2])
            
#             data_100th[col1].append(df.iloc[99][col1])
#             data_100th[col2].append(df.iloc[99][col2])
            
#             data_200th[col1].append(df.iloc[199][col1])
#             data_200th[col2].append(df.iloc[199][col2])
    
#     # Function to create scatter plot
#     def create_scatter_plot(data, row_number):
#         plt.figure(figsize=(8, 6))
#         plt.scatter(data[col1], data[col2], label=f'Row {row_number}')
#         plt.xlabel(col1)
#         plt.ylabel(col2)
#         plt.title(f'Scatter Plot for Row {row_number}')
#         plt.legend()
#         plt.grid(True)
#         plt.show()

#     # Create scatter plots for each specified row
#     create_scatter_plot(data_first, 1)
#     create_scatter_plot(data_50th, 50)
#     create_scatter_plot(data_100th, 100)
#     create_scatter_plot(data_200th, 200)
    
# def scatter_plot_from_dfs(dfs_dict, col1, col2, datetime_list):
#     # Initialize a dictionary to collect values for each specified datetime
#     data_by_datetime = {dt: {col1: [], col2: []} for dt in datetime_list}
    
#     # Iterate over each DataFrame in the dictionary
#     for key, df in dfs_dict.items():
#         # Check for each datetime in the list if it exists in the DataFrame's index
#         for dt in datetime_list:
#             if dt in df.index:
#                 data_by_datetime[dt][col1].append(df.loc[dt, col1])
#                 data_by_datetime[dt][col2].append(df.loc[dt, col2])
    
#     # Function to create scatter plots for each datetime
#     def create_scatter_plot(data, datetime_value):
#         plt.figure(figsize=(8, 6))
#         plt.scatter(data[col1], data[col2], label=f'Data from {datetime_value}')
        
#         # Calculate the means for col1 and col2
#         mean_col1 = sum(data[col1]) / len(data[col1])
#         mean_col2 = sum(data[col2]) / len(data[col2])
        
#         # Add vertical line at mean of col1 and horizontal line at mean of col2
#         plt.axvline(mean_col1, color='r', linestyle='--', label=f'Mean {col1}: {mean_col1:.2f}')
#         plt.axhline(mean_col2, color='b', linestyle='--', label=f'Mean {col2}: {mean_col2:.2f}')
        
#         plt.xlabel(col1)
#         plt.ylabel(col2)
#         plt.title(f'Scatter Plot for {datetime_value}')
#         plt.legend()
#         plt.grid(True)
#         plt.show()

#     # Create scatter plots for each datetime
#     for dt, data in data_by_datetime.items():
#         create_scatter_plot(data, dt)
        
# def scatter_plot_from_dfs(dfs_dict, col1, col2, datetime_list):
#     # Initialize a dictionary to collect average values for each week around specified datetimes
#     weekly_data = {dt: {col1: [], col2: []} for dt in datetime_list}
    
#     # Iterate over each DataFrame in the dictionary
#     for key, df in dfs_dict.items():
#         # Resample the DataFrame to weekly data centered around each datetime in the list
#         for dt in datetime_list:
#             # Define the week range around the datetime
#             week_start = dt - Week(weekday=0)  # Adjust the weekday as needed
#             week_end = dt + Week(weekday=6)
            
#             # Filter data for this week
#             weekly_df = df[(df.index >= week_start) & (df.index <= week_end)]
            
#             if not weekly_df.empty:
#                 weekly_data[dt][col1].append(weekly_df[col1].mean())
#                 weekly_data[dt][col2].append(weekly_df[col2].mean())

#     # Function to create scatter plots for each week
#     def create_scatter_plot(data, datetime_value):
#         plt.figure(figsize=(8, 6))
#         plt.scatter(data[col1], data[col2], label=f'Weekly Avg from {datetime_value.strftime("%Y-%m-%d")}')
        
#         # Calculate the means for col1 and col2
#         mean_col1 = sum(data[col1]) / len(data[col1]) if data[col1] else None
#         mean_col2 = sum(data[col2]) / len(data[col2]) if data[col2] else None
        
#         # Add vertical and horizontal lines for means, if any data exists
#         if mean_col1 is not None and mean_col2 is not None:
#             plt.axvline(mean_col1, color='r', linestyle='--', label=f'Mean {col1}: {mean_col1:.2f}')
#             plt.axhline(mean_col2, color='b', linestyle='--', label=f'Mean {col2}: {mean_col2:.2f}')
        
#         plt.xlabel(col1)
#         plt.ylabel(col2)
#         plt.title(f'Scatter Plot for Week of {datetime_value.strftime("%Y-%m-%d")}')
#         plt.legend()
#         plt.grid(True)
#         plt.show()

#     # Create scatter plots for each week
#     for dt, data in weekly_data.items():
#         create_scatter_plot(data, dt)
        
# # def scatter_plot_from_dfs(dfs_dict, col1, col2, datetime_list):
# #     # Initialize a dictionary to collect average values for each day around specified datetimes
# #     daily_data = {dt.date(): {col1: [], col2: []} for dt in datetime_list}
    
# #     # Iterate over each DataFrame in the dictionary
# #     for key, df in dfs_dict.items():
# #         # For each datetime, get data for that specific day
# #         for dt in datetime_list:
# #             day_data = df[df.index.date == dt.date()]

# #             if not day_data.empty:
# #                 daily_data[dt.date()][col1].append(day_data[col1].mean())
# #                 daily_data[dt.date()][col2].append(day_data[col2].mean())

# #     # Function to create scatter plots for each day
# #     def create_scatter_plot(data, date_value):
# #         plt.figure(figsize=(8, 6))
# #         plt.scatter(data[col1], data[col2], label=f'Daily Avg from {date_value}')
        
# #         # Calculate the means for col1 and col2
# #         mean_col1 = sum(data[col1]) / len(data[col1]) if data[col1] else None
# #         mean_col2 = sum(data[col2]) / len(data[col2]) if data[col2] else None
        
# #         # Add vertical and horizontal lines for means, if any data exists
# #         if mean_col1 is not None and mean_col2 is not None:
# #             plt.axvline(mean_col1, color='r', linestyle='--', label=f'Mean {col1}: {mean_col1:.2f}')
# #             plt.axhline(mean_col2, color='b', linestyle='--', label=f'Mean {col2}: {mean_col2:.2f}')
        
# #         plt.xlabel(col1)
# #         plt.ylabel(col2)
# #         plt.title(f'Scatter Plot for {date_value}')
# #         plt.legend()
# #         plt.grid(True)
# #         plt.show()

# #     # Create scatter plots for each day
# #     for date, data in daily_data.items():
# #         create_scatter_plot(data, date)
    

# scatter_plot_from_dfs(scen_dict[dt.datetime(2024,5,2)]['liq'], 'de_rld',
#                       'fr_rld', [dt.datetime(2024,5,8,12)])
