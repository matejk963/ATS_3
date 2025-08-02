import os
import xarray as xr
import numpy as np
from scipy.signal import butter, filtfilt

class WeatherRegimePreprocessor:
    def __init__(self, data_source, base_dir):
        """
        Initialize the WeatherRegimePreprocessor class.

        Args:
            data_source (str): Either 'ERA5' or 'GFS'.
            base_dir (str): Base directory for input and output data.
        """
        self.data_source = data_source
        self.base_dir = base_dir
        self.input_dir = os.path.join(base_dir, "RawData", data_source, "geopotential")
        self.output_dir = os.path.join(base_dir, "ProcessedData", data_source, "geopotential")
        os.makedirs(self.output_dir, exist_ok=True)

    def load_data(self, variable, start_date, end_date):
        """
        Load geopotential height data for the specified variable and date range.

        Args:
            variable (str): Variable name (e.g., 'geopotential').
            start_date (str): Start date in 'YYYY-MM-DD' format.
            end_date (str): End date in 'YYYY-MM-DD' format.

        Returns:
            xarray.DataArray: Loaded data.
        """
        file_pattern = os.path.join(self.input_dir, f"{variable}_*.nc")
        dataset = xr.open_mfdataset(file_pattern, combine="by_coords")

        # Dynamically determine the time dimension
        time_dim = None
        for dim in dataset.dims:
            if "time" in dim.lower() or "valid_time" in dim.lower():
                time_dim = dim
                break

        if not time_dim:
            raise KeyError("No valid time dimension found in the dataset.")

        # Use 'z' for variable reference (geopotential height)
        if 'z' not in dataset.data_vars:
            raise KeyError("'z' variable (geopotential height) not found in the dataset.")

        # Squeeze out the single pressure level dimension
        data = dataset.sel({time_dim: slice(start_date, end_date)})['z'].squeeze(dim="pressure_level")
        print(f"Loaded data from {start_date} to {end_date} for {self.data_source}. Variable: 'z' (geopotential height)")
        return data

    def apply_low_pass_filter(self, data, cutoff_days=10):
        """
        Apply a 10-day low-pass filter to the data.

        Args:
            data (xarray.DataArray): Input data to filter.
            cutoff_days (int): Cutoff period for the low-pass filter in days.

        Returns:
            xarray.DataArray: Filtered data.
        """
        # Convert cutoff frequency to sampling frequency (assuming daily data)
        sampling_freq = 1  # Daily data means 1 sample per day
        nyquist_freq = sampling_freq / 2
        cutoff_freq = 1 / cutoff_days  # Frequency corresponding to the cutoff period
        b, a = butter(4, cutoff_freq / nyquist_freq, btype="low")

        def filter_func(x):
            return filtfilt(b, a, x, axis=0)

        # Rechunk along the 'valid_time' dimension to ensure a single chunk
        if data.chunks is not None:
            data = data.chunk({"valid_time": -1})

        filtered_data = xr.apply_ufunc(
            filter_func,
            data,
            input_core_dims=[["valid_time"]],
            output_core_dims=[["valid_time"]],
            vectorize=True,
            dask="parallelized",
            dask_gufunc_kwargs={"allow_rechunk": True},
            output_dtypes=[data.dtype],
        )
        print("Applied 10-day low-pass filter.")
        return filtered_data


    def calculate_climatology(self, data, window_days=90):
        """
        Calculate a running mean climatology for the data.

        Args:
            data (xarray.DataArray): Input data.
            window_days (int): Window size for the running mean in days.

        Returns:
            xarray.DataArray: Climatology data.
        """
        window_size = window_days  # Daily data, so window size is in days
        climatology = data.rolling(valid_time=window_size, center=True).mean()
        print(f"Calculated {window_days}-day running mean climatology.")
        return climatology

    def preprocess(self, variable, start_date, end_date):
        """
        Perform preprocessing steps on the data: load, filter, and calculate climatology.

        Args:
            variable (str): Variable name (e.g., 'geopotential').
            start_date (str): Start date in 'YYYY-MM-DD' format.
            end_date (str): End date in 'YYYY-MM-DD' format.

        Returns:
            None
        """
        # Step 1: Load data
        data = self.load_data(variable, start_date, end_date)

        # Step 2: Apply low-pass filter
        filtered_data = self.apply_low_pass_filter(data)

        # Step 3: Calculate climatology
        climatology = self.calculate_climatology(filtered_data)

        # Save the preprocessed data year by year
        years = np.unique(filtered_data["valid_time.year"])
        for year in years:
            yearly_data = climatology.sel(valid_time=slice(f"{year}-01-01", f"{year}-12-31"))
            output_file = os.path.join(self.output_dir, f"{variable}_preprocessed_{year}.nc")
            yearly_data.to_netcdf(output_file)
            print(f"Saved preprocessed data for year {year} to {output_file}")

# Example Usage
if __name__ == "__main__":
    base_directory = r"W:\Data\Spot\Weather"

    preprocessor = WeatherRegimePreprocessor(
        data_source="ERA5",
        base_dir=base_directory
    )

    # Preprocess data for geopotential height from 1989 to 2015
    preprocessor.preprocess(
        variable="geopotential",
        start_date="2013-01-01",
        end_date="2015-12-31"
    )
