# -*- coding: utf-8 -*-
"""
Created on Fri Jul 19 15:32:46 2024

@author: krajcovic
"""
data_path = r'Z:\Data\Spot'


import xarray as xr
import numpy as np
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
import pickle
import os

# Define the path to the pickle files

# List all pickle files in the directory
pickle_files = [f for f in os.listdir(data_path) if f.endswith('.pkl')]

# Initialize lists to accumulate principal components and labels
all_PCs = []
all_labels = []
all_times = []

# Perform incremental processing
for pickle_file in pickle_files:
    with open(os.path.join(data_path, pickle_file), 'rb') as f:
        ds = pickle.load(f)
        
        # Extract geopotential height data
        geopotential = ds['z']
        
        # Compute daily anomalies
        daily_mean = geopotential.mean(dim='time')
        daily_anomalies = geopotential - daily_mean
        
        # Normalize anomalies by their standard deviation
        daily_std = geopotential.std(dim='time')
        normalized_anomalies = daily_anomalies / daily_std
        
        # Reshape the data for EOF analysis
        reshaped_data = normalized_anomalies.stack(points=('latitude', 'longitude')).transpose('time', 'points')
        
        # Perform PCA to find EOFs
        pca = PCA(n_components=14)
        PCs = pca.fit_transform(reshaped_data)
        
        # Accumulate the principal components and times
        all_PCs.append(PCs)
        all_times.append(ds.time.values)
        
# Concatenate all principal components and times
all_PCs = np.concatenate(all_PCs, axis=0)
all_times = np.concatenate(all_times, axis=0)

# Apply K-means clustering to the concatenated PCs to identify weather regimes
kmeans = KMeans(n_clusters=4, random_state=42)
labels = kmeans.fit_predict(all_PCs)

# Reshape labels to match the time dimension
reshaped_labels = labels.reshape((-1,))  # Assuming all_labels is 1D array

# Create a new DataArray for the regimes
regime_da = xr.DataArray(reshaped_labels, coords=[all_times], dims=["time"])

# Save the regime DataArray to a NetCDF file
regime_da.to_netcdf("weather_regimes.nc")

print("Weather regimes identified and saved to 'weather_regimes.nc'.")
