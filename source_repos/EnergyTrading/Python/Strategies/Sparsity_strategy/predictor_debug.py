# -*- coding: utf-8 -*-
"""
Created on Fri Aug  2 14:24:26 2024

@author: scasny
"""
import numpy as np
import pandas as pd
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor
import concurrent
from sklearn.metrics import confusion_matrix
from multiprocessing import Pool, cpu_count
import time
import itertools
import scipy.stats as stats

df = pd.read_pickle("obt_reg_mqy.pkl")
df['pm_diff'] = df['p_movement_0.3'].diff(1)
_MID_P = 'p_movement_0.5'
_TOP_P = 'p_movement_1.0'
df['direct_str'] = df.apply(lambda row: row[_MID_P] > row[_TOP_P] if row[_TOP_P] > 0 else row[_MID_P] < row[_TOP_P], axis=1)
df['shift_a_s'] = df['a_price_sparsity'].shift(1)
df['shift_b_s'] = df['b_price_sparsity'].shift(1)
df['diff_ba_volrat'] = df['ba_volrat_30'].diff(1)



# sparsity_diff
def predictor_sparsity_diff(row):
    d_a_s = row['shift_a_s']
    d_b_s = row['shift_b_s']
    a_s = row['a_price_sparsity']
    b_s = row['b_price_sparsity']
    shift_ratio = np.tanh(-np.log10(d_b_s) + np.log10(d_a_s))
    current_ratio = np.tanh(-np.log10(b_s) + np.log10(a_s))
    return current_ratio - shift_ratio
# drop pd_diff == 0
dummy_data = {
    'a_price_sparsity': 0.31,
    'b_price_sparsity': 0.22,
    'shift_a_s': 0.16,
    'shift_b_s': 0.29,
    'diff_ba_volrat': 0.10}


# df['sparsity_diff'] = df.apply(predictor_sparsity_diff, axis=1)

import numpy as np
import matplotlib.pyplot as plt


# Define the combined function with adjustment constant
def combined_function(x):
    """ Calculate the value of the combined function given x and the inflection point x_inf. """
    def calculate_a(x_inf):
        """ Calculate the value of a given the inflection point x_inf. """
        if x_inf <= 0:
            raise ValueError("Inflection point must be positive.")
        return 1 / x_inf

    def find_intersection(func, x_range):
        """ Approximate where func(x) = 0 using a numerical search. """
        for i in range(len(x_range) - 1):
            x1, x2 = x_range[i], x_range[i + 1]
            y1, y2 = func(x1), func(x2)
            if y1 * y2 <= 0:  # Check if the function changes sign
                return (x1 + x2) / 2  # Return the midpoint as an approximation
        raise ValueError("No intersection found within the specified range.")

    def combined_function_1(x, a):
        """ First function where y = -log10(10 * a * x) if log_value < 0 """
        if x <= 0:
            raise ValueError("x must be positive for logarithm to be defined.")
        return -np.log10(10 * a * x)

    def combined_function_2(x, b):
        """ Second function where y = -log10(10 * b * x) """
        if x <= 0:
            raise ValueError("x must be positive for logarithm to be defined.")
        return np.log10(10 * b * -x)

    # Calculate the adjustment constant
    a = 0.6  # Inflection point
    b = 1  # Steepness coefficient

    # Define the numerical range for finding intersections
    x_range = np.linspace(0.01, 1, 1000)

    # Function to find where combined_function_1 crosses zero
    def func1(x):
        return combined_function_1(x, a)

    # Function to find where combined_function_2 crosses zero
    def func2(x):
        return combined_function_2(x, b)

    # Find intersection points
    x1 = find_intersection(func1, x_range)
    x2 = find_intersection(func2, x_range)

    # Calculate the adjustment constant as the difference between intersection points
    adjustment_constant = x2 - x1
    if x <= 0:
        raise ValueError("x must be positive for logarithm to be defined.")
    
    log_value = np.log10(10 * a * x)
    
    if log_value < 0:
        y = min(-log_value, 1)
    else:
        y = np.log10(10 * (b * -x + adjustment_constant))
    
    return y

# Plotting
x_values = np.linspace(0.01, 1, 100)
y_values = [combined_function(x) for x in x_values]

plt.plot(x_values, y_values)
plt.xlabel('x')
plt.ylabel('y')
plt.grid(True)
plt.show()




ratio = lambda a,b: np.tanh(((a/(a+b))-0.5)/0.5)
ratio = lambda a,b: np.cbrt((2*(a/(a+b))-1))



import pickle
from scipy.stats import norm
import math
import numpy as np

df_data = pickle.load(open(r"C:\develop\EnergyTrading\Python\Strategies\Sparsity_strategy\obt_reg_mqy.pkl", 'rb'))
df_data.reset_index(names='timestamp', inplace=True)
unique_dates = df_data['timestamp'].dt.date.unique()

curr_mean_list = []
curr_std_list = []
hist_mean_list = []
hist_std_list = []
day_list = []
col_name = 'a_price_sparsity'

def df_days_tag(df):
    unique_dates = df['timestamp'].dt.date.unique()
    
    # Create a dictionary to map unique dates to tags
    date_to_tag = {date: tag for tag, date in enumerate(unique_dates)}
    
    # Add a new column for the tags
    df['day'] = df['timestamp'].dt.date.map(date_to_tag)
    
    return df.copy()

df_data = df_days_tag(df_data).copy()




# Function to insert missing values into the sorted array
def insert_missing_values(sorted_array, full_range):
    updated_array = sorted_array.copy()  # Copy to avoid modifying the original array
    
    for value in full_range:
        if value not in updated_array:
            # Find the indices of the closest values before and after `value`
            index_prev = np.searchsorted(updated_array, value, side='left') - 1
            index_next = index_prev + 1
            
            # Handle cases where index_prev or index_next is out of range
            if index_prev < 0:
                index_prev = 0
            if index_next >= len(updated_array):
                index_next = len(updated_array) - 1
            
            # Insert the missing value into the sorted array
            updated_array = np.insert(updated_array, index_next, value)
    
    return updated_array

train_days = 5
for i in range(train_days, df_data['day'].max()+1):
    df_hist = df_data[(df_data['day'] >= i-train_days) & (df_data['day'] < i)]
    df_curr = df_data[df_data['day'] == i]
    
    sp = sorted(df_hist['a_price_sparsity'].values)
    # Create a full range with steps of 0.01
    full_range = np.round(np.arange(0.0, 1.01, 0.01), 2)
    sp = np.round(sp, 2)
    
    # Step 3: Fill missing values
    filled_sp = insert_missing_values(sp, full_range)
    length = len(filled_sp)
    
    func = lambda a: norm.ppf(np.where(filled_sp == a)[0][0]/length)
    df_data.loc[df_data['day'] == i, 'scaled_sparsity'] = df_curr.apply(
        lambda row: math.erf((func(row['a_price_sparsity'])-func(row['b_price_sparsity']))/2), axis=1)
    
df_data['sparsity_diff'] = df_data['scaled_sparsity'].diff(1)
    
    
