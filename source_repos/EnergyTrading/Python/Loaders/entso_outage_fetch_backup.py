import xml.etree.ElementTree as ET
import requests
from datetime import datetime, timedelta
import pandas as pd
import re
import pytz
import zipfile
import io
import logging
import time
import json
import pickle
import os

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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

def extract_hourly_data(xml_content, outage_type):
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError:
        logging.error("Error: Received content is not well-formed XML. Skipping this interval.")
        with open("invalid_response.xml", "wb") as f:
            f.write(xml_content)
        return {}, {}

    ns = {'ns': 'urn:iec62325.351:tc57wg16:451-6:outagedocument:3:0'}

    resource_dict = {}
    psr_type_dict = {}
    
    # Extract the root-level mRID (outage identifier)
    try:
        outage_mrid = root.find(".//ns:mRID", ns).text
        created_date_time = pd.to_datetime(root.find(".//ns:createdDateTime", ns).text.replace('Z', '+00:00')).tz_convert('Europe/Berlin').tz_localize(None)
        version = root.find(".//ns:revisionNumber", ns).text
        doc_status = root.find(".//ns:docStatus", ns).text if root.find(".//ns:docStatus", ns) is not None else "active"
    except AttributeError as e:
        logging.error(f"Missing required fields in XML: {e}")
        return {}, {}

    for time_series in root.findall(".//ns:TimeSeries", ns):
        available_period = time_series.find(".//ns:Available_Period", ns)
        if available_period is None:
            continue

        time_interval = available_period.find(".//ns:timeInterval", ns)
        if time_interval is None:
            continue

        start_time_str = time_interval.find(".//ns:start", ns).text
        end_time_str = time_interval.find(".//ns:end", ns).text

        # Find all resolution changes and corresponding datetime values
        resolutions = []
        resolution_change_dates = []
        for res in available_period.findall(".//ns:resolution", ns):
            resolutions.append(res.text)
            # The corresponding date for the resolution change is the start of the period
            change_date_str = start_time_str if len(resolutions) == 1 else res.get("changeDate")
            if change_date_str:
                change_date = pd.to_datetime(change_date_str.replace('Z', '+00:00')).tz_convert('Europe/Berlin').tz_localize(None)
                resolution_change_dates.append(change_date)

        resource_mrid = time_series.find(".//ns:production_RegisteredResource.mRID", ns)
        if resource_mrid is not None:
            resource_mrid = resource_mrid.text

        gen_unit_mrid = time_series.find(".//ns:production_RegisteredResource.pSRType.powerSystemResources.mRID", ns)
        if gen_unit_mrid is not None:
            gen_unit_mrid = gen_unit_mrid.text
        else:
            gen_unit_mrid = resource_mrid

        psr_type = time_series.find(".//ns:production_RegisteredResource.pSRType.psrType", ns)
        if psr_type is not None:
            psr_type = psr_type.text

        start_time = pd.to_datetime(start_time_str.replace('Z', '+00:00')).tz_convert('Europe/Berlin').tz_localize(None)
        end_time = pd.to_datetime(end_time_str.replace('Z', '+00:00')).tz_convert('Europe/Berlin').tz_localize(None)

        data = []
        current_time = start_time
        position = 1
        while current_time < end_time:
            point = available_period.find(f".//ns:Point[ns:position='{position}']", ns)
            if point is not None:
                quantity = float(point.find(".//ns:quantity", ns).text)
                data.append((current_time, quantity))
            current_time += pd.Timedelta(minutes=15)  # Temporary placeholder, actual value will be calculated using resolutions later
            position += 1

        if resource_mrid is not None:
            if resource_mrid not in resource_dict:
                resource_dict[resource_mrid] = {}
            if gen_unit_mrid not in resource_dict[resource_mrid]:
                resource_dict[resource_mrid][gen_unit_mrid] = {}
            if outage_mrid not in resource_dict[resource_mrid][gen_unit_mrid]:
                resource_dict[resource_mrid][gen_unit_mrid][outage_mrid] = {}

            nominal_p = time_series.find(".//ns:production_RegisteredResource.pSRType.powerSystemResources.nominalP", ns)
            nominal_p = float(nominal_p.text) if nominal_p is not None else None

            # Store the data with resolutions and change dates
            resource_dict[resource_mrid][gen_unit_mrid][outage_mrid][created_date_time] = {
                "psr_type": psr_type,
                "data": pd.DataFrame(data, columns=['Timestamp', 'Quantity (MW)']).astype({'Timestamp': 'datetime64[s]'}),
                "start_end": [start_time, end_time],
                "version": version,
                "outage_type": outage_type,
                "resolution": resolutions,
                "resolution_change_dates": [date.tz_localize(None) for date in resolution_change_dates],
                "doc_status": doc_status
            }
            resource_dict[resource_mrid][gen_unit_mrid][outage_mrid][created_date_time]["data"]['Installed (MW)'] = nominal_p
            resource_dict[resource_mrid][gen_unit_mrid][outage_mrid][created_date_time]["data"].set_index('Timestamp', inplace=True)

        if psr_type is not None:
            psr_type_dict.setdefault(psr_type, []).append(resource_mrid)

    return resource_dict, psr_type_dict

