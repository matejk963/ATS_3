# -*- coding: utf-8 -*-
"""
Created on Wed Aug 21 09:56:22 2024

@author: krajcovic
"""

import xarray as xr
import numpy as np
import os
import re
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
from tqdm import tqdm

# Define directories
normalized_dir = r'Z:\Data\Spot\Weather\Normalized'

# Regular expression to match normalized anomaly files
pattern = re.compile(r'normalized_anomalies_\d{4}-\d{2}-\d{2}\.nc')

# List all normalized anomaly files in the directory that match the pattern
normalized_files = sorted([os.path.join(normalized_dir, f) for f in os.listdir(normalized_dir) if pattern.match(f)])

# Load all normalized data at once using 'nested' combine and specify 'time' as the concatenation dimension
print("Loading normalized data...")
all_normalized_data = xr.open_mfdataset(normalized_files, combine='nested', concat_dim='time')

# Perform EOF analysis
print("Performing EOF analysis...")
reshaped_data = all_normalized_data.stack(points=('latitude', 'longitude')).transpose('time', 'points')

# Ensure reshaped_data is a NumPy array
reshaped_data_np = reshaped_data.to_array()

# Check the shape and data type
print("Shape of reshaped_data:", reshaped_data_np.shape)
print("Data type of reshaped_data_np:", reshaped_data_np.dtype)

# Convert to a float array if necessary
reshaped_data_np = reshaped_data_np.astype(np.float64)

# Check for NaN or infinite values
if np.isnan(reshaped_data_np).any() or np.isinf(reshaped_data_np).any():
    raise ValueError("Data contains NaN or infinite values, which will cause issues with PCA.")

# Perform PCA
pca = PCA(n_components=7)  # Adjust the number of components if needed
PCs = pca.fit_transform(reshaped_data_np[0])

# K-Means clustering to identify weather regimes
print("Clustering weather regimes...")
kmeans = KMeans(n_clusters=7, random_state=42)
kmeans.fit(PCs)

# Calculate regime strengths
distances = kmeans.transform(PCs)
strengths = 1 / distances
strengths /= strengths.sum(axis=1, keepdims=True)

# Save regime strengths
regime_strengths_file = os.path.join(normalized_dir, 'regime_strengths.nc')
xr.Dataset({'strengths': (['time', 'regime'], strengths), 'time': all_normalized_data.time}).to_netcdf(regime_strengths_file)
print(f"Regime strengths saved to {regime_strengths_file}")

print("Processing complete.")