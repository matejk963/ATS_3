import os
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import pickle
import zipfile
import io
import logging
import re  # Import 're' for regex matching

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Dictionary to map docStatus codes to their names
DOCSTATUS = {
    'A01': 'Intermediate',
    'A02': 'Final',
    'A05': 'Active',
    'A09': 'Cancelled',
    'A13': 'Withdrawn',
    'X01': 'Estimated'
}

# Parse resolution strings
def parse_resolution(resolution_str):
    match = re.match(r'PT(\d+)([HMS])', resolution_str)
    if match:
        value, unit = match.groups()
        value = int(value)
        if unit == 'M':
            return timedelta(minutes=value)
        elif unit == 'H':
            return timedelta(hours=value)
        elif unit == 'S':
            return timedelta(seconds=value)
    return None

# Extract outage data from XML content
def extract_hourly_data(xml_content, outage_type):
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError:
        logging.error("Error: Received content is not well-formed XML. Skipping this interval.")
        return {}, []

    ns = {'ns': 'urn:iec62325.351:tc57wg16:451-6:outagedocument:3:0'}

    resource_dict = {}
    mRID_list_for_redownload = []

    # Extract root-level mRID (outage identifier)
    try:
        outage_mrid = root.find(".//ns:mRID", ns).text
        created_date_time = pd.to_datetime(root.find(".//ns:createdDateTime", ns).text.replace('Z', '+00:00')).tz_convert('Europe/Berlin').tz_localize(None)
        version = int(root.find(".//ns:revisionNumber", ns).text)
        logging.info(f"Extracted outage mRID: {outage_mrid}, version: {version}")

        # If version is 2 or more, add this mRID to the list for re-download
        if version >= 2:
            mRID_list_for_redownload.append(outage_mrid)
        
        # Extract docStatus
        doc_status_element = root.find(".//ns:docStatus", ns)
        doc_status_code = None
        if doc_status_element is not None:
            value_element = doc_status_element.find("ns:value", ns)
            if value_element is not None:
                doc_status_code = value_element.text
            else:
                doc_status_code = doc_status_element.text.strip() if doc_status_element.text else "A05"
        else:
            doc_status_code = "A05"
        doc_status = DOCSTATUS.get(doc_status_code, 'Unknown')
    except AttributeError as e:
        logging.error(f"Missing required fields in XML: {e}")
        return {}, []

    # Extract time series information
    for time_series in root.findall(".//ns:TimeSeries", ns):
        available_period = time_series.find(".//ns:Available_Period", ns)
        if available_period is None:
            logging.warning("No Available_Period found in TimeSeries. Skipping this TimeSeries.")
            continue

        time_interval = available_period.find(".//ns:timeInterval", ns)
        if time_interval is None:
            logging.warning("No timeInterval found in Available_Period. Skipping this TimeSeries.")
            continue

        start_time_str = time_interval.find(".//ns:start", ns).text
        end_time_str = time_interval.find(".//ns:end", ns).text
        start_time = pd.to_datetime(start_time_str.replace('Z', '+00:00')).tz_convert('Europe/Berlin').tz_localize(None)
        end_time = pd.to_datetime(end_time_str.replace('Z', '+00:00')).tz_convert('Europe/Berlin').tz_localize(None)

        resource_mrid = time_series.find(".//ns:production_RegisteredResource.mRID", ns)
        resource_mrid = resource_mrid.text if resource_mrid is not None else None

        gen_unit_mrid = time_series.find(".//ns:production_RegisteredResource.pSRType.powerSystemResources.mRID", ns)
        gen_unit_mrid = gen_unit_mrid.text if gen_unit_mrid is not None else resource_mrid

        psr_type = time_series.find(".//ns:production_RegisteredResource.pSRType.psrType", ns)
        psr_type = psr_type.text if psr_type is not None else None

        nominal_p_element = time_series.find(".//ns:production_RegisteredResource.pSRType.powerSystemResources.nominalP", ns)
        nominal_p = float(nominal_p_element.text) if nominal_p_element is not None else None

        if resource_mrid is None:
            logging.warning(f"No resource mRID found in TimeSeries for outage {outage_mrid}. Skipping.")
            continue

        # Extracting data points and associating each point with its datetime
        data_points = []
        current_time = start_time
        for point in available_period.findall(".//ns:Point", ns):
            position = point.find(".//ns:position", ns).text
            quantity = point.find(".//ns:quantity", ns).text
            if position and quantity:
                data_points.append({'Timestamp': current_time, 'Quantity (MW)': float(quantity)})
                # Increment time based on the resolution
                current_time += timedelta(hours=1)  # Default to hourly if no specific resolution is provided

        if not data_points:
            logging.warning(f"No data points found for outage {outage_mrid} in TimeSeries. Skipping.")
            continue

        # Convert data points to DataFrame and set Timestamp as the index
        data_df = pd.DataFrame(data_points)
        data_df.set_index('Timestamp', inplace=True)

        # Add 'Installed (MW)' to the DataFrame
        if nominal_p is not None:
            data_df['Installed (MW)'] = nominal_p
        else:
            logging.warning(f"Missing nominal capacity for resource {resource_mrid}. Skipping addition of installed capacity.")

        # Extract resolutions and corresponding change dates
        resolutions = []
        resolution_change_dates = []

        for res in available_period.findall(".//ns:resolution", ns):
            resolutions.append(res.text)
            # The corresponding change date for the resolution is the start of the period if it's the first resolution
            change_date_str = start_time_str if len(resolutions) == 1 else res.get("changeDate")
            if change_date_str:
                change_date = pd.to_datetime(change_date_str.replace('Z', '+00:00')).tz_convert('Europe/Berlin').tz_localize(None)
                resolution_change_dates.append(change_date)

        # Adding the extracted data to resource_dict
        if resource_mrid not in resource_dict:
            resource_dict[resource_mrid] = {}
        if gen_unit_mrid not in resource_dict[resource_mrid]:
            resource_dict[resource_mrid][gen_unit_mrid] = {}
        if outage_mrid not in resource_dict[resource_mrid][gen_unit_mrid]:
            resource_dict[resource_mrid][gen_unit_mrid][outage_mrid] = {}

        resource_dict[resource_mrid][gen_unit_mrid][outage_mrid][created_date_time] = {
            "psr_type": psr_type,
            "start_end": [start_time, end_time],
            "version": version,
            "outage_type": outage_type,
            "doc_status": doc_status,
            "data": data_df,  # Include data with Timestamp as index and Installed (MW)
            "resolution": resolutions,
            "resolution_change_dates": [date.tz_localize(None) for date in resolution_change_dates],
        }

    return resource_dict, mRID_list_for_redownload




