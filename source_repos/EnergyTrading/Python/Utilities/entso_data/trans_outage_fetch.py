import os
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import pickle
import zipfile
import io
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Grid codes and neighbors mapping
COUNTRY_TO_GRID = {
    "BE": "10YBE----------2",
    "FR": "10YFR-RTE------C",
    "DE": {
        "DE": "10Y1001A1001A82H",
        "Amprion": "10YDE-VE-------2",
        "TransnetBW": "10YDE-ENBW-----N",
        "50Hertz": "10YDE-EON------1",
        "TenneT": "10YDE-TENNET---Z"        
    },
    "NL": "10YNL----------L",
    "CZ": "10YCZ-CEPS-----N",
    "SK": "10YSK-SEPS-----K",
    "HU": "10YHU-MAVIR----U",
    "RO": "10YRO-TEL------P",
    "HR": "10YHR-HEP------M",
    "SI": "10YSI-ELES-----O",
    "CH": "10YCH-SWISSGRIDZ",
    "IT": {
        "IT_North": "10YIT-GRTN-----B",
        "IT_South": "10Y1001A1001A83F",
        "IT_Sicily": "10Y1001A1001A893",
        "IT_Sardinia": "10Y1001A1001A82H"
    },
    "ES": "10YES-REE------0",
    "AT": "10YAT-APG------L"
}

NEIGHBORS = {
    "BE": ["FR", "NL", "DE"],
    # "FR": ["BE", "ES", "DE", "IT_North"],
    "FR": ["DE"],
    "DE": ["FR", "BE", "NL", "CZ", "CH", "AT"],
    "NL": ["BE", "DE"],
    "CZ": ["DE", "SK", "AT"],
    "SK": ["CZ", "HU", "AT"],
    "HU": ["SK", "RO", "HR", "SI"],
    "RO": ["HU", "BG"],
    "HR": ["HU", "SI"],
    "SI": ["HR", "IT_North", "AT"],
    "CH": ["FR", "DE", "IT_North"],
    "IT": {
        "IT_North": ["FR", "CH", "SI"],
        "IT_South": [],
        "IT_Sicily": [],
        "IT_Sardinia": []
    },
    "ES": ["FR", "PT"],
    "AT": ["DE", "CZ", "SK", "SI"],
}

