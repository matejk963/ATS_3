# -*- coding: utf-8 -*-
"""
Adjusted for 30-day window normalization and leap year handling
"""

import xarray as xr
import numpy as np
import os
import datetime

# Define directories
data_dir = r'Z:\Data\Spot\Weather\RawData'
output_dir = r'Z:\Data\Spot\Weather\Normalized2'
mean_std_dir = r'Z:\Data\Spot\Weather\MeanStd2'
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

# Function to compute and subtract the zonal mean
def remove_zonal_mean(data):
    zonal_mean = data.mean(dim='longitude')
    data_zonal_anomaly = data - zonal_mean
    return data_zonal_anomaly

# Apply zonal mean removal to the filtered dataset
filtered_data_zonal_anomaly = remove_zonal_mean(final_dataset)

# Apply latitude weighting
latitudes = filtered_data_zonal_anomaly['latitude']
cos_lat_weights = np.cos(np.deg2rad(latitudes))

# Apply the weighting to the entire dataset
weighted_data = filtered_data_zonal_anomaly * cos_lat_weights

# Convert month and day to day_of_year
def get_day_of_year(month, day):
    try:
        day_of_year = (datetime.datetime(2000, month, day) - datetime.datetime(2000, 1, 1)).days + 1
    except ValueError:
        return None  # For invalid days like Feb 30 or similar
    return day_of_year

# Function to normalize using a 30-day window, handling leap years
def climatology_with_window(data, day_of_year, time_dim, window=30):
    if day_of_year <= window:
        days_to_include = list(range(1, day_of_year + window + 1)) + list(range(366 - (window - day_of_year + 1), 367))
    elif day_of_year > 366 - window:
        days_to_include = list(range(day_of_year - window, 367)) + list(range(1, day_of_year - (366 - window) + 1))
    else:
        days_to_include = list(range(day_of_year - window, day_of_year + window + 1))

    selected_data = data.sel({time_dim: np.in1d(data[time_dim].dt.dayofyear, days_to_include)})

    # Exclude February 29 for leap years
    selected_data = selected_data.sel(valid_time=~((selected_data['valid_time'].dt.month == 2) &
                                                   (selected_data['valid_time'].dt.day == 29)))

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
            # Select data for the specific day
            day_data_filtered = weighted_data.sel({'valid_time': (weighted_data['valid_time'].dt.month == month) &
                                                             (weighted_data['valid_time'].dt.day == day)})
            if not day_data_filtered['valid_time'].size or not is_valid_date(day_data_filtered['valid_time'].dt).all():
                print(f'Skipping: {month}/{day}')
                continue

            # Calculate mean and std, then normalize using the filtered data
            mean, std = climatology_with_window(weighted_data, day_of_year, time_dim='valid_time')
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
all_means_xr = xr.concat(all_means, dim='day_of_year')
all_stds_xr = xr.concat(all_stds, dim='day_of_year')

# Save climatology means and stds
all_means_xr.load().to_netcdf(os.path.join(mean_std_dir, 'mean_1989_2019.nc'))
all_stds_xr.load().to_netcdf(os.path.join(mean_std_dir, 'std_1989_2019.nc'))

# Save the normalized data by year
for year, year_data in normalized_data_by_year.items():
    anomalies = xr.concat(year_data, dim='valid_time')
    anomalies.name = 'z'
    output_file = os.path.join(output_dir, f'normalized_anomalies_{year}.nc')
    anomalies.load().to_netcdf(output_file)
    print(f"Saved normalized data for year {year} to {output_file}")

print("Normalization process completed and saved.")