# Merge extracted dictionaries into the overall dataset
def merge_dictionaries(resource_dict, all_resource_dict):
    for resource, gen_units in resource_dict.items():
        if resource not in all_resource_dict:
            all_resource_dict[resource] = gen_units
        else:
            for gen_unit, outages in gen_units.items():
                if gen_unit not in all_resource_dict[resource]:
                    all_resource_dict[resource][gen_unit] = outages
                else:
                    for outage, versions in outages.items():
                        if outage not in all_resource_dict[resource][gen_unit]:
                            all_resource_dict[resource][gen_unit][outage] = versions
                        else:
                            all_resource_dict[resource][gen_unit][outage].update(versions)

# Download outages from ENTSO-E API
def download_entsoe_outages(start, end, token, bidding_zone, document_type, bsn_type, offset=0, mrid=None):
    base_url = "https://web-api.tp.entsoe.eu/api"
    params = {
        "securityToken": token,
        "documentType": document_type,
        "businessType": bsn_type,
        "biddingZone_Domain": bidding_zone,
        "periodStart": start.strftime("%Y%m%d%H%M"),
        "periodEnd": end.strftime("%Y%m%d%H%M"),
        "offset": offset
    }

    if mrid:
        params["mRID"] = mrid

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/xml, application/zip"
    }

    try:
        response = requests.get(base_url, params=params, headers=headers)
        response.raise_for_status()
    except requests.RequestException as e:
        logging.error(f"Request failed: {e}")
        return None, []

    all_resource_dict = {}
    mRID_list_for_redownload = []

    if response.headers.get('Content-Type') == 'application/zip':
        logging.info(f"ZIP file received for {start}. Extracting...")
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            for filename in z.namelist():
                with z.open(filename) as xml_file:
                    xml_content = xml_file.read()
                    resource_dict, mRID_list = extract_hourly_data(xml_content, "planned" if bsn_type == 'A53' else "unplanned")
                    merge_dictionaries(resource_dict, all_resource_dict)
                    mRID_list_for_redownload.extend(mRID_list)

    elif response.headers.get('Content-Type') == 'application/xml':
        logging.info(f"XML data downloaded successfully for {start}.")
        resource_dict, mRID_list = extract_hourly_data(response.content, "planned" if bsn_type == 'A53' else "unplanned")
        merge_dictionaries(resource_dict, all_resource_dict)
        mRID_list_for_redownload.extend(mRID_list)

    return all_resource_dict, mRID_list_for_redownload

