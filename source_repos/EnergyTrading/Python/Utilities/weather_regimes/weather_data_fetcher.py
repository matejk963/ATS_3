import cdsapi
import os
import xarray as xr
import numpy as np
from datetime import datetime, timedelta
import requests
import cfgrib

class WeatherDataFetcher:
    def __init__(self, base_output_dir):
        """
        Initialize the WeatherDataFetcher class.

        Args:
            base_output_dir (str): Base directory where data will be stored.
        """
        self.base_output_dir = base_output_dir
        os.makedirs(self.base_output_dir, exist_ok=True)
        self.cds_client = cdsapi.Client()
        self.dir_dict = {
            "ERA5": {
                "geopotential": os.path.join(self.base_output_dir, "ERA5", "geopotential")
            },
            "GFS": {
                "geopotential": os.path.join(self.base_output_dir, "GFS", "geopotential")
            }
            # Add other data types and sources here as needed
        }
        for source, variables in self.dir_dict.items():
            for variable, path in variables.items():
                os.makedirs(path, exist_ok=True)

    def _get_last_downloaded_date(self, file_path):
        """
        Get the last date of data in an existing NetCDF file.

        Args:
            file_path (str): Path to the NetCDF file.

        Returns:
            datetime: Last date in the NetCDF file.
        """
        if not os.path.exists(file_path):
            return None

        try:
            with xr.open_dataset(file_path) as ds:
                if "time" in ds:
                    time_values = ds.time.values
                elif "datetime" in ds:
                    time_values = ds.datetime.values
                elif "date" in ds:
                    time_values = ds.date.values
                elif "valid_time" in ds:
                    time_values = ds.valid_time.values
                else:
                    raise ValueError("No recognizable time variable found in the dataset.")

                last_date = np.max(time_values)
                return np.datetime64(last_date).astype(datetime)
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            return None

    def download_era5_data(self, start_year, end_year, variable, pressure_level):
        """
        Download ERA5 data for the given years and store them in the appropriate directory.

        Args:
            start_year (int): Start year for the data.
            end_year (int): End year for the data.
            variable (str): Variable to download (e.g., "geopotential").
            pressure_level (str): Pressure level (e.g., "500").
        """
        output_dir = self.dir_dict.get("ERA5", {}).get(variable, self.base_output_dir)

        for year in range(start_year, end_year + 1):
            print(f"Processing year {year}...")
            year_file = os.path.join(output_dir, f"{variable}_{year}.nc")

            if year < end_year:
                if os.path.exists(year_file):
                    print(f"File for year {year} already exists: {year_file}. Skipping download.")
                    continue
                else:
                    last_date = self._get_last_downloaded_date(year_file)

                    if last_date:
                        start_date = last_date - timedelta(days=5)
                        print(f"Resuming download from {start_date} for year {year}...")
                    else:
                        start_date = datetime(year, 1, 1)
                        print(f"Downloading full year {year}...")

                    try:
                        self.cds_client.retrieve(
                            'reanalysis-era5-pressure-levels',
                            {
                                'product_type': 'reanalysis',
                                'variable': variable,
                                'pressure_level': pressure_level,
                                'year': str(year),
                                'month': [str(month).zfill(2) for month in range(1, 13)],
                                'day': [str(day).zfill(2) for day in range(1, 32)],
                                'time': '12:00',
                                'format': 'netcdf',
                            },
                            year_file
                        )
                        print(f"Downloaded data for year {year} to {year_file}")

                    except Exception as e:
                        print(f"Error downloading data for year {year}: {e}")
            else:  # Always download for the end_year
                print(f"Downloading data for final year {end_year}...")
                try:
                    self.cds_client.retrieve(
                        'reanalysis-era5-pressure-levels',
                        {
                            'product_type': 'reanalysis',
                            'variable': variable,
                            'pressure_level': pressure_level,
                            'year': str(year),
                            'month': [str(month).zfill(2) for month in range(1, 13)],
                            'day': [str(day).zfill(2) for day in range(1, 32)],
                            'time': '12:00',
                            'format': 'netcdf',
                        },
                        year_file
                    )
                    print(f"Downloaded data for year {year} to {year_file}")

                except Exception as e:
                    print(f"Error downloading data for year {year}: {e}")

    def download_gfs_data(self, start_date, end_date, variable):
        """
        Download GFS data for the given date range and store them in the appropriate directory.

        Args:
            start_date (datetime): Start date for the data.
            end_date (datetime): End date for the data.
            variable (str): Variable to download (e.g., "geopotential").
        """
        output_dir = self.dir_dict.get("GFS", {}).get(variable, self.base_output_dir)
        current_date = start_date

        while current_date <= end_date:
            print(f"Processing date {current_date.strftime('%Y-%m-%d')}...")
            date_str = current_date.strftime('%Y%m%d')
            file_name = f"gfs_{variable}_500hPa_{date_str}.grib2"
            file_path = os.path.join(output_dir, file_name)

            if os.path.exists(file_path):
                print(f"File already exists: {file_path}, skipping download.")
                current_date += timedelta(days=1)
                continue

            # Construct GFS URL for the first available hour and 500 hPa
            base_url = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod/"
            gfs_cycle = "00"  # Default cycle, can be parameterized
            file_url = f"{base_url}gfs.{date_str}/{gfs_cycle}/atmos/gfs.t{gfs_cycle}z.pgrb2.0p25.f000"

            try:
                response = requests.get(file_url, stream=True)
                if response.status_code == 200:
                    with open(file_path, "wb") as f:
                        f.write(response.content)
                    print(f"Downloaded GFS data for {current_date.strftime('%Y-%m-%d')} to {file_path}")

                    # Transform GRIB2 to NetCDF
                    self.convert_grib2_to_netcdf(file_path)

                else:
                    print(f"Failed to download GFS data for {current_date.strftime('%Y-%m-%d')}: HTTP {response.status_code}")
            except Exception as e:
                print(f"Error downloading GFS data for {current_date.strftime('%Y-%m-%d')}: {e}")

            current_date += timedelta(days=1)

    def convert_grib2_to_netcdf(self, grib2_path):
        """
        Convert a GRIB2 file to NetCDF format, extracting only the geopotential height variable.

        Args:
            grib2_path (str): Path to the GRIB2 file.
        """
        netcdf_path = grib2_path.replace('.grib2', '.nc')
        try:
            # Open GRIB2 file and filter for data at 500 hPa
            ds = cfgrib.open_datasets(
                grib2_path, 
                backend_kwargs={"filter_by_keys": {"typeOfLevel": "isobaricInhPa", "level": 500}}
            )
            
            # Merge datasets
            combined_ds = xr.merge(ds, compat="override")
            
            # Extract only the geopotential height ('gh') variable
            if "gh" in combined_ds.data_vars:
                combined_ds = combined_ds[["gh"]]
            else:
                raise KeyError("'gh' variable not found in the dataset.")
            
            # Save the filtered dataset to NetCDF
            combined_ds.to_netcdf(netcdf_path)
            print(f"Converted {grib2_path} to {netcdf_path}, extracting only 'gh'")
            
            # Iterate over directory and delete GRIB2 and auxiliary files
            directory = os.path.dirname(grib2_path)
            for file_name in os.listdir(directory):
                if file_name.endswith('.grib2') or file_name.endswith('.idx'):
                    file_to_delete = os.path.join(directory, file_name)
                    os.remove(file_to_delete)
                    print(f"Deleted file: {file_to_delete}")
        except Exception as e:
            print(f"Error converting {grib2_path} to NetCDF: {e}")




if __name__ == "__main__":
    base_dir = r'W:\Data\Spot\Weather\RawData'
    fetcher = WeatherDataFetcher(base_output_dir=base_dir)

    # Example: Download ERA5 geopotential data for 500 hPa from 1989 to 2024
    fetcher.download_era5_data(start_year=1979, end_year=2024, variable="geopotential", pressure_level="500")

    # Example: Download GFS geopotential data for a specific date range
    start_date = datetime(2024, 12, 18)
    end_date = datetime(2024, 12, 27)
    fetcher.download_gfs_data(start_date=start_date, end_date=end_date, variable="geopotential")
