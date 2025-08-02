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

# Perform PCA on all data (entire year)
n_components = 2000  # Adjust the number of components as needed
pca = PCA(n_components=n_components)
PCs = pca.fit_transform(reshaped_data)

# Perform K-Means clustering on the principal components
n_clusters = 8 # Adjust the number of clusters as needed
kmeans = KMeans(n_clusters=n_clusters, random_state=42)
kmeans.fit(PCs)

# Get the cluster labels (i.e., regimes) for all days
regimes = kmeans.labels_

# Calculate distances to cluster centers
distances = kmeans.transform(PCs)

# Calculate strengths as the inverse of the distances
strengths = 1 / distances
strengths /= strengths.sum(axis=1, keepdims=True)  # Normalize to sum to 1

# Create a DataFrame for the strengths with each column representing a regime
strengths_df = pd.DataFrame(strengths, columns=[f'Regime_{i+1}' for i in range(n_clusters)], index=times)

# Save the DataFrame as a pickle file
output_pickle_file = os.path.join(regimes_dir, 'regime_strengths_all_days.pkl')
strengths_df.to_pickle(output_pickle_file)
print(f"Regime strengths saved to {output_pickle_file} as a DataFrame")

# Plot the maps of each regime with a geographical background
mean_geopotential_by_regime = np.zeros((n_clusters, len(latitudes[ea_lat]), len(longitudes[ea_lon])))

for cluster in range(n_clusters):
    indices = np.where(regimes == cluster)[0]  # Select the indices for this cluster
    regime_data = all_data_sel[:, :, indices]  # Select data for the given cluster
    
    # Average over time (valid_time) for the regime
    mean_geopotential_by_regime[cluster, :, :] = np.nanmean(regime_data, axis=2)

# Create a figure with subplots (2 columns, ceil(n_clusters / 2) rows)
fig, axes = plt.subplots(nrows=(n_clusters + 1) // 2, ncols=2, figsize=(15, 10), subplot_kw={'projection': ccrs.PlateCarree()})

# Flatten the axes array to iterate through it easily
axes = axes.flatten()

# Plot regime maps for the entire year in a 2-column grid
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
    ax.set_title(f'Regime {i + 1}')
    ax.set_xlabel('Longitude')
    ax.set_ylabel('Latitude')

# If there are fewer regimes than subplots, hide the empty subplot
for j in range(i + 1, len(axes)):
    fig.delaxes(axes[j])

# Adjust layout for the subplots
plt.tight_layout()

# Save the figure
plt.savefig(os.path.join(regimes_dir, 'all_regimes.png'))

# Show the figure
plt.show()

print("All regime maps have been saved in a single figure.")
