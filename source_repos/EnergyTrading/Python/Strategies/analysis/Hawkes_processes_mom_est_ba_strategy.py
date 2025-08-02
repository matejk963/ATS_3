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

import seaborn as sns


assembler = TDA(source='database')
params_dict = {}

params_dict['tenor_list'] = ['m']
params_dict['tn1_list'] = [1]
params_dict['mkt_list'] = ['de'] * len(params_dict['tenor_list'])
params_dict['tn2_list'] = []
params_dict['prod'] = 'base'
params_dict['venue_list'] = ['eex']*len(params_dict['mkt_list'])
params_dict['start_date'] = datetime(2023, 11, 1)
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

def create_train_dict(df):
    ba_data = {}
    train_dict = {}
    for ba in ['bid', 'ask']:
        ba_data[ba] = df[[ba +'_trade']]
        start_time = ba_data[ba].index[0]
        date = start_time.date()
        train_dict[ba] = ba_data[ba].loc[ba_data[ba].index.date==
                                         date]
        train_dict[ba+'_trade'] = train_dict[ba].loc[train_dict[ba][ba+'_trade']==1]
        train_dict[ba+'_event_times'] = (train_dict[ba+'_trade'].index
                                         - start_time).astype('timedelta64[ns]').astype('int64') / 1e9
        train_dict[ba+'_event_times_grid'] = (train_dict[ba].index
                                         - start_time).astype('timedelta64[ns]').astype('int64') / 1e9
        train_dict[ba+'_empirical_mean'] = np.mean(train_dict[ba+'_event_times'])
        train_dict[ba+'_empirical_variance'] = np.var(train_dict[ba+'_event_times'])
        train_dict[ba+'_empirical_moments'] = [train_dict[ba+'_empirical_mean'],
                                               train_dict[ba+'_empirical_variance']]
        
    return train_dict


    


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

est_params_dict = {}
initial_guess = [0.1, 1,1]
for date in np.unique(data.index.date):
    aux = data[data.index.date==date].copy()
    train_dict = create_train_dict(aux)
    est_params_dict[date]={}
    for ba in ['bid', 'ask']:
        results = minimize(objective_function, initial_guess, args=(train_dict[ba+'_empirical_moments']))
        est_params_dict[date][ba] = results.x

train_dates, test_dates = split_array_by_ratio(np.unique(data.index.date),[0.8,0.2])


bid_params = []
ask_params = []

for date, params_dict in est_params_dict.items():
    bid_params.append(params_dict['bid'])
    ask_params.append(params_dict['ask'])
    
bid_params_tot = np.mean(np.array(bid_params)[:-1],axis=0)
ask_params_tot = np.mean(np.array(ask_params)[:-1],axis=0)

df = aux[['price', 'bidbestprice', 'askbestprice']].copy()
# Time delta (in seconds)
t = 15

# Function to find the target row and compute the (1,0,-1) value
def find_and_compute(timestamp, row):
    if pd.notna(row['price']):
        start_time = timestamp.floor('S')
        end_time = start_time + timedelta(seconds=t)
        future_rows = df[(df.index > timestamp) & (df.index <= end_time)].copy()

        bb_now, ba_now = row['bidbestprice'], row['askbestprice']
        condition_met = False

        for future_time, future_row in future_rows.iterrows():
            bb_future, ba_future, price_future = future_row['bidbestprice'], future_row['askbestprice'], future_row['price']

            if bb_future > ba_now or (pd.notna(price_future) and price_future > ba_now):
                return 1
            if ba_future < bb_now or (pd.notna(price_future) and price_future < bb_now):
                return -1
            condition_met = True

        return 0 if condition_met else None
    else:
        return None

# Apply the function to each row
df['computed_value'] = [find_and_compute(ts, row) for ts, row in df.iterrows()]


# Define the exponential kernel function
def exp_kernel(t, alpha, beta):
    return alpha * np.exp(-beta * t)

# Define the intensity function for the Hawkes process
def hawkes_intensity(time, event_times, mu, alpha, beta):
    return mu + sum(exp_kernel(time - event_time, alpha, beta) for event_time in event_times if event_time <= time)

event_times_grid_bid = (data.index - data.index[0]).astype('timedelta64[ns]').astype('int64') / 1e9
# Calculate intensities at each point in the time grid
intensities_bid = [hawkes_intensity(t, train_dict['bid_event_times'], 0,
                                    bid_params_tot[0],
                                    bid_params_tot[1]) for t in 
                   train_dict['bid_event_times_grid']]
intensities_ask = [hawkes_intensity(t, train_dict['ask_event_times'], 0,
                                    ask_params_tot[0],
                                    ask_params_tot[1]) for t in
                   train_dict['ask_event_times_grid']]


df['int_bid'] = np.round(intensities_bid,0)
df['int_ask'] = np.round(intensities_ask,0)

sns.regplot(data=df, x='int_bid', y='computed_value')

# plt.figure(figsize=(10, 6))
# plt.plot(train_dict['bid_event_times_grid'], intensities_bid, label="Estimated Intensity_bid")
# plt.plot(train_dict['ask_event_times_grid'], intensities_ask, label="Estimated Intensity_ask")
# plt.scatter(train_dict['ask_event_times'], [0]*len(train_dict['ask_event_times']), color='red', marker='|', s=100, label="Ask Events")
# plt.scatter(train_dict['bid_event_times'], [0]*len(train_dict['bid_event_times']), color='green', marker='|', s=100, label="Bid Events")
# plt.xlabel('Time')
# plt.ylabel('Intensity')
# plt.title('Hawkes Process Intensity Over Time')
# plt.legend()
# plt.show()