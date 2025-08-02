# %%
import sys
import time

sys.path.append(r'C:\Users\AS4user\Desktop\git-repos\EnergyTrading\Python')

import pandas as pd
import datetime as dt
from Database.DB_reader import Database
from geopy.exc import GeocoderUnavailable, GeocoderTimedOut
from geopy.adapters import RequestsAdapter
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import requests


class TielineProcessor:
    def __init__(self, file_path, line_type='tielines',
                schema_name='FUND_Trans'):
        self.file_path = file_path
        self.schema_name = schema_name
        self.table_name = line_type
        self.line_type = line_type
        self.stage_table_name = f"stage_{line_type}"
        self.geolocator = Nominatim(user_agent="geoapi", timeout=10)  # Specify timeout here
        self.geolocation_cache = {}  # Cache for geolocation results
        self.neighboring_countries = {
            "BE": ["FR", "DE", "NL", "LU"],
            "FR": ["BE", "DE", "CH", "IT", "ES", "LU"],
            "DE": ["BE", "FR", "NL", "CZ", "AT", "CH", "PL", "LU"],
            "NL": ["BE", "DE"],
            "CZ": ["DE", "AT", "SK", "PL"],
            "SK": ["CZ", "HU", "AT", "PL"],
            "HU": ["SK", "AT", "RO", "HR"],
            "RO": ["HU", "BG", "UA"],
            "HR": ["HU", "SI", "BA"],
            "SI": ["HR", "AT", "IT"],
            "CH": ["FR", "DE", "IT", "AT"],
            "IT": ["FR", "CH", "SI"],
            "ES": ["FR"],
            "AT": ["DE", "CZ", "SK", "HU", "SI", "CH", "PL"],
            "PL": ["CZ", "DE", "SK", "AT", "PL"],
            "LU": ["BE", "FR", "DE", "LU"]
        }
        self.eic_to_original_name = {
            "BE": ["België", "Belgium", "Belgie"],
            "FR": ["France"],
            "DE": ["Deutschland", "Germany"],
            "NL": ["Nederland", "Netherlands"],
            "CZ": ["Česko", "Czech Republic"],
            "SK": ["Slovensko", "Slovakia"],
            "HU": ["Magyarország", "Hungary"],
            "RO": ["România", "Romania"],
            "HR": ["Hrvatska", "Croatia"],
            "SI": ["Slovenija", "Slovenia"],
            "CH": ["Schweiz", "Switzerland"],
            "IT": ["Italia", "Italy"],
            "ES": ["España", "Spain"],
            "AT": ["Österreich", "Austria"],
            "PL": ["Polska", "Poland"],
            "LU": ["Luxembourg", "Lëtzebuerg"]
        }
        # Reverse mapping for flexibility in matching
        self.original_name_to_eic = {
            name: code for code, names in self.eic_to_original_name.items() for name in names
        }



    def load_data(self):
        """Load the Excel file and copy the 'Tielines' sheet."""
        tielines = pd.read_excel(self.file_path, sheet_name=self.line_type.capitalize())
        self.df = tielines.copy()

    def wrangle_data(self):
        """Clean and process the dataframe."""
        if self.line_type == 'tielines':
            self.df = self.df.loc[:, :"Dynamic line rating (DLR)"].copy()
        elif self.line_type == 'lines':
            self.df = self.df.loc[:, :"Electrical Parameters"].copy()
        # Cut columns after DLR
        self.df.iloc[1:, 6:] = self.df.iloc[1:, 6:].apply(pd.to_numeric, errors='coerce')
        self.df["IMax"] = self.df.iloc[1:, 6:].mean(axis=1, skipna=True)
        self.df.iloc[0, 3] = "Substation_1"
        self.df.iloc[0, 4] = "Substation_2"
        self.df.iloc[0, -1] = 'IMax'
        self.df.columns = self.df.iloc[0]
        self.df = self.df[1:]
        self.df = self.df[['NE_name', 'EIC_Code', 'TSO', 'Substation_1', 'Substation_2', 'Voltage_level(kV)', 'IMax']].copy()
        self.df['date'] = dt.datetime(1970, 1, 1)

    def match_country_name(self, country_name):
        """Match country name, including slash-separated values, to an EIC code."""
        for name_part in country_name.split("/"):  # Split by '/'
            name_part = name_part.strip()  # Remove any surrounding whitespace
            if name_part in self.original_name_to_eic:
                return self.original_name_to_eic[name_part]
        return None  # Return None if no match is found

    def get_countries(self, city_name):
        """Get possible countries and their EIC codes for a city."""
        if city_name in self.geolocation_cache:
            return self.geolocation_cache[city_name]

        retries = 3
        delay = 1  # Initial delay for exponential backoff
        for attempt in range(retries):
            try:
                locations = self.geolocator.geocode(city_name, exactly_one=False, limit=5)
                if locations:
                    countries = []
                    for loc in locations:
                        country_name = loc.address.split(",")[-1].strip()
                        eic_code = self.match_country_name(country_name)
                        if eic_code:
                            countries.append((eic_code, (loc.latitude, loc.longitude)))
                    self.geolocation_cache[city_name] = countries
                    return countries
                else:
                    self.geolocation_cache[city_name] = []
                    return []
            except (GeocoderUnavailable, GeocoderTimedOut) as e:
                print(f"Geolocation attempt {attempt + 1} for '{city_name}' failed: {e}")
                time.sleep(delay)
                delay *= 2  # Exponential backoff
        print(f"Failed to geolocate '{city_name}' after {retries} attempts.")
        self.geolocation_cache[city_name] = []
        return []

    def get_shortest_distance_country(self, sub1, sub2, possible_countries):
        """Calculate shortest distance and return the associated country."""
        if not possible_countries:
            return "Unknown"
        distances = []
        try:
            sub2_coord = self.geolocator.geocode(sub2, timeout=10)  # Specify timeout for geocode
            if not sub2_coord:
                return "Unknown"
            for country, coord in possible_countries:
                dist = geodesic(coord, (sub2_coord.latitude, sub2_coord.longitude)).km
                distances.append((country, dist))
            return min(distances, key=lambda x: x[1])[0] if distances else "Unknown"
        except (GeocoderUnavailable, GeocoderTimedOut) as e:
            print(f"Error finding shortest distance between '{sub1}' and '{sub2}': {e}")
        return "Unknown"

    def add_countries(self):
        """Add Country_1 and Country_2 columns using EIC code or geolocation."""
        def get_country_from_eic(eic_code):
            """Extract countries from EIC code."""
            if pd.isna(eic_code):
                return "Unknown", "Unknown"
            parts = eic_code.split("-")
            if len(parts) >= 3 and parts[1] in self.neighboring_countries and parts[2] in self.neighboring_countries:
                return parts[1], parts[2]
            return "Unknown", "Unknown"

        self.df[['Country_1', 'Country_2']] = self.df['EIC_Code'].apply(lambda x: pd.Series(get_country_from_eic(x)))

        self.df['Country_1'] = self.df.apply(
            lambda row: self.get_shortest_distance_country(
                row['Substation_1'], row['Substation_2'], self.get_countries(row['Substation_1'])
            ) if row['Country_1'] == "Unknown" else row['Country_1'], axis=1
        )
        self.df['Country_2'] = self.df.apply(
            lambda row: self.get_shortest_distance_country(
                row['Substation_2'], row['Substation_1'], self.get_countries(row['Substation_2'])
            ) if row['Country_2'] == "Unknown" else row['Country_2'], axis=1
        )

    def save_to_db(self):
        """Save the dataframe to the database."""
        db = Database()
        self.df.to_sql(name=self.stage_table_name, schema=self.schema_name, con=db.connection_string, if_exists='replace', index=False)
        db.merge_from_staging_to_prod(self.schema_name, self.table_name)

    def process(self):
        """Complete processing pipeline."""
        self.load_data()
        self.wrangle_data()
        self.add_countries()
        self.save_to_db()


# Usage example:
if __name__ == '__main__':
    processor = TielineProcessor(file_path=r'W:\Data\Spot\Entso\20230920_Core Static Grid Model merged_v4.xlsx',
                                    line_type='lines')
    processor.process()
