import sys
import os
import pandas as pd
from Database.DB_reader import Database
import datetime as dt
import re

# Directory containing Parquet files
data_dir = '//192.168.10.91/d/data/Data/Spot/Entso/InstCap'

# Initialize database connection
db = Database()

# Naming dictionary for renaming columns
naming_dict = {
    'B01': 'Bio',
    'B02': 'Lig',
    'B04': 'Gas',
    'B05': 'Coal',
    'B06': 'Oil',
    'B14': 'Nuc',
    'B10': 'Pump'
}

# Grid mapping dictionary
grid_mapping = {
    "10YHU-MAVIR----U": {"column_suffix": "_hu", "table_name": "HUN"},
    "10YCZ-CEPS-----N": {'column_suffix': '_cz', 'table_name': 'CZE'},
    "10YSK-SEPS-----K": {"column_suffix": "_sk", "table_name": "SVK"},
    "10Y1001A1001A82H": {"column_suffix": "_de", "table_name": "DEU"},
    "10YAT-APG------L": {"column_suffix": "_at", "table_name": "AUT"},
    "10YBE----------2": {"column_suffix": "_be", "table_name": "BEL"},
    "10YRO-TEL------P": {"column_suffix": "_ro", "table_name": "ROU"},
    "10YNL----------L": {"column_suffix": "_nl", "table_name": "NLD"},
}

# Grids to omit from processing
omit_grids = ["10Y1001A1001A82H", "10YFR-RTE------C"]

# Hour information
hour = '12'

# Funds to process
funds = ['InstCap', 'LtInstCap']


# Determine forecast date range
def get_fcst_date_range(schema_name, table_name):
    query = f"""
    SELECT MAX(forecast_date) AS last_forecast_date
    FROM "{schema_name}"."{table_name}_12";
    """
    try:
        result = db.execute(query)
        if result.empty or pd.isnull(result.iloc[0]['last_forecast_date']):
            start_date = dt.datetime(2019, 1, 1, 12)
        else:
            last_forecast_date = result.iloc[0]['last_forecast_date']
            start_date = last_forecast_date - dt.timedelta(days=5)
    except Exception as e:
        print(f"Error querying database: {e}")
        start_date = dt.datetime(2019, 1, 1, 12)
    end_date = dt.datetime.today().replace(hour=0, minute=0,
                                    second=0, microsecond=0)
    return pd.date_range(start_date, end_date, freq='12H')

# Iterate over all Parquet files containing "inst_cap" in their names
for file_name in os.listdir(data_dir):
    if re.search(r'inst_cap', file_name, re.IGNORECASE) and file_name.endswith('.parquet'):
        # Extract grid code from the file name
        grid_code_match = re.match(r'(.*)_inst_cap', file_name)
        if not grid_code_match:
            print(f"Could not extract grid code from file: {file_name}")
            continue

        grid_code = grid_code_match.group(1)

        # Skip omitted grids
        if grid_code in omit_grids:
            continue

        # Get grid mapping for the grid code
        if grid_code not in grid_mapping:
            print(f"Grid code {grid_code} not found in grid_mapping. Skipping.")
            continue

        column_suffix = grid_mapping[grid_code]['column_suffix']
        table_name = f"{grid_mapping[grid_code]['table_name']}"

        file_path = os.path.join(data_dir, file_name)

        # Load the installed capacity DataFrame
        inst_cap = pd.read_parquet(file_path)

        # Drop duplicates and ensure last dates are present
        inst_cap = inst_cap.drop_duplicates()
        last_date_list = [dt.datetime(2026, 1, 1), dt.datetime(2027, 1, 1), dt.datetime(2028, 1, 1)]
        for last_date in last_date_list:
            if last_date not in inst_cap.index:
                inst_cap.loc[last_date] = None

        inst_cap = inst_cap.ffill()

        

        # Process each fund
        for fund in funds:
            schema_name = f"FUND_{fund}"
            fcst_date_list = get_fcst_date_range(schema_name, table_name)
            # Process each forecast date
            for forecast_date in fcst_date_list:
                df = inst_cap.copy()

                # Rename columns based on naming_dict
                df.rename(columns=naming_dict, inplace=True)

                # Drop columns not in naming_dict
                df = df[[a for a in naming_dict.values() if a in df.columns]]

                # Update column names to add suffix for the specific grid
                df.columns = [f'{a}{column_suffix}' for a in df.columns]

                df = df.reset_index()
                df = df.rename(columns={'index': 'value_date'})

                # Set forecast_date column
                df['forecast_date'] = forecast_date

                # Save to SQL
                staging_table_name = f"stage_{table_name}_{hour}"
                schema_name = f"FUND_{fund}"
                df.to_sql(
                    name=staging_table_name,
                    schema=schema_name,
                    con=db.connection_string,
                    if_exists='replace',
                    index=False
                )
                try:
                    db.merge_from_staging_to_prod(schema_name, f"{table_name}_{hour}")
                except:
                    print(f"Error merging {staging_table_name} to production table.")
