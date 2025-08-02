import cdsapi
import xarray as xr
import numpy as np
import os
import threadpoolctl
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans

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

import numpy as np
import xarray as xr
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
from scipy.signal import butter, filtfilt
import matplotlib.pyplot as plt
import cartopy.crs as ccrs

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
labels = kmeans.fit_predict(PCs)

# Step 5: Assign regimes back to the original data
daily_anomalies = daily_anomalies.assign_coords(regime=('time', labels.astype(int)))



# Step 6: Normalize to remove seasonal amplitude variability
mean_anomaly = daily_anomalies.mean(dim='time')
std_anomaly = daily_anomalies.std(dim='time')
normalized_anomalies = (daily_anomalies - mean_anomaly) / std_anomaly

# Step 7: Further refine regime definitions (optional)
# Implement persistence criteria, lifecycle stages, etc.

# Step 8: Visualization of Regimes
fig, axes = plt.subplots(num_regimes, 1, figsize=(10, 20), subplot_kw={'projection': ccrs.PlateCarree()})
for regime in range(num_regimes):
    ax = axes[regime]
    ax.set_extent([-90, 30, 20, 80], crs=ccrs.PlateCarree())
    ax.coastlines()
    regime_data = normalized_anomalies.where(daily_anomalies.regime == regime, drop=True).mean(dim='time')
    im = ax.contourf(normalized_anomalies.longitude, normalized_anomalies.latitude, regime_data,
                     transform=ccrs.PlateCarree(), cmap='coolwarm')
    ax.set_title(f'Weather Regime {regime + 1}')
    fig.colorbar(im, ax=ax, orientation='horizontal', pad=0.05)

plt.tight_layout()
plt.show()
