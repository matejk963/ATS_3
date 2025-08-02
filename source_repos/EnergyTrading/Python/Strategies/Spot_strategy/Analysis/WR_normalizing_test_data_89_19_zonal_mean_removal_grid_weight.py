# -*- coding: utf-8 -*-
"""
Created on Wed Sep 18 14:59:45 2024

@author: krajcovic
"""

# Import necessary libraries
import xarray as xr
import numpy as np
import os

# Define directories
new_data_dir = r'Z:\Data\Spot\Weather\RawData'  # Directory for new out-of-sample data
output_dir = r'Z:\Data\Spot\Weather\NormalizedOutSample'
mean_std_dir = r'Z:\Data\Spot\Weather\MeanStd'
os.makedirs(output_dir, exist_ok=True)

# Get list of yearly files
yearly_files = sorted([os.path.join(new_data_dir, f)
                       for f in os.listdir(new_data_dir)
                       if f.endswith('.nc') and int(f[-7:-3]) in range(2020, 2025)])

# Load precomputed mean and std from training period (1989–2019)
mean_file = os.path.join(mean_std_dir, 'mean_1989_2019.nc')
std_file = os.path.join(mean_std_dir, 'std_1989_2019.nc')

mean_data = xr.open_dataset(mean_file)['z']  # Mean for geopotential height
std_data = xr.open_dataset(std_file)['z']    # Std deviation for geopotential height

# Function to remove zonal mean
def remove_zonal_mean(data):
    zonal_mean = data.mean(dim='longitude')
    data_zonal_anomaly = data - zonal_mean
    return data_zonal_anomaly

# Function to apply cosine latitude weighting
def apply_cosine_latitude_weighting(data):
    latitudes = data['latitude']
    cos_lat_weights = np.cos(np.deg2rad(latitudes))
    weighted_data = data * cos_lat_weights
    return weighted_data

# Function to normalize data using precomputed mean and std
def normalize_out_of_sample(new_data, mean_data, std_data):
    anomalies = (new_data - mean_data) / std_data
    return anomalies

# Function to drop February 29th if present
def drop_feb_29(data):
    # Drop February 29th if present in the dataset
    data_filtered = data.sel(valid_time=~((data['valid_time'].dt.month == 2) & (data['valid_time'].dt.day == 29)))
    return data_filtered
# Ensure the dimensions match by converting 'valid_time' to 'day_of_year'
def convert_time_to_day_of_year(data):
    # Create a new coordinate for 'day_of_year' from 'valid_time'
    data = data.assign_coords(day_of_year=data['valid_time'].dt.dayofyear)
    return data.swap_dims({'valid_time': 'day_of_year'})

# Process each new year of data
for new_file in yearly_files:
    new_data = xr.open_dataset(new_file)['z'].squeeze('pressure_level')  # Load geopotential height data

    # Step 0: Drop February 29th
    new_data_filtered = drop_feb_29(new_data)

    # Step 1: Convert 'valid_time' to 'day_of_year'
    new_data_filtered = convert_time_to_day_of_year(new_data_filtered)

    # Step 2: Remove zonal mean
    new_data_zonal_anomaly = remove_zonal_mean(new_data_filtered)

    # Step 3: Apply cosine latitude weighting
    weighted_new_data = apply_cosine_latitude_weighting(new_data_zonal_anomaly)

    # Step 4: Normalize using precomputed mean and std
    normalized_new_data = normalize_out_of_sample(weighted_new_data, mean_data, std_data)

    # Save normalized data
    output_file = os.path.join(output_dir, f'normalized_out_of_sample_{new_file[-7:-3]}.nc')
    normalized_new_data.to_netcdf(output_file)
    print(f"Saved normalized out-of-sample data for {new_file[-7:-3]} to {output_file}")


