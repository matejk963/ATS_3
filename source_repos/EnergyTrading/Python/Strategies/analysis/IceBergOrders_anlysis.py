# -*- coding: utf-8 -*-
"""
Created on Wed Dec 20 16:25:13 2023

@author: krajcovic
"""

from datetime import datetime, time
import pandas as pd
import numpy as np
from Database.TPData import TPDataDa
from scipy.stats import skew, kurtosis
import matplotlib.pyplot as plt
import seaborn as sns
plt.ion()

import os

# Add your Oracle Client's bin directory to the PATH
oracle_client_bin_path = r'C:\oracle\instantclient_19_9'
os.environ['PATH'] = oracle_client_bin_path + ';' + os.environ['PATH']

# Now you can import and use libraries that rely on the updated PATH
import cx_Oracle

data_class = TPDataDa()

mkt_list = ['de']
tenor_list = ['m']
tn1_list = [1]
tn2_list = [2]
prod = 'base'
venue_list = ['eex']
start_date = datetime(2023, 12, 20)
end_date = datetime(2023, 12, 20)
n_s = 2

dates = pd.date_range(start_date, end_date, freq='B')
product_date1 = [dates.shift(1, freq='B') if t == 'da' else
                 dates.shift(1, freq='D') if t == 'd' else
                 dates.shift(tn, freq='W-MON') if t == 'w' else
                 (dates + n_s * dates.freq).shift(tn, freq='2QS-Apr') if t in ['sum', 'win'] else
                 (dates + n_s * dates.freq).shift(tn, freq=t.upper() + 'S')
                 for t, tn in zip(tenor_list, tn1_list)]
if not tn2_list:
    product_date2 = [None] * len(product_date1)
else:
    product_date2 = [dates.shift(1, freq='B') if t == 'da' else
                     dates.shift(1, freq='D') if t == 'd' else
                     dates.shift(tn, freq='W-MON') if t == 'w' else
                     (dates + n_s * dates.freq).shift(tn, freq='2QS-Apr') if t in ['sum', 'win'] else
                     (dates + n_s * dates.freq).shift(tn, freq=t.upper() + 'S')
                     for t, tn in zip(tenor_list, tn2_list)]

if not tn2_list:
    tn_list = [str(t1) for t1 in tn1_list]
else:
    tn_list = [str(t1) + '_' + str(t2) for (t1, t2) in zip(tn1_list, tn2_list)]

start_time = time(8, 0, 0)
end_time = time(20, 0, 0)


# df_ord_data = data_class.get_orders_data(mkt, tenor, venue_list, start_date,
#                                          bT, eT, prod)

ba_data_dict = {m + t + n: [] for m, t, n in zip(mkt_list, tenor_list, tn_list)}
tr_data_dict = {m + t + n: [] for m, t, n in zip(mkt_list, tenor_list, tn_list)}

for m, t, n, p1_d, p2_d in zip(mkt_list, tenor_list, tn_list, product_date1,
                               product_date2):
    df_ba = pd.DataFrame([])
    df_tr = pd.DataFrame([])
    df_ob = pd.DataFrame([])
    if p2_d is None:
        df_prod_dates = pd.DataFrame([p1_d], columns=dates).T
    else:
        df_prod_dates = pd.DataFrame([p1_d, p2_d], columns=dates).T
    for p_d, ds in df_prod_dates.groupby(0).groups.items():
        bT = datetime.combine(ds[0], start_time)
        eT = datetime.combine(ds[-1], end_time)
        if p2_d is None:
            pd_2 = None
        else:
            pd_2 = df_prod_dates.loc[ds[0], 1]
        # # Bid Ask
        # # data_class.create_connection('PostgreSQL')
        # df_ba_aux = data_class.get_best_orders_data(m, t, p_d, bT, eT, prod,
        #                                             pd_2)
        # df_ba_aux = df_ba_aux.between_time(start_time, end_time)
        # #df_ba_aux = data_class.filter_data(df_ba_aux, df_ba_aux['bidbestprice'], 20)
        # df_ba = pd.concat([df_ba, df_ba_aux])
        # # Trades
        # # data_class.create_connection('OracleSQL')
        # df_tr_aux = data_class.get_trades(m, t, venue_list, p_d, bT, eT, prod,
        #                                   pd_2)
        # df_tr_aux = df_tr_aux.between_time(start_time, end_time)
        # df_tr_aux = data_class.filter_data(df_tr_aux, df_tr_aux['price'], 20)
        # df_tr = pd.concat([df_tr, df_tr_aux])
        # Orders
        # data_class.create_connection('OracleSQL')
        df_ob_aux = data_class.get_orders_data(m, t, venue_list, p_d, bT, eT, prod,
                                          pd_2)
        df_ob_aux = df_ob_aux.between_time(start_time, end_time)
        df_ob_aux = data_class.filter_data(df_ob_aux, df_ob_aux['price'], 20)
        df_ob = pd.concat([df_ob, df_ob_aux])
        
        

