# -*- coding: utf-8 -*-
"""
Created on Fri Jul 19 11:09:02 2024

@author: krajcovic
"""

import cdsapi
import xarray as xr
import pickle
import os

# Ensure the threadpool limits are set correctly to avoid issues
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

# Function to download data for a given year
def download_era5_data(year):
    c = cdsapi.Client()
    c.retrieve(
        'reanalysis-era5-pressure-levels',
        {
            'product_type': 'reanalysis',
            'variable': 'geopotential',
            'pressure_level': '500',
            'year': str(year),
            'month': [str(m).zfill(2) for m in range(1, 13)],
            'day': [str(d).zfill(2) for d in range(1, 32)],
            'time': '12:00',
            'format': 'netcdf',
        },
        f'download_{year}.nc'
    )

# Download data for the specified period
years = range(1979, 2024)  # Update to include up to the present year
for year in years:
    download_era5_data(year)


# Load each NetCDF file and save as a separate pickle file
for year in years:
    ds = xr.open_dataset(f'download_{year}.nc')
    file_path = f'Z:\Data\Spot\Weather\'era5_geopotential_500hPa_{year}.pkl'
    with open(file_path, 'wb') as f:
        pickle.dump(ds, f)
    print(f"Data for {year} saved to {file_path}")

print("All data successfully downloaded and saved as individual pickle files.")