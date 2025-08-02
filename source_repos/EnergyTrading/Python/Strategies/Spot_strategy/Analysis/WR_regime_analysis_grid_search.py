# -*- coding: utf-8 -*-
"""
Created on Tue Sep 10 07:45:05 2024

@author: krajcovic
"""


import numpy as np
import pandas as pd
import os
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
import xarray as xr
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from scipy.interpolate import griddata
import matplotlib.pyplot as plt

# Directory where normalized data is stored
normalized_dir = r'Z:\Data\Spot\Weather\Normalized'
regimes_dir = r'Z:\Data\Spot\Weather\Regimes'
os.makedirs(regimes_dir, exist_ok=True)

# Load all normalized data files
normalized_files = sorted([os.path.join(normalized_dir, f) for f in os.listdir(normalized_dir) if f.endswith('.nc')])

# Initialize lists to store time, lat, lon, and data arrays
times = []
latitudes = []
longitudes = []
all_data = []

# Load data using xarray
for file in normalized_files:
    ds = xr.open_dataset(file)
    
    # Extract time, latitude, longitude, and geopotential height ('z') data
    times.append(ds['valid_time'].values)
    if len(latitudes) == 0:
        latitudes = ds['latitude'].values
    if len(longitudes) == 0:
        longitudes = ds['longitude'].values
    
    # Append the 'z' data
    all_data.append(ds['z'])
    
    ds.close()

# Convert lists to NumPy arrays
times = np.concatenate(times)
latitudes = np.array(latitudes)
longitudes = np.array(longitudes)
longitudes = (longitudes + 180) % 360 - 180

# Define Euro-Atlantic area
ea_lat_tuple = (30,70)
ea_lon_tuple = (-60,60)

# Concatenate the data along the valid_time axis (axis 0)
all_data = np.concatenate(all_data, axis=2)

# Select EA region lat/lon
# Masks
ea_lat = ((latitudes >= ea_lat_tuple[0]) & (latitudes <= ea_lat_tuple[1]))
ea_lon = ((longitudes >= ea_lon_tuple[0]) & (longitudes <= ea_lon_tuple[1]))

all_data_sel = all_data[ea_lat, :, :][:, ea_lon, :]

# Reshape the data: (time, lat, lon) -> (time, spatial)
reshaped_data = all_data_sel.reshape(all_data_sel.shape[2], -1)

# Handle NaNs by filling them with the mean of each feature
reshaped_data_mean = np.nanmean(reshaped_data, axis=0)
nan_mask = np.isnan(reshaped_data)
reshaped_data[nan_mask] = np.take(reshaped_data_mean, np.where(nan_mask)[1])

# Define the list of numbers of PCs and clusters to test
num_pcs_list = [100, 500, 1000]  # Example list of number of PCs
num_clusters_list = [7, 10]  # Example list of number of clusters

# DataFrame to store explained variance and other statistics
explained_variance_df = pd.DataFrame(columns=['num_PCs', 'num_clusters', 'explained_variance'])

