import cdsapi
import os
import time

# Initialize the CDS API client
c = cdsapi.Client()

# Define the directory where MJO data will be saved
output_dir = r'Z:\Data\Spot\Weather\MJO_raw_data'
os.makedirs(output_dir, exist_ok=True)

# Define the years for which you want to download the data
years = [str(year) for year in range(2005, 2025)]

# Variables needed for MJO: U-wind at 850 hPa and 200 hPa, OLR
variables = [
    {'name': 'u_component_of_wind', 'pressure_levels': ['850', '200']},
    {'name': 'top_net_thermal_radiation', 'pressure_levels': None}  # Updated name for OLR
]

# Retry configuration
max_retries = 5
wait_time = 60  # in seconds

# Download data year by year
for year in years:
    for variable in variables:
        if variable['pressure_levels']:
            # For u_component_of_wind at specified pressure levels
            for pressure in variable['pressure_levels']:
                print(f"Downloading {variable['name']} data for year {year} at {pressure} hPa")

                # File path to save the data
                var_file = os.path.join(output_dir, f"{variable['name']}_{pressure}_{year}.nc")

                # Request the data for wind variables
                retries = 0
                while retries < max_retries:
                    try:
                        c.retrieve(
                            'reanalysis-era5-pressure-levels',
                            {
                                'product_type': 'reanalysis',
                                'variable': variable['name'],
                                'pressure_level': pressure,
                                'year': year,
                                'month': [str(month).zfill(2) for month in range(1, 13)],
                                'day': [str(day).zfill(2) for day in range(1, 32)],
                                'time': '00:00',
                                'format': 'netcdf',
                            },
                            var_file
                        )
                        break  # Break the loop if successful
                    except ValueError as e:
                        if "Result not ready, job is running" in str(e):
                            retries += 1
                            print(f"Retry {retries}/{max_retries} for {variable['name']} ({pressure} hPa) in {year}")
                            time.sleep(wait_time)
                        else:
                            raise e

        else:
            # For outgoing_longwave_radiation (single-level variable)
            print(f"Downloading {variable['name']} data for year {year}")

            # File path to save the data
            var_file = os.path.join(output_dir, f"{variable['name']}_{year}.nc")

            # Request the data for OLR
            retries = 0
            while retries < max_retries:
                try:
                    c.retrieve(
                        'reanalysis-era5-single-levels',
                        {
                            'product_type': 'reanalysis',
                            'variable': variable['name'],
                            'year': year,
                            'month': [str(month).zfill(2) for month in range(1, 13)],
                            'day': [str(day).zfill(2) for day in range(1, 32)],
                            'time': '00:00',
                            'format': 'netcdf',
                        },
                        var_file
                    )
                    break  # Break the loop if successful
                except ValueError as e:
                    if "Result not ready, job is running" in str(e):
                        retries += 1
                        print(f"Retry {retries}/{max_retries} for {variable['name']} in {year}")
                        time.sleep(wait_time)
                    else:
                        raise e

        print(f"Data for {variable['name']} ({pressure if variable['pressure_levels'] else 'single level'}) for year {year} downloaded and saved to {var_file}")

print("All MJO-related data download complete!")
