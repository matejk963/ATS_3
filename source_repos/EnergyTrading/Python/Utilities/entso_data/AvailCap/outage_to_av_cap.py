import sys

sys.path.append(r'C:\Users\AS4user\Desktop\git-repos\EnergyTrading\Python')

import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import re
import logging
from Database.DB_reader import Database

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class AvailableCapacityCalculator:
    def __init__(self, base_inst_cap_dir, outage_dir, output_dir, grid, grid_mapping):
        self.base_inst_cap_dir = base_inst_cap_dir
        self.outage_dir = outage_dir
        self.output_dir = output_dir
        self.grid = grid
        self.inst_cap_path = self.construct_inst_cap_path()
        self.naming_dict = {
            'B01': 'Bio',
            'B02': 'Lig',
            'B04': 'Gas',
            'B05': 'Coal',
            'B06': 'Oil',
            'B14': 'Nuc'
        }
        self.fund = 'AvailCap'
        self.hour = '12'
        self.db = Database()
        self.default_last_forecast_date = datetime(2019, 1, 1)
        self.column_suffix = grid_mapping[grid]['column_suffix']
        self.table_name = grid_mapping[grid]['table_name']

    def construct_inst_cap_path(self):
        return os.path.join(self.base_inst_cap_dir, f"{self.grid}_inst_cap.parquet")

    def ensure_installed_capacity_resample(self, fcst_date):

        query = f"""
                SELECT *
                FROM "FUND_InstCap"."{self.table_name}_{self.hour}"
                WHERE forecast_date = '{fcst_date.strftime('%Y-%m-%d')}';
            """

        inst_cap = pd.read_sql(query, self.db.connection_string).set_index('value_date')

        # if pd.Timestamp(last_date) not in inst_cap.index:
        #     inst_cap.loc[pd.Timestamp(last_date)] = None
        inst_cap = inst_cap.resample('h').ffill().dropna()

        return inst_cap

    
    def get_last_forecast_date(self):
        try:
            query = f"""
                SELECT MAX(forecast_date) as last_forecast_date
                FROM "FUND_{self.fund}"."{self.table_name}_{self.hour}"
            """
            last_forecast_date_result = pd.read_sql(query, self.db.connection_string)

            if not last_forecast_date_result.empty and pd.notna(last_forecast_date_result['last_forecast_date'].iloc[0]):
                return last_forecast_date_result['last_forecast_date'].iloc[0]
        except Exception as e:
            logging.warning(f"Could not retrieve forecast_date from database for grid '{self.grid}', using default. Error: {e}")
        return self.default_last_forecast_date

    def save_to_database(self, file_path, forecast_date):
        logging.info(f"Saving data from file {file_path} with forecast_date={forecast_date} to database.")
        
        df = pd.read_parquet(file_path)

        # # Rename columns based on naming_dict
        # df.rename(columns=self.naming_dict, inplace=True)

        # # Drop columns not in naming_dict
        # df = df[[a for a in self.naming_dict.values() if a in df.columns]]

        # # Update column names to add suffix for the grid
        # df.columns = [f'{a}{self.column_suffix}' for a in df.columns]

        # Set forecast_date column
        df['forecast_date'] = forecast_date

        # Set value_date column and reset the index
        df['value_date'] = df.index
        df.reset_index(drop=True, inplace=True)

        # Save to SQL
        table_name = f"stage_{self.table_name}_{self.hour}"
        schema_name = f"FUND_{self.fund}"

        df.to_sql(name=table_name, schema=schema_name, con=self.db.connection_string, if_exists='replace', index=False)
        self.db.merge_from_staging_to_prod(schema_name, f"{self.table_name}_{self.hour}")                                                                                                                           


    def calculate_available_capacity(self, start_date, last_date):
        """
        Calculate available capacity using outage curves within the specified date range.

        :param start_date: The start date from which to process outage curves.
        :param last_date: The end date up to which to process outage curves.
        """

        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        # Ensure installed capacity data is prepared
        inst_cap = self.ensure_installed_capacity_resample(last_date)

        # Process outage files within the specified date range
        self.process_outage_files_in_date_range(inst_cap, start_date, last_date)

    def process_outage_files_in_date_range(self, inst_cap, start_date, last_date):
        """
        Process outage files for a specific date range.

        :param inst_cap: Installed capacity DataFrame.
        :param start_date: The start date of the range.
        :param last_date: The end date of the range.
        """
        file_filter = f'outage_curve_{self.grid}'

        for filename in os.listdir(self.outage_dir):
            if file_filter in filename and filename.endswith('.parquet'):
                match = re.search(r'_(\d{8})\.parquet$', filename)
                if not match:
                    logging.warning(f"Skipping file {filename}: No valid date found in the filename.")
                    continue

                file_date_str = match.group(1)
                file_date = datetime.strptime(file_date_str, '%Y%m%d')

                # Process files only within the specified date range
                if not (start_date <= file_date <= last_date):
                    logging.info(f"Skipping file {filename}: File date {file_date} not in range {start_date} to {last_date}.")
                    continue

                logging.info(f"Processing file {filename} for date {file_date}.")
                
                file_path = os.path.join(self.outage_dir, filename)
                test_outage = pd.read_parquet(file_path).reset_index()

                if {'PsrType', 'Timestamp', 'Outage (MW)'}.issubset(test_outage.columns):
                    test_outage['Timestamp'] = pd.to_datetime(test_outage['Timestamp'])
                    test_outage = test_outage[test_outage['Timestamp'] >= (file_date + timedelta(days=1))]

                    test_outage_pivot = test_outage.pivot(
                        index='Timestamp', columns='PsrType', values='Outage (MW)'
                    ).fillna(0)
                    test_outage_pivot.rename(columns=self.naming_dict, inplace=True)
                    test_outage_pivot = test_outage_pivot[[a for a in self.naming_dict.values() if a in test_outage_pivot.columns]]
                    test_outage_pivot.columns = [f'{a}{self.column_suffix}' for a in test_outage_pivot.columns]

                    # test_outage_pivot = test_outage_pivot.reindex(inst_cap.index, fill_value=0)
                    # Ensure installed capacity data is prepared
                    inst_cap = self.ensure_installed_capacity_resample(file_date)
                    # Pair outage to inst cap
                    temp_inst_cap = inst_cap.reindex(test_outage_pivot.index).ffill()
                    temp_inst_cap[test_outage_pivot.columns] = temp_inst_cap[test_outage_pivot.columns] - test_outage_pivot

                    result = temp_inst_cap.copy()
                    result = result[~result.index.duplicated(keep='first')].copy()
                    
                    # Save the last row
                    last_row = result.iloc[-1:]

                    # Drop duplicate rows based on the index
                    result = result.drop_duplicates(keep='first').copy()

                    # Add the saved last row back to the DataFrame
                    result = pd.concat([result, last_row]).drop_duplicates(keep='first').copy()

                    output_file_path = os.path.join(self.output_dir, f"av_cap_{filename}")
                    result.to_parquet(output_file_path)

                    self.save_to_database(output_file_path, file_date)


# Example usage
if __name__ == "__main__":
    base_inst_cap_dir = '//192.168.10.91/d/data/Data/Spot/Entso/InstCap'
    outage_dir = '//192.168.10.91/d/data/Data/Spot/Entso/Outages/Curves'
    output_dir = '//192.168.10.91/d/data/Data/Spot/Entso/Outages/AvCap'
    grid = "10YRO-TEL------P"

    grid_mapping = {
        "10YHU-MAVIR----U": {"column_suffix": "_hu", "table_name": "HUN"},
        "10YRO-TEL------P": {"column_suffix": "_ro", "table_name": "ROU"}
        # "10Y1001A1001A82H": {"column_suffix": "_de", "table_name": "DEU"}
        # Add other grids and their mappings here
    }
    start_date = datetime(2025, 2, 25)
    last_date = datetime(2025, 3, 12)

    calculator = AvailableCapacityCalculator(base_inst_cap_dir, outage_dir, output_dir, grid, grid_mapping)
    calculator.calculate_available_capacity(start_date, last_date)

    logging.info("Available capacity calculation and database update completed successfully.")
