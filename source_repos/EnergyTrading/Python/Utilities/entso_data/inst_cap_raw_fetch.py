import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import os
import time

# Replace with your ENTSO-E API key
api_key = '0e829f02-4563-482b-8a57-802b1e685c67'

# API endpoint URL for installed capacity data
url = "https://web-api.tp.entsoe.eu/api"

# Define the date range
start_date = datetime(2019, 1, 1)
end_date = datetime(2026, 1, 2)

grids = [
    "10YCZ-CEPS-----N", "10YSK-SEPS-----K", "10YFR-RTE------C",
    "10Y1001A1001A82H", "10YAT-APG------L", "10YBE----------2",
    "10YHU-MAVIR----U", "10YRO-TEL------P", "10YHR-HEP------M",
    "10YSI-ELES-----O", "10YCH-SWISSGRIDZ", "10YIT-GRTN-----B",
    "10YES-REE------0"
]

# Directory to save data
inst_cap_path = r'C:\data\Data\Spot\Entso\InstCap'
os.makedirs(inst_cap_path, exist_ok=True)

# Get today’s date
current_day = datetime.now()

# Main data retrieval loop
for grid in grids:
    inst_cap_filepath = os.path.join(inst_cap_path, f"{grid}_inst_cap.parquet")
    
    # Check if file exists
    if os.path.exists(inst_cap_filepath):
        print(f"File exists for grid {grid}. Checking for updates...")
        
        # Load existing data and get the last date
        existing_data = pd.read_parquet(inst_cap_filepath)
        existing_data.index = pd.to_datetime(existing_data.index)
        last_date = existing_data.index.max()

        if last_date > current_day:
            # If last date is after today, go from 7 days before today to end date
            start_date = current_day - timedelta(days=7)
            print(f"Last date {last_date} is after today. Fetching data from {start_date} to {end_date}.")
        else:
            # If last date is not after today, go from last date to end date
            start_date = last_date + timedelta(days=1)
            print(f"Last date {last_date} is not after today. Fetching data from {start_date} to {end_date}.")
    else:
        print(f"No file found for grid {grid}. Fetching data from {start_date} to {end_date}.")

    # Initialize a dictionary to store the summed quantities per day per psrType
    summary_data = {}

    # Fetch data day by day
    current_date = start_date
    while current_date <= end_date:
        period_start = current_date.strftime("%Y%m%d0000")
        period_end = (current_date + timedelta(days=1)).strftime("%Y%m%d0000")

        params = {
            "securityToken": api_key,
            "documentType": "A71",
            "processType": "A33",
            "in_Domain": grid,
            "periodStart": period_start,
            "periodEnd": period_end
        }

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()

            root = ET.fromstring(response.text)
            ns = {'ns': 'urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0'}

            for timeseries in root.findall(".//ns:TimeSeries", ns):
                psr_type = timeseries.find("ns:MktPSRType/ns:psrType", ns).text or "N/A"
                quantity = float(timeseries.find(".//ns:Point/ns:quantity", ns).text or "0")
                summary_data.setdefault(current_date, {}).setdefault(psr_type, 0.0)
                summary_data[current_date][psr_type] += quantity

        except requests.exceptions.RequestException as e:
            print(f"Error on {current_date.strftime('%Y-%m-%d')} for grid {grid}: {e}")
            time.sleep(10)
            continue

        current_date += timedelta(days=1)
        time.sleep(1)  # Avoid overwhelming the server

    # Save or update the data
    new_data_df = pd.DataFrame.from_dict(summary_data, orient='index').fillna(0)

    if os.path.exists(inst_cap_filepath):
        updated_data = pd.concat([existing_data, new_data_df]).sort_index().drop_duplicates()
        updated_data.to_parquet(inst_cap_filepath)
        print(f"Updated file for grid {grid} saved successfully.")
    else:
        new_data_df.to_parquet(inst_cap_filepath)
        print(f"New file for grid {grid} saved successfully.")
