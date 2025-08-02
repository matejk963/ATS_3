# -*- coding: utf-8 -*-
"""
Created on Wed Sep 18 15:00:09 2024

@author: krajcovic
"""

# -*- coding: utf-8 -*-
"""
Adjusted for proper longitude handling and mapping with normalized regime strengths and regime probabilities saving,
including normalized projections per ECMWF methodology.
"""

import xarray as xr
import numpy as np
import os
from eofs.xarray import Eof  # Import Eof class from eofs package
from sklearn.cluster import KMeans
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import pandas as pd  # To save regime probabilities and strengths to pickle
from scipy.interpolate import griddata  
from scipy.spatial.distance import cdist

# Directory where normalized data is stored
normalized_dir = r'Z:\Data\Spot\Weather\Normalized'
regimes_dir = r'Z:\Data\Spot\Weather\Regimes'
os.makedirs(regimes_dir, exist_ok=True)

# Create the Maps folder inside the regimes_dir
maps_dir = os.path.join(regimes_dir, 'Maps')
os.makedirs(maps_dir, exist_ok=True)

# Load all normalized data files
normalized_files = sorted([os.path.join(normalized_dir, f) for f in os.listdir(normalized_dir) if f.endswith('.nc')])

# Initialize lists to store data arrays
times = []
all_data = []

# Load data using xarray
for file in normalized_files:
    ds = xr.open_dataset(file)
    
    # Extract geopotential height ('z') and valid_time
    times.append(ds['valid_time'].values)
    all_data.append(ds['z'])
    
    ds.close()

# Concatenate data along the time dimension
all_data = xr.concat(all_data, dim='valid_time')

# Extract the time coordinates from the 'times' list
time_coords = np.concatenate(times)


# Transform longitudes from 0–360 to -180–180
all_data['longitude'] = ((all_data['longitude'] + 180) % 360) - 180

# Define Euro-Atlantic area
ea_lat_tuple = (20, 80)
ea_lon_tuple = (-90, 60)

# Select EA region lat/lon
ea_lat = (all_data.latitude >= ea_lat_tuple[0]) & (all_data.latitude <= ea_lat_tuple[1])
ea_lon = (all_data.longitude >= ea_lon_tuple[0]) & (all_data.longitude <= ea_lon_tuple[1])

# Select only the Euro-Atlantic region
data_region = all_data.sel(latitude=ea_lat, longitude=ea_lon)

data_region = data_region.transpose('valid_time', 'latitude', 'longitude')

# Perform EOF analysis using the eofs package
solver = Eof(data_region)

# Number of EOFs to retain
n_modes = 20  # Adjust as needed based on explained variance

# Get the EOFs (spatial patterns) and PCs (time series)
eofs = solver.eofs(neofs=n_modes)
pcs = solver.pcs(npcs=n_modes)

# Explained variance for each EOF
explained_variance = solver.varianceFraction(neigs=n_modes)

# Print explained variance
print(f'Explained variance (fraction): {explained_variance.values}')
print(f'Total variance explained: {explained_variance.sum().values}')

# Perform K-Means clustering on the PCs
n_clusters = 7  # Adjust the number of clusters as needed
kmeans = KMeans(n_clusters=n_clusters, random_state=42)
kmeans.fit(pcs)

# Get the cluster labels (i.e., regimes)
regimes = kmeans.labels_

# Calculate regime centroids (mean PC for each cluster)
centroids = np.zeros((n_clusters, pcs.shape[1]))
for cluster in range(n_clusters):
    indices = np.where(regimes == cluster)[0]  # Select indices for this cluster
    centroids[cluster, :] = pcs[indices, :].mean(axis=0)
    
# Save the EOFs
eof_file = os.path.join(regimes_dir, 'saved_eofs.nc')
eofs_xr = xr.DataArray(eofs, dims=['mode', 'latitude', 'longitude'], 
                       coords={'mode': np.arange(1, n_modes + 1),
                               'latitude': data_region.latitude, 
                               'longitude': data_region.longitude})
eofs_xr.to_netcdf(eof_file)
print(f'EOFs saved to {eof_file}')

# Save the centroids (mean PCs for each regime)
centroid_file = os.path.join(regimes_dir, 'saved_centroids.pkl')
centroids_df = pd.DataFrame(centroids, columns=[f'PC_{i+1}' for i in range(pcs.shape[1])], 
                            index=[f'Regime_{i+1}' for i in range(n_clusters)])
