# -*- coding: utf-8 -*-
"""
Created on Wed Jan 24 12:54:01 2024

@author: krajcovic
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time
from scipy.optimize import minimize
from Database.TPData import TPDataAssembly as TDA
from Strategies.Intensity_class import TradeIntensity as TI
import matplotlib.pyplot as plt

import numpy as np
from scipy.integrate import odeint
from scipy.optimize import minimize


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

bid_data = data[['bid_trade']].copy()
start_time = bid_data.index[0]
date = start_time.date()

bid_data = bid_data.loc[bid_data.index.date==date].copy()
bid_trades = bid_data.loc[bid_data['bid_trade']==1].copy()

event_times =(bid_trades.index - start_time).total_seconds().values

event_times =(bid_trades.index - start_time).astype('timedelta64[ns]').astype('int64') / 1e9

event_times_grid = (bid_data.index-bid_data.index[0]).astype('timedelta64[ns]').astype('int64') / 1e9

# Step 2: Calculate empirical moments
empirical_mean = np.mean(event_times)
empirical_variance = np.var(event_times)

# Step 3 & 4: Define and solve ODEs for theoretical moments
def calculate_theoretical_moments(alpha, beta, lambda_infinity, t_max, initial_conditions):
    def system_of_odes(y, t):
        E_Nt, E_lambda_t = y
        dE_Nt_dt = E_lambda_t
        dE_lambda_t_dt = beta * (lambda_infinity - E_lambda_t) + alpha * E_lambda_t
        return [dE_Nt_dt, dE_lambda_t_dt]

    t = np.linspace(0, t_max, 100)
    sol = odeint(system_of_odes, initial_conditions, t)
    E_Nt = sol[:, 0]
    E_lambda_t = sol[:, 1]

    theoretical_mean = E_Nt[-1]
    theoretical_variance = E_lambda_t[-1]

    return theoretical_mean, theoretical_variance

# Define the objective function for the MoM
def objective_function(params, empirical_moments):
    alpha, beta, lambda_infinity = params
    theoretical_moments = calculate_theoretical_moments(alpha, beta, lambda_infinity, t_max=10, initial_conditions=[0, 0])
    squared_error = sum((empirical_moment - theoretical_moment) ** 2 for empirical_moment, theoretical_moment in zip(empirical_moments, theoretical_moments))
    return squared_error

# Optimization for parameter estimation
initial_guess = [0.1, 1,1]  # Initial guess for the parameters
empirical_moments = [empirical_mean, empirical_variance]
result = minimize(objective_function, initial_guess, args=(empirical_moments))

estimated_params = result.x
print("Estimated Parameters:", estimated_params)

# Define the exponential kernel function
def exp_kernel(t, alpha, beta):
    return alpha * np.exp(-beta * t)

# Define the intensity function for the Hawkes process
def hawkes_intensity(time, event_times, mu, alpha, beta):
    return mu + sum(exp_kernel(time - event_time, alpha, beta) for event_time in event_times if event_time <= time)

alpha, beta, mu = estimated_params
# Calculate intensities at each point in the time grid
intensities = [hawkes_intensity(t, event_times, mu, alpha, beta) for t in event_times_grid]


plt.figure(figsize=(10, 6))
plt.plot(event_times_grid, intensities, label="Estimated Intensity")
plt.scatter(event_times, [0]*len(event_times), color='red', marker='|', s=100, label="Actual Events")
plt.xlabel('Time')
plt.ylabel('Intensity')
plt.title('Hawkes Process Intensity Over Time')
plt.legend()
plt.show()