def merge_dictionaries(resource_dict, psr_type_dict, all_resource_dict, all_psr_type_dict):
    for resource, gen_units in resource_dict.items():
        if resource not in all_resource_dict:
            all_resource_dict[resource] = {}
        for gen_unit, outages in gen_units.items():
            if gen_unit not in all_resource_dict[resource]:
                all_resource_dict[resource][gen_unit] = {}
            for outage, versions in outages.items():
                if outage not in all_resource_dict[resource][gen_unit]:
                    all_resource_dict[resource][gen_unit][outage] = {}
                for created_date, data in versions.items():
                    all_resource_dict[resource][gen_unit][outage][created_date] = data
    
    for psr, resources in psr_type_dict.items():
        all_psr_type_dict.setdefault(psr, []).extend([r for r in resources if r not in all_psr_type_dict[psr]])



def download_entsoe_outages(start, end, token, bidding_zone, document_type, bsn_type, offset=0):
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
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/xml, application/zip"
    }

    try:
        response = requests.get(base_url, params=params, headers=headers)
        response.raise_for_status()
    except requests.RequestException as e:
        logging.error(f"Request failed: {e}")
        return None, None

    all_resource_dict = {}
    all_psr_type_dict = {}
    if response.headers.get('Content-Type') == 'application/zip':
        logging.info(f"ZIP file received for {start}. Extracting...")
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            for filename in z.namelist():
                with z.open(filename) as xml_file:
                    xml_content = xml_file.read()
                    resource_dict, psr_type_dict = extract_hourly_data(xml_content, "planned" if bsn_type == 'A53' else "unplanned")
                    merge_dictionaries(resource_dict, psr_type_dict, all_resource_dict, all_psr_type_dict)
    elif response.headers.get('Content-Type') == 'application/xml':
        logging.info(f"XML data downloaded successfully for {start}.")
        resource_dict, psr_type_dict = extract_hourly_data(response.content, "planned" if bsn_type == 'A53' else "unplanned")
        merge_dictionaries(resource_dict, psr_type_dict, all_resource_dict, all_psr_type_dict)
    else:
        logging.error(f"Received non-XML response for {start}. Skipping this interval.")
        with open("non_xml_response.html", "wb") as f:
            f.write(response.content)
        return None, None

    return all_resource_dict, all_psr_type_dict



def main():
    API_TOKEN = "0e829f02-4563-482b-8a57-802b1e685c67"
    START_DATE = datetime(2019, 1, 1)
    END_DATE = datetime(2028, 1, 1)
    grids = ["10Y1001A1001A82H"]

    for bidding_zone in grids:
        current_date = START_DATE
        while current_date < END_DATE:
            interval_end = min(current_date + timedelta(weeks=1), END_DATE)

            all_resource_dict = {}
            all_psr_type_dict = {}

            offset = 0
            while True:
                resource_dict, psr_type_dict = download_entsoe_outages(current_date, interval_end, API_TOKEN, bidding_zone, document_type='A80', bsn_type='A53', offset=offset)
                if resource_dict and psr_type_dict:
                    merge_dictionaries(resource_dict, psr_type_dict, all_resource_dict, all_psr_type_dict)
                else:
                    break

                resource_dict, psr_type_dict = download_entsoe_outages(current_date, interval_end, API_TOKEN, bidding_zone, document_type='A80', bsn_type='A54', offset=offset)
                if resource_dict and psr_type_dict:
                    merge_dictionaries(resource_dict, psr_type_dict, all_resource_dict, all_psr_type_dict)
                else:
                    break

                offset += 200
                if offset > 4800:
                    break

            bidding_zone_data = {
                bidding_zone: {
                    "resource_dict": all_resource_dict,
                    "psr_type_dict": all_psr_type_dict
                }
            }
            logging.info(f"Data extraction complete for grid {bidding_zone} and week starting {current_date}. Saving to parquet file.")

            # Save data to a pickle file
            file_path = r'X:\Data\Test_data\entso'
            filename_str =  f"outages_{bidding_zone}_{current_date.strftime('%Y%m%d')}_{interval_end.strftime('%Y%m%d')}.pkl"
            filename = os.path.join(file_path, filename_str)
            with open(filename, 'wb') as pickle_file:
                pickle.dump(bidding_zone_data, pickle_file)

            current_date += timedelta(weeks=1)

if __name__ == "__main__":
    main()