# Loop through combinations of number of PCs and clusters
for num_pcs in num_pcs_list:
    for num_clusters in num_clusters_list:
        print(f"Processing with {num_pcs} PCs and {num_clusters} clusters")
        
        # Perform PCA with the current number of PCs
        pca = PCA(n_components=num_pcs)
        PCs = pca.fit_transform(reshaped_data)
        
        # Save explained variance for this number of PCs
        explained_variance = pca.explained_variance_ratio_.sum()
        explained_variance_df = explained_variance_df.append({'num_PCs': num_pcs, 'num_clusters': num_clusters, 
                                                              'explained_variance': explained_variance}, ignore_index=True)
        
        # Perform K-Means clustering with the current number of clusters
        kmeans = KMeans(n_clusters=num_clusters, random_state=42)
        kmeans.fit(PCs)
        
        # Get the cluster labels (i.e., regimes)
        regimes = kmeans.labels_
        
        # Calculate distances to cluster centers
        distances = kmeans.transform(PCs)
        
        # Calculate strengths as the inverse of the distances
        strengths = 1 / distances
        strengths /= strengths.sum(axis=1, keepdims=True)  # Normalize to sum to 1
        
        # Create a DataFrame for the strengths
        strengths_df = pd.DataFrame(strengths, columns=[f'Regime_{i+1}' for i in range(num_clusters)], index=times)
        
        # Save the DataFrame as a pickle file for the current combination of PCs and clusters
        output_pickle_file = os.path.join(regimes_dir, f'regime_strengths_{num_pcs}_PCs_{num_clusters}_clusters.pkl')
        strengths_df.to_pickle(output_pickle_file)
        print(f"Regime strengths saved to {output_pickle_file} as a DataFrame")
        
        # Calculate mean geopotential for each regime
        mean_geopotential_by_regime = np.zeros((num_clusters, len(latitudes[ea_lat]), len(longitudes[ea_lon])))
        
        for cluster in range(num_clusters):
            indices = np.where(regimes == cluster)[0]  # Select the indices for this cluster
            regime_data = all_data_sel[:, :, indices]  # Select data for the given cluster
            
            # Average over time (valid_time) for the regime
            mean_geopotential_by_regime[cluster, :, :] = np.nanmean(regime_data, axis=2)
        
        # Plot regime maps for the current combination of PCs and clusters
        fig, axes = plt.subplots(nrows=(num_clusters + 1) // 2, ncols=2, figsize=(15, 10), subplot_kw={'projection': ccrs.PlateCarree()})
        
        # Flatten the axes array to iterate through it easily
        axes = axes.flatten()
        
        for i, regime_map in enumerate(mean_geopotential_by_regime):
            ax = axes[i]
            
            # Set the extent based on the indices provided by ea_lon and ea_lat
            ax.set_extent([longitudes[ea_lon].min(), longitudes[ea_lon].max(), 
                           latitudes[ea_lat].min(), latitudes[ea_lat].max()], crs=ccrs.PlateCarree())
            
            # Add coastlines and borders for geographical context
            ax.coastlines()
            ax.add_feature(cfeature.BORDERS, linestyle=':')
            
            # Interpolation step: Create a finer grid for interpolation
            lon_new = np.linspace(longitudes[ea_lon].min(), longitudes[ea_lon].max(), 1000)
            lat_new = np.linspace(latitudes[ea_lat].min(), latitudes[ea_lat].max(), 500)
            lon_grid, lat_grid = np.meshgrid(lon_new, lat_new)
        
            # Create a meshgrid from the original longitudes and latitudes slices
            lon_orig, lat_orig = np.meshgrid(longitudes[ea_lon], latitudes[ea_lat])
        
            # Interpolate the regime_map onto the finer grid
            regime_map_interp = griddata((lon_orig.ravel(), lat_orig.ravel()), regime_map.ravel(), (lon_grid, lat_grid), method='linear')
        
            # Plot the interpolated data using the finer grid
            contour = ax.contourf(lon_new, lat_new, regime_map_interp, cmap='coolwarm', levels=20, transform=ccrs.PlateCarree())
            
            # Add colorbar to each subplot
            plt.colorbar(contour, ax=ax, orientation='horizontal', label='Geopotential Height Anomaly')
            
            # Set title for each regime
            ax.set_title(f'{num_pcs} PCs, {num_clusters} Clusters - Regime {i + 1}')
            ax.set_xlabel('Longitude')
            ax.set_ylabel('Latitude')
        
        # If there are fewer regimes than subplots, hide the empty subplot
        for j in range(i + 1, len(axes)):
            fig.delaxes(axes[j])
        
        # Adjust layout for the subplots
        plt.tight_layout()
        
        # Save the figure
        plt.savefig(os.path.join(regimes_dir, f'regime_maps_{num_pcs}_PCs_{num_clusters}_clusters.png'))
        
        # Show the figure
        plt.show()

# Save explained variance statistics
explained_variance_df.to_csv(os.path.join(regimes_dir, 'explained_variance_statistics.csv'), index=False)
print("Explained variance statistics saved to CSV.")
