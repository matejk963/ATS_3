# -*- coding: utf-8 -*-
"""
Created on Fri Feb 23 13:20:09 2024

@author: krajcovic
"""

import warnings
warnings.filterwarnings("ignore")


from datetime import datetime, time, date
import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
from Math.accumfeatures import MSTD, EMA, DerivativeEMA
from Math.ti_class import TI_class, TR_class
from Database.TPData import TPData, TPDataDa
from Strategies.IntensityHawkes_strategy.calibration import HIStrategyCalibration
from SynthSpread.spreadviewer_class import SpreadSingle, SpreadViewerData, norm_coeff
from Strategies.IntensityHawkes_strategy.model_class import HawkesIntensity
from Strategies.IntensityHawkes_strategy.backtest_class import BacktestIB
from Strategies.IntensityHawkes_strategy.strategy_class import StrategyHI, VolumeClass
from Math.nlm_class import VasicekEKF, VasicekUKF
from Math.lm_class import kalman, LinearModel
from scipy.integrate import odeint
from scipy.optimize import minimize
tol=0.019

ba = pd.read_csv(r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Algo\dem1_ba_11_12.csv',
                    parse_dates=['datetime']).set_index('datetime')
trades = pd.read_csv(r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Algo\dem1_trades_11_12.csv',
                    parse_dates=['datetime']).set_index('datetime')



hi_obj = HawkesIntensity(trades, ba, ['dem1'])

hi_obj.prepare_data()
hi_obj.create_data_dict()

data_dict = hi_obj.data_dict

bid_times_diff = np.array([])
bid_times = pd.DataFrame()
for i in range(20):
    aux = data_dict[list(data_dict)[i]]['dem1']['bid_event_times_dem1']
    aux_diff = np.array([(dt - aux.index[0]).total_seconds() for dt in aux.index])
    if bid_times.shape[0] == 0:
        bid_times_diff = aux_diff
        bid_times = aux.copy()
    else:
        bid_times_diff = np.concatenate([bid_times_diff, aux_diff])
        bid_times = pd.concat([bid_times, aux])


sns.kdeplot(aux_diff,shade=True, color="r", alpha=0.6, bw_adjust=0.5)


 # Sample time differences data
time_differences = np.array([bid_times])  # Replace with your actual time differences

# Estimating mu (base intensity)
# We'll use the entire duration to estimate the baseline rate of events
total_time = np.sum(time_differences)
total_events = len(time_differences)
mu_estimate = total_events / total_time  # Events per unit time

# Estimating alpha and beta (excitation and decay parameters)
# This is more heuristic-based and will need adjustment based on your data

# For alpha, let's assume the immediate increase in event rate is proportional to the initial peak
# This is heuristic and requires you to analyze the specific behaviors in your data
peak_rate = np.max(np.histogram(time_differences, bins=50)[0]) / (total_time / 50)  # Peak event rate in one of the bins
alpha_estimate = (peak_rate - mu_estimate)  # Increase over baseline, simplistic approach

# For beta, we need to estimate how quickly the rate decays back to baseline
# This is a simplified approach, assuming exponential decay back to the baseline after the peak
# Find where the event rate falls back to approximately the baseline rate
# This could be refined with more sophisticated analysis
decay_time_index = np.argmax(np.histogram(time_differences, bins=50)[0] < mu_estimate * (total_time / 50))
decay_time = (total_time / 50) * decay_time_index  # Approximate time it takes to decay to baseline

beta_estimate = 1 / decay_time  # Assuming exponential decay, beta is the inverse of decay time

# Print estimated parameters
print(f"Estimated mu (base intensity): {mu_estimate}")
print(f"Estimated alpha (excitation): {alpha_estimate}")
print(f"Estimated beta (decay): {beta_estimate}")



def hawkes_log_likelihood(params, event_times):
    mu, alpha, beta = params
    T = event_times[-1]
    n = len(event_times)
    
    # Intensity for each event
    intensity = mu + alpha * np.sum(np.exp(-beta * (event_times[-1] - event_times[:n])), axis=0)

    # Log-likelihood
    log_likelihood = n * np.log(mu) + np.sum(np.log(intensity))
    log_likelihood -= mu * T
    log_likelihood -= (alpha / beta) * (np.sum(1 - np.exp(-beta * (T - event_times))))
    
    # Return negative log-likelihood for minimization
    return -log_likelihood


from scipy.optimize import minimize

# Initial parameter guesses
initial_params = [mu_estimate, alpha_estimate, beta_estimate]  # mu, alpha, beta

# Bounds to ensure positivity
bounds = [(0, None), (0, None), (0, None)]

# # event_times = pd.Series
params = []
for i in range(20,44):
    aux = data_dict[list(data_dict)[i]]['dem1']['bid_event_times_dem1']
    if aux.shape[0] == 0:
        continue
    timestamps = aux.index
    
    # Convert timestamp strings to datetime objects
    datetime_objects = timestamps.copy()
    
    # Calculate time differences in seconds from the first event
    event_times = np.array([(dt - datetime_objects[0]).total_seconds() for dt in datetime_objects])
    # Define the time bins
    bin_size = 10  # Size of each time bin in the same units as 'event_times' (e.g., seconds)
    bins = np.arange(0, max(event_times) + bin_size, bin_size)  # Create bins from 0 to the max event time
    hist, bin_edges = np.histogram(event_times, bins=bins)  # Count events in each bin

    # Calculate empirical intensity as events per unit time (e.g., per second)
    empirical_intensity = hist / bin_size  # Convert event counts to rates

    # For plotting, use the middle point of each bin as the time point
    empirical_time_points = (bin_edges[:-1] + bin_edges[1:]) / 2
    
    # Plotting
    plt.figure(figsize=[10,6])
    plt.plot(empirical_time_points, empirical_intensity, label='Empirical', color='blue')
    # plt.plot(time_points, fitted_intensity, label='Fitted', color='green')
    plt.xlabel('Time')
    plt.ylabel('Intensity rate')
    plt.title('Fitted vs Empirical Intensities')
    plt.legend()
    plt.show()
    
    # event_times = bid_times
    
    # Perform the optimization
    result = minimize(hawkes_log_likelihood, initial_params, args=(event_times,), bounds=bounds, method='L-BFGS-B')
    
    print("Optimized parameters:", result.x)
    if result.success:
        params.append(result.x)


