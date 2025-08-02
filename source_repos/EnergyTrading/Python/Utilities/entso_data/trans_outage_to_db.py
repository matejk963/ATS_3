import sys
import os
import logging
import pandas as pd
from datetime import datetime, timedelta
from Database.DB_reader import Database
from avail_trans_creator import CountryPairAggregator  # Ensure the second script is importable

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ForecastDataFetcher:
    def __init__(self, countries, outages_folder, db_connection):
        self.countries = countries
        self.outages_folder = outages_folder
        self.forecast_table = 'AvailCap_trans'  # Hardcoded table name
        self.schema_name = 'FUND_Trans'  # Hardcoded schema name
        self.db = db_connection

    def get_last_forecast_date(self):
        """
        Retrieve the last forecast date from the database.
        If the table does not exist, set the first forecast date to 2019-01-01.
        """
        query = f"""
            SELECT MAX(forecast_date) as last_forecast_date
            FROM {self.schema_name}."{self.forecast_table}"
        """
        try:
            result = pd.read_sql(query, self.db.connection_string)
            if not result.empty and pd.notna(result['last_forecast_date'].iloc[0]):
                return pd.Timestamp(result['last_forecast_date'].iloc[0])
        except Exception as e:
            logging.warning(f"Table {self.forecast_table} does not exist or query failed: {e}")

        # Default to the initial forecast date if the table does not exist
        return pd.Timestamp("2019-01-01")

    def calculate_forecast_date_range(self, last_forecast_date):
        """
        Calculate the forecast date range: from the next day of the last forecast date
        to the end of the current year plus three years.
        """
        start_date = last_forecast_date + timedelta(days=1)
        end_date = pd.Timestamp(datetime(datetime.now().year + 3, 12, 31))
        return start_date, end_date

    def fetch_forecast_data(self):
        """
        Fetch forecast data using CountryPairAggregator for the calculated forecast date range.
        Combine hourly series for all pairs into a single DataFrame.
        """
        last_forecast_date = self.get_last_forecast_date()
        start_date, end_date = self.calculate_forecast_date_range(last_forecast_date)

        logging.info(f"Fetching data for forecast date range: {start_date} to {end_date}")

        aggregator = CountryPairAggregator(
            countries=self.countries,
            outages_folder=self.outages_folder,
            date_range=(start_date.strftime('%Y%m%d'), end_date.strftime('%Y%m%d')),
            forecast_date=start_date.strftime('%Y%m%d')
        )

        result = aggregator.calculate_imax_with_outages()

        # Combine hourly series into a single DataFrame
        combined_df = pd.DataFrame()

        for pair, data in result.items():
            logging.info(f"Processed pair: {pair}")
            hourly_curve = data['hourly_curve']
            hourly_curve.rename(columns={"net_imax": pair}, inplace=True)

            if combined_df.empty:
                combined_df = hourly_curve[[pair]].copy()
            else:
                combined_df = combined_df.join(hourly_curve[[pair]], how='outer')

        combined_df.index.name = 'Timestamp'

        # Save combined data to the database
        self.save_to_database(combined_df)

        return combined_df

    def save_to_database(self, combined_df):
        """
        Save the combined DataFrame to the database.
        """
        combined_df.reset_index(inplace=True)
        combined_df['forecast_date'] = datetime.now()

        try:
            combined_df.to_sql(
                name=self.forecast_table,
                schema=self.schema_name,
                con=self.db.connection_string,
                if_exists='replace',
                index=False
            )
            logging.info(f"Successfully saved combined data to table {self.schema_name}.{self.forecast_table}.")
        except Exception as e:
            logging.error(f"Failed to save combined data to database: {e}")


if __name__ == "__main__":
    countries = ['DE', 'FR']  # Specify the countries of interest
    outages_folder = r'W:\Data\Spot\Entso\Transmission'  # Folder containing outage pickle files

    # Initialize the database connection
    db_connection = Database()

    # Create and run the fetcher
    fetcher = ForecastDataFetcher(countries, outages_folder, db_connection)
    forecast_results = fetcher.fetch_forecast_data()

    logging.info("Forecast data fetching completed successfully.")
