# -*- coding: utf-8 -*-
"""
Created on Wed Sep 18 14:59:30 2024

@author: krajcovic
"""

# Import necessary libraries
import xarray as xr
import numpy as np
import pandas as pd
import os
import pickle  # For loading centroids from a .pkl file

# Define directories
new_data_dir = r'Z:\Data\Spot\Weather\RawData'  # Directory for new out-of-sample data
output_dir = r'Z:\Data\Spot\Weather\NormalizedOutSample_7_nodes'
mean_std_dir = r'Z:\Data\Spot\Weather\MeanStd'
eof_dir = r'Z:\Data\Spot\Weather\Regimes_7_nodes'  # Directory where EOFs and centroids are stored
os.makedirs(output_dir, exist_ok=True)

# Load precomputed mean and std from training period (1989–2019)
mean_file = os.path.join(mean_std_dir, 'mean_1989_2019.nc')
std_file = os.path.join(mean_std_dir, 'std_1989_2019.nc')
mean_data = xr.open_dataset(mean_file).to_array().squeeze('variable')
# mean_data = mean_data.rename({'day_of_year': 'valid_time'})  # Rename to 'z'
std_data = xr.open_dataset(std_file).to_array().squeeze('variable')
# std_data = std_data.rename({'day_of_year': 'valid_time'})    # Rename to 'z'

# Load EOFs and centroids from training data
eofs = xr.open_dataarray(os.path.join(eof_dir, 'saved_eofs.nc'))  # EOF patterns

# Load centroids from .pkl file
with open(os.path.join(eof_dir, 'saved_centroids.pkl'), 'rb') as f:
    centroids = pickle.load(f)  # Centroids from K-Means clustering

# Define Euro-Atlantic area
ea_lat_tuple = (20, 80)
ea_lon_tuple = (-90, 60)

# Function to remove zonal mean
def remove_zonal_mean(data):
    zonal_mean = data.mean(dim='longitude')
    return data - zonal_mean

# Function to apply cosine latitude weighting
def apply_cosine_latitude_weighting(data):
    cos_lat_weights = np.cos(np.deg2rad(data['latitude']))
    return data * cos_lat_weights

# Function to normalize data using precomputed mean and std
def normalize_out_of_sample(new_data, mean_data, std_data):
    return (new_data - mean_data) / std_data

# Function to drop February 29th if present
def drop_feb_29(data):
    return data.sel(valid_time=~((data['valid_time'].dt.month == 2) & (data['valid_time'].dt.day == 29)))

# # Convert 'valid_time' to 'day_of_year'
# def convert_time_to_day_of_year(data):
#     return data.assign_coords(day_of_year=data['valid_time'].dt.dayofyear).swap_dims({'valid_time': 'day_of_year'})

def convert_time_to_day_of_year(data):
    # Create 'day_of_year' based on valid_time
    day_of_year = data['valid_time'].dt.dayofyear

    # Identify leap years and shift days after February 29th
    leap_year_mask = (data['valid_time'].dt.year % 4 == 0) & \
                     ((data['valid_time'].dt.year % 100 != 0) | (data['valid_time'].dt.year % 400 == 0))
    feb_29_mask = (day_of_year > 59) & leap_year_mask

    # Shift days after February 29th in leap years
    day_of_year = xr.where(feb_29_mask, day_of_year - 1, day_of_year)

    # Assign the adjusted day_of_year and swap the dimension
    return data.assign_coords(day_of_year=day_of_year).swap_dims({'valid_time': 'day_of_year'})


# Function to select data based on Euro-Atlantic lat/lon
def select_lat_lon_region(data):
    ea_lat = (data.latitude >= ea_lat_tuple[0]) & (data.latitude <= ea_lat_tuple[1])
    ea_lon = (data.longitude >= ea_lon_tuple[0]) & (data.longitude <= ea_lon_tuple[1])
    return data.sel(latitude=ea_lat, longitude=ea_lon)

# Project anomalies onto EOFs
def project_onto_eofs(data, eofs):
    reshaped_data = data.values.reshape(data.shape[0], -1)
    return np.dot(reshaped_data, eofs.values.reshape(eofs.shape[0], -1).T)