# Main function to download outages for given date range and refine those with multiple versions
def main():
    API_TOKEN = "0e829f02-4563-482b-8a57-802b1e685c67"
    START_DATE = datetime(2024,11,20)
    END_DATE = datetime(2028, 1, 1)
    # grids = ["10YRO-TEL------P", "10YHU-MAVIR----U"]
    grids = ["10YCZ-CEPS-----N", "10YSK-SEPS-----K", "10YFR-RTE------C",
             "10Y1001A1001A82H", "10YAT-APG------L", "10YBE----------2",
             "10YHU-MAVIR----U", "10YRO-TEL------P"]

    for bidding_zone in grids:
        current_date = START_DATE
        while current_date < END_DATE:
            interval_end = min(current_date + timedelta(weeks=13), END_DATE)
            all_resource_dict = {}
            mRID_list_for_redownload = []

            offset = 0
            while True:
                # Download both planned (A53) and unplanned (A54) outages
                for bsn_type in ['A53', 'A54']:
                    resource_dict, mRID_list = download_entsoe_outages(
                        current_date, interval_end, API_TOKEN, bidding_zone, document_type='A80', bsn_type=bsn_type, offset=offset
                    )
                    if resource_dict:
                        merge_dictionaries(resource_dict, all_resource_dict)
                    mRID_list_for_redownload.extend(mRID_list)

                # Break if no more results or too many offsets
                if not resource_dict or offset > 4800:
                    break
                offset += 200

            # Redownload outages with version > 1 to gather more details
            for outage_mrid in mRID_list_for_redownload:
                logging.info(f"Redownloading data for mRID {outage_mrid} with multiple versions")
                resource_dict, _ = download_entsoe_outages(
                    current_date, interval_end, API_TOKEN, bidding_zone, document_type='A80', bsn_type='A53', mrid=outage_mrid
                )
                if resource_dict:
                    merge_dictionaries(resource_dict, all_resource_dict)

            # Save data to a pickle file
            filename_str = f"outages_{bidding_zone}_{current_date.strftime('%Y%m%d')}_{interval_end.strftime('%Y%m%d')}.pkl"
            file_path = os.path.join(r'C:\data\Data\Spot\Entso\Outages', filename_str)
            with open(file_path, 'wb') as pickle_file:
                pickle.dump({bidding_zone: {"resource_dict": all_resource_dict}}, pickle_file)

            current_date += timedelta(weeks=1)

if __name__ == "__main__":
    main()
