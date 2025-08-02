# -*- coding: utf-8 -*-
"""
Created on Sat Aug 17 21:51:13 2024

@author: krajcovic
"""

# -*- coding: utf-8 -*-
"""
Created on Sat Aug 17 15:05:04 2024

@author: krajcovic
"""

import cdsapi
import xarray as xr
import numpy as np
import dask
import dask.array as da
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
from scipy.signal import butter, filtfilt
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
from sklearn.decomposition import IncrementalPCA
import os

# Step 1: Downloading 30 years of data
c = cdsapi.Client()

c.retrieve(
    'reanalysis-era5-pressure-levels',
    {
        'product_type': 'reanalysis',
        'variable': 'geopotential',
        'pressure_level': '500',
        'year': [str(year) for year in range(1988, 2025)],  # 30 years
        'month': [str(month).zfill(2) for month in range(1, 13)],  # All months
        'day': [str(day).zfill(2) for day in range(1, 32)],
        'time': '12:00',
        'format': 'netcdf',
    },
    'download.nc')

# Load the dataset with Dask
ds = xr.open_dataset('download.nc', chunks={'time': 10})  # Adjust chunk size as needed
geopotential = ds['z']

# Step 2: Apply a 10-day low-pass filter to the data
def low_pass_filter(data, cutoff=5, fs=1, order=5):
    nyquist = 0.5 * fs
    normal_cutoff = cutoff / nyquist
    
    if normal_cutoff >= 1 or normal_cutoff <= 0:
        raise ValueError("Cutoff frequency must be between 0 and the Nyquist frequency.")
    
    b, a = butter(order, normal_cutoff, btype='low', analog=False)
    
    # Apply filtering along the last axis (time)
    filtered_data = filtfilt(b, a, data, axis=-1)
    
    return filtered_data

geopotential_filtered = xr.apply_ufunc(
    low_pass_filter, geopotential,
    input_core_dims=[['time']],
    output_core_dims=[['time']],
    vectorize=True,
    dask='parallelized',
    output_dtypes=[geopotential.dtype],
    dask_gufunc_kwargs={'allow_rechunk': True},
    kwargs={'cutoff': 5, 'fs': 20, 'order': 5}
)

# Step 3: Loop over each month and perform analysis
num_regimes = 4  # or 7 for year-round approach

for month in range(1, 13):
    # Select the data for the current month, previous month, and next month
    current_month_data = geopotential_filtered.sel(
        time=geopotential_filtered['time.month'].isin([(month-1) % 12 + 1, month, (month+1) % 12 + 1])
    )

    # Compute daily anomalies for the selected months
    daily_anomalies = current_month_data - current_month_data.mean(dim='time')

    # Perform EOF analysis
    reshaped_data = daily_anomalies.stack(points=('latitude', 'longitude')).transpose('time', 'points')
    
    # Convert reshaped_data to Dask array if not already
    reshaped_data = reshaped_data.chunk({'points': -1})
    
    # Adjust batch_size based on your available memory
    batch_size = 10  # You may need to adjust this
    
    # Create the IncrementalPCA object
    ipca = IncrementalPCA(n_components=14)
    
    # Loop over the reshaped data in chunks
    for i in range(0, reshaped_data.shape[0], batch_size):
        chunk = reshaped_data[i:i+batch_size].compute()  # Convert Dask array to NumPy for each chunk
        ipca.partial_fit(chunk)
    
    # Transform the data in chunks
    PCs = []
    for i in range(0, reshaped_data.shape[0], batch_size):
        chunk = reshaped_data[i:i+batch_size].compute()  # Convert Dask array to NumPy for each chunk
        PCs_chunk = ipca.transform(chunk)
        PCs.append(PCs_chunk)
    
    # Concatenate the PCs to get the full transformed data
    PCs = np.concatenate(PCs, axis=0)
    
    # pca = PCA(n_components=14)
    # PCs = pca.fit_transform(reshaped_data)

    # Cluster the leading EOFs to identify weather regimes
    kmeans = KMeans(n_clusters=num_regimes, random_state=42)
    kmeans.fit(PCs)

    # Calculate regime strengths for each time point
    distances = kmeans.transform(PCs)
    strengths = 1 / distances
    strengths /= strengths.sum(axis=1, keepdims=True)

    # Normalize regime strengths (Z-scores)
    z_scores = (strengths - np.mean(strengths, axis=0)) / np.std(strengths, axis=0)

    # Plot normalized regime strength time series (Z-scores)
    plt.figure(figsize=(12, 8))
    for regime in range(num_regimes):
        plt.plot(daily_anomalies.time, z_scores[:, regime], label=f'Regime {regime + 1}')

    plt.axhline(0, color='black', linestyle='--')
    plt.title(f'Z-Score Normalized Regime Strength Time Series for Month {month}')
    plt.xlabel('Time')
    plt.ylabel('Z-Score of Strength')
    plt.legend()
    plt.show()

    # Step 4: Visualization of Regimes (mean anomaly maps)
    fig, axes = plt.subplots(num_regimes, 1, figsize=(10, 20), subplot_kw={'projection': ccrs.PlateCarree()})
    for regime in range(num_regimes):
        ax = axes[regime]
        ax.set_extent([-90, 30, 20, 80], crs=ccrs.PlateCarree())
        ax.coastlines()

        # Calculate mean anomalies for the regime
        regime_indices = z_scores[:, regime] > 0
        regime_mean_anomaly = daily_anomalies.isel(time=regime_indices).mean(dim='time')

        im = ax.contourf(geopotential.longitude, geopotential.latitude, regime_mean_anomaly,
                         transform=ccrs.PlateCarree(), cmap='coolwarm')
        ax.set_title(f'Weather Regime {regime + 1} for Month {month}')
        fig.colorbar(im, ax=ax, orientation='horizontal', pad=0.05)

    plt.tight_layout()
    plt.show()


# Assume `ds` is your large xarray dataset
# Define the directory where the smaller NetCDF files will be saved
output_dir = r'C:\Users\krajcovic\Documents\Algo\Projects\Data'
os.makedirs(output_dir, exist_ok=True)

# Get the unique years in the dataset
# Extract the unique combinations of year and month from the dataset
years = ds['time.year'].values
months = ds['time.month'].values
unique_years = np.unique(years)
unique_months = np.unique(months)

# Loop over each year and month and save the data for that specific month separately
for year in unique_years:
    for month in unique_months:
        # Select data for the specific year and month
        month_ds = ds.sel(time=str(year) + '-' + str(month).zfill(2))
        
        # Define the file name
        file_name = f"{output_dir}/geopotential_{year}_{str(month).zfill(2)}.nc"
        
        # Save the monthly data to a NetCDF file
        month_ds.to_netcdf(file_name)
        print(f"Saved data for {year}-{str(month).zfill(2)} to {file_name}")