centroids_df.to_pickle(centroid_file)
print(f'Centroids saved to {centroid_file}')


# Calculate regime strength (distances to centroids)
def calculate_regime_strength(pcs, centroids):
    # Compute Euclidean distance between each PC time step and each regime centroid
    distances = cdist(pcs, centroids, metric='euclidean')
    
    # Normalize strengths so they sum to 1 for each timestep
    normalized_strengths = 1 / distances
    normalized_strengths /= normalized_strengths.sum(axis=1, keepdims=True)
    return normalized_strengths

# Calculate regime probabilities (using softmax)
def calculate_regime_probability(distances):
    # Apply softmax to distances (closer distances should have higher probabilities)
    from scipy.special import softmax
    probabilities = softmax(-distances, axis=1)
    return probabilities

# Function to normalize regime strengths by mean and std (per regime)
def normalize_regime_strengths_by_mean_std(strengths):
    # Calculate mean and std for each regime (along time axis)
    regime_means = np.mean(strengths, axis=0)  # Mean for each regime
    regime_stds = np.std(strengths, axis=0)    # Std for each regime
    
    # Normalize each regime's strength by its respective mean and std
    normalized_strengths = (strengths - regime_means) / regime_stds
    return normalized_strengths

# Step 1: Project Anomalies onto the EOFs (20 components, Non-Normalized Data)
def project_onto_eofs(data_region, eofs):
    # Reshape the geopotential height anomalies into 2D (time, spatial) format
    reshaped_data = data_region.values.reshape(data_region.shape[0], -1)
    
    # Normalize the geopotential height anomalies (mean subtraction)
    anomalies = reshaped_data - reshaped_data.mean(axis=0)
    
    # Project anomalies onto the EOFs (inner product between anomalies and EOFs)
    projections = np.dot(anomalies, eofs.values.reshape(eofs.shape[0], -1).T)
    
    return projections

# Step 2: Project onto Regime Centroids (Non-Normalized Data)
def project_onto_regimes(projections, centroids):
    # Compute projection onto regime centroids (reduce from 20 EOF components to 7 regime centroids)
    projected_regimes = np.dot(projections, centroids.T)
    return projected_regimes


# Function to compute and apply month-wise normalization
def compute_month_wise_normalization(pcs, time_coords):
    pcs_normalized = np.zeros_like(pcs)
    
    # Convert time coordinates to a DataArray with month information
    time_months = xr.DataArray(time_coords, dims="time").dt.month

    # Loop over each month
    for month in range(1, 13):
        # Select the PCs for the current month
        month_indices = np.where(time_months == month)[0]
        month_pcs = pcs[month_indices, :]
        
        # Compute mean and std for the PCs of the current month
        mean_pcs = np.mean(month_pcs, axis=0)
        std_pcs = np.std(month_pcs, axis=0)
        
        # Normalize the PCs for the current month
        pcs_normalized[month_indices, :] = (month_pcs - mean_pcs) / std_pcs
    
    return pcs_normalized

# Apply the normalization
normalized_pcs = compute_month_wise_normalization(pcs, time_coords)

# Continue with the rest of your process...




# Step 4: Save the Projections (Non-Normalized and Normalized)

# Compute the non-normalized projection of geopotential anomalies onto EOFs (20 EOFs)
projections = project_onto_eofs(data_region, eofs)

# Project onto regime centroids (non-normalized data)
non_normalized_projections = project_onto_regimes(projections, centroids)

# Normalize the projections for optional analysis or comparison
normalized_projections = compute_month_wise_normalization(non_normalized_projections, time_coords)

# Save the non-normalized projections as the regime index (7 regimes)
non_normalized_file = os.path.join(regimes_dir, 'regime_non_normalized_projection.nc')

# Convert to xarray DataArray and save
non_normalized_xr = xr.DataArray(non_normalized_projections, dims=['time', 'regime'], 
                                 coords={'time': time_coords, 'regime': np.arange(1, n_clusters + 1)})
non_normalized_xr.to_netcdf(non_normalized_file)

# Save the normalized projections as well (optional)
normalized_file = os.path.join(regimes_dir, 'regime_normalized_projection.nc')

# Convert to xarray DataArray and save
normalized_xr = xr.DataArray(normalized_projections, dims=['time', 'regime'], 
                             coords={'time': time_coords, 'regime': np.arange(1, n_clusters + 1)})