class EntsoeTransmissionUnavailabilityFetcher:
    def __init__(self, api_token, output_dir):
        self.api_token = api_token
        self.output_dir = output_dir
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

    def parse_transmission_unavailability(self, xml_content, base_params):
        """
        Parse the XML content for transmission unavailability, fetching and merging additional versions.
        """
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError:
            logging.error("Error: Received content is not well-formed XML. Skipping this message.")
            return {}

        ns = {'ns': 'urn:iec62325.351:tc57wg16:451-6:outagedocument:3:0'}
        results = {}

        try:
            outage_mrid = root.find(".//ns:mRID", ns).text
            revision_numbers = [int(rev.text) for rev in root.findall(".//ns:revisionNumber", ns)]
            revision_numbers.sort()

            created_datetime = root.find(".//ns:createdDateTime", ns)
            created_datetime = (
                pd.to_datetime(created_datetime.text.replace('Z', '+00:00')).tz_convert('Europe/Berlin').tz_localize(None)
                if created_datetime is not None else None
            )

            for revision_number in revision_numbers:
                time_series = root.find(".//ns:TimeSeries", ns)
                if not time_series:
                    continue  # Skip if no TimeSeries is found

                # Extract start from the first element and end from the last element
                available_periods = time_series.findall(".//ns:Available_Period/ns:timeInterval", ns)
                if not available_periods:
                    continue  # Skip if no time intervals are found

                first_start = pd.to_datetime(
                    available_periods[0].find("ns:start", ns).text.replace('Z', '+00:00')
                ).tz_convert('Europe/Berlin').tz_localize(None)

                last_end = pd.to_datetime(
                    available_periods[-1].find("ns:end", ns).text.replace('Z', '+00:00')
                ).tz_convert('Europe/Berlin').tz_localize(None)

                # Assuming asset_mRID and domain identifiers are consistent across the revision
                asset = time_series.find(".//ns:Asset_RegisteredResource", ns)
                if asset is None:
                    logging.info("No Asset_RegisteredResource found; skipping this message.")
                    continue

                asset_mrid = asset.find("ns:mRID", ns).text
                in_domain = time_series.find(".//ns:in_Domain.mRID", ns).text
                out_domain = time_series.find(".//ns:out_Domain.mRID", ns).text
                curve_type = time_series.find(".//ns:curveType", ns).text

                # Add the data to results
                if (in_domain, out_domain) not in results:
                    results[(in_domain, out_domain)] = {}

                if outage_mrid not in results[(in_domain, out_domain)]:
                    results[(in_domain, out_domain)][outage_mrid] = {}

                # Keep all revisions
                if revision_number not in results[(in_domain, out_domain)][outage_mrid]:
                    results[(in_domain, out_domain)][outage_mrid][revision_number] = {}

                # Save aggregated start and end for this revision
                results[(in_domain, out_domain)][outage_mrid][revision_number][asset_mrid] = {
                    "start": first_start,
                    "end": last_end,
                    "curveType": curve_type,
                    "createdDateTime": created_datetime,
                }

            # Fetch and merge additional versions
            additional_versions = self.fetch_additional_versions(outage_mrid, base_params)
            for (in_domain, out_domain), outages in additional_versions.items():
                if (in_domain, out_domain) not in results:
                    results[(in_domain, out_domain)] = outages
                else:
                    for additional_outage_mrid, revisions in outages.items():
                        if additional_outage_mrid not in results[(in_domain, out_domain)]:
                            results[(in_domain, out_domain)][additional_outage_mrid] = revisions
                        else:
                            for revision_number, revision_data in revisions.items():
                                if revision_number not in results[(in_domain, out_domain)][additional_outage_mrid]:
                                    results[(in_domain, out_domain)][additional_outage_mrid][revision_number] = revision_data
                                else:
                                    # Merge assets into the existing revision
                                    for asset_mrid, asset_data in revision_data.items():
                                        if asset_mrid not in results[(in_domain, out_domain)][additional_outage_mrid][revision_number]:
                                            results[(in_domain, out_domain)][additional_outage_mrid][revision_number][asset_mrid] = asset_data
                                        else:
                                            # Update createdDateTime if different
                                            existing_datetime = results[(in_domain, out_domain)][additional_outage_mrid][revision_number][asset_mrid].get("createdDateTime")
                                            new_datetime = asset_data.get("createdDateTime")
                                            if existing_datetime != new_datetime:
                                                results[(in_domain, out_domain)][additional_outage_mrid][revision_number][asset_mrid]["createdDateTime"] = new_datetime

        except AttributeError as e:
            logging.error(f"Missing required fields in XML: {e}")

        return results


    
    def fetch_additional_versions(self, outage_mrid, base_params):
        """
        Fetch additional versions of the given outage mRID using original parameters.
        Handles both XML and ZIP responses without cyclic calls.
        """
        # Clone the original parameters and add the outage mRID
        params = base_params.copy()
        params["mRID"] = outage_mrid

        base_url = "https://web-api.tp.entsoe.eu/api"
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/xml, application/zip"}

        try:
            response = requests.get(base_url, params=params, headers=headers)
            response.raise_for_status()

            all_versions = {}
            content_type = response.headers.get('Content-Type')

            # Handle XML response
            if content_type == 'application/xml':
                xml_content = response.content.decode('utf-8')
                parsed_data = self._parse_xml_content(xml_content)  # Directly parse the XML
                all_versions.update(parsed_data)

            # Handle ZIP response
            elif content_type == 'application/zip':
                with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                    for filename in z.namelist():
                        with z.open(filename) as xml_file:
                            xml_content = xml_file.read()
                            parsed_data = self._parse_xml_content(xml_content)  # Parse each XML file
                            # Merge parsed data into all_versions
                            for key, value in parsed_data.items():
                                if key not in all_versions:
                                    all_versions[key] = value
                                else:
                                    # Merge outages and their versions
                                    for outage_key, outage_value in value.items():
                                        if outage_key not in all_versions[key]:
                                            all_versions[key][outage_key] = outage_value
                                        else:
                                            # Merge revisions
                                            all_versions[key][outage_key].update(outage_value)

            return all_versions

        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching additional versions for {outage_mrid}: {e}")
            return {}
        
    def _parse_xml_content(self, xml_content):
        """
        Parse the XML content and return the extracted data grouped by (in_domain, out_domain),
        with start from the first TimeSeries and end from the last TimeSeries for each revision and asset.
        """
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError:
            logging.error("Error: Received content is not well-formed XML. Skipping this message.")
            return {}

        ns = {'ns': 'urn:iec62325.351:tc57wg16:451-6:outagedocument:3:0'}
        results = {}

        try:
            outage_mrid = root.find(".//ns:mRID", ns).text
            revision_numbers = [int(rev.text) for rev in root.findall(".//ns:revisionNumber", ns)]
            revision_numbers.sort()

            created_datetime = root.find(".//ns:createdDateTime", ns)
            created_datetime = (
                pd.to_datetime(created_datetime.text.replace('Z', '+00:00')).tz_convert('Europe/Berlin').tz_localize(None)
                if created_datetime is not None else None
            )

            for revision_number in revision_numbers:
                time_series = root.find(".//ns:TimeSeries", ns)
                if not time_series:
                    continue  # Skip if no TimeSeries is found

                # Get start from the first element and end from the last element
                
                first_series = time_series.findall(".//ns:Available_Period/ns:timeInterval", ns)[0]
                last_series = time_series.findall(".//ns:Available_Period/ns:timeInterval", ns)[-1]

                first_start = pd.to_datetime(
                    first_series.find(".//ns:start", ns).text.replace('Z', '+00:00')
                ).tz_convert('Europe/Berlin').tz_localize(None)

                last_end = pd.to_datetime(
                    last_series.find(".//ns:end", ns).text.replace('Z', '+00:00')
                ).tz_convert('Europe/Berlin').tz_localize(None)

                # Assuming asset_mRID and domain identifiers are consistent across the revision
                asset = time_series.find(".//ns:Asset_RegisteredResource", ns)
                if asset is None:
                    logging.info("No Asset_RegisteredResource found; skipping this message.")
                    continue

                asset_mrid = asset.find("ns:mRID", ns).text
                in_domain = time_series.find(".//ns:in_Domain.mRID", ns).text
                out_domain = time_series.find(".//ns:out_Domain.mRID", ns).text
                curve_type = time_series.find(".//ns:curveType", ns).text

                # Add the data to results
                if (in_domain, out_domain) not in results:
                    results[(in_domain, out_domain)] = {}

                if outage_mrid not in results[(in_domain, out_domain)]:
                    results[(in_domain, out_domain)][outage_mrid] = {}

                # Keep all revisions
                if revision_number not in results[(in_domain, out_domain)][outage_mrid]:
                    results[(in_domain, out_domain)][outage_mrid][revision_number] = {}

                # Save aggregated start and end for this revision
                results[(in_domain, out_domain)][outage_mrid][revision_number][asset_mrid] = {
                    "start": first_start,
                    "end": last_end,
                    "curveType": curve_type,
                    "createdDateTime": created_datetime,
                }

        except AttributeError as e:
            logging.error(f"Missing required fields in XML: {e}")

        return results


        
    def validate_grid_pair(self, in_domain, out_domain):
        """
        Validate if the grid pair has data available.
        """
        base_url = "https://web-api.tp.entsoe.eu/api"
        params = {
            "securityToken": self.api_token,
            "documentType": "A78",
            "in_Domain": in_domain,
            "out_Domain": out_domain,
            "periodStart": "202101010000",
            "periodEnd": "202101020000"
        }
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/xml"}
        try:
            response = requests.get(base_url, params=params, headers=headers)
            if response.status_code == 400:
                logging.warning(f"Grid pair {in_domain} -> {out_domain} is invalid. Skipping.")
                return False
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logging.error(f"Error validating grid pair {in_domain} -> {out_domain}: {e}")
            return False

    def fetch_transmission_unavailability(self, country, start_date=None, end_date=None):
        if country not in COUNTRY_TO_GRID or country not in NEIGHBORS:
            logging.error(f"Invalid country: {country}")
            return

        grids = COUNTRY_TO_GRID[country]
        if not isinstance(grids, dict):
            grids = {country: grids}

        processed_pairs = set()

        for grid_name, grid_code in grids.items():
            neighbors = NEIGHBORS.get(country, [])
            for neighbor in neighbors:
                neighbor_grids = COUNTRY_TO_GRID.get(neighbor, neighbor)
                if not isinstance(neighbor_grids, dict):
                    neighbor_grids = {neighbor: neighbor_grids}

                for neighbor_grid_name, neighbor_grid_code in neighbor_grids.items():
                    pair = tuple(sorted((grid_code, neighbor_grid_code)))
                    if pair in processed_pairs:
                        continue

                    if not self.validate_grid_pair(grid_code, neighbor_grid_code):
                        continue  # Skip invalid grid pairs

                    processed_pairs.add(pair)

                    if not start_date:
                        start_date = datetime(2018, 1, 1)
                    if not end_date:
                        end_date = pd.to_datetime(datetime.now().date())
                        end_date = datetime(2028, 12, 31)
                    current_date = start_date
                    max_increment = timedelta(weeks=52)
                    min_increment = timedelta(days=1)
                    increment = max_increment

                    while current_date < end_date:
                        interval_end = min(current_date + increment, end_date)
                        logging.info(f"Fetching data from {current_date} to {interval_end} for {grid_code} -> {neighbor_grid_code}.")

                        results, success = self.download_entsoe_transmission(
                            start=current_date, end=interval_end, in_domain=grid_code, out_domain=neighbor_grid_code, document_type='A78'
                        )

                        # Handle "No data available" case
                        if "no_data" in results:
                            logging.info(f"No data available for {grid_code} -> {neighbor_grid_code}. Skipping this grid pair.")
                            break  # Exit the loop for this neighbor grid

                        if success and results:
                            logging.info(f"Data successfully fetched for {current_date} to {interval_end}.")
                            filename = f"transmission_{grid_code}_{neighbor_grid_code}_{current_date.strftime('%Y%m%d')}_{interval_end.strftime('%Y%m%d')}.pkl"
                            file_path = os.path.join(self.output_dir, filename)
                            with open(file_path, 'wb') as pickle_file:
                                pickle.dump({(grid_code, neighbor_grid_code): results}, pickle_file)

                        # Adjust increment on failure
                        increment = max(increment / 2, min_increment) if not success else max_increment
                        current_date = interval_end
                        
    def download_entsoe_transmission(self, start, end, in_domain, out_domain, document_type, offset=0, outage_mrid=None):
        """
        Download data from ENTSO-E API and parse it.
        """
        base_url = "https://web-api.tp.entsoe.eu/api"
        params = {
            "securityToken": self.api_token,
            "documentType": document_type,
            "in_Domain": in_domain,
            "out_Domain": out_domain,
            "periodStart": start.strftime("%Y%m%d%H%M"),
            "periodEnd": end.strftime("%Y%m%d%H%M"),
            "offset": offset
        }

        if outage_mrid:
            params["mRID"] = outage_mrid

        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/xml, application/zip"}

        try:
            response = requests.get(base_url, params=params, headers=headers)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching data for {in_domain} -> {out_domain}: {e}")
            return {}, False

        # Handle "No data available" case
        if response.headers.get('Content-Type') == 'application/xml':
            xml_content = response.content.decode('utf-8')
            if "<Reason>" in xml_content and "<code>999</code>" in xml_content:
                logging.info(f"No data available for {in_domain} -> {out_domain} from {start} to {end}. Skipping.")
                return {"no_data": True}, False  # Return a flag for no data

        # Handle actual data response
        all_results = {}
        if response.headers.get('Content-Type') == 'application/zip':
            # Process ZIP file
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                for filename in z.namelist():
                    with z.open(filename) as xml_file:
                        xml_content = xml_file.read()
                        parsed_data = self.parse_transmission_unavailability(xml_content, params)
                        for key, value in parsed_data.items():
                            if key in all_results:
                                for outage_mrid, versions in value.items():
                                    if outage_mrid not in all_results[key]:
                                        all_results[key][outage_mrid] = versions
                                    else:
                                        all_results[key][outage_mrid].update(versions)
                            else:
                                all_results[key] = value
        elif response.headers.get('Content-Type') == 'application/xml':
            # Process single XML file
            xml_content = response.content
            parsed_data = self.parse_transmission_unavailability(xml_content)
            for key, value in parsed_data.items():
                if key in all_results:
                    for outage_mrid, versions in value.items():
                        if outage_mrid not in all_results[key]:
                            all_results[key][outage_mrid] = versions
                        else:
                            all_results[key][outage_mrid].update(versions)
                else:
                    all_results[key] = value

        return all_results, True





def main():
    api_token = "0e829f02-4563-482b-8a57-802b1e685c67"
    output_dir = r"W:\Data\Spot\Entso\Transmission"
    fetcher = EntsoeTransmissionUnavailabilityFetcher(api_token, output_dir)
    countries = ["DE", "FR", "BE", "NL", "CZ", "SK", "HU", "RO", "HR", "SI", "IT", "ES", "AT", "CH"]
    countries = ["FR", "DE", "HU"]
    for country in countries:
        fetcher.fetch_transmission_unavailability(country)

if __name__ == "__main__":
    main()