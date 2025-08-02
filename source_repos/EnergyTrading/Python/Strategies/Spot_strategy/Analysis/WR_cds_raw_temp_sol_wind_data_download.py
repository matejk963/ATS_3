import cdsapi
import os

# Initialize the CDS API client
c = cdsapi.Client()

# Define the root directory where the data will be saved
base_dir = r'C:\Users\krajcovic\Documents\Algo\Projects\Data\Spot\Weather\RawData'
os.makedirs(base_dir, exist_ok=True)

# Define subdirectories for each data type
temperature_dir = os.path.join(base_dir, 'Temperature')
solar_dir = os.path.join(base_dir, 'Solar')
wind_dir = os.path.join(base_dir, 'Wind')

os.makedirs(temperature_dir, exist_ok=True)
os.makedirs(solar_dir, exist_ok=True)
os.makedirs(wind_dir, exist_ok=True)

# Define the years you want to download
years = [str(year) for year in range(1989, 2025)]

# # Download temperature data
# for year in years:
#     print(f"Downloading temperature data for year {year}")
#     temp_file = os.path.join(temperature_dir, f'temperature_{year}.nc')

#     c.retrieve(
#         'reanalysis-era5-single-levels',
#         {
#             'product_type': 'reanalysis',
#             'variable': '2m_temperature',
#             'year': year,
#             'month': [str(month).zfill(2) for month in range(1, 13)],
#             'day': [str(day).zfill(2) for day in range(1, 32)],
#             'time': ['00:00', '06:00', '12:00', '18:00'],
#             'format': 'netcdf',
#         },
#         temp_file
#     )
#     print(f"Temperature data for {year} saved.")

# Download solar radiation data
for year in years:
    print(f"Downloading solar radiation data for year {year}")
    solar_file = os.path.join(solar_dir, f'solar_radiation_{year}.nc')

    c.retrieve(
        'reanalysis-era5-single-levels',
        {
            'product_type': 'reanalysis',
            'variable': 'surface_solar_radiation_downwards',
            'year': year,
            'month': [str(month).zfill(2) for month in range(1, 13)],
            'day': [str(day).zfill(2) for day in range(1, 32)],
            'time': ['00:00', '06:00', '12:00', '18:00'],
            'format': 'netcdf',
        },
        solar_file
    )
    print(f"Solar radiation data for {year} saved.")

# Download wind speed data
for year in years:
    print(f"Downloading wind speed data for year {year}")
    wind_file = os.path.join(wind_dir, f'wind_speed_{year}.nc')

    c.retrieve(
        'reanalysis-era5-single-levels',
        {
            'product_type': 'reanalysis',
            'variable': ['10m_u_component_of_wind', '10m_v_component_of_wind'],
            'year': year,
            'month': [str(month).zfill(2) for month in range(1, 13)],
            'day': [str(day).zfill(2) for day in range(1, 32)],
            'time': ['00:00', '06:00', '12:00', '18:00'],
            'format': 'netcdf',
        },
        wind_file
    )
    print(f"Wind speed data for {year} saved.")

print("All data download complete!")