# Example parameters (replace these with your fitted values)
mu, alpha, beta = np.nanmean(params,axis=0)# base rate
mu=0
# alpha = 0.5  # excitation parameter
# beta = 1.0  # decay rate

# Your event timestamps
# event_times = np.array([your_event_timestamps])  # Replace with your data
timestamps = aux.index

# Convert timestamp strings to datetime objects
datetime_objects = timestamps.copy()

# Calculate time differences in seconds from the first event
event_times = np.array([(dt - datetime_objects[0]).total_seconds() for dt in datetime_objects])
# Time points at which to calculate intensity
time_points = np.linspace(0, max(event_times), num=len(aux))  # For example, up to 450 units of time

# Calculate fitted intensity at each time point
fitted_intensity = np.zeros_like(event_times)
for i, t in enumerate(time_points):
    # Sum the influence of all past events on the intensity at time t
    past_events = event_times[event_times < t]
    fitted_intensity[i] = mu + np.sum(alpha * np.exp(-beta * (t - past_events)))

# To estimate the number of events in each unit of time, you can simply use the fitted intensity
# Assuming continuous approximation, number of events ~ intensity * time interval
time_interval = time_points[1] - time_points[0]  # assuming uniform intervals
estimated_events = fitted_intensity * time_interval

# Now, estimated_events contains the estimated number of occurrences for each unit of time

empirical_intensity = np.zeros_like(time_points)
for i, t in enumerate(time_points):
    # Count how many events have occurred up to time t
    empirical_intensity[i] = np.sum(event_times <= t) / t if t > 0 else 0  # Avoid division by zero at t=0
    
# Define the time bins
bin_size = 60  # Size of each time bin in the same units as 'event_times' (e.g., seconds)
bins = np.arange(0, max(event_times) + bin_size, bin_size)  # Create bins from 0 to the max event time
hist, bin_edges = np.histogram(event_times, bins=bins)  # Count events in each bin

# Calculate empirical intensity as events per unit time (e.g., per second)
empirical_intensity = hist / bin_size  # Convert event counts to rates

# For plotting, use the middle point of each bin as the time point
empirical_time_points = (bin_edges[:-1] + bin_edges[1:]) / 2

# Plotting
plt.figure(figsize=[10,6])
plt.plot(empirical_time_points, empirical_intensity, label='Empirical', color='blue')
plt.plot(time_points, fitted_intensity, label='Fitted', color='green')
plt.xlabel('Time')
plt.ylabel('Intensity rate')
plt.title('Fitted vs Empirical Intensities')
plt.legend()
plt.show()

for day in range(30):
    try:
        df = trades[trades.index.date==date(2023,11,day)][['price_dem1', 'volume_dem1']].copy()
        df['vwap'] = (df['price_dem1']*df['volume_dem1']).cumsum()/df['volume_dem1'].cumsum()
        df['mov_avg_fast'] = df['price_dem1'].rolling(30).mean()
        df['mov_avg_slow'] = df['price_dem1'].rolling(100).mean()
        # Calculate the difference between prices and VWAP
        df['price_vwap_diff'] = df['price_dem1'] - df['vwap']
        
        # Calculate the standard deviation of this difference
        std_dev_diff = df['price_vwap_diff'].expanding().std()
        # Calculate the bands
        df['vwap_plus_1std'] = df['vwap'] + std_dev_diff
        df['vwap_minus_1std'] = df['vwap'] - std_dev_diff
        df['vwap_plus_2std'] = df['vwap'] + 2 * std_dev_diff
        df['vwap_minus_2std'] = df['vwap'] - 2 * std_dev_diff
        plt.figure(figsize=(12, 7))
        
        # Plot VWAP line
        plt.plot(df.index, df['vwap'], label='VWAP', color='blue', linewidth=2)
        plt.plot(df.index, df['mov_avg_fast'], label='mov_avg', color='green', linewidth=1)
        plt.plot(df.index, df['mov_avg_slow'], label='mov_avg', color='red', linewidth=1)
        
        # Plot first standard deviation area
        plt.fill_between(df.index, df['vwap_minus_1std'], df['vwap_plus_1std'], color='blue', alpha=0.3, label='1st Std Dev')
        
        # Plot second standard deviation area
        plt.fill_between(df.index, df['vwap_minus_2std'], df['vwap_plus_2std'], color='blue', alpha=0.1, label='2nd Std Dev')
        
        # Optionally, plot the prices as well
        plt.plot(df.index, df['price_dem1'], label='price', color='gray', alpha=0.6, linewidth=1)
        
        plt.title('VWAP with Standard Deviation Clouds')
        plt.xlabel('Time')  # Replace 'Time' with your actual time column name if applicable
        plt.ylabel('Price')
        plt.legend()
        plt.grid(True)
        plt.show()
    except:
        continue




