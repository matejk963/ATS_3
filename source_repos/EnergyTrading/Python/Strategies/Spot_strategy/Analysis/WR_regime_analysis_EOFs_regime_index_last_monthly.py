import xarray as xr
import numpy as np
import os
from eofs.xarray import Eof
from sklearn.cluster import KMeans
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import pandas as pd
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

# Function to save geopotential height maps
def save_geopotential_height_maps(mean_geopotential_by_regime, month):
    fig, axes = plt.subplots(nrows=(n_clusters + 1) // 2, ncols=2, figsize=(15, 10), subplot_kw={'projection': ccrs.PlateCarree()})
    axes = axes.flatten()
    
    for i, regime_map in enumerate(mean_geopotential_by_regime):
        ax = axes[i]
        ax.set_extent([-90, 60, 20, 80], crs=ccrs.PlateCarree())
        ax.coastlines()
        ax.add_feature(cfeature.BORDERS, linestyle=':')
        
        lon_new = np.linspace(data_region.longitude.min(), data_region.longitude.max(), 1000)
        lat_new = np.linspace(data_region.latitude.min(), data_region.latitude.max(), 500)
        lon_grid, lat_grid = np.meshgrid(lon_new, lat_new)
        lon_orig, lat_orig = np.meshgrid(data_region.longitude, data_region.latitude)
        
        regime_map_interp = griddata((lon_orig.ravel(), lat_orig.ravel()), regime_map.ravel(), (lon_grid, lat_grid), method='linear')
        contour = ax.contourf(lon_new, lat_new, regime_map_interp, cmap='coolwarm', levels=20, transform=ccrs.PlateCarree())
        plt.colorbar(contour, ax=ax, orientation='horizontal', label='Geopotential Height Anomaly')
        ax.set_title(f'Regime {i + 1}')
    
    for j in range(i + 1, len(axes)):
        fig.delaxes(axes[j])

    plt.tight_layout()
    plt.savefig(os.path.join(maps_dir, f'regime_maps_month_{month}.png'))
    plt.show()
    plt.close()

# Step 1: Adjust data for fitting monthly windows (previous month, current month, and next month)
def get_month_window_data(all_data, month):
    prev_month = (month - 2) % 12 + 1
    next_month = month % 12 + 1
    
    # Get data for the three-month window
    selected_data = all_data.sel(valid_time=all_data['valid_time.month'].isin([prev_month, month, next_month]))
    
    return selected_data

# Supporting functions for projection and normalization
def project_onto_eofs(data_region, eofs):
    reshaped_data = data_region.values.reshape(data_region.shape[0], -1)
    anomalies = reshaped_data - reshaped_data.mean(axis=0)
    projections = np.dot(anomalies, eofs.values.reshape(eofs.shape[0], -1).T)
    return projections

def project_onto_regimes(projections, centroids):
    projected_regimes = np.dot(projections, centroids.T)
    return projected_regimes

def normalize_projections(projections, centroids):
    centroids_t = centroids
    projections_in_eof_space = np.dot(projections, centroids_t)
    distances = cdist(projections_in_eof_space, centroids, metric='euclidean')
    normalized_projections = (distances - np.mean(distances, axis=0)) / np.std(distances, axis=0)
    return normalized_projections

# Step 2: Loop through each month and apply EOF and regime analysis
for month in range(1, 13):
    print(f"Processing month {month}")
    
    # Get data for the current month window (prev_month, month, next_month)
    month_data = get_month_window_data(all_data, month)
    
    # Ensure time is the first dimension
    month_data = month_data.transpose('valid_time', 'latitude', 'longitude')

    # Perform EOF analysis using the eofs package on the selected data
    solver = Eof(month_data)

    # Number of EOFs to retain
    n_modes = 20  # Adjust as needed

    # Get the EOFs (spatial patterns) and PCs (time series)
    eofs = solver.eofs(neofs=n_modes)
    pcs = solver.pcs(npcs=n_modes)

    # Perform K-Means clustering on the PCs
    n_clusters = 6  # Adjust the number of clusters as needed
    kmeans = KMeans(n_clusters=n_clusters, random_state=42)
    kmeans.fit(pcs)

    # Get the cluster labels (i.e., regimes)
    regimes = kmeans.labels_

    # Calculate regime centroids (mean PC for each cluster)
    centroids = np.zeros((n_clusters, pcs.shape[1]))
    for cluster in range(n_clusters):
        indices = np.where(regimes == cluster)[0]
        centroids[cluster, :] = pcs[indices, :].mean(axis=0)

    # Step 3: Project the data onto EOFs
    projections = project_onto_eofs(month_data, eofs)
    
    # Project onto regime centroids (non-normalized data)
    non_normalized_projections = project_onto_regimes(projections, centroids)
    
    # Normalize the projections for optional analysis or comparison
    normalized_projections = normalize_projections(non_normalized_projections, centroids)

    # Save the projections for this month
    non_normalized_file = os.path.join(regimes_dir, f'regime_non_normalized_projection_month_{month}.nc')
    non_normalized_xr = xr.DataArray(non_normalized_projections, dims=['time', 'regime'], 
                                     coords={'time': month_data['valid_time'].values, 'regime': np.arange(1, n_clusters + 1)})
    non_normalized_xr.to_netcdf(non_normalized_file)

    # Save the normalized projections as well (optional)
    normalized_file = os.path.join(regimes_dir, f'regime_normalized_projection_month_{month}.nc')
    normalized_xr = xr.DataArray(normalized_projections, dims=['time', 'regime'], 
                                 coords={'time': month_data['valid_time'].values, 'regime': np.arange(1, n_clusters + 1)})
    normalized_xr.to_netcdf(normalized_file)

    print(f'Projections saved for month {month}')

    # Calculate and save mean geopotential height maps
    mean_geopotential_by_regime = np.zeros((n_clusters, data_region.latitude.size, data_region.longitude.size))

    for cluster in range(n_clusters):
        indices = np.where(regimes == cluster)[0]  # Select indices for this cluster
        regime_data = data_region.isel(valid_time=indices)
        mean_geopotential_by_regime[cluster, :, :] = regime_data.mean(dim='valid_time')
    
    save_geopotential_height_maps(mean_geopotential_by_regime, month)


