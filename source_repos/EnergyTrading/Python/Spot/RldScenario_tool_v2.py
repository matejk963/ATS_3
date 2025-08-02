# -*- coding: utf-8 -*-
"""
Created on Tue Sep 24 14:49:02 2024

@author: krajcovic
"""

from Spot.SpotModelClass_mark4 import PowerModel as PM
from Spot.Monitor_class import RldMonitor as RM
from Spot.Monitor_class import AvCapMonitor as AM

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import datetime as dt
import pickle
import os

import seaborn as sns

from sklearn.neighbors import KernelDensity

import itertools

# Function to generate pairs based on correlation level with added diagonal layers
def generate_pairs_based_on_correlation_layers(correlation, num_quantiles=10):
    # Calculate how many diagonals (layers) around the main diagonal to include
    layers = int((1 - correlation) * 10)  # Each 0.1 change in correlation adds 1 more diagonal layer

    # Initialize an empty list for the selected pairs
    selected_pairs = []

    # Loop through the layers from the main diagonal outward
    for offset in range(layers + 1):
        for i in range(num_quantiles - offset):
            selected_pairs.append((i, i + offset))  # Main diagonal and upper diagonal
            if offset != 0:
                selected_pairs.append((i + offset, i))  # Lower diagonal
    
    # Optional: Visualize the selected pairs in a grid for clarity
    grid = np.zeros((num_quantiles, num_quantiles))
    for pair in selected_pairs:
        grid[pair[0], pair[1]] = 1
    


    return selected_pairs

def compute_kendall_tau_per_month(time_series):
    tau_dict = {}

    # Extract the 'month' from the datetime index
    time_series['month'] = time_series.index.month

    # Group by month and compute the Kendall's Tau correlation matrix for each month
    for month in range(1, 13):
        subset = time_series[time_series['month'] == month]
        
        # Compute the Kendall's Tau correlation matrix if there are enough data points
        if len(subset) > 1:
            tau_matrix = subset.drop('month', axis=1).corr(method='kendall')
            tau_dict[f'month_{month}'] = tau_matrix
        else:
            tau_dict[f'month_{month}'] = None

    return tau_dict

# Function to sample from the joint distributions based on Kendall's Tau and empirical samples from scen_dict
def sample_based_on_tau(scen_dict, tau_dict, num_samples=1000, percentiles=np.arange(2, 100, 2) / 100.0):
    def sample_from_empirical_distributions(tau_matrix, distributions, size):
        def compute_covariance_from_correlation(correlation_matrix, variances):
            std_devs = np.sqrt(variances)
            diagonal_matrix = np.diag(std_devs)
            covariance_matrix = diagonal_matrix @ correlation_matrix @ diagonal_matrix
            return covariance_matrix

        d = len(distributions)

        # Convert Kendall's Tau to correlation matrix using the sine approximation
        correlation_matrix = np.sin(np.pi / 2 * tau_matrix)

        # Calculate the variance of each empirical distribution
        variances = np.array([np.var(distributions[i]) for i in range(len(distributions))])

        # Compute the covariance matrix from the correlation matrix and variances
        covariance_matrix = compute_covariance_from_correlation(correlation_matrix, variances)

        # Generate multivariate normal samples based on the covariance matrix
        base_samples = np.random.multivariate_normal(np.zeros(d), covariance_matrix, size=size)

        # Initialize array for final samples
        final_samples = np.zeros((size, d))

        # Resample from the empirical distributions based on ranks of normal samples
        for i in range(d):
            empirical_data = distributions[i]
            sorted_indices = np.argsort(empirical_data)
            ranks = np.argsort(np.argsort(base_samples[:, i]))
            resampled_indices = sorted_indices[ranks % len(empirical_data)]
            final_samples[:, i] = empirical_data[resampled_indices]

        return final_samples

    variables = list(scen_dict.keys())  # List of variables
    percentiles_dict = {}

    # Loop over each month
    for month in range(1, 13):
        # Extract samples for each variable at the current month (row)
        distributions = [scen_dict[var].loc[month].values for var in variables]
        
        # Retrieve the corresponding Kendall's Tau matrix for the month
        tau_matrix = tau_dict.get(f'month_{month}')

        if tau_matrix is not None and not tau_matrix.isnull().values.any():
            # Generate samples using the empirical distributions and the tau matrix
            samples = sample_from_empirical_distributions(tau_matrix, distributions, num_samples)

            # Store the percentiles
            for percentile in percentiles:
                percentile_value = np.percentile(samples, percentile * 100, axis=0)
                key = f'{int(percentile * 100)}th'
                if key not in percentiles_dict:
                    percentiles_dict[key] = pd.DataFrame(index=np.arange(1, 13), columns=variables)
                percentiles_dict[key].loc[month] = percentile_value

    return percentiles_dict

