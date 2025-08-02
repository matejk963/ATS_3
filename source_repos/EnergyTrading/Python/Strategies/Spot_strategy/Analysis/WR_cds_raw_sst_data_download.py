# -*- coding: utf-8 -*-
"""
Created on Mon Sep 16 14:30:13 2024

@author: krajcovic
"""

import cdsapi
import os

# Initialize the CDS API client
c = cdsapi.Client()

# Define the directory where the SST data will be saved
output_dir = r'Z:\Data\Spot\Weather\SST'
os.makedirs(output_dir, exist_ok=True)

# Define the years for which you want to download the SST data
years = [str(year) for year in range(2024, 2025)]

# Download SST data year by year
for year in years:
    print(f"Downloading SST data for year {year}")
    
    # File path to save the SST data
    sst_file = os.path.join(output_dir, f'SST_{year}.nc')
    
    # Request the SST data
    c.retrieve(
        'reanalysis-era5-single-levels',
        {
            'product_type': 'reanalysis',
            'variable': 'sea_surface_temperature',
            'year': year,
            'month': [str(month).zfill(2) for month in range(1, 13)],
            'day': [str(day).zfill(2) for day in range(1, 32)],
            'time': '12:00',
            'format': 'netcdf',
        },
        sst_file
    )
    
    print(f"SST data for year {year} downloaded and saved to {sst_file}")

print("All SST data download complete!")
