import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import time
import requests.exceptions
import os

# Replace with your ENTSO-E API key
api_key = '0e829f02-4563-482b-8a57-802b1e685c67'

# API endpoint URL for installed capacity data
url = "https://web-api.tp.entsoe.eu/api"

# Define the date range
start_date = datetime(2019, 1, 1)
end_date = datetime(2026, 1, 2)  # Extended range for demonstration
grids = ["10YCZ-CEPS-----N", "10YSK-SEPS-----K", "10YFR-RTE------C",
             "10Y1001A1001A82H", "10YAT-APG------L", "10YBE----------2",
             "10YHU-MAVIR----U", "10YRO-TEL------P"]

# Initialize a dictionary to store the summed quantities per day per psrType
summary_data = {}

# Iterate over each day in the date range
current_date = start_date
counter = 0
for grid in grids:
    while current_date <= end_date:
        # Format the current date for the API request
        period_start = current_date.strftime("%Y%m%d0000")
        period_end = (current_date + timedelta(days=365)).strftime("%Y%m%d0000")

        # Update the query parameters for the current day
        params = {
            "securityToken": api_key,
            "documentType": "A71",  # Document type for production and generation units
            "processType": "A33",   # Process type for actual values
            # "documentType": "A95",  # Document type for production and generation units
            # "processType": "A39", 
            "in_Domain":grid,  # Example EIC code for the bidding zone (replace with desired country code)
            "periodStart": period_start,  # Start of the period in YYYYMMDDHHMM format
            "periodEnd": period_end, 
            "PsrType": "B05"# End of the period in YYYYMMDDHHMM format
        }

        try:
            # Make the GET request to the API endpoint
            response = requests.get(url, params=params)
            response.raise_for_status()  # Raise an exception for HTTP errors

            # Parse the XML response
            xml_data = response.text
            root = ET.fromstring(xml_data)

            # Define the namespace (needed due to the xmlns attribute in XML response)
            ns = {'ns': 'urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0'}

            # Iterate through each TimeSeries element
            for timeseries in root.findall(".//ns:TimeSeries", ns):
                # Extract the production type (psrType)
                psr_type = timeseries.find("ns:MktPSRType/ns:psrType", ns).text if timeseries.find("ns:MktPSRType/ns:psrType", ns) is not None else "N/A"

                # Extract the quantity
                quantity = timeseries.find(".//ns:Point/ns:quantity", ns).text if timeseries.find(".//ns:Point/ns:quantity", ns) is not None else "0"
                quantity = float(quantity)

                # Add the quantity to the summary data
                if current_date not in summary_data:
                    summary_data[current_date] = {}
                if psr_type not in summary_data[current_date]:
                    summary_data[current_date][psr_type] = 0.0
                summary_data[current_date][psr_type] += quantity

        except requests.exceptions.ConnectionError as e:
            print(f"Connection error for {current_date.strftime('%Y-%m-%d')}: {e}")
            time.sleep(10)  # Wait before retrying
            continue
        except requests.exceptions.HTTPError as e:
            print(f"HTTP error for {current_date.strftime('%Y-%m-%d')}: {e}")
            time.sleep(10)  # Wait before retrying
            continue

        # Move to the next day
        current_date += timedelta(days=1)
        counter += 1

        # Pause after every 50 days
        if counter % 50 == 0:
            time.sleep(30)

        # Pause for 1 second after each request to avoid overwhelming the server
        time.sleep(1)

    # Convert the summary data to a DataFrame
    summary_df = pd.DataFrame.from_dict(summary_data, orient='index').fillna(0)

    # Display the DataFrame
    inst_cap_path = r'C:\data\Data\Spot\Entso\InstCap'
    inst_cap_filepath = os.path.join(inst_cap_path, f"{grid}_inst_cap.parquet")
    summary_data.to_parquet(inst_cap_filepath)