def investigate_distribution(dataframe, column):
    """
    Investigate the moments of distribution and selected percentiles of a specified column 
    in a DataFrame and plot its distribution.

    Parameters:
    dataframe (pd.DataFrame): The DataFrame containing the data.
    column (str): The column name to investigate.

    Returns:
    dict: A dictionary containing the calculated moments of distribution and percentiles.
    """
    
    # Ensure the column exists in the DataFrame
    if column not in dataframe.columns:
        raise ValueError(f"The column '{column}' does not exist in the DataFrame.")

    # Descriptive statistics
    mean_value = dataframe[column].mean()
    median_value = dataframe[column].median()
    variance_value = dataframe[column].var()  # pandas uses ddof=1 by default (sample variance)
    skewness_value = skew(dataframe[column])
    kurtosis_value = kurtosis(dataframe[column])
    percentile_75th = np.percentile(dataframe[column], 75)
    percentile_90th = np.percentile(dataframe[column], 90)

    # Output the descriptive statistics
    moments = {
        'Mean': mean_value,
        'Median': median_value,
        'Variance': variance_value,
        'Skewness': skewness_value,
        'Kurtosis': kurtosis_value,
        '75th Percentile': percentile_75th,
        '90th Percentile': percentile_90th
    }
    
    for moment, value in moments.items():
        print(f"{moment}: {value}")

    # Plot the distribution
    plt.figure(figsize=(10, 6))
    sns.histplot(dataframe[column], kde=True, bins=20)
    plt.title(f'Distribution of {column}')
    plt.xlabel(column)
    plt.ylabel('Frequency')
    plt.grid(True)
    plt.show()

    return moments

def plot_joint_distribution(dataframe, column1, column2):
    """
    Plot the joint distribution of two specified columns in a DataFrame.

    Parameters:
    dataframe (pd.DataFrame): The DataFrame containing the data.
    column1 (str): The first column name.
    column2 (str): The second column name.
    """
    
    # Ensure the columns exist in the DataFrame
    if column1 not in dataframe.columns or column2 not in dataframe.columns:
        raise ValueError(f"One or both columns '{column1}' and '{column2}' do not exist in the DataFrame.")

    # Plot the joint distribution using seaborn
    plt.figure(figsize=(10, 8))
    sns.jointplot(x=column1, y=column2, data=dataframe, kind="hex", color="b")
    plt.title(f'Joint Distribution of {column1} and {column2}', pad=80)
    plt.show()

trades = df_tr.dropna()

# Create a new column 'group' that changes every time 'price' changes
trades['group'] = trades['price'].ne(trades['price'].shift()).cumsum()

# Perform the cumulative sum within each group
trades['cumulative_volume'] = trades.groupby('group')['volume'].cumsum()
# Perfomr the cumulative average within each gropu
trades['average_action'] = trades.groupby('group')['action'].cumsum()/\
    (trades.groupby('group')['action'].cumcount()+1)
trades = trades.reset_index()
    
sumed_trades = trades.groupby('group').last()
sumed_trades = sumed_trades.set_index('datetime')



moments = investigate_distribution(sumed_trades, 'cumulative_volume')
moments2 = investigate_distribution(sumed_trades.loc[sumed_trades['cumulative_volume']>=9], 'average_action')

plot_joint_distribution(sumed_trades, 'cumulative_volume', 'average_action')



