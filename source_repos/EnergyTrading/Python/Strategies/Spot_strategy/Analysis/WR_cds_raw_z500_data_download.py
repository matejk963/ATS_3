import cdsapi
import xarray as xr
import os
import numpy as np

# Initialize the CDS API client
c = cdsapi.Client()

# Define the directory where the data will be saved
output_dir = r'Z:\Data\Spot\Weather\RawData\ERA5\geopotential'
os.makedirs(output_dir, exist_ok=True)

# Define the years you want to download
years = [str(year) for year in range(1989, 2025)]

# Download the data year by year
for year in years:
    print(f"Downloading data for year {year}")
    
    # Temporary file to save the whole year data
    year_file = os.path.join(output_dir, f'geopotential_{year}.nc')
    
    # Request the full year's data
    c.retrieve(
        'reanalysis-era5-pressure-levels',
        {
            'product_type': 'reanalysis',
            'variable': 'geopotential',
            'pressure_level': '500',
            'year': year,
            'month': [str(month).zfill(2) for month in range(1, 13)],
            'day': [str(day).zfill(2) for day in range(1, 32)],
            'time': '12:00',
            'format': 'netcdf',
        },
        year_file
    )
    
    print(f"Downloaded data for year {year}, now splitting into daily files...")
    
    

print("All data download complete!")
