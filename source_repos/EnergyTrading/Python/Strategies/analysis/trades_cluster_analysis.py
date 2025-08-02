# -*- coding: utf-8 -*-
"""
Created on Tue Jan 30 12:57:40 2024

@author: krajcovic
"""


import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.pyplot as plt
import datetime as dt
from datetime import datetime, timedelta

from Strategies.Intensity_class import TradeIntensity as TI
from Database.TPData import TPDataAssembly as TDA

from sklearn.cluster import DBSCAN


assembler = TDA(source='database')
params_dict = {}

params_dict['tenor_list'] = ['m']
params_dict['tn1_list'] = [1]
params_dict['mkt_list'] = ['ttf'] * len(params_dict['tenor_list'])
params_dict['tn2_list'] = []
params_dict['prod'] = 'base'
params_dict['venue_list'] = ['eex']*len(params_dict['mkt_list'])
params_dict['start_date'] = datetime(2023, 10, 1)
params_dict['end_date'] = datetime(2024, 1, 28)
params_dict['ns'] = 2

# Fetch trades and best orders for the curve
assembler = TDA(source='trayport', user='matej')
# assembler.set_start_end_time(start=[10,0,0], end=[12,0,0])    
trades_dict = assembler.get_data(params_dict, target_data='trades')
assembler.set_data_source('database')
ba_dict = assembler.get_data(params_dict, target_data='best_orders')

assert ba_dict.keys() == trades_dict.keys(), "Curve doesn't fit for both trades and best_orders"


for key in trades_dict.keys():
    ti_inst = TI(trades_dict[key], ba_dict[key])
    ti_inst.set_conditions()

data = ti_inst.data
bid_data = data[['bid_trade']].loc[data['bid_trade']!=0].copy()
ask_data = data[['ask_trade']].loc[data['ask_trade']!=0].copy()

from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

time_differences = np.array(bid_data.index.to_series().diff().dropna().dt.total_seconds()).reshape(-1,1)

dbscan = DBSCAN(eps=60, min_samples=2).fit(time_differences)

# Labels of the clusters
labels = dbscan.labels_

# Number of clusters in labels, ignoring noise if present.
n_clusters_ = len(set(labels)) - (1 if -1 in labels else 0)

print(f"Estimated number of clusters: {n_clusters_}")
print("Cluster labels:", labels)

# Plotting
plt.scatter(time_differences[:, 0], np.zeros_like(time_differences), c=labels, cmap='viridis', marker='o')
plt.xlabel('Time Differences (seconds)')
plt.title('DBSCAN Clustering of Time Differences')
plt.yticks([])  # Hide y-axis ticks
plt.show()

bid_data['clusters'] = np.concatenate(([0],labels))
bid_data['time_diffs'] = bid_data.index.to_series().diff().dt.total_seconds()
