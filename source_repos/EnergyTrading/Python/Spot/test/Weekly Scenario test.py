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
eD = datetime(2024,3,17)
mon_inst = RM()
mon_inst.set_date_range(sD, eD)

# scen_dict = mon_inst.get_scenarios(market='de',
#                                    days_fwd_list=[2],
#                                    source='local')

# # raw_normal = mon_inst.get_raw_data(normal=True)

# raw_data = mon_inst.get_raw_data()
# nominal_matrix = mon_inst.data_matrix(raw_data)

raw_norm_data = mon_inst.get_raw_data_normalized()

matrix = mon_inst.data_matrix(raw_norm_data)

# matrix_chng = matrix.shift(-3).shift(72,axis=1)-matrix

curve_da = mon_inst.get_da_data(matrix).set_index('value_date').resample('D').mean().rolling(14).mean().iloc[-1].values[0]

curve = matrix.iloc[[-1],72:].copy()
# nom_curve = nominal_matrix.iloc[[-1],72:].copy()
# norm_curve = nom_curve/curve
values_ser = mon_inst.get_curve_values(curve, matrix, curve_da)


# scen_ser = pd.DataFrame(index=[10,25,50,75,90,'real_value'])
# for hour in values_ser.index:
#     percentiles_list = []
#     scenario_list = []
#     curve_value = curve[hour].iloc[0]
#     values = values_ser[hour]
#     mask = mon_inst.get_mask(values,matrix_chng, matrix)
#     aux = matrix_chng[mask].copy()
#     non_nan_mask = ~aux.isna()
#     non_nan_values = aux[non_nan_mask].values.flatten()
#     non_nan_values = non_nan_values[~np.isnan(non_nan_values)]
#     for perc in [10,25,50,75,90]:
#         percentile = np.percentile(non_nan_values, perc)
#         scenario_list.append(curve_value+percentile)
#         percentiles_list.append(percentile)
#     scenario_list.append(curve_value)  
    
        
#     scen_ser[hour] = scenario_list

# scen_ser_act = scen_ser*pd.DataFrame([norm_curve.values[0] for a in range(len(scen_ser))],columns=scen_ser.columns,index=scen_ser.index) 
# scen_ser_act = scen_ser_act.T
# scen_ser_act.index = curve.index[0] + pd.to_timedelta(scen_ser_act.index,unit='h')

# # keys = ['month', 'weekday', 'hour', 'value_quant', 'hist_quant', 'fcst_days']
# values = [9, 0, 1,4,0,14]
# mask = mon_inst.get_mask(values, matrix_chng, matrix)
# test = matrix_chng[mask].copy()
# non_nan_mask = ~test.isna()

# # Use this mask to select non-NaN values from the DataFrame, then flatten the result
# non_nan_values = test[non_nan_mask].values.flatten()

# # Remove NaN values from the flattened array (if there are any left)
# non_nan_values = non_nan_values[~np.isnan(non_nan_values)]
# non_nan_list = non_nan_values.tolist()
# # filtered_df = mon_inst.filter_values(values, data_matrix)


# sns.histplot(data=non_nan_values,kde=True)
# plt.axvline(np.mean(non_nan_values))

# plt.show()


