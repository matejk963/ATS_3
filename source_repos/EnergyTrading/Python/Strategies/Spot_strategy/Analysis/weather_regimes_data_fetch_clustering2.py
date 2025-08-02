# -*- coding: utf-8 -*-
"""
Created on Sat Aug 17 15:05:04 2024

@author: krajcovic
"""

import cdsapi
import xarray as xr
import numpy as np
import os
import threadpoolctl
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
from scipy.signal import butter, filtfilt
import matplotlib.pyplot as plt
import cartopy.crs as ccrs

# Downloading data (this section remains the same)
c = cdsapi.Client()

c.retrieve(
    'reanalysis-era5-pressure-levels',
    {
        'product_type': 'reanalysis',
        'variable': 'geopotential',
        'pressure_level': '500',
        'year': [str(a) for a in range(2016,2019)],
        'month': [str(a) for a in range(1,13)],
        'day': [str(day).zfill(2) for day in range(1, 32)],
        'time': '12:00',
        'format': 'netcdf',
    },
    'download.nc')

# Load your dataset
ds = xr.open_dataset('download.nc')
geopotential = ds['z']

# Step 1: Apply a 10-day low-pass filter to the data
def low_pass_filter(data, cutoff=5, fs=1, order=5):
    nyquist = 0.5 * fs
    normal_cutoff = cutoff / nyquist
    
    if normal_cutoff >= 1 or normal_cutoff <= 0:
        raise ValueError("Cutoff frequency must be between 0 and the Nyquist frequency.")
    
    b, a = butter(order, normal_cutoff, btype='low', analog=False)
    
    # Apply filtering along the last axis (time)
    filtered_data = filtfilt(b, a, data, axis=-1)
    
    return filtered_data

# Use apply_ufunc to apply the filter over the 'time' dimension
geopotential_filtered = xr.apply_ufunc(
    low_pass_filter, geopotential,
    input_core_dims=[['time']],  # Specifies 'time' as the dimension to apply the function over
    output_core_dims=[['time']], # Keeps the output dimension the same
    vectorize=True, 
    kwargs={'cutoff': 5, 'fs': 20, 'order': 5}
)

# Step 2: Compute daily anomalies
daily_anomalies = geopotential_filtered - geopotential_filtered.mean(dim='time')

# Step 3: Perform EOF analysis
reshaped_data = daily_anomalies.stack(points=('latitude', 'longitude')).transpose('time', 'points')
pca = PCA(n_components=14)  # Choose number of components
PCs = pca.fit_transform(reshaped_data)

# Step 4: Cluster the leading EOFs to identify weather regimes
num_regimes = 4  # or 7 for year-round approach
kmeans = KMeans(n_clusters=num_regimes, random_state=42)
kmeans.fit(PCs)

# Step 5: Calculate regime strengths for each time point
distances = kmeans.transform(PCs)
strengths = 1 / distances
strengths /= strengths.sum(axis=1, keepdims=True)  # Normalize to sum to 1 for each day

# Step 6: Normalize regime strengths (Z-scores)
z_scores = (strengths - np.mean(strengths, axis=0)) / np.std(strengths, axis=0)

# Step 7: Plot normalized regime strength time series (Z-scores)
plt.figure(figsize=(12, 8))
for regime in range(num_regimes):
    plt.plot(daily_anomalies.time, z_scores[:, regime], label=f'Regime {regime + 1}')

plt.axhline(0, color='black', linestyle='--')
plt.title('Z-Score Normalized Regime Strength Time Series')
plt.xlabel('Time')
plt.ylabel('Z-Score of Strength')
plt.legend()
plt.show()

# Step 8: Visualization of Regimes (mean anomaly maps)
# We need to calculate mean anomalies for each regime
fig, axes = plt.subplots(num_regimes, 1, figsize=(10, 20), subplot_kw={'projection': ccrs.PlateCarree()})
for regime in range(num_regimes):
    ax = axes[regime]
    ax.set_extent([-90, 30, 20, 80], crs=ccrs.PlateCarree())
    ax.coastlines()
    
    # Calculate mean anomalies for the regime
    regime_indices = z_scores[:, regime] > 0  # Select times when regime strength is positive
    regime_mean_anomaly = daily_anomalies.isel(time=regime_indices).mean(dim='time')
    
    im = ax.contourf(geopotential.longitude, geopotential.latitude, regime_mean_anomaly,
                     transform=ccrs.PlateCarree(), cmap='coolwarm')
    ax.set_title(f'Weather Regime {regime + 1}')
    fig.colorbar(im, ax=ax, orientation='horizontal', pad=0.05)

plt.tight_layout()
plt.show()
