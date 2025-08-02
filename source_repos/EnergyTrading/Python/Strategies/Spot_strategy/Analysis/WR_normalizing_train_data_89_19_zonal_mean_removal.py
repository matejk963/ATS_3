
# -*- coding: utf-8 -*-
"""
Created on Fri Aug 23 12:00:46 2024

@author: krajcovic
"""

import xarray as xr
import numpy as np
import os
from scipy.signal import butter, filtfilt
import pickle
import matplotlib.pyplot as plt
import datetime

# Define directories
data_dir = r'Z:\Data\Spot\Weather\RawData'
output_dir = r'Z:\Data\Spot\Weather\Normalized'
mean_std_dir = r'Z:\Data\Spot\Weather\MeanStd'
os.makedirs(output_dir, exist_ok=True)
os.makedirs(mean_std_dir, exist_ok=True)

# Get list of yearly files
yearly_files = sorted([os.path.join(data_dir, f) for f in os.listdir(data_dir) if f.endswith('.nc') and int(f[-7:-3]) in range(1989, 2020)])

# Initialize an empty list to hold each year's data
datasets = []

# Load and drop unnecessary dimensions for each file
for year_file in yearly_files:
    data = xr.open_dataset(year_file)
    
    # Drop pressure_level
    data_selected = data[['z']].squeeze('pressure_level')
    datasets.append(data_selected)

# Concatenate datasets along the time dimension ('valid_time')
final_dataset = xr.concat(datasets, dim='valid_time')

# Apply low-pass filter (10-day cutoff for daily data)
def low_pass_filter(data, cutoff=1/10, fs=1.0, order=5):
    nyquist = 0.5 * fs
    normal_cutoff = cutoff / nyquist
    b, a = butter(order, normal_cutoff, btype='low', analog=False)
    filtered_data = filtfilt(b, a, data, axis=-1)
    return filtered_data

# Apply the low-pass filter to the entire dataset first
filtered_data = xr.apply_ufunc(
    low_pass_filter, final_dataset['z'],  # Apply filter to the geopotential height variable
    input_core_dims=[['valid_time']],
    output_core_dims=[['valid_time']],
    vectorize=True,
    dask='parallelized',
    output_dtypes=[final_dataset['z'].dtype],
    dask_gufunc_kwargs={'allow_rechunk': True}
)

# Function to compute and subtract the zonal mean
def remove_zonal_mean(data):
    """
    Removes the zonal mean (longitude-averaged) from the geopotential height field.
    """
    # Compute zonal mean (mean across longitude, axis=1)
    zonal_mean = data.mean(dim='longitude')
    
    # Subtract zonal mean from each grid point (broadcast along longitudes)
    data_zonal_anomaly = data - zonal_mean
    
    return data_zonal_anomaly

# Apply zonal mean removal to the filtered dataset
filtered_data_zonal_anomaly = remove_zonal_mean(filtered_data)

# Convert month and day to day_of_year
def get_day_of_year(month, day):
    """Convert month and day to the day of the year (accounting for leap years)."""
    try:
        day_of_year = (datetime.datetime(2000, month, day) - datetime.datetime(2000, 1, 1)).days + 1
    except ValueError:
        return None  # For invalid days like Feb 30 or similar
    return day_of_year

# Normalize the data using the filtered dataset with zonal mean removed
def climatology_with_window(data, day_of_year, time_dim, window=10):
    if day_of_year <= window:
        days_to_include = list(range(1, day_of_year + window + 1)) + list(range(366 - (window - day_of_year + 1), 367))
    elif day_of_year > 366 - window:
        days_to_include = list(range(day_of_year - window, 367)) + list(range(1, day_of_year - (366 - window) + 1))
    else:
        days_to_include = list(range(day_of_year - window, day_of_year + window + 1))
    
    # Select data for the relevant days across all years
    selected_data = data.sel({time_dim: np.in1d(data[time_dim].dt.dayofyear, days_to_include)})
    
    # Calculate mean and std across the time dimension
    mean = selected_data.mean(dim=time_dim)
    std = selected_data.std(dim=time_dim)
    
    return mean, std

# Function to check if the date is valid (no Feb 29)
def is_valid_date(time_values):
    return ~((time_values.month == 2) & (time_values.day == 29))

# Process data by day/month instead of day of year
all_means, all_stds, normalized_data_by_year = [], [], {}

for month in range(1, 13):
    for day in range(1, 32):
        day_of_year = get_day_of_year(month, day)  # Convert month and day to day_of_year
        if day_of_year is None:  # Skip invalid dates
            continue

        try:
            # Select data for the specific day after filtering
            day_data_filtered = filtered_data_zonal_anomaly.sel({'valid_time': (filtered_data_zonal_anomaly['valid_time'].dt.month == month) &
                                                             (filtered_data_zonal_anomaly['valid_time'].dt.day == day)})
            if not day_data_filtered['valid_time'].size or not is_valid_date(day_data_filtered['valid_time'].dt).all():
                print(f'Skipping: {month}/{day}')
                continue

            # Calculate mean and std, then normalize using the filtered data with zonal mean removed
            mean, std = climatology_with_window(filtered_data_zonal_anomaly, day_of_year, time_dim='valid_time')  # Use day_of_year here
            anomalies = (day_data_filtered - mean) / std

            # Store normalized data by year
            years = np.unique(day_data_filtered['valid_time'].dt.year)
            for year in years:
                if year not in normalized_data_by_year:
                    normalized_data_by_year[year] = []
                normalized_data_by_year[year].append(anomalies.sel({'valid_time': day_data_filtered['valid_time'].dt.year == year}))

            all_means.append(mean)
            all_stds.append(std)

        except KeyError:
            continue

# Concatenate and save mean/std arrays
all_means2 = xr.concat(all_means, dim='day_of_year')
all_stds2 = xr.concat(all_stds, dim='day_of_year')

all_means2 = all_means2.assign_coords(day_of_year=np.arange(1, len(all_means) + 1))
all_stds2 = all_stds2.assign_coords(day_of_year=np.arange(1, len(all_stds) + 1))

all_means2.load().to_netcdf(os.path.join(mean_std_dir, 'mean_1989_2019.nc'))
all_stds2.load().to_netcdf(os.path.join(mean_std_dir, 'std_1989_2019.nc'))

# Save the normalized data by year
for year, year_data in normalized_data_by_year.items():
    # Concatenate along the 'valid_time' dimension
    anomalies = xr.concat(year_data, dim='valid_time')

    # Save the concatenated DataArray to a NetCDF file
    output_file = os.path.join(output_dir, f'normalized_anomalies_{year}.nc')
    anomalies.load().to_netcdf(output_file)
    print(f"Saved normalized data for year {year} to {output_file}")

print("Normalization process completed and saved.")
