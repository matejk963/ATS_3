import os
import pandas as pd
import numpy as np
import datetime as dt
import re

# Paths and constants
inst_cap_path = r'C:\data\Data\Spot\Entso\InstCap\10YHU-MAVIR----U_inst_cap.parquet'
test_outage_dir = r'C:\data\Data\Spot\Entso\Outages\Curves'
output_dir = r'C:\data\Data\Spot\Entso\Outages\AvCap'
file_filter = 'outage_curve_10YHU-MAVIR----U'

# Load the installed capacity DataFrame
inst_cap = pd.read_parquet(inst_cap_path)

# Ensure last_date is present and resample as needed
last_date = dt.datetime(2026, 1, 1)
if last_date not in inst_cap.index:
    inst_cap.loc[last_date] = None
    inst_cap = inst_cap.resample('h').ffill().dropna()

# Iterate through files in the specified directory
for filename in os.listdir(test_outage_dir):
    if file_filter in filename and filename.endswith('.parquet'):
        # Extract the date from the filename (assumed format 'outage_curve_10YHU-MAVIR----U_YYYYMMDD.parquet')
        match = re.search(r'_(\d{8})\.parquet$', filename)
        if match:
            file_date_str = match.group(1)
            file_date = dt.datetime.strptime(file_date_str, '%Y%m%d')

            # Construct full path to the file
            file_path = os.path.join(test_outage_dir, filename)

            # Load the outage data
            test_outage = pd.read_parquet(file_path).reset_index()

            # Make sure the columns are as expected
            if {'PsrType', 'Timestamp', 'Outage (MW)'}.issubset(test_outage.columns):
                # Convert Timestamp to datetime
                test_outage['Timestamp'] = pd.to_datetime(test_outage['Timestamp'])

                # Filter out dates above the date in the filename
                test_outage = test_outage[test_outage['Timestamp'] >= file_date]

                # Pivot the DataFrame
                test_outage_pivot = test_outage.pivot(index='Timestamp', columns='PsrType', values='Outage (MW)').fillna(0)

                # Align the index of test_outage_pivot with inst_cap
                test_outage_pivot = test_outage_pivot.reindex(inst_cap.index, fill_value=0)

                # Subtract the test_outage DataFrame from the inst_cap DataFrame
                result = inst_cap.subtract(test_outage_pivot, fill_value=0)
                # Drop duplicate rows (excluding the index)
                result_reset = result.copy()
                result = result_reset.drop_duplicates(keep='first')

                # Create output file path
                output_file_path = os.path.join(output_dir, f"av_cap_{filename}")

                # Save the result as a parquet file
                result.to_parquet(output_file_path)

print("Subtraction and saving process completed successfully.")