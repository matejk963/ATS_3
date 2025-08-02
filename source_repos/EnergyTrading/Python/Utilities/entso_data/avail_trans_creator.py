
import sys

sys.path.append(r'C:\Users\AS4user\Desktop\git-repos\EnergyTrading\Python')

import os
import pandas as pd
import pickle
from itertools import permutations, combinations
from Database.DB_reader import Database
from datetime import datetime, timedelta

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

class CountryPairAggregator:
    def __init__(self, countries, outages_folder, date_range, forecast_date):
        self.countries = countries
        self.db = Database()  # Directly instantiate Database to use its connection
        self.outages_folder = outages_folder
        self.date_range = date_range  # Expected as a tuple (start_date, end_date)
        self.forecast_date = forecast_date  # Date when the forecast was made
        self.pairs = self._create_country_pairs()

    def _create_country_pairs(self):
        """Generate all unique pairs of countries."""
        return [f"{c1}_{c2}" for c1, c2 in combinations(self.countries, 2)]

    # def _aggregate_tielines(self):
    #     """Aggregate tielines data for the generated country pairs."""
    #     # Load tielines data from the database using pandas
    #     tielines_query = 'SELECT "Country_1", "Country_2", "EIC_Code", "IMax" FROM "FUND_Trans"."tielines"'
    #     tielines_df = pd.read_sql_query(tielines_query, con=self.db.connection_string)

    #     # Initialize the results dictionary
    #     aggregated_data = {}

    #     for pair in self.pairs:
    #         c1, c2 = pair.split('_')

    #         # Filter rows where country_1 and country_2 match the pair (in either order)
    #         pair_data = tielines_df[
    #             ((tielines_df['Country_1'] == c1) & (tielines_df['Country_2'] == c2)) |
    #             ((tielines_df['Country_1'] == c2) & (tielines_df['Country_2'] == c1))
    #         ]

    #         # Aggregate IMax and create lists of EIC codes and respective IMax
    #         total_imax = pair_data['IMax'].sum()
    #         eic_imax_list = pair_data[['EIC_Code', 'IMax']].values.tolist()

    #         aggregated_data[pair] = {
    #             'total_imax': total_imax,
    #             'eic_imax_list': eic_imax_list
    #         }

    #     return aggregated_data
    
    def _aggregate_tielines(self):
        """Aggregate tielines data for the generated country pairs."""
        # Load tielines data from the database using pandas
        # Load for both tielines and lines
        tielines_query = 'SELECT "Country_1", "Country_2", "EIC_Code", "IMax" FROM "FUND_Trans"."tielines"'
        tielines_df = pd.read_sql_query(tielines_query, con=self.db.connection_string)
        lines_query = 'SELECT "Country_1", "Country_2", "EIC_Code", "IMax" FROM "FUND_Trans"."lines"'
        lines_df = pd.read_sql_query(lines_query, con=self.db.connection_string)

        # Combine tielines and lines into a single DataFrame
        tielines_df = pd.concat([tielines_df, lines_df])

        # Initialize the results dictionary
        aggregated_data = {}

        for pair in self.pairs:
            c1, c2 = pair.split('_')

            # Filter rows for pair_data (including same-country connections)
            pair_data = tielines_df[
                ((tielines_df['Country_1'] == c1) & (tielines_df['Country_2'] == c2)) |
                ((tielines_df['Country_1'] == c2) & (tielines_df['Country_2'] == c1)) |
                ((tielines_df['Country_1'] == c1) & (tielines_df['Country_2'] == c1)) |
                ((tielines_df['Country_1'] == c2) & (tielines_df['Country_2'] == c2))
            ]
            
            pair_data = tielines_df.copy()

            # Filter rows for pair_data_tielines (strictly country pairs in either order)
            pair_data_tielines = tielines_df[
                ((tielines_df['Country_1'] == c1) & (tielines_df['Country_2'] == c2)) |
                ((tielines_df['Country_1'] == c2) & (tielines_df['Country_2'] == c1))
            ]

            # Aggregate IMax and create lists of EIC codes and respective IMax
            total_imax = pair_data['IMax'].sum()
            eic_imax_list = pair_data[['EIC_Code', 'IMax']].values.tolist()

            total_imax_tielines = pair_data_tielines['IMax'].sum()
            eic_imax_tielines_list = pair_data_tielines[['EIC_Code', 'IMax']].values.tolist()

            aggregated_data[pair] = {
                'pair_data': {
                    'total_imax': total_imax,
                    'eic_imax_list': {row[0]: row[1] for row in eic_imax_list}  # Dict for quick lookup
                },
                'pair_data_tielines': {
                    'total_imax': total_imax_tielines,
                    'eic_imax_list': {row[0]: row[1] for row in eic_imax_tielines_list}  # Dict for quick lookup
                }
            }

        return aggregated_data


    def _find_outage_files(self, pair):
        """Find all outage files for a given pair within the date range."""
        start_date, end_date = self.date_range

        # Use COUNTRY_TO_GRID to find the grid codes
        c1, c2 = pair.split('_')

        def get_grid_codes(country):
            if isinstance(COUNTRY_TO_GRID[country], dict):
                return list(COUNTRY_TO_GRID[country].values())
            return [COUNTRY_TO_GRID[country]]

        c1_codes = get_grid_codes(c1)
        c2_codes = get_grid_codes(c2)

        matched_files = []
        for file in os.listdir(self.outages_folder):
            for c1_code in c1_codes:
                for c2_code in c2_codes:
                    # Match files regardless of the order of grid codes
                    if f"transmission_{c1_code}_{c2_code}_" in file or f"transmission_{c2_code}_{c1_code}_" in file:
                        parts = file.replace('.pkl', '').split('_')
                        if len(parts) >= 4:
                            file_start, file_end = parts[-2], parts[-1]
                            # if start_date <= file_start <= end_date or start_date <= file_end <= end_date:
                            matched_files.append(os.path.join(self.outages_folder, file))
        return matched_files



    def _load_outages(self, pair):
        matched_files = self._find_outage_files(pair)
        merged_outages = {}

        for file in matched_files:
            with open(file, 'rb') as f:
                outages_data = pickle.load(f)
                for key, value in outages_data.items():
                    if key not in merged_outages:
                        merged_outages[key] = value
                    else:
                        for outage_mrid, revisions in value.items():
                            if outage_mrid not in merged_outages[key]:
                                merged_outages[key][outage_mrid] = revisions
                            else:
                                for revision_number, assets in revisions.items():
                                    if revision_number not in merged_outages[key][outage_mrid]:
                                        merged_outages[key][outage_mrid][revision_number] = assets
                                    else:
                                        merged_outages[key][outage_mrid][revision_number].update(assets)

        return merged_outages


    def _generate_hourly_curve(self, aggregated_data, outages_data):
        """Generate hourly values of total and net IMax."""
        start_date, end_date = self.date_range
        start_datetime = datetime.strptime(start_date, '%Y%m%d')
        end_datetime = datetime.strptime(end_date, '%Y%m%d')
        hourly_index = pd.date_range(start=start_datetime, end=end_datetime, freq='h')

        hourly_data = pd.DataFrame(index=hourly_index, columns=['total_imax', 'net_imax'])
        hourly_data['total_imax'] = aggregated_data['pair_data_tielines']['total_imax']
        hourly_data['net_imax'] = 0.

        for direction, details in outages_data.items():
            for direction2, details2 in details.items():
                for outage_id, outage_data in details2.items():
                    if outage_id == 'UO6KcVLz26PxNLg1U8787Q':
                        print('206')
                    for revision, revision_data in outage_data.items():
                        for asset, asset_details in revision_data.items():
                            created_datetime = asset_details.get('createdDateTime')
                            if created_datetime and created_datetime <= pd.to_datetime(self.forecast_date):
                                start = asset_details['start']
                                end = asset_details['end']
                                imax = aggregated_data['pair_data']['eic_imax_list'].get(asset)
                                if imax:
                                    if len(hourly_data.loc[start:end, 'net_imax'])>1:
                                        print('214')
                                    hourly_data.loc[start:end, 'net_imax'] -= imax

        hourly_data = hourly_data.resample('h').mean()
        return hourly_data




    def calculate_imax_with_outages(self):
        """Calculate the net IMax for each pair considering outages."""
        # Aggregate tielines data# The `aggregated_data = self._aggregate_tielines()` method in the
        # `CountryPairAggregator` class is responsible for aggregating
        # tielines data for the generated country pairs. Here's a breakdown
        # of what it does:
        
        aggregated_data = self._aggregate_tielines()

        results = {}

        for pair in self.pairs:
            c1, c2 = pair.split('_')

            # Load outages data for the pair
            outages_data = self._load_outages(pair)

            # Generate hourly curve for total and net IMax
            hourly_curve = self._generate_hourly_curve(aggregated_data[pair], outages_data)

            # Store the results
            results[pair] = {
                'total_imax': aggregated_data[pair]['pair_data_tielines']['total_imax'],
                'eic_imax_list': aggregated_data[pair]['pair_data_tielines']['eic_imax_list'],
                'hourly_curve': hourly_curve
            }

        return results

# Example usage
if __name__ == '__main__':
    countries = ['DE', 'FR']
    outages_folder = r'W:\Data\Spot\Entso\Transmission'  # Folder where outage pickle files are stored

    date_range = ('20200101', '20220101')  # Specify the date range for outages
    forecast_date = '20200101'  # Specify the forecast date

    aggregator = CountryPairAggregator(countries, outages_folder, date_range, forecast_date)
    result = aggregator.calculate_imax_with_outages()

    # Print results
    for pair, data in result.items():
        print(f"Pair: {pair}")
        print(f"  Total IMax: {data['total_imax']}")
        print(f"  EIC Codes and IMax: {data['eic_imax_list']}")
        print(f"  Hourly Curve:")
        print(data['hourly_curve'])