normalized_xr.to_netcdf(normalized_file)

# Save non-normalized projections as a pandas DataFrame
non_normalized_df = pd.DataFrame(non_normalized_projections, columns=[f'Regime_{i+1}' for i in range(n_clusters)], index=time_coords)
non_normalized_df.to_pickle(os.path.join(regimes_dir, 'non_normalized_projections.pkl'))
print(f'Non-normalized projections saved as DataFrame.')

# Save normalized projections as a pandas DataFrame
normalized_df = pd.DataFrame(normalized_projections, columns=[f'Regime_{i+1}' for i in range(n_clusters)], index=time_coords)
normalized_df.to_pickle(os.path.join(regimes_dir, 'normalized_projections.pkl'))
print(f'Normalized projections saved as DataFrame.')

print(f'Non-Normalized projections saved to {non_normalized_file}')
print(f'Normalized projections saved to {normalized_file}')


# Calculate the mean geopotential height for each regime
mean_geopotential_by_regime = np.zeros((n_clusters, data_region.latitude.size, data_region.longitude.size))

for cluster in range(n_clusters):
    indices = np.where(regimes == cluster)[0]  # Select indices for this cluster
    regime_data = data_region.isel(valid_time=indices)
    mean_geopotential_by_regime[cluster, :, :] = regime_data.mean(dim='valid_time')
    
# After computing mean_geopotential_by_regime, save the means to a NetCDF file
mean_geopotential_file = os.path.join(regimes_dir, 'mean_geopotential_by_regime.nc')
mean_geopotential_xr = xr.DataArray(mean_geopotential_by_regime, dims=['regime', 'latitude', 'longitude'],
                                    coords={'regime': np.arange(1, n_clusters + 1),
                                            'latitude': data_region.latitude,
                                            'longitude': data_region.longitude})
mean_geopotential_xr.to_netcdf(mean_geopotential_file)
print(f'Mean geopotential heights saved to {mean_geopotential_file}')



# Plot regime maps for the current combination of PCs and clusters
fig, axes = plt.subplots(nrows=(n_clusters + 1) // 2, ncols=2, figsize=(15, 10), subplot_kw={'projection': ccrs.PlateCarree()})

# Flatten the axes array to iterate through it easily
axes = axes.flatten()

for i, regime_map in enumerate(mean_geopotential_by_regime):
    ax = axes[i]
    
    # Set the extent based on the indices provided by ea_lon and ea_lat
    ax.set_extent([-90, 60, 20, 80], crs=ccrs.PlateCarree())  # Euro-Atlantic extent
    
    # Add coastlines and borders for geographical context
    ax.coastlines()
    ax.add_feature(cfeature.BORDERS, linestyle=':')
    
    # Interpolation step: Create a finer grid for interpolation
    lon_new = np.linspace(data_region.longitude.min(), data_region.longitude.max(), 1000)
    lat_new = np.linspace(data_region.latitude.min(), data_region.latitude.max(), 500)
    lon_grid, lat_grid = np.meshgrid(lon_new, lat_new)

    # Create a meshgrid from the original longitudes and latitudes slices
    lon_orig, lat_orig = np.meshgrid(data_region.longitude, data_region.latitude)

    # Interpolate the regime_map onto the finer grid
    regime_map_interp = griddata((lon_orig.ravel(), lat_orig.ravel()), regime_map.ravel(), (lon_grid, lat_grid), method='linear')

    # Plot the interpolated data using the finer grid
    contour = ax.contourf(lon_new, lat_new, regime_map_interp, cmap='coolwarm', levels=20, transform=ccrs.PlateCarree())
    
    # Add colorbar to each subplot
    plt.colorbar(contour, ax=ax, orientation='horizontal', label='Geopotential Height Anomaly')
    
    # Set title for each regime
    ax.set_title(f'Regime {i + 1}')
    ax.set_xlabel('Longitude')
    ax.set_ylabel('Latitude')

# If there are fewer regimes than subplots, hide the empty subplot
for j in range(i + 1, len(axes)):
    fig.delaxes(axes[j])

# Adjust layout for the subplots
plt.tight_layout()

# Save the figure
plt.savefig(os.path.join(maps_dir, 'regime_maps_fixed_interpolation.png'))

# Show the figure
plt.show()
plt.close()
