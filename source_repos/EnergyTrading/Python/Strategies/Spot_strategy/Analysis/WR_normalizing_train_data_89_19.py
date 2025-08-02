# -*- coding: utf-8 -*-
"""
Created on Thu Aug 22 11:53:09 2024

@author: krajcovic
"""

import xarray as xr
import numpy as np
import os
from scipy.signal import butter, filtfilt

# Define directories
data_dir = r'Z:\Data\Spot\Weather\RawData'
output_dir = r'Z:\Data\Spot\Weather\Normalized'
mean_std_dir = r'Z:\Data\Spot\Weather\MeanStd'
os.makedirs(output_dir, exist_ok=True)
os.makedirs(mean_std_dir, exist_ok=True)

# Load all data (only from 1989 to 2019)
yearly_files = sorted([os.path.join(data_dir, f) for f in os.listdir(data_dir) if f.endswith('.nc') and int(f[-7:-3]) in range(1989, 2020)])
data = xr.open_mfdataset(yearly_files, combine='by_coords')

# Determine the time dimension
time_dim = None
for dim in data.dims:
    if "time" in dim:
        time_dim = dim
        break

if time_dim is None:
    raise ValueError("Time dimension not found in the dataset")

# Apply low-pass filter
def low_pass_filter(data, cutoff=0.1, fs=1.0, order=5):
    nyquist = 0.5 * fs
    normal_cutoff = cutoff / nyquist
    b, a = butter(order, normal_cutoff, btype='low', analog=False)
    filtered_data = filtfilt(b, a, data, axis=-1)
    return filtered_data


# Normalize the data
def climatology_with_window(data, day_of_year, time_dim, window=10):
    # Handle days near the beginning of the year
    if day_of_year <= window:
        days_to_include = list(range(1, day_of_year + window + 1)) + list(range(366 - (window - day_of_year + 1), 367))
    # Handle days near the end of the year
    elif day_of_year > 366 - window:
        days_to_include = list(range(day_of_year - window, 367)) + list(range(1, day_of_year - (366 - window) + 1))
    else:
        days_to_include = list(range(day_of_year - window, day_of_year + window + 1))
    
    # Select data for the relevant days
    selected_data = data.sel(valid_time=np.in1d(data[f'{time_dim}.dayofyear'], days_to_include))
    
    # Calculate mean and std across the time dimension
    mean = selected_data.mean(dim=time_dim)
    std = selected_data.std(dim=time_dim)
    
    return mean, std


# Process each day of the year
days_of_year = np.arange(1, 367)
normalized_data = []
all_means = []
all_stds = []

for day in days_of_year:
    day_data = data.sel({time_dim: data[f'{time_dim}.dayofyear'] == day})
    
    # Normalize only if there is valid data for the given day
    if not day_data[time_dim].size:
        print('No data for day of year: ', str(day))
        continue

   
    # Access the 'z' variable (assuming 'z' is the geopotential height)
    geopotential = day_data['z']
    
    # Apply low-pass filter specifically to the 'z' variable
    day_data_filtered = xr.apply_ufunc(
        low_pass_filter, geopotential,  # Apply to geopotential instead of the whole dataset
        input_core_dims=[[time_dim]],
        output_core_dims=[[time_dim]],
        vectorize=True,
        dask='parallelized',
        output_dtypes=[geopotential.dtype],
        dask_gufunc_kwargs={'allow_rechunk': True}
    )
    
    # Ensure that the time dimension is re-assigned if it was dropped
    if time_dim not in day_data_filtered.dims:
        day_data_filtered = day_data_filtered.expand_dims({time_dim: day_data[time_dim].values})
    
    # Now you can proceed with normalization
    mean, std = climatology_with_window(data, day, time_dim=time_dim)
    anomalies = (day_data_filtered - mean) / std
    normalized_data.append(anomalies)
    
    # Save the daily normalized data
    for time_point in anomalies[time_dim].values:
        date_str = np.datetime_as_string(time_point, unit='D')
        output_file = os.path.join(output_dir, f'normalized_anomalies_{date_str}.nc')
        anomalies.sel({time_dim: time_point}).to_netcdf(output_file)

        
    # Store mean and std
    all_means.append(mean)
    all_stds.append(std)

# Save the mean and std arrays for each day
all_means = xr.concat(all_means, dim='day_of_year')
all_stds = xr.concat(all_stds, dim='day_of_year')
all_means.to_netcdf(os.path.join(mean_std_dir, 'mean_1989_2019.nc'))
all_stds.to_netcdf(os.path.join(mean_std_dir, 'std_1989_2019.nc'))

# Complete message
print("Normalization process completed and saved to", output_dir)