# Project onto regime centroids
def project_onto_regimes(projections, centroids):
    return np.dot(projections, centroids.T)

mean_data['longitude'] = ((mean_data['longitude'] + 180) % 360) - 180
std_data['longitude'] = ((std_data['longitude'] + 180) % 360) - 180

# Create a new output directory for regime projections
output_dir_projections = r'Z:\Data\Spot\Weather\RegimesOutOfSample'
os.makedirs(output_dir_projections, exist_ok=True)

# Load monthly mean and std projections
monthly_mean_file = os.path.join(eof_dir, 'monthly_mean_projections.pkl')
monthly_std_file = os.path.join(eof_dir, 'monthly_std_projections.pkl')

monthly_mean_df = pd.read_pickle(monthly_mean_file)
monthly_std_df = pd.read_pickle(monthly_std_file)

# Function to normalize the test projections based on monthly means and stds
def normalize_projections_by_month(projections, time_coords, monthly_mean_df, monthly_std_df):
    normalized_projections = np.zeros_like(projections)
    
    # Extract month from the time coordinates
    time_months = pd.to_datetime(time_coords).month
    
    # Normalize projections based on the respective month
    for i in range(projections.shape[0]):
        month = time_months[i]
        mean = monthly_mean_df.iloc[month - 1].values
        std = monthly_std_df.iloc[month - 1].values
        normalized_projections[i, :] = (projections[i, :] - mean) / std
    
    return normalized_projections

# Process each new year of data
for new_file in sorted(os.listdir(new_data_dir)):
    if new_file.endswith('.nc') and int(new_file[-7:-3]) in range(2020, 2025):
        print(f"Processing file: {new_file}")
        new_data = xr.open_dataset(os.path.join(new_data_dir, new_file))['z'].squeeze('pressure_level')
        
        # Step 0: Drop February 29th
        new_data_filtered = drop_feb_29(new_data)
        
        # Step 1: Convert 'valid_time' to 'day_of_year'
        new_data_filtered = convert_time_to_day_of_year(new_data_filtered)
        
        # Convert longitude to center around prime meridian
        new_data_filtered['longitude'] = ((new_data_filtered['longitude'] + 180) % 360) - 180
        
        # Step 2: Select the relevant lat/lon region (Euro-Atlantic region)
        new_data_region = select_lat_lon_region(new_data_filtered)

        # Step 3: Remove zonal mean
        new_data_zonal_anomaly = remove_zonal_mean(new_data_region)

        # Step 4: Apply cosine latitude weighting
        weighted_new_data = apply_cosine_latitude_weighting(new_data_zonal_anomaly)

        # Step 5: Normalize using precomputed mean and std
        normalized_new_data = normalize_out_of_sample(weighted_new_data, mean_data, std_data)

        # Step 6: Project normalized data onto EOFs
        projections = project_onto_eofs(normalized_new_data, eofs)

        # Step 7: Project onto regime centroids
        regime_projections = project_onto_regimes(projections, centroids)

        # Step 8: Normalize projections using monthly mean and std
        normalized_regime_projections = normalize_projections_by_month(regime_projections, new_data_filtered['valid_time'].values, monthly_mean_df, monthly_std_df)

        # Step 9: Save non-normalized and normalized projections as DataFrames
        non_normalized_df = pd.DataFrame(regime_projections, columns=[f'Regime_{i+1}' for i in range(centroids.shape[0])],
                                         index=normalized_new_data.valid_time.values)
        normalized_df = pd.DataFrame(normalized_regime_projections, columns=[f'Regime_{i+1}' for i in range(centroids.shape[0])],
                                     index=normalized_new_data.valid_time.values)

        non_normalized_df.to_pickle(os.path.join(output_dir_projections, f'non_normalized_projections_{new_file[-7:-3]}.pkl'))
        normalized_df.to_pickle(os.path.join(output_dir_projections, f'normalized_projections_{new_file[-7:-3]}.pkl'))

        print(f"Saved projections for {new_file[-7:-3]} in both normalized and non-normalized forms.")
