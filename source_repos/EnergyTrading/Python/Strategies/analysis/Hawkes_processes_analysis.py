# -*- coding: utf-8 -*-
"""
Created on Fri Jan 19 13:40:19 2024

@author: krajcovic
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time
from scipy.optimize import minimize
from Database.TPData import TPDataAssembly as TDA
from Strategies.Intensity_class import TradeIntensity as TI
import matplotlib.pyplot as plt


assembler = TDA(source='database')
params_dict = {}

params_dict['tenor_list'] = ['m']
params_dict['tn1_list'] = [1]
params_dict['mkt_list'] = ['de'] * len(params_dict['tenor_list'])
params_dict['tn2_list'] = []
params_dict['prod'] = 'base'
params_dict['venue_list'] = ['eex']*len(params_dict['mkt_list'])
params_dict['start_date'] = datetime(2023, 11, 22)
params_dict['end_date'] = datetime(2023, 11, 24)
params_dict['ns'] = 2

# Fetch trades and best orders for the curve
assembler = TDA(source='trayport', user='matej')
# assembler.set_start_end_time(start=[10,0,0], end=[12,0,0])    
trades_dict = assembler.get_data(params_dict, target_data='trades')
assembler.set_data_source('database')
ba_dict = assembler.get_data(params_dict, target_data='best_orders')

assert ba_dict.keys() == trades_dict.keys(), "Curve doesn't fit for both trades and best_orders"

# Go key by key(product by product) in dictionaries and process through Intensity Class
# together to get proper trade side
# Concat the porcessed products to one df
data = pd.DataFrame()
for key in trades_dict.keys():
    trades_aux = trades_dict[key].loc[trades_dict[key]['broker_id']==14].copy()
    ba_aux = ba_dict[key]
    # iInitalize IntClass with each key
    int_inst = TI(trades_aux, ba_aux)
    int_inst.set_conditions()
    data_aux = int_inst.data
    data_aux['id'] = key
    if data.empty:
        data = data_aux.copy()
    else:
        data = pd.concat([data, data_aux])

        

data['bid_ask'] = (data['bidbestprice']-data['askbestprice'])/data['bidbestprice']
data['ba_perc'] = pd.qcut(data['bid_ask'], q=10, labels=False)

test_date = np.unique(data.index.date)[-1]
test_data = data[test_date:].copy()
train_data = data[:test_date].copy()

bid_train_data = train_data.loc[train_data['bid_trade']==1].copy()
bid_test_data = test_data.loc[test_data['bid_trade']==1].copy()


# Convert the datetime index to numeric (e.g., seconds since start)
start_time = bid_train_data.index[0]
event_times = np.round((bid_train_data.drop_duplicates().index - start_time).total_seconds().values,0)
# Convert the datetime index to numeric (e.g., seconds since start)
start_test_time = bid_test_data.index[0]
event_test_times = np.round((bid_test_data.drop_duplicates().index - start_test_time).total_seconds().values,0)

# Define the exponential kernel function
def exp_kernel(t, alpha, beta):
    return alpha * np.exp(-beta * t)

# Define the log-likelihood function
def log_likelihood(params, event_times):
    mu, alpha, beta = params
    # mu = 0.01
    T = event_times[-1]
    n = len(event_times)
    
    # Intensity function
    intensity = mu + sum(exp_kernel(T - event_times[i], alpha, beta) for i in range(n))
    
    # Log-likelihood calculation
    ll = n * np.log(intensity) - mu * T - sum(sum(exp_kernel(event_times[j] - event_times[i], alpha, beta) for i in range(j)) for j in range(1, n))
    print(ll)
    return -ll  # Negative log-likelihood for minimization

# Initial parameter guesses
initial_params = [0.01, 1,1]  # Example: mu, alpha, beta

# Use a minimizer to find the best parameters
result = minimize(log_likelihood, initial_params, args=(event_times),
                  bounds=[(0.01, None), (0, None), (0, None)])

# Best-fit parameters
mu, alpha, beta = result.x
# mu = 0.1
print(f"Estimated Parameters: mu={mu}, alpha={alpha}, beta={beta}")

# Define the exponential kernel function
def exp_kernel(t, alpha, beta):
    return alpha * np.exp(-beta * t)

# Define the intensity function for the Hawkes process
def hawkes_intensity(time, event_times, mu, alpha, beta):
    return mu + sum(exp_kernel(time - event_time, alpha, beta) for event_time in event_times if event_time <= time)

# Event times (from your data)
# event_times = np.array([...])  # replace with your actual event times

# Create a time grid (you can adjust the resolution as needed)
# start_time = 0
sel_events = event_test_times
end_time = max(sel_events)

time_grid = np.arange(0, end_time + 1, 1)  # for example, 1000 points

# Calculate intensities at each point in the time grid
intensities = [hawkes_intensity(t, sel_events, mu, alpha, 2) for t in time_grid]

# fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True)
# pd.Series(intensities).plot(ax=ax1)
# pd.Series(event_test_times).plot(ax=ax2)
 
# def on_xlims_change(event_ax):
#     other_ax = ax2 if event_ax == ax1 else ax1
#     other_ax.set_xlim(event_ax.get_xlim())
 
# ax1.callbacks.connect('xlim_changed', on_xlims_change)
 
# plt.show()


plt.figure(figsize=(10, 6))
plt.plot(time_grid, intensities, label="Estimated Intensity")
plt.scatter(sel_events, [0]*len(sel_events), color='red', marker='|', s=100, label="Actual Events")
plt.xlabel('Time')
plt.ylabel('Intensity')
plt.title('Hawkes Process Intensity Over Time')
plt.legend()
plt.show()

