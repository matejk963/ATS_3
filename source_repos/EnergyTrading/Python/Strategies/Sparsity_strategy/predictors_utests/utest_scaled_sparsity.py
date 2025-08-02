# -*- coding: utf-8 -*-
"""
Created on Wed Nov  6 16:47:33 2024

@author: scasny
"""
from datetime import datetime, timedelta
from Utilities.mock_functions import Mock
import json
import math


from Strategies.Sparse_momentum.ob_attributes import TR_attributes
import pandas as pd
import numpy as np


tr_class = TR_attributes(feature_list=['scaled_sparsity'])

dt_moments = Mock.mock_datetime(timedelta(days=2))
a_price_sparsity = Mock.mock_sparsity(len(dt_moments))
b_price_sparsity = Mock.mock_sparsity(len(dt_moments))

df_data = pd.DataFrame({'timestamp': dt_moments,
                        'b_price_sparsity': b_price_sparsity,
                        'a_price_sparsity': a_price_sparsity})
def generate_sp_dist(df_data):
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
    train_days = 1
    for i in range(train_days, df_data['day'].max()+1):
        df_hist = df_data[(df_data['day'] >= i-train_days) & (df_data['day'] < i)]
        df_curr = df_data[df_data['day'] == i]
        
        sp = sorted(df_hist['a_price_sparsity'].values)
        # Create a full range with steps of 0.01
        full_range = np.round(np.arange(0.0, 1.01, 0.01), 2)
        full_range = np.concatenate([full_range, [2.0]])
        sp = np.round(sp, 2)
        
        # Step 3: Fill missing values
        filled_sp = insert_missing_values(sp, full_range)
        filled_sp = sorted(filled_sp)
        # Save the list to a JSON file
    with open('todo.json', 'w') as file:
        json.dump(list(filled_sp), file)
        
def predictor_scaled_sparsity(b_price_sparsity, a_price_sparsity):
    FILENAME_SP_DISTRIBUTION_ = "todo.json"

    with open(FILENAME_SP_DISTRIBUTION_, 'r') as file:
        sp_distribution = np.array(json.load(file))

    if len(sp_distribution) < 1:
        raise ValueError(f"sp_distribution loading failed, name of file: {FILENAME_SP_DISTRIBUTION_}")
        
    length = len(sp_distribution)
        
    def approx_ppf(sparsity):
        p = np.where(sp_distribution == sparsity)[0][0] / length

        tol = 1e-5
        if p <= 0 or p >= 1:
            # Handle the boundary cases for p = 0 and p = 1
            if round(p, 2) <= 0:
                return -np.inf  # Approximate negative infinity for p = 0
            elif round(p, 2) >= 1:
                return np.inf  # Approximate positive infinity for p = 1
            else:
                raise ValueError("p must be in the range (0, 1)")

        # Constants for central approximation
        a = [2.50662823884, -18.61500062529, 41.39119773534, -25.44106049637]
        b = [-8.4735109309, 23.08336743743, -21.06224101826, 3.13082909833]

        # Polynomial approximation for the central region (0.08 < p < 0.92)
        if 0.08 < p < 0.92:
            q = p - 0.5
            r = q * q
            return q * (((a[3] * r + a[2]) * r + a[1]) * r + a[0]) / \
                ((((b[3] * r + b[2]) * r + b[1]) * r + b[0]) * r + 1.0)

        # Tail approximation for values near 0 and 1
        else:
            if p < 0.5:
                r = np.sqrt(-2.0 * np.log(p))
                return -(r - (2.515517 + 0.802853 * r + 0.010328 * r ** 2) /
                         (1 + 1.432788 * r + 0.189269 * r ** 2 + 0.001308 * r ** 3))
            else:
                r = np.sqrt(-2.0 * np.log(1.0 - p))
                return r - (2.515517 + 0.802853 * r + 0.010328 * r ** 2) / \
                    (1 + 1.432788 * r + 0.189269 * r ** 2 + 0.001308 * r ** 3)

    return math.erf((approx_ppf(a_price_sparsity) - approx_ppf(b_price_sparsity)) / 2)

generate_sp_dist(df_data)
org_sparsity = tr_class._feature_scaled_sparsity(df_data, train_days=1)
prod_sparsity = [predictor_scaled_sparsity(b, a)for b,a in zip(b_price_sparsity, a_price_sparsity)]
aa = pd.DataFrame({'org': org_sparsity, 'prod': prod_sparsity}).dropna()