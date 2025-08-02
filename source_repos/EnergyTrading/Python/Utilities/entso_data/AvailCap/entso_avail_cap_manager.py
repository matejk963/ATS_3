import os
import pandas as pd
from datetime import datetime, timedelta
import logging
from Utilities.entso_data.AvailCap.outage_fetch import EntsoeOutagesFetcher
from Utilities.entso_data.AvailCap.outage_merge import OutageDataMerger
from Utilities.entso_data.AvailCap.outage_curve_creator import OutageCurveCreator
from Utilities.entso_data.AvailCap.outage_to_av_cap import AvailableCapacityCalculator
from Database.DB_reader import Database

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class EntsoeOutagesMaster:
    def __init__(self, base_inst_cap_dir, outage_dir, output_dir, grid, grid_mapping, api_token):
        self.base_inst_cap_dir = base_inst_cap_dir
        self.outage_dir = outage_dir
        self.output_dir = output_dir
        self.grid = grid
        self.grid_mapping = grid_mapping
        self.api_token = api_token
        self.db = Database()

    def get_date_ranges(self):
        default_start_date = datetime(2019, 1, 1)
        default_end_date = datetime(2028, 1, 1)
        
        try:
            query = f"""
                SELECT MAX(forecast_date) as last_forecast_date
                FROM "FUND_AvailCap"."{self.grid_mapping[self.grid]['table_name']}_12"
            """
            last_forecast_date_result = pd.read_sql(query, self.db.connection_string)

            if not last_forecast_date_result.empty and pd.notna(last_forecast_date_result['last_forecast_date'].iloc[0]):
                last_forecast_date = last_forecast_date_result['last_forecast_date'].iloc[0]
                start_date = last_forecast_date - timedelta(days=7)
            else:
                start_date = default_start_date
        except Exception as e:
            logging.warning(f"Could not retrieve forecast_date for grid '{self.grid}', using default start date. Error: {e}")
            start_date = default_start_date

        end_date = datetime(datetime.now().year + 3, 12, 31)
        return start_date, end_date

    def should_run_process(self):
        try:
            query = f"""
                SELECT MAX(forecast_date) as last_forecast_date
                FROM "FUND_AvailCap"."{self.grid_mapping[self.grid]['table_name']}_12"
            """
            last_forecast_date_result = pd.read_sql(query, self.db.connection_string)

            if not last_forecast_date_result.empty and pd.notna(last_forecast_date_result['last_forecast_date'].iloc[0]):
                last_forecast_date = last_forecast_date_result['last_forecast_date'].iloc[0]
                return pd.Timestamp(last_forecast_date).date() < datetime.now().date()
        except Exception as e:
            logging.warning(f"Could not determine if process should run for grid '{self.grid}'. Error: {e}")
            return True

    def run(self):
        # if not self.should_run_process():
        #     logging.info(f"No updates required for grid '{self.grid}'. Exiting.")
        #     return

        # Get start and end dates for processing
        start_date, end_date = self.get_date_ranges()

        # Define the last date to save
        # last_date_to_save = datetime(end_date.year + 0,1,1)
        last_date_to_save = pd.to_datetime(datetime.now().date())

        logging.info(f"Running process for grid '{self.grid}' with start_date={start_date}, end_date={end_date}, last_date_to_save={last_date_to_save}")

        # Step 1: Fetch raw data
        fetcher = EntsoeOutagesFetcher(api_token=self.api_token, output_dir=self.outage_dir)
        # Fetch one year before the start date is before 2020
        if start_date < datetime(2020,1,1):
            fetch_start_date = datetime(2017,1,1)
        else:
            fetch_start_date = start_date - timedelta(days=5)
        fetcher.fetch_outages(grid=self.grid, start_date=fetch_start_date, end_date=end_date)

        # Step 2: Merge raw data into a dictionary
        merger = OutageDataMerger(self.outage_dir)
        merged_dict = merger.load_and_merge_dictionaries(grid=self.grid, start_date=start_date, end_date=end_date)

        # Step 3: Produce outage curves
        curve_creator = OutageCurveCreator(base_file_path=self.outage_dir, output_folder=self.output_dir)
        fcst_dates = pd.date_range(start=start_date + timedelta(hours=12), end=last_date_to_save + timedelta(hours=12), freq='D')
        curve_creator.get_outage_curves_for_all_units(grid=self.grid, fcst_dates=fcst_dates)

        # Step 4: Generate available capacity curves and save to database
        av_cap_calculator = AvailableCapacityCalculator(
            base_inst_cap_dir=self.base_inst_cap_dir,
            outage_dir=self.output_dir,  # Use the output directory with outage curves
            output_dir=os.path.join(self.base_inst_cap_dir, "AvCap"),
            grid=self.grid,
            grid_mapping=self.grid_mapping
        )
        # Pass start_date and last_date explicitly
        av_cap_calculator.calculate_available_capacity(start_date=start_date, last_date=last_date_to_save)


# Example usage
if __name__ == "__main__":
    base_inst_cap_dir = '//192.168.10.91/d/data/Data/Spot/Entso/InstCap'
    outage_dir = '//192.168.10.91/d/data/Data/Spot/Entso/Outages'
    output_dir = '//192.168.10.91/d/data/Data/Spot/Entso/Outages/Curves'


    grid_mapping = {
        # "10YRO-TEL------P": {"column_suffix": "_ro", "table_name": "ROU"},
        # "10YHU-MAVIR----U": {"column_suffix": "_hu", "table_name": "HUN"},
        "10YIT-GRTN-----B": {"column_suffix": "_it", "table_name": "ITA"}
        # "10YCZ-CEPS-----N": {'column_suffix': '_cz', 'table_name': 'CZE'},
        # "10YSK-SEPS-----K": {"column_suffix": "_sk", "table_name": "SVK"},
        # # "10Y1001A1001A82H": {"column_suffix": "_de", "table_name": "DEU"},
        # "10YAT-APG------L": {"column_suffix": "_at", "table_name": "AUT"},
        # "10YBE----------2": {"column_suffix": "_be", "table_name": "BEL"},        
        # "10YNL----------L": {"column_suffix": "_nl", "table_name": "NLD"},
    }

    api_token = "0e829f02-4563-482b-8a57-802b1e685c67"

    for grid in grid_mapping.keys():

        master = EntsoeOutagesMaster(base_inst_cap_dir, outage_dir, output_dir, grid, grid_mapping, api_token)
        master.run()

        logging.info("Process completed successfully.")
