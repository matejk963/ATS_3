# -*- coding: utf-8 -*-
"""
Created on Tue Jun  4 12:55:02 2024

@author: scasny
"""


from datetime import datetime, time
import pandas as pd
import numpy as np
import pickle
from scipy.optimize import minimize
from Database.TPData import TPData, TPDataDa
from SynthSpread.spreadviewer_class import SpreadSingle


n_s = 2
mkt_list = ['de']
tenor_list = ['m']
tn1_list = [1,]
tn2_list = []
prod = 'base'
venue_list = ['eex']
start_date = datetime(2024, 6, 1)
end_date = datetime(2024, 7, 10)

if not tn2_list:
    tn_list = [str(t1) for t1 in tn1_list]
else:
    tn_list = [str(t1) + '_' + str(t2) for (t1, t2) in zip(tn1_list, tn2_list)]

dates = pd.date_range(start_date, end_date, freq='B')

spread_class = SpreadSingle(mkt_list, tenor_list, tn1_list, tn2_list, venue_list)
product_date1 = spread_class.product_dates(dates, n_s, tn_bool=True)[0]
product_date2 = spread_class.product_dates(dates, n_s, tn_bool=False)

start_time = time(9, 0, 0, 0)
end_time = time(17, 25, 0, 0)

gran = None

is_db = False
is_tr = False

if is_tr:
    data_class = TPData() 
else:
    data_class = TPDataDa()

# features_list = ['ba_volrat', 'mid_priceW', 'bid_sparsity', 'ask_sparsity']
# features_list = [*OB_attributes.attr_list(),
#                  *OB_attributes.attr_list(types='cross')]


name_list = [m + t + tn for m, t, tn in zip(mkt_list, tenor_list, tn_list)]


class_ser = pd.Series([])
df_trades = pd.DataFrame()
data_class_tr = TPDataDa()

for ds in dates:

    try:
        bT = datetime.combine(ds, start_time)
        eT = datetime.combine(ds, end_time)
        for i, (m, t, n, pd1, pd2) in enumerate(zip(mkt_list, tenor_list, tn_list,
                                                    product_date1, product_date2)):
            # Trades
            if is_tr:
                data_class.create_connection('OracleSQL')
                trades = data_class.get_trades(m, t, venue_list, pd1, bT, eT,
                                                    prod)
                trades = trades.reset_index(names='datetime').drop_duplicates('datetime', keep='last').set_index('datetime')
            else:
                trades = data_class_tr.get_trades(m, t, venue_list, pd1, bT, eT, prod)
        
            df_trades = pd.concat([df_trades, trades])
    except Exception as e:
        print(e)

def estimate_params(data, columns_dict,
                    train_lookback=10, retrain_gran='W'):
    def negative_log_likelihood(params, data):
        mu, alpha, beta = params
        if mu <= 0 or alpha <= 0 or beta <= 0:
            return np.inf  # Ensure parameters are positive

        # Convert data to numpy array for efficient computation
        data = np.array(data)

        # Initialize likelihood
        likelihood = 0

        # Calculate the contribution of each event to the likelihood
        for i, t in enumerate(data):
            # Compute sum of influences from all previous events
            # This avoids recomputing the exponential for all pairs of events
            prev_events = data[:i]  # Events before the current event
            time_diffs = t - prev_events  # Time differences to previous events
            intensity_contributions = alpha * np.exp(-beta * time_diffs)
            lambda_t = mu + np.sum(intensity_contributions)

            # Update the likelihood
            likelihood += np.log(lambda_t)

        # Subtract the integral of the base rate over the observation period
        likelihood -= mu * data[-1]

        # Subtract the integral of the triggered intensity
        # Instead of calculating for each pair, sum over all past event contributions
        # Note: The integral of each exponential term over the observation period
        for i, t in enumerate(data):
            # Only consider contributions from events that occurred before t
            if i > 0:
                prev_events = data[:i]
                time_diffs = t - prev_events
                likelihood -= np.sum((alpha / beta) * (1 - np.exp(-beta * time_diffs)))

        # Add contribution from the last event to the end of the observation window
        last_event = data[-1]
        time_diffs = last_event - data[:-1]
        likelihood -= np.sum((alpha / beta) * (1 - np.exp(-beta * time_diffs)))

        return -likelihood  # Return the negative log-likelihood
    
    def get_initial_guess(time_differences):
        # Sample time differences data
       time_differences = np.array([time_differences])  # Replace with your actual time differences

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
       return [mu_estimate, alpha_estimate, beta_estimate]
   
    def exp_kernel(t, alpha, beta):
        return alpha * np.exp(-beta * t)
    
    data_columns = [a for a in columns_dict.values()]
    df_columns = [a for a in columns_dict.keys()]
    
    df = data[data_columns].copy()
    df.columns = df_columns
    
    trades = df.dropna(subset=['price'])
    
    df['time_diff'] = df.index.to_series().diff().dt.total_seconds()
    trades['time_diff'] = trades.index.to_series().diff().dt.total_seconds()
    
    estimation_dates_total = np.unique(df.index.date)[train_lookback:]
    
    if retrain_gran.lower() in ['w']:
        estimation_dates = [a.isocalendar().week for a in estimation_dates_total]
    changes = np.zeros_like(estimation_dates, dtype=bool)
    changes[1:] = [element1 != element2 for element1, element2 in zip(estimation_dates[1:], estimation_dates[:-1])]

    changes[0] = True
    
    int_dict = {}
    bounds = [(0, None), (0, None), (0, None)]
    
    for date, est_bool in zip(estimation_dates_total, changes):
        if est_bool:
            df_train = trades.loc[:date].iloc[:-1].copy()
            unique_dates = np.unique(df_train.index.date)
            params_list = []
            for train_date in unique_dates:
                aux_train = df_train[df_train.index.date==train_date].copy()
                initial_params = get_initial_guess(aux_train['time_diff'].dropna())
                aux_sum = aux_train['time_diff'].dropna().cumsum()
                results = minimize(negative_log_likelihood,
                                    initial_params,
                                    args=(np.array(aux_sum),),
                                    bounds=bounds, method='L-BFGS-B',
                                    options={'gtol': 1e-6, 'ftol': 1e-6})
                if results.success:
                    params_list.append(results.x)
                    
            params = np.nanmean(np.array(params_list),axis=0)
            
        df_test = df[df.index.date==date].copy()
        df_test['count_time'] = df_test.index
        df_test['event_time'] = pd.to_datetime(np.where(~df_test['price'].isna(),
                                                        df_test.index,
                                                        None))
        df_test['event_time'] = df_test['event_time'].ffill()
        df_test.dropna(subset=['count_time'],inplace=True)
        
        mu, alpha, beta = params
        intensities_list = [mu + sum(exp_kernel((count_time - event_time).total_seconds(), alpha, beta)
                        for event_time in df_test['event_time'] if event_time<=count_time)
                       for count_time in df_test['count_time']]
        intensities = pd.Series(intensities_list, index=df_test.index)
        df_test['int'] = intensities
        int_dict[date] = df_test
        
                
            
                
                
    
    return int_dict

columns_dict = {'price': 'price'}

int_dict_3 = estimate_params(df_trades, columns_dict, train_lookback=3)

df_trades['int_3'] = pd.concat(int_dict_3.values())['int']            
       
        
    