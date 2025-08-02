# -*- coding: utf-8 -*-
"""
Created on Wed Jan 17 14:41:55 2024

@author: krajcovic
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import datetime as dt
import matplotlib.pyplot as plt
import seaborn as sns
# from Spot.Monitor_class import SettleMonitor as SM
from Spot.Monitor_class import RldMonitor as RM
from sklearn.linear_model import LinearRegression

import statsmodels.api as sm



sD = datetime(2013,1,1)
eD = datetime(2024,1,17)
mon_inst = RM()
mon_inst.set_date_range(sD, eD)

# raw_normal = mon_inst.get_raw_data(normal=True)
# raw_data = mon_inst.get_raw_data()

raw_norm_data = mon_inst.get_raw_data_normalized()

matrix = mon_inst.data_matrix(raw_norm_data)

matrix_chng = matrix.shift(-1).shift(24,axis=1)-matrix
# 
# data_matrix = mon_inst.data_matrix(raw_data)

# data_da = mon_inst.get_da_data(data_matrix)

# normalized_curve = mon_inst.get_rld_curve(normalize=True)

# data_chng_dict = mon_inst.get_hist_changes()

# test = mon_inst.rld_chng_mask(data_matrix, mask_type='hist_position')

# masks = mon_inst.generate_masks(data_matrix)



# df1, df2, df3, df4, df5, df6 = [aligned_dfs[a] for a in aligned_dfs.keys()]

# keys = ['month', 'weekday', 'hour', 'value_quant', 'hist_quant', 'fcst_days']
values = [9, 0, 1,4,0,14]
mask = mon_inst.get_mask(values, matrix_chng, matrix)
test = matrix_chng[mask].copy()
non_nan_mask = ~test.isna()

# Use this mask to select non-NaN values from the DataFrame, then flatten the result
non_nan_values = test[non_nan_mask].values.flatten()

# Remove NaN values from the flattened array (if there are any left)
non_nan_values = non_nan_values[~np.isnan(non_nan_values)]
non_nan_list = non_nan_values.tolist()
# filtered_df = mon_inst.filter_values(values, data_matrix)


sns.histplot(data=non_nan_values,kde=True)
plt.axvline(np.mean(non_nan_values))

plt.show()
# # Check if keys list and values list have the same length to avoid errors
# if len(keys) != len(values):
#     raise ValueError("Keys and values lists must have the same length")

# # Initialize the result with the comparison of the first DataFrame
# result = aligned_dfs[keys[0]] == values[0]

# # Loop through the remaining keys and values, updating the result
# for key, value in zip(keys[1:], values[1:]):  # Start from the second item
#     result &= (aligned_dfs[key] == value) 


# normal_matrix = mon_inst.normal_matrix(raw_normal)

