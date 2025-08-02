# -*- coding: utf-8 -*-
"""
Created on Thu Jul 18 16:42:54 2024

@author: krajcovic
"""

import cdsapi

c = cdsapi.Client()

# Example to download geopotential height data for one year (you need to loop through years for full dataset)
c.retrieve(
    'reanalysis-era5-pressure-levels',
    {
        'product_type': 'reanalysis',
        'variable': 'geopotential',
        'pressure_level': '500',
        'year': '2018',
        'month': [
            '12'
        ],
        'day': [
            '01', '02', '03', '04', '05',
            '06', '07', '08', '09', '10',
            '11', '12', '13', '14', '15',
            '16', '17', '18', '19', '20',
            '21', '22', '23', '24', '25',
            '26', '27', '28', '29', '30', '31'
        ],
        'time': '12:00',
        'format': 'netcdf',
    },
    'download.nc')

import xarray as xr
import numpy as np
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
import os
import threadpoolctl

# Ensure the threadpool limits are set correctly to avoid issues
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

# Load the downloaded NetCDF file
ds = xr.open_dataset('download.nc')
geopotential = ds['z']

# Compute daily anomalies
daily_anomalies = geopotential - geopotential.mean(dim='time')

# Confirm the units of the anomalies
print(daily_anomalies.attrs)

# Reshape the data for EOF analysis
reshaped_data = daily_anomalies.stack(points=('latitude', 'longitude')).transpose('time', 'points')

# Perform PCA to find EOFs
pca = PCA(n_components=14)
PCs = pca.fit_transform(reshaped_data)

# Apply K-means clustering to the PCs to identify weather regimes
with threadpoolctl.threadpool_limits(limits=1, user_api='blas'):
    kmeans = KMeans(n_clusters=4, random_state=42)
    labels = kmeans.fit_predict(PCs)

# Reshape labels to match the time dimension
labels_reshaped = labels.reshape((daily_anomalies.shape[0], -1)).mean(axis=1)

# Assign labels back to original data
daily_anomalies = daily_anomalies.assign_coords(regime=('time', labels_reshaped.astype(int)))

# Create a map plot for each weather regime, focusing on the North Atlantic and Europe
num_regimes = 4
fig, axes = plt.subplots(num_regimes, 1, figsize=(10, 20), subplot_kw={'projection': ccrs.PlateCarree()})

for regime in range(num_regimes):
    ax = axes[regime]
    ax.set_extent([-90, 30, 20, 80], crs=ccrs.PlateCarree())
    ax.coastlines()
    regime_data = daily_anomalies.where(daily_anomalies.regime == regime, drop=True).mean(dim='time')
    im = ax.contourf(daily_anomalies.longitude, daily_anomalies.latitude, regime_data, transform=ccrs.PlateCarree(), cmap='coolwarm')
    ax.set_title(f'Weather Regime {regime + 1}')
    fig.colorbar(im, ax=ax, orientation='horizontal', pad=0.05)

plt.tight_layout()
plt.show()



