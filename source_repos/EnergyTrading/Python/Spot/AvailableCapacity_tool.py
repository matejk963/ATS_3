# -*- coding: utf-8 -*-
"""
Created on Tue Sep 24 12:17:17 2024

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

def conditional_fill_pivot(pivot_df):
    """
    Function to process a pivoted DataFrame, filter columns closest to 12:00:00 for each date,
    and forward-fill NaN values to catch the latest update for each value_date.
    
    Parameters:
    pivot_df (pd.DataFrame): Pivoted DataFrame with `value_date` as index and `forecast_date` as columns.

    Returns:
    pd.DataFrame: Processed DataFrame with forward-filled values, where `value_date` is a regular column.
    """
    pivot_df.index = pd.to_datetime(pivot_df.index).floor('H')
    pivot_df = pivot_df.resample('H').mean()
    # Step 1: Create a new hourly index from the min to the max value_date
    hourly_index = pd.date_range(start=pd.to_datetime(pivot_df.index.min()), end=pivot_df.index.max(), freq='H')

    # Step 2: Reindex the DataFrame to hourly intervals without filling the missing values yet
    pivot_df_hourly = pivot_df.reindex(hourly_index)

    # Step 3: Select the column closest to 12:00:00 for each date
    forecast_times = pivot_df_hourly.columns

    # Create a mask where the value_date is greater than or equal to the forecast_date
    forecast_dates = pd.to_datetime(forecast_times.date)
    mask = np.greater_equal.outer(pd.to_datetime(pivot_df_hourly.index), forecast_dates)

    # Convert DataFrame to NumPy array for efficient processing
    values = pivot_df_hourly.to_numpy()

    # Step 4: Apply left-to-right fill (Horizontal pass)
    for i in range(1, values.shape[1]):
        # Ensure that we only forward-fill values where the value_date is greater than or equal to forecast_date
        values[:, i] = np.where(mask[:, i], np.where(np.isnan(values[:, i]), values[:, i - 1], values[:, i]), values[:, i])

    # Convert back to DataFrame
    filled_df = pd.DataFrame(values, index=pivot_df_hourly.index, columns=pivot_df_hourly.columns)

    # Step 5: Apply top-to-bottom fill (Vertical pass)
    filled_df = filled_df.ffill(axis=0)

    # Step 6: Apply another left-to-right fill to ensure all values are filled correctly
    values = filled_df.to_numpy()  # Convert DataFrame back to NumPy for efficiency
    for i in range(1, values.shape[1]):
        values[:, i] = np.where(mask[:, i], np.where(np.isnan(values[:, i]), values[:, i - 1], values[:, i]), values[:, i])

    # Convert back to DataFrame after the final left-to-right fill
    final_filled_df = pd.DataFrame(values, index=filled_df.index, columns=filled_df.columns)

    return final_filled_df

def filter_day_ahead_values(filled_df):
    """
    Function to filter day-ahead values from a DataFrame where value_date (index)
    is exactly one day after forecast_date (column).
    
    Parameters:
    filled_df (pd.DataFrame): A DataFrame where the index is value_date and columns are forecast_date.
    
    Returns:
    pd.Series: A single time series combining day-ahead values.
    """
    # Convert index and columns to `datetime.date` if they aren't already
    index_dates = pd.to_datetime(filled_df.index).date
    column_dates = pd.to_datetime(filled_df.columns)

    # Create a mask where the index is exactly one day after the column date
    mask = np.equal.outer(index_dates, (column_dates + pd.Timedelta(days=1)).date)

    # Apply the mask to the DataFrame to filter day-ahead values
    day_ahead_df = pd.DataFrame(
        np.where(mask, filled_df, np.nan),  # Keep values where mask is True, otherwise NaN
        index=filled_df.index,
        columns=filled_df.columns
    )

    # Forward fill to combine into a single time series, ensuring the most recent forecast is kept
    single_series = day_ahead_df.bfill(axis=1).iloc[:, 0]

    return single_series

def multiply_by_ratios(row):
    quarter = row['quarter']
    coal_value = row['Coal_de']
    
    # Get the corresponding row from 'all_ratios' based on the quarter
    ratios = all_ratios.loc[quarter]
    
    # Multiply each ratio by the 'Coal_de' value
    return coal_value * ratios


# Load long term av cap
file_path_de_ltav = r'C:\Users\krajcovic\Documents\Algo\Projects\Data\AvCapPC\DEU\LT_AvCap_DE.xlsx'
file_path_fr_ltav = r'C:\Users\krajcovic\Documents\Algo\Projects\Data\AvCapPC\FRA\LT_AvCap_FR.xlsx'

lt_av_de = pd.read_excel(file_path_de_ltav)
lt_av_de['Date'] = pd.to_datetime(lt_av_de['Date'])
lt_av_de = lt_av_de.set_index('Date').rename(columns={'Lignite': 'Lig_de',
                                                        'Coal': 'Coal_de',
                                                        'Gas': 'Gas_de'})
lt_av_fr = pd.read_excel(file_path_fr_ltav)
lt_av_fr['Date'] = pd.to_datetime(lt_av_fr['Date'])
lt_av_fr = lt_av_fr.set_index('Date').rename(columns={'Nuc': 'Nuc_fr',
                                                    'Coal': 'Coal_fr',
                                                    'Gas': 'Gas_fr'})


params_dict = {}
params_dict['product_list'] = ['Y_1']
params_dict['sD'] = dt.datetime(2019,12,25)
params_dict['eD'] = dt.datetime(2024,9,26)



# Fetch and adjust intalled capacity
am_inst = AM()
rm_inst = RM()
am_inst.set_date_range(params_dict['sD'],
                      params_dict['eD'])
rm_inst.set_date_range(params_dict['sD'],
                      params_dict['eD'])



av_cap_scenarios = {}

country = 'DEU'
source = 'Coal_de'

for country in ['DEU', 'FRA']:
    av_cap_scenarios[country] = {}

    #av_cap_da = am_inst.get_data_da(market='de', source='db')
    av_cap = rm_inst.get_fund_data_db('FUND_AvailCap', f'{country}_12')
    inst_cap = rm_inst.get_fund_data_db('FUND_InstCap', f'{country}_12')
    
    for source in av_cap.columns[2:]:
    
        # Create curves df
        av_cap_pivot = pd.pivot_table(av_cap[['forecast_date', 'value_date', source]],
                       index='value_date', columns='forecast_date',
                       values=source)
        inst_pivot = pd.pivot_table(inst_cap[['forecast_date', 'value_date', source]],
                       index='value_date', columns='forecast_date',
                       values=source)
        
        av_cap_curves = conditional_fill_pivot(av_cap_pivot)
        inst_curves = conditional_fill_pivot(inst_pivot)
        
        # Create DA data
        av_cap_da = filter_day_ahead_values(av_cap_curves)
        inst_da = filter_day_ahead_values(inst_curves)
        
        # Merget av cap and inst cap
        df = pd.concat([av_cap_da.dropna(),
                       inst_da.dropna()],axis=1,join='inner')
        df.columns = ['av_cap', 'inst']
        df['quarter'] = df.index.quarter
        df['ratio'] = df['av_cap']/df['inst']
        sel_index = df[df['ratio']>1].index
        df['av_cap'] = np.where(df['av_cap']>df['inst'],np.nan,df['av_cap'])
        df['av_cap'] = df['av_cap'].ffill()
        df['ratio_adj'] = df['av_cap']/df['inst']
        
        # Agregate ratios
        all_ratios = df[['ratio_adj', 'quarter']].groupby(['quarter']).mean()
        all_ratios.columns = ['mean_ratio']
        
        for quant_ten in range(10,100,10):
            quant = quant_ten/100
            temp = df[['ratio_adj', 'quarter']].groupby(['quarter']).quantile(quant)
            temp.columns = [f'q{quant_ten}_ratio']
            all_ratios = pd.concat([all_ratios, temp],axis=1)
        
        # Get curves for forecast dates
        latest_curve = inst_curves.iloc[:,[-1]].dropna().copy()
        latest_curve.columns = ['Coal_de']
        if country in ['DEU']:
            if source in ['Coal_de', 'Lig_de', 'Gas_de']:
                add_curve = lt_av_de[[source]]
            else:
                add_curve = pd.DataFrame([np.nan],
                                         index=[dt.datetime(2035,12,31,23)],
                                         columns=[latest_curve.columns[0]])
        if country in ['FRA']:
            if source in ['Coal_fr', 'Nuc_fr', 'Gas_fr']:
                add_curve = lt_av_fr[[source]]
            else:
                add_curve = pd.DataFrame([np.nan],
                                         index=[dt.datetime(2035,12,31,23)],
                                         columns=[latest_curve.columns[0]])
                
        latest_curve = pd.concat([latest_curve,
                                add_curve])
        latest_curve = latest_curve.resample('h').last().ffill()
        
        latest_curve['quarter'] = latest_curve.index.quarter
        
        # Create scenarios for source
        result_df = latest_curve.apply(multiply_by_ratios, axis=1)
        
        av_cap_scenarios[country][source] = result_df.copy()
        
        
folder_path = r'Z:\Data\Spot\Scenarios\AvCap'
file_path = os.path.join(folder_path, f"AvCap_scen_{params_dict['eD'].strftime('%Y%m%d')}.pkl")

with open(file_path, 'wb') as f:
    pickle.dump(av_cap_scenarios, f)