# Function to create KDE samples for each month
# Function to create KDE samples for each month and return a single DataFrame
def generate_kde_samples_per_month(df, value_col='rld_da', month_col='month', num_samples=1000):
    # Initialize an empty list to store each month's KDE samples
    samples_list = []

    # Loop through each month (from 1 to 12)
    for month in range(1, 13):
        # Filter the data for the current month
        month_data = df[df[month_col] == month][value_col].values

        if len(month_data) > 1:  # Ensure there are enough data points for KDE
            # Fit the KDE model on the current month's data
            kde = KernelDensity(kernel='gaussian', bandwidth=0.1).fit(month_data[:, np.newaxis])

            # Generate 1000 samples from the fitted KDE
            kde_samples = kde.sample(num_samples).flatten()  # Flatten the samples into a 1D array

            # Append the samples to the list
            samples_list.append(kde_samples)

    # Create a DataFrame from the samples list (rows = months, columns = samples)
    samples_df = pd.DataFrame(samples_list, index=np.arange(1, 13), columns=[f'sample_{i}' for i in range(1, num_samples + 1)])

    return samples_df

start_date = dt.datetime(2015,1,1)
end_date = dt.datetime(2024,9,25)

rm_inst = RM()
rm_inst.set_date_range(start_date,
                      end_date)

rld_scen_dict = {}
rld_da_tot = pd.DataFrame()
rld_norm_dict = {}
for market in ['de', 'fr', 'be', 'nl', 'at']:

    rld = rm_inst.get_fund_curve('ResidualDemand', '00',
                                 normalize_to='ResidualDemand',
                                 market=market)
    norm_data = rm_inst.get_fund_data('normal', 'ResidualDemand', '00',market=market, source='local')
    norm_data['month'] = norm_data['value_date'].dt.month
    rld_norm_dict[market] = norm_data
    
    rld_da = rm_inst.get_da_data(rld).set_index('value_date').rename(columns={'rld_da': market})
    
    rld_da_tot = pd.concat([rld_da_tot,
                           rld_da],
                           axis=1)
    
    rld_da = rld_da.rename(columns={market: 'rld_da'})
    
    rld_da['month'] = rld_da.index.month
    
    monthly_samples_dict = generate_kde_samples_per_month(rld_da, value_col='rld_da', month_col='month')
        
    rld_scen_dict[market] = monthly_samples_dict
    
    
rld_da_tot = rld_da_tot.dropna()

tau_dict = compute_kendall_tau_per_month(rld_da_tot)



# monthly_samples_dict = generate_kde_samples_per_month(rld_da, value_col='rld_da', month_col='month')
percentiles_dict = sample_based_on_tau(rld_scen_dict, tau_dict, num_samples=1000)

final_scen_dict = {}
for perc, perc_df in percentiles_dict.items():
    final_scen_dict[perc] = pd.DataFrame()
    for col in perc_df.columns:
        final_scen_dict[perc][col] = rld_norm_dict[col].set_index('value_date')['rld']\
            * rld_norm_dict[col].set_index('value_date')['month'].map(perc_df[col])
    final_scen_dict[perc].dropna(inplace=True)
        


folder_path = r'Z:\Data\Spot\Scenarios\Rld'
file_path = os.path.join(folder_path, f"Rld_scen_{end_date.strftime('%Y%m%d')}.pkl")

with open(file_path, 'wb') as f:
    pickle.dump(final_scen_dict, f)