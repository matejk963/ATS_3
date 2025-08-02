import os
import pandas as pd
from Database.DB_reader import Database
import datetime as dt
import re

# Paths and constants
output_dir = r'C:\data\Data\Spot\Entso\Outages\AvCap'
naming_dict = {
    'B01': 'Bio',
    'B02': 'Lig',
    'B04': 'Gas',
    'B05': 'Coal',
    'B06': 'Oil',
    'B14': 'Nuc'
}

fund = 'AvailCap'
hour = '12'
db = Database()

# Last forecast date fallback if the table does not exist or is empty
default_last_forecast_date = dt.datetime(2019, 1, 1)

# Iterate through files in the output directory
for filename in os.listdir(output_dir):
    if filename.endswith('.parquet'):
        # Extract grid code and forecast date from the filename
        # Assuming the filename pattern is 'av_cap_<grid_code>_YYYYMMDD.parquet'
        match = re.search(r'av_cap_outage_curve_([A-Z0-9-]+)_(\d{8})\.parquet$', filename)
        if match:
            grid_code = match.group(1)
            file_date_str = match.group(2)
            forecast_date = dt.datetime.strptime(file_date_str, '%Y%m%d')

            # Extract grid information from the grid_code
            grid_mapping = {
                # '10YRO-TEL------P': 'ROU'
                '10YHU-MAVIR----U': 'HUN'
                # Add more grid codes and their corresponding grids as needed
            }
            grid = grid_mapping.get(grid_code, None)

            # Skip if the grid_code is not recognized
            if grid is None:
                print(f"Warning: Grid code '{grid_code}' not recognized. Skipping file '{filename}'.")
                continue

            # Query to get the latest forecast_date from the database, if it exists
            try:
                query = f"""
                    SELECT MAX(forecast_date) as last_forecast_date
                    FROM "FUND_{fund}"."{grid}_{hour}"
                """
                last_forecast_date_result = pd.read_sql(query, db.connection_string)

                # Update last_forecast_date only if the result is valid
                if not last_forecast_date_result.empty and pd.notna(last_forecast_date_result['last_forecast_date'].iloc[0]):
                    last_forecast_date = last_forecast_date_result['last_forecast_date'].iloc[0]
                else:
                    last_forecast_date = default_last_forecast_date
            except Exception as e:
                print(f"Warning: Could not retrieve forecast_date from database for grid '{grid}', using default. Error: {e}")
                last_forecast_date = default_last_forecast_date

            # Only process files newer than the last forecast date
            if forecast_date > last_forecast_date:
                # Construct full path to the file
                file_path = os.path.join(output_dir, filename)

                # Load the DataFrame
                df = pd.read_parquet(file_path)

                # Rename columns based on naming_dict
                df.rename(columns=naming_dict, inplace=True)

                # Drop columns not in naming_dict
                df = df[[a for a in list(naming_dict.values()) if a in df.columns]]

                # Update column names to add suffix for Hungarian units
                df.columns = [f'{a}_hu' for a in df.columns]

                # Set forecast_date column
                df['forecast_date'] = forecast_date

                # Set value_date column and reset the index
                df['value_date'] = df.index
                df.reset_index(drop=True, inplace=True)

                # Save to SQL
                df.to_sql(name="stage_" + grid + "_" + hour,
                          schema='FUND_'+fund,
                          con=db.connection_string,
                          if_exists='replace', index=False)
                db.merge_from_staging_to_prod('FUND_'+fund, f"{grid}_{hour}")

print("Loading, renaming, dropping, and SQL operations completed successfully.")
