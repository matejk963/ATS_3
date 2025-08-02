# -*- coding: utf-8 -*-
"""
Created on Fri Oct 27 07:51:42 2023

@author: krajcovic
"""

import requests
import pandas as pd
from xml.etree import ElementTree
from datetime import datetime, timedelta
import pytz

class ENTSOEData:
    BASE_URL = "https://web-api.tp.entsoe.eu/api?"
    NAMESPACE = {'ns': 'urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0'}
    
    PSRTYPE_MAPPINGS = {
        'A03': 'Mixed',
        'A04': 'Generation',
        'A05': 'Load',
        'B01': 'Biomass',
        'B02': 'Fossil Brown coal/Lignite',
        'B03': 'Fossil Coal-derived gas',
        'B04': 'Fossil Gas',
        'B05': 'Fossil Hard coal',
        'B06': 'Fossil Oil',
        'B07': 'Fossil Oil shale',
        'B08': 'Fossil Peat',
        'B09': 'Geothermal',
        'B10': 'Hydro Pumped Storage',
        'B11': 'Hydro Run-of-river and poundage',
        'B12': 'Hydro Water Reservoir',
        'B13': 'Marine',
        'B14': 'Nuclear',
        'B15': 'Other renewable',
        'B16': 'Solar',
        'B17': 'Waste',
        'B18': 'Wind Offshore',
        'B19': 'Wind Onshore',
        'B20': 'Other',
        'B21': 'AC Link',
        'B22': 'DC Link',
        'B23': 'Substation',
        'B24': 'Transformer'}
    
    COUNTRY_MAPPINGS = {
        'DE': '10Y1001A1001A83F',
        'FR': '10YFR-RTE------C',
        'BE': '10YBE----------2',
        'AT': '10YAT-APG------L',
        'NL': '10YNL----------L'
        }
    
    

    def __init__(self, BASE_URL="https://web-api.tp.entsoe.eu/api?"):
        self.api_key = None
        self.country_code = None
        self.start_date = None
        self.end_date = None
        self.url = BASE_URL
        self.date_ranges = []
      
    @property
    def country_mappings(self):
        my_dict = {
            'DE': '10Y1001A1001A83F',
            'FR': '10YFR-RTE------C',
            'BE': '10YBE----------2',
            'AT': '10YAT-APG------L',
            'NL': '10YNL----------L'
            }
        return my_dict

    def set_api_key(self, api_key):
        self.api_key = api_key

    def set_country(self, country):
        self.country_code = self.COUNTRY_MAPPINGS[country]

    # def set_date_range(self, start_date, end_date):
    #     self.start_date = start_date
    #     self.end_date = end_date
    
    def set_date_range(self, start_date, end_date):
        berlin_tz = pytz.timezone('Europe/Berlin')

        # Initialize the list that will hold all the dictionaries
        date_ranges = []

        # Ensure start_date is always before end_date
        if start_date > end_date:
            start_date, end_date = end_date, start_date

        current_start_date = start_date
        while current_start_date < end_date:
            # Calculate the end date for the current range, but not beyond the original end_date
            one_year_later = self.add_years_to_date(current_start_date, 1)
            current_end_date = min(one_year_later, end_date)

            # Localize the datetime objects to 'Europe/Berlin'
            start_date_berlin = berlin_tz.localize(current_start_date)
            end_date_berlin = berlin_tz.localize(current_end_date)

            # Convert to UTC
            start_date_utc = start_date_berlin.astimezone(pytz.utc)
            end_date_utc = end_date_berlin.astimezone(pytz.utc)

            # Append the new range to the list
            date_ranges.append({
                'start_date': current_start_date,
                'end_date': current_end_date,
                'start_date_utc': start_date_utc,
                'end_date_utc': end_date_utc
            })

            # Move to the next range
            current_start_date = current_end_date

        self.date_ranges = date_ranges

    def add_years_to_date(self, original_date, years):
        """Add years to a datetime. Adjusts for leap year if necessary."""
        try:
            return original_date.replace(year=original_date.year + years)
        except ValueError:  # This handles adding to Feb 29 on a non-leap year.
            return original_date.replace(month=3, day=1, year=original_date.year + years)
        
        
    # def set_date_range(self, start_date, end_date):
    #     berlin_tz = pytz.timezone('Europe/Berlin')
        
        
        
    #     # Convert naive datetime to aware datetime in 'Europe/Berlin' timezone
    #     self.start_date = berlin_tz.localize(start_date)
    #     self.end_date = berlin_tz.localize(end_date)
        
    #     # Convert from 'Europe/Berlin' timezone to UTC
    #     self.start_date_utc = self.start_date.astimezone(pytz.utc)
    #     self.end_date_utc = self.end_date.astimezone(pytz.utc)

    def fetch_data(self, date_range):
        if not all([self.api_key, self.country_code]):
            raise ValueError("API Key, Country Code, Start Date, and End Date must all be set before fetching data.")

        headers = {
            'securityToken': self.api_key
        }

        params = {
            'securityToken': self.api_key,
            'documentType': 'A75',
            'processType': 'A16',
            'in_Domain': self.country_code,
            'periodStart': date_range['start_date_utc'].strftime('%Y%m%d%H%M'),
            'periodEnd': date_range['end_date_utc'].strftime('%Y%m%d%H%M')
        }

        response = requests.get(url=self.url, params=params)

        if response.status_code != 200:
            raise Exception(f"Error {response.status_code}: {response.text}")

        return response.text
    
    
    def aggregate_duplicates(self, df):
        # Aggregate on the raw data granularity (15 minutes in this case)
        df_aggregated = df.groupby(['Fuel Type', 'datetime']).agg({'Average Generation (MW)': 'sum'}).reset_index()
        return df_aggregated
    
    
    def transform_to_dataframe(self, xml_data):
        root = ElementTree.fromstring(xml_data)
        
        rows = []
        
        for time_series in root.findall(".//ns:TimeSeries", namespaces=self.NAMESPACE):
            psr_type_code = time_series.find(".//ns:psrType", namespaces=self.NAMESPACE).text
            psr_type = self.PSRTYPE_MAPPINGS.get(psr_type_code, psr_type_code)
            # Get mapped value or default to the code itself
    
            for period in time_series.findall(".//ns:Period", namespaces=self.NAMESPACE):
                resolution = period.find(".//ns:resolution", namespaces=self.NAMESPACE).text
                period_start_str = period.find(".//ns:timeInterval/ns:start", namespaces=self.NAMESPACE).text.replace('Z', '+00:00')
                period_start = datetime.fromisoformat(period_start_str)
                
                if period_start.minute != 0:
                    continue
                
                points = period.findall(".//ns:Point", namespaces=self.NAMESPACE)
                
                if resolution == "PT15M":  # If data is in 15-minute granularity
                    # Sum the values for duplicate psrTypes for the same 15-minute period
                    point_data = {}
                    for point in points:
                        position = int(point.find("ns:position", namespaces=self.NAMESPACE).text)
                        quantity = float(point.find("ns:quantity", namespaces=self.NAMESPACE).text)
                        point_data[position] = point_data.get(position, 0) + quantity
    
                    # Aggregate to hourly data
                    for i in range(1, len(point_data) + 1, 4):
                        if all(j in point_data for j in range(i, i + 4)):  # Check if all positions exist
                            hour_avg = sum([point_data[j] for j in range(i, i + 4)]) / 4
                            rows.append({
                                "psrType": psr_type,
                                "position": i,
                                "quantity": hour_avg
                            })
                
                # If data is already in hourly granularity, just extract it as is
                elif resolution in ["PT1H", "PT60M"]:
                    for point in points:
                        position = int(point.find("ns:position", namespaces=self.NAMESPACE).text)
                        quantity = float(point.find("ns:quantity", namespaces=self.NAMESPACE).text)
                        rows.append({
                            "psrType": psr_type,
                            "position": position,
                            "quantity": quantity
                        })
        
        df = pd.DataFrame(rows)
        df.rename(columns={
            'psrType': 'Fuel Type',
            'position': 'Hour Start',
            'quantity': 'Average Generation (MW)'
        }, inplace=True)
        
        df['Hour Start'] = df['Hour Start'].apply(lambda x: (x-1)//4)  # Convert position to hour start
        df['datetime'] = df.apply(lambda row: (period_start + timedelta(hours=row['Hour Start'])).replace(tzinfo=None), axis=1)
        
        # Aggregate duplicates before returning the dataframe
        df = self.aggregate_duplicates(df)
        
        # Convert the datetime column back to 'Europe/Berlin' timezone
        df['datetime'] = df['datetime'].dt.tz_localize('UTC').dt.tz_convert('Europe/Berlin').dt.tz_localize(None)
        
        return df

    
    def reshape_dataframe(self, df):
        # Map the Fuel Type to its human-readable name
        # df['Fuel Type'] = df['Fuel Type'].map(self.PSRTYPE_MAPPINGS)

        # Pivot the dataframe
        # df_pivot = df.pivot(index='datetime', columns='Fuel Type', values='Average Generation (MW)')
        df_pivot = df.pivot_table(index='datetime', columns='Fuel Type', values='Average Generation (MW)', aggfunc='mean')

        return df_pivot


    def get_generation_data(self):
        gen_df = pd.DataFrame()
        for date_range in self.date_ranges:
            xml_data = self.fetch_data(date_range)
            df = self.transform_to_dataframe(xml_data)
            df_reshaped = self.reshape_dataframe(df)
            if gen_df.empty:
                gen_df = df_reshaped.copy()
            else:
                gen_df = pd.concat([gen_df, df_reshaped])
        return gen_df
    
def reshape_dataframe(df, psrtype_mappings):
    # Map the Fuel Type to its human-readable name
    df['Fuel Type'] = df['Fuel Type'].map(psrtype_mappings)

    # Pivot the dataframe
    df_pivot = df.pivot(index='datetime', columns='Fuel Type', values='Average Generation (MW)')

    return df_pivot

    
# PSRTYPE_MAPPINGS = {
#     'A03': 'Mixed',
#     'A04': 'Generation',
#     'A05': 'Load',
#     'B01': 'Biomass',
#     'B02': 'Fossil Brown coal/Lignite',
#     'B03': 'Fossil Coal-derived gas',
#     'B04': 'Fossil Gas',
#     'B05': 'Fossil Hard coal',
#     'B06': 'Fossil Oil',
#     'B07': 'Fossil Oil shale',
#     'B08': 'Fossil Peat',
#     'B09': 'Geothermal',
#     'B10': 'Hydro Pumped Storage',
#     'B11': 'Hydro Run-of-river and poundage',
#     'B12': 'Hydro Water Reservoir',
#     'B13': 'Marine',
#     'B14': 'Nuclear',
#     'B15': 'Other renewable',
#     'B16': 'Solar',
#     'B17': 'Waste',
#     'B18': 'Wind Offshore',
#     'B19': 'Wind Onshore',
#     'B20': 'Other',
#     'B21': 'AC Link',
#     'B22': 'DC Link',
#     'B23': 'Substation',
#     'B24': 'Transformer'}


# if __name__ == '__main__':
#     # Define the date range using datetime objects. Adjust these as needed.
#     start_date = datetime.strptime('2023-10-01T00:00Z', '%Y-%m-%dT%H:%MZ')
#     end_date = datetime.strptime('2023-10-31T00:00Z', '%Y-%m-%dT%H:%MZ')
    
#     start_date = datetime(2023,1,1)
#     end_date = datetime(2024,2,1)
    
#     # Instantiate the ENTSOEData class and set necessary parameters
#     entsoe = ENTSOEData()
#     entsoe.set_api_key("4961d306-7fb4-410a-9bb0-165a59343d92")
#     entsoe.set_country("DE")
#     entsoe.set_date_range(start_date, end_date)

#     # Fetch and transform the data, and then print the resulting DataFrame
#     df = entsoe.get_generation_data()
#     # df_reshaped = reshape_dataframe(df, PSRTYPE_MAPPINGS)
#     # print(df_reshaped)


    
