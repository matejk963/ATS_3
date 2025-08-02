import os
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import pickle
import zipfile
import io
import logging
import re

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

class EntsoeOutagesFetcher:
    def __init__(self, api_token, output_dir):
        self.api_token = api_token
        self.output_dir = output_dir
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

    def parse_resolution(self, resolution_str):
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

    def extract_hourly_data(self, xml_content, outage_type):
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError:
            logging.error("Error: Received content is not well-formed XML. Skipping this interval.")
            return {}, []

        ns = {'ns': 'urn:iec62325.351:tc57wg16:451-6:outagedocument:3:0'}

        resource_dict = {}
        mRID_list_for_redownload = []
        
        try:
            outage_mrid = root.find(".//ns:mRID", ns).text
            created_date_time = pd.to_datetime(root.find(".//ns:createdDateTime", ns).text.replace('Z', '+00:00')).tz_convert('Europe/Berlin').tz_localize(None)
            version = int(root.find(".//ns:revisionNumber", ns).text)

            if version >= 2:
                mRID_list_for_redownload.append(outage_mrid)

            doc_status_element = root.find(".//ns:docStatus", ns)
            doc_status_code = doc_status_element.find("ns:value", ns).text if doc_status_element is not None else "A05"
            doc_status = DOCSTATUS.get(doc_status_code, 'Unknown')
        except AttributeError as e:
            logging.error(f"Missing required fields in XML: {e}")
            return {}, []

        for time_series in root.findall(".//ns:TimeSeries", ns):
            available_period = time_series.find(".//ns:Available_Period", ns)
            if not available_period:
                continue

            time_interval = available_period.find(".//ns:timeInterval", ns)
            start_time = pd.to_datetime(time_interval.find(".//ns:start", ns).text.replace('Z', '+00:00')).tz_convert('Europe/Berlin').tz_localize(None)
            end_time = pd.to_datetime(time_interval.find(".//ns:end", ns).text.replace('Z', '+00:00')).tz_convert('Europe/Berlin').tz_localize(None)

            resource_mrid = time_series.find(".//ns:production_RegisteredResource.mRID", ns)
            resource_mrid = resource_mrid.text if resource_mrid is not None else None

            gen_resource_mrid = time_series.find(".//ns:production_RegisteredResource.pSRType.powerSystemResources.mRID", ns)
            gen_resource_mrid = gen_resource_mrid.text if resource_mrid is not None else None

            if gen_resource_mrid is None:
                break
            
            resource_psr_type = time_series.find(".//ns:production_RegisteredResource.pSRType.psrType", ns)
            resource_psr_type = resource_psr_type.text if resource_psr_type is not None else None
            
            nominal_p_element = time_series.find(".//ns:production_RegisteredResource.pSRType.powerSystemResources.nominalP", ns)
            nominal_p = float(nominal_p_element.text) if nominal_p_element is not None else None

            data_points = []
            current_time = start_time
            for point in available_period.findall(".//ns:Point", ns):
                quantity = point.find(".//ns:quantity", ns).text
                if quantity:
                    data_points.append({'Timestamp': current_time, 'Quantity (MW)': float(quantity)})
                    current_time += timedelta(hours=1)

            if not data_points:
                continue

            data_df = pd.DataFrame(data_points)
            data_df.set_index('Timestamp', inplace=True)
            if nominal_p is not None:
                data_df['Installed (MW)'] = nominal_p

            if resource_mrid not in resource_dict:
                resource_dict[resource_mrid] = {}
            created_datetime = created_date_time  # Ensure `created_date_time` is captured
            resource_dict.setdefault(resource_mrid, {}).setdefault(gen_resource_mrid, {}).setdefault(outage_mrid, {})[created_datetime] = {
                "start_end": [start_time, end_time],
                "version": version,
                "outage_type": outage_type,
                "psr_type": resource_psr_type,
                "doc_status": doc_status,
                "data": data_df
            }

        return resource_dict, mRID_list_for_redownload

    def merge_dictionaries(self, resource_dict, all_resource_dict):
        for resource, gen_units in resource_dict.items():
            if resource not in all_resource_dict:
                all_resource_dict[resource] = gen_units
            else:
                for gen_unit, outages in gen_units.items():
                    if gen_unit not in all_resource_dict[resource]:
                        all_resource_dict[resource][gen_unit] = outages
                    else:
                        for outage, details in outages.items():
                            if outage not in all_resource_dict[resource][gen_unit]:
                                all_resource_dict[resource][gen_unit][outage] = details
                            else:
                                all_resource_dict[resource][gen_unit][outage].update(details)

    def download_entsoe_outages(self, start, end, bidding_zone, document_type, bsn_type, offset=0, mrid=None):
        base_url = "https://web-api.tp.entsoe.eu/api"
        params = {
            "securityToken": self.api_token,
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
        except requests.exceptions.RequestException as e:
            if "too many messages" in str(e).lower():
                logging.warning("Too many messages in the request. Adjusting the period.")
                return None, None, False
            logging.error(f"An HTTP error occurred: {e}")
            # Handle the 400 error or log it as needed
            return None, None, False  # Or handle it differently

        all_resource_dict = {}
        mRID_list_for_redownload = []

        if response.headers.get('Content-Type') == 'application/zip':
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                for filename in z.namelist():
                    with z.open(filename) as xml_file:
                        xml_content = xml_file.read()
                        # Debug lines start
                        namespace = {'ns': 'urn:iec62325.351:tc57wg16:451-6:outagedocument:3:0'}  # Define namespace
                        root = ET.fromstring(xml_content)

                        # Extract mRID from the root document
                        mRID_value = root.find('ns:mRID', namespace).text
                        if mRID_value in ['qQngIsYRi1HWjVmV6SbtLw']:
                            print("mRID:", mRID_value)
                            # Debug lines end
                        resource_dict, mRID_list = self.extract_hourly_data(xml_content, "planned" if bsn_type == 'A53' else "unplanned")
                        self.merge_dictionaries(resource_dict, all_resource_dict)
                        mRID_list_for_redownload.extend(mRID_list)
        elif response.headers.get('Content-Type') == 'application/xml':
            resource_dict, mRID_list = self.extract_hourly_data(response.content, "planned" if bsn_type == 'A53' else "unplanned")
            self.merge_dictionaries(resource_dict, all_resource_dict)
            mRID_list_for_redownload.extend(mRID_list)

        return all_resource_dict, mRID_list_for_redownload, True

    def fetch_outages(self, grid, start_date, end_date):
        current_date = start_date
        increment = timedelta(weeks=52)

        while current_date < end_date:
            interval_end = min(current_date + increment, end_date)

            while True:
                resource_dict, mRID_list, success = self.download_entsoe_outages(
                    start=current_date, end=interval_end, bidding_zone=grid, document_type='A80', bsn_type='A53'
                )

                if success:
                    break
                increment /= 2
                interval_end = min(current_date + increment, end_date)

            all_resource_dict = {}
            mRID_list_for_redownload = []

            # **Fix: Reset offset for each new period**
            offset = 0  
                        
            for bsn_type in ['A53', 'A54']:
                while True:
                    resource_dict, mRID_list, success = self.download_entsoe_outages(
                        start=current_date, end=interval_end, bidding_zone=grid,
                        document_type='A80', bsn_type=bsn_type, offset=offset
                    )
                    if resource_dict:
                        if '15WMATRA-----PPK' in resource_dict:
                            if '15WMATRAG3---STO' in resource_dict['15WMATRA-----PPK']:
                                if 'qQngIsYRi1HWjVmV6SbtLw' in resource_dict['15WMATRA-----PPK']['15WMATRAG3---STO']:
                                    print('debug 223')
                        self.merge_dictionaries(resource_dict, all_resource_dict)
                    mRID_list_for_redownload.extend(mRID_list)

                    # **Stop iteration if no more data or offset exceeds limit**
                    if not resource_dict or offset > 4800:
                        break
                    offset += 200

            # **Handle redownload cases for missing mRID outages with offsets**
            for outage_mrid in mRID_list_for_redownload:
                offset = 0  # Reset offset for each outage_mrid
                while True:
                    if outage_mrid == 'I76eatNnmn0eQS2WmQJkLg':
                        print('debug 234')
                    resource_dict, _, success = self.download_entsoe_outages(
                        start=current_date, end=interval_end, bidding_zone=grid,
                        document_type='A80', bsn_type='A53', mrid=outage_mrid, offset=offset
                    )
                    
                    if resource_dict:
                        self.merge_dictionaries(resource_dict, all_resource_dict)

                    # **Stop redownloading when no more data or offset limit reached**
                    if not resource_dict or offset > 4800:
                        break
                    offset += 200

            # **Save complete outage data for the current period**
            filename = f"outages_{grid}_{current_date.strftime('%Y%m%d')}_{interval_end.strftime('%Y%m%d')}.pkl"
            file_path = os.path.join(self.output_dir, filename)
            with open(file_path, 'wb') as pickle_file:
                pickle.dump({grid: {"resource_dict": all_resource_dict}}, pickle_file)

            # Move to the next period and reset increment
            current_date = interval_end
            increment = timedelta(weeks=52)
            offset = 0  # Reset offset for the next period



if __name__ == "__main__":
    api_token = "0e829f02-4563-482b-8a57-802b1e685c67"
    output_dir = '//192.168.10.91/d/data/Data/Spot/Entso/Outages'
    grid = "10YHU-MAVIR----U"
    start_date = datetime(2024, 1, 21)
    end_date = datetime(2025, 1, 19)

    fetcher = EntsoeOutagesFetcher(api_token, output_dir)
    fetcher.fetch_outages(grid, start_date, end_date)
