import xarray as xr
import numpy as np
import pandas as pd
import os
import re

# Define directories
daily_dir = r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Weather\Weather Regimes\Geopotential_1993_2022\Daily'
normalized_dir = r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Weather\Weather Regimes\Normalized_1993_2022'
os.makedirs(normalized_dir, exist_ok=True)

# Regular expression to match files in the format geopotential_YYYY_MM_DD.nc
pattern = re.compile(r'geopotential_\d{4}_\d{2}_\d{2}\.nc')

# Function to calculate climatology with a ±10-day window for each day of the year across all years
def climatology_with_window(data, window=10):
    extended_mean = data.rolling(time=2*window+1, center=True).mean(dim='time')
    extended_std = data.rolling(time=2*window+1, center=True).std(dim='time')
    return extended_mean, extended_std

# Get list of all raw daily files
daily_files = sorted([os.path.join(daily_dir, f) for f in os.listdir(daily_dir) if pattern.match(f)])

# Extract unique days (ignoring the year) to process each day across all years at once
unique_days = sorted(set([re.match(r'geopotential_\d{4}_(\d{2}_\d{2})\.nc', os.path.basename(f)).group(1) for f in daily_files]))

# Process each unique day
for day in unique_days[-5:]:
    print(f"Processing day: {day}")
    
    # Get all files corresponding to this day across all years
    day_files = sorted([f for f in daily_files if f"_{day}.nc" in f])
    
    # Load the data for all years for this specific day
    day_data = [xr.open_dataset(f)['z'] for f in day_files]
    day_data = xr.concat(day_data, dim='time')

    # Calculate the day of the year
    year_placeholder = "2000"  # Use a placeholder year to avoid issues with leap years
    day_str = f'{year_placeholder}-{day.replace("_", "-")}'
    dayofyear = pd.to_datetime(day_str).day_of_year
    
    # Gather data for this day and ±10 days across all years
    relevant_days = []
    for offset in range(-10, 11):
        offset_day = dayofyear + offset
        if offset_day > 365:
            offset_day -= 365
        elif offset_day < 1:
            offset_day += 365
        relevant_days.append(offset_day)

    # Initialize list to hold data for all relevant days
    relevant_data = []

    # Iterate over all days and select relevant data
    for f in daily_files:
        ds = xr.open_dataset(f)
        ds_dayofyear = ds['time'].dt.dayofyear.values
        
        # Handle scalar and non-scalar time dimensions
        if ds_dayofyear.ndim == 0:
            ds_dayofyear = ds_dayofyear.item()  # Convert scalar to a regular Python number
        else:
            ds_dayofyear = ds_dayofyear[0]  # Take the first value if there are multiple

        if ds_dayofyear in relevant_days:
            relevant_data.append(ds['z'])
        
        ds.close()

    if relevant_data:
        relevant_data = xr.concat(relevant_data, dim='time')

        # Calculate climatology
        climatology_mean, climatology_std = climatology_with_window(relevant_data)

        # Normalize each day's data
        normalized_data = (day_data - climatology_mean.sel(time=day_data['time'])) / climatology_std.sel(time=day_data['time'])

        # Save the normalized data
        for f, norm in zip(day_files, normalized_data):
            year = re.match(r'geopotential_(\d{4})', os.path.basename(f)).group(1)
            output_file = os.path.join(normalized_dir, f'normalized_anomalies_{year}_{day}.nc')
            norm.to_netcdf(output_file)
            print(f"Saved normalized data for {year}-{day} to {output_file}")

    # Clear memory after processing
    del relevant_data, day_data, climatology_mean, climatology_std

print("Normalization process completed.